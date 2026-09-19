# -*- coding: utf-8 -*-
"""
ZH: v4.19（方案二 2.6 後半）—— 資料集內容摘要：上傳時算、派工時送、worker 先比快取。

ZH: 三段各守一件事：
      1. 上傳存下來的 sha256 就是檔案內容的 SHA-256（不是檔名、不是 uuid）。
      2. 派工 payload 帶 dataset_digest（前 16 碼）；舊資料（NULL）帶 None。
      3. worker 有 hint 且快取齊全 → **不下載**；沒快取 → 照常下載；hint 錯 → 信檔案。
    「前 16 碼」兩邊要同一個數字 —— 測試直接拿 crud.DATASET_DIGEST_CHARS 對 worker 的切片。

@node tests/test_dataset_digest.py
"""
import hashlib
import io
import pathlib
import sys
import zipfile

import pytest

from conftest import make_user, auth_headers

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "gpu-worker"))
import worker as gw   # noqa: E402

WORKER_AUTH = {"Authorization": "Bearer test-worker-token-16c"}


@pytest.fixture
def user_headers(client, db):
    make_user(db)
    return auth_headers(client)


@pytest.fixture(autouse=True)
def _dataset_root(tmp_path, monkeypatch):
    from app.routers import datasets as ds
    monkeypatch.setattr(ds, "DATASET_ROOT", tmp_path / "datasets", raising=False)


def _zip_bytes(members):
    z = io.BytesIO()
    with zipfile.ZipFile(z, "w") as zf:
        for n, data in members:
            zf.writestr(n, data)
    return z.getvalue()


def _upload(client, headers, data, name="d.zip"):
    r = client.post("/api/v1/datasets/upload", headers=headers,
                    files={"file": (name, data, "application/zip")})
    assert r.status_code == 200, r.text
    return r.json()


def _heartbeat_and_take(client):
    for path in ("heartbeat", "take"):
        r = client.post(f"/api/v1/worker/{path}",
                        json={"node_id": "n1", "available_gpus": ["0"],
                              "pool_type": "batch", "shares_service_storage": True},
                        headers=WORKER_AUTH)
        assert r.status_code == 200, r.text
    return r.json()["job"]


# ── 1. 上傳 ──────────────────────────────────────────────────────────────

def test_upload_stores_the_content_sha256(client, db, user_headers):
    from app import models
    data = _zip_bytes([("cats/a.txt", "x")])
    ds_id = _upload(client, user_headers, data)["dataset_id"]
    row = db.query(models.Dataset).filter_by(id=ds_id).first()
    assert row.sha256 == hashlib.sha256(data).hexdigest()


def test_same_content_different_name_same_digest(client, db, user_headers):
    """ZH: 摘要看內容不看檔名 —— 那正是快取能命中的原因。"""
    from app import models
    data = _zip_bytes([("cats/a.txt", "x")])
    a = _upload(client, user_headers, data, "one.zip")["dataset_id"]
    b = _upload(client, user_headers, data, "two.zip")["dataset_id"]
    rows = {r.id: r.sha256 for r in db.query(models.Dataset).all()}
    assert rows[a] == rows[b]


# ── 2. 派工 payload ──────────────────────────────────────────────────────

def test_take_payload_carries_the_digest_prefix(client, db, user_headers):
    from app import crud
    data = _zip_bytes([("cats/a.txt", "x")])
    up = _upload(client, user_headers, data)
    r = client.post("/api/v1/jobs", headers=user_headers,
                    json={"job_name": "t", "model_name": "resnet18",
                          "dataset_id": up["dataset_id"], "config": {"epochs": 1}})
    assert r.status_code == 201, r.text
    job = _heartbeat_and_take(client)
    want = hashlib.sha256(data).hexdigest()[:crud.DATASET_DIGEST_CHARS]
    assert job["dataset_digest"] == want
    # ZH: worker 那邊切的長度要一樣，不然永遠比不到（而且沒有錯誤）
    assert crud.DATASET_DIGEST_CHARS == 16


def test_take_payload_via_dataset_path_also_carries_it(client, db, user_headers):
    """ZH: V1 上傳後送單用的是 dataset_path（相容路徑）—— 也要解析到同一份資料集。"""
    data = _zip_bytes([("cats/a.txt", "x")])
    up = _upload(client, user_headers, data)
    r = client.post("/api/v1/jobs", headers=user_headers,
                    json={"job_name": "t", "model_name": "resnet18",
                          "dataset_path": up["dataset_path"], "config": {"epochs": 1}})
    assert r.status_code == 201, r.text
    assert _heartbeat_and_take(client)["dataset_digest"] == hashlib.sha256(data).hexdigest()[:16]


def test_legacy_dataset_without_digest_sends_none(client, db, user_headers):
    from app import models
    data = _zip_bytes([("cats/a.txt", "x")])
    up = _upload(client, user_headers, data)
    row = db.query(models.Dataset).filter_by(id=up["dataset_id"]).first()
    row.sha256 = None                       # ZH: 模擬 v4.19 之前上傳的
    db.commit()
    r = client.post("/api/v1/jobs", headers=user_headers,
                    json={"job_name": "t", "model_name": "resnet18",
                          "dataset_id": up["dataset_id"], "config": {"epochs": 1}})
    assert r.status_code == 201, r.text
    assert _heartbeat_and_take(client)["dataset_digest"] is None


def test_no_dataset_sends_none(client, db, user_headers):
    r = client.post("/api/v1/jobs", headers=user_headers,
                    json={"job_name": "t", "model_name": "resnet18", "config": {"epochs": 1}})
    assert r.status_code == 201, r.text
    assert _heartbeat_and_take(client)["dataset_digest"] is None


# ── 3. worker ───────────────────────────────────────────────────────────

@pytest.fixture
def storage(tmp_path, monkeypatch):
    monkeypatch.setattr(gw, "HOST_STORAGE_MOUNT", str(tmp_path))
    return tmp_path


def test_cached_digest_skips_the_download(storage, monkeypatch):
    """ZH: 🔴 快取齊全就不該碰網路 —— download_dataset 被呼叫就是失敗。"""
    cache = storage / "datasets" / "abcdefabcdefabcd"
    cache.mkdir(parents=True)
    (cache / ".ready").write_text("ok")

    def boom(job_id):
        raise AssertionError("download_dataset must not be called when the cache is ready")
    monkeypatch.setattr(gw, "download_dataset", boom)

    out = gw.prepare_dataset("job-1", "abcdefabcdefabcd")
    assert out.endswith("/datasets/abcdefabcdefabcd")


def test_digest_without_cache_downloads_normally(storage, monkeypatch, tmp_path):
    """ZH: 有 hint 但本機沒有 → 照常下載、解壓，目錄名用**算出來的**雜湊。"""
    z = tmp_path / "in.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("cats/a.txt", "x")
    real = gw.file_sha256(z)[:16]
    monkeypatch.setattr(gw, "download_dataset", lambda job_id: _copy(z, tmp_path / "dl.zip"))

    out = gw.prepare_dataset("job-2", real)
    assert out.endswith(f"/datasets/{real}")
    assert (storage / "datasets" / real / ".ready").exists()


def test_wrong_hint_trusts_the_file(storage, monkeypatch, tmp_path):
    """ZH: 服務層說的摘要與檔案不符 → 用檔案的，不要用錯的名字建快取。"""
    z = tmp_path / "in.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("cats/a.txt", "x")
    real = gw.file_sha256(z)[:16]
    monkeypatch.setattr(gw, "download_dataset", lambda job_id: _copy(z, tmp_path / "dl.zip"))

    out = gw.prepare_dataset("job-3", "0000000000000000")
    assert out.endswith(f"/datasets/{real}")
    assert not (storage / "datasets" / "0000000000000000").exists()


def test_half_extracted_cache_is_not_trusted_even_with_hint(storage, monkeypatch, tmp_path):
    """ZH: 有目錄沒 .ready ＝ 上次沒解完 —— hint 對也不能直接用。"""
    z = tmp_path / "in.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("cats/a.txt", "x")
    real = gw.file_sha256(z)[:16]
    (storage / "datasets" / real).mkdir(parents=True)          # ZH: 沒有 .ready
    called = []
    monkeypatch.setattr(gw, "download_dataset",
                        lambda job_id: called.append(1) or _copy(z, tmp_path / "dl.zip"))

    gw.prepare_dataset("job-4", real)
    assert called, "半套快取被當成完整的用了"
    assert (storage / "datasets" / real / ".ready").exists()


def _copy(src, dst):
    dst.write_bytes(pathlib.Path(src).read_bytes())
    return dst
