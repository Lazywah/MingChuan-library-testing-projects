"""
ZH: MYAI 點數的兩段提醒（v3.8 #9）—— 快用完一次、用完一次。

ZH: 這裡守的是三件在正式環境**很難重現**的事:
      1. 兩段的界線（沒綁帳號 ≠ 用完 ≠ 偏低）
      2. 節流是分人又分階段的
      3. 「快用完 → 用完」一定寄得出第二封
    第 3 點是整個功能的重點:如果節流只看人不看階段,
    真正該通知的那一刻反而會被當成重複而吞掉。
"""
from datetime import datetime, timedelta, timezone

import pytest

from app import crud, models
from app.services import myai_sync
from conftest import make_user


# ── 判定 ─────────────────────────────────────────────────────────────
@pytest.mark.parametrize("points,threshold,expected", [
    (None, 500, "unknown"),    # ZH: 沒綁帳號 —— 不是 0,那個人還沒開始用
    (0,    500, "empty"),
    (-30,  500, "empty"),      # ZH: 廠商回過負數（扣到透支）
    (1,    500, "low"),
    (499,  500, "low"),
    (500,  500, "ok"),         # ZH: 等於門檻不算低（門檻的語意是「低於」）
    (900,  500, "ok"),
    (10,   0,   "ok"),         # ZH: 門檻 0 = 不提醒偏低,但用完仍然算 empty
    (0,    0,   "empty"),
])
def test_balance_state(points, threshold, expected):
    assert crud.myai_balance_state(points, threshold) == expected


def test_threshold_reader_survives_garbage(db):
    """ZH: 設定值被寫成非數字時要退回預設,而不是讓整個排程炸掉。"""
    crud.set_system_config(db, crud.MYAI_LOW_BALANCE_KEY, "abc")
    assert crud.myai_low_balance_threshold(db) == crud.DEFAULT_LOW_BALANCE


# ── 寄信 ─────────────────────────────────────────────────────────────
@pytest.fixture
def outbox(db, db_engine, monkeypatch):
    """
    ZH: 讓真實的寄信路徑整條跑完,只把它寫紀錄用的 session 導到測試 DB。

    ZH: 🔴 **刻意不攔截 send_email。** 節流讀的是 email_log,
        而那張表是 send_email 內部寫的 —— 把 send_email 換成假的,
        就等於把節流要讀的東西一起換掉:第二次呼叫照樣寄,測試卻綠燈。
        （第一版就是這樣寫的,test_second_run_is_throttled 直接抓到。）

    ZH: `_record` 是在函式內才 `from ..database import SessionLocal`,
        所以換掉模組屬性就會被它拿到。不這樣做的話,測試會把紀錄寫進**正式 DB**。

    ZH: 測試信箱是 @example.com（RFC 2606 保留網域）→ 寄信路徑會判定 blocked、
        不實際外寄,但**照樣寫 email_log** —— 正是節流需要的。
    """
    from sqlalchemy.orm import sessionmaker
    from app import database

    monkeypatch.setattr(database, "SessionLocal",
                        sessionmaker(autocommit=False, autoflush=False, bind=db_engine))

    class Box:
        def kinds(self):
            db.expire_all()
            return [r.kind for r in db.query(models.EmailLog)
                    .filter(models.EmailLog.kind.like("myai_balance:%"))
                    .order_by(models.EmailLog.created_at).all()]

        def to(self):
            db.expire_all()
            return {r.to_email for r in db.query(models.EmailLog)
                    .filter(models.EmailLog.kind.like("myai_balance:%")).all()}

    return Box()


def _bind(db, user, points):
    """ZH: 建一個 MYAI 帳號列並用 email 對到平台使用者（最後那條退路）。"""
    row = models.MyaiAccount(vendor_sn=f"sn-{user.username}", email=user.email,
                             name=user.username, points=points)
    db.add(row)
    db.commit()
    return row


def _log(db, user_id, stage, when):
    """ZH: 直接補一筆寄信紀錄,用來把節流的時鐘往前撥。"""
    from app.services import email_service
    db.add(models.EmailLog(to_email="x@example.com", user_id=user_id,
                           kind=email_service.MYAI_BALANCE_KIND_PREFIX + stage,
                           subject="s", status="sent", created_at=when))
    db.commit()


def test_sends_one_email_per_stage(db, outbox):
    crud.set_system_config(db, crud.MYAI_LOW_BALANCE_KEY, "500")
    crud.set_settings(db, {"myai_balance_alert_days": "7"})
    u = make_user(db, username="low1", email="low1@example.com")
    _bind(db, u, 120)

    res = myai_sync.notify_balance_alerts(db)
    assert res["sent"] == 1, res
    assert outbox.kinds() == ["myai_balance:low"]
    assert outbox.to() == {"low1@example.com"}


def test_second_run_is_throttled(db, outbox):
    """ZH: 同一階段在間隔內只寄一次 —— 點數低會持續好幾天,每輪都寄就是洗版。"""
    crud.set_system_config(db, crud.MYAI_LOW_BALANCE_KEY, "500")
    crud.set_settings(db, {"myai_balance_alert_days": "7"})
    u = make_user(db, username="low2", email="low2@example.com")
    _bind(db, u, 120)

    myai_sync.notify_balance_alerts(db)
    res = myai_sync.notify_balance_alerts(db)
    assert res["sent"] == 0 and res["skipped"] == 1, res


def test_running_out_after_a_low_warning_still_sends(db, outbox):
    """
    ZH: 🔴 這是整個功能的重點 ——
        昨天寄過「快用完」,今天真的用完了,那一封**必須寄得出去**。
        節流若只看人不看階段,最需要通知的那一刻就會被吞掉。
    """
    crud.set_system_config(db, crud.MYAI_LOW_BALANCE_KEY, "500")
    crud.set_settings(db, {"myai_balance_alert_days": "7"})
    u = make_user(db, username="drop", email="drop@example.com")
    row = _bind(db, u, 120)

    myai_sync.notify_balance_alerts(db)                 # 快用完
    assert outbox.kinds() == ["myai_balance:low"]

    row.points = 0                                       # 用完了
    db.commit()
    res = myai_sync.notify_balance_alerts(db)
    assert res["sent"] == 1, res
    assert outbox.kinds() == ["myai_balance:low", "myai_balance:empty"]


def test_throttle_is_per_user(db, outbox):
    """ZH: 節流不分人的話,一天只寄得出一封,第二個人永遠收不到。"""
    crud.set_system_config(db, crud.MYAI_LOW_BALANCE_KEY, "500")
    crud.set_settings(db, {"myai_balance_alert_days": "7"})
    a = make_user(db, username="pa", email="pa@example.com")
    b = make_user(db, username="pb", email="pb@example.com")
    _bind(db, a, 100)
    _bind(db, b, 100)

    res = myai_sync.notify_balance_alerts(db)
    assert res["sent"] == 2, res
    assert outbox.to() == {"pa@example.com", "pb@example.com"}


def test_sends_again_after_the_interval(db, outbox):
    """ZH: 過了間隔要能再寄一次 —— 否則提醒只會出現一輩子一次。"""
    crud.set_system_config(db, crud.MYAI_LOW_BALANCE_KEY, "500")
    crud.set_settings(db, {"myai_balance_alert_days": "7"})
    u = make_user(db, username="again", email="again@example.com")
    _bind(db, u, 120)

    _log(db, u.id, "low", datetime.now(timezone.utc) - timedelta(days=8))
    res = myai_sync.notify_balance_alerts(db)
    assert res["sent"] == 1, res


def test_unbound_user_gets_nothing(db, outbox):
    """ZH: 沒綁 MYAI 帳號的人不該收到「額度用完」—— 他根本還沒開始用。"""
    crud.set_settings(db, {"myai_balance_alert_days": "7"})
    make_user(db, username="nobind", email="nobind@example.com")

    res = myai_sync.notify_balance_alerts(db)
    assert res["sent"] == 0 and outbox.kinds() == []


def test_disabled_user_gets_nothing(db, outbox):
    """ZH: 停用的帳號不寄 —— 他已經進不來了,提醒他去申請額度沒有意義。"""
    crud.set_system_config(db, crud.MYAI_LOW_BALANCE_KEY, "500")
    crud.set_settings(db, {"myai_balance_alert_days": "7"})
    u = make_user(db, username="off", email="off@example.com")
    _bind(db, u, 10)
    u.is_active = 0
    db.commit()

    res = myai_sync.notify_balance_alerts(db)
    assert res["sent"] == 0 and outbox.kinds() == []


def test_zero_days_disables_email_entirely(db, outbox):
    """ZH: 0 = 管理員關掉寄信。畫面提示仍在,但一封信都不寄。"""
    crud.set_system_config(db, crud.MYAI_LOW_BALANCE_KEY, "500")
    crud.set_settings(db, {"myai_balance_alert_days": "0"})
    u = make_user(db, username="quiet", email="quiet@example.com")
    _bind(db, u, 10)

    res = myai_sync.notify_balance_alerts(db)
    assert res["disabled"] is True
    assert res["sent"] == 0 and outbox.kinds() == []


def test_healthy_balance_sends_nothing(db, outbox):
    # ZH: v4.0 起「健康」要高於**早期**門檻（預設 10000 且預設開啟）。
    #     這個測試原本給 9000 —— 三段式上線後那是 low_early、會寄信，
    #     測試紅掉的當下就證明了早期段真的有作用。
    crud.set_system_config(db, crud.MYAI_LOW_BALANCE_KEY, "500")
    crud.set_system_config(db, crud.MYAI_EARLY_BALANCE_KEY, "10000")
    crud.set_settings(db, {"myai_balance_alert_days": "7"})
    u = make_user(db, username="fine", email="fine@example.com")
    _bind(db, u, 20000)

    res = myai_sync.notify_balance_alerts(db)
    assert res["sent"] == 0 and outbox.kinds() == []


def test_email_carries_the_apply_link(db, monkeypatch):
    """
    ZH: 信裡一定要有「怎麼申請」——
        只說「額度快用完了」是一句沒有下一步的話。
        這個連結管理端本來就設定得了,但在 v3.8 之前哪裡都不顯示。
    """
    crud.set_system_config(db, crud.MYAI_LOW_BALANCE_KEY, "500")
    crud.set_system_config(db, "myai_apply_guide_url", "https://apply.example.com/x")
    crud.set_settings(db, {"myai_balance_alert_days": "7"})
    u = make_user(db, username="link", email="link@example.com")
    _bind(db, u, 10)

    # ZH: 這一題要看的是**信的內容**,email_log 沒有存內文 —— 所以這裡才攔截。
    #     它不碰節流,所以攔掉 send_email 不會像上面那樣把要測的東西一起換掉。
    box = []
    from app.services import email_service
    monkeypatch.setattr(email_service, "send_email",
                        lambda to, subject, html, **kw: box.append(html))

    myai_sync.notify_balance_alerts(db)
    assert len(box) == 1, "沒有寄出提醒信"
    assert "https://apply.example.com/x" in box[0]


# ══════════════════════════════════════════════════════════════════════════
# ZH: v4.0 三段式 —— 早期門檻（開始變少）
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("points,threshold,early,expected", [
    (9999,  500, 10000, "low_early"),   # ZH: 落在早期段
    (10000, 500, 10000, "ok"),          # ZH: 等於早期門檻不算（語意是「低於」）
    (499,   500, 10000, "low"),         # ZH: 低於快用完門檻 → low 優先於 low_early
    (0,     500, 10000, "empty"),
    (None,  500, 10000, "unknown"),
    (9999,  500, 0,     "ok"),          # ZH: early=0 = 關掉這段 → 回到兩段式
    (9999,  500, None,  "ok"),          # ZH: 舊呼叫端不傳 early → 行為不變
    (300,   500, 400,   "low"),         # ZH: 🔴 early ≤ low（設定交叉）→ 視同關閉
    (450,   500, 400,   "low"),
    (600,   500, 400,   "ok"),          # ZH: 交叉時不得出現永遠輪不到的 low_early
])
def test_balance_state_three_tiers(points, threshold, early, expected):
    assert crud.myai_balance_state(points, threshold, early) == expected


def test_early_reminder_sends_and_all_three_stages_are_independent(db, outbox):
    """ZH: 早期段會寄；而且 early → low → empty 三段各自獨立，一定寄得出三封。"""
    crud.set_system_config(db, crud.MYAI_LOW_BALANCE_KEY, "500")
    crud.set_system_config(db, crud.MYAI_EARLY_BALANCE_KEY, "10000")
    crud.set_settings(db, {"myai_balance_alert_days": "7"})
    u = make_user(db, username="tiers1", email="tiers1@example.com")
    row = _bind(db, u, 8000)

    assert myai_sync.notify_balance_alerts(db)["sent"] == 1
    assert outbox.kinds() == ["myai_balance:low_early"]

    row.points = 300; db.commit()
    assert myai_sync.notify_balance_alerts(db)["sent"] == 1, "掉進 low 段要能再寄"

    row.points = 0; db.commit()
    assert myai_sync.notify_balance_alerts(db)["sent"] == 1, "掉到 empty 要能再寄"
    assert outbox.kinds() == ["myai_balance:low_early", "myai_balance:low",
                              "myai_balance:empty"]


def test_early_stage_is_throttled_like_the_others(db, outbox):
    """ZH: 同一人同一段（early）在間隔內只寄一封。"""
    crud.set_system_config(db, crud.MYAI_LOW_BALANCE_KEY, "500")
    crud.set_system_config(db, crud.MYAI_EARLY_BALANCE_KEY, "10000")
    crud.set_settings(db, {"myai_balance_alert_days": "7"})
    u = make_user(db, username="tiers2", email="tiers2@example.com")
    _bind(db, u, 8000)

    assert myai_sync.notify_balance_alerts(db)["sent"] == 1
    res = myai_sync.notify_balance_alerts(db)
    assert res["sent"] == 0 and res["skipped"] == 1, "早期段也要吃節流"
