"""
ZH: 帳號刪除後、Lab 資料銷毀前的提醒信（v3.8）。

ZH: 流程本身（刪帳號 → 原地封存 → 逾期銷毀）v3.3 就已經實作而且在跑,
    這一批只加提醒。所以測試守的是**提醒本身的三個坑**:
      1. 寄在銷毀之前(反過來的話收到信時東西已經沒了)
      2. 同一筆不重複寄(每日掃描)
      3. 沒有可用地址的紀錄要跳過,不要灌爆退信紀錄
"""
from datetime import datetime, timedelta, timezone

import pytest

from app import crud, models
from app.services import lab_manager

UTC = timezone.utc


def _archive(db, name, days_left, email="grad@example.com", username="grad"):
    """ZH: 造一筆封存紀錄,距離銷毀還有 days_left 天。"""
    rec = models.ArchivedLabVolume(
        volume_name=name, user_id=None, username=username, email=email,
        size_bytes=1234, reason="admin_delete",
        archived_at=datetime.now(UTC) - timedelta(days=30 - days_left),
        expires_at=datetime.now(UTC) + timedelta(days=days_left, hours=1),
    )
    db.add(rec)
    db.commit()
    return rec


@pytest.fixture(autouse=True)
def _no_real_mail(monkeypatch):
    """ZH: 攔住寄信,只記錄。這一組不需要走到 send_email。"""
    sent = []
    # ZH: send_purge_reminders 是在函式內 `from . import email_service`,
    #     所以換掉模組上的那個屬性就攔得到（不需要動 lab_manager）。
    from app.services import email_service
    monkeypatch.setattr(email_service, "send_lab_purge_reminder",
                        lambda *a, **k: sent.append((a, k)))
    return sent


class TestWhenReminderFires:
    def test_first_reminder_inside_the_window(self, db, _no_real_mail):
        _archive(db, "home_a", days_left=29)
        assert lab_manager.send_purge_reminders(db)["first"] == 1
        assert len(_no_real_mail) == 1

    def test_final_reminder_inside_the_final_window(self, db, _no_real_mail):
        rec = _archive(db, "home_b", days_left=5)
        rec.reminded_first_at = datetime.now(UTC) - timedelta(days=20)
        db.commit()
        assert lab_manager.send_purge_reminders(db)["final"] == 1
        assert _no_real_mail[0][1]["stage"] == "final"

    def test_already_expired_is_left_to_the_purge(self, db, _no_real_mail):
        """ZH: 已經到期的不寄信 —— 那封信只會告訴人一件已經發生的事。"""
        rec = _archive(db, "home_c", days_left=1)
        rec.expires_at = datetime.now(UTC) - timedelta(hours=1)
        db.commit()
        assert lab_manager.send_purge_reminders(db) == {"first": 0, "final": 0,
                                                        "skipped_no_email": 0}
        assert _no_real_mail == []

    def test_restored_archives_are_not_reminded(self, db, _no_real_mail):
        rec = _archive(db, "home_d", days_left=3)
        rec.restored_at = datetime.now(UTC)
        db.commit()
        assert lab_manager.send_purge_reminders(db)["final"] == 0
        assert _no_real_mail == []

    def test_zero_disables_both(self, db, _no_real_mail):
        crud.set_settings(db, {"lab_purge_first_days": 0, "lab_purge_final_days": 0})
        _archive(db, "home_e", days_left=2)
        assert lab_manager.send_purge_reminders(db) == {"first": 0, "final": 0,
                                                        "skipped_no_email": 0}
        assert _no_real_mail == []


class TestNoDuplicates:
    def test_daily_scan_does_not_resend(self, db, _no_real_mail):
        """ZH: 掃描每天跑。不去重的話同一個人每天收一封,連續 23 天。"""
        _archive(db, "home_f", days_left=25)
        assert lab_manager.send_purge_reminders(db)["first"] == 1
        assert lab_manager.send_purge_reminders(db)["first"] == 0
        assert len(_no_real_mail) == 1

    def test_first_then_final_are_two_different_mails(self, db, _no_real_mail):
        """ZH: **陽性對照** —— 上面那條「第二次回 0」若是因為函式整個不動也會綠。
        這條證明時間推進之後它確實會再寄一封(而且是不同的那一封)。"""
        rec = _archive(db, "home_g", days_left=25)
        assert lab_manager.send_purge_reminders(db)["first"] == 1
        rec.expires_at = datetime.now(UTC) + timedelta(days=3)
        db.commit()
        assert lab_manager.send_purge_reminders(db)["final"] == 1
        assert [k["stage"] for _, k in _no_real_mail] == ["first", "final"]

    def test_late_start_sends_only_the_final_one(self, db, _no_real_mail):
        """
        ZH: 保留期被調短、或系統停機一陣子之後,同一筆可能同時符合兩個窗。
            這時只寄最後那封並把兩格都標掉 —— 同一天收到兩封內容雷同的信,
            使用者只會覺得系統壞了。
        """
        _archive(db, "home_h", days_left=3)
        out = lab_manager.send_purge_reminders(db)
        assert (out["first"], out["final"]) == (0, 1)
        rec = db.query(models.ArchivedLabVolume).filter_by(volume_name="home_h").first()
        assert rec.reminded_first_at is not None, "第一格沒標掉,之後會補寄一封多餘的信"
        assert rec.reminded_final_at is not None
        assert len(_no_real_mail) == 1


class TestAddressesWeCannotUse:
    @pytest.mark.parametrize("email", [None, "", "   ", "12361114@unknown"])
    def test_unusable_addresses_are_skipped(self, db, _no_real_mail, email):
        """
        ZH: 孤兒 volume 被 --adopt 收編時 username/email 都是 None;
            SSO 推不出信箱時是 `@unknown`。這兩種寄了必退。

        ZH: 實測:目前正式資料庫裡唯一那筆封存的 email 就是 None。
        """
        _archive(db, "home_i", days_left=3, email=email)
        out = lab_manager.send_purge_reminders(db)
        assert out["skipped_no_email"] == 1
        assert (out["first"], out["final"]) == (0, 0)
        assert _no_real_mail == []

    def test_skipping_does_not_mark_it_as_reminded(self, db, _no_real_mail):
        """ZH: 跳過不等於寄過 —— 之後補上地址就該寄得出去。"""
        _archive(db, "home_j", days_left=3, email=None)
        lab_manager.send_purge_reminders(db)
        rec = db.query(models.ArchivedLabVolume).filter_by(volume_name="home_j").first()
        assert rec.reminded_first_at is None and rec.reminded_final_at is None

        rec.email = "found@example.com"
        db.commit()
        assert lab_manager.send_purge_reminders(db)["final"] == 1
