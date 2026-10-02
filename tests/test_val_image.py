# -*- coding: utf-8 -*-
"""
ZH: v4.36 「模型判斷錯的」那幾張圖 —— GET /jobs/{id}/val-image?path=…

ZH: 圖片分類訓練完，內建腳本會回報驗證資料裡判錯的圖（metrics 裡 kind="mistakes"，
    items[].path ＝ zip 成員名）。結果頁靠這支把圖從使用者上傳的 zip 拿出來。

ZH: 這一族守的是**端點的能力不能比用途大**：
      1. 只給這張單**自己回報過**的路徑 —— 不然就變成「讀任意 zip 成員」的入口
      2. 權限沿用本檔既有規則：學生只能看自己的單
      3. 回應碼分得開（404／410／413／415），前端據此退回只顯示檔名
      4. Content-Type 依副檔名、帶 nosniff（內容是使用者上傳的）

@node tests/test_val_image.py
"""
import io
import json
import zipfile

import pytest

from conftest import auth_headers, make_user

PNG = (b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)


def _zip(path, members):
    with zipfile.ZipFile(path, "w") as zf:
        for name, data in members.items():
            zf.writestr(name, data)
    return str(path)


def _job(db, user, zp, items, task_name="image"):
    from app import models
    j = models.TrainingJob(job_name="t", model_name="resnet18", status="completed",
                           user_id=user.id, dataset_path=zp,
                           config=json.dumps({"task": "image_classification"}),
                           metrics=json.dumps([
                               {"kind": "dataset", "classes": ["cats", "dogs"], "images": 2},
                               {"kind": "mistakes", "checked": 2, "wrong": len(items), "items": items},
                           ]))
    db.add(j)
    db.commit()
    return j.id


@pytest.fixture
def owner(client, db):
    u = make_user(db, username="owner1", email="owner1@example.com")
    return u, auth_headers(client, "owner1")


def _get(client, h, job_id, path):
    return client.get(f"/api/v1/jobs/{job_id}/val-image", params={"path": path}, headers=h)


# ── 1. 正常拿得到 ────────────────────────────────────────────────────

def test_returns_the_reported_image_bytes(client, db, owner, tmp_path):
    u, h = owner
    zp = _zip(tmp_path / "d.zip", {"data/cats/c1.png": PNG, "data/dogs/d1.jpg": b"JPEGDATA"})
    jid = _job(db, u, zp, [{"path": "data/cats/c1.png", "truth": "cats", "pred": "dogs"}])
    r = _get(client, h, jid, "data/cats/c1.png")
    assert r.status_code == 200, r.text
    assert r.content == PNG
    assert r.headers["content-type"] == "image/png"
    assert r.headers.get("x-content-type-options") == "nosniff"


# ── 2. 只給回報過的路徑 ──────────────────────────────────────────────

def test_unreported_member_is_refused_even_if_it_exists(client, db, owner, tmp_path):
    """ZH: 🔴 zip 裡明明有這張，但這張單沒回報過 —— 不給。"""
    u, h = owner
    zp = _zip(tmp_path / "d.zip", {"data/cats/c1.png": PNG, "data/dogs/d1.png": PNG})
    jid = _job(db, u, zp, [{"path": "data/cats/c1.png", "truth": "cats", "pred": "dogs"}])
    assert _get(client, h, jid, "data/dogs/d1.png").status_code == 404


def test_traversal_style_path_is_just_not_in_the_list(client, db, owner, tmp_path):
    u, h = owner
    zp = _zip(tmp_path / "d.zip", {"data/cats/c1.png": PNG})
    jid = _job(db, u, zp, [{"path": "data/cats/c1.png", "truth": "cats", "pred": "dogs"}])
    assert _get(client, h, jid, "../../etc/passwd").status_code == 404


def test_job_without_mistakes_metric_refuses_everything(client, db, owner, tmp_path):
    from app import models
    u, h = owner
    zp = _zip(tmp_path / "d.zip", {"a.png": PNG})
    j = models.TrainingJob(job_name="t", model_name="m", status="completed", user_id=u.id,
                           dataset_path=zp, metrics="not json")
    db.add(j)
    db.commit()
    assert _get(client, h, j.id, "a.png").status_code == 404


# ── 3. 權限 ─────────────────────────────────────────────────────────

def test_another_student_cannot_see_it(client, db, owner, tmp_path):
    u, _h = owner
    zp = _zip(tmp_path / "d.zip", {"c.png": PNG})
    jid = _job(db, u, zp, [{"path": "c.png", "truth": "cats", "pred": "dogs"}])
    make_user(db, username="other1", email="other1@example.com")
    assert _get(client, auth_headers(client, "other1"), jid, "c.png").status_code == 403


# ── 4. 回應碼分得開 ──────────────────────────────────────────────────

def test_deleted_dataset_is_410(client, db, owner, tmp_path):
    """ZH: 資料集被刪掉是正常會發生的事（自己刪、逾保留期）—— 410，前端退回只顯示檔名。"""
    u, h = owner
    zp = _zip(tmp_path / "d.zip", {"c.png": PNG})
    jid = _job(db, u, zp, [{"path": "c.png", "truth": "cats", "pred": "dogs"}])
    import os
    os.remove(zp)
    assert _get(client, h, jid, "c.png").status_code == 410


def test_unsupported_format_is_415(client, db, owner, tmp_path):
    u, h = owner
    zp = _zip(tmp_path / "d.zip", {"c.tif": b"TIFF"})
    jid = _job(db, u, zp, [{"path": "c.tif", "truth": "cats", "pred": "dogs"}])
    assert _get(client, h, jid, "c.tif").status_code == 415


def test_too_large_is_413(client, db, owner, tmp_path, monkeypatch):
    from app.routers import jobs as jr
    monkeypatch.setattr(jr, "_VAL_IMAGE_MAX_BYTES", 10)
    u, h = owner
    zp = _zip(tmp_path / "d.zip", {"c.png": PNG})
    jid = _job(db, u, zp, [{"path": "c.png", "truth": "cats", "pred": "dogs"}])
    assert _get(client, h, jid, "c.png").status_code == 413


def test_reported_but_missing_from_zip_is_404(client, db, owner, tmp_path):
    u, h = owner
    zp = _zip(tmp_path / "d.zip", {"other.png": PNG})
    jid = _job(db, u, zp, [{"path": "c.png", "truth": "cats", "pred": "dogs"}])
    assert _get(client, h, jid, "c.png").status_code == 404
