"""
==============================================================================
Module 1: 統一設定管理 (Configuration Management)
==============================================================================
ZH: 用途：集中管理所有環境變數與應用設定，避免 os.environ 散落各處
EN: Purpose: Centralize all env vars and app settings, avoid scattered os.environ

ZH: 流程：
    1. 應用啟動時，Pydantic Settings 自動從 .env 或環境變數讀取設定
    2. 各模組透過 from app.config import settings 引用
    3. 型別錯誤或缺少必填值時，啟動即報錯
EN: Flow:
    1. On startup, Pydantic Settings auto-reads from .env or env vars
    2. Other modules import via: from app.config import settings
    3. Type errors or missing required values cause immediate startup failure

ZH: 模組化設計：
    - 此模組是所有其他模組的基礎依賴
    - 修改設定只需改 .env 檔案，無需改動程式碼
    - 新增設定項只需在 Settings class 中加一行
EN: Modular design:
    - This module is the foundational dependency for all others
    - Changing settings only requires editing .env, no code changes
    - Adding new settings only requires one line in Settings class
==============================================================================
"""

from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """
    ZH: 應用程式設定類別 - 所有設定項的唯一來源
    EN: Application settings class - single source of truth for all settings
    """

    # ------------------------------------------------------------------
    # ZH: JWT 認證設定 | EN: JWT Authentication
    # ------------------------------------------------------------------
    JWT_SECRET_KEY: str = "dev-jwt-secret-key-change-in-production"  # ZH: JWT 簽名金鑰 | EN: JWT signing key
    JWT_ALGORITHM: str = "HS256"  # ZH: JWT 演算法 | EN: JWT algorithm
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 120  # ZH: Token 過期時間 (分鐘) | EN: Token expiry (minutes)

    # ------------------------------------------------------------------
    # ZH: 資料庫設定 | EN: Database
    # ------------------------------------------------------------------
    DATABASE_PATH: str = "/data/ai_platform.db"  # ZH: SQLite 檔案路徑 | EN: SQLite file path

    # ------------------------------------------------------------------
    # ZH: Token 額度設定 | EN: Token Quota
    # ------------------------------------------------------------------
    DEFAULT_MONTHLY_TOKEN_LIMIT: int = 5_000_000  # ZH: 每月上限 (預設 5M) | EN: Monthly limit
    TOKEN_RESET_DAY: int = 1  # ZH: 每月重置日 (1-28) | EN: Monthly reset day

    # ------------------------------------------------------------------
    # ZH: GPU 伺服器設定 | EN: GPU Server
    # ------------------------------------------------------------------
    GPU_MOCK_MODE: bool = True  # ZH: Mock 模式開關 | EN: Mock mode toggle
    GPU_SERVER_1_HOST: str = "192.168.1.100"  # ZH: GPU 伺服器 1 IP | EN: GPU server 1 IP
    GPU_SERVER_2_HOST: str = "192.168.1.101"  # ZH: GPU 伺服器 2 IP | EN: GPU server 2 IP
    GPU_SERVER_USERNAME: str = "gpu_admin"  # ZH: SSH 使用者名稱 | EN: SSH username
    SSH_KEY_PATH: str = "/root/.ssh/id_rsa"  # ZH: SSH 私鑰路徑 | EN: SSH private key path

    # ------------------------------------------------------------------
    # ZH: 排程器設定 | EN: Scheduler
    # ------------------------------------------------------------------
    MAX_CONCURRENT_JOBS: int = 4  # ZH: 最大同時任務數 | EN: Max concurrent jobs
    JOB_CHECK_INTERVAL: int = 10  # ZH: 佇列檢查間隔 (秒) | EN: Queue check interval (sec)

    # ------------------------------------------------------------------
    # ZH: 日誌設定 | EN: Logging
    # ------------------------------------------------------------------
    LOG_LEVEL: str = "INFO"  # ZH: 日誌等級 | EN: Log level

    class Config:
        """
        ZH: Pydantic Settings 設定 | EN: Pydantic Settings configuration
        """
        env_file = ".env"  # ZH: 自動讀取 .env 檔案 | EN: Auto-read .env file
        case_sensitive = True  # ZH: 環境變數區分大小寫 | EN: Case-sensitive env vars


# ==============================================================================
# ZH: 全域設定實例 - 其他模組透過此物件存取設定
# EN: Global settings instance - other modules access settings via this object
# ZH: 用法：from app.config import settings
# EN: Usage: from app.config import settings
# ==============================================================================
settings = Settings()
