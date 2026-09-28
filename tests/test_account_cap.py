# -*- coding: utf-8 -*-
"""
ZH: v4.34 帳號總數上限（擁有者 2026-09-28，測試期間限制人數）。

ZH: 擁有者裁定的形狀是**不對稱**的，而那個不對稱正是最容易被後人「修掉」的地方：
      · 自助建號（SSO 首登／mock 側門／自助註冊）—— 滿了就擋
      · 管理端建號（配發、臨時帳號、批次匯入）—— **永遠不擋**
    所以這裡兩邊都要有測試。只測「滿了會擋」的話，哪天有人順手把檢查
    放進 crud.create_user「統一處理」，管理端就會在名額滿的那天整個卡死，
    而那正是管理者最需要能建帳號的時候。

ZH: 另一件事：算的是**啟用中且未到期**的帳號。停用與過期的不算 ——
    否則管理者為了開一個新帳號得先去刪稽核要用的舊資料。

@node tests/test_account_cap.py
"""
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "job-scheduler"))

from app import crud, models  # noqa: E402
from conftest import auth_headers, make_user  # noqa: E402


def _cap(db, n):
    crud.set_system_config(db, "max_accounts", str(n))


# ══════════════════════════════════════════════════════════════════════
# ZH: 一、數誰
# ══════════════════════════════════════════════════════════════════════

def test_counts_only_active_and_unexpired(db):
    """ZH: 停用的與已到期的不算 —— 它們登不進來，也不會用掉 MYAI 點數。"""
    make_user(db, username="live", email="live@example.com")
    off = make_user(db, username="off", email="off@example.com")
    off.is_active = 0
    gone = make_user(db, username="gone", email="gone@example.com")
    gone.expires_at = datetime.now(timezone.utc) - timedelta(days=1)
    later = make_user(db, username="later", email="later@example.com")
    later.expires_at = datetime.now(timezone.utc) + timedelta(days=1)
    db.commit()

    assert crud.active_account_count(db) == 2, "只有 live 與 later 算數"


def test_cap_zero_is_unlimited(db):
    make_user(db, username="a1", email="a1@example.com")
    _cap(db, 0)
    st = crud.account_cap_state(db)
    assert st["cap"] == 0 and st["full"] is False


def test_full_is_inclusive_at_the_boundary(db):
    """ZH: 🔴 上限 2 的意思是「第 3 個不准進來」。差一個就是 off-by-one。"""
    make_user(db, username="b1", email="b1@example.com")
    _cap(db, 2)
    assert crud.account_cap_state(db)["full"] is False
    make_user(db, username="b2", email="b2@example.com")
    assert crud.account_cap_state(db)["full"] is True


# ══════════════════════════════════════════════════════════════════════
# ZH: 二、滿了要擋的（自助）
# ══════════════════════════════════════════════════════════════════════

def test_self_registration_is_blocked_when_full(client, db):
    """ZH: 🔴 403 不是 400 —— 這不是「你填錯了」，換個帳號名重試不會成功。"""
    make_user(db, username="c1", email="c1@example.com")
    _cap(db, 1)
    r = client.post("/api/v1/auth/register", json={
        "username": "newbie", "email": "newbie@example.com",
        "password": "password123", "role": "student"})
    assert r.status_code == 403, r.text
    assert crud.get_user_by_username(db, "newbie") is None


def test_self_registration_works_when_there_is_room(client, db):
    make_user(db, username="c2", email="c2@example.com")
    _cap(db, 5)
    r = client.post("/api/v1/auth/register", json={
        "username": "newbie2", "email": "newbie2@example.com",
        "password": "password123", "role": "student"})
    assert r.status_code == 201, r.text


def test_sso_first_login_is_turned_away_with_its_own_reason(client, db, monkeypatch):
    """ZH: 🔴 名額滿了與「還沒開通」要是**兩個不同的 sso_error**。

    ZH: 講成同一句的話，名額滿的人會去找管理員說「幫我開通」——
        而管理端建號不受上限限制，他一建就成功，於是上限安靜地失效。
    """
    from app.routers import sso as sso_router
    monkeypatch.setattr(sso_router.alma_service, "lookup_identity", lambda sub: None)
    crud.set_system_config(db, "sso_autocreate", "1")
    make_user(db, username="d1", email="d1@example.com")
    _cap(db, 1)

    r = sso_router._finalize_sso_login(
        db, {"username": "11299999", "email": "11299999@me.mcu.edu.tw",
             "auth_source": "sso_mock"})
    assert r.status_code in (302, 307)
    assert "sso_error=account_full" in r.headers["location"], r.headers["location"]
    assert crud.get_user_by_username(db, "11299999") is None


def test_existing_account_still_signs_in_when_full(client, db, monkeypatch):
    """ZH: 擋的是**建新帳號**，不是登入。已經有帳號的人不受影響。"""
    from app.routers import sso as sso_router
    monkeypatch.setattr(sso_router.alma_service, "lookup_identity", lambda sub: None)
    u = make_user(db, username="11288888", email="11288888@me.mcu.edu.tw")
    _cap(db, 1)

    r = sso_router._finalize_sso_login(
        db, {"username": "11288888", "email": "11288888@me.mcu.edu.tw",
             "auth_source": "sso_mock"})
    assert r.status_code in (302, 307)
    assert "sso_error" not in r.headers["location"], r.headers["location"]
    db.refresh(u)
    assert u.auth_source == "sso_mock"


# ══════════════════════════════════════════════════════════════════════
# ZH: 三、滿了也**不能**擋的（管理端）—— 擁有者裁定
# ══════════════════════════════════════════════════════════════════════

def test_admin_provision_is_never_blocked(client, db):
    """ZH: 🔴 名額滿了照樣建得起來。這不是漏檢查，是擁有者要的行為：

    ZH: 上限是防爆閘門（擋自助），不是配額（管不到管理者）。
        哪天有人把檢查搬進 crud.create_user「統一處理」，這條會紅。
    """
    make_user(db, username="admin1", email="admin1@example.com", role="admin")
    _cap(db, 1)
    assert crud.account_cap_state(db)["full"] is True

    h = auth_headers(client, "admin1")
    r = client.post("/api/v1/admin/users/provision", headers=h, json={
        "username": "e1", "email": "e1@example.com", "role": "student"})
    assert r.status_code in (200, 201), r.text
    assert crud.get_user_by_username(db, "e1") is not None


def test_admin_temp_account_is_never_blocked(client, db):
    """ZH: 臨時帳號那條路同上 —— 它連 crud.create_user 都不走，直接建 models.User。"""
    make_user(db, username="admin2", email="admin2@example.com", role="admin")
    _cap(db, 1)

    h = auth_headers(client, "admin2")
    # ZH: 到期日有「最多 90 天」的驗證（schemas），所以算一個近期的日子，
    #     不要寫死一個遙遠的年份 —— 那會在 schema 那一層就 422，
    #     測不到這裡真正要測的「上限沒有擋住管理端」。
    soon = (datetime.now(timezone.utc) + timedelta(days=30)).strftime("%Y-%m-%d")
    r = client.post("/api/v1/admin/users/temporary", headers=h, json={
        "username": "temp1", "purpose": "上限測試", "expires_on": soon})
    assert r.status_code in (200, 201), r.text
    assert crud.get_user_by_username(db, "temp1") is not None
