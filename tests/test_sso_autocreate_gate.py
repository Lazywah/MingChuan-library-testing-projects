# -*- coding: utf-8 -*-
"""
ZH: v4.20 —— SSO 自動建帳號的閘門（擁有者 2026-09-21，測試期間關閉）。

ZH: 這支要釘住的是**關掉之後 SSO 仍然能用**：
      · 已經存在的帳號（不管是管理端手動建的、還是以前自動建的）照常登入
      · 不存在的人被回絕，而且回得到登入頁、說得出原因（不是 500、不是空白頁）
      · 開關打開時行為與 v4.19 完全相同（預設 1，既有部署不受影響）
    只擋「建新帳號」這一步，不是擋 SSO —— 兩者混在一起的話，
    關掉開關等於把全校鎖在門外。

@node tests/test_sso_autocreate_gate.py
"""
import pytest

from conftest import make_user


@pytest.fixture
def sso_login(client, db, monkeypatch):
    """ZH: 直接打共用的收尾函式，跳過 OIDC 交握（那不是這支要測的東西）。"""
    from app.routers import sso as sso_router

    def _go(username, email=None):
        return sso_router._finalize_sso_login(
            db, {"username": username, "email": email or f"{username}@me.mcu.edu.tw",
                 "auth_source": "sso_mock"})
    # ZH: Alma 在測試裡不該被呼叫（沒有網路、也不該依賴外部服務）。
    monkeypatch.setattr(sso_router.alma_service, "lookup_identity", lambda sub: None)
    return _go


def _set(db, value):
    from app import crud
    crud.set_settings(db, {"sso_autocreate": str(value)})


# ── 開關關閉 ─────────────────────────────────────────────────────────────

def test_unknown_user_is_refused_when_off(client, db, sso_login):
    """ZH: 不存在的人被回絕 —— 而且**沒有建帳號**。"""
    from app import models
    _set(db, 0)
    before = db.query(models.User).count()

    resp = sso_login("99999999")
    assert resp.status_code in (302, 307)
    assert "sso_error=no_account" in resp.headers["location"]
    assert db.query(models.User).count() == before, "回絕了卻還是建了帳號"


def test_refusal_lands_on_the_login_page(client, db, sso_login):
    """ZH: 🔴 要回得到登入頁。丟 500 或空白頁的話，使用者只會以為平台壞了。"""
    _set(db, 0)
    loc = sso_login("99999999").headers["location"]
    assert loc.startswith("/V1/login.html"), loc


def test_existing_account_still_signs_in_when_off(client, db, sso_login):
    """ZH: 🔴 關掉的是「建新帳號」，**不是 SSO**。管理端建立的帳號照常登入。"""
    _set(db, 0)
    make_user(db, username="12345678", email="12345678@me.mcu.edu.tw")

    resp = sso_login("12345678")
    assert resp.status_code in (302, 307)
    loc = resp.headers["location"]
    assert "sso_token=" in loc, loc
    assert "sso_error" not in loc


def test_temp_account_created_by_admin_signs_in_when_off(client, db, sso_login):
    """ZH: 臨時帳號也是管理端手動建的 —— 同樣不受閘門影響。"""
    from app import models
    _set(db, 0)
    u = make_user(db, username="guest9", email="guest9@example.com")
    u.temp_purpose = "教育部訪視"
    db.commit()

    assert "sso_token=" in sso_login("guest9", "guest9@example.com").headers["location"]


# ── 開關打開（既有行為）──────────────────────────────────────────────────

def test_unknown_user_is_created_when_on(client, db, sso_login):
    """ZH: 陰性對照 —— 打開時與 v4.19 逐字相同：首次登入就建帳號。"""
    from app import models
    _set(db, 1)
    assert db.query(models.User).filter_by(username="77777777").first() is None

    resp = sso_login("77777777")
    assert "sso_token=" in resp.headers["location"]
    created = db.query(models.User).filter_by(username="77777777").first()
    assert created is not None and created.role == "student"


def test_default_is_on(client, db):
    """ZH: 預設 1 —— 其他部署升級到這一版時行為不變（這台另外設成 0）。"""
    from app import crud
    assert str(crud.get_setting(db, "sso_autocreate")) == "1"
