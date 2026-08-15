"""
ZH: 測試環境的外部服務隔離
EN: External-service isolation in the test environment

ZH: 為什麼有這個檔案：
    `config.py` 會讀 repo 根目錄的 `.env`，那是**正式環境設定**。
    conftest 負責把外部服務全部中和掉，但那是「外部防線」——被改壞了不會有人發現，
    直到又真的打到廠商 API 或寄出真信為止。實際發生過兩次：

      · SMTP  → 2026-08-15 用正式 SMTP 寄出約 35 封必退信件
      · MYAI  → 跑測試時真的 GET myai168.com/.../export_user_list 並回 200，
                把廠商的 7 筆使用者資料同步進測試 DB

    這個檔案讓那道防線自己有測試。斷言的是**行為前提**（憑證為空、主機不可路由），
    不是實作細節。
"""
import pytest

from app.config import settings
from app.services.bounce_reader import imap_config


class TestNoProductionCredentials:
    """ZH: 測試沒有任何理由持有正式服務的登入資訊。"""

    @pytest.mark.parametrize("name", [
        "SMTP_USERNAME", "SMTP_PASSWORD",
        "MYAI_ADMIN_EMAIL", "MYAI_ADMIN_PASSWORD",
        "IMAP_USERNAME", "IMAP_PASSWORD",
    ])
    def test_credential_is_empty(self, name):
        # ZH: 刻意先轉成 bool 再斷言 —— 直接 assert 值的話，失敗時 pytest 會把
        #     **正式密碼原文印進主控台與 CI log**。這裡只讓它印長度。
        value = getattr(settings, name, "") or ""
        has_value = bool(value)
        assert not has_value, (
            f"{name} 在測試環境有值（長度 {len(value)}）—— conftest 的隔離被破壞了。"
            f"這代表測試可能會用正式憑證連上外部服務。"
        )


class TestNoOutboundHosts:
    def test_smtp_disabled(self):
        """ZH: 空的 SMTP_SERVER → send_email 走 mock 分支，不實際寄出。"""
        assert settings.SMTP_SERVER == ""

    def test_imap_host_unresolvable(self):
        """ZH: bounce_reader 由 SMTP 主機推導 IMAP 主機；兩邊都空 → 不會連線。"""
        assert imap_config()["host"] == ""

    @pytest.mark.parametrize("name", ["OLLAMA_BASE_URL", "MYAI_BASE_URL"])
    def test_base_url_points_at_localhost(self, name):
        """ZH: 指向本機關閉埠 —— 連線立即被拒，不做 DNS 查詢（DNS 逾時很慢）。"""
        url = getattr(settings, name, "")
        assert "127.0.0.1" in url or "localhost" in url, f"{name}={url} 指向外部主機"

    def test_portkey_disabled(self):
        assert settings.PORTKEY_ENABLED is False


class TestSchedulerLoopsOff:
    """ZH: 排程的自動同步要關掉，否則 lifespan 一起來就開始打廠商 API。"""

    def test_myai_auto_sync_off(self):
        assert settings.MYAI_SYNC_INTERVAL_HOURS == 0

    def test_myai_balance_poll_off(self):
        assert settings.MYAI_BALANCE_POLL_MINUTES == 0


class TestNotProductionDatabase:
    def test_database_is_not_production(self):
        """ZH: 正式 DB 是 /data/ai_platform.db（compose 把 ./data 掛上去）。"""
        assert "/data/ai_platform.db" not in settings.DATABASE_PATH.replace("\\", "/"), (
            "測試指向正式資料庫 —— 測試會污染真實資料"
        )
