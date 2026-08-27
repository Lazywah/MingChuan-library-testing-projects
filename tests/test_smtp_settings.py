"""
ZH: SMTP 連線設定改為管理端可設（v3.8）。

ZH: 這支測試守三件事，優先順序就是這個順序：
      1. **密碼絕不從資料庫讀** —— 擁有者裁定，也是全站「密鑰只從 .env 讀」的一環
      2. **測試不會真的寄信** —— 這裡出過事（2026-08-15 約 35 封、08-21 又 9 封）
      3. 覆寫要一路生效到退信回收，不能只有寄信端跟著改
"""
import pytest

from app import crud
from app.config import settings
from app.services import email_service, bounce_reader


class TestEffectiveSmtp:
    def test_falls_back_to_env_when_no_override(self, db):
        cfg = crud.effective_smtp(db)
        assert cfg["server"] == settings.SMTP_SERVER
        assert cfg["port"] == settings.SMTP_PORT
        assert cfg["from_email"] == settings.SMTP_FROM_EMAIL

    def test_override_wins(self, db):
        crud.set_settings(db, {"smtp_server": "smtp.example-relay.net",
                               "smtp_port": 2525,
                               "smtp_from_email": "no-reply@ai.mcu.edu.tw"})
        cfg = crud.effective_smtp(db)
        assert cfg["server"] == "smtp.example-relay.net"
        assert cfg["port"] == 2525
        assert cfg["from_email"] == "no-reply@ai.mcu.edu.tw"

    def test_password_is_never_read_from_the_database(self, db):
        """
        ZH: 陽性對照 —— 直接在 system_config 裡種一列 `smtp_password`，
            證明 effective_smtp **不會**去撿它。

        ZH: 只斷言「回傳值等於 .env」是不夠的：.env 的密碼在測試裡是空字串，
            所以就算實作真的去讀了 DB、只要 DB 也是空的，測試一樣會綠。
            種一個**不同的值**才分得出「沒讀」與「讀了但剛好一樣」。
        """
        crud.set_system_config(db, "smtp_password", "PLANTED-SHOULD-NOT-BE-USED")
        cfg = crud.effective_smtp(db)
        assert cfg["password"] == settings.SMTP_PASSWORD
        assert cfg["password"] != "PLANTED-SHOULD-NOT-BE-USED"
        assert "smtp_password" not in crud.SYSTEM_SETTINGS


class TestTextSettingValidation:
    def test_host_rejects_a_url(self, db):
        with pytest.raises(ValueError):
            crud.set_settings(db, {"smtp_server": "https://smtp.gmail.com"})

    def test_host_rejects_whitespace(self, db):
        with pytest.raises(ValueError):
            crud.set_settings(db, {"smtp_server": "smtp gmail com"})

    def test_from_email_rejects_a_non_address(self, db):
        with pytest.raises(ValueError):
            crud.set_settings(db, {"smtp_from_email": "不是信箱"})

    def test_too_long_is_rejected(self, db):
        with pytest.raises(ValueError):
            crud.set_settings(db, {"smtp_server": "a" * 300})

    def test_valid_values_are_stored_trimmed(self, db):
        crud.set_settings(db, {"smtp_server": "  smtp.mcu.edu.tw  "})
        assert crud.effective_smtp(db)["server"] == "smtp.mcu.edu.tw"

    def test_every_text_setting_declares_its_validation(self):
        """ZH: 漏宣告的話會靜默不驗。這條與 crud 匯入時的自檢是同一個判準。"""
        bad = [k for k, v in crud.SYSTEM_SETTINGS.items()
               if v.get("type") == "text"
               and (v.get("maxlen") is None
                    or v.get("text_kind") not in {"any", "host", "email"})]
        assert bad == []


class TestStillCannotSendDuringTests:
    def test_empty_config_goes_to_mock_not_to_a_real_relay(self, db, monkeypatch):
        """
        ZH: 🔴 這條是防漏寄的那道外部防線的迴歸測試。

        ZH: v3.8 之前判斷式是 `if not settings.SMTP_SERVER`，而 conftest
            把那個環境變數設成空字串 —— 防線就掛在那一句上。
            改成讀資料庫之後，如果哪天有人讓它「DB 沒值就去猜一個預設主機」，
            測試就會開始對外寄信，而且**測試全綠**。

        ZH: 作法：把 smtplib.SMTP 換成一個「被呼叫就炸」的假物件。
            沒有走 mock 分支的話，這個測試會失敗而不是寄出一封信。
        """
        def _boom(*a, **k):
            raise AssertionError("測試竟然嘗試連線真的 SMTP 伺服器")
        monkeypatch.setattr(email_service.smtplib, "SMTP", _boom)

        assert crud.effective_smtp(db)["server"] == "", "測試環境的 SMTP 主機不是空的"
        email_service.send_email("someone@mcu.edu.tw", "主旨", "<p>內文</p>")
        # ZH: 沒有拋 AssertionError 就代表沒有嘗試連線。

    def test_positive_control_a_configured_host_does_reach_the_connect_step(self, db, monkeypatch):
        """
        ZH: **陽性對照。** 上面那條測試「沒有拋錯就算過」——
            如果哪天 monkeypatch 打錯對象、或 send_email 提早 return，
            它會**永遠綠**而守不住任何東西（「檢查到 0 份」和「沒有問題」長得一樣）。

        ZH: 這條故意把主機設起來，證明同一個假物件**確實攔得到連線嘗試**。
            兩條一起看才有意義：這條紅了代表尺壞了，不是功能壞了。
        """
        calls = []
        def _spy(*a, **k):
            calls.append(a)
            raise RuntimeError("stop here")     # ZH: 不要真的連出去
        monkeypatch.setattr(email_service.smtplib, "SMTP", _spy)
        monkeypatch.setattr(email_service, "_smtp", lambda: {
            "server": "smtp.mcu.edu.tw", "port": 587, "username": "",
            "from_email": "no-reply@ai.mcu.edu.tw", "password": ""})

        email_service.send_email("someone@mcu.edu.tw", "主旨", "<p>內文</p>")
        assert calls, "設了主機卻沒有走到連線 —— 上面那條測試守不住任何東西"
        assert calls[0][:2] == ("smtp.mcu.edu.tw", 587)

    def test_reserved_domain_is_blocked_before_anything_else(self, db, monkeypatch):
        """ZH: 路徑內那道防線（RFC 2606/6761）不受這次改動影響。"""
        def _boom(*a, **k):
            raise AssertionError("保留網域竟然走到連線階段")
        monkeypatch.setattr(email_service.smtplib, "SMTP", _boom)
        email_service.send_email("nobody@example.com", "主旨", "<p>內文</p>")


class TestBounceReaderFollowsTheOverride:
    def test_imap_host_is_derived_from_the_overridden_smtp_host(self, db):
        """
        ZH: 換了 SMTP 主機而退信回收沒跟著換的話，症狀是
            「信照寄、退信全部收不到」而且沒有任何錯誤 —— 這正是要擋的。
        """
        crud.set_settings(db, {"smtp_server": "smtp.mcu.edu.tw"})
        assert bounce_reader.imap_config(db)["host"] == "imap.mcu.edu.tw"

    def test_from_email_is_carried_into_the_parser(self, db):
        """ZH: 判斷「哪封退信是我們寄的」要用同一個寄件地址,否則會對到錯的人。"""
        crud.set_settings(db, {"smtp_from_email": "no-reply@ai.mcu.edu.tw"})
        assert bounce_reader.imap_config(db)["from_email"] == "no-reply@ai.mcu.edu.tw"

    def test_without_db_it_still_falls_back_to_env(self):
        """ZH: db=None 的行為要與 v3.7 相同,不能因為新參數而變。"""
        assert bounce_reader.imap_config()["user"] == (settings.SMTP_USERNAME or "").strip()
