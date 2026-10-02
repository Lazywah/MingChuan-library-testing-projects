# -*- coding: utf-8 -*-
"""
ZH: MYAI 點數依身分分級（v4.34 擁有者 2026-09-28；v4.35 2026-10-02 改成「開關 + 表」）。

ZH: v4.35 的形狀：
      · 兩個**純開關**：myai_initial_credit_on / myai_monthly_topup_on
      · 一張表：每個身分 × 初始／每月，**每一格都是明確的值，沒有繼承**
    v4.34 的「總旋鈕（開關＋數字）＋ 沒設的跟著總旋鈕走」拿掉了 ——
    總旋鈕上的數字在五格都設了之後沒有任何人會拿到，擁有者為了讓大家都是
    50000 打了六次。

ZH: 這一族守四件事：
      1. 開關關著 = 0，不看表（「先全部停掉」是一個動作）
      2. 每一格就是那個身分拿到的數；沒填 = 0（不再偷偷跟著別的值走）
      3. 舊部署的值**搬一次就好**，而且搬完之後關得掉（見 migrate 那三條）
      4. 真的用在發放與每月補點上

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

ROLES = ("student", "teacher", "staff", "guest", "admin")


def _set(db, **kv):
    for k, v in kv.items():
        crud.set_system_config(db, k, str(v))


def _raw(db, key):
    return crud.get_system_config(db, key, "")


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
# ZH: 一、開關與表
# ══════════════════════════════════════════════════════════════════════

def test_switch_off_means_nobody_gets_anything(db):
    """ZH: 表填好了但開關關著 —— 全部 0。「先全部停掉」不必清十格。"""
    _set(db, myai_initial_credit_on=0, myai_initial_credit_teacher=20000,
         myai_monthly_topup_on=0, myai_monthly_topup_teacher=20000)
    assert crud.myai_credit_for(db, "teacher", "initial") == 0
    assert crud.myai_credit_for(db, "teacher", "topup") == 0


def test_each_cell_is_exactly_what_that_role_gets(db):
    """ZH: 擁有者現在的設定：初始一律 50000；每月學生／訪客 10000、教職員 20000。"""
    _set(db, myai_initial_credit_on=1, myai_monthly_topup_on=1)
    for r in ROLES:
        _set(db, **{"myai_initial_credit_%s" % r: 50000})
    _set(db, myai_monthly_topup_student=10000, myai_monthly_topup_guest=10000,
         myai_monthly_topup_teacher=20000, myai_monthly_topup_staff=20000,
         myai_monthly_topup_admin=20000)
    for r in ROLES:
        assert crud.myai_credit_for(db, r, "initial") == 50000, r
    assert crud.myai_credit_for(db, "student", "topup") == 10000
    assert crud.myai_credit_for(db, "teacher", "topup") == 20000


def test_unfilled_cell_is_zero_not_inherited(db):
    """ZH: 🔴 v4.35 起沒有繼承：沒填的格子就是 0，不會偷偷跟著別的值走。"""
    _set(db, myai_initial_credit_on=1, myai_initial_credit_student=10000)
    assert crud.myai_credit_for(db, "teacher", "initial") == 0


def test_unknown_role_falls_back_to_student(db):
    """ZH: 認不得的身分往低的方向猜，而且不丟例外（這支在發點數的路徑上）。"""
    _set(db, myai_initial_credit_on=1, myai_initial_credit_student=10000,
         myai_initial_credit_teacher=20000)
    assert crud.myai_credit_for(db, "wizard", "initial") == 10000
    assert crud.myai_credit_for(db, None, "initial") == 10000


def test_registry_shape_matches_the_card(db):
    """ZH: 卡片是寫死的版面 —— 分組裡的 key 必須正好是卡片畫的那十三個。
    （後端載入時也有同一條自檢；這裡再釘一次，免得有人把自檢拿掉。）"""
    group = {k for k, v in crud.SYSTEM_SETTINGS.items() if v["group"] == "myai_credit"}
    assert group == crud._CREDIT_CARD_KEYS
    assert len(group) == 3 + 2 * len(ROLES)
    for k in ("myai_initial_credit", "myai_monthly_topup_to"):
        assert k not in crud.SYSTEM_SETTINGS, "舊的總旋鈕不該再出現在畫面上：%s" % k
    for k in group:
        assert not crud.SYSTEM_SETTINGS[k].get("default_from"), "v4.35 起沒有繼承：%s" % k


# ══════════════════════════════════════════════════════════════════════
# ZH: 二、舊部署的搬移
# ══════════════════════════════════════════════════════════════════════

def test_migration_turns_old_value_into_switch_and_fills_blank_cells(db):
    """ZH: 舊語意「總旋鈕 N = 開，沒設的身分拿 N」→ 開關打開、沒設的格子填 N。"""
    _set(db, myai_initial_credit=50000, myai_monthly_topup_to=10000,
         myai_monthly_topup_teacher=20000)        # ZH: 這一格本來就明確設過
    res = crud.migrate_myai_credit_switches(db)
    assert res["status"] == "migrated"
    assert _raw(db, "myai_initial_credit_on") == "1"
    assert _raw(db, "myai_monthly_topup_on") == "1"
    for r in ROLES:
        assert _raw(db, "myai_initial_credit_%s" % r) == "50000", r
    assert _raw(db, "myai_monthly_topup_student") == "10000"
    assert _raw(db, "myai_monthly_topup_teacher") == "20000", "明確設過的不能被蓋掉"
    # ZH: 搬完之後的行為要與搬之前一模一樣
    assert crud.myai_credit_for(db, "guest", "topup") == 10000
    assert crud.myai_credit_for(db, "teacher", "topup") == 20000


def test_migration_of_an_old_zero_writes_nothing(db):
    """ZH: 舊值 0 = 本來就關著 —— 不寫開關、不填格子，維持「什麼都不發」。"""
    _set(db, myai_initial_credit=0)
    crud.migrate_myai_credit_switches(db)
    assert _raw(db, "myai_initial_credit_on") in (None, "")
    assert _raw(db, "myai_initial_credit_student") in (None, "")
    assert crud.myai_credit_for(db, "student", "initial") == 0


def test_migration_runs_once_so_the_switch_can_be_turned_off(db):
    """ZH: 🔴 只跑一次，靠記號。不然管理者在新開關上按「回到預設」（清空）之後，
    下次開機又被舊值搬回「開」—— 一個關不掉的開關。"""
    _set(db, myai_initial_credit=50000)
    crud.migrate_myai_credit_switches(db)
    crud.set_system_config(db, "myai_initial_credit_on", "")    # ZH: 回到預設（關）
    assert crud.migrate_myai_credit_switches(db)["status"] == "already_done"
    assert _raw(db, "myai_initial_credit_on") in (None, "")
    assert crud.myai_credit_for(db, "student", "initial") == 0


# ══════════════════════════════════════════════════════════════════════
# ZH: 三、真的用在發放上
# ══════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_initial_grant_uses_the_role_cell(db, monkeypatch):
    """ZH: 🔴 老師開通時送出去的是老師那一格的數。"""
    sent = []

    async def fake(rows, confirm_grant=False):
        sent.append(rows)
        return {"ok": True, "granted": True, "count": len(rows),
                "points": sum(r["points"] for r in rows)}

    monkeypatch.setattr(M, "transfer_credit_batch", fake)
    _set(db, myai_initial_credit_on=1, myai_initial_credit_student=10000,
         myai_initial_credit_teacher=20000)
    _u, acc = _bind(db, "t9001", "teacher")

    res = await M.grant_initial_credit(db, acc, "t9001@example.com")
    assert res["granted"] is True and res["points"] == 20000, res
    assert sent[0][0]["points"] == 20000


@pytest.mark.asyncio
async def test_initial_grant_skips_a_role_set_to_zero(db, monkeypatch):
    """ZH: 那一格填 0 的身分**不送出任何東西**（不是送 0 點）。"""
    async def boom(rows, confirm_grant=False):
        raise AssertionError("不該送出：這個身分的點數設成 0")

    monkeypatch.setattr(M, "transfer_credit_batch", boom)
    _set(db, myai_initial_credit_on=1, myai_initial_credit_student=10000,
         myai_initial_credit_guest=0)
    _u, acc = _bind(db, "g9001", "guest")

    res = await M.grant_initial_credit(db, acc, "g9001@example.com")
    assert res["granted"] is False and res["reason"] == "disabled"


def test_monthly_targets_are_per_role(db):
    """ZH: 每月補點不給 target → 每個人補到他身分那一格。"""
    _set(db, myai_monthly_topup_on=1, myai_monthly_topup_student=10000,
         myai_monthly_topup_teacher=20000, myai_monthly_topup_guest=0)
    _bind(db, "s9002", "student", points=1000)
    _bind(db, "t9002", "teacher", points=1000)
    _bind(db, "g9002", "guest", points=0)

    rows = {r["email"]: r["points"] for r in M.topup_targets(db)}
    assert rows == {"s9002@example.com": 9000, "t9002@example.com": 19000}, rows


def test_manual_topup_target_overrides_the_table(db):
    """ZH: 管理者手動補齊打的數字是明確的指令 —— 不該被表格改寫。"""
    _set(db, myai_monthly_topup_on=1, myai_monthly_topup_student=10000,
         myai_monthly_topup_teacher=20000)
    _bind(db, "s9003", "student", points=0)
    _bind(db, "t9003", "teacher", points=0)

    rows = {r["email"]: r["points"] for r in M.topup_targets(db, 500)}
    assert rows == {"s9003@example.com": 500, "t9003@example.com": 500}, rows


# ══════════════════════════════════════════════════════════════════════
# ZH: 四、管理端 API —— 卡片讀得到、存得回去
# ══════════════════════════════════════════════════════════════════════

def test_admin_api_round_trip_for_the_credit_card(client, db):
    """ZH: GET 要帶出 card 分組（前端靠它決定不用通用表畫）；PUT 整張卡片存得回去。"""
    from conftest import auth_headers, make_user
    make_user(db, username="crad", email="crad@example.com", role="admin")
    h = auth_headers(client, "crad")

    r = client.get("/api/v1/admin/system-settings", headers=h)
    assert r.status_code == 200, r.text
    groups = {g["key"]: g for g in r.json()["groups"]}
    assert groups["myai_credit"].get("card") == "credit"
    keys = {s["key"] for s in r.json()["settings"] if s["group"] == "myai_credit"}
    assert keys == crud._CREDIT_CARD_KEYS

    payload = {"myai_initial_credit_on": "1", "myai_monthly_topup_on": "0",
               "myai_monthly_topup_day": "5"}
    for role in ROLES:
        payload["myai_initial_credit_%s" % role] = "50000"
        payload["myai_monthly_topup_%s" % role] = "20000" if role in ("teacher", "staff", "admin") else "10000"
    r = client.put("/api/v1/admin/system-settings", headers=h, json=payload)
    assert r.status_code == 200, r.text
    assert crud.myai_credit_for(db, "guest", "initial") == 50000
    assert crud.myai_credit_for(db, "teacher", "topup") == 0, "每月補點的開關存成關"
    assert crud.get_setting(db, "myai_monthly_topup_day") == 5
