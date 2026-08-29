"""
ZH: MYAI 每月補點的測試。

ZH: 規則（擁有者 2026-08-29）：補到固定值 · 所有綁定帳號 · 每月 1 號（台北時間）。

ZH: 這裡守的三件事，每一件出錯都是**收不回來的點數**：
      1. 一個月只送出一次（排程每小時醒一次，重入就是發兩倍）
      2. 差額要用**新鮮**的點數算（拿舊資料算會補過頭）
      3. 池子不夠就整批不送（硬送可能只轉一部分，誰拿到誰沒拿到查不出來）
"""
import sys
import os
import asyncio

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "job-scheduler"))

from app import crud, models  # noqa: E402
from conftest import make_user  # noqa: E402
from app.services import myai_sync as M  # noqa: E402


def _bind(db, email, points, sn=None):
    """ZH: 造一個「平台帳號綁到廠商帳號、廠商端有 N 點」的狀態。"""
    sn = sn or ("sn-" + email.split("@")[0])
    u = models.User(username=email.split("@")[0], email=email,
                    hashed_password="x", role="student")
    db.add(u)
    db.flush()
    db.add(models.MyaiAccount(vendor_sn=sn, email=email, points=points))
    db.add(models.ExternalAiAccount(user_id=u.id, vendor_username=email,
                                    myai_vendor_sn=sn, status="active"))
    db.commit()
    return u


def _no_network(monkeypatch):
    """ZH: sync 換成不做事 —— 這組測試不對廠商送任何東西。"""
    async def fake_sync(db):
        return {"created": 0, "updated": 0}
    monkeypatch.setattr(M, "sync", fake_sync)


def _capture_transfer(monkeypatch, granted=True):
    """ZH: 攔下轉點，回傳收到的名單。"""
    seen = []

    async def fake(rows, confirm_grant=False):
        assert confirm_grant is True, "沒有明確帶 confirm_grant"
        seen.append(rows)
        return {"ok": granted, "granted": granted, "count": len(rows),
                "points": sum(r["points"] for r in rows)}

    monkeypatch.setattr(M, "transfer_credit_batch", fake)
    return seen


# ══════════════════════════════════════════════════════════════════════════
# ZH: 一、算誰要補、補多少
# ══════════════════════════════════════════════════════════════════════════

def test_tops_up_to_the_target_not_by_a_fixed_amount(db):
    """ZH: 補到固定值 —— 兩個人起點不同，補完應該一樣高。"""
    _bind(db, "a@example.com", 100)
    _bind(db, "b@example.com", 700)
    rows = {r["email"]: r["points"] for r in M.topup_targets(db, 1000)}
    assert rows == {"a@example.com": 900, "b@example.com": 300}


def test_people_already_at_or_above_target_are_skipped(db):
    """ZH: 已達標的不入列 —— 補 0 是白跑，而且 xlsx 會拒收 0。"""
    _bind(db, "c@example.com", 1000)
    _bind(db, "d@example.com", 1200)
    assert M.topup_targets(db, 1000) == []


def test_unbound_vendor_accounts_are_not_topped_up(db):
    """
    ZH: 🔴 廠商後台還有我們的管理帳號與其他來源的帳號。
        沒綁定就不是我們的學生，補到他們身上是把點數送給不相干的人。
    """
    db.add(models.MyaiAccount(vendor_sn="sn-stranger",
                              email="stranger@example.com", points=0))
    db.commit()
    assert M.topup_targets(db, 500) == []


def test_disabled_binding_is_skipped(db):
    """ZH: 停用的綁定不補。"""
    u = _bind(db, "e@example.com", 0)
    acc = (db.query(models.ExternalAiAccount)
             .filter(models.ExternalAiAccount.user_id == u.id).first())
    acc.status = "disabled"
    db.commit()
    assert M.topup_targets(db, 500) == []


def test_the_source_account_is_never_topped_up(db, monkeypatch):
    """
    ZH: 🔴 轉出帳號自己也是一個綁定的平台帳號（MYAI_ADMIN_EMAIL 是某人的學號信箱）。
        池子低於目標值時，補點會變成「自己轉給自己」—— 廠商行為未知，不要試。
    """
    _bind(db, "boss@example.com", 0)
    _bind(db, "kid@example.com", 0)
    monkeypatch.setattr(M.settings, "MYAI_ADMIN_EMAIL", "BOSS@example.com")
    rows = [r["email"] for r in M.topup_targets(db, 500)]
    assert rows == ["kid@example.com"], f"轉出帳號入列了：{rows}"


# ══════════════════════════════════════════════════════════════════════════
# ZH: 二、一個月只送一次
# ══════════════════════════════════════════════════════════════════════════

def test_runs_once_then_never_again_that_month(db, monkeypatch):
    """ZH: 🔴 整組測試的核心。排程每小時醒一次 —— 第二次醒來絕對不能再送。"""
    _bind(db, "f@example.com", 0)
    crud.set_system_config(db, "myai_monthly_topup_to", "500")
    crud.set_system_config(db, "myai_monthly_topup_day", "1")
    monkeypatch.setattr(M, "_taipei_day", lambda: 1)
    _no_network(monkeypatch)
    seen = _capture_transfer(monkeypatch)

    first = asyncio.run(M.monthly_topup(db))
    assert first["status"] == "done" and first["points"] == 500

    second = asyncio.run(M.monthly_topup(db))
    assert second["status"] == "already_done"
    assert len(seen) == 1, "同一個月送了兩次"


def test_force_still_cannot_bypass_the_monthly_gate(db, monkeypatch):
    """
    ZH: force 只跳過「今天是不是補點日」，**不跳過**「這個月做過了沒」。
        繞過後者就是重複發放。
    """
    _bind(db, "g@example.com", 0)
    crud.set_system_config(db, "myai_monthly_topup_to", "500")
    _no_network(monkeypatch)
    seen = _capture_transfer(monkeypatch)

    assert asyncio.run(M.monthly_topup(db, force=True))["status"] == "done"
    assert asyncio.run(M.monthly_topup(db, force=True))["status"] == "already_done"
    assert len(seen) == 1


def test_does_nothing_before_the_topup_day(db, monkeypatch):
    """ZH: 還沒到補點日就不送。"""
    _bind(db, "h@example.com", 0)
    crud.set_system_config(db, "myai_monthly_topup_to", "500")
    crud.set_system_config(db, "myai_monthly_topup_day", "15")
    monkeypatch.setattr(M, "_taipei_day", lambda: 14)
    _no_network(monkeypatch)
    seen = _capture_transfer(monkeypatch)

    assert asyncio.run(M.monthly_topup(db))["status"] == "not_today"
    assert seen == []


def test_does_nothing_after_the_topup_day(db, monkeypatch):
    """
    ZH: 只在當天跑（擁有者裁定：服務 24/7 在線）。

    ZH: ⚠️ 代價：補點日整天服務沒起來就整個月不補，而且不會報錯。
        真的遇到時的出路是**手動補齊**（manual_topup），不是自動補跑。
    """
    _bind(db, "m@example.com", 0)
    crud.set_system_config(db, "myai_monthly_topup_to", "500")
    crud.set_system_config(db, "myai_monthly_topup_day", "1")
    monkeypatch.setattr(M, "_taipei_day", lambda: 7)
    _no_network(monkeypatch)
    seen = _capture_transfer(monkeypatch)

    assert asyncio.run(M.monthly_topup(db))["status"] == "not_today"
    assert seen == []


def test_target_zero_means_off(db, monkeypatch):
    """ZH: 0 = 不補（預設值）。"""
    _bind(db, "i@example.com", 0)
    _no_network(monkeypatch)
    seen = _capture_transfer(monkeypatch)
    assert asyncio.run(M.monthly_topup(db))["status"] == "disabled"
    assert seen == []


# ══════════════════════════════════════════════════════════════════════════
# ZH: 三、失敗時的方向
# ══════════════════════════════════════════════════════════════════════════

def test_stale_points_are_never_used(db, monkeypatch):
    """
    ZH: 🔴 同步失敗就整個放棄，**不拿舊點數算差額**（會補過頭）。
        而且**不標記月份** —— 下一輪醒來要能再試。
    """
    _bind(db, "j@example.com", 0)
    crud.set_system_config(db, "myai_monthly_topup_to", "500")

    async def boom(db_):
        raise RuntimeError("廠商掛了")
    monkeypatch.setattr(M, "sync", boom)
    seen = _capture_transfer(monkeypatch)

    res = asyncio.run(M.monthly_topup(db, force=True))
    assert res["status"] == "sync_failed"
    assert seen == []
    assert crud.get_system_config(db, M.TOPUP_MONTH_KEY, "") == "", \
        "同步失敗卻標記了月份，這個月就再也不會補"


def test_failure_after_sending_does_not_retry(db, monkeypatch):
    """
    ZH: 🔴 送出後失敗 —— 點數**可能已經轉出**。月份照樣要標記，
        否則下一輪會再送一次，有機率發兩倍。
    """
    _bind(db, "k@example.com", 0)
    crud.set_system_config(db, "myai_monthly_topup_to", "500")
    _no_network(monkeypatch)
    seen = _capture_transfer(monkeypatch, granted=False)

    res = asyncio.run(M.monthly_topup(db, force=True))
    assert res["status"] == "unknown"
    assert asyncio.run(M.monthly_topup(db, force=True))["status"] == "already_done"
    assert len(seen) == 1, "失敗後又送了一次"


def test_exception_after_sending_still_closes_the_month(db, monkeypatch):
    """
    ZH: 🔴 轉點**拋例外**時，點數可能已經送出了（連線在確認之後才斷）。
        月份照樣要標記，否則下一輪醒來會再送一次。

    ZH: 這一支是突變測試逼出來的：把「標記月份」搬到送出**之後**，
        原本 16 支測試**全部照過** —— 因為沒有一支讓轉點拋例外。
        `granted=False` 的那支是正常回傳，走的是不同的路。
    """
    _bind(db, "n@example.com", 0)
    crud.set_system_config(db, "myai_monthly_topup_to", "500")
    _no_network(monkeypatch)

    seen = []

    async def boom(rows, confirm_grant=False):
        seen.append(rows)                      # ZH: 送出去了
        raise M.MyaiSyncError("確認之後連線中斷")

    monkeypatch.setattr(M, "transfer_credit_batch", boom)

    assert asyncio.run(M.monthly_topup(db, force=True))["status"] == "failed"
    assert asyncio.run(M.monthly_topup(db, force=True))["status"] == "already_done"
    assert len(seen) == 1, "拋例外之後又送了一次"


def test_nobody_below_target_still_closes_the_month(db, monkeypatch):
    """ZH: 沒人需要補也算做完了 —— 否則每小時都會重跑一次同步。"""
    _bind(db, "l@example.com", 9999)
    crud.set_system_config(db, "myai_monthly_topup_to", "500")
    _no_network(monkeypatch)
    seen = _capture_transfer(monkeypatch)

    assert asyncio.run(M.monthly_topup(db, force=True))["status"] == "nobody_below"
    assert seen == []
    assert asyncio.run(M.monthly_topup(db, force=True))["status"] == "already_done"


# ══════════════════════════════════════════════════════════════════════════
# ZH: 四、池子不夠就不送
# ══════════════════════════════════════════════════════════════════════════

TRANSFER_PREVIEW = (
    '<div class="css_td">您的點數</div><div class="css_td">{pool}</div>'
    '<form action="transfer_credit_batch_result" method="post">'
    '<input type="text" name="emails[]" value="a@example.com" />'
    '<input type="text" name="transferPoints[]" value="100" />'
    '<input type="hidden" name="remarks[]" value="monthly-topup" />'
    '</form>')

NO_POOL_PREVIEW = (
    '<form action="transfer_credit_batch_result" method="post">'
    '<input type="text" name="emails[]" value="a@example.com" />'
    '<input type="text" name="transferPoints[]" value="100" />'
    '<input type="hidden" name="remarks[]" value="monthly-topup" />'
    '</form>')

ONE_ROW = [{"email": "a@example.com", "points": 100, "remark": "monthly-topup"}]


class FakeResponse:
    def __init__(self, text, status_code=200):
        self.text = text
        self.status_code = status_code


def _stub(monkeypatch, first_html):
    """ZH: 第一次回預覽，之後回確認完成；記錄被呼叫幾次。"""
    calls = []

    async def fake_session(do_fetch, is_valid):
        calls.append(1)
        if len(calls) == 1:
            return FakeResponse(first_html)
        return FakeResponse("<html>完成</html>")

    monkeypatch.setattr(M, "_session_request", fake_session)
    return calls


def test_pool_balance_is_parsed_from_the_real_markup():
    """ZH: 廠商用逗號分位；讀不出來要回 None（不是 0）。"""
    assert M._pool_balance('<div>您的點數</div><div>2,033,236</div>') == 2033236
    assert M._pool_balance('<div>沒有這一段</div>') is None


def test_transfer_aborts_when_the_pool_is_short(monkeypatch):
    """
    ZH: 🔴 要轉 100、池子只剩 50 → 整批不送。
        硬送的話廠商可能只轉一部分，誰拿到誰沒拿到我們查不出來。
    """
    calls = _stub(monkeypatch, TRANSFER_PREVIEW.format(pool="50"))
    with pytest.raises(M.MyaiSyncError):
        asyncio.run(M.transfer_credit_batch(ONE_ROW, confirm_grant=True))
    assert len(calls) == 1, "餘額不足卻還是送出了確認"


def test_transfer_proceeds_when_the_pool_is_enough(monkeypatch):
    """ZH: 陽性對照 —— 夠的時候要送得出去，否則上面那條等於恆真。"""
    calls = _stub(monkeypatch, TRANSFER_PREVIEW.format(pool="1,000"))
    res = asyncio.run(M.transfer_credit_batch(ONE_ROW, confirm_grant=True))
    assert res["granted"] is True
    assert len(calls) == 2


def test_unreadable_pool_does_not_block_the_transfer(monkeypatch):
    """
    ZH: 讀不到餘額（廠商改版型）→ 照送並在日誌講明，**不要當成餘額 0**。
        當成 0 的話每一次補點都會被擋下來，而那看起來像功能壞了。
    """
    calls = _stub(monkeypatch, NO_POOL_PREVIEW)
    res = asyncio.run(M.transfer_credit_batch(ONE_ROW, confirm_grant=True))
    assert res["granted"] is True
    assert len(calls) == 2


# ══════════════════════════════════════════════════════════════════════════
# ZH: 五、手動補齊
# ══════════════════════════════════════════════════════════════════════════

def test_manual_preview_sends_nothing(db, monkeypatch):
    """ZH: dry_run（預設）只回報，不送出 —— 不可逆的操作先讓人看一眼。"""
    _bind(db, "p1@example.com", 100)
    _no_network(monkeypatch)
    seen = _capture_transfer(monkeypatch)

    res = asyncio.run(M.manual_topup(db, 500, "admin-id"))
    assert res["status"] == "preview"
    assert res["count"] == 1 and res["points"] == 400
    assert seen == [], "預覽卻送出去了"


def test_manual_ignores_the_monthly_gate(db, monkeypatch):
    """
    ZH: 手動補齊**不看補點日、也不看「這個月做過了沒」** ——
        它就是為了例外而存在的。這一點與 monthly_topup 刻意不同。
    """
    # ZH: admin_id 要是真的使用者 —— admin_actions.admin_id 有外鍵，
    #     隨便給一個字串會 IntegrityError（測試環境有開 foreign_keys）。
    admin = make_user(db, username="adm3", email="adm3@example.com", role="admin")
    _bind(db, "p2@example.com", 0)
    crud.set_system_config(db, M.TOPUP_MONTH_KEY, M._taipei_month())  # ZH: 這個月做過了
    _no_network(monkeypatch)
    seen = _capture_transfer(monkeypatch)

    res = asyncio.run(M.manual_topup(db, 500, admin.id, dry_run=False))
    assert res["status"] == "done"
    assert len(seen) == 1


def test_manual_twice_does_not_double_grant(db, monkeypatch):
    """
    ZH: 🔴 重複按不會重複發放 —— 因為是「補到 N」不是「加 N」。
        第一次跑完大家都在 N，第二次算差額就是空的。
        **這是不要把它改成「固定加」的理由。**
    """
    admin = make_user(db, username="adm4", email="adm4@example.com", role="admin")
    _bind(db, "p3@example.com", 0)
    sent = []

    async def fake_transfer(rows, confirm_grant=False):
        sent.append(rows)
        # ZH: 模擬廠商真的把點數加上去了 —— 下一次同步就會看到新值
        row = db.query(models.MyaiAccount).filter_by(email="p3@example.com").first()
        row.points = 500
        db.commit()
        return {"ok": True, "granted": True, "count": len(rows), "points": 500}

    monkeypatch.setattr(M, "transfer_credit_batch", fake_transfer)
    _no_network(monkeypatch)

    assert asyncio.run(M.manual_topup(db, 500, admin.id, dry_run=False))["status"] == "done"
    second = asyncio.run(M.manual_topup(db, 500, admin.id, dry_run=False))
    assert second["status"] == "nobody_below"
    assert len(sent) == 1, "按第二次又送了一批"


def test_manual_writes_an_audit_row(db, monkeypatch):
    """
    ZH: 不可逆的操作要留下軌跡。手動補齊**有真正的執行者**，
        所以稽核寫得進 admin_actions（自動補點沒有管理員，只能記在帳號上）。
    """
    admin = make_user(db, username="adm2", email="adm2@example.com", role="admin")
    _bind(db, "p4@example.com", 0)
    _no_network(monkeypatch)
    _capture_transfer(monkeypatch)

    asyncio.run(M.manual_topup(db, 500, admin.id, dry_run=False))
    rows = (db.query(models.AdminAction)
              .filter(models.AdminAction.action == "myai_manual_topup").all())
    assert len(rows) == 1
    assert rows[0].admin_id == admin.id
    assert "500" in rows[0].payload


def test_manual_rejects_non_positive_target(db, monkeypatch):
    """ZH: 補到 0 或負數沒有意義，擋在最前面。"""
    _no_network(monkeypatch)
    for bad in (0, -1):
        with pytest.raises(M.MyaiSyncError):
            asyncio.run(M.manual_topup(db, bad, "a", dry_run=False))


# ══════════════════════════════════════════════════════════════════════════
# ZH: 六、個別加點
# ══════════════════════════════════════════════════════════════════════════
# ZH: 🔴 這一支與補齊**語意相反**：它是「加 N」，不是冪等的。
#     測試要釘住的是「它誠實地不冪等」，不是假裝它是。

def test_grant_adds_the_amount(db, monkeypatch):
    """ZH: 加 N 就是加 N，不是補到 N。"""
    admin = make_user(db, username="ga", email="ga@example.com", role="admin")
    u = _bind(db, "g1@example.com", 100)
    seen = _capture_transfer(monkeypatch)

    res = asyncio.run(M.grant_points(db, u, 250, admin.id, "個別需求"))
    assert res["status"] == "done"
    assert res["before"] == 100 and res["after"] == 350
    assert seen[0][0]["points"] == 250, "送出的是差額而不是加值"


def test_grant_twice_really_grants_twice(db, monkeypatch):
    """
    ZH: 🔴 **刻意驗證它不冪等。**

    ZH: 這不是缺陷，是這支功能的語意（個別加點就是要能加第二次）。
        寫成測試是為了讓下一個人清楚知道：擋重複的責任在介面，不在這裡。
        哪天有人把它「修」成冪等，這條會紅並問他是不是搞混了兩支功能。
    """
    admin = make_user(db, username="gb", email="gb@example.com", role="admin")
    u = _bind(db, "g2@example.com", 0)
    seen = _capture_transfer(monkeypatch)

    asyncio.run(M.grant_points(db, u, 100, admin.id))
    asyncio.run(M.grant_points(db, u, 100, admin.id))
    assert len(seen) == 2, "第二次沒送出 —— 個別加點不該被當成冪等的"


def test_grant_writes_audit_with_the_target_user(db, monkeypatch):
    """
    ZH: 加點是給特定某個人的，稽核要查得到「誰拿到了」——
        所以 target_user 必須有值（手動補齊那支是整批，沒有單一對象）。
    """
    admin = make_user(db, username="gc", email="gc@example.com", role="admin")
    u = _bind(db, "g3@example.com", 0)
    _capture_transfer(monkeypatch)

    asyncio.run(M.grant_points(db, u, 50, admin.id, "社團活動"))
    row = (db.query(models.AdminAction)
             .filter(models.AdminAction.action == "myai_grant_points").one())
    assert row.admin_id == admin.id
    assert row.target_user == u.id
    assert "社團活動" in row.payload


def test_grant_refuses_unbound_user(db, monkeypatch):
    """ZH: 沒綁定就沒有可以加點的對象 —— 明講，不要靜靜地不做事。"""
    admin = make_user(db, username="gd", email="gd@example.com", role="admin")
    lonely = make_user(db, username="lonely", email="lonely@example.com")
    seen = _capture_transfer(monkeypatch)
    with pytest.raises(M.MyaiSyncError):
        asyncio.run(M.grant_points(db, lonely, 100, admin.id))
    assert seen == []


def test_grant_refuses_the_source_account(db, monkeypatch):
    """ZH: 不能加給轉出帳號自己 —— 自己轉給自己，廠商行為未知。"""
    admin = make_user(db, username="ge", email="ge@example.com", role="admin")
    u = _bind(db, "boss2@example.com", 0)
    monkeypatch.setattr(M.settings, "MYAI_ADMIN_EMAIL", "BOSS2@example.com")
    seen = _capture_transfer(monkeypatch)
    with pytest.raises(M.MyaiSyncError):
        asyncio.run(M.grant_points(db, u, 100, admin.id))
    assert seen == []


@pytest.mark.parametrize("bad", [0, -10])
def test_grant_refuses_non_positive(db, monkeypatch, bad):
    """ZH: 加 0 是白跑；負數在廠商端的行為未知（可能變成扣點）。"""
    admin = make_user(db, username="gf" + str(abs(bad)), role="admin",
                      email="gf%d@example.com" % abs(bad))
    u = _bind(db, "g4-%d@example.com" % abs(bad), 0)
    seen = _capture_transfer(monkeypatch)
    with pytest.raises(M.MyaiSyncError):
        asyncio.run(M.grant_points(db, u, bad, admin.id))
    assert seen == []
