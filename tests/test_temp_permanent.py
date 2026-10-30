# -*- coding: utf-8 -*-
"""
ZH: v4.20 —— 臨時帳號可以「永久有效」（擁有者 2026-09-21）。

ZH: 測試期間管理者手動建立的帳號要能長期存在，但仍然看得出「是誰為了什麼開的」——
    所以是「不設到期日」而不是「變成一般帳號」：`temp_purpose` 仍然必填、仍然留著。

ZH: 🔴 最重要的一條是 `test_missing_both_is_refused`：兩個都不給時**不可以默默當成永久**。
    那會讓「忘記填日期」變成「開了一個永遠不會消失的帳號」，而且沒有人會發現。

@node tests/test_temp_permanent.py
"""
import datetime

import pytest

from conftest import make_user, auth_headers


@pytest.fixture
def admin_headers(client, db):
    make_user(db, username="adm", email="adm@example.com", role="admin")
    return auth_headers(client, "adm", "password123")


def _day(n):
    return (datetime.date.today() + datetime.timedelta(days=n)).isoformat()


def _create(client, headers, **over):
    body = {"username": "guest1", "purpose": "教育部訪視", "expires_on": _day(7)}
    body.update(over)
    return client.post("/api/v1/admin/users/temporary", json=body, headers=headers)


# ── 永久 ────────────────────────────────────────────────────────────────

def test_permanent_account_has_no_expiry(client, db, admin_headers):
    from app import models
    r = _create(client, admin_headers, never_expires=True, expires_on=None)
    assert r.status_code == 200, r.text
    assert r.json()["expires_at"] is None

    u = db.query(models.User).filter_by(username="guest1").first()
    assert u.expires_at is None
    assert u.is_active == 1


def test_permanent_account_keeps_its_purpose(client, db, admin_headers):
    """ZH: 沒有到期日之後，用途是唯一還看得出「這個帳號為什麼在」的東西。"""
    from app import models
    _create(client, admin_headers, never_expires=True, expires_on=None, purpose="長官視察")
    u = db.query(models.User).filter_by(username="guest1").first()
    assert u.temp_purpose == "長官視察"


def test_permanent_account_can_log_in(client, db, admin_headers):
    """ZH: 與一般帳號同形 —— 密碼登得進來，而且不會被到期判定擋掉。"""
    pw = _create(client, admin_headers, never_expires=True, expires_on=None).json()["password"]
    r = client.post("/api/v1/auth/login", data={"username": "guest1", "password": pw})
    assert r.status_code == 200, r.text


def test_permanent_account_is_not_expired(client, db, admin_headers):
    from app import models
    from app.auth import is_expired
    _create(client, admin_headers, never_expires=True, expires_on=None)
    assert is_expired(db.query(models.User).filter_by(username="guest1").first()) is False


def test_audit_says_permanent_not_null(client, db, admin_headers):
    """ZH: 稽核裡明寫 permanent —— 留 null 會讓人以為是漏記的。"""
    import json
    from app import models
    _create(client, admin_headers, never_expires=True, expires_on=None)
    row = db.query(models.AdminAction).filter_by(action="create_temp_account").first()
    assert json.loads(row.payload)["expires_on"] == "permanent"


# ── 兩個欄位的互斥 ───────────────────────────────────────────────────────

def test_missing_both_is_refused(client, db, admin_headers):
    """ZH: 🔴 兩個都不給 → 422，**不可以默默當成永久**。"""
    from app import models
    r = _create(client, admin_headers, expires_on=None)
    assert r.status_code == 422, r.text
    assert db.query(models.User).filter_by(username="guest1").first() is None


def test_both_together_is_refused(client, db, admin_headers):
    """ZH: 勾了永久又填日期是矛盾的輸入 —— 不要自己挑一個來用。"""
    r = _create(client, admin_headers, never_expires=True, expires_on=_day(7))
    assert r.status_code == 422, r.text


# ── 既有行為不變 ─────────────────────────────────────────────────────────

def test_dated_account_still_works(client, db, admin_headers):
    """ZH: 陰性對照 —— 沒勾永久時與 v4.19 逐字相同。"""
    from app import models
    r = _create(client, admin_headers)
    assert r.status_code == 200, r.text
    assert r.json()["expires_at"] is not None
    assert db.query(models.User).filter_by(username="guest1").first().expires_at is not None


def test_extend_refuses_a_permanent_account(client, db, admin_headers):
    """ZH: 永久帳號沒有到期日可以延 —— 要明確拒絕，不要默默寫一個到期日進去
       （那會把永久帳號變回臨時帳號）。"""
    from app import models
    _create(client, admin_headers, never_expires=True, expires_on=None)
    uid = db.query(models.User).filter_by(username="guest1").first().id
    r = client.post(f"/api/v1/admin/users/{uid}/extend",
                    json={"expires_on": _day(7), "confirm_username": "guest1"},
                    headers=admin_headers)
    assert r.status_code == 400, r.text


# ══════════════════════════════════════════════════════════════════════
# ZH: v4.42 延期可以改成永久（擁有者 2026-10-30）
# ══════════════════════════════════════════════════════════════════════

def _uid(db, name):
    from app import models
    return db.query(models.User).filter_by(username=name).first().id


def test_extend_can_make_it_permanent(client, db, admin_headers):
    """ZH: 🔴 在此之前只能選一個日期 —— 想讓臨時帳號轉正只好設一個很遠的日子，
        而那種帳號到期時沒有人記得它為什麼在。"""
    import json as _json
    from app import models
    assert _create(client, admin_headers).status_code == 200

    r = client.post("/api/v1/admin/users/%s/extend" % _uid(db, "guest1"), headers=admin_headers,
                    json={"never_expires": True, "confirm_username": "guest1"})
    assert r.status_code == 200, r.text
    assert r.json()["expires_at"] is None
    db.expire_all()
    u = db.query(models.User).filter_by(username="guest1").first()
    assert u.expires_at is None and u.is_active == 1

    # ZH: 稽核要看得出是誰讓它永久的 —— 日後盤點永久帳號就靠這一筆。
    a = (db.query(models.AdminAction)
           .filter(models.AdminAction.action == "extend_temp_account").all())[-1]
    payload = _json.loads(a.payload)
    assert payload["never_expires"] is True
    assert payload["expires_on"] is None and payload["new_expires_at"] is None


def test_extend_rejects_both_a_date_and_never(client, db, admin_headers):
    """ZH: 兩個都給是矛盾的輸入 —— 該照哪一個沒有人說得準，所以直接擋。"""
    assert _create(client, admin_headers).status_code == 200
    r = client.post("/api/v1/admin/users/%s/extend" % _uid(db, "guest1"), headers=admin_headers,
                    json={"never_expires": True, "confirm_username": "guest1",
                          "expires_on": _day(9)})
    assert r.status_code == 422, r.text


def test_extend_rejects_neither(client, db, admin_headers):
    """ZH: 都不給等於沒說要改成什麼。"""
    assert _create(client, admin_headers).status_code == 200
    r = client.post("/api/v1/admin/users/%s/extend" % _uid(db, "guest1"), headers=admin_headers,
                    json={"confirm_username": "guest1"})
    assert r.status_code == 422, r.text


def test_extend_to_a_far_future_date(client, db, admin_headers):
    """ZH: v4.42 拿掉 90 天上限之後，延到一年後也要收。"""
    assert _create(client, admin_headers).status_code == 200
    r = client.post("/api/v1/admin/users/%s/extend" % _uid(db, "guest1"), headers=admin_headers,
                    json={"expires_on": _day(400), "confirm_username": "guest1"})
    assert r.status_code == 200, r.text
