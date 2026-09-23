# -*- coding: utf-8 -*-
"""
ZH: v4.28 —— 批次匯入臨時帳號的「永久有效」選項（擁有者 2026-09-24）。

ZH: 這一族守的其實只有一件事：**「忘記填到期日」不可以變成「開了一批
    永遠不會消失的帳號」。** 單筆那條路早就有這條規則
    （schemas.AdminTempUserCreate.one_of_expiry），但 multipart 拿不到
    pydantic body model，所以匯入端點是**另外手寫一份**同樣的驗證 ——
    兩份會不會漂開，只有測試看得出來。

ZH: 批次比單筆更需要這條：單筆填錯是一個帳號，批次填錯是一整個檔案。

@node tests/test_temp_import_forever.py
"""
import datetime
import io
import json

import pytest

from conftest import make_user, auth_headers


@pytest.fixture
def admin_headers(client, db):
    make_user(db, username="adm", email="adm@example.com", role="admin")
    return auth_headers(client, "adm", "password123")


def _csv(rows):
    head = "username,email,password,role\n"
    return (head + "\n".join(",".join(r) for r in rows)).encode("utf-8")


def _post(client, headers, form, rows=None):
    """ZH: form 逐字送出 —— 「什麼都不填」也要測得到，所以不給預設值。"""
    data = _csv(rows or [["g1", "g1@example.com", "", "學生"]])
    return client.post("/api/v1/admin/users/temporary/import", headers=headers, data=form,
                       files={"file": ("t.csv", io.BytesIO(data), "text/csv")})


def _in_a_week():
    return (datetime.date.today() + datetime.timedelta(days=7)).isoformat()


# ── 永久：真的沒有到期日 ─────────────────────────────────────────────────

def test_never_expires_creates_accounts_without_an_expiry(client, db, admin_headers):
    """ZH: 🔴 永久 = `expires_at` 是 NULL，不是一個很遠的日期。

    ZH: 「很遠的日期」會在某一天突然全部失效，而那一天沒有人記得。
        NULL 與一般帳號同形，清單與 tempCard 都照既有邏輯處理。
    """
    from app import models
    r = _post(client, admin_headers,
              {"purpose": "長官視察", "never_expires": "true", "dry_run": "false"},
              rows=[["g1", "g1@example.com", "", "學生"],
                    ["g2", "g2@example.com", "", "學生"]])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["expires_at"] is None
    assert body["never_expires"] is True

    users = db.query(models.User).filter(models.User.username.in_(["g1", "g2"])).all()
    assert len(users) == 2
    assert all(u.expires_at is None for u in users)
    # ZH: 用途仍然要留著 —— 永久的臨時帳號更需要有人說得出它為什麼在。
    assert all(u.temp_purpose == "長官視察" for u in users)


def test_audit_says_it_was_permanent(client, db, admin_headers):
    """ZH: 稽核紀錄要分得出「永久」與「漏寫」——兩者的 expires_on 都是 null。"""
    from app import models
    r = _post(client, admin_headers,
              {"purpose": "長官視察", "never_expires": "true", "dry_run": "false"})
    assert r.status_code == 200, r.text
    act = db.query(models.AdminAction).filter_by(action="create_temp_account").first()
    payload = json.loads(act.payload)
    assert payload["expires_on"] is None
    assert payload["never_expires"] is True
    assert payload["batch_import"] is True


# ── 忘記填不等於永久 ─────────────────────────────────────────────────────

def test_neither_given_is_rejected(client, db, admin_headers):
    """ZH: 🔴 兩個都不給 → 400，**不要默默當成永久**。

    ZH: 這是整族測試的核心。沒有這一條的話，「忘記填日期」會安靜地
        變成「一口氣開了一批永遠不會消失的帳號」，而且沒有人會發現。
    """
    from app import models
    r = _post(client, admin_headers, {"purpose": "長官視察", "dry_run": "false"})
    assert r.status_code == 400, r.text
    assert db.query(models.User).filter_by(username="g1").first() is None


def test_both_given_is_rejected(client, db, admin_headers):
    """ZH: 矛盾的輸入要當場擋 —— 不要自己挑一個來用。"""
    from app import models
    r = _post(client, admin_headers, {"purpose": "長官視察", "never_expires": "true",
                                      "expires_on": _in_a_week(), "dry_run": "false"})
    assert r.status_code == 400, r.text
    assert db.query(models.User).filter_by(username="g1").first() is None


def test_preview_is_blocked_too(client, db, admin_headers):
    """ZH: 預覽也要擋 —— 兩段式的用途就是讓錯誤在送出前現形。"""
    r = _post(client, admin_headers, {"purpose": "長官視察", "dry_run": "true"})
    assert r.status_code == 400, r.text


# ── 陰性對照：原本那條路沒有被改壞 ───────────────────────────────────────

def test_dated_import_still_works(client, db, admin_headers):
    """ZH: 填日期的那條路要與 v4.27 逐字相同（到期日照舊寫進去）。"""
    from app import models
    r = _post(client, admin_headers,
              {"purpose": "長官視察", "expires_on": _in_a_week(), "dry_run": "false"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["expires_at"] is not None
    assert body["never_expires"] is False
    u = db.query(models.User).filter_by(username="g1").first()
    assert u.expires_at is not None


def test_out_of_range_date_still_rejected(client, db, admin_headers):
    """ZH: 90 天上限沒有因為多了「永久」而鬆掉 —— 要永久就明講永久。"""
    far = (datetime.date.today() + datetime.timedelta(days=200)).isoformat()
    r = _post(client, admin_headers,
              {"purpose": "長官視察", "expires_on": far, "dry_run": "false"})
    assert r.status_code == 400, r.text


def test_purpose_is_still_required_for_permanent(client, db, admin_headers):
    """ZH: 永久**不是**豁免用途 —— 沒有理由的永久帳號正是要防的東西。"""
    from app import models
    r = _post(client, admin_headers,
              {"purpose": "  ", "never_expires": "true", "dry_run": "false"})
    assert r.status_code == 400, r.text
    assert db.query(models.User).filter_by(username="g1").first() is None
