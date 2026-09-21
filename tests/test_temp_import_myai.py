# -*- coding: utf-8 -*-
"""
ZH: v4.20 —— 批次匯入臨時帳號時順手開通 MYAI（擁有者 2026-09-21）。

ZH: 🔴 廠商呼叫一律 monkeypatch。這些測試**絕對不可以真的打 MYAI** ——
    那會在廠商端建出真的帳號（刪不掉、而且會吃到點數池）。

ZH: 這一族守的三件事：
      1. 每一列用**自己那一列的密碼**開通（不是共用一組、也不是重新亂數）
      2. 勾了卻有列沒 Email → 預覽就擋下來，**整批不建**（全有或全無）
      3. 開通在帳號建好之後才跑；一列失敗不影響其他列，也不回滾帳號

@node tests/test_temp_import_myai.py
"""
import datetime
import io

import pytest

from conftest import make_user, auth_headers


@pytest.fixture
def admin_headers(client, db):
    make_user(db, username="adm", email="adm@example.com", role="admin")
    return auth_headers(client, "adm", "password123")


@pytest.fixture
def fake_myai(monkeypatch):
    """ZH: 攔下 provision_user，記下每一次的 (帳號, 密碼)。"""
    from app.services import myai_sync
    calls = []

    async def fake(db, user, password=None):
        calls.append((user.username, password))
        return {"status": "created", "email": user.email}

    monkeypatch.setattr(myai_sync, "provision_user", fake)
    return calls


def _csv(rows):
    """ZH: 匯入範本的欄位：帳號,信箱,密碼,身分。"""
    head = "username,email,password,role\n"
    return (head + "\n".join(",".join(r) for r in rows)).encode("utf-8")


def _post(client, headers, data, *, dry_run=False, myai=False, purpose="長官視察"):
    form = {"purpose": purpose,
            "expires_on": (datetime.date.today() + datetime.timedelta(days=7)).isoformat(),
            "dry_run": "true" if dry_run else "false"}
    if myai:
        form["provision_myai"] = "true"
    return client.post("/api/v1/admin/users/temporary/import", headers=headers, data=form,
                       files={"file": ("t.csv", io.BytesIO(data), "text/csv")})


# ── 每一列用自己的密碼 ───────────────────────────────────────────────────

def test_each_row_uses_its_own_password(client, db, admin_headers, fake_myai):
    """ZH: 🔴 自填密碼的用自填的、留空的用產生的 —— 逐列對應，不是共用一組。"""
    data = _csv([["g1", "g1@example.com", "Visit2026ok", "學生"],
                 ["g2", "g2@example.com", "", "學生"]])
    r = _post(client, admin_headers, data, myai=True)
    assert r.status_code == 200, r.text
    body = r.json()

    by_name = {c["username"]: c for c in body["created"]}
    calls = dict(fake_myai)
    assert calls["g1"] == "Visit2026ok"
    # ZH: g2 的密碼是系統產生的，回應裡有明文 —— 帶給廠商的必須是同一個
    assert calls["g2"] == by_name["g2"]["password"]
    assert by_name["g1"]["password"] is None, "自填密碼的列不該回顯"


def test_each_row_reports_its_own_result(client, db, admin_headers, fake_myai):
    data = _csv([["g1", "g1@example.com", "", "學生"]])
    r = _post(client, admin_headers, data, myai=True)
    assert r.json()["created"][0]["myai"]["status"] == "created"


def test_internal_fields_are_not_leaked(client, db, admin_headers, fake_myai):
    """ZH: 開通要用的暫存欄位（ORM 物件、明碼）不可以出現在回應裡。"""
    r = _post(client, admin_headers, _csv([["g1", "g1@example.com", "", "學生"]]), myai=True)
    row = r.json()["created"][0]
    assert "_user" not in row and "_pw" not in row


# ── 沒有 MYAI 時完全不動廠商 ─────────────────────────────────────────────

def test_vendor_untouched_without_the_flag(client, db, admin_headers, fake_myai):
    """ZH: 陰性對照 —— 沒勾就與 v4.19 逐字相同。"""
    r = _post(client, admin_headers, _csv([["g1", "g1@example.com", "", "學生"]]))
    assert r.status_code == 200, r.text
    assert r.json()["created"][0]["myai"] is None
    assert fake_myai == []


# ── 全有或全無 ───────────────────────────────────────────────────────────

def test_row_without_email_blocks_the_whole_batch(client, db, admin_headers, fake_myai):
    """ZH: 🔴 勾了開通卻有列沒 Email → 整批不建。

    ZH: 沒 Email 時平台會合成 `.invalid` 位址（永遠寄不到），拿去廠商註冊會留下
        一個收不到信、救不回密碼的垃圾帳號。
    """
    from app import models
    data = _csv([["g1", "g1@example.com", "", "學生"],
                 ["g2", "", "", "學生"]])
    r = _post(client, admin_headers, data, myai=True)
    assert r.status_code == 400, r.text
    assert "MYAI" in r.text
    assert db.query(models.User).filter_by(username="g1").first() is None, "一列有錯卻建了其他列"
    assert fake_myai == []


def test_same_row_is_fine_without_the_flag(client, db, admin_headers, fake_myai):
    """ZH: 陰性對照 —— 同一份檔案不開通時照樣建得起來（沒 Email 本來就允許）。"""
    data = _csv([["g1", "g1@example.com", "", "學生"],
                 ["g2", "", "", "學生"]])
    assert _post(client, admin_headers, data).status_code == 200


def test_preview_shows_the_problem(client, db, admin_headers, fake_myai):
    """ZH: 預覽就要看得到 —— 這正是兩段式的用途。"""
    data = _csv([["g1", "", "", "學生"]])
    r = _post(client, admin_headers, data, dry_run=True, myai=True)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is False
    assert any("MYAI" in p for p in body["rows"][0]["errors"])


@pytest.mark.parametrize("pw,ok", [("x" * 21, False), ("x" * 20, True)])
def test_password_upper_bound(client, db, admin_headers, fake_myai, pw, ok):
    """ZH: 廠商規則 8~20 —— 上限以前沒驗，超過會在廠商那邊才失敗。"""
    r = _post(client, admin_headers, _csv([["g1", "g1@example.com", pw, "學生"]]))
    assert (r.status_code == 200) is ok, r.text


# ── 失敗不連坐 ───────────────────────────────────────────────────────────

def test_one_failure_does_not_stop_the_rest(client, db, admin_headers, monkeypatch):
    """ZH: 一列失敗不影響其他列，也不回滾已建立的帳號 —— 這是批次不是交易。"""
    from app import models
    from app.services import myai_sync

    async def flaky(db, user, password=None):
        if user.username == "g1":
            raise RuntimeError("vendor down")
        return {"status": "created", "email": user.email}
    monkeypatch.setattr(myai_sync, "provision_user", flaky)

    data = _csv([["g1", "g1@example.com", "", "學生"],
                 ["g2", "g2@example.com", "", "學生"]])
    r = _post(client, admin_headers, data, myai=True)
    assert r.status_code == 200, r.text
    got = {c["username"]: c["myai"]["status"] for c in r.json()["created"]}
    assert got == {"g1": "failed", "g2": "created"}
    # ZH: 兩個帳號都還在（開通失敗不回滾）
    assert db.query(models.User).filter(models.User.username.in_(["g1", "g2"])).count() == 2
