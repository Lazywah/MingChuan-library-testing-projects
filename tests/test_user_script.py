# -*- coding: utf-8 -*-
"""
ZH: v3.6 —— 自帶 .py 排程訓練。

ZH: 這個功能的本質是**讓使用者在 GPU 主機上執行任意 Python**，
    所以最要緊的不是「跑不跑得起來」，是**它看得到什麼**。

ZH: 🔴 開發前實測確認過一個既有的曝露：訓練容器掛的是
    `-v {STORAGE}:/workspace`，也就是共享儲存的**整個根目錄** ——
    容器裡 `cat /workspace/datasets/<別人的>/secret.txt` 讀得到。
    只跑平台自己的腳本時無害（它只讀被告知的路徑），
    但一開放自帶 .py，三行 Python 就能把全校的資料與模型撈走。
    所以掛載必須跟功能一起收窄。
"""
import pathlib
import sys

import pytest

from conftest import make_user, auth_headers

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "gpu-worker"))
import worker as gw   # noqa: E402

WORKER_AUTH = {"Authorization": "Bearer test-worker-token-16c"}

SCRIPT = "import os\nprint('hello from my own script')\n"


@pytest.fixture
def user_headers(client, db):
    make_user(db)
    return auth_headers(client)


def _heartbeat(client):
    client.post("/api/v1/worker/heartbeat",
                json={"node_id": "n1", "available_gpus": ["0"], "pool_type": "batch",
                      "shares_service_storage": True}, headers=WORKER_AUTH)


def _submit(client, headers, **over):
    body = {"job_name": "t", "model_name": "resnet18", "config": {"epochs": 1}}
    body.update(over)
    return client.post("/api/v1/jobs", headers=headers, json=body)


def _take(client):
    r = client.post("/api/v1/worker/take",
                    json={"node_id": "n1", "available_gpus": ["0"], "pool_type": "batch",
                          "shares_service_storage": True}, headers=WORKER_AUTH)
    return r.json()["job"]


# ──────────────────────────────────────────────────────────────────────────
# ZH: 一、送單與派工
# ──────────────────────────────────────────────────────────────────────────

def test_script_reaches_the_worker(client, db, user_headers):
    _heartbeat(client)
    assert _submit(client, user_headers, script_source=SCRIPT).status_code == 201
    assert _take(client)["script_source"] == SCRIPT


def test_user_script_wins_over_the_builtin(client, db, user_headers, tmp_path, monkeypatch):
    """ZH: 自己帶了程式就跑他的 —— 不該被換成內建腳本。

    ZH: ⚠ 這條**一定要同時帶資料集**。只帶腳本的話 `builtin_task_for` 本來就
        因為「沒有資料集」而回 None —— 測試會通過，但**是因為錯的理由**，
        把排除條件拿掉也照樣綠。（陽性對照抓到的，第一版就是這樣寫的。）
    """
    import io as _io
    import zipfile
    import uuid as _uuid
    from app.routers import datasets as dsr
    from app.routers import worker as wr
    root = f"/tmp/us_{_uuid.uuid4().hex[:8]}"
    monkeypatch.setattr(dsr, "DATASET_DIR", root)
    monkeypatch.setattr(wr, "DATASET_ROOT", root)

    z = _io.BytesIO()
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("cats/a.jpg", "x")
    ds_id = client.post("/api/v1/datasets/upload", headers=user_headers,
                        files={"file": ("d.zip", z.getvalue(), "application/zip")}
                        ).json()["dataset_id"]

    _heartbeat(client)
    assert _submit(client, user_headers, script_source=SCRIPT,
                   dataset_id=ds_id).status_code == 201
    job = _take(client)
    assert job["builtin_task"] is None, "帶了自己的程式卻被換成內建腳本"
    assert job["has_dataset"] is True          # 資料集照常送到（不是沒帶）


def test_script_does_not_trip_the_lab_gate(client, db, user_headers):
    """ZH: 🔴 自帶 .py **不需要**實驗室的檔案，所以不該被同機閘門擋下。

    ZH: 這正是「不沿用 `inline_code` 欄位」的理由：那個欄位是實驗室模式的判準，
        混用會讓自帶程式的單被錯誤地擋在遠端節點外（而遠端節點正是它該跑的地方）。
    """
    # ZH: 線上只有**不同機**的節點
    client.post("/api/v1/worker/heartbeat",
                json={"node_id": "remote", "available_gpus": ["0"], "pool_type": "batch",
                      "shares_service_storage": False}, headers=WORKER_AUTH)
    r = _submit(client, user_headers, script_source=SCRIPT)
    assert r.status_code == 201, r.text          # 送得出去（不是 503）

    got = client.post("/api/v1/worker/take",
                      json={"node_id": "remote", "available_gpus": ["0"],
                            "pool_type": "batch", "shares_service_storage": False},
                      headers=WORKER_AUTH).json()["job"]
    assert got is not None, "自帶程式的單被同機閘門擋住了"


def test_inline_code_still_trips_the_lab_gate(client, db, user_headers):
    """ZH: 陰性對照 —— 實驗室模式的閘門沒有被弄壞。"""
    client.post("/api/v1/worker/heartbeat",
                json={"node_id": "remote", "available_gpus": ["0"], "pool_type": "batch",
                      "shares_service_storage": False}, headers=WORKER_AUTH)
    assert _submit(client, user_headers, inline_code="echo hi").status_code == 503


def test_oversized_script_is_refused(client, db, user_headers):
    """ZH: 單一訓練腳本遠小於 256 KB；再大就不該走這條路。"""
    _heartbeat(client)
    assert _submit(client, user_headers, script_source="x" * 300000).status_code == 422


# ──────────────────────────────────────────────────────────────────────────
# ZH: 二、🔴 掛載範圍 —— 這是整個功能最要緊的一條
# ──────────────────────────────────────────────────────────────────────────

def test_narrow_mounts_do_not_expose_the_storage_root(monkeypatch, tmp_path):
    """ZH: 🔴 資料集這條路**不可以**把共享儲存的根目錄掛給容器。

    ZH: 掛了的話，容器裡看得到 `datasets/`（每一位使用者的資料）
        與 `outputs/`（每一張單的模型）。實測確認過那是讀得到的。
    """
    monkeypatch.setattr(gw, "STORAGE_MOUNT_PATH", str(tmp_path))
    monkeypatch.setattr(gw, "HOST_STORAGE_MOUNT", str(tmp_path))

    cmd = _build_cmd(gw, job_id="job-1", dataset_dir="/workspace/datasets/abc123",
                     builtin_task="image_classification", script_source=None)
    mounts = [cmd[i + 1] for i, a in enumerate(cmd) if a == "-v"]

    root_mount = f"{tmp_path}:/workspace"
    assert root_mount not in mounts, f"整個共享儲存被掛進去了：{mounts}"
    # ZH: 該掛的還是要掛
    assert any(m.endswith(":/workspace/dataset:ro") for m in mounts), mounts
    assert any(m.endswith(":/workspace/output:rw") for m in mounts), mounts


def test_dataset_is_mounted_read_only(monkeypatch, tmp_path):
    """ZH: 資料集唯讀 —— 使用者的程式不該改到快取（那是跨單共用的）。"""
    monkeypatch.setattr(gw, "STORAGE_MOUNT_PATH", str(tmp_path))
    cmd = _build_cmd(gw, job_id="job-1", dataset_dir="/workspace/datasets/abc123",
                     builtin_task=None, script_source=SCRIPT)
    mounts = [cmd[i + 1] for i, a in enumerate(cmd) if a == "-v"]
    ds = [m for m in mounts if "/workspace/dataset" in m]
    assert ds and ds[0].endswith(":ro"), ds


def test_user_script_gets_its_own_dir_not_the_shared_one(monkeypatch, tmp_path):
    """ZH: 使用者的程式放在**這張單專屬**的目錄，不與別人的混在一起。

    ZH: 混在共用的 scripts/ 裡就是另一種「看得到別人的東西」——
        別人的訓練程式也是他的東西。
    """
    monkeypatch.setattr(gw, "STORAGE_MOUNT_PATH", str(tmp_path))
    cmd = _build_cmd(gw, job_id="job-1", dataset_dir=None,
                     builtin_task=None, script_source=SCRIPT)
    mounts = [cmd[i + 1] for i, a in enumerate(cmd) if a == "-v"]
    code = [m for m in mounts if "/workspace/code" in m]
    assert code, mounts
    assert "jobscripts/job-1" in code[0].replace("\\", "/"), code
    assert code[0].endswith(":ro"), code


def test_lab_mode_keeps_the_old_broad_mount(monkeypatch, tmp_path):
    """ZH: 陰性對照 —— 實驗室與自訂入口那條路**維持原本的寬掛載**。

    ZH: 那是既有行為，這次不動它（風險與收益不成比例）。
        沒有這條的話，上面幾條在「所有路徑都被收窄」時也會綠，
        而那會悄悄改變實驗室的容器形狀。
    """
    monkeypatch.setattr(gw, "STORAGE_MOUNT_PATH", str(tmp_path))
    cmd = _build_cmd(gw, job_id="job-1", dataset_dir=None,
                     builtin_task=None, script_source=None)
    mounts = [cmd[i + 1] for i, a in enumerate(cmd) if a == "-v"]
    assert f"{tmp_path}:/workspace" in mounts, mounts


# ZH: 把 worker 裡那段掛載判準抽出來重現。**它必須與 worker.py 一致**，
#     所以下面那支測試直接讀原始碼確認判準沒有被改掉。
def _build_cmd(gw_mod, job_id, dataset_dir, builtin_task, script_source):
    S = gw_mod.STORAGE_MOUNT_PATH
    narrow = bool(dataset_dir or builtin_task or script_source)
    if narrow:
        mounts = [
            "-v", f"{S}/outputs/{job_id}:/workspace/output:rw",
            "-v", f"{S}/.torch:/workspace/.torch:rw",
        ]
        if dataset_dir:
            digest = dataset_dir.rsplit("/", 1)[-1]
            mounts += ["-v", f"{S}/datasets/{digest}:/workspace/dataset:ro"]
        if script_source:
            mounts += ["-v", f"{S}/jobscripts/{job_id}:/workspace/code:ro"]
        else:
            mounts += ["-v", f"{S}/scripts:/workspace/scripts:ro"]
    else:
        mounts = ["-v", f"{S}:/workspace"]
    return ["docker", "run", "--rm"] + mounts


def test_narrow_rule_matches_worker():
    """ZH: 🔴 上面那幾支測的是**重現的**判準。這一支確認 worker.py 裡的沒有變。

    ZH: 不釘住的話，有人改了 worker 的掛載邏輯而測試照樣全綠 ——
        那些綠燈就只是在測我自己抄的那份。
    """
    src = pathlib.Path(gw.__file__).read_text(encoding="utf-8")
    for needle in (
        'narrow = bool(dataset_dir or builtin_task or script_source)',
        '/outputs/{job_id}:/workspace/output:rw',
        '/datasets/{digest}:/workspace/dataset:ro',
        '/jobscripts/{job_id}:/workspace/code:ro',
        'storage_mounts = ["-v", f"{STORAGE_MOUNT_PATH}:/workspace"]',
    ):
        assert needle in src, f"worker.py 的掛載判準變了，但測試還在測舊的：{needle}"


def test_user_script_uses_the_platform_training_image(client, db, user_headers):
    """ZH: 自帶程式的單要用**平台的標準環境**，不是 worker 的精簡預設。

    ZH: 實測踩過：第一張自帶程式的單花了好幾分鐘在拉 4 GB 的公版 pytorch 映像，
        而那個映像裡沒有 torchvision / sklearn / pandas ——
        自己寫訓練程式的人幾乎一定需要那些。
    """
    from app import crud
    _heartbeat(client)
    assert _submit(client, user_headers, script_source=SCRIPT).status_code == 201
    assert _take(client)["docker_image"] == crud.PLATFORM_TRAINING_IMAGE


def test_user_chosen_image_still_wins(client, db, user_headers):
    """ZH: 陰性對照 —— 他自己選了就用他的。"""
    _heartbeat(client)
    assert _submit(client, user_headers, script_source=SCRIPT,
                   docker_image="aibase/tensorflow:2026-spring").status_code == 201
    assert _take(client)["docker_image"] == "aibase/tensorflow:2026-spring"


def test_lab_jobs_keep_the_worker_default(client, db, user_headers):
    """ZH: 陰性對照 —— 實驗室與自訂入口不受影響（None ＝ 交給 worker 決定）。"""
    _heartbeat(client)
    assert _submit(client, user_headers, entry_args=["./main", "-m", "x"]).status_code == 201
    assert _take(client)["docker_image"] is None
