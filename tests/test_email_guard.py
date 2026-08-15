"""
ZH: 保留網域寄信閘門
EN: Reserved-domain send guard

ZH: 為什麼有這個檔案：
    2026-08-15 跑測試時，conftest 沒有覆蓋 SMTP_SERVER，43 個測試登入點真的
    用**正式 SMTP** 往 xxx@example.com 寄了信，約 35 封全數退回寄件信箱。
    而且紀錄寫進測試用的記憶體 DB、隨測試結束消失，正式 email_log 查不到任何痕跡。

    conftest 已改成強制 mock（外部防線），但那道防線改壞了就破功。
    這裡釘住的是**寄信路徑內**的那道：收件網域若為 RFC 2606 / 6761 保留名稱，
    一律不寄。任何呼叫端都繞不過去。
"""
import pytest

from app.services import email_service as es


class TestReservedDomainDetection:
    @pytest.mark.parametrize("addr", [
        "test@example.com", "admin@EXAMPLE.COM",      # 大小寫不敏感
        "x@example.org", "x@example.net", "x@example.edu",
        "a@foo.test", "a@bar.invalid", "a@anything.example",
        "a@localhost", "a@x.localhost",               # TLD 本身與子網域都要擋
    ])
    def test_reserved_is_blocked(self, addr):
        assert es.is_undeliverable_by_spec(addr) is True

    @pytest.mark.parametrize("addr", [
        "12361114@me.mcu.edu.tw", "nyalazyforwork@gmail.com", "admin@school.edu.tw",
        "someone@myexample.com",     # 含 example 但不是保留網域
        "a@example.com.tw",          # 尾綴像但不是
        "a@testing.org", "a@invalidate.io",
    ])
    def test_real_domain_not_blocked(self, addr):
        assert es.is_undeliverable_by_spec(addr) is False


class TestSendEmailGuard:
    def test_send_to_reserved_domain_never_reaches_smtp(self, monkeypatch):
        """ZH: 閘門在最前面，連 SMTP 物件都不該被建立——即使 SMTP_SERVER 有設。"""
        called = []
        monkeypatch.setattr(es.smtplib, "SMTP",
                            lambda *a, **k: called.append(a) or pytest.fail("不該連 SMTP"))
        monkeypatch.setattr(es.settings, "SMTP_SERVER", "smtp.example-real.com")
        recorded = []
        monkeypatch.setattr(es, "_record", lambda *a, **k: recorded.append(a))

        es.send_email("test@example.com", "主旨", "<p>內文</p>", kind="login_alert")

        assert not called, "保留網域仍嘗試連線 SMTP"
        assert recorded and recorded[0][2] == "blocked", f"狀態應為 blocked：{recorded}"

    def test_real_domain_still_goes_through_mock_path(self, monkeypatch):
        """ZH: 一般網域不受影響——未設 SMTP_SERVER 時仍走既有的 mock 分支。"""
        monkeypatch.setattr(es.settings, "SMTP_SERVER", "")
        recorded = []
        monkeypatch.setattr(es, "_record", lambda *a, **k: recorded.append(a))

        es.send_email("real@gmail.com", "主旨", "<p>內文</p>", kind="login_alert")

        assert recorded and recorded[0][2] == "mock", f"狀態應為 mock：{recorded}"
