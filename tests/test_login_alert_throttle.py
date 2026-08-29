"""
ZH: 登入通知信的節流測試。

ZH: 這裡守的不是「信有沒有寄」，而是**節流不能把換 IP 的登入一起吃掉** ——
    登入通知唯一真正的價值就是「有人從沒看過的地方登入」。
    節流失效的方向是安靜的（信變少，看起來像設定生效），所以每一條都要有陽性對照。
"""
import sys
import os
from datetime import datetime, timezone, timedelta

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "job-scheduler"))

from app import crud, models  # noqa: E402
from app.services.email_service import LOGIN_ALERT_KIND  # noqa: E402
from conftest import make_user  # noqa: E402


def _log(db, user_id, minutes_ago):
    """ZH: 塞一筆過去的登入通知紀錄（節流是讀 email_log 判斷的）。"""
    db.add(models.EmailLog(
        to_email="x@example.com", user_id=user_id, kind=LOGIN_ALERT_KIND,
        subject="s", status="sent",
        created_at=datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)))
    db.commit()


def _set(db, **kv):
    for k, v in kv.items():
        crud.set_system_config(db, k, str(v))


def test_default_behaviour_is_unchanged(db):
    """
    ZH: 陽性對照 —— 預設值（email=1, hours=0）必須維持「每次都寄」。
        加了設定卻順手改掉現況，是這種修改最常見的意外。
    """
    u = make_user(db, username="a", email="a@example.com")
    send, why = crud.should_send_login_alert(db, u.id, "1.1.1.1", "1.1.1.1")
    assert send is True and why == "always"


def test_master_switch_off_suppresses_everything(db):
    """ZH: 總開關關掉就不寄 —— 連換 IP 也不寄（使用者明確關掉的東西要真的關掉）。"""
    u = make_user(db, username="b", email="b@example.com")
    _set(db, login_alert_email=0)
    assert crud.should_send_login_alert(db, u.id, "1.1.1.1", "9.9.9.9")[0] is False


def test_same_ip_within_interval_is_throttled(db):
    """ZH: 同一個 IP、間隔內 → 不寄。這是使用者要的那件事。"""
    u = make_user(db, username="c", email="c@example.com")
    _set(db, login_alert_email=1, login_alert_hours=24)
    _log(db, u.id, minutes_ago=60)
    send, why = crud.should_send_login_alert(db, u.id, "1.1.1.1", "1.1.1.1")
    assert send is False and why == "throttled"


def test_same_ip_after_interval_sends_again(db):
    """ZH: 陽性對照 —— 超過間隔就要恢復寄信，否則等於永久關掉。"""
    u = make_user(db, username="d", email="d@example.com")
    _set(db, login_alert_email=1, login_alert_hours=1)
    _log(db, u.id, minutes_ago=90)
    assert crud.should_send_login_alert(db, u.id, "1.1.1.1", "1.1.1.1")[0] is True


def test_new_ip_always_sends_even_inside_the_interval(db):
    """
    ZH: 🔴 整組測試的核心 —— 換 IP 一律照寄，不看間隔。
        剛剛才寄過、間隔設很長，但位址不同 → 還是要寄。
    """
    u = make_user(db, username="e", email="e@example.com")
    _set(db, login_alert_email=1, login_alert_hours=720)
    _log(db, u.id, minutes_ago=1)
    send, why = crud.should_send_login_alert(db, u.id, "1.1.1.1", "2.2.2.2")
    assert send is True and why == "new_ip"


def test_throttle_counts_failed_sends_too(db):
    """
    ZH: 寄失敗的紀錄一樣算數 —— SMTP 掛掉時不該反過來把人的信箱洗版。
    """
    u = make_user(db, username="f", email="f@example.com")
    _set(db, login_alert_email=1, login_alert_hours=24)
    db.add(models.EmailLog(to_email="f@example.com", user_id=u.id,
                           kind=LOGIN_ALERT_KIND, subject="s", status="failed",
                           created_at=datetime.now(timezone.utc)))
    db.commit()
    assert crud.should_send_login_alert(db, u.id, "1.1.1.1", "1.1.1.1")[0] is False


def test_throttle_is_per_user(db):
    """
    ZH: 節流分人 —— 不分人的話，一個人登入之後其他人全部收不到通知。
    """
    a = make_user(db, username="g", email="g@example.com")
    b = make_user(db, username="h", email="h@example.com")
    _set(db, login_alert_email=1, login_alert_hours=24)
    _log(db, a.id, minutes_ago=1)
    assert crud.should_send_login_alert(db, a.id, "1.1.1.1", "1.1.1.1")[0] is False
    assert crud.should_send_login_alert(db, b.id, "1.1.1.1", "1.1.1.1")[0] is True


def test_first_ever_login_sends(db):
    """ZH: 第一次登入 prev_ip 是 None → 與現在的 IP 不同 → 寄。"""
    u = make_user(db, username="i", email="i@example.com")
    _set(db, login_alert_email=1, login_alert_hours=720)
    send, why = crud.should_send_login_alert(db, u.id, None, "1.1.1.1")
    assert send is True and why == "new_ip"


# ══════════════════════════════════════════════════════════════════════════
# ZH: 呼叫端的接線 —— helper 對不代表路由用對了
# ══════════════════════════════════════════════════════════════════════════
# ZH: 🔴 這兩支測的是 auth.py 的 `prev_login_ip` 有沒有在**被蓋掉之前**抄下來。
#     抄在之後的話 prev 永遠等於 now，換 IP 的登入會被節流吃掉 ——
#     而單元測 helper 完全看不出來（helper 拿到什麼就算什麼）。
#
# ZH: ⚠️ 這裡**不能數 email_log 的筆數**來判斷有沒有寄：email_service._record
#     自己開 SessionLocal，而測試環境把它隔離到另一個記憶體 DB，
#     從 db fixture 查永遠是 0 筆。改成攔 send_login_alert 本身 ——
#     那正好就是這兩支要問的問題（路由到底有沒有決定要寄）。


def _capture(monkeypatch):
    """ZH: 攔下 send_login_alert，回傳被呼叫時收到的參數清單。"""
    from app.services import email_service
    got = []
    monkeypatch.setattr(email_service, "send_login_alert",
                        lambda *a, **k: got.append(a))
    return got


def test_route_throttles_repeat_login_from_same_ip(client, db, monkeypatch):
    """ZH: 同一個來源、間隔內已寄過 → 路由不該再寄。"""
    u = make_user(db, username="r1", email="r1@example.com")
    _set(db, login_alert_email=1, login_alert_hours=24)
    _log(db, u.id, minutes_ago=1)
    u.last_login_ip = "testclient"          # ZH: 上一次就是這個來源
    db.commit()

    got = _capture(monkeypatch)
    r = client.post("/api/v1/auth/login",
                    data={"username": "r1", "password": "password123"})
    assert r.status_code == 200, r.text
    assert got == [], f"節流沒生效，還是寄了：{got}"


def test_route_still_alerts_when_the_ip_changed(client, db, monkeypatch):
    """
    ZH: 🔴 上一次的 IP 與這次不同 → 即使剛寄過、間隔設到最長，也要寄。

    ZH: 這一支是用來釘住「prev_login_ip 抄在覆寫之前」的。
        把那行搬到覆寫之後，prev 就會等於 now，這裡會變成 0 次。
    """
    u = make_user(db, username="r2", email="r2@example.com")
    _set(db, login_alert_email=1, login_alert_hours=720)
    _log(db, u.id, minutes_ago=1)           # ZH: 剛剛才寄過
    u.last_login_ip = "203.0.113.9"         # ZH: 上一次是別的位址
    db.commit()

    got = _capture(monkeypatch)
    r = client.post("/api/v1/auth/login",
                    data={"username": "r2", "password": "password123"})
    assert r.status_code == 200, r.text
    assert len(got) == 1, "換了 IP 卻沒寄（prev_login_ip 可能抄在覆寫之後）"
    assert got[0][3] == u.id, "沒把 user_id 傳下去，email_log 那一欄會是 NULL"
