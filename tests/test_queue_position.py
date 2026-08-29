"""
ZH: 排隊位置與等待原因（會議交辦 #8）。

ZH: 🔴 這裡守的是一種**不會被發現的錯**：位置算錯時畫面照樣顯示一個
    看起來很合理的數字，使用者沒有任何辦法察覺它是錯的。
    所以測試釘的是「與派工端同一套排序、同一個池」，不是「有沒有回傳數字」。

ZH: 桃園校區只有一張卡，而程式實驗室會**獨佔**它 —— 所以「有人開著實驗室」
    是最常見的等待原因。那條路徑有獨立的測試。
"""
import sys
import os
from datetime import datetime, timezone, timedelta

import pytest
from conftest import make_user

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "job-scheduler"))

from app import crud, models  # noqa: E402


def _job(db, user, name, pool="batch", priority=0, minutes_ago=0):
    j = models.TrainingJob(
        user_id=user.id, job_name=name, model_name="m", status="pending",
        pool_type=pool, priority=priority,
        created_at=datetime.now(timezone.utc) - timedelta(minutes=minutes_ago))
    db.add(j)
    db.commit()
    db.refresh(j)
    return j


@pytest.fixture
def u(db):
    return make_user(db, username="q1", email="q1@example.com")


# ══════════════════════════════════════════════════════════════════════════
# ZH: 一、順序要與派工端一致
# ══════════════════════════════════════════════════════════════════════════

def test_position_follows_submission_order(db, u):
    """ZH: 同優先權時先送的排前面（created_at ASC）。"""
    a = _job(db, u, "a", minutes_ago=30)
    b = _job(db, u, "b", minutes_ago=20)
    c = _job(db, u, "c", minutes_ago=10)
    q = crud.queue_info(db)
    assert [q[x.id]["position"] for x in (a, b, c)] == [1, 2, 3]
    assert q[a.id]["total"] == 3


def test_higher_priority_jumps_the_queue(db, u):
    """
    ZH: 🔴 排序是 `priority DESC, created_at ASC` —— 高優先權會插隊。
        只用送出時間算的話，被插隊的人看到的位置**永遠是錯的**，
        而且他等得越久越不合理，卻不知道為什麼。
    """
    old = _job(db, u, "old", minutes_ago=60)
    vip = _job(db, u, "vip", priority=10, minutes_ago=1)
    q = crud.queue_info(db)
    assert q[vip.id]["position"] == 1
    assert q[old.id]["position"] == 2


def test_positions_are_counted_within_the_same_pool(db, u):
    """
    ZH: 🔴 worker 拿到清單之後**還會再依 pool 篩一次**（見 routers/worker.py
        的 `_pool_allows`）。跨池一起數的話，批次任務會把互動任務算進自己的隊伍，
        位置就虛報了 —— 而那個數字看起來完全正常。
    """
    b1 = _job(db, u, "b1", pool="batch", minutes_ago=30)
    i1 = _job(db, u, "i1", pool="interactive", minutes_ago=20)
    b2 = _job(db, u, "b2", pool="batch", minutes_ago=10)
    q = crud.queue_info(db)
    assert (q[b1.id]["position"], q[b1.id]["total"]) == (1, 2)
    assert (q[b2.id]["position"], q[b2.id]["total"]) == (2, 2)
    assert (q[i1.id]["position"], q[i1.id]["total"]) == (1, 1)


def test_only_pending_jobs_are_counted(db, u):
    """ZH: 執行中／完成的不佔位子 —— 派工端的篩選就是 status=='pending'。"""
    running = _job(db, u, "running")
    running.status = "running"
    db.commit()
    waiting = _job(db, u, "waiting")
    q = crud.queue_info(db)
    assert running.id not in q
    assert q[waiting.id]["position"] == 1


def test_nothing_pending_returns_empty(db, u):
    assert crud.queue_info(db) == {}


# ══════════════════════════════════════════════════════════════════════════
# ZH: 二、等待原因
# ══════════════════════════════════════════════════════════════════════════

def test_reason_is_only_given_to_the_first_in_line(db, u):
    """
    ZH: 排在後面的人不需要解釋 —— 原因很明顯：前面有人。
        每一筆都掛一句「有人在用 GPU」只是噪音。
    """
    a = _job(db, u, "a", minutes_ago=20)
    b = _job(db, u, "b", minutes_ago=10)
    q = crud.queue_info(db)
    assert q[a.id]["reason"] is not None
    assert q[b.id]["reason"] is None


def test_lab_holding_the_gpu_is_reported(db, u, monkeypatch):
    """
    ZH: 🔴 桃園只有一張卡，程式實驗室會獨佔它 —— 這是最常見的等待原因。
        不講的話，使用者只看到「排隊中…」而完全不知道要等多久、
        也不知道該不該去問管理員。
    """
    j = _job(db, u, "waiting")
    # ZH: 有可派工的節點（不是「沒機器」），但卡被實驗室佔著。
    monkeypatch.setattr(crud, "pool_availability",
                        lambda _db, **kw: {"batch": {"available": True, "next_open": None}})
    monkeypatch.setattr(crud, "gpu_busy_reason", lambda _db: "lab")
    assert crud.queue_info(db)[j.id]["reason"] == "lab"


def test_outside_the_open_window_says_so(db, u, monkeypatch):
    """ZH: 「等時段」與「等機器上線」要分開 —— 使用者的下一步不同。"""
    j = _job(db, u, "waiting")
    monkeypatch.setattr(crud, "pool_availability",
                        lambda _db, **kw: {"batch": {"available": False,
                                                     "next_open": "2026-08-30T09:00:00+08:00"}})
    assert crud.queue_info(db)[j.id]["reason"] == "closed"


def test_no_machine_online_says_so(db, u, monkeypatch):
    monkeypatch.setattr(crud, "pool_availability",
                        lambda _db, **kw: {"batch": {"available": False, "next_open": None}})
    j = _job(db, u, "waiting")
    assert crud.queue_info(db)[j.id]["reason"] == "no_node"


# ══════════════════════════════════════════════════════════════════════════
# ZH: 三、端點真的帶出去
# ══════════════════════════════════════════════════════════════════════════

def test_the_list_endpoint_exposes_the_fields(client, db):
    """
    ZH: 🔴 清單是**手工組的 dict** —— 只在 schema 加欄位不會自動帶上
        （jobs.py 自己的註解說這個坑踩過兩次）。所以要驗真的走一次端點。
    """
    from conftest import auth_headers
    make_user(db, username="q2", email="q2@example.com")
    h = auth_headers(client, "q2", "password123")
    u2 = db.query(models.User).filter_by(username="q2").one()
    _job(db, u2, "a", minutes_ago=20)
    _job(db, u2, "b", minutes_ago=10)

    rows = client.get("/api/v1/jobs", headers=h).json()["jobs"]
    by_name = {r["job_name"]: r for r in rows}
    assert by_name["a"]["queue_position"] == 1
    assert by_name["b"]["queue_position"] == 2
    assert by_name["a"]["queue_total"] == 2
    assert "wait_reason" in by_name["a"]
