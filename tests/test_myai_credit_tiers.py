# -*- coding: utf-8 -*-
"""
ZH: v4.34 MYAI 點數依身分分級（擁有者 2026-09-28：學生 10000、老師/職員 20000）。

ZH: 這一族守的是分級**表達得出三種狀態**：
      1. 沒設過   → 跟著總旋鈕走（既有部署一個字都不用改，行為不變）
      2. 設成 N   → 這個身分拿 N
      3. 設成 0   → 這個身分**不發**
    🔴 第 2 與第 3 分得開，是選 `default_from` 而不是「0 = 沿用預設」的唯一理由。
    用 0 當「沿用」的話，「老師不發點」這個要求在介面上表達不出來，
    而且沒有任何錯誤訊息 —— 管理者設了 0，然後老師照樣收到點數。

ZH: ⚠ 總旋鈕仍然是總開關（<=0 = 整個功能關閉，不看分級），
    不然「先全部停掉」要清五格，而漏清一格就是繼續發。

ZH: 廠商 HTTP 一律攔掉 —— 測試絕不對廠商送出任何東西。

@node tests/test_myai_credit_tiers.py
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "job-scheduler"))

from app import crud, models  # noqa: E402
from app.services import myai_sync as M  # noqa: E402


def _set(db, **kv):
    for k, v in kv.items():
        crud.set_system_config(db, k, str(v))


def _bind(db, username, role, points=0):
    """ZH: 造一個「平台帳號（某身分）綁到廠商帳號」的狀態。"""
    email = "%s@example.com" % username
    sn = "sn-" + username
    u = models.User(username=username, email=email, hashed_password="x", role=role)
    db.add(u)
    db.flush()
    db.add(models.MyaiAccount(vendor_sn=sn, email=email, points=points))
    acc = models.ExternalAiAccount(user_id=u.id, vendor_username=email,
                                   myai_vendor_sn=sn, status="active")
    db.add(acc)
    db.commit()
    return u, acc


# ══════════════════════════════════════════════════════════════════════
# ZH: 一、三種狀態
# ══════════════════════════════════════════════════════════════════════

def test_unset_roles_follow_the_master_knob(db):
    """ZH: 🔴 既有部署不受影響 —— 一格都沒設時，每個身分都拿總旋鈕的值。"""
    _set(db, myai_initial_credit=10000, myai_monthly_topup_to=888)
    for role in ("student", "teacher", "staff", "guest", "admin"):
        assert crud.myai_credit_for(db, role, "initial") == 10000, role
        assert crud.myai_credit_for(db, role, "topup") == 888, role


def test_per_role_override_wins(db):
    """ZH: 擁有者要的那組數字：學生 10000、老師/職員 20000。"""
    _set(db, myai_initial_credit=10000,
         myai_initial_credit_teacher=20000, myai_initial_credit_staff=20000)
    assert crud.myai_credit_for(db, "student", "initial") == 10000
    assert crud.myai_credit_for(db, "teacher", "initial") == 20000
    assert crud.myai_credit_for(db, "staff", "initial") == 20000
    assert crud.myai_credit_for(db, "guest", "initial") == 10000, "沒設的照總旋鈕"


def test_explicit_zero_means_this_role_gets_nothing(db):
    """ZH: 🔴 「設成 0」與「沒設過」是兩件事。分不開的話這個要求表達不出來。"""
    _set(db, myai_initial_credit=10000, myai_initial_credit_guest=0)
    assert crud.myai_credit_for(db, "guest", "initial") == 0
    assert crud.myai_credit_for(db, "student", "initial") == 10000


def test_master_zero_turns_everything_off(db):
    """ZH: 總開關關掉就是全部不發 —— 不看分級，不必清五格。"""
    _set(db, myai_initial_credit=0, myai_initial_credit_teacher=20000)
    assert crud.myai_credit_for(db, "teacher", "initial") == 0


def test_unknown_role_falls_back_to_student(db):
    """ZH: 認不得的身分往低的方向猜，而且不丟例外（這支在發點數的路徑上）。"""
    _set(db, myai_initial_credit=10000, myai_initial_credit_teacher=20000)
    assert crud.myai_credit_for(db, "wizard", "initial") == 10000
    assert crud.myai_credit_for(db, None, "initial") == 10000


def test_registry_covers_every_role_for_both_knobs(db):
    """ZH: 兩族欄位必須成對存在 —— 少一半的症狀是「初始發得對、每月補的不對」，
    而那要等到下個月 1 號才看得出來。"""
    for role, _zh, _en in crud.MYAI_CREDIT_ROLES:
        for key in ("myai_initial_credit_%s" % role, "myai_monthly_topup_%s" % role):
            assert key in crud.SYSTEM_SETTINGS, key
            spec = crud.SYSTEM_SETTINGS[key]
            assert spec["group"] == "myai" and spec["type"] == "int"
            assert spec.get("default_from"), key


# ══════════════════════════════════════════════════════════════════════
# ZH: 二、真的用在發放上
# ══════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_initial_grant_uses_the_role_tier(db, monkeypatch):
    """ZH: 🔴 老師開通時送出去的是 20000，不是總旋鈕那個 10000。"""
    sent = []

    async def fake(rows, confirm_grant=False):
        sent.append(rows)
        return {"ok": True, "granted": True, "count": len(rows),
                "points": sum(r["points"] for r in rows)}

    monkeypatch.setattr(M, "transfer_credit_batch", fake)
    _set(db, myai_initial_credit=10000, myai_initial_credit_teacher=20000)
    _u, acc = _bind(db, "t9001", "teacher")

    res = await M.grant_initial_credit(db, acc, "t9001@example.com")
    assert res["granted"] is True and res["points"] == 20000, res
    assert sent[0][0]["points"] == 20000


@pytest.mark.asyncio
async def test_initial_grant_skips_a_role_set_to_zero(db, monkeypatch):
    """ZH: 設成 0 的身分**不送出任何東西**（不是送 0 點）。"""
    async def boom(rows, confirm_grant=False):
        raise AssertionError("不該送出：這個身分的點數設成 0")

    monkeypatch.setattr(M, "transfer_credit_batch", boom)
    _set(db, myai_initial_credit=10000, myai_initial_credit_guest=0)
    _u, acc = _bind(db, "g9001", "guest")

    res = await M.grant_initial_credit(db, acc, "g9001@example.com")
    assert res["granted"] is False and res["reason"] == "disabled"


def test_monthly_targets_are_per_role(db):
    """ZH: 每月補點不給 target → 每個人補到他身分該有的水位。"""
    _set(db, myai_monthly_topup_to=10000, myai_monthly_topup_teacher=20000,
         myai_monthly_topup_guest=0)
    _bind(db, "s9002", "student", points=1000)
    _bind(db, "t9002", "teacher", points=1000)
    _bind(db, "g9002", "guest", points=0)

    rows = {r["email"]: r["points"] for r in M.topup_targets(db)}
    assert rows == {"s9002@example.com": 9000, "t9002@example.com": 19000}, rows


def test_manual_topup_target_overrides_the_tiers(db):
    """ZH: 管理者手動補齊打的數字是明確的指令 —— 不該被分級改寫。"""
    _set(db, myai_monthly_topup_to=10000, myai_monthly_topup_teacher=20000)
    _bind(db, "s9003", "student", points=0)
    _bind(db, "t9003", "teacher", points=0)

    rows = {r["email"]: r["points"] for r in M.topup_targets(db, 500)}
    assert rows == {"s9003@example.com": 500, "t9003@example.com": 500}, rows
