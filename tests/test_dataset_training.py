# -*- coding: utf-8 -*-
"""
ZH: v3.6 —— 上傳一包分好類的圖片就能訓練（不必寫程式）。2a 後端部分。

ZH: 這條路徑之所以以前不會動，是因為三個缺口：
      1. 送給 worker 的 `dataset_path` 是**服務層容器裡**的絕對路徑，跨容器／跨機沒有意義
      2. 沒有任何地方會解壓
      3. `script_path` 預設指向不存在的 `/workspace/train.py`
    這裡測的是補起來的那三個缺口的服務層一側，加上 worker 端可以單獨測的純函式
    （下載、解壓、快取）。

ZH: 解壓那幾支刻意用**真的 zip 檔**測，不是 mock —— 路徑穿越與壓縮炸彈的防線
    如果只對假物件成立，那就等於沒有防線。
"""
import io
import os
import pathlib
import sys
import zipfile

import pytest

from conftest import make_user, auth_headers

WORKER_AUTH = {"Authorization": "Bearer test-worker-token-16c"}

# ZH: worker.py 不是套件，直接把它的目錄加進路徑再 import。
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "gpu-worker"))
import worker as gw   # noqa: E402


# ──────────────────────────────────────────────────────────────────────────
# ZH: 工具
# ──────────────────────────────────────────────────────────────────────────

def _heartbeat(client, node_id="n1", shares=True):
    r = client.post("/api/v1/worker/heartbeat",
                    json={"node_id": node_id, "available_gpus": ["0"],
                          "pool_type": "batch", "shares_service_storage": shares},
                    headers=WORKER_AUTH)
    assert r.status_code == 200, r.text
    return r


def _take(client, node_id="n1", shares=True):
    r = client.post("/api/v1/worker/take",
                    json={"node_id": node_id, "available_gpus": ["0"],
                          "pool_type": "batch", "shares_service_storage": shares},
                    headers=WORKER_AUTH)
    assert r.status_code == 200, r.text
    return r.json()["job"]


@pytest.fixture
def user_headers(client, db):
    make_user(db)
    return auth_headers(client)


@pytest.fixture
def dataset_file(tmp_path, monkeypatch):
    """ZH: 造一個真的 zip 放進「資料集根目錄」，並把根目錄指到 tmp。"""
    from app.routers import worker as wr
    root = tmp_path / "datasets" / "u1"
    root.mkdir(parents=True)
    z = root / "abc123_cats.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("cats/a.txt", "meow")
        zf.writestr("dogs/b.txt", "woof")
    monkeypatch.setattr(wr, "DATASET_ROOT", str(tmp_path / "datasets"))
    return z


def _submit(client, headers, **over):
    body = {"job_name": "t", "model_name": "resnet18", "config": {"epochs": 2}}
    body.update(over)
    return client.post("/api/v1/jobs", json=body, headers=headers)


# ──────────────────────────────────────────────────────────────────────────
# ZH: 一、take payload —— 送 worker 用得到的東西，不送沒有意義的容器路徑
# ──────────────────────────────────────────────────────────────────────────

def test_take_payload_has_dataset_flag_not_container_path(client, db, user_headers):
    """ZH: 有資料集時送 has_dataset + 檔名，且**不再送** dataset_path。

    ZH: 為什麼要斷言「不送」：留著那個欄位比拿掉更糟——它看起來像可以用，
        於是下一個人會直接拿去開檔，然後得到一個空目錄。
    """
    _heartbeat(client)
    assert _submit(client, user_headers,
                   dataset_path="/data/datasets/u1/abc_cats.zip").status_code == 201

    job = _take(client)
    assert job["has_dataset"] is True
    assert job["dataset_filename"] == "abc_cats.zip"
    assert "dataset_path" not in job


def test_take_payload_without_dataset(client, db, user_headers):
    """ZH: 陰性對照 —— 沒帶資料集時 has_dataset 為 False、沒有內建腳本。"""
    _heartbeat(client)
    assert _submit(client, user_headers).status_code == 201

    job = _take(client)
    assert job["has_dataset"] is False
    assert job["dataset_filename"] is None
    assert job["builtin_task"] is None


# ──────────────────────────────────────────────────────────────────────────
# ZH: 二、內建腳本的選定
# ──────────────────────────────────────────────────────────────────────────

def test_dataset_job_gets_the_builtin_task(client, db, user_headers):
    """ZH: 上傳資料又沒自己帶程式 → 平台提供腳本。"""
    _heartbeat(client)
    assert _submit(client, user_headers,
                   dataset_path="/data/datasets/u1/a.zip").status_code == 201
    assert _take(client)["builtin_task"] == "image_classification"


def test_inline_code_job_keeps_its_own_code(client, db, user_headers):
    """ZH: 自己帶程式的人不該被換成內建腳本 —— 他一定是想跑自己的東西。"""
    _heartbeat(client)
    assert _submit(client, user_headers, dataset_path="/data/datasets/u1/a.zip",
                   inline_code="echo hi").status_code == 201
    assert _take(client)["builtin_task"] is None


def test_entry_args_job_keeps_its_own_entry(client, db, user_headers):
    """ZH: 自訂入口（llama.cpp 那類）同理。"""
    _heartbeat(client)
    assert _submit(client, user_headers, dataset_path="/data/datasets/u1/a.zip",
                   entry_args=["./main", "-m", "x.gguf"]).status_code == 201
    assert _take(client)["builtin_task"] is None


def test_unknown_task_is_rejected_at_submit(client, db, user_headers):
    """ZH: 指名了不認得的種類 → 當場 400。

    ZH: 不可以默默退回預設種類：使用者指名 X 卻跑了 Y，結果會是
        「訓練成功但完全不是他要的東西」——那是最難查的一種失敗。
    """
    _heartbeat(client)
    r = _submit(client, user_headers, dataset_path="/data/datasets/u1/a.zip",
                config={"epochs": 2, "task": "speech_recognition"})
    assert r.status_code == 400, r.text
    assert "speech_recognition" in r.text


def test_known_task_is_accepted(client, db, user_headers):
    """ZH: 陰性對照 —— 認得的種類照收。"""
    _heartbeat(client)
    r = _submit(client, user_headers, dataset_path="/data/datasets/u1/a.zip",
                config={"epochs": 2, "task": "image_classification"})
    assert r.status_code == 201, r.text


# ──────────────────────────────────────────────────────────────────────────
# ZH: 三、資料集下載端點
# ──────────────────────────────────────────────────────────────────────────

def test_download_requires_worker_token(client, db, user_headers, dataset_file):
    r = client.get("/api/v1/worker/datasets/whatever")
    assert r.status_code == 401


def _job_with_dataset(client, headers, db, real_path):
    """ZH: 送一張單，然後把 dataset_path 直接改成磁碟上真實的檔案路徑。

    ZH: 為什麼不直接用 API 送：`JobCreate.dataset_path` 有字元白名單
        （防命令注入），而 Windows 的暫存路徑帶冒號，過不了驗證——
        那個驗證是對的，該繞過的是**測試**，不是驗證。
    """
    from app import models
    job_id = client.post("/api/v1/jobs",
                         json={"job_name": "t", "model_name": "resnet18",
                               "config": {"epochs": 2},
                               "dataset_path": "/data/datasets/u1/a.zip"},
                         headers=headers).json()["job_id"]
    row = db.query(models.TrainingJob).filter_by(id=job_id).first()
    row.dataset_path = str(real_path)
    db.commit()
    return job_id


def test_download_returns_the_file(client, db, user_headers, dataset_file):
    _heartbeat(client)
    job_id = _job_with_dataset(client, user_headers, db, dataset_file)

    d = client.get(f"/api/v1/worker/datasets/{job_id}", headers=WORKER_AUTH)
    assert d.status_code == 200, d.text
    # ZH: 拿到的必須是**真的那個 zip**，不是一個長度對的空殼
    with zipfile.ZipFile(io.BytesIO(d.content)) as zf:
        assert sorted(zf.namelist()) == ["cats/a.txt", "dogs/b.txt"]


def test_download_404_for_unknown_job(client, db, user_headers, dataset_file):
    r = client.get("/api/v1/worker/datasets/no-such-job", headers=WORKER_AUTH)
    assert r.status_code == 404


def test_download_404_when_job_has_no_dataset(client, db, user_headers):
    _heartbeat(client)
    job_id = _submit(client, user_headers).json()["job_id"]
    r = client.get(f"/api/v1/worker/datasets/{job_id}", headers=WORKER_AUTH)
    assert r.status_code == 404


def test_download_refuses_a_path_outside_the_dataset_root(client, db, user_headers,
                                                          dataset_file, tmp_path):
    """ZH: DB 裡的 dataset_path 被寫成根目錄以外的檔案時，必須拒絕。

    ZH: 縱深防禦——上傳端已經擋過一次，這裡不信任存下來的字串再擋一次。
        用的是一個**真的存在**的檔案，所以 404 只可能來自根目錄檢查，
        不會是「反正檔案不存在」那個分支。
    """
    outside = tmp_path / "secret.txt"
    outside.write_text("nope", encoding="utf-8")
    assert outside.is_file()

    _heartbeat(client)
    job_id = _job_with_dataset(client, user_headers, db, outside)
    r = client.get(f"/api/v1/worker/datasets/{job_id}", headers=WORKER_AUTH)
    assert r.status_code == 404
    assert b"nope" not in r.content


def test_download_404_when_the_file_is_gone(client, db, user_headers, dataset_file):
    """ZH: 檔案被清掉時是明確的 404，不是「跑起來但資料夾空的」。"""
    _heartbeat(client)
    job_id = _job_with_dataset(client, user_headers, db, dataset_file)
    os.remove(dataset_file)
    r = client.get(f"/api/v1/worker/datasets/{job_id}", headers=WORKER_AUTH)
    assert r.status_code == 404


# ──────────────────────────────────────────────────────────────────────────
# ZH: 四、worker 端的解壓防線（用真的 zip 檔測）
# ──────────────────────────────────────────────────────────────────────────

def _zip_with(tmp_path, members, name="in.zip"):
    z = tmp_path / name
    with zipfile.ZipFile(z, "w") as zf:
        for n, data in members:
            zf.writestr(n, data)
    return z


def test_extract_normal_archive(tmp_path):
    z = _zip_with(tmp_path, [("cats/a.txt", "x"), ("dogs/b.txt", "y")])
    dest = tmp_path / "out"
    n = gw.safe_extract_zip(z, dest)
    assert n == 2
    assert (dest / "cats" / "a.txt").read_text() == "x"


def test_extract_refuses_path_traversal(tmp_path):
    """ZH: zip slip —— 成員名字往上跳出目的地。"""
    z = _zip_with(tmp_path, [("../escaped.txt", "pwned")])
    with pytest.raises(ValueError, match="traversal"):
        gw.safe_extract_zip(z, tmp_path / "out")
    assert not (tmp_path / "escaped.txt").exists()


def test_extract_refuses_absolute_path(tmp_path):
    z = _zip_with(tmp_path, [("/etc/passwd", "pwned")])
    with pytest.raises(ValueError, match="absolute"):
        gw.safe_extract_zip(z, tmp_path / "out")


def test_extract_refuses_a_zip_bomb(tmp_path, monkeypatch):
    """ZH: 宣告解出來的大小超過上限就中止（不必真的做一顆炸彈）。"""
    z = _zip_with(tmp_path, [("big.bin", "0" * 5000)])
    monkeypatch.setattr(gw, "MAX_EXTRACT_BYTES", 1000)
    with pytest.raises(ValueError, match="expands to|size limit"):
        gw.safe_extract_zip(z, tmp_path / "out")


def test_extract_refuses_too_many_members(tmp_path, monkeypatch):
    z = _zip_with(tmp_path, [(f"f{i}.txt", "x") for i in range(20)])
    monkeypatch.setattr(gw, "MAX_EXTRACT_MEMBERS", 5)
    with pytest.raises(ValueError, match="members"):
        gw.safe_extract_zip(z, tmp_path / "out")


def test_extract_limit_is_enforced_while_writing_not_just_from_the_header(tmp_path, monkeypatch):
    """ZH: zip 標頭宣告的大小**是可以說謊的**，所以實際寫入時要再數一次。

    ZH: 怎麼測到第二道關：把第一道關（讀標頭）騙過去——讓 `_declared_size` 回 0，
        於是只剩寫入時那道關能擋。**沒有這個接縫，第二道關在測試裡永遠碰不到**，
        而「有寫但從來沒被驗證過」的防線和沒有防線是一樣的。
    """
    z = _zip_with(tmp_path, [("big.bin", "0" * 5000)])
    monkeypatch.setattr(gw, "_declared_size", lambda infos: 0)   # 標頭說謊
    monkeypatch.setattr(gw, "MAX_EXTRACT_BYTES", 1000)
    with pytest.raises(ValueError, match="understated"):
        gw.safe_extract_zip(z, tmp_path / "out")


def test_extract_header_gate_and_write_gate_are_separate(tmp_path, monkeypatch):
    """ZH: 陰性對照 —— 不騙標頭時，擋下來的是第一道關（訊息不同）。

    ZH: 兩支合起來才證明「兩道關都在、而且各自會動」。
    """
    z = _zip_with(tmp_path, [("big.bin", "0" * 5000)])
    monkeypatch.setattr(gw, "MAX_EXTRACT_BYTES", 1000)
    with pytest.raises(ValueError, match="expands to"):
        gw.safe_extract_zip(z, tmp_path / "out")


def test_sha256_is_content_based(tmp_path):
    """ZH: 快取鍵看內容不看檔名——同內容不同名要同 hash，反之要不同。"""
    a = tmp_path / "a.zip"; a.write_bytes(b"same")
    b = tmp_path / "b.zip"; b.write_bytes(b"same")
    c = tmp_path / "c.zip"; c.write_bytes(b"different")
    assert gw.file_sha256(a) == gw.file_sha256(b)
    assert gw.file_sha256(a) != gw.file_sha256(c)
