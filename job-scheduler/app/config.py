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
import logging
import yaml
from pydantic_settings import BaseSettings
from pydantic import field_validator

logger = logging.getLogger(__name__)

# ZH: C3 修復：弱秘鑰黑名單，啟動時若 .env 仍用這些值會 fail-fast
# EN: C3 fix: weak-secret blacklist — fail-fast on container start
_INSECURE_SECRETS = {
    "default-insecure-secret-key",
    "dev-jwt-secret-key-change-in-production",
    "mcu-secret-token-change-in-production",
    "changeme",
    "secret",
    "",
}

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
    logger.warning("Failed to load scheduler_policy.yaml: %s", e)

# 讀取 SSO 政策
SSO_POLICY_PATH = os.path.join(os.path.dirname(__file__), "sso_policy.yaml")
try:
    with open(SSO_POLICY_PATH, "r", encoding="utf-8") as f:
        SSO_POLICY = yaml.safe_load(f)
except Exception as e:
    SSO_POLICY = {"mock_mode": True, "mock": {"users": []}, "cas": {}}
    logger.warning("Failed to load sso_policy.yaml: %s", e)

class Settings(BaseSettings):
    """
    ZH: 應用程式基礎設定類別 (僅保留與密碼、路徑相關)
    EN: Application base settings class (paths and secrets only)
    """

    # ------------------------------------------------------------------
    # ZH: JWT 認證設定 | EN: JWT Authentication
    # ------------------------------------------------------------------
    # ZH: 預設值刻意設為被黑名單拒絕的字串，強制透過 .env 注入
    # EN: Default deliberately set to a blacklisted value to force .env injection
    JWT_SECRET_KEY: str = "dev-jwt-secret-key-change-in-production"  # rejected by validator
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 120

    # ------------------------------------------------------------------
    # ZH: Worker 節點靜態 Token (與 gpu-worker/docker-compose.yml 的 API_TOKEN 一致)
    # EN: Worker node static token (must match API_TOKEN in gpu-worker/docker-compose.yml)
    # ------------------------------------------------------------------
    WORKER_API_TOKEN: str = "mcu-secret-token-change-in-production"

    # ------------------------------------------------------------------
    # ZH: v2.0 Secrets 加密主金鑰 (KEK) — 用 AES-256-GCM 加密使用者 secrets
    # EN: v2.0 Secrets master key (KEK) — AES-256-GCM encrypts user secrets
    # ------------------------------------------------------------------
    SECRETS_MASTER_KEY: str = "dev-secrets-master-key-change-in-production"

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
    # ZH: Portkey LLM Gateway | EN: Portkey LLM Gateway
    # ------------------------------------------------------------------
    # ZH: Portkey OSS gateway 實際監聽 8787（PORT env 無效）；Ollama 需經 custom-host 指向
    # EN: Portkey OSS gateway actually listens on 8787 (PORT env ignored); Ollama needs custom-host
    PORTKEY_URL: str = "http://ai-platform-portkey:8787/v1/chat/completions"
    PORTKEY_ENABLED: bool = True
    # ZH: 本機 Ollama 位址（Portkey OSS 為 header 路由，ollama 須明確告知 host）
    # EN: Local Ollama base URL (OSS Portkey is header-routed; ollama needs explicit host)
    OLLAMA_BASE_URL: str = "http://ai-platform-ollama:11434"

    # ------------------------------------------------------------------
    # ZH: 任務超時設定 (分鐘) | EN: Job timeout (minutes)
    # ------------------------------------------------------------------
    JOB_TIMEOUT_MINUTES: int = 120

    # ------------------------------------------------------------------
    # ZH: 日誌設定 | EN: Logging
    # ------------------------------------------------------------------
    LOG_LEVEL: str = "INFO"

    # ------------------------------------------------------------------
    # ZH: SMTP 郵件設定 | EN: SMTP Email Configuration
    # ------------------------------------------------------------------
    SMTP_SERVER: str = ""
    SMTP_PORT: int = 587
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM_EMAIL: str = "noreply@ai-platform.local"

    model_config = {
        "env_file": ".env",
        "case_sensitive": True,
        "extra": "ignore",
    }

    # ZH: C3 修復：啟動時驗證 secrets 強度，拒絕弱值與預設值
    # EN: C3 fix: validate secret strength at startup; reject weak/default values
    @field_validator("JWT_SECRET_KEY")
    @classmethod
    def _validate_jwt_secret(cls, v: str) -> str:
        if v in _INSECURE_SECRETS:
            raise ValueError(
                "JWT_SECRET_KEY uses an insecure default value. "
                "Set a strong random string (≥32 chars) in .env."
            )
        if len(v) < 32:
            raise ValueError(
                f"JWT_SECRET_KEY too short ({len(v)} chars). Minimum 32 chars required."
            )
        return v

    @field_validator("WORKER_API_TOKEN")
    @classmethod
    def _validate_worker_token(cls, v: str) -> str:
        if v in _INSECURE_SECRETS:
            raise ValueError(
                "WORKER_API_TOKEN uses an insecure default value. "
                "Set a strong random string in .env (must match gpu-worker API_TOKEN)."
            )
        if len(v) < 16:
            raise ValueError(
                f"WORKER_API_TOKEN too short ({len(v)} chars). Minimum 16 chars required."
            )
        return v

    @field_validator("SECRETS_MASTER_KEY")
    @classmethod
    def _validate_secrets_master_key(cls, v: str) -> str:
        """
        ZH: v2.0 Secrets KEK — 必須足夠強，加密所有使用者 API keys
        EN: v2.0 Secrets KEK — must be strong; encrypts all user API keys
        """
        if v in _INSECURE_SECRETS or v == "dev-secrets-master-key-change-in-production":
            raise ValueError(
                "SECRETS_MASTER_KEY uses an insecure default value. "
                "Set a strong random string (≥32 chars) in .env. "
                "WARNING: changing this key after secrets exist will invalidate all stored secrets."
            )
        if len(v) < 32:
            raise ValueError(
                f"SECRETS_MASTER_KEY too short ({len(v)} chars). Minimum 32 chars required."
            )
        return v


settings = Settings()


# ==============================================================================
# v2.1 SSO OIDC 啟用旗標 | v2.1 SSO OIDC enable flag
# ==============================================================================
# ZH: 啟動時偵測 sso_policy.yaml 內 OIDC 設定是否完整（client_id / client_secret 不是 PENDING）
# EN: At startup, detect whether OIDC config in sso_policy.yaml is complete
#     (client_id / client_secret not PENDING)
#
# ZH: OIDC_ENABLED=True 時，/api/v1/sso/providers 端點才會回傳 "oidc"
#     前端依此決定是否顯示「使用學校帳號登入」按鈕
# EN: When OIDC_ENABLED=True, /api/v1/sso/providers includes "oidc";
#     frontend uses this to decide whether to show the school-login button
#
# ZH: 失敗保險 — IT 還沒給 client_id 時，OIDC_ENABLED=False，前端顯示
#     fallback 提示「系統登入功能尚在設定中」，本機 admin 登入照常運作。
# ==============================================================================
_PENDING_VALUES = {"PENDING", "", None}

_oidc_cfg = SSO_POLICY.get("oidc", {}) if isinstance(SSO_POLICY, dict) else {}
OIDC_ENABLED = (
    SSO_POLICY.get("provider") == "oidc"
    and _oidc_cfg.get("client_id") not in _PENDING_VALUES
    and _oidc_cfg.get("client_secret") not in _PENDING_VALUES
    and bool(_oidc_cfg.get("tenant_id"))
    and bool(_oidc_cfg.get("redirect_uri"))
)

if SSO_POLICY.get("provider") == "oidc" and not OIDC_ENABLED:
    logger.warning(
        "OIDC provider selected but config is incomplete "
        "(client_id/secret still PENDING or required fields missing). "
        "OIDC login disabled; the system will fallback to mock for /sso/login. "
        "Update sso_policy.yaml with IT-provided credentials and restart to enable."
    )
elif OIDC_ENABLED:
    _redirect = _oidc_cfg.get("redirect_uri", "?")
    logger.info(f"OIDC enabled (redirect_uri={_redirect})")
