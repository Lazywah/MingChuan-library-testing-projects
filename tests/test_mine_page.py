# -*- coding: utf-8 -*-
"""
ZH: v4.29 「我的資料與模型」—— 一頁兩區（擁有者 2026-09-24）。

ZH: 擁有者問了三件事，這一族各守一件：
      1. **「我的資料集也不能下載」** —— 上傳的那一包進去就出不來，
         本機弄丟就真的沒了。補 GET /datasets/{id}/download。
      2. **「模型不佔 2 GB？」** —— 不佔，但它有另一套規則（每人 N 個、TTL 天），
         而畫面上一條都沒講。補 GET /jobs/models，把規則本身一起回。
      3. **模型被清掉之後畫面只是讓下載鈕消失** —— 清掉的與從來沒有的
         長得一模一樣（artifact_bytes 都是 None）。補 artifact_purged_at，
         畫面才講得出「已過保留期」這句真話。

ZH: 檔名清理搬到 services/download_names（模型與資料集共用一份）——
    既有的 test_model_artifact 那幾條檔名測試同時在守它沒被改壞。

@node tests/test_mine_page.py
"""
import io
import os
import pathlib
import urllib.parse
import zipfile
from datetime import datetime, timedelta, timezone

import pytest

from conftest import make_user, auth_headers

WORKER_AUTH = {"Authorization": "Bearer test-worker-token-16c"}


# ── 兩個根目錄都指到暫存，不碰真實的 /data ──────────────────────────

@pytest.fixture(autouse=True)
def dataset_dir(monkeypatch):
    """ZH: 與 test_datasets 同一個做法（POSIX 形狀的路徑，見那邊的說明）。"""
    import shutil
    import uuid as _uuid
    from app.routers import datasets as ds
    from app.routers import worker as wr
    root = f"/tmp/mine_{_uuid.uuid4().hex[:8]}"
    monkeypatch.setattr(ds, "DATASET_DIR", root)
    monkeypatch.setattr(wr, "DATASET_ROOT", root)
    yield pathlib.Path(root)
    shutil.rmtree(root, ignore_errors=True)


@pytest.fixture(autouse=True)
def artifact_dir(tmp_path, monkeypatch):
    from app.routers import worker as wr
    monkeypatch.setattr(wr, "ARTIFACT_ROOT", str(tmp_path / "artifacts"))
    return tmp_path / "artifacts"


@pytest.fixture
def user_headers(client, db):
    make_user(db)
    return auth_headers(client)


def _zip(names=("cats/a.jpg", "dogs/b.jpg")):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for n in names:
            zf.writestr(n, "x" * 100)
    return buf.getvalue()


def _upload_ds(client, headers, name="我的貓狗圖片.zip"):
    r = client.post("/api/v1/datasets/upload", headers=headers,
                    files={"file": (name, _zip(), "application/zip")})
    assert r.status_code in (200, 201), r.text
    return r.json()["dataset_id"]


def _heartbeat(client):
    client.post("/api/v1/worker/heartbeat",
                json={"node_id": "n1", "available_gpus": ["0"], "pool_type": "batch",
                      "shares_service_storage": True}, headers=WORKER_AUTH)


def _submit(client, headers, name="t"):
    return client.post("/api/v1/jobs", headers=headers,
                       json={"job_name": name, "model_name": "resnet18",
                             "config": {"epochs": 1}}).json()["job_id"]


def _upload_model(client, job_id, payload=b"MODEL-BYTES"):
    r = client.post(f"/api/v1/worker/jobs/{job_id}/artifact",
                    files={"file": ("model.pt", payload, "application/octet-stream")},
                    headers=WORKER_AUTH)
    assert r.status_code == 200, r.text


def _age(db, job_id, days):
    """ZH: 把一張單的完成時間往回撥，讓 TTL 清理抓得到它。"""
    from app import models
    row = db.query(models.TrainingJob).filter_by(id=job_id).first()
    row.completed_at = datetime.now(timezone.utc) - timedelta(days=days)
    db.commit()


# ══════════════════════════════════════════════════════════════════════
# ZH: 一、資料集下載 —— 上傳的那一包要拿得回來
# ══════════════════════════════════════════════════════════════════════

def test_download_returns_the_uploaded_bytes(client, db, user_headers):
    """ZH: 拿到的必須是**真的那個檔**，而且檔名是當初上傳的中文名。"""
    ds_id = _upload_ds(client, user_headers, "我的貓狗圖片.zip")
    r = client.get(f"/api/v1/datasets/{ds_id}/download", headers=user_headers)
    assert r.status_code == 200, r.text
    assert r.content == _zip()
    cd = r.headers.get("content-disposition", "")
    assert "filename*=UTF-8''" in cd, cd
    assert urllib.parse.quote("我的貓狗圖片.zip", safe="") in cd, cd
    assert 'filename="' in cd, cd                     # 老瀏覽器看的 ASCII 版本


def test_another_user_gets_404_not_403(client, db):
    """ZH: 與刪除同一條規則：不是自己的回 404 —— 403 等於告訴對方這個 id 存在。"""
    make_user(db, username="alice", email="a@example.com")
    make_user(db, username="bob", email="b@example.com")
    alice, bob = auth_headers(client, "alice"), auth_headers(client, "bob")
    ds_id = _upload_ds(client, alice)
    r = client.get(f"/api/v1/datasets/{ds_id}/download", headers=bob)
    assert r.status_code == 404, r.text
    assert r.content != _zip()


def test_owner_can_still_download(client, db):
    """ZH: 陰性對照 —— 沒有這條，上一條在「下載整個壞掉」時也會綠。"""
    make_user(db, username="alice", email="a@example.com")
    alice = auth_headers(client, "alice")
    ds_id = _upload_ds(client, alice)
    assert client.get(f"/api/v1/datasets/{ds_id}/download", headers=alice).status_code == 200


def test_download_410_when_the_file_vanished(client, db, user_headers):
    """ZH: 紀錄在、檔案不在 → 410，與模型下載同一個分法（404 是「本來就沒有」）。"""
    from app import crud, models
    from app.routers import datasets as dsr
    ds_id = _upload_ds(client, user_headers)
    row = db.query(models.Dataset).filter_by(id=ds_id).first()
    os.remove(crud.dataset_file_path(dsr.DATASET_DIR, row))
    assert client.get(f"/api/v1/datasets/{ds_id}/download",
                      headers=user_headers).status_code == 410


def test_unknown_dataset_is_404(client, db, user_headers):
    assert client.get("/api/v1/datasets/no-such-id/download",
                      headers=user_headers).status_code == 404


def test_dataset_download_filename_is_sanitised(client, db, user_headers):
    """ZH: 原始檔名是使用者輸入的字串 —— 路徑字元一律清掉，副檔名不從原名猜。"""
    ds_id = _upload_ds(client, user_headers, "../../etc/passwd.zip")
    cd = client.get(f"/api/v1/datasets/{ds_id}/download",
                    headers=user_headers).headers.get("content-disposition", "")
    assert "/" not in cd and ".." not in cd, cd
    assert ".zip" in cd, cd


# ══════════════════════════════════════════════════════════════════════
# ZH: 二、模型跟著訓練單走 —— 規則要回、清掉的要講得出來、到期日要事先講
# ══════════════════════════════════════════════════════════════════════
# ZH: v4.30 兩頁合一之後沒有獨立的「模型清單」了：模型就是訓練單的一部分。
#     所以規則（retention）跟著 /jobs 列表回，每一列帶 model_expires_at。

def _jobs(client, headers):
    return client.get("/api/v1/jobs?limit=50", headers=headers).json()


def test_list_carries_the_retention_rules(client, db, user_headers):
    """ZH: 規則（每人幾個、幾天、單檔上限）跟著列表回 —— 前端不寫死。"""
    body = _jobs(client, user_headers)
    r = body["retention"]
    assert isinstance(r["keep"], int) and r["keep"] > 0
    assert isinstance(r["ttl_days"], int) and r["ttl_days"] > 0
    assert isinstance(r["max_bytes"], int)


def test_kept_model_says_when_it_expires(client, db, user_headers):
    _heartbeat(client)
    job_id = _submit(client, user_headers, "a")
    _upload_model(client, job_id, b"x" * 2048)
    row = {j["job_id"]: j for j in _jobs(client, user_headers)["jobs"]}[job_id]
    assert row["has_model"] is True and row["model_bytes"] == 2048
    assert row["model_expires_at"] is not None, "要事先講得出哪一天會被清"
    assert row["model_purged_at"] is None


def test_never_had_a_model_has_neither_date(client, db, user_headers):
    _heartbeat(client)
    job_id = _submit(client, user_headers, "no-model")
    row = {j["job_id"]: j for j in _jobs(client, user_headers)["jobs"]}[job_id]
    assert row["has_model"] is False
    assert row["model_expires_at"] is None and row["model_purged_at"] is None


def test_purged_model_is_marked_gone(client, db, user_headers, artifact_dir):
    """ZH: 🔴 清掉之後要說「清掉了」—— 不然下載鈕安靜消失，跟「平台弄丟了」分不出來。"""
    from app import crud
    from app.routers import worker as wr
    _heartbeat(client)
    job_id = _submit(client, user_headers, "old")
    _upload_model(client, job_id)
    _age(db, job_id, 99)
    assert crud.purge_expired_artifacts(db, 30, wr.remove_artifact_file)["removed"] == 1
    row = {j["job_id"]: j for j in _jobs(client, user_headers)["jobs"]}[job_id]
    assert row["has_model"] is False
    assert row["model_purged_at"] is not None
    assert row["model_expires_at"] is None


def test_evicted_by_the_keep_limit_is_also_marked(client, db, user_headers, monkeypatch):
    """ZH: 被「每人 N 個」擠掉的走同一條 purge，所以同樣要有記號。"""
    from app.routers import worker as wr
    monkeypatch.setattr(wr, "ARTIFACT_KEEP_PER_USER", 1)
    _heartbeat(client)
    first, second = _submit(client, user_headers, "1"), _submit(client, user_headers, "2")
    _upload_model(client, first)
    _upload_model(client, second)
    rows = {j["job_id"]: j for j in _jobs(client, user_headers)["jobs"]}
    assert rows[first]["has_model"] is False and rows[first]["model_purged_at"] is not None
    assert rows[second]["has_model"] is True and rows[second]["model_purged_at"] is None


def test_reupload_clears_the_purged_marker(client, db, user_headers):
    """ZH: 又有檔了就不算「被清掉」（同一張單重傳模型）。"""
    from app import crud
    from app.routers import worker as wr
    _heartbeat(client)
    job_id = _submit(client, user_headers)
    _upload_model(client, job_id)
    _age(db, job_id, 99)
    crud.purge_expired_artifacts(db, 30, wr.remove_artifact_file)
    _upload_model(client, job_id, b"again")
    row = {j["job_id"]: j for j in _jobs(client, user_headers)["jobs"]}[job_id]
    assert row["has_model"] is True and row["model_purged_at"] is None
