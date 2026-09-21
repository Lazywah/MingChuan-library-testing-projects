# -*- coding: utf-8 -*-
"""
ZH: v4.20 —— 手動建立臨時帳號時：可指定密碼、可順手開通 MYAI（兩平台同一組密碼）。

ZH: 這一族的背景：MYAI 的開通**只有 SSO 首次登入那一條路**會觸發（sso.py），
    而臨時帳號是用密碼登入的 —— 在此之前它永遠不會有 MYAI 額度，
    而且沒有任何錯誤訊息，只有「進去之後發現沒有額度」。

ZH: 🔴 廠商呼叫一律 monkeypatch 掉。這些測試**絕對不可以真的打 MYAI** ——
    那會在廠商端建出真的帳號（刪不掉、而且會吃到點數池）。

@node tests/test_temp_password_myai.py
"""
import datetime

import pytest

from conftest import make_user, auth_headers


@pytest.fixture
def admin_headers(client, db):
    make_user(db, username="adm", email="adm@example.com", role="admin")
    return auth_headers(client, "adm", "password123")


@pytest.fixture
def fake_myai(monkeypatch):
    """ZH: 攔下 provision_user，記下被呼叫時帶的密碼。"""
    from app.services import myai_sync
    seen = {}

    async def fake(db, user, password=None):
        seen["username"] = user.username
        seen["password"] = password
        seen["email"] = user.email
        return {"status": "created", "email": user.email}

    monkeypatch.setattr(myai_sync, "provision_user", fake)
    return seen


def _day(n):
    return (datetime.date.today() + datetime.timedelta(days=n)).isoformat()


def _create(client, headers, **over):
    body = {"username": "guest1", "purpose": "長官視察", "expires_on": _day(7)}
    body.update(over)
    return client.post("/api/v1/admin/users/temporary", json=body, headers=headers)


# ── 指定密碼 ─────────────────────────────────────────────────────────────

def test_given_password_is_used(client, db, admin_headers):
    r = _create(client, admin_headers, password="Visit2026ok")
    assert r.status_code == 200, r.text
    assert r.json()["password"] == "Visit2026ok"

    lg = client.post("/api/v1/auth/login",
                     data={"username": "guest1", "password": "Visit2026ok"})
    assert lg.status_code == 200, lg.text


def test_blank_password_falls_back_to_random(client, db, admin_headers):
    """ZH: 留空＝照舊隨機（與 v4.19 逐字相同）。"""
    r = _create(client, admin_headers, password="   ")
    assert r.status_code == 200, r.text
    pw = r.json()["password"]
    assert pw and pw != "   "
    assert client.post("/api/v1/auth/login",
                       data={"username": "guest1", "password": pw}).status_code == 200


@pytest.mark.parametrize("bad", ["short7c", "x" * 21])
def test_password_length_is_checked_up_front(client, db, admin_headers, bad):
    """ZH: 廠商規則 8~20 —— 當場擋，不要等送到廠商才失敗。"""
    from app import models
    r = _create(client, admin_headers, password=bad)
    assert r.status_code == 422, r.text
    assert db.query(models.User).filter_by(username="guest1").first() is None


# ── 開通 MYAI ────────────────────────────────────────────────────────────

def test_myai_is_not_touched_by_default(client, db, admin_headers, fake_myai):
    """ZH: 預設不開通 —— 在廠商端建帳號不是可以隨手做的事。"""
    r = _create(client, admin_headers)
    assert r.status_code == 200, r.text
    assert r.json()["myai"] is None
    assert fake_myai == {}, "沒要求卻呼叫了廠商"


def test_myai_provisioned_with_the_same_password(client, db, admin_headers, fake_myai):
    """ZH: 🔴 兩平台同一組密碼（擁有者裁定）—— 帶下去的必須是同一個字串。"""
    r = _create(client, admin_headers, email="boss@example.com",
                password="Visit2026ok", provision_myai=True)
    assert r.status_code == 200, r.text
    assert r.json()["myai"]["status"] == "created"
    assert fake_myai["password"] == "Visit2026ok"
    assert fake_myai["password"] == r.json()["password"]


def test_generated_password_is_also_shared(client, db, admin_headers, fake_myai):
    """ZH: 沒指定密碼時，隨機產生的那一組也要同時用在 MYAI 上。"""
    r = _create(client, admin_headers, email="boss@example.com", provision_myai=True)
    assert fake_myai["password"] == r.json()["password"]


def test_myai_requires_a_real_email(client, db, admin_headers, fake_myai):
    """ZH: 🔴 沒填 Email 時平台會合成 `.invalid` 位址（永遠寄不到、註冊不了）——
       不擋的話會在廠商端建出一個救不回密碼的垃圾帳號。"""
    from app import models
    r = _create(client, admin_headers, provision_myai=True)
    assert r.status_code == 422, r.text
    assert "Email" in r.text or "email" in r.text
    assert db.query(models.User).filter_by(username="guest1").first() is None
    assert fake_myai == {}


def test_vendor_failure_keeps_the_platform_account(client, db, admin_headers, monkeypatch):
    """ZH: 廠商掛掉不該讓帳號建立失敗 —— 帳號已經建好了，一起收掉更糟
       （管理者會以為什麼都沒發生，然後重按一次撞到「帳號已存在」）。"""
    from app import models
    from app.services import myai_sync

    async def boom(db, user, password=None):
        raise RuntimeError("vendor down")
    monkeypatch.setattr(myai_sync, "provision_user", boom)

    r = _create(client, admin_headers, email="boss@example.com", provision_myai=True)
    assert r.status_code == 200, r.text
    assert r.json()["myai"]["status"] == "failed"
    assert db.query(models.User).filter_by(username="guest1").first() is not None


def test_linked_only_is_reported_as_is(client, db, admin_headers, monkeypatch):
    """ZH: 廠商端早就有這個信箱時只做綁定 —— **密碼不是我們給的這一組**，
       結果要原樣回給畫面，由它提醒管理者（不然帳密交出去對方登不進 MYAI）。"""
    from app.services import myai_sync

    async def linked(db, user, password=None):
        return {"status": "linked_only", "email": user.email}
    monkeypatch.setattr(myai_sync, "provision_user", linked)

    r = _create(client, admin_headers, email="boss@example.com", provision_myai=True)
    assert r.json()["myai"]["status"] == "linked_only"
