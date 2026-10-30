# -*- coding: utf-8 -*-
"""
ZH: 廠商交易日誌的兩個判讀錯誤（擁有者 2026-10-30 問「為啥我有用量？」查到的）。

ZH: (1) 回收（Recycle）被當成用 AI —— 被收回點數的人在總覽「有用量」，
        數據頁還多出「Recycle: delete」這種模型。
    (2) 即時用量那一格把廠商的**台灣當地時間**當成 UTC：時間窗被放寬 8 小時，
        顯示時又被加 8 小時（10:39 的事寫成 18:39）。

@node tests/test_myai_recycle_and_vendor_time.py
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app import models
from app.services import myai_sync as M


# ── (1) 回收不是用 AI ─────────────────────────────────────────────────

@pytest.mark.parametrize("note,pts", [
    ("Recycle: reclaim-live-test", -100),   # ZH: 被收回的那一方
    ("Recycle: delete", 300),               # ZH: 池子那一方
    ("recycle: 帳號回收", -1),
])
def test_recycle_is_a_transfer_not_ai_usage(note, pts):
    assert M._classify(note, pts) == ("transfer", None)


def test_real_usage_is_still_ai_usage():
    """ZH: 陰性對照 —— 改 Recycle 不能把真的用量一起改掉。"""
    assert M._classify("gpt_5_6_sol", -12) == ("ai_usage", "gpt_5_6_sol")


# ── (2) 即時用量用廠商當地時間 ─────────────────────────────────────────

def _bind(db, username):
    email = "%s@example.com" % username
    u = models.User(username=username, email=email, hashed_password="x", role="student")
    db.add(u)
    db.flush()
    db.add(models.ExternalAiAccount(user_id=u.id, vendor_username=email,
                                    myai_vendor_sn="sn-" + username, status="active"))
    db.commit()
    return u, email


def _usage(db, email, sn, local_when):
    db.add(models.MyaiTransaction(
        occurred_at=local_when, vendor_sn=sn, email=email, points_delta=-5,
        event_type="ai_usage", model="m", dedup_key=str(uuid.uuid4())))
    db.commit()


def _tw_now():
    return datetime.now(timezone.utc).astimezone(M.VENDOR_TZ).replace(tzinfo=None)


def test_recent_local_usage_is_counted_and_shown_in_taipei_time(db):
    u, email = _bind(db, "lt1")
    when = _tw_now() - timedelta(minutes=5)
    _usage(db, email, "sn-lt1", when)
    out = M.live_usage_quadrants(db, usage_minutes=15)
    rows = out["using_active"] + out["using_offplat"]
    assert [r["email"] for r in rows] == [email]
    # ZH: 🔴 帶 +08:00，時刻就是廠商記的那個時刻（不能被前端再加 8 小時）。
    got = datetime.fromisoformat(rows[0]["last_used_at"])
    assert got.utcoffset() == timedelta(hours=8)
    assert got.replace(tzinfo=None) == when


def test_usage_hours_ago_is_outside_the_window(db):
    """ZH: 🔴 原本的 bug：拿 UTC 比台灣時間，3 小時前的用量也會算成「最近 15 分鐘」。"""
    u, email = _bind(db, "lt2")
    _usage(db, email, "sn-lt2", _tw_now() - timedelta(hours=3))
    out = M.live_usage_quadrants(db, usage_minutes=15)
    assert out["using_active"] == [] and out["using_offplat"] == []


# ── (3) 「近 N 天」與同步區間也用廠商當地時間（擁有者 2026-10-30「修」）────────

def test_vendor_now_is_taipei_time():
    want = datetime.now(timezone.utc) + timedelta(hours=8)
    assert abs((M.vendor_now() - want.replace(tzinfo=None)).total_seconds()) < 5


def test_vendor_since_all_is_none():
    assert M.vendor_since(0) is None


def test_consumption_last_day_uses_local_time(client, db):
    """ZH: 🔴 原本起點用 UTC 的 now()：「近 1 天」會多吃進 8 小時，
        28 小時前的交易也被算進來。"""
    from conftest import make_user, auth_headers
    make_user(db, username="tz-adm", email="tz-adm@example.com", role="admin")
    h = auth_headers(client, "tz-adm", "password123")
    now = M.vendor_now()
    _usage(db, "x@example.com", "sn-x", now - timedelta(hours=28))   # ZH: 超過 1 天，不算
    _usage(db, "x@example.com", "sn-x", now - timedelta(hours=20))   # ZH: 1 天內，算
    r = client.get("/api/v1/external-ai/admin/consumption?days=1", headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["tx_count"] == 1


@pytest.mark.asyncio
async def test_sync_asks_the_vendor_up_to_the_local_date(db, monkeypatch):
    """ZH: 台灣凌晨 0–8 點時，UTC 的日期還是昨天 —— 當天凌晨的交易會晚 8 小時才進來。"""
    asked = []

    async def fake_fetch(start, end):
        asked.append((start, end))
        return "<html><body><table></table></body></html>"   # ZH: 沒有交易的那種頁面

    monkeypatch.setattr(M, "fetch_transactions_html", fake_fetch)
    await M.sync_transactions(db, days=3)
    assert asked[0][1] == M.vendor_now().strftime("%Y-%m-%d")
