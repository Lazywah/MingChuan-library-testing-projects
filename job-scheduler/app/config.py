"""
==============================================================================
Module 1: 統一設定管理 (Configuration Management)
==============================================================================
ZH: 用途：集中管理所有環境變數與應用設定，動態載入 YAML 政策檔
EN: Purpose: Centralize env vars and load YAML policy dynamically

ZH: 流程：
    1. 應用啟動時，Pydantic Settings 自動讀取基礎庫環境變數
    2. 同步載入 scheduler_policy.yaml 取得最新之叢集佈署參數
    3. 各模組透過 from app.config import settings, SCHEDULER_POLICY 引用
EN: Flow:
    1. Auto-read base env vars 
    2. Sync load scheduler_policy.yaml for cluster nodes
    3. Modules import via: from app.config import settings, SCHEDULER_POLICY
==============================================================================
"""

import os
import yaml
from pydantic_settings import BaseSettings

# ==============================================================================
# ZH: 讀取排程政策與資源層硬體 YAML
# EN: Read scheduling policy & Resource Layer hardware YAML
# ==============================================================================
POLICY_PATH = os.path.join(os.path.dirname(__file__), "scheduler_policy.yaml")
try:
    with open(POLICY_PATH, "r", encoding="utf-8") as f:
        SCHEDULER_POLICY = yaml.safe_load(f)
except Exception as e:
    # ZH: 若無檔案則給予預設空值防崩潰
    # EN: Default empty object on failure to prevent crash
    SCHEDULER_POLICY = {"scheduling": {}, "mock_mode": True, "nodes": []}
    print(f"[Warning] Failed to load scheduler_policy.yaml: {e}")

class Settings(BaseSettings):
    """
    ZH: 應用程式基礎設定類別 (僅保留與密碼、路徑相關)
    EN: Application base settings class (paths and secrets only)
    """

    # ------------------------------------------------------------------
    # ZH: JWT 認證設定 | EN: JWT Authentication
    # ------------------------------------------------------------------
    JWT_SECRET_KEY: str = "dev-jwt-secret-key-change-in-production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 120

    # ------------------------------------------------------------------
    # ZH: 資料庫設定 | EN: Database
    # ------------------------------------------------------------------
    DATABASE_PATH: str = "/data/ai_platform.db"

    # ------------------------------------------------------------------
    # ZH: Token 額度設定 | EN: Token Quota
    # ------------------------------------------------------------------
    DEFAULT_MONTHLY_TOKEN_LIMIT: int = 5_000_000
    TOKEN_RESET_DAY: int = 1

    # ------------------------------------------------------------------
    # ZH: 日誌設定 | EN: Logging
    # ------------------------------------------------------------------
    LOG_LEVEL: str = "INFO"

    class Config:
        env_file = ".env"
        case_sensitive = True

settings = Settings()
