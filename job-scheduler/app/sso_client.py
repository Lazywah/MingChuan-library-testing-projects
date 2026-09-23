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
import re
import urllib.parse
import time
import hmac
import hashlib
import secrets
import base64
import logging
from abc import ABC, abstractmethod

import httpx
# ZH: v3.1 起身分改由 userinfo endpoint 取得（不從 id_token 解析身分）。
# ZH: v4.24 補上 **id_token 的簽章驗證**（jwks + nonce + sub 對帳）——
#     身分仍然來自 userinfo，這一層是縱深防禦，見 OIDCSSOClient._verify_id_token。
# EN: Identity still comes from userinfo; v4.24 adds id_token signature verification
#     (jwks + nonce + sub cross-check) as defence in depth.

logger = logging.getLogger(__name__)


# ── PENDING 值清單，用於工廠函式偵測 OIDC 是否已配置（v1.1 I7）──
PENDING_VALUES = {"PENDING", "", None}


# ==============================================================================
# 抽象介面 | Abstract Interface
# ==============================================================================
class BaseSSOClient(ABC):
    """@node job-scheduler/app/sso_client.py::BaseSSOClient"""
    @abstractmethod
    def get_login_url(self) -> str:
        """取得 SSO 登入導向網址

        @node job-scheduler/app/sso_client.py::BaseSSOClient.get_login_url
        """
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

        @node job-scheduler/app/sso_client.py::BaseSSOClient.validate_ticket
        """
        pass


# ==============================================================================
# MockSSOClient — 開發測試用
# ==============================================================================
class MockSSOClient(BaseSSOClient):
    """@node job-scheduler/app/sso_client.py::MockSSOClient"""
    def __init__(self, mock_users: list):
        """@node job-scheduler/app/sso_client.py::MockSSOClient.__init__"""
        self.mock_users = mock_users

    def get_login_url(self) -> str:
        """@node job-scheduler/app/sso_client.py::MockSSOClient.get_login_url"""
        return "/api/v1/sso/mock-login"

    def validate_ticket(self, ticket: str) -> dict:
        """@node job-scheduler/app/sso_client.py::MockSSOClient.validate_ticket"""
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
    """@node job-scheduler/app/sso_client.py::CASSSOClient"""
    def __init__(self, server_url: str, service_url: str, version: str = "3.0"):
        """@node job-scheduler/app/sso_client.py::CASSSOClient.__init__"""
        self.server_url = server_url.rstrip("/")
        self.service_url = service_url
        self.version = version

    def get_login_url(self) -> str:
        """@node job-scheduler/app/sso_client.py::CASSSOClient.get_login_url"""
        encoded_service = urllib.parse.quote(self.service_url, safe='')
        return f"{self.server_url}/login?service={encoded_service}"

    def validate_ticket(self, ticket: str) -> dict:
        """@node job-scheduler/app/sso_client.py::CASSSOClient.validate_ticket"""
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
# OIDCSSOClient — v3.1 改版：discovery 驅動，對接 MCU 自建 OIDC（auth.mcu.edu.tw）
# ==============================================================================
# ZH: v3.1 重要變更（2026-08-01，實測 AADSTS700016 後確認）：
#     MCU 的 SSO **不是** Microsoft Entra，而是自建 OIDC 伺服器 auth.mcu.edu.tw。
#     其 id_token 只有 sub/iss/auth_time/acr（無 email/學號）→ 身分必須拿
#     access_token 打 userinfo_endpoint 取得（IT 明示）。因此：
#       1. 端點改由 discovery URL（.well-known/openid-configuration）啟動時抓取
#       2. validate_ticket 改為 code → access_token → GET userinfo → 取學號
# EN: v3.1: MCU runs its OWN OIDC server (auth.mcu.edu.tw), not Microsoft Entra.
#     Its id_token carries no identity claims — identity comes from the
#     userinfo endpoint via access_token. Endpoints are discovery-driven.
# ==============================================================================
class OIDCSSOClient(BaseSSOClient):
    """
    v3.1 OIDC client（手寫 httpx，不加 authlib 依賴）。

    用法：
      client = OIDCSSOClient(discovery_url=..., client_id=..., client_secret=...,
                             redirect_uri=...)
      url = client.get_login_url()        # 內部會生 state，回 authorization URL
      ok = client.verify_state(state)     # router 在 callback 先驗證
      info = client.validate_ticket(code) # code→token→userinfo，回 user info

    state 採 stateless HMAC 設計（不需 Redis/in-memory storage）。

    @node job-scheduler/app/sso_client.py::OIDCSSOClient
    """

    # ZH: username_claim 未設定時，依序嘗試這些 userinfo 欄位當學號/員編
    # EN: candidate userinfo claims tried in order when username_claim is unset
    _USERNAME_CANDIDATES = (
        "preferred_username", "student_id", "studentId", "uid",
        "employee_id", "employeeId", "account", "username", "user_id", "sub",
    )

    def __init__(self,
                 discovery_url: str,
                 client_id: str,
                 client_secret: str,
                 redirect_uri: str,
                 scopes: list = None,
                 username_claim: str = "",
                 email_domain: str = "",
                 email_rules: list = None):
        """@node job-scheduler/app/sso_client.py::OIDCSSOClient.__init__"""
        self.discovery_url  = discovery_url
        self.client_id      = client_id
        self.client_secret  = client_secret
        self.redirect_uri   = redirect_uri
        self.scopes         = scopes or ["openid", "email", "profile"]
        self.username_claim = (username_claim or "").strip()
        # ZH: userinfo 沒給 email 時的網域 fallback（MCU 只回 sub → 學號@此網域；
        #     供 MYAI email 綁定對得上）。留空則交由上層用 @unknown。
        self.email_domain   = (email_domain or "").strip().lstrip("@")
        # ZH: v3.4 依 sub 型態選網域（學生 @me / 教職員 @mail）；見 sso_policy.yaml 說明
        self.email_rules    = email_rules or []
        self._doc: dict | None = None   # discovery 文件快取
        # ZH: v4.24 jwks 快取（kid → key）。0 代表還沒抓過。
        self._jwks_keys: dict = {}
        self._jwks_at: float = 0.0

        # ZH: 啟動先試抓 discovery；失敗不擋啟動（第一次登入時 lazy 重試）
        # EN: Try discovery at startup; failure doesn't block boot (lazy retry on first login)
        try:
            self._endpoints()
        except Exception as e:  # noqa: BLE001
            logger.warning(f"OIDC discovery 首次抓取失敗（登入時會重試）: {e}")

    # ── discovery ───────────────────────────────────────────────────────
    def _endpoints(self) -> dict:
        """抓取並快取 OpenID configuration；缺必要端點視為失敗。

        @node job-scheduler/app/sso_client.py::OIDCSSOClient._endpoints
        """
        if self._doc:
            return self._doc
        resp = httpx.get(self.discovery_url, timeout=10.0)
        resp.raise_for_status()
        doc = resp.json()
        missing = [k for k in ("authorization_endpoint", "token_endpoint", "userinfo_endpoint")
                   if not doc.get(k)]
        if missing:
            raise RuntimeError(f"OIDC discovery 缺少必要端點: {missing}")
        self._doc = doc
        logger.info(f"OIDC discovery 載入完成 (issuer={doc.get('issuer', '?')})")
        return doc

    # ── 介面契約 ────────────────────────────────────────────────────────
    def get_login_url(self) -> str:
        """組 authorization URL（state 內部生成，無外部參數）

        @node job-scheduler/app/sso_client.py::OIDCSSOClient.get_login_url
        """
        eps = self._endpoints()
        state = self._sign_state()
        params = {
            "client_id":     self.client_id,
            "response_type": "code",
            "redirect_uri":  self.redirect_uri,
            "scope":         " ".join(self.scopes),
            "state":         state,
            # ZH: v4.24 nonce 由 state 推導（見 nonce_for_state）——
            #     callback 時才有辦法在沒有 session 儲存區的情況下比對。
            "nonce":         self.nonce_for_state(state),
        }
        return f"{eps['authorization_endpoint']}?{urllib.parse.urlencode(params)}"

    # ── id_token 驗證（v4.24）──────────────────────────────────────────
    #
    # ZH: 🔴 **這一層是縱深防禦，不是身分來源。** 身分仍然來自 userinfo
    #     （直接以 TLS 連到 IdP、帶 access_token）。那條路本來就不經過瀏覽器，
    #     所以偽造的 id_token 影響不到它。這裡要擋的是另一件事：
    #       · token endpoint 回的 token 其實屬於**別人**（token substitution）
    #       · 這次的 token 是**別次登入**的重播（nonce 不對）
    #
    # ZH: 🔴 **演算法必須釘死。** auth.mcu.edu.tw 的 discovery 自己宣告
    #     `id_token_signing_alg_values_supported: ['none','HS256',…,'RS256',…]`——
    #     照單全收的話，攻擊者只要把 alg 改成 `none` 就不必簽章，
    #     或改成 HS256 拿**公鑰當 HMAC 密鑰**（公鑰是公開的）。兩種都是經典手法。
    #     所以只收 RS*，而且明確傳 algorithms，不讓函式庫自己決定。
    _ID_TOKEN_ALGS = ("RS256", "RS384", "RS512")

    # ZH: jwks 快取。IdP 換金鑰時 kid 會變 —— 遇到沒看過的 kid 才重抓，
    #     但**最短間隔 60 秒**：否則隨便一個帶假 kid 的請求就能讓我們去打 IdP。
    _JWKS_MIN_REFETCH_SECONDS = 60

    def _jwks(self, force: bool = False) -> dict:
        """ZH: 取得 jwks（kid → key dict）。有快取，force 才重抓。

        @node job-scheduler/app/sso_client.py::OIDCSSOClient._jwks
        """
        now = time.time()
        if (not force and self._jwks_keys
                and (now - self._jwks_at) < 3600):
            return self._jwks_keys
        if force and (now - self._jwks_at) < self._JWKS_MIN_REFETCH_SECONDS:
            return self._jwks_keys
        uri = self._endpoints().get("jwks_uri")
        if not uri:
            raise ValueError("OIDC discovery 沒有 jwks_uri，無法驗證 id_token 簽章")
        resp = httpx.get(uri, timeout=10.0)
        resp.raise_for_status()
        keys = {}
        for k in (resp.json().get("keys") or []):
            if k.get("kid"):
                keys[k["kid"]] = k
        if not keys:
            raise ValueError(f"jwks 沒有任何帶 kid 的金鑰（{uri}）")
        self._jwks_keys, self._jwks_at = keys, now
        logger.info("OIDC jwks 已更新（%d 把金鑰）", len(keys))
        return keys

    def _verify_id_token(self, raw: str, expected_nonce: str | None,
                         expected_sub: str | None) -> dict:
        """
        ZH: 驗 id_token 的簽章、簽發者、對象、時效、nonce 與 sub。驗不過就丟 ValueError。

        ZH: ⚠ `at_hash` 不驗 —— 那要 access_token 的雜湊，而部分 IdP 不放這個 claim；
            它保護的是「id_token 與 access_token 配對」，而我們已經用
            **sub 對帳**達成同一件事（而且更直接）。

        @node job-scheduler/app/sso_client.py::OIDCSSOClient._verify_id_token
        """
        from jose import jwt as jose_jwt, jwk as jose_jwk  # noqa: F401  (延遲 import)
        from jose.utils import base64url_decode            # noqa: F401
        from jose.exceptions import JWTError

        try:
            header = jose_jwt.get_unverified_header(raw)
        except Exception as e:
            raise ValueError(f"id_token 格式不對：{e}")

        alg = (header.get("alg") or "").upper()
        if alg not in self._ID_TOKEN_ALGS:
            # ZH: 這是**攻擊的樣子**，不是設定問題 —— 用 error 記，而且要看得到 alg。
            logger.error("id_token 的 alg=%s 不在允許清單 %s", alg, self._ID_TOKEN_ALGS)
            raise ValueError(f"id_token 使用了不被接受的簽章演算法：{alg or 'none'}")

        kid = header.get("kid")
        keys = self._jwks()
        key = keys.get(kid)
        if key is None:
            # ZH: 沒看過的 kid = IdP 可能換了金鑰。重抓一次再說（有最短間隔保護）。
            keys = self._jwks(force=True)
            key = keys.get(kid)
        if key is None:
            raise ValueError(f"jwks 裡找不到 id_token 的 kid={kid}")

        eps = self._endpoints()
        try:
            claims = jose_jwt.decode(
                raw, key,
                algorithms=list(self._ID_TOKEN_ALGS),
                audience=self.client_id,
                issuer=eps.get("issuer") or None,
                # ZH: leeway 60 秒 —— 兩邊的時鐘不會完全一致，而差幾秒就把人擋在
                #     門外的話，症狀是「有時候登得進去有時候不行」，最難查。
                options={"verify_at_hash": False, "leeway": 60},
            )
        except JWTError as e:
            raise ValueError(f"id_token 驗證失敗：{e}")

        # ZH: 🔴 nonce 綁定「這次的登入請求」。沒有它的話，攻擊者可以把
        #     另一次（合法的）登入結果重播進來。
        if expected_nonce:
            got = str(claims.get("nonce") or "")
            if not hmac.compare_digest(got, expected_nonce):
                raise ValueError("id_token 的 nonce 與本次登入請求不符")

        # ZH: 🔴 sub 對帳：id_token 說的人，必須就是 userinfo 回的那個人。
        #     不一致＝拿到的是**別人的** token，這是最該擋下來的情況。
        if expected_sub:
            if str(claims.get("sub") or "") != str(expected_sub):
                logger.error("id_token.sub 與 userinfo.sub 不一致 —— 拒絕登入")
                raise ValueError("id_token 與 userinfo 指向不同的使用者")
        return claims

    def validate_ticket(self, code: str, state: str | None = None,
                        verify_id_token: bool = True) -> dict:
        """
        OIDC 的 'ticket' 是 authorization code。流程（v3.1）：
          1. POST token endpoint（client_secret_post）→ access_token
          2. GET userinfo endpoint（Bearer access_token）→ 學號/員編等身分欄位
        state 驗證由 router 在進入此方法前完成（verify_state）。

        ZH: v4.24 多了第 3 步：**驗 id_token**（簽章 / iss / aud / exp / nonce / sub）。
            身分仍然來自 userinfo —— 這一層是縱深防禦，見 _verify_id_token。

        ZH: `state` 給了才驗得了 nonce（nonce 由 state 推導）。
            不給仍然會驗簽章與 sub —— 少驗一項比整個不驗好。

        ZH: 🔴 **沒有 id_token 時不擋。** 身分本來就不從它來，而且
            「IdP 這次沒給」與「有人偽造」是兩件事。記一行 warning，繼續。
            ⚠ 反過來，**有 id_token 但驗不過就一定要擋** —— 那才是異常。

        ZH: `verify_id_token=False` 是給管理端的閘門用的（system setting
            `sso_verify_id_token`）。IdP 改東西而我們還沒跟上時，
            要有辦法在不改程式的情況下讓學生登得進來。

        @node job-scheduler/app/sso_client.py::OIDCSSOClient.validate_ticket
        """
        eps = self._endpoints()
        try:
            token_resp = httpx.post(
                eps["token_endpoint"],
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

        token_json = token_resp.json()
        access_token = token_json.get("access_token")
        if not access_token:
            logger.error("OIDC token response missing access_token")
            raise ValueError("OIDC response missing access_token")
        raw_id_token = token_json.get("id_token")

        try:
            ui_resp = httpx.get(
                eps["userinfo_endpoint"],
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=10.0,
            )
            ui_resp.raise_for_status()
        except httpx.HTTPError as e:
            logger.error(f"OIDC userinfo failed: {e}")
            raise ValueError(f"OIDC userinfo 取得失敗: {e}")

        info = ui_resp.json()
        # ZH: 2026-08-01 實測確認 MCU userinfo 僅回 {'sub': '<學號>'}；username_claim 已
        #     釘死為 sub（sso_policy.yaml）。完整 payload 降為 debug（內含個資）。
        # EN: Verified: MCU userinfo returns only {'sub': '<student-id>'}; claim pinned.
        logger.debug(f"OIDC userinfo keys={sorted(info.keys())} payload={info}")

        # ZH: v4.24 驗 id_token（見 _verify_id_token 的檔頭說明）。
        if verify_id_token:
            if not raw_id_token:
                # ZH: 身分不從 id_token 來，所以這不是致命的 —— 但要看得見，
                #     因為一個 OIDC 伺服器不回 id_token 本身就不尋常。
                logger.warning("OIDC token 回應沒有 id_token —— 略過簽章驗證（身分仍由 userinfo 決定）")
            else:
                self._verify_id_token(
                    raw_id_token,
                    expected_nonce=(self.nonce_for_state(state) if state else None),
                    expected_sub=info.get("sub"))
                logger.info("id_token 簽章與 sub 對帳通過")

        username = self._extract_username(info)
        # ZH: v3.4 email 推導 —— IdP 有給就用（最可信）；否則依 email_rules 依 sub 型態
        #     選網域。**推不出來就留空**，交由上層判定「無法確信」而跳過建號。
        email, email_source = self._derive_email(username, info.get("email"))

        return {
            "username":    username,                     # 學號/員編
            "email":       email,                        # 可能為空；上層有 fallback
            "name":        info.get("name") or username,
            "role":        "student",                    # 預設；admin 須手動提權
            "auth_source": "sso_oidc",
            "external_id": str(info.get("sub") or "") or None,   # IdP 永久 ID
            # ZH: idp=IdP 直接提供(最可信) / rule:<label>=依規則推導 / fallback=舊單一網域
            #     / none=推不出來。供 MYAI 自動開通判斷要不要建帳號。
            "email_source": email_source,
        }

    def _derive_email(self, username: str, idp_email: str | None) -> tuple[str, str]:
        """
        ZH: 產生這個人的信箱。MCU 的 userinfo 只回 sub，不自己建構就完全沒有地址可用。
            優先序：IdP 給的 email > email_rules 依 sub 選網域 > email_domain > 無。

            ⚠ 界線（別混淆）：這裡是用 IdP 的 **sub（不可變的學號/員編）建構**地址，
              不是拿平台上「使用者可自由更改的名稱」做判定。分類請一律用
              myai_sync.classify_email()（只看網域）。
              建構出來的地址不代表信箱存在 —— 存不存在由實際寄送的退件紀錄回答。
        EN: Build the address from the IdP's immutable `sub` (userinfo returns only sub).
            This is construction, not judgement; classification keys off the DOMAIN only
            (myai_sync.classify_email). Existence is answered by real bounces, not guesses.

        @node job-scheduler/app/sso_client.py::OIDCSSOClient._derive_email
        """
        idp_email = (idp_email or "").strip()
        if idp_email:
            return idp_email, "idp"
        local = (username or "").strip()
        if not local:
            return "", "none"
        for rule in self.email_rules:
            try:
                pat = rule.get("pattern") or ""
                dom = (rule.get("domain") or "").strip().lstrip("@")
                if pat and dom and re.match(pat, local):
                    return f"{local}@{dom}", f"rule:{rule.get('label') or dom}"
            except re.error as e:
                logger.warning("email_rules 的 pattern 無效（略過該條）: %s", e)
        if self.email_domain:
            # ZH: 舊的單一網域設定；規則都沒中時才用，可信度較低
            return f"{local}@{self.email_domain}", "fallback"
        return "", "none"

    def _extract_username(self, info: dict) -> str:
        """
        ZH: 從 userinfo 取學號/員編。username_claim 有設就用它（找不到即報錯，避免悄悄用錯欄位）；
            未設則依候選清單嘗試。值若為 email 形式取 @ 前半段。
        EN: Extract the account id from userinfo. Explicit username_claim wins (hard
            error if absent); otherwise try candidates. Emails are trimmed at '@'.

        @node job-scheduler/app/sso_client.py::OIDCSSOClient._extract_username
        """
        if self.username_claim:
            val = info.get(self.username_claim)
            if not val:
                raise ValueError(
                    f"OIDC userinfo 缺少設定的 username_claim '{self.username_claim}'"
                    f"（實際欄位: {sorted(info.keys())}）")
        else:
            val = next((info[k] for k in self._USERNAME_CANDIDATES if info.get(k)), None)
            if not val:
                raise ValueError(f"OIDC userinfo 找不到可用的帳號欄位（實際欄位: {sorted(info.keys())}）")
        val = str(val).strip()
        return val.split("@")[0] if "@" in val else val

    # ── stateless state 簽章（防 CSRF + replay）──────────────────────────
    def _sign_state(self) -> str:
        # 延遲 import 避免循環相依
        """@node job-scheduler/app/sso_client.py::OIDCSSOClient._sign_state"""
        from .config import settings
        payload = f"{int(time.time())}|{secrets.token_urlsafe(16)}"
        sig = hmac.new(
            settings.JWT_SECRET_KEY.encode(),
            payload.encode(),
            hashlib.sha256,
        ).hexdigest()[:16]
        return base64.urlsafe_b64encode(f"{payload}|{sig}".encode()).decode()

    def nonce_for_state(self, state: str) -> str:
        """
        ZH: 這個 state 對應的 OIDC nonce。

        ZH: 🔴 **由 state 推導而不是另外存一份** —— 平台沒有 session 儲存區，
            state 本來就是 stateless HMAC。nonce = HMAC(密鑰, state 裡的亂數)，
            所以登入時與 callback 時算得出同一個值，而攻擊者算不出來
            （他沒有 JWT_SECRET_KEY）。

        ZH: ⚠ 直接把 state 當 nonce 是不行的：state 會出現在**瀏覽器網址列與
            Referer**，等於把 nonce 一起洩漏出去。推導一層之後，
            看得到 state 的人仍然算不出 nonce。

        ZH: 算不出來（state 壞掉）就回空字串 —— 呼叫端會當成「這次不驗 nonce」，
            而 state 本身已經先被 verify_state 擋掉了。

        @node job-scheduler/app/sso_client.py::OIDCSSOClient.nonce_for_state
        """
        from .config import settings
        try:
            decoded = base64.urlsafe_b64decode(state.encode()).decode()
            ts, rand, _sig = decoded.split("|")
        except Exception:
            return ""
        return hmac.new(settings.JWT_SECRET_KEY.encode(),
                        f"oidc-nonce|{ts}|{rand}".encode(),
                        hashlib.sha256).hexdigest()[:32]

    def verify_state(self, state: str, max_age_seconds: int = 600) -> bool:
        """@node job-scheduler/app/sso_client.py::OIDCSSOClient.verify_state"""
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

    @node job-scheduler/app/sso_client.py::get_sso_client
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
            # v3.1: 提級為 error — OIDC 已正式上線，憑證遺失/漂移屬於重大異常，
            #       須立刻被看見（/callback 已加閘，此 fallback 不會變成登入後門）
            logger.error(
                "provider=oidc 但 client_id/secret 是 PENDING；fallback 至 mock（SSO 實質停用）。"
                "OIDC 已上線環境出現此訊息＝.env 憑證遺失或未載入，請立即檢查！"
            )
            mock_users = config.get("mock", {}).get("users", [])
            return MockSSOClient(mock_users)
        logger.info(f"使用 OIDC SSO Client (discovery={oidc_cfg.get('discovery_url', '?')})")
        return OIDCSSOClient(
            discovery_url=oidc_cfg["discovery_url"],
            client_id=oidc_cfg["client_id"],
            client_secret=oidc_cfg["client_secret"],
            redirect_uri=oidc_cfg["redirect_uri"],
            scopes=oidc_cfg.get("scopes"),
            username_claim=oidc_cfg.get("username_claim", ""),
            email_domain=oidc_cfg.get("email_domain", ""),
            email_rules=oidc_cfg.get("email_rules") or [],
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

    @node job-scheduler/app/sso_client.py::build_oidc_client_if_enabled
    """
    if config.get("provider") != "oidc":
        return None
    oidc_cfg = config.get("oidc", {})
    if (oidc_cfg.get("client_id") in PENDING_VALUES or
            oidc_cfg.get("client_secret") in PENDING_VALUES):
        return None
    try:
        return OIDCSSOClient(
            discovery_url=oidc_cfg["discovery_url"],
            client_id=oidc_cfg["client_id"],
            client_secret=oidc_cfg["client_secret"],
            redirect_uri=oidc_cfg["redirect_uri"],
            scopes=oidc_cfg.get("scopes"),
            username_claim=oidc_cfg.get("username_claim", ""),
            email_domain=oidc_cfg.get("email_domain", ""),
            email_rules=oidc_cfg.get("email_rules") or [],
        )
    except KeyError as e:
        logger.error(f"OIDC 設定缺少必要欄位 {e}；OIDC 不啟用")
        return None
