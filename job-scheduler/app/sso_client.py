"""
==============================================================================
SSO Client 抽象層 — 支援 Mock / CAS / OIDC 三種 provider
SSO Client Abstraction Layer — Mock / CAS / OIDC providers
==============================================================================
ZH: 三個 client 都繼承 BaseSSOClient，互不知道對方存在；
    工廠函式 get_sso_client() 依 yaml 的 provider 欄位決定載入哪個。
EN: All three clients inherit BaseSSOClient and are mutually independent;
    factory get_sso_client() loads the right one based on yaml's `provider` field.

ZH: 回傳契約 — validate_ticket() 統一回傳 dict 含 `auth_source` 欄位（v1.1 E5）
EN: Return contract — validate_ticket() always returns dict with `auth_source` (v1.1 E5)
==============================================================================
"""
import urllib.parse
import time
import hmac
import hashlib
import secrets
import base64
import logging
from abc import ABC, abstractmethod

import httpx
from jose import jwt  # v1.1 E3: requirements 是 python-jose 不是 PyJWT

logger = logging.getLogger(__name__)


# ── PENDING 值清單，用於工廠函式偵測 OIDC 是否已配置（v1.1 I7）──
PENDING_VALUES = {"PENDING", "", None}


# ==============================================================================
# 抽象介面 | Abstract Interface
# ==============================================================================
class BaseSSOClient(ABC):
    @abstractmethod
    def get_login_url(self) -> str:
        """取得 SSO 登入導向網址"""
        pass

    @abstractmethod
    def validate_ticket(self, ticket: str) -> dict:
        """
        驗證 SSO Ticket 並回傳使用者資訊。

        回傳 dict 必須含：
          - username (str)
          - email (str)
          - name (str, optional)
          - role (str, "student" / "teacher" / "admin")
          - auth_source (str, "sso_mock" / "sso_cas" / "sso_oidc")
          - external_id (str, optional) — OIDC 的 oid；CAS 留空
        """
        pass


# ==============================================================================
# MockSSOClient — 開發測試用
# ==============================================================================
class MockSSOClient(BaseSSOClient):
    def __init__(self, mock_users: list):
        self.mock_users = mock_users

    def get_login_url(self) -> str:
        return "/api/v1/sso/mock-login"

    def validate_ticket(self, ticket: str) -> dict:
        for user in self.mock_users:
            if user.get("student_id") == ticket:
                return {
                    "username":    user.get("student_id"),
                    "email":       user.get("email"),
                    "name":        user.get("name"),
                    "role":        user.get("role", "student"),
                    "auth_source": "sso_mock",       # v1.1 E5
                    "external_id": None,
                }
        raise ValueError("無效的模擬 Ticket 或找不到此使用者")


# ==============================================================================
# CASSSOClient — Yale CAS 協定（學術界 SSO 標準，目前 MCU 沒用，留著未來其他學校用）
# ==============================================================================
class CASSSOClient(BaseSSOClient):
    def __init__(self, server_url: str, service_url: str, version: str = "3.0"):
        self.server_url = server_url.rstrip("/")
        self.service_url = service_url
        self.version = version

    def get_login_url(self) -> str:
        encoded_service = urllib.parse.quote(self.service_url, safe='')
        return f"{self.server_url}/login?service={encoded_service}"

    def validate_ticket(self, ticket: str) -> dict:
        encoded_service = urllib.parse.quote(self.service_url, safe='')
        # 注意: 依照真實 CAS 伺服器設定，可能是 /serviceValidate 或 /p3/serviceValidate
        validate_url = f"{self.server_url}/p3/serviceValidate?service={encoded_service}&ticket={ticket}"

        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.get(validate_url)
                response.raise_for_status()

            if "cas:authenticationSuccess" in response.text:
                import re
                user_match = re.search(r'<cas:user>(.*?)<\/cas:user>', response.text)
                if user_match:
                    username = user_match.group(1).strip()
                    return {
                        "username":    username,
                        "email":       f"{username}@school.edu.tw",
                        "name":        username,
                        "role":        "student",
                        "auth_source": "sso_cas",     # v1.1 E5
                        "external_id": None,
                    }
            logger.error(f"CAS ticket validation failed: {response.text}")
            raise ValueError("CAS 伺服器驗證 Ticket 失敗")
        except Exception as e:
            logger.error(f"CAS SSO Error: {e}")
            raise


# ==============================================================================
# OIDCSSOClient — v2.1 新增，對接 Microsoft Entra ID（MCU 使用此種）
# ==============================================================================
class OIDCSSOClient(BaseSSOClient):
    """
    v2.1 OIDC client（手寫 httpx，不加 authlib 依賴）。

    用法：
      client = OIDCSSOClient(tenant_id=..., client_id=..., client_secret=...,
                             redirect_uri=...)
      url = client.get_login_url()        # 內部會生 state，回 authorization URL
      ok = client.verify_state(state)     # router 在 callback 先驗證
      info = client.validate_ticket(code) # 用 code 換 id_token、回 user info

    state 採 stateless HMAC 設計（不需 Redis/in-memory storage）。
    """

    def __init__(self,
                 tenant_id: str,
                 client_id: str,
                 client_secret: str,
                 redirect_uri: str,
                 scopes: list = None):
        self.tenant_id     = tenant_id
        self.client_id     = client_id
        self.client_secret = client_secret
        self.redirect_uri  = redirect_uri
        self.scopes        = scopes or ["openid", "email", "profile"]
        self.authority     = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0"

    # ── 介面契約 ────────────────────────────────────────────────────────
    def get_login_url(self) -> str:
        """組 Microsoft authorization URL（state 內部生成，無外部參數）"""
        state = self._sign_state()
        params = {
            "client_id":     self.client_id,
            "response_type": "code",
            "redirect_uri":  self.redirect_uri,
            "scope":         " ".join(self.scopes),
            "state":         state,
            "response_mode": "query",
        }
        return f"{self.authority}/authorize?{urllib.parse.urlencode(params)}"

    def validate_ticket(self, code: str) -> dict:
        """
        OIDC 的 'ticket' 是 authorization code；POST 換 id_token。

        注意：state 驗證由 router 在進入此方法前完成（呼叫 verify_state）。
        MVP 階段不驗 id_token 簽章（token 直接從 HTTPS token endpoint 拿，
        端對端加密；v2.2 將加 jwks 簽章驗證）。
        """
        try:
            token_resp = httpx.post(
                f"{self.authority}/token",
                data={
                    "client_id":     self.client_id,
                    "client_secret": self.client_secret,
                    "code":          code,
                    "redirect_uri":  self.redirect_uri,
                    "grant_type":    "authorization_code",
                },
                timeout=10.0,
            )
            token_resp.raise_for_status()
        except httpx.HTTPError as e:
            logger.error(f"OIDC token exchange failed: {e}")
            raise ValueError(f"OIDC token 交換失敗: {e}")

        id_token = token_resp.json().get("id_token")
        if not id_token:
            logger.error("OIDC response missing id_token")
            raise ValueError("OIDC response missing id_token")

        # python-jose 的乾淨 API
        claims = jwt.get_unverified_claims(id_token)

        email = claims.get("email") or claims.get("preferred_username", "")
        if not email:
            raise ValueError("OIDC id_token 沒有 email claim")

        return {
            "username":    email.split("@")[0],          # 學號
            "email":       email,
            "name":        claims.get("name", email),
            "role":        "student",                    # 預設；admin 須手動提權
            "auth_source": "sso_oidc",
            "external_id": claims.get("oid"),            # Microsoft 永久 ID
        }

    # ── stateless state 簽章（防 CSRF + replay）──────────────────────────
    def _sign_state(self) -> str:
        # 延遲 import 避免循環相依
        from .config import settings
        payload = f"{int(time.time())}|{secrets.token_urlsafe(16)}"
        sig = hmac.new(
            settings.JWT_SECRET_KEY.encode(),
            payload.encode(),
            hashlib.sha256,
        ).hexdigest()[:16]
        return base64.urlsafe_b64encode(f"{payload}|{sig}".encode()).decode()

    def verify_state(self, state: str, max_age_seconds: int = 600) -> bool:
        from .config import settings
        try:
            decoded = base64.urlsafe_b64decode(state.encode()).decode()
            ts, nonce, sig = decoded.split("|")
            expected = hmac.new(
                settings.JWT_SECRET_KEY.encode(),
                f"{ts}|{nonce}".encode(),
                hashlib.sha256,
            ).hexdigest()[:16]
            if not hmac.compare_digest(sig, expected):
                return False
            return (time.time() - int(ts)) < max_age_seconds
        except Exception:
            return False


# ==============================================================================
# 工廠函式 | Factory
# ==============================================================================
def get_sso_client(mock_mode: bool = True, config: dict = None) -> BaseSSOClient:
    """
    依設定回傳對應的 SSO 客戶端。

    決策順序（v1.1）：
      1. mock_mode=True 強制 → MockSSOClient（向後相容 v1）
      2. config["provider"] == "oidc"：檢查 client_id / client_secret 是否 PENDING
         → 是：warning 後 fallback 到 mock（v1.1 I7）
         → 否：建立 OIDCSSOClient
      3. config["provider"] == "cas"：建立 CASSSOClient
      4. default fallback → MockSSOClient
    """
    config = config or {}

    # 向後相容：mock_mode flag 仍最優先
    if mock_mode:
        mock_users = config.get("mock", {}).get("users", [])
        logger.info("使用 Mock SSO Client (mock_mode=True)")
        return MockSSOClient(mock_users)

    provider = config.get("provider", "mock")

    if provider == "oidc":
        oidc_cfg = config.get("oidc", {})
        if (oidc_cfg.get("client_id") in PENDING_VALUES or
                oidc_cfg.get("client_secret") in PENDING_VALUES):
            # v1.1 I7: PENDING 時降級成 mock，避免服務崩潰
            logger.warning(
                "provider=oidc 但 client_id/secret 是 PENDING；fallback 至 mock。"
                "請於 sso_policy.yaml 填入 IT 提供的真實值後重啟。"
            )
            mock_users = config.get("mock", {}).get("users", [])
            return MockSSOClient(mock_users)
        logger.info(f"使用 OIDC SSO Client (tenant={oidc_cfg.get('tenant_id', '?')[:8]}...)")
        return OIDCSSOClient(
            tenant_id=oidc_cfg["tenant_id"],
            client_id=oidc_cfg["client_id"],
            client_secret=oidc_cfg["client_secret"],
            redirect_uri=oidc_cfg["redirect_uri"],
            scopes=oidc_cfg.get("scopes"),
        )

    if provider == "cas":
        cas_cfg = config.get("cas", {})
        server_url = cas_cfg.get("server_url", "")
        service_url = cas_cfg.get("service_url", "")
        version = cas_cfg.get("version", "3.0")
        logger.info(f"使用 Real CAS SSO Client (Server: {server_url})")
        return CASSSOClient(server_url, service_url, version)

    # default fallback
    mock_users = config.get("mock", {}).get("users", [])
    logger.info(f"使用 Mock SSO Client (default fallback, provider={provider})")
    return MockSSOClient(mock_users)


def build_oidc_client_if_enabled(config: dict) -> "OIDCSSOClient | None":
    """
    建立獨立的 OIDC client singleton（即使主 sso_client 是 mock 也可同時建 OIDC client）。
    供 routers/sso.py 的 /oidc/login + /oidc/callback 端點使用。
    若 OIDC 設定 PENDING 則回 None（前端會根據 /providers 端點隱藏 OIDC 按鈕）。
    """
    if config.get("provider") != "oidc":
        return None
    oidc_cfg = config.get("oidc", {})
    if (oidc_cfg.get("client_id") in PENDING_VALUES or
            oidc_cfg.get("client_secret") in PENDING_VALUES):
        return None
    try:
        return OIDCSSOClient(
            tenant_id=oidc_cfg["tenant_id"],
            client_id=oidc_cfg["client_id"],
            client_secret=oidc_cfg["client_secret"],
            redirect_uri=oidc_cfg["redirect_uri"],
            scopes=oidc_cfg.get("scopes"),
        )
    except KeyError as e:
        logger.error(f"OIDC 設定缺少必要欄位 {e}；OIDC 不啟用")
        return None
