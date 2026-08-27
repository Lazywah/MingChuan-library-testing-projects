"""
ZH: 管理員告警的 To / CC（v3.8）。

ZH: v3.7 以前是**逐一寄**（一人一封，彼此看不到對方信箱）。
    擁有者 2026-08-27 裁定改成一封信 To + CC —— 讓收件人看得出誰也收到了，
    才不會三個人同時處理同一件事、或三個人都以為別人會處理。

ZH: 這裡守三件會靜默出錯的事：
      1. CC 有沒有放進**信封收件人**（只寫 Cc 標頭的話，CC 的人收不到而且不報錯）
      2. 一封多人的信，email_log 要**每個收件人一列**（否則名冊對不回退信）
      3. 退信要對回**正確的那一列**（同一個 Message-ID 現在有多列）
"""
import pytest
from sqlalchemy.orm import sessionmaker

from app import crud, database, models
from app.services import bounce_reader, email_service


# ── 地址正規化 ────────────────────────────────────────────────────────
@pytest.mark.parametrize("raw,expected", [
    ("a@x.com", ["a@x.com"]),
    ("a@x.com, b@y.com", ["a@x.com", "b@y.com"]),
    ("a@x.com,,  ,b@y.com ", ["a@x.com", "b@y.com"]),
    (["a@x.com", "A@X.COM"], ["a@x.com"]),          # ZH: 大小寫視為同一人
    (None, []),
    ("", []),
])
def test_addr_list(raw, expected):
    assert email_service._addr_list(raw) == expected


# ── 共用：把寄信紀錄導到測試 DB ──────────────────────────────────────
@pytest.fixture
def log_to_test_db(db_engine, monkeypatch):
    """
    ZH: `_record` 是在函式內才 `from ..database import SessionLocal`，
        所以換掉模組屬性就會被它拿到。不這樣做的話，測試會寫進**正式 DB**。
    """
    monkeypatch.setattr(database, "SessionLocal",
                        sessionmaker(autocommit=False, autoflush=False, bind=db_engine))


@pytest.fixture
def smtp(monkeypatch, log_to_test_db):
    """
    ZH: 攔在 smtplib 這一層，不是攔 send_email —— 這樣 send_email 的整段邏輯
        （保留網域閘門、信封組裝、逐個收件人記錄）都會真的跑過。
        攔 send_email 的話，這個測試就只是在測我自己寫的假函式。

    ZH: 測試地址用 `.test`（RFC 6761 保留），所以要把保留網域閘門讓開 ——
        那道閘門是另一件事，有它自己的測試。
    """
    sent = {}

    class FakeSMTP:
        def __init__(self, host, port):
            sent["host"] = host

        def ehlo(self):
            pass

        def starttls(self):
            pass

        def login(self, u, p):
            pass

        def sendmail(self, from_addr, to_addrs, body):
            sent["from"] = from_addr
            sent["envelope"] = list(to_addrs)
            sent["body"] = body
            return sent.get("refuse", {})

        def quit(self):
            pass

    monkeypatch.setattr(email_service.smtplib, "SMTP", FakeSMTP)
    monkeypatch.setattr(email_service, "_smtp", lambda: {
        "server": "smtp.example.test", "port": 587, "username": "", "password": "",
        "from_email": "noreply@mcu.test",
    })
    monkeypatch.setattr(email_service, "is_undeliverable_by_spec", lambda a: False)
    return sent


# ── 寄送 ─────────────────────────────────────────────────────────────
def test_cc_is_in_the_envelope(smtp):
    """
    ZH: 🔴 只設 Cc 標頭而沒放進 sendmail 的收件人清單 → CC 的人**收不到，
        而且完全不報錯**。這是這次改動最容易犯又最難發現的錯。
    """
    email_service.send_email("a@x.test", "s", "<p>h</p>", cc=["c@y.test"])
    assert smtp["envelope"] == ["a@x.test", "c@y.test"]
    assert "Cc: c@y.test" in smtp["body"]
    assert "To: a@x.test" in smtp["body"]


def test_no_cc_header_when_cc_is_empty(smtp):
    email_service.send_email("a@x.test", "s", "<p>h</p>")
    assert smtp["envelope"] == ["a@x.test"]
    assert "Cc:" not in smtp["body"]


def test_address_in_both_to_and_cc_is_sent_once(smtp):
    """ZH: 重複的話對方會收到兩封，email_log 也會多一筆對不到退信的紀錄。"""
    email_service.send_email(["a@x.test", "b@x.test"], "s", "<p>h</p>",
                             cc=["a@x.test", "c@x.test"])
    assert smtp["envelope"] == ["a@x.test", "b@x.test", "c@x.test"]


def test_each_recipient_gets_its_own_log_row(db, smtp):
    """
    ZH: 一封信多個收件人 → email_log **每人一列**。
        名冊的用途是「收到退信時查出那是誰」，只記一列的話 CC 的人查不到。
    """
    email_service.send_email(["a@x.test", "b@x.test"], "主旨 | Subject", "<p>h</p>",
                             kind="alert:unit", cc=["c@x.test"])
    rows = db.query(models.EmailLog).filter(models.EmailLog.kind == "alert:unit").all()
    assert {r.to_email for r in rows} == {"a@x.test", "b@x.test", "c@x.test"}
    assert len({r.message_id for r in rows}) == 1, "同一封信應該共用一個 Message-ID"


def test_partial_refusal_only_marks_the_refused_one(db, smtp):
    """
    ZH: `sendmail` 回傳的 dict 只含**被拒的那幾個**，其餘是照常送出的。
        整封記成同一個狀態的話，一個地址被拒會讓其他人也顯示成失敗。
    """
    smtp["refuse"] = {"b@x.test": (550, b"No such user")}
    email_service.send_email(["a@x.test", "b@x.test"], "主旨 | Subject", "<p>h</p>",
                             kind="alert:partial")
    rows = {r.to_email: r.status for r in
            db.query(models.EmailLog).filter(models.EmailLog.kind == "alert:partial").all()}
    assert rows == {"a@x.test": "sent", "b@x.test": "refused"}


# ── 收件人設定 ───────────────────────────────────────────────────────
@pytest.fixture
def alert_calls(monkeypatch, log_to_test_db):
    """ZH: 這一組測的是「兩個設定怎麼變成 To 與 CC」，寄送本身上面已經測過了。"""
    calls = []
    monkeypatch.setattr(email_service, "send_email",
                        lambda to, subj, html, **kw: calls.append((to, kw.get("cc"))))
    return calls


def test_alert_uses_both_lists(db, alert_calls):
    crud.set_settings(db, {"admin_alert_emails": "boss@x.test",
                           "admin_alert_cc_emails": "team@x.test, log@x.test"})
    n = email_service.send_admin_alert("unit", "主旨 | Subject", "<p>h</p>")

    assert len(alert_calls) == 1, "應該只寄一封信（To + CC），不是逐一寄"
    to, cc = alert_calls[0]
    assert to == ["boss@x.test"]
    assert cc == ["team@x.test", "log@x.test"]
    assert n == 3


def test_cc_only_is_promoted_to_to(db, alert_calls):
    """ZH: 一封沒有 To 的信會被不少伺服器判成垃圾信；管理員多半只是填錯欄位。"""
    crud.set_settings(db, {"admin_alert_emails": "",
                           "admin_alert_cc_emails": "team@x.test"})
    email_service.send_admin_alert("unit2", "主旨 | Subject", "<p>h</p>")
    assert alert_calls == [(["team@x.test"], [])]


def test_both_lists_empty_sends_nothing(db, alert_calls):
    """ZH: 沒有人填收件人的告警系統應該安靜，而不是往預設信箱亂寄。"""
    crud.set_settings(db, {"admin_alert_emails": "", "admin_alert_cc_emails": ""})
    assert email_service.send_admin_alert("unit3", "主旨 | Subject", "<p>h</p>") == 0
    assert alert_calls == []


# ── 退信對回 ─────────────────────────────────────────────────────────
def _row(db, addr, mid):
    r = models.EmailLog(to_email=addr, subject="s", status="sent",
                        kind="alert:unit", message_id=mid)
    db.add(r)
    db.commit()
    return r


def test_bounce_lands_on_the_right_recipient(db):
    """
    ZH: 🔴 一個 Message-ID 現在對到多列。C 的退信必須記在 C 那一列 ——
        原本的 `.first()` 會記到 A 身上：A 明明寄成功卻被標成退信，
        而且沒有任何錯誤訊息。
    """
    mid = "<multi@mcu.test>"
    a = _row(db, "a@x.test", mid)
    c = _row(db, "c@x.test", mid)

    bounce_reader.apply_bounce(db, {"message_id": mid, "recipients": [
        {"recipient": "c@x.test", "status": "5.1.1", "action": "failed",
         "diagnostic": "no such user"}]})
    db.refresh(a)
    db.refresh(c)

    assert c.status != "sent" and c.bounced_at is not None, "C 應該被標成退信"
    assert a.status == "sent" and a.bounced_at is None, "A 不該被動到"


def test_single_recipient_bounce_still_works(db):
    """ZH: 單收件人（絕大多數的信）要與改版前完全一樣。"""
    mid = "<single@mcu.test>"
    r = _row(db, "solo@x.test", mid)
    bounce_reader.apply_bounce(db, {"message_id": mid, "recipients": [
        {"recipient": "solo@x.test", "status": "5.1.1", "action": "failed",
         "diagnostic": "no such user"}]})
    db.refresh(r)
    assert r.bounced_at is not None


def test_unmatched_address_in_a_multi_row_message_is_not_backfilled(db):
    """ZH: 對不到地址時寧可少記一筆，也不要把退信記到不相干的人身上。"""
    mid = "<multi2@mcu.test>"
    a = _row(db, "a@x.test", mid)
    b = _row(db, "b@x.test", mid)

    n = bounce_reader.apply_bounce(db, {"message_id": mid, "recipients": [
        {"recipient": "someone-else@z.test", "status": "5.1.1", "action": "failed",
         "diagnostic": "x"}]})
    db.refresh(a)
    db.refresh(b)
    assert n == 0
    assert a.status == "sent" and b.status == "sent"


# ── 管理端渲染需要的資訊 ─────────────────────────────────────────────
def test_settings_payload_exposes_text_kind(db):
    """
    ZH: 管理端靠 `text_kind` 決定把哪些欄位畫成信箱清單。

    ZH: 漏送的話**不會壞掉，只會退回普通文字框** —— 沒有錯誤訊息，
        只是管理者又要自己打逗號，而沒有人會把這個回報成 bug。
    """
    payload = {s["key"]: s for s in crud.get_all_settings(db)}

    assert payload["admin_alert_emails"]["text_kind"] == "emails"
    assert payload["admin_alert_cc_emails"]["text_kind"] == "emails"
    # ZH: 非信箱的文字旋鈕不該被誤畫成清單
    assert payload["smtp_server"]["text_kind"] == "host"
    # ZH: 數字型沒有 text_kind，但欄位一定要在（前端讀 undefined 不會報錯，
    #     可是「鍵不存在」與「值是 None」在除錯時是兩件事）
    assert "text_kind" in payload["smtp_port"]
    assert payload["smtp_port"]["text_kind"] is None


def test_every_emails_setting_is_declared_as_such(db):
    """
    ZH: 反過來守：登錄表裡凡是「收件人清單」性質的旋鈕，都要標 text_kind="emails"。
        標漏了驗證與清單介面兩件事會一起失效。
    """
    missing = [k for k, spec in crud.SYSTEM_SETTINGS.items()
               if k.endswith("_emails") and spec.get("text_kind") != "emails"]
    assert not missing, f"這些旋鈕看起來是信箱清單卻沒標 text_kind=emails: {missing}"
