# -*- coding: utf-8 -*-
"""
ZH: v3.7 —— 臨時帳號（校外人士、長官視察、例外用途）。

ZH: 這份測試的重點**不是「能不能建帳號」**，而是「到期會不會真的生效」。
    一個寫著到期日卻還登得進來的帳號，比沒有到期日更糟 ——
    管理者會以為它自己會關掉，於是不再管它。

ZH: 三個必須各自釘住的點：
      1. 登入路徑擋（即時）
      2. **已經發出去的 token 也要擋**（不然到期前登入的人可以繼續用到 token 過期）
      3. 每日排程把 is_active 設成 0（讓管理端看得出來）
    只做第 3 點的話，中間有最多一整天的空窗。
"""
import pathlib
import sys
from datetime import datetime, timedelta, timezone

import pytest

from conftest import make_user, auth_headers

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "job-scheduler"))
from app import crud, models   # noqa: E402


@pytest.fixture
def admin_headers(client, db):
    make_user(db, username="root", email="root@example.com", role="admin")
    return auth_headers(client, "root")


def _create(client, headers, **kw):
    body = {"username": "guest1", "purpose": "教育部訪視", "days": 1}
    body.update(kw)
    return client.post("/api/v1/admin/users/temporary", json=body, headers=headers)


# ──────────────────────────────────────────────────────────────────────────
# ZH: 一、建立
# ──────────────────────────────────────────────────────────────────────────

def test_creates_account_and_returns_the_password_once(client, db, admin_headers):
    """ZH: 沒有信可寄，所以密碼必須回傳 —— 那是唯一一次拿得到明文的機會。"""
    r = _create(client, admin_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["password"], body
    assert body["purpose"] == "教育部訪視"
    assert body["has_email"] is False

    u = db.query(models.User).filter_by(username="guest1").first()
    assert u is not None
    assert u.expires_at is not None
    assert u.temp_purpose == "教育部訪視"


def test_password_actually_works(client, db, admin_headers):
    """ZH: 陰性對照 —— 回傳的密碼要真的登得進來，不然這個功能等於沒有。"""
    pw = _create(client, admin_headers).json()["password"]
    r = client.post("/api/v1/auth/login",
                    data={"username": "guest1", "password": pw})
    assert r.status_code == 200, r.text


def test_no_email_means_a_reserved_domain_not_a_real_looking_one(client, db, admin_headers):
    """ZH: 🔴 沒填 email 時合成的位址必須是**永遠不可能存在**的網域。

    ZH: `users.email` 是 NOT NULL + UNIQUE，所以一定要填點什麼。
        填一個看起來像真的（例如 guest1@mcu.edu.tw）會有兩個後果：
        平台可能真的寄信過去，而且那個位址可能真的屬於某個人。
        `.invalid` 是 RFC 2606 保留、永遠不會被指派的網域。
    """
    _create(client, admin_headers)
    u = db.query(models.User).filter_by(username="guest1").first()
    assert u.email.endswith("@invalid"), u.email


def test_purpose_is_required(client, db, admin_headers):
    """ZH: 用途必填 —— 半年後看到一個叫 guest3 的帳號而沒有人知道為什麼，
       就沒有人敢刪它。那是臨時帳號變成永久帳號的標準路徑。
    """
    assert _create(client, admin_headers, purpose="").status_code == 422
    assert _create(client, admin_headers, purpose="   ").status_code == 422


def test_days_has_an_upper_bound(client, db, admin_headers):
    """ZH: 超過 90 天就不叫臨時了，應該走正式開帳號的流程。"""
    assert _create(client, admin_headers, days=91).status_code == 422
    assert _create(client, admin_headers, days=0).status_code == 422


def test_creating_is_audited(client, db, admin_headers):
    """ZH: 「誰、什麼時候、為了什麼開了這個帳號」要留得住。"""
    _create(client, admin_headers)
    act = db.query(models.AdminAction).filter_by(action="create_temp_account").first()
    assert act is not None
    assert "教育部訪視" in (act.payload or "")


# ──────────────────────────────────────────────────────────────────────────
# ZH: 二、🔴 到期真的會生效（這一節才是重點）
# ──────────────────────────────────────────────────────────────────────────

def _expire(db, username="guest1"):
    u = db.query(models.User).filter_by(username=username).first()
    u.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db.commit()
    return u


def test_expired_account_cannot_log_in(client, db, admin_headers):
    """ZH: 🔴 到期就登不進來 —— 即時，不等排程。"""
    pw = _create(client, admin_headers).json()["password"]
    _expire(db)
    r = client.post("/api/v1/auth/login", data={"username": "guest1", "password": pw})
    assert r.status_code == 401, r.text


def test_token_issued_before_expiry_stops_working(client, db, admin_headers):
    """ZH: 🔴 **已經發出去的 token 也要擋。**

    ZH: 只在登入時檢查的話，到期前幾分鐘登入的人可以繼續用到 token 自己過期
        （預設 120 分鐘）。長官視察結束後那兩個小時，帳號其實還活著。
    """
    pw = _create(client, admin_headers).json()["password"]
    tok = client.post("/api/v1/auth/login",
                      data={"username": "guest1", "password": pw}).json()["access_token"]
    h = {"Authorization": f"Bearer {tok}"}

    # 還沒到期 → 正常
    assert client.get("/api/v1/auth/me", headers=h).status_code == 200

    _expire(db)

    # 到期後 → 同一個 token 應該失效
    r = client.get("/api/v1/auth/me", headers=h)
    assert r.status_code == 403, r.text


def test_permanent_accounts_are_untouched(client, db, admin_headers):
    """ZH: 陰性對照 —— 沒有 expires_at 的一般帳號完全不受影響。

    ZH: 這條在防的是「到期判斷把 None 當成很久以前」這種寫法，
        那會**把全校的帳號一起鎖掉**。
    """
    make_user(db, username="normal", email="n@example.com")
    h = auth_headers(client, "normal")
    assert client.get("/api/v1/auth/me", headers=h).status_code == 200

    u = db.query(models.User).filter_by(username="normal").first()
    assert u.expires_at is None
    from app import auth as _auth
    assert _auth.is_expired(u) is False


def test_daily_sweep_marks_expired_as_disabled(client, db, admin_headers):
    """ZH: 排程把 is_active 設成 0 —— 讓管理端**看得出來**。

    ZH: 少了這一步，清單上它還是「啟用」而實際上登不進來，
        那種不一致會讓人以為是登入功能壞了。
    """
    _create(client, admin_headers)
    _expire(db)
    n = crud.disable_expired_temp_accounts(db)
    assert n == 1
    u = db.query(models.User).filter_by(username="guest1").first()
    assert u.is_active == 0


def test_sweep_does_not_rewrite_already_disabled_accounts(client, db, admin_headers):
    """ZH: 只改「還是啟用中」的那些 —— 否則每天都重複寫一次，
       稽核紀錄會被灌滿沒有意義的變更。
    """
    _create(client, admin_headers)
    _expire(db)
    assert crud.disable_expired_temp_accounts(db) == 1
    assert crud.disable_expired_temp_accounts(db) == 0     # 第二次不該再動它


def test_admin_list_shows_expiry_and_purpose(client, db, admin_headers):
    """ZH: 🔴 清單要看得出**什麼時候失效、為什麼存在**。

    ZH: 沒有這兩個欄位的話，臨時帳號在清單裡與一般帳號長得一模一樣，
        於是它會被當成一般帳號留下來。
        （而且這裡是**手工建構** AdminUserListItem 的，
          光在 schema 加欄位不會生效 —— 那個坑在 v3.6 踩過兩次。）
    """
    _create(client, admin_headers)
    rows = client.get("/api/v1/admin/users?limit=500", headers=admin_headers).json()
    me = [r for r in rows if r["username"] == "guest1"][0]
    assert me["expires_at"] is not None, me
    assert me["temp_purpose"] == "教育部訪視", me


# ──────────────────────────────────────────────────────────────────────────
# ZH: 三、延期
#
# ZH: 這一節在防的是**兩種「按了沒反應」**：延期之後對方還是登不進來，
#     而畫面上完全沒有錯誤訊息。兩個原因各自獨立，要各自釘住。
# ──────────────────────────────────────────────────────────────────────────

def _extend(client, headers, uid, days=7):
    return client.post(f"/api/v1/admin/users/{uid}/extend",
                       json={"days": days}, headers=headers)


def test_extend_pushes_the_expiry_out(client, db, admin_headers):
    _create(client, admin_headers)
    u = db.query(models.User).filter_by(username="guest1").first()
    before = u.expires_at

    assert _extend(client, admin_headers, u.id).status_code == 200
    db.refresh(u)
    assert u.expires_at > before


def test_extending_an_expired_account_actually_makes_it_usable(client, db, admin_headers):
    """ZH: 🔴 已經過期的要**從現在起算**，不是從舊的到期日。

    ZH: 從舊日期起算的話，一個過期一個月的帳號「延長 7 天」之後**仍然是過期的**——
        管理者按了、沒有錯誤訊息、對方還是登不進來。
    """
    pw = _create(client, admin_headers).json()["password"]
    u = db.query(models.User).filter_by(username="guest1").first()
    u.expires_at = datetime.now(timezone.utc) - timedelta(days=30)
    db.commit()

    assert _extend(client, admin_headers, u.id, days=7).status_code == 200

    db.refresh(u)
    assert u.expires_at > datetime.now(timezone.utc).replace(tzinfo=None) \
        if u.expires_at.tzinfo is None else u.expires_at > datetime.now(timezone.utc)

    # ZH: 真正的判準不是欄位值，是**他能不能登入**
    r = client.post("/api/v1/auth/login", data={"username": "guest1", "password": pw})
    assert r.status_code == 200, r.text


def test_extending_reenables_an_account_the_sweep_disabled(client, db, admin_headers):
    """ZH: 🔴 延期要把 is_active 設回 1。

    ZH: 每日排程會把過期帳號標成停用。只改到期日而不解除停用的話，
        帳號依舊登不進來 —— 一樣是按了沒反應、沒有任何錯誤訊息。
    """
    pw = _create(client, admin_headers).json()["password"]
    _expire(db)
    crud.disable_expired_temp_accounts(db)          # 模擬排程跑過
    u = db.query(models.User).filter_by(username="guest1").first()
    assert u.is_active == 0

    _extend(client, admin_headers, u.id)
    db.refresh(u)
    assert u.is_active == 1

    r = client.post("/api/v1/auth/login", data={"username": "guest1", "password": pw})
    assert r.status_code == 200, r.text


def test_cannot_extend_a_normal_account(client, db, admin_headers):
    """ZH: 一般帳號沒有到期日，延長它沒有意義 —— 要明確拒絕而不是默默寫一個到期日進去
       （那會把一個永久帳號變成臨時帳號）。
    """
    make_user(db, username="normal", email="n@example.com")
    uid = db.query(models.User).filter_by(username="normal").first().id
    r = _extend(client, admin_headers, uid)
    assert r.status_code == 400, r.text


def test_extend_is_audited(client, db, admin_headers):
    _create(client, admin_headers)
    uid = db.query(models.User).filter_by(username="guest1").first().id
    _extend(client, admin_headers, uid)
    assert db.query(models.AdminAction).filter_by(action="extend_temp_account").first() is not None
