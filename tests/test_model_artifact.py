# -*- coding: utf-8 -*-
"""
ZH: v3.6 —— 訓練出來的模型檔要能下載。

ZH: 缺口：model.pt 原本只留在**運算主機**上。跨機部署時服務層根本讀不到，
    畫面也就給不出下載——而「訓練完了卻拿不到東西」是最令人洩氣的結果。
    `output_path` 存的正是那個沒有意義的主機路徑（與 dataset_path 同一個陷阱）。

ZH: 這裡最要緊的兩件事：
      1. **權限** —— 別人的模型不能下載。這是唯一會外洩使用者成果的路徑。
      2. **界限** —— 上一次（GPU 主機快取）我留了一個會塞爆磁碟的空窗，
         這次同一個 commit 就要有上限，而且要測得到。
"""
import os

import pytest

from conftest import make_user, auth_headers

WORKER_AUTH = {"Authorization": "Bearer test-worker-token-16c"}


@pytest.fixture(autouse=True)
def artifact_dir(tmp_path, monkeypatch):
    """ZH: 把模型檔的存放位置指到 tmp，不要碰真實的 /data。"""
    from app.routers import worker as wr
    monkeypatch.setattr(wr, "ARTIFACT_ROOT", str(tmp_path / "artifacts"))
    return tmp_path / "artifacts"


@pytest.fixture
def user_headers(client, db):
    make_user(db)
    return auth_headers(client)


def _heartbeat(client):
    r = client.post("/api/v1/worker/heartbeat",
                    json={"node_id": "n1", "available_gpus": ["0"],
                          "pool_type": "batch", "shares_service_storage": True},
                    headers=WORKER_AUTH)
    assert r.status_code == 200


def _submit(client, headers, name="t"):
    return client.post("/api/v1/jobs", headers=headers,
                       json={"job_name": name, "model_name": "resnet18",
                             "config": {"epochs": 1}}).json()["job_id"]


def _upload(client, job_id, payload=b"MODEL-BYTES"):
    return client.post(f"/api/v1/worker/jobs/{job_id}/artifact",
                       files={"file": ("model.pt", payload, "application/octet-stream")},
                       headers=WORKER_AUTH)


# ──────────────────────────────────────────────────────────────────────────
# ZH: 一、上傳 → 下載這條路
# ──────────────────────────────────────────────────────────────────────────

def test_upload_then_download_returns_the_same_bytes(client, db, user_headers):
    """ZH: 拿到的必須是**真的那個檔**，不是一個長度對的空殼。"""
    _heartbeat(client)
    job_id = _submit(client, user_headers)
    assert _upload(client, job_id, b"REAL-MODEL-CONTENT").status_code == 200

    r = client.get(f"/api/v1/jobs/{job_id}/model", headers=user_headers)
    assert r.status_code == 200, r.text
    assert r.content == b"REAL-MODEL-CONTENT"


def test_status_reports_whether_a_model_exists(client, db, user_headers):
    """ZH: 前端靠 `has_model` 決定要不要顯示下載鈕，不要讓它自己猜。

    ZH: 訓練成功 != 檔案送到了 —— 傳輸可能失敗，那時模型還在運算主機上。
    """
    _heartbeat(client)
    job_id = _submit(client, user_headers)

    before = client.get(f"/api/v1/jobs/{job_id}", headers=user_headers).json()
    assert before["has_model"] is False
    assert before["model_bytes"] is None

    _upload(client, job_id, b"x" * 1234)
    after = client.get(f"/api/v1/jobs/{job_id}", headers=user_headers).json()
    assert after["has_model"] is True
    assert after["model_bytes"] == 1234


def test_download_404_when_the_job_has_no_model(client, db, user_headers):
    _heartbeat(client)
    job_id = _submit(client, user_headers)
    assert client.get(f"/api/v1/jobs/{job_id}/model", headers=user_headers).status_code == 404


def test_download_410_when_the_file_vanished(client, db, user_headers, artifact_dir):
    """ZH: DB 說有、檔案不在 -> **410 而不是 404**。

    ZH: 兩者要分得開：404 是「這張單本來就沒有模型」（正常），
        410 是「有過但不在了」（逾保留期，或出事了）。
        全落到 404 的話，管理者查不出到底是哪一種。
    """
    _heartbeat(client)
    job_id = _submit(client, user_headers)
    _upload(client, job_id)
    os.remove(artifact_dir / job_id / "model.pt")

    r = client.get(f"/api/v1/jobs/{job_id}/model", headers=user_headers)
    assert r.status_code == 410, r.text


def test_upload_requires_the_worker_token(client, db, user_headers):
    _heartbeat(client)
    job_id = _submit(client, user_headers)
    r = client.post(f"/api/v1/worker/jobs/{job_id}/artifact",
                    files={"file": ("model.pt", b"x", "application/octet-stream")})
    assert r.status_code == 401


# ──────────────────────────────────────────────────────────────────────────
# ZH: 二、權限 —— 這是唯一會外洩使用者成果的路徑
# ──────────────────────────────────────────────────────────────────────────

def test_a_student_cannot_download_another_users_model(client, db):
    """ZH: 別人的模型不能下載。"""
    make_user(db, username="alice", email="a@example.com")
    make_user(db, username="bob", email="b@example.com")
    alice = auth_headers(client, "alice")
    bob = auth_headers(client, "bob")

    _heartbeat(client)
    job_id = _submit(client, alice, "alice-model")
    _upload(client, job_id, b"ALICE-SECRET-MODEL")

    r = client.get(f"/api/v1/jobs/{job_id}/model", headers=bob)
    assert r.status_code == 403, r.text
    assert b"ALICE-SECRET-MODEL" not in r.content


def test_the_owner_can_download_it(client, db):
    """ZH: 陰性對照 —— 沒有這條，上一條在「下載整個壞掉」時也會綠。"""
    make_user(db, username="alice", email="a@example.com")
    alice = auth_headers(client, "alice")
    _heartbeat(client)
    job_id = _submit(client, alice, "alice-model")
    _upload(client, job_id, b"ALICE-SECRET-MODEL")
    r = client.get(f"/api/v1/jobs/{job_id}/model", headers=alice)
    assert r.status_code == 200
    assert r.content == b"ALICE-SECRET-MODEL"


def test_a_teacher_can_download_a_student_model(client, db):
    """ZH: 沿用本檔既有的權限規則（教師／管理員可看全部），不另發明一套。"""
    make_user(db, username="alice", email="a@example.com")
    make_user(db, username="teach", email="t@example.com", role="teacher")
    alice = auth_headers(client, "alice")
    teach = auth_headers(client, "teach")
    _heartbeat(client)
    job_id = _submit(client, alice)
    _upload(client, job_id, b"M")
    assert client.get(f"/api/v1/jobs/{job_id}/model", headers=teach).status_code == 200


def test_download_filename_is_sanitised(client, db, user_headers):
    """ZH: 檔名帶任務名稱比較好認，但那是**使用者輸入的字串**。"""
    _heartbeat(client)
    job_id = _submit(client, user_headers, name="../../etc/passwd")
    _upload(client, job_id)
    r = client.get(f"/api/v1/jobs/{job_id}/model", headers=user_headers)
    cd = r.headers.get("content-disposition", "")
    assert "/" not in cd and ".." not in cd, cd
    assert ".pt" in cd


# ──────────────────────────────────────────────────────────────────────────
# ZH: 三、界限 —— 不要重蹈「功能做完才補清理」的覆轍
# ──────────────────────────────────────────────────────────────────────────

def test_upload_rejects_an_oversized_file(client, db, user_headers, monkeypatch):
    """ZH: 上限是**邊寫邊數**的，不信任 Content-Length（那是請求方說了算）。"""
    from app.routers import worker as wr
    monkeypatch.setattr(wr, "MAX_ARTIFACT_BYTES", 100)
    _heartbeat(client)
    job_id = _submit(client, user_headers)
    r = _upload(client, job_id, b"x" * 5000)
    assert r.status_code == 413, r.text


def test_oversized_upload_leaves_no_half_file(client, db, user_headers,
                                              monkeypatch, artifact_dir):
    """ZH: 半套的檔案比沒有檔案更糟 —— 它看起來像有，下載下來卻是壞的。"""
    from app.routers import worker as wr
    monkeypatch.setattr(wr, "MAX_ARTIFACT_BYTES", 100)
    _heartbeat(client)
    job_id = _submit(client, user_headers)
    _upload(client, job_id, b"x" * 5000)

    assert not (artifact_dir / job_id / "model.pt").exists()
    assert client.get(f"/api/v1/jobs/{job_id}",
                      headers=user_headers).json()["has_model"] is False


def test_only_the_newest_n_artifacts_are_kept_per_user(client, db, user_headers,
                                                       monkeypatch, artifact_dir):
    """ZH: 每人保留 N 個是**硬上限** —— 沒有它，一個晚上跑一百張單就佔掉幾 GB。

    ZH: 在上傳當下就淘汰，不是等每日掃描：等一天的話界限等於不存在。
    """
    from app.routers import worker as wr
    monkeypatch.setattr(wr, "ARTIFACT_KEEP_PER_USER", 2)
    _heartbeat(client)

    ids = []
    for i in range(4):
        jid = _submit(client, user_headers, f"job-{i}")
        _upload(client, jid, f"model-{i}".encode())
        ids.append(jid)

    kept = [j for j in ids
            if client.get(f"/api/v1/jobs/{j}", headers=user_headers).json()["has_model"]]
    assert len(kept) == 2, kept
    # ZH: 留下來的必須是**最新的兩個**
    assert set(kept) == set(ids[-2:]), (kept, ids)
    # ZH: 而且實體檔案也真的不見了（DB 與檔案要一起處理）
    for j in ids[:-2]:
        assert not (artifact_dir / j / "model.pt").exists(), j


def test_one_user_uploads_do_not_evict_another(client, db, monkeypatch):
    """ZH: 陰性對照 —— 上限是**每人**的，不是全站的。"""
    from app.routers import worker as wr
    monkeypatch.setattr(wr, "ARTIFACT_KEEP_PER_USER", 1)
    make_user(db, username="alice", email="a@example.com")
    make_user(db, username="bob", email="b@example.com")
    alice, bob = auth_headers(client, "alice"), auth_headers(client, "bob")
    _heartbeat(client)

    a = _submit(client, alice, "a1")
    _upload(client, a)
    for i in range(3):
        _upload(client, _submit(client, bob, f"b{i}"))

    assert client.get(f"/api/v1/jobs/{a}", headers=alice).json()["has_model"] is True


def test_expired_artifacts_are_purged(client, db, user_headers, artifact_dir):
    """ZH: TTL 收拾的是「不再使用的帳號」留下的長尾。"""
    from datetime import datetime, timedelta, timezone
    from app import crud, models
    from app.routers import worker as wr

    _heartbeat(client)
    old_id = _submit(client, user_headers, "old")
    new_id = _submit(client, user_headers, "new")
    _upload(client, old_id)
    _upload(client, new_id)

    row = db.query(models.TrainingJob).filter_by(id=old_id).first()
    row.completed_at = datetime.now(timezone.utc) - timedelta(days=99)
    db.commit()

    stats = crud.purge_expired_artifacts(db, 30, wr.remove_artifact_file)
    assert stats["removed"] == 1, stats
    assert not (artifact_dir / old_id / "model.pt").exists()
    assert (artifact_dir / new_id / "model.pt").exists()


def test_cjk_job_name_survives_in_the_download_filename(client, db, user_headers):
    """ZH: 🔴 中文任務名要保得住。

    ZH: 只給 `filename=` 的話，中文會被清成空字串，於是**每個人下載到的都叫
        model.pt** —— 而這裡的任務名幾乎都是中文（來自 zip 的檔名）。
        實測踩過：任務叫「下載測試」，下載下來是 model.pt。
        解法是 RFC 5987 的 `filename*=UTF-8''…`。
    """
    import urllib.parse
    _heartbeat(client)
    job_id = _submit(client, user_headers, name="貓狗分類")
    _upload(client, job_id)

    cd = client.get(f"/api/v1/jobs/{job_id}/model",
                    headers=user_headers).headers.get("content-disposition", "")
    assert "filename*=UTF-8''" in cd, cd
    assert urllib.parse.quote("貓狗分類.pt", safe="") in cd, cd
    # ZH: 純 ASCII 的保守版本也要在（老瀏覽器看那個）
    assert 'filename="' in cd, cd
