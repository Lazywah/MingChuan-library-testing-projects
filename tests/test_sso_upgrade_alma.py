# -*- coding: utf-8 -*-
"""
ZH: v4.32 —— 手動開通的帳號第一次走 SSO 時，也問一次 Alma 預填（擁有者 2026-09-25）。

ZH: 缺口：Alma 只在「建新 SSO 帳號」那條路被問。sso_autocreate=0 時新學生
    都是管理者手動開通（auth_source=local）再用 SSO 登入 —— 走的是
    upgrade_to_sso 那條，沒有人問 Alma；排程回填又跳過 local 帳號，
    要等升級之後隔天才補得到。第一天的初次設定彈窗就是空的。

ZH: 這一族守三件事：
      1. 升級時真的有預填（校區／學系／常用信箱）
      2. **只補空的** —— 管理者建號時填的不能被蓋掉；角色完全不動
      3. Alma 查無時登入照常、什麼都不改（不能因為多問一次就把登入弄壞）

@node tests/test_sso_upgrade_alma.py
"""
import pytest

from conftest import make_user

ALMA = {"role": "student", "campus": "桃園", "department": "資訊管理學系",
        "email": "someone@gmail.com", "user_group": "01"}


@pytest.fixture
def sso_login(client, db, monkeypatch):
    """ZH: 與 test_sso_autocreate_gate 同一個做法：直接打共用的收尾函式。"""
    from app import models
    from app.routers import sso as sso_router

    # ZH: 測試的 DB 沒有跑 seed_org_tables —— 預填只寫「對得上組織表」的學系，
    #     所以要自己種（與 test_org_admin 同一個做法）。
    for name, college in (("資訊管理學系", "管理學院"), ("資訊工程學系", "資訊學院")):
        if not db.query(models.OrgDepartment).filter_by(name=name).first():
            db.add(models.OrgDepartment(name=name, college=college, campus=None, active=1))
    db.commit()

    def _go(username, alma=None, email=None):
        monkeypatch.setattr(sso_router.alma_service, "lookup_identity", lambda sub: alma)
        return sso_router._finalize_sso_login(
            db, {"username": username, "email": email or f"{username}@me.mcu.edu.tw",
                 "auth_source": "sso_mock"})
    return _go


def _campuses(db, user):
    from app import models
    return [c.campus for c in db.query(models.UserCampus)
            .filter(models.UserCampus.user_id == user.id).all()]


# ── 1. 升級時預填 ────────────────────────────────────────────────────

def test_local_account_gets_alma_prefill_on_first_sso_login(client, db, sso_login):
    """ZH: 🔴 手動開通 → 第一次 SSO 登入 → 校區／學系／常用信箱已經填好。"""
    from app import crud, models
    u = make_user(db, username="11234567", email="11234567@me.mcu.edu.tw")
    assert u.auth_source == "local" and not u.department

    r = sso_login("11234567", alma=ALMA)
    assert r.status_code in (302, 307), r
    db.refresh(u)
    assert u.auth_source == "sso_mock", "既有的升級行為要還在"
    assert u.department == "資訊管理學系"
    assert _campuses(db, u) == ["桃園"]
    assert u.contact_email == "someone@gmail.com"
    # ZH: 預填不等於完成初次設定 —— 彈窗照樣要出現讓本人確認。
    assert u.onboarded_at is None


def test_role_is_never_touched_on_upgrade(client, db, sso_login):
    """ZH: 手動開通的角色是管理者的決定，不是信箱猜的 —— Alma 說學生也不能改。"""
    u = make_user(db, username="t0001", email="t0001@mail.mcu.edu.tw", role="teacher")
    sso_login("t0001", alma=dict(ALMA, role="student"))
    db.refresh(u)
    assert u.role == "teacher"


# ── 2. 只補空的 ─────────────────────────────────────────────────────

def test_admin_set_values_are_not_overwritten(client, db, sso_login):
    """ZH: 🔴 管理者建號時填的校區／學系不能被 Alma 蓋掉（與排程回填同一個原則）。"""
    from app import crud
    u = make_user(db, username="11234568", email="11234568@me.mcu.edu.tw")
    u.department = "資訊工程學系"
    crud.set_user_campuses(db, u, ["台北"])
    u.contact_email = "mine@example.com"
    db.commit()

    sso_login("11234568", alma=ALMA)
    db.refresh(u)
    assert u.department == "資訊工程學系"
    assert _campuses(db, u) == ["台北"]
    assert u.contact_email == "mine@example.com"


def test_new_account_path_still_prefills_everything(client, db, sso_login):
    """ZH: 陰性對照 —— 建新帳號那條路（帳號全空）的行為沒被 only_blank 改壞。"""
    from app import crud, models
    crud.set_settings(db, {"sso_autocreate": "1"})
    sso_login("11234569", alma=ALMA)
    u = db.query(models.User).filter_by(username="11234569").first()
    assert u is not None and u.department == "資訊管理學系"
    assert _campuses(db, u) == ["桃園"]


# ── 3. 查無時什麼都不改 ─────────────────────────────────────────────

def test_alma_miss_changes_nothing_and_login_still_works(client, db, sso_login):
    u = make_user(db, username="guest3", email="guest3@example.com")
    r = sso_login("guest3", alma=None)
    assert r.status_code in (302, 307)
    db.refresh(u)
    assert u.auth_source == "sso_mock"
    assert not u.department and _campuses(db, u) == [] and not u.contact_email


def test_alma_department_unknown_to_org_table_is_skipped(client, db, sso_login):
    """ZH: 對不上組織表的學系**不寫**（彈窗預選一個不存在的選項比沒預填更糟）。"""
    u = make_user(db, username="11234570", email="11234570@me.mcu.edu.tw")
    sso_login("11234570", alma=dict(ALMA, department="不存在的學系"))
    db.refresh(u)
    assert not u.department
    assert _campuses(db, u) == ["桃園"], "學系對不上不影響校區照補"
