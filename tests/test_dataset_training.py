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


# ──────────────────────────────────────────────────────────────────────────
# ZH: 五、內建任務的映像指名（實跑之後補的）
# ──────────────────────────────────────────────────────────────────────────

def test_builtin_task_pins_its_image(client, db, user_headers):
    """ZH: 使用者沒選映像時，內建任務要指名一個**保證有 torchvision** 的映像。

    ZH: 這條是實跑逼出來的：我當時得手動指定映像才跑得起來。
        使用者從畫面送單不會指定，於是會落到 worker 的 DEFAULT_IMAGE，
        而那是「剛好有沒有 torchvision」的賭博——賭輸的症狀是容器一起來就
        ImportError，而使用者根本不知道自己選過映像。
    """
    from app import crud
    _heartbeat(client)
    assert _submit(client, user_headers,
                   dataset_path="/data/datasets/u1/a.zip").status_code == 201
    job = _take(client)
    assert job["docker_image"] == crud.builtin_task_image("image_classification")
    assert job["docker_image"]          # 不可以是 None


def test_user_chosen_image_wins(client, db, user_headers):
    """ZH: 使用者自己選了映像就用他的 —— 指名只是預設值，不是強制。"""
    _heartbeat(client)
    assert _submit(client, user_headers, dataset_path="/data/datasets/u1/a.zip",
                   docker_image="aibase/tensorflow:2026-spring").status_code == 201
    assert _take(client)["docker_image"] == "aibase/tensorflow:2026-spring"


def test_non_builtin_job_keeps_none_image(client, db, user_headers):
    """ZH: 陰性對照 —— 不是內建任務的單不受影響（None ＝ 交給 worker 的預設）。"""
    _heartbeat(client)
    assert _submit(client, user_headers).status_code == 201
    assert _take(client)["docker_image"] is None


# ──────────────────────────────────────────────────────────────────────────
# ZH: 六、實際在瀏覽器走一遍才查到的三件事（2b）
# ──────────────────────────────────────────────────────────────────────────

def test_cjk_filename_survives_upload_then_submit(client, db, user_headers, tmp_path):
    """ZH: 🔴 中文檔名讓「上傳→送單」整條路走不通。

    ZH: 症狀：上傳 `我的圖片.zip` 回 201，拿回傳的 dataset_path 去送單卻 422——
        因為 `JobCreate.dataset_path` 有字元白名單（防命令注入，那條是對的），
        而上傳端把原始檔名原封不動接進路徑。**中文檔名對這裡的使用者是常態。**
        修在上傳端：存到磁碟的名字不需要是使用者的名字。
    """
    import io as _io
    z = _io.BytesIO()
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("貓/a.jpg", "x")
    r = client.post("/api/v1/datasets/upload", headers=user_headers,
                    files={"file": ("我的圖片.zip", z.getvalue(), "application/zip")})
    assert r.status_code == 200, r.text
    path = r.json()["dataset_path"]

    # ZH: 這才是重點——回傳的路徑必須送得出去
    _heartbeat(client)
    s = client.post("/api/v1/jobs", headers=user_headers,
                    json={"job_name": "我的圖片", "model_name": "resnet18",
                          "dataset_path": path, "config": {"epochs": 1}})
    assert s.status_code == 201, f"中文檔名的路徑送不出去：{s.text}"


def test_upload_keeps_the_extension(client, db, user_headers):
    """ZH: 清檔名時**不可以把副檔名一起吃掉**。

    ZH: 第一版把整個名字（含副檔名）一起清再 strip('._-')，於是
        `我的圖片.zip` 變成 `..._zip` —— 上傳成功、送單成功、然後 worker 那邊
        會拿到一個沒有副檔名的東西。實測踩過。
    """
    import io as _io
    z = _io.BytesIO()
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("a/b.jpg", "x")
    r = client.post("/api/v1/datasets/upload", headers=user_headers,
                    files={"file": ("我的圖片.zip", z.getvalue(), "application/zip")})
    assert r.json()["dataset_path"].endswith(".zip"), r.json()["dataset_path"]


def test_job_status_returns_metrics(client, db, user_headers):
    """ZH: 🔴 指標存進 DB 了，但 `GET /jobs/{id}` 永遠回 null。

    ZH: 原因：那個端點回的是**手工組的 dict**，不是 ORM 物件——
        只在 JobStatusResponse 加欄位不會自動帶上。
        症狀是「後端明明有、前端永遠拿不到」，而兩邊各自看都正常。
    """
    _heartbeat(client)
    job_id = _submit(client, user_headers).json()["job_id"]

    for m in ({"kind": "dataset", "classes": ["a", "b"], "images": 10},
              {"kind": "epoch", "epoch": 1, "epochs": 2, "val_accuracy": 0.5}):
        u = client.post(f"/api/v1/worker/jobs/{job_id}/update",
                        json={"metric": m}, headers=WORKER_AUTH)
        assert u.status_code == 200, u.text

    got = client.get(f"/api/v1/jobs/{job_id}", headers=user_headers).json()
    assert isinstance(got.get("metrics"), list), got.get("metrics")
    assert len(got["metrics"]) == 2
    assert got["metrics"][0]["kind"] == "dataset"


def test_broken_metrics_json_does_not_break_the_whole_query(client, db, user_headers):
    """ZH: 指標壞掉時回 None，**不要讓整個任務查詢 500**——狀態與日誌還是要看得到。"""
    from app import models
    _heartbeat(client)
    job_id = _submit(client, user_headers).json()["job_id"]
    row = db.query(models.TrainingJob).filter_by(id=job_id).first()
    row.metrics = "{這不是合法的 JSON"
    db.commit()

    r = client.get(f"/api/v1/jobs/{job_id}", headers=user_headers)
    assert r.status_code == 200, r.text
    assert r.json()["metrics"] is None
    assert r.json()["status"] == "pending"


# ──────────────────────────────────────────────────────────────────────────
# ZH: 七、私有 registry 的映像前綴（worker 端）
# ──────────────────────────────────────────────────────────────────────────
# ZH: 為什麼前綴在 worker 而不是服務層：同機的節點該用本機映像、遠端的該從
#     registry 拉，**兩台的正確答案不同**。服務層送同一個字串必定有一邊是錯的。

def test_no_prefix_leaves_images_alone(monkeypatch):
    """ZH: 沒設 registry（單機部署）＝ 行為與加這個功能之前完全一樣。"""
    monkeypatch.setattr(gw, "IMAGE_REGISTRY_PREFIX", "")
    assert gw.resolve_image("aibase/pytorch:2026-spring") == "aibase/pytorch:2026-spring"


def test_prefix_is_added_to_platform_images(monkeypatch):
    monkeypatch.setattr(gw, "IMAGE_REGISTRY_PREFIX", "reg.example:5000")
    assert gw.resolve_image("aibase/pytorch:2026-spring") == \
        "reg.example:5000/aibase/pytorch:2026-spring"


def test_public_images_are_never_prefixed(monkeypatch):
    """ZH: 🔴 使用者可以指定公開映像。硬加前綴會讓它去私有 registry 找
       一個不存在的東西——而錯誤訊息會是「manifest unknown」，
       完全看不出是平台自己改了名字。
    """
    monkeypatch.setattr(gw, "IMAGE_REGISTRY_PREFIX", "reg.example:5000")
    for public in ("pytorch/pytorch:2.7.0-cuda12.8-cudnn9-runtime",
                   "ubuntu:22.04",
                   "ghcr.io/someone/thing:v1"):
        assert gw.resolve_image(public) == public, public


def test_already_prefixed_image_is_not_prefixed_twice(monkeypatch):
    """ZH: 有人把完整位址填進 docker_image 時不能再包一層。"""
    monkeypatch.setattr(gw, "IMAGE_REGISTRY_PREFIX", "reg.example:5000")
    full = "reg.example:5000/aibase/pytorch:2026-spring"
    assert gw.resolve_image(full) == full


def test_trailing_slash_in_prefix_does_not_double(monkeypatch):
    """ZH: 設定值寫成 `reg.example:5000/` 是很自然的手誤，不該變成 `//`。"""
    monkeypatch.setattr(gw, "IMAGE_REGISTRY_PREFIX", "reg.example:5000")
    assert "//" not in gw.resolve_image("aibase/pytorch:2026-spring")


def test_empty_image_is_safe(monkeypatch):
    monkeypatch.setattr(gw, "IMAGE_REGISTRY_PREFIX", "reg.example:5000")
    assert gw.resolve_image("") == ""


def test_login_is_skipped_without_a_registry(monkeypatch):
    """ZH: 沒設 registry 就不該去 docker login（單機部署根本沒有那個東西）。"""
    monkeypatch.setattr(gw, "IMAGE_REGISTRY_PREFIX", "")
    called = []
    monkeypatch.setattr(gw.subprocess, "run", lambda *a, **k: called.append(a))
    assert gw.registry_login() is False
    assert called == []


def test_login_warns_but_does_not_crash_without_credentials(monkeypatch):
    """ZH: 有 registry 卻沒帳密——可能是刻意匿名，更常是忘了設。
       要說出來，但**不能中止 worker**：它仍然可以跑不需要私有映像的任務。
    """
    monkeypatch.setattr(gw, "IMAGE_REGISTRY_PREFIX", "reg.example:5000")
    monkeypatch.setattr(gw, "REGISTRY_USERNAME", "")
    monkeypatch.setattr(gw, "REGISTRY_PASSWORD", "")
    assert gw.registry_login() is False


def test_login_never_puts_the_password_on_the_command_line(monkeypatch):
    """ZH: 🔴 密碼走 stdin。放在命令列會出現在 `ps` 與 docker 的警告裡。"""
    monkeypatch.setattr(gw, "IMAGE_REGISTRY_PREFIX", "reg.example:5000/aibase")
    monkeypatch.setattr(gw, "REGISTRY_USERNAME", "u")
    monkeypatch.setattr(gw, "REGISTRY_PASSWORD", "s3cr3t-password")
    seen = {}

    class R:
        returncode = 0
        stderr = ""

    def fake_run(cmd, **kw):
        seen["cmd"] = cmd
        seen["input"] = kw.get("input")
        return R()

    monkeypatch.setattr(gw.subprocess, "run", fake_run)
    assert gw.registry_login() is True
    assert "s3cr3t-password" not in " ".join(seen["cmd"]), seen["cmd"]
    assert seen["input"] == "s3cr3t-password"
    # ZH: 只把主機名餵給 docker login，不是整個前綴（前綴可能含路徑段）
    assert "reg.example:5000" in seen["cmd"]
    assert "reg.example:5000/aibase" not in seen["cmd"]
