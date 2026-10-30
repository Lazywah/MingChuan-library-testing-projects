"""
ZH: v4.43 回收點數（擁有者 2026-10-30）：單人全部／單人指定數量／批次收到水位。

ZH: 🔴 這一族守的是**方向**。轉出點數最壞是把池子送光；回收最壞是**把學生的點數扣光**，
    而那個沒有「再發一次」以外的救法（發回去的是新的點，用掉的歷史對不回來）。
    所以這裡釘的每一條都是「什麼時候**不准**送出」。

@node tests/test_myai_reclaim.py
"""
import json

import pytest

from conftest import auth_headers, make_user

from app import models
from app.services import myai_sync as M


def _bind(db, username, points):
    email = "%s@example.com" % username
    sn = "sn-" + username
    u = models.User(username=username, email=email, hashed_password="x", role="student")
    db.add(u)
    db.flush()
    db.add(models.MyaiAccount(vendor_sn=sn, email=email, points=points))
    db.add(models.ExternalAiAccount(user_id=u.id, vendor_username=email,
                                    myai_vendor_sn=sn, status="active"))
    db.commit()
    return u


@pytest.fixture()
def sent(monkeypatch):
    """ZH: 不連廠商。同步什麼都不做；回收記下送出的名單。"""
    box = []

    async def fake_sync(db):
        return {"status": "ok"}

    async def fake_reclaim(rows, confirm_reclaim=False):
        assert confirm_reclaim is True, "呼叫端沒有明確表示知道這會扣點"
        box.append(list(rows))
        return {"ok": True, "reclaimed": True, "count": len(rows),
                "points": sum(r["points"] for r in rows)}

    monkeypatch.setattr(M, "sync", fake_sync)
    monkeypatch.setattr(M, "reclaim_credit_batch", fake_reclaim)
    return box


@pytest.fixture()
def admin_headers(client, db):
    make_user(db, username="rc-admin", email="rc-admin@example.com", role="admin")
    return auth_headers(client, "rc-admin", "password123")


# ── 閘門：端點不能被誤用 ──────────────────────────────────────────────

def test_reclaim_needs_an_explicit_confirm():
    with pytest.raises(M.MyaiSyncError, match="confirm_reclaim"):
        M._assert_reclaim_endpoint(M.GET_CREDIT_CHECK_PATH, False)


@pytest.mark.parametrize("bad", [
    "/mcu/gt_sdk/admin_168/user/transfer_credit_batch_check",
    "/mcu/gt_sdk/admin_168/user/register_batch",
    "/mcu/gt_sdk/admin_168/user/delete",
])
def test_reclaim_refuses_other_batch_endpoints(bad):
    with pytest.raises(M.MyaiSyncError):
        M._assert_reclaim_endpoint(bad, True)


def test_transfer_guard_still_bans_get_credit():
    """ZH: 🔴 做了回收**不代表**轉出那道閘門可以鬆掉。

    ZH: 兩支分開的理由就在這裡：共用一支並放寬白名單的話，一個手滑的迴圈
        就能用「轉出」的程式碼打到「回收」的端點，方向整個反過來。
    """
    with pytest.raises(M.MyaiSyncError):
        M._assert_transfer_endpoint(M.GET_CREDIT_CHECK_PATH, True)


# ── 預覽頁對帳：對不上就中止 ──────────────────────────────────────────

_SENT = [{"email": "a@x.com", "points": 100}, {"email": "b@x.com", "points": 50}]


def _page(mails, pts, extra=""):
    html = ""
    for m in mails:
        html += '<input name="emails[]" value="%s">' % m
    for p in pts:
        html += '<input name="getPoints[]" value="%s">' % p
    return html + extra


def test_echo_rows_identify_columns_by_content():
    """ZH: 欄位名靠**內容**認（含 @ 的是信箱、數字且與送出相同的是點數）——
        廠商改欄位名不該讓我們送出一個它看不懂的 body。"""
    fields, rows = M._reclaim_echo_rows(_page(["a@x.com", "b@x.com"], [100, 50]), _SENT)
    assert set(fields) == {"emails", "getPoints"}
    assert rows[0]["emails"] == "a@x.com" and rows[0]["getPoints"] == "100"


def test_echo_rows_survive_a_renamed_field():
    html = (_page([], [])
            + '<input name="mailAddr[]" value="a@x.com"><input name="mailAddr[]" value="b@x.com">'
            + '<input name="pts[]" value="100"><input name="pts[]" value="50">')
    fields, rows = M._reclaim_echo_rows(html, _SENT)
    assert set(fields) == {"mailAddr", "pts"}


@pytest.mark.parametrize("html,why", [
    ("<p>nothing</p>", "完全沒有回吐欄位"),
    (_page(["a@x.com"], [100]), "列數比送出的少"),
    (_page(["a@x.com", "b@x.com"], [100, 999]), "點數被改掉了"),
    (_page(["a@x.com", "zzz@x.com"], [100, 50]), "信箱被改掉了"),
])
def test_echo_rows_abort_when_the_preview_disagrees(html, why):
    """ZH: 🔴 這幾種都要**停在第二段之前** —— 盲送的後果是點數扣了而我們不知道扣了誰。"""
    with pytest.raises(M.MyaiSyncError) as e:
        M._reclaim_echo_rows(html, _SENT)
    assert "未扣任何點數" in str(e.value), why


# ── 單人回收 ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_reclaim_all_takes_exactly_what_they_have(db, sent):
    u = _bind(db, "r1", 1234)
    out = await M.reclaim_points(db, u, 0, None, "課程結束", all_points=True)
    assert sent[0] == [{"email": "r1@example.com", "points": 1234, "remark": "課程結束"}]
    assert out["points"] == 1234 and out["after"] == 0
    db.expire_all()
    assert db.query(models.MyaiAccount).filter_by(email="r1@example.com").first().points == 0


@pytest.mark.asyncio
async def test_reclaim_a_specific_amount(db, sent):
    u = _bind(db, "r2", 1000)
    out = await M.reclaim_points(db, u, 300, None, "")
    assert sent[0][0]["points"] == 300
    assert out["after"] == 700


@pytest.mark.asyncio
async def test_reclaim_cannot_go_negative(db, sent):
    """ZH: 🔴 收超過他有的＝我們算錯了。廠商對「扣成負的」行為未知，不要試。"""
    u = _bind(db, "r3", 100)
    with pytest.raises(M.MyaiSyncError, match="只有 100 點"):
        await M.reclaim_points(db, u, 101, None, "")
    assert sent == [], "不該送出任何東西"


@pytest.mark.asyncio
async def test_reclaim_all_on_an_empty_account_is_refused(db, sent):
    u = _bind(db, "r4", 0)
    with pytest.raises(M.MyaiSyncError):
        await M.reclaim_points(db, u, 0, None, "", all_points=True)
    assert sent == []


@pytest.mark.asyncio
async def test_reclaim_writes_an_audit_row(db, sent):
    # ZH: admin_id 是外鍵 —— 要用真的存在的管理員，不能塞一個字串。
    adm = make_user(db, username="rc-a2", email="rc-a2@example.com", role="admin")
    u = _bind(db, "r5", 500)
    await M.reclaim_points(db, u, 200, adm.id, "測試")
    a = db.query(models.AdminAction).filter_by(action="myai_reclaim_points").one()
    p = json.loads(a.payload)
    assert a.target_user == u.id
    assert p["points"] == 200 and p["before"] == 500 and p["outcome"] == "ok"


# ── 批次收到水位 ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_batch_reclaims_only_the_excess(db, sent):
    _bind(db, "b1", 5000)
    _bind(db, "b2", 1000)
    _bind(db, "b3", 800)
    r = await M.manual_reclaim(db, 1000, None, dry_run=True)
    got = {x["email"]: x["points"] for x in r["rows"]}
    assert got == {"b1@example.com": 4000}, "只有高於水位的進名單，剛好等於的不進"
    assert sent == [], "預覽不能送出任何東西"


@pytest.mark.asyncio
async def test_batch_is_idempotent(db, sent):
    """ZH: 🔴 「收到 N」不是「扣 N」—— 跑完第二次算出來是空的。"""
    _bind(db, "b4", 5000)
    await M.manual_reclaim(db, 1000, None, dry_run=False)
    db.query(models.MyaiAccount).filter_by(email="b4@example.com").update({"points": 1000})
    db.commit()
    r2 = await M.manual_reclaim(db, 1000, None, dry_run=False)
    assert r2["status"] == "nobody_above" and len(sent) == 1


@pytest.mark.asyncio
async def test_batch_honours_the_exclusion_on_the_real_send(db, sent):
    """ZH: 🔴 送出時後端重算名單 —— 排除名單必須一起生效（同手動補齊那一條）。"""
    _bind(db, "b5", 9000)
    _bind(db, "b6", 9000)
    r = await M.manual_reclaim(db, 1000, None, dry_run=False,
                               exclude=["B6@EXAMPLE.COM"])
    assert [x["email"] for x in sent[0]] == ["b5@example.com"]
    assert r["excluded"] == ["b6@example.com"]


@pytest.mark.asyncio
async def test_batch_skips_the_pool_account(db, sent, monkeypatch):
    """ZH: 轉出帳號自己不收 —— 把池子的點數「收回池子」沒有意義，廠商行為也未知。"""
    monkeypatch.setattr(M.settings, "MYAI_ADMIN_EMAIL", "pool@example.com")
    _bind(db, "pool", 999999)
    db.query(models.MyaiAccount).filter_by(email="pool@example.com").update(
        {"email": "pool@example.com"})
    db.commit()
    r = await M.manual_reclaim(db, 10, None, dry_run=True)
    assert "pool@example.com" not in [x["email"] for x in r["rows"]]


# ── API ──────────────────────────────────────────────────────────────

def test_batch_api_needs_self_confirm(client, db, admin_headers, sent):
    _bind(db, "api1", 5000)
    r = client.post("/api/v1/admin/myai/reclaim", headers=admin_headers,
                    json={"target": 100, "dry_run": False, "confirm_username": "wrong"})
    assert r.status_code == 400, r.text
    assert sent == []


def test_single_api_needs_target_confirm(client, db, admin_headers, sent):
    u = _bind(db, "api2", 500)
    r = client.post("/api/v1/admin/users/%s/myai/reclaim" % u.id, headers=admin_headers,
                    json={"points": 100, "confirm_username": "someone-else"})
    assert r.status_code == 400, r.text
    assert sent == []


def test_single_api_round_trip(client, db, admin_headers, sent):
    u = _bind(db, "api3", 500)
    r = client.post("/api/v1/admin/users/%s/myai/reclaim" % u.id, headers=admin_headers,
                    json={"all_points": True, "confirm_username": "api3", "reason": "結案"})
    assert r.status_code == 200, r.text
    assert r.json()["after"] == 0 and sent[0][0]["points"] == 500
