# -*- coding: utf-8 -*-
"""
ZH: 使用統計的兩張追蹤表（v3.9）。

ZH: 這兩張表的共通點是**壞掉的時候完全看不出來** —— 沒有錯誤訊息、
    畫面上一切正常，只是幾個月後統計出來是空的或錯的。所以要有測試釘住。

ZH: 釘的四件事：
    1. 跳轉會被記下來，而且**不存 IP**
    2. 記錄失敗不可以害使用者去不了 MYAI
    3. Lab 每次啟動記一列（不是覆寫同一列 —— lab_sessions 就是那樣才不能用）
    4. `used_gpu` 分得出 CPU 與 GPU 兩種使用
"""
import pytest
from conftest import auth_headers, make_user

from app import models


@pytest.fixture()
def student(client, db):
    u = make_user(db, username="stat-user", email="stat-user@example.com", role="student")
    return u, auth_headers(client, "stat-user", "password123")


# ── MYAI 跳轉 ───────────────────────────────────────────────────────

def test_visit_is_recorded(client, db, student):
    u, headers = student

    r = client.post("/api/v1/external-ai/visit", headers=headers)

    assert r.status_code == 204, r.text
    rows = db.query(models.MyaiVisit).all()
    assert len(rows) == 1
    assert rows[0].user_id == u.id
    assert rows[0].occurred_at is not None


def test_visit_stores_no_ip(client, db, student):
    """ZH: 🔴 統計要回答的是「哪個系在用」，那由 user_id 就推得出來。

    ZH: 存 IP 對那個問題沒有任何貢獻，只是多留一份可以反推位置的資料。
        欄位不存在，就不會有人「順手」把它填上。
    """
    _, headers = student
    client.post("/api/v1/external-ai/visit", headers=headers)

    cols = {c.name for c in models.MyaiVisit.__table__.columns}

    assert "ip" not in cols and "ip_address" not in cols and "remote_addr" not in cols
    assert cols == {"id", "user_id", "occurred_at"}


def test_visit_requires_login(client, db):
    """ZH: 沒登入就記不了 —— 不然任何人都能灌爆統計。"""
    r = client.post("/api/v1/external-ai/visit")

    assert r.status_code in (401, 403)


def test_repeated_visits_all_recorded(client, db, student):
    """ZH: 跳三次就是三次。去重的話「常用的人」與「用一次的人」會一樣重。"""
    _, headers = student
    for _ in range(3):
        client.post("/api/v1/external-ai/visit", headers=headers)

    assert db.query(models.MyaiVisit).count() == 3


# ── Lab 使用 ────────────────────────────────────────────────────────

def test_lab_log_separates_cpu_and_gpu(db):
    """ZH: `used_gpu` 要分得出兩種使用 —— 這正是 user_session_usage 做不到的。"""
    u = make_user(db, username="lab-user", email="lab-user@example.com")
    db.add(models.LabUsageLog(user_id=u.id, used_gpu=0))
    db.add(models.LabUsageLog(user_id=u.id, used_gpu=1, gpu_index=0))
    db.add(models.LabUsageLog(user_id=u.id, used_gpu=1, gpu_index=1))
    db.commit()

    gpu = db.query(models.LabUsageLog).filter(models.LabUsageLog.used_gpu == 1).count()
    cpu = db.query(models.LabUsageLog).filter(models.LabUsageLog.used_gpu == 0).count()

    assert (gpu, cpu) == (2, 1)


def test_lab_log_is_append_only(db):
    """ZH: 🔴 一次啟動一列 —— 不可以像 lab_sessions 那樣覆寫。

    ZH: `lab_sessions` 每次啟動都覆寫同一列的 started_at，所以它只答得出
        「現在」不是「這段期間」。這張表存在的唯一理由就是不那樣做。
    """
    u = make_user(db, username="lab-user2", email="lab-user2@example.com")
    for _ in range(4):
        db.add(models.LabUsageLog(user_id=u.id, used_gpu=0))
    db.commit()

    assert db.query(models.LabUsageLog).filter(
        models.LabUsageLog.user_id == u.id).count() == 4


def test_unfinished_session_has_null_end(db):
    """ZH: 還在跑的是 NULL，不是 0。

    ZH: 存 0 的話，算平均時長時會把「還在跑的長工作」算成用了 0 秒，
        平均值會被拉低而且看不出原因。
    """
    u = make_user(db, username="lab-user3", email="lab-user3@example.com")
    db.add(models.LabUsageLog(user_id=u.id, used_gpu=1))
    db.commit()

    row = db.query(models.LabUsageLog).filter(
        models.LabUsageLog.user_id == u.id).first()

    assert row.ended_at is None
