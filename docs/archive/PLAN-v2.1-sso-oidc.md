# Plan: Microsoft Entra ID OIDC SSO 整合

> **版本**：v1.2（2026-05-22 — User UI 純淨入口 + Mock SSO 不曝光）
> **變更歷史**：v1 → v1.1（10 個審查發現修正）→ v1.2（admin 入口完全分離、移除折疊區）
> **目標**：在不破壞現有 mock / CAS 路徑的前提下，新增 Microsoft Entra ID OIDC client，讓 MCU 學生 / 老師 / 管理員能用學校 Microsoft 帳號登入
> **交付方式**：先寫架構（不需 IT 資料）→ 拿到 client_id / client_secret 後填值即可上線

## v1.2 修正摘要（2026-05-22 使用者要求調整）

**設計變更**：
- **I12: User UI 不曝光 admin 入口** — 學生 / 老師看不到管理頁面存在
- **I13: Mock SSO 不曝光於任何 UI** — admin 不應以別人帳號登入（mock 本質就是 impersonation）

**實質改動**：
- 移除 v1.1 Section 6 的折疊區 `<details class="admin-login-toggle">`
- User UI（port 80）登入頁**只有一個按鈕**：「使用學校帳號登入」
- Admin 走獨立的 admin UI（port 8888）做 username+password 登入（不在 user UI 顯露）
- Mock SSO 不在任何前端按鈕；僅在 dev 環境用 `provider: mock` + 直接打 URL `/api/v1/sso/login` 使用

---

## v1.1 修正摘要（審查 v1 發現的問題）

**A. Plan 範例 code 寫錯（4 個，本版已修）**
- E1: `get_login_url()` 不能加 `state` 參數（破壞 BaseSSOClient 契約）→ state 邏輯內收進 OIDCSSOClient
- E3: requirements 用 python-jose 不是 PyJWT → 改 `from jose import jwt`
- E6: `urlencode` 沒 import → 改用 `urllib.parse.urlencode`
- I11: 寫「三階段」但實際 4 階段 → 統一為「四階段」

**B. Plan 設計細節遺漏（6 個，本版已補）**
- E2: `OIDCSSOClient.__init__` 改用細項參數（對齊既有 CASSSOClient 風格）
- E4: 加上 `routers/sso.py` 呼叫 site 修改到檔案清單
- E5: 各 SSO client 的 `validate_ticket()` 回傳 dict 統一含 `auth_source`
- I7: 工廠函式偵測 PENDING → fallback 到 Mock 並 warning
- ~~I9~~: v1.2 已捨棄此設計（admin 折疊區整個移除，見 v1.2 變更）
- I10: v2.1 logout 行為 = 只清本機 localStorage（不主動登出 Microsoft，SLO 留 v2.2）

**C. 加固建議（6 個，移到「未來考慮」當 v2.2）**
- I8 / S12 / S13 / S14 / S15 / S16 — 詳見文末「未來考慮」

---

## Context

### 為什麼做這個

目前 `sso_client.py` 支援 CAS（Yale 開發的學術界 SSO 協定）+ MockSSOClient。但實測 MCU 後發現：

- **MCU 沒有 CAS server**（嘗試 `sso.mcu.edu.tw` 得 ECONNREFUSED）
- **MCU 是 Microsoft 365 Managed Tenant**：
  - Tenant ID: `30f2f0eb-3fc8-4a5a-94b5-fffa8944532e`
  - issuer: `https://sts.windows.net/30f2f0eb-3fc8-4a5a-94b5-fffa8944532e/`
  - OIDC discovery 完整可用
  - `NameSpaceType: Managed`、`IsFederatedNS: false`（密碼直接在 Entra ID）

所以要接 MCU SSO，**必須走 OIDC**（Microsoft 不對外開放 CAS）。

### 為什麼不直接替換 CAS client

- 現有 mock SSO 機制是開發測試的基石（學生 T1090001 等帳號）→ 必須保留
- 未來其他學校可能用 CAS（學術界主流）→ 程式碼留著
- 「新增 provider」比「替換 provider」風險低 50%

### 使用者決策（已確認）

| 議題 | 選擇 |
|------|------|
| Callback 路徑 | 獨立 `/api/v1/sso/oidc/callback`（與 CAS 完全分離） |
| User.auth_source 欄位 | **現在加**（local / sso_cas / sso_oidc / sso_mock），順便分流密碼變更 |
| OIDC client 實作 | 手寫 httpx（不加 authlib 依賴；100 行內搞定） |
| 前端 SSO 按鈕 | 「使用學校帳號登入」（學生 / 老師 走 OIDC）|
| **Admin 登入** | **完全分離的 admin UI（port 8888）**：admin 走本機 username+password，user UI 不曝光此入口（v1.2 修正：避免學生發現管理頁面存在） |
| **Mock SSO 顯示** | **完全不曝光於任何 UI**（v1.2 修正：admin 不應以別人帳號登入；mock 僅供 dev 環境直接打 URL 用） |
| **密碼變更 UX** | OIDC 使用者：設定頁顯示「為何不能改密碼」說明 + Microsoft 連結（**業界標準做法**，Slack / Notion / Figma 都這樣）；admin 本機帳號：照常可改 |
| 訪客登入 | 暫不考慮（後期實作機率低） |

### 5 個常見問題的標準答案（已釐清）

**Q1: Microsoft 端的隱私邊界**
- 學校 Microsoft Entra 內含學生 / 老師基本資料（學號、姓名、email、密碼 hash、MFA 設定、群組）— 但這是學校 IT 管的，與本平台無關
- 我們透過 OIDC 只拿 `openid email profile` 三個 scope 對應的欄位（email、name、oid），**拿不到密碼、群組、其他活動**

**Q2: Mock / CAS / OIDC 三者關係**
- 三者都繼承 `BaseSSOClient` 抽象介面，**互不知道對方存在**
- `sso_policy.yaml` 的 `provider` 欄位決定載入哪個 client
- 切換 provider 不需要動程式碼，只需要改 yaml + restart

**Q4: Admin 登入安全策略**
- Admin 必須走「本機 username+password」(`auth_source="local"`)
- 理由：學校 SSO 故障時 admin 仍可進去救火（**Emergency Access Account** 模式，Microsoft 自己也是這樣設計）
- 學生 / 老師走 OIDC (`auth_source="sso_oidc"`)
- 學生**無法**透過 SSO 升級成 admin — callback 永遠寫入 `role="student"`，admin 必須由現有 admin 手動提權

**Q5: 為什麼密碼不能在本系統改**
- SSO 的本質：**密碼存 Microsoft，我們的 app 從未拿到密碼**
- 連 hash 都沒有 → 沒辦法在系統內改
- 4 種替代方案評估：
  - ✅ A. 顯示說明 + Microsoft 連結（推薦，業界標準）
  - ❌ B. 內嵌 iframe Microsoft 頁（CSP 禁止）
  - ⚠️ C. 用 Microsoft Graph API 代理（需要超高權限，學校 IT 99% 不會給）
  - ⚠️ D. 雙密碼模式（違反 SSO 設計初衷，安全攻擊面變大）

---

## 架構總覽

```
┌────────────────────────────────────────────────────────────────────┐
│  使用者瀏覽器                                                       │
└────────────┬───────────────────────────────────────────────────────┘
             │
             │ ① 點「使用學校帳號登入」按鈕
             ▼
┌────────────────────────────────────────────────────────────────────┐
│  GET /api/v1/sso/oidc/login                                        │
│  → 產生 state (HMAC 簽章)、組 authorization URL                    │
│  → 302 RedirectResponse                                            │
└────────────┬───────────────────────────────────────────────────────┘
             │
             │ ② 302 到 Microsoft
             ▼
┌────────────────────────────────────────────────────────────────────┐
│  Microsoft Entra ID                                                │
│  login.microsoftonline.com/{tenant_id}/oauth2/v2.0/authorize       │
│  使用者輸入 學號@mcu.edu.tw + 密碼 + 過 MFA                          │
└────────────┬───────────────────────────────────────────────────────┘
             │
             │ ③ 302 帶 ?code=xxx&state=yyy 回來
             ▼
┌────────────────────────────────────────────────────────────────────┐
│  GET /api/v1/sso/oidc/callback?code=...&state=...                  │
│  ↓ 驗證 state (防 CSRF)                                            │
│  ↓ POST code 到 token endpoint                                     │
│  ↓ 拿到 id_token (JWT)                                             │
│  ↓ 解 JWT 取 email / name / oid                                    │
│  ↓ get_or_create_sso_user(auth_source="sso_oidc")                  │
│  ↓ 簽發本機 JWT                                                    │
│  → 302 /?sso_token=...                                             │
└────────────┬───────────────────────────────────────────────────────┘
             │
             │ ④ 前端解 URL 參數，存 localStorage
             ▼
        使用者登入完成
```

---

## 失敗保險（FailSafe）— 程式碼可先寫、不影響運行

OIDC 設定缺失時的降級策略：

```python
# config.py 啟動時偵測
PENDING_VALUES = {"PENDING", "", None}
OIDC_ENABLED = (
    SSO_POLICY.get("oidc", {}).get("client_id") not in PENDING_VALUES
    and SSO_POLICY.get("oidc", {}).get("client_secret") not in PENDING_VALUES
)
if not OIDC_ENABLED:
    logger.warning("OIDC client_id/secret not configured — OIDC login disabled")
```

效果：
- ✅ `sso_policy.yaml` 內 `client_id: "PENDING"` 時，服務照常啟動，只是 OIDC 不啟用
- ✅ 前端會去抓 `/api/v1/sso/providers` 來決定要不要顯示「使用學校帳號登入」按鈕
- ✅ 本機登入 / mock SSO 永遠不受影響

---

## 元件詳細設計

### 1. 後端 OIDC client（重點，v1.1 修正）

**檔案**：`job-scheduler/app/sso_client.py`（修改）

新增 `OIDCSSOClient(BaseSSOClient)`，**保持 `get_login_url()` 無參數的既有契約**，state 邏輯內收進 client 用 stateless HMAC（不需外部 storage）：

```python
import urllib.parse
import time, hmac, hashlib, secrets, base64
import httpx
from jose import jwt           # ← v1.1 E3 修正：requirements 是 python-jose
from .config import settings


class OIDCSSOClient(BaseSSOClient):
    # ── v1.1 E2 修正：與既有 CASSSOClient 風格一致，用細項參數 ──
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

    # ── v1.1 E1 修正：與 BaseSSOClient 契約一致（無參數），state 內部生成 ──
    def get_login_url(self) -> str:
        state = self._sign_state()
        params = {
            "client_id":     self.client_id,
            "response_type": "code",
            "redirect_uri":  self.redirect_uri,
            "scope":         " ".join(self.scopes),
            "state":         state,
            "response_mode": "query",
        }
        # v1.1 E6 修正：用 urllib.parse.urlencode（既有 import 已 ready）
        return f"{self.authority}/authorize?{urllib.parse.urlencode(params)}"

    def validate_ticket(self, code: str) -> dict:
        """OIDC 的 'ticket' 是 authorization code；POST 換 id_token

        注意：state 驗證由 router 在進入此方法前完成。
        """
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
        id_token = token_resp.json()["id_token"]
        # v1.1 E3 修正：python-jose 乾淨 API（不需 options dict）
        # MVP 階段不驗簽（token 直接從 HTTPS token endpoint 拿，已端對端加密）
        # v2.2 加 jwks 簽章驗證（見「未來考慮」）
        claims = jwt.get_unverified_claims(id_token)
        return {
            "username":    claims["email"].split("@")[0],   # 學號
            "email":       claims["email"],
            "name":        claims.get("name", claims["email"]),
            "external_id": claims["oid"],                   # Microsoft 永久 ID
            "role":        "student",                       # 預設；admin 須手動提權
            "auth_source": "sso_oidc",                      # ← v1.1 E5 修正：統一回傳 auth_source
        }

    # ── stateless state 簽章 ──
    def _sign_state(self) -> str:
        payload = f"{int(time.time())}|{secrets.token_urlsafe(16)}"
        sig = hmac.new(
            settings.JWT_SECRET_KEY.encode(),
            payload.encode(), hashlib.sha256
        ).hexdigest()[:16]
        return base64.urlsafe_b64encode(f"{payload}|{sig}".encode()).decode()

    def verify_state(self, state: str, max_age_seconds: int = 600) -> bool:
        try:
            decoded = base64.urlsafe_b64decode(state.encode()).decode()
            ts, nonce, sig = decoded.split("|")
            expected = hmac.new(
                settings.JWT_SECRET_KEY.encode(),
                f"{ts}|{nonce}".encode(), hashlib.sha256
            ).hexdigest()[:16]
            if not hmac.compare_digest(sig, expected):
                return False
            return (time.time() - int(ts)) < max_age_seconds
        except Exception:
            return False
```

**為什麼這樣設計**：
- 重用 `BaseSSOClient` 契約 → router 不必為 OIDC 寫特殊分支
- 用 httpx（既有依賴）→ 不加新套件
- state 用 stateless HMAC → 不需 in-memory storage、不需 Redis
- 不驗 id_token 簽章（MVP 取捨）→ v2.2 加 jwks 驗證

**v1.1 E5：MockSSOClient 與 CASSSOClient 也要回傳 `auth_source`**

各 client 的 `validate_ticket()` 統一在回傳 dict 加 `auth_source` 欄位：

```python
# MockSSOClient.validate_ticket() 回傳 dict 加：
"auth_source": "sso_mock"

# CASSSOClient.validate_ticket() 回傳 dict 加：
"auth_source": "sso_cas"

# OIDCSSOClient.validate_ticket() 已內含：
"auth_source": "sso_oidc"
```

Router 從此可統一 `create_sso_user(auth_source=user_info["auth_source"])`，不必為各 provider 特判。

### 2. SSO router 擴充（v1.1 修正）

**檔案**：`job-scheduler/app/routers/sso.py`（修改）

新增 4 個端點：

| 方法 | 路徑 | 說明 |
|------|------|------|
| GET  | `/api/v1/sso/oidc/login` | 呼叫 `oidc_client.get_login_url()` → 302 to Microsoft |
| GET  | `/api/v1/sso/oidc/callback` | 取 `code` + `state` → `verify_state` → `validate_ticket(code)` → 建本機 user → 簽 JWT → 302 回前端 |
| GET  | `/api/v1/sso/providers` | 回 `{"providers": ["mock"]}` 或 `["mock", "oidc"]`，前端決定顯示哪些按鈕 |
| GET  | `/api/v1/sso/password-change-info` | 回「該帳號改密碼怎麼做」（OIDC → Microsoft 連結；local → null） |

**Router callback 邏輯（v1.1 簡化版）**：

```python
@router.get("/oidc/callback")
def oidc_callback(code: str, state: str, db: Session = Depends(get_db)):
    # v1.1 E1：state 驗證委派給 OIDC client
    if not oidc_client.verify_state(state):
        raise HTTPException(400, "Invalid or expired state")

    user_info = oidc_client.validate_ticket(code)

    # 識別優先序：external_id (oid) → email → username
    user = (
        crud.get_user_by_external_id(db, user_info["external_id"])
        or crud.get_user_by_email(db, user_info["email"])
        or crud.get_user_by_username(db, user_info["username"])
    )

    if user is None:
        user = crud.create_sso_user(
            db,
            username=user_info["username"],
            email=user_info["email"],
            role=user_info["role"],
            auth_source=user_info["auth_source"],   # v1.1 E5：統一從 user_info 拿
            external_id=user_info["external_id"],
        )
    elif user.auth_source == "local":
        # 既有 local 帳號首次走 OIDC → 升級為 sso_oidc 並記 audit
        crud.upgrade_to_sso(db, user, user_info["auth_source"], user_info["external_id"])

    access_token = create_access_token(data={"sub": user.username, "role": user.role})
    return RedirectResponse(url=f"/?sso_token={access_token}")
```

### 2.5 工廠函式擴充（v1.1 E4 + I7 修正）

**檔案**：`job-scheduler/app/sso_client.py`（修改 `get_sso_client()`）

**重要修正**：
- 保留既有 `mock_mode` 參數位置（向後相容，不破壞現有 `routers/sso.py` 呼叫）
- 加 PENDING 偵測，自動 fallback 到 mock，避免 yaml 與實際狀態不一致

```python
PENDING_VALUES = {"PENDING", "", None}


def get_sso_client(mock_mode: bool = True, config: dict = None) -> BaseSSOClient:
    """
    決策順序（v1.1）：
      1. mock_mode=True 強制 → MockSSOClient（向後相容）
      2. config["provider"] == "oidc"：檢查 client_id 是否 PENDING
         → 是：warning 後 fallback 到 mock
         → 否：建立 OIDCSSOClient
      3. config["provider"] == "cas"：建立 CASSSOClient
      4. default fallback → MockSSOClient
    """
    config = config or {}

    # 向後相容：mock_mode flag 仍最優先
    if mock_mode:
        mock_users = config.get("mock", {}).get("users", [])
        return MockSSOClient(mock_users)

    provider = config.get("provider", "mock")

    if provider == "oidc":
        oidc_cfg = config.get("oidc", {})
        if (oidc_cfg.get("client_id") in PENDING_VALUES or
            oidc_cfg.get("client_secret") in PENDING_VALUES):
            # v1.1 I7：PENDING 時降級 mock，服務不會崩
            logger.warning(
                "provider=oidc but client_id/secret is PENDING; falling back to mock"
            )
            mock_users = config.get("mock", {}).get("users", [])
            return MockSSOClient(mock_users)
        return OIDCSSOClient(
            tenant_id=oidc_cfg["tenant_id"],
            client_id=oidc_cfg["client_id"],
            client_secret=oidc_cfg["client_secret"],
            redirect_uri=oidc_cfg["redirect_uri"],
            scopes=oidc_cfg.get("scopes"),
        )

    if provider == "cas":
        cas_cfg = config.get("cas", {})
        return CASSSOClient(
            server_url=cas_cfg.get("server_url", ""),
            service_url=cas_cfg.get("service_url", ""),
            version=cas_cfg.get("version", "3.0"),
        )

    # default
    mock_users = config.get("mock", {}).get("users", [])
    return MockSSOClient(mock_users)
```

**v1.1 E4：既有 `routers/sso.py` 第 15 行的呼叫不用改**（保留 `mock_mode` 參數位置）：
```python
# 不動
sso_client = get_sso_client(mock_mode=mock_mode, config=SSO_POLICY)

# 但新增一個 OIDC 專用的 singleton（router 內 OIDC callback 用）
oidc_client = None
if SSO_POLICY.get("provider") == "oidc" and OIDC_ENABLED:
    oidc_cfg = SSO_POLICY["oidc"]
    oidc_client = OIDCSSOClient(
        tenant_id=oidc_cfg["tenant_id"],
        client_id=oidc_cfg["client_id"],
        client_secret=oidc_cfg["client_secret"],
        redirect_uri=oidc_cfg["redirect_uri"],
        scopes=oidc_cfg.get("scopes"),
    )
```

兩個 client 並存：`sso_client`（既有 /login 用）+ `oidc_client`（新 /oidc/login 用）。

### 3. sso_policy.yaml 結構擴充

**檔案**：`job-scheduler/app/sso_policy.yaml`（修改）

```yaml
# v2.1: provider 取代舊 mock_mode（向後相容：mock_mode=true 等同 provider=mock）
mock_mode: false        # 保留以向後相容
provider: oidc          # mock | cas | oidc（決定 /sso/login 行為）

mock:                   # 保留供開發使用
  users:
    - student_id: "T1090001"
      password: "T1090001"
      name: "林小明"
      email: "T1090001@school.edu.tw"
      role: "student"

cas:                    # 保留供未來其他學校
  server_url: ""
  service_url: ""

# v2.1 新增 OIDC 區塊
oidc:
  tenant_id: "30f2f0eb-3fc8-4a5a-94b5-fffa8944532e"  # MCU Microsoft Entra
  client_id: "PENDING"          # ⏳ 等 IT 給
  client_secret: "PENDING"      # ⏳ 等 IT 給
  redirect_uri: "http://localhost:8002/api/v1/sso/oidc/callback"  # IT 註冊時需登記
  scopes: ["openid", "email", "profile"]
  password_change_url: "https://account.activedirectory.windowsazure.com/ChangePassword.aspx"
```

### 4. User model 擴充

**檔案**：`job-scheduler/app/models.py`（修改）

```python
class User(Base):
    ...
    # v2.1 SSO 整合
    auth_source = Column(String, default="local", nullable=False)
    # 可能值: "local" | "sso_mock" | "sso_cas" | "sso_oidc"
    external_id = Column(String, nullable=True, index=True)
    # OIDC 的 oid（Microsoft 永久 ID）；CAS 沒有則為 NULL
```

**檔案**：`job-scheduler/app/database.py`（init_db ALTER 補欄位）

```python
try: conn.execute(text("ALTER TABLE users ADD COLUMN auth_source VARCHAR DEFAULT 'local'"))
except Exception: pass
try: conn.execute(text("ALTER TABLE users ADD COLUMN external_id VARCHAR"))
except Exception: pass
```

### 5. CRUD 擴充

**檔案**：`job-scheduler/app/crud.py`（修改）

- `create_sso_user()` 新增 `auth_source` 與 `external_id` 參數
- 新增 `get_user_by_external_id()`（OIDC 主要用 oid 識別）
- 修改 `update_user()`：若 `auth_source != "local"` 且 `update_data.password` 非空 → 拒絕

```python
def update_user(db, db_user, update_data):
    if update_data.password is not None and update_data.password.strip():
        if db_user.auth_source != "local":
            raise ValueError(
                f"SSO users (auth_source={db_user.auth_source}) cannot change "
                f"password locally. Use the IdP's password change page."
            )
        db_user.hashed_password = get_password_hash(update_data.password)
    ...
```

### 6. 前端登入頁設計（v1.2 — User UI 純淨入口）

**檔案**：`web-ui/index.html`（修改登入頁面）

> **v1.2 I12 + I13 修正**：
> - 移除 v1.1 的 `<details class="admin-login-toggle">` 折疊區（學生不應看到 admin 入口）
> - User UI 只剩 SSO 按鈕一個入口
> - Admin 走獨立的 admin UI（port 8888）— 與 user UI 完全分離
> - Mock SSO 不在任何前端按鈕

**user UI 登入頁 HTML**（精簡到只剩主入口）：

```html
<div class="login-form">

  <!-- ── 唯一入口：學校帳號 (OIDC) ── -->
  <div id="sso-section" style="display:none;">
    <button id="sso-oidc-btn" class="sso-btn primary">
      <ion-icon name="school-outline"></ion-icon>
      <span data-i18n="sso_school_login">使用學校帳號登入</span>
    </button>
    <p class="sso-hint" data-i18n="sso_hint">
      請使用學校 Microsoft 帳號（學號@mcu.edu.tw）
    </p>
  </div>

  <!-- ── OIDC 尚未配置時的 fallback 提示（v1.2 加） ── -->
  <div id="sso-pending" style="display:none;">
    <p class="sso-pending-msg" data-i18n="sso_pending_msg">
      ⏳ 系統登入功能尚在設定中，請稍後再試。
    </p>
    <p class="sso-pending-hint" data-i18n="sso_pending_hint">
      若您是管理員，請透過管理介面登入。
    </p>
  </div>

  <!-- 既有的 username/password form：v1.2 完全移除 -->
  <!-- Admin 改走 admin-ui (port 8888) 的獨立登入頁 -->
</div>
```

**為什麼這設計**：
- ✅ 學生 / 老師看到極簡入口，**完全不知道有 admin 頁面**
- ✅ Admin 從 port 8888 進入（學生不會自然發現此 port）
- ✅ Mock SSO 不曝光，admin 不能誤用 mock 帳號（也不會被學生看到 mock 選項）
- ✅ OIDC PENDING 時顯示 fallback 提示，引導 admin 走 port 8888

**Admin UI 不動**：
- `admin-ui/index.html` 既有登入頁繼續用 username + password
- 此頁面不會從 user UI 連結過去
- 學生若想找 admin 入口需要知道 `:8888` port（足以擋一般使用者）

**檔案**：`web-ui/app.js`（修改）

```javascript
// 載入時處理 sso_token URL 參數
const ssoToken = new URLSearchParams(window.location.search).get('sso_token');
if (ssoToken) {
    localStorage.setItem('ai_hud_token', ssoToken);
    window.history.replaceState({}, document.title, '/');
    authToken = ssoToken;
}

// v1.2：依 providers 決定顯示主入口或 fallback 提示
fetch('/api/v1/sso/providers').then(r => r.json()).then(({providers}) => {
    if (providers.includes('oidc')) {
        document.getElementById('sso-section').style.display = 'block';
    } else {
        // 沒 OIDC 就是 PENDING 或 dev 環境，顯示 fallback 提示
        document.getElementById('sso-pending').style.display = 'block';
    }
});

// 點 OIDC 按鈕
document.getElementById('sso-oidc-btn').addEventListener('click', () => {
    window.location.href = '/api/v1/sso/oidc/login';
});

// v1.2：移除既有 admin form 相關 JS（#username #password #login-btn 不在 user UI 內）
// 既有 POST /api/v1/auth/login 邏輯搬到 admin-ui/admin.js（已經在那邊了，本來就是）
```

### 6.5 開發者測試流程（v1.2 新增）

由於 Mock SSO 不在 UI 曝光，dev 環境測試方式：

**情境 1：開發者想用 mock 帳號（T1090001）進 user UI**
1. yaml 設 `mock_mode: true` 或 `provider: mock`
2. 直接打開瀏覽器到 `http://localhost/api/v1/sso/login`
3. 看到 mock 登入 HTML 表單 → 選一個學生 → 進 user UI

**情境 2：開發者本人是 MCU 員工，想以自己學校帳號測試 OIDC**
1. yaml 設 `provider: oidc` 並填入真實 client_id/secret
2. 從 `/login` 點「使用學校帳號登入」走正常 OIDC 流程

**情境 3：Admin 想看 user UI 是什麼樣（不需要 student 視角）**
1. Admin 從 port 8888 登入 admin UI
2. 在 admin UI 內提供「快速跳轉 user UI」連結 → 用 admin 自己的 JWT 進 user UI
3. 看到 user UI 的版面、佈局（但顯示的是 admin 自己的任務資料）

**情境 4：Admin 需要看「特定學生」視角排查問題**
- v2.1 不支援（impersonation 是另一個 plan）
- 暫時做法：請該學生本人提供截圖

### 7. 設定頁面密碼變更分流

**檔案**：`web-ui/index.html` + `app.js`

設定頁面的「變更密碼」區塊根據 `auth_source` 顯示不同 UI：

**情境 A：OIDC 使用者（學生 / 老師）**
```html
<div class="change-password-section sso-mode">
  <h4>變更密碼</h4>
  <div class="sso-password-notice">
    <ion-icon name="information-circle-outline"></ion-icon>
    <p>您使用學校 Microsoft 帳號登入，密碼由學校統一管理。</p>
  </div>
  <a href="https://account.activedirectory.windowsazure.com/ChangePassword.aspx"
     target="_blank" class="ms-password-link">
    🔗 開啟 Microsoft 密碼變更頁（新分頁）
  </a>
  <details class="why-explanation">
    <summary>為什麼不能在這裡改？</summary>
    <p>
      學校採用單一登入（SSO）機制，您的密碼存在學校的 Microsoft 系統，
      本平台從未拿到您的密碼。這是業界標準的安全設計（Slack / Notion / Figma 等
      使用 SSO 的服務都是如此）。
    </p>
    <p>
      如果您忘記密碼，請至 <a href="https://passwordreset.microsoftonline.com/"
      target="_blank">Microsoft 密碼重設頁</a>。
    </p>
  </details>
</div>
```

**情境 B：本機帳號（admin）**
```html
<!-- 完全沿用既有 UI -->
<form id="profile-update-form">
  <input type="password" id="old-password" placeholder="目前密碼">
  <input type="password" id="new-password" placeholder="新密碼">
  <button>變更密碼</button>
</form>
```

**JS 切換邏輯**：
```javascript
if (currentUser.auth_source === 'sso_oidc') {
    document.getElementById('password-local-form').style.display = 'none';
    document.getElementById('password-sso-notice').style.display = 'block';
} else {
    document.getElementById('password-local-form').style.display = 'block';
    document.getElementById('password-sso-notice').style.display = 'none';
}
```

---

### 8. Logout 行為（v1.1 I10 修正）

**決策**：v2.1 範圍內 logout 只清本機 token，**不主動登出 Microsoft session**。

**理由**：
- 業界主流（Slack / Notion / Figma 都如此）
- 主動登出 Microsoft 會影響使用者在其他分頁開的 Microsoft 服務（Outlook、Teams 等），UX 惡劣
- SLO（Single Logout）留 v2.2 處理（見「未來考慮」）

**前端實作**：
```javascript
// web-ui/app.js — 登出按鈕 handler
function logout() {
    localStorage.removeItem('ai_hud_token');
    localStorage.removeItem('ai_hud_sessions');
    sessionStorage.clear();
    window.location.href = '/login';   // 跳回登入頁
}
```

**OIDC 使用者體驗**：
- 點本平台「登出」→ 立即清本機 token → 跳回登入頁
- 若 Microsoft session 仍有效（cookie 仍在）→ 再次點「使用學校帳號登入」會「秒進」（無需再輸入密碼，但 callback 仍會重新跑 → 重發本機 JWT）
- 若 Microsoft session 已過期 → 跳到 Microsoft 登入頁正常認證

這是符合期待的行為（單一平台登出不影響整個 IdP session）。

---

## 需修改 / 新增的檔案清單

### 修改
- `job-scheduler/app/sso_client.py` — 加 `OIDCSSOClient` + 修 `get_sso_client()` 工廠
- `job-scheduler/app/sso_policy.yaml` — 加 `oidc:` 區塊 + `provider:` 欄位
- `job-scheduler/app/routers/sso.py` — 加 4 個新端點（含 state 簽章邏輯）
- `job-scheduler/app/models.py` — User 加 `auth_source` + `external_id` 欄位
- `job-scheduler/app/database.py` — init_db ALTER 補欄位
- `job-scheduler/app/crud.py` — `create_sso_user` 加參數、`update_user` 加 SSO 拒絕邏輯、新增 `get_user_by_external_id`
- `job-scheduler/app/schemas.py` — `UserResponse` 加 `auth_source`（給前端判斷）
- `job-scheduler/app/config.py` — 新增 `OIDC_ENABLED` flag（依 `client_id != "PENDING"` 判斷）
- `web-ui/index.html` — 登入頁加 SSO 按鈕、設定頁密碼區塊條件渲染
- `web-ui/app.js` — fetch providers、sso_token 解析、密碼變更分流、i18n

### 新增
- `docs/dev/IT-OIDC-申請信範本.md` — 給使用者直接複製寄給 MCU IT

### 不動
- 既有 mock / CAS 程式碼路徑
- 既有本機 `/api/v1/auth/login` 路徑
- 既有 admin / 一般 user 的所有功能

---

## 重用既有元件

| 既有功能 | 重用方式 |
|---------|---------|
| `BaseSSOClient` 抽象類 | OIDCSSOClient 直接繼承 `get_login_url() + validate_ticket()` 兩個 method |
| `routers/sso.py` `/callback` 路徑模式 | OIDC callback 沿用同一個「validate ticket → get_or_create user → 簽 JWT → 302」流程 |
| `crud.create_sso_user()` | 加 `auth_source` 參數即可重用，邏輯不變 |
| `crud.get_user_by_username()` | OIDC 識別時可重用（學號當 username） |
| `auth.create_access_token()` | OIDC 登入後簽 JWT 完全沿用 |
| `httpx` library | OIDC token exchange + jwks 用同一個 client |
| `PyJWT` library | 解析 id_token（已在 `python-jose` 內） |
| `settings.JWT_SECRET_KEY` | OIDC state 簽章用同一個 secret（不需新增） |
| `auth_request` 機制（nginx）| 完全不用動，OIDC 走相同認證流程 |

---

## 階段拆分（四階段：A/B/C 預先做、D 待 IT 資料）

### 階段 OIDC-A：架構先行（不需 IT 資料 / 約 3 小時）
1. `models.py` 加 `auth_source` + `external_id`
2. `database.py` 加 ALTER
3. `sso_client.py` 加 `OIDCSSOClient` + 工廠擴充
4. `sso_policy.yaml` 加 `oidc:` 區塊（值用 PENDING）
5. `config.py` 加 OIDC_ENABLED flag
6. `routers/sso.py` 加 4 個端點 + state 簽章
7. `crud.py` 修改 3 個函式
8. `schemas.py` 加 `auth_source` 欄位
9. Import 驗證 + node --check

### 階段 OIDC-B：前端（不需 IT 資料 / 約 1.5 小時）
10. `index.html` 加 SSO 按鈕 + 密碼區塊條件渲染
11. `app.js` 加 `?sso_token=` 解析、providers fetch、按鈕 click、密碼變更分流
12. 加 i18n（`sso_school_login` / `password_change_external` 等）

### 階段 OIDC-C：申請信範本 + 文件（不需 IT 資料 / 約 30 分鐘）
13. `docs/dev/IT-OIDC-申請信範本.md` — 含 redirect_uri、scopes、tenant_id、應用名稱
14. 更新 `docs/01-部署與運營/05-SSO整合設定指南.md` — 加 OIDC 章節

### 階段 OIDC-D：拿到 IT 資料後（你執行，幾分鐘）
15. 把 `sso_policy.yaml` 的 PENDING 換成真值
16. `docker compose restart job-scheduler`
17. 用學校帳號測試登入

---

## 驗證方式（End-to-End）

### A. 階段 A 後（沒有 IT 資料）
1. `docker compose up -d` — 服務啟動 healthy
2. `curl http://localhost/api/v1/sso/providers` → 回 `{"providers": ["mock"]}`（OIDC 因 PENDING 不啟用）
3. `curl http://localhost/api/v1/sso/oidc/login` → 回 503 "OIDC not configured"
4. **既有本機登入仍可用** — 用 admin 帳號 POST `/api/v1/auth/login` 成功

### B. 階段 B 後（前端到位）
5. 瀏覽器打開 `/train/` — 登入頁不顯示 SSO 按鈕（因為 OIDC_ENABLED=false）
6. 設定頁的密碼變更區塊照常顯示（admin 是 local 帳號）

### C. 階段 D 後（IT 資料填入）
7. 重啟服務 → `/api/v1/sso/providers` 回 `{"providers": ["mock", "oidc"]}`
8. 登入頁出現「使用學校帳號登入」按鈕
9. 點按鈕 → 302 到 Microsoft → 用 MCU 帳號登入 → 302 回 `/?sso_token=...` → 自動進 dashboard
10. 在資料庫 `users` 表內可看到該使用者，`auth_source="sso_oidc"`、`external_id=<oid>`
11. 設定頁切到「變更密碼」→ 顯示 Microsoft 帳號設定連結（**不顯示**舊密碼輸入框）
12. 嘗試對該帳號 PUT `/me {"password": "xxx"}` → 拒絕 + 400 錯誤

### D. 回歸測試（不能壞）
13. 既有 admin 本機登入仍可用
14. mock SSO 仍可（將 provider 改回 mock 測試）
15. 既有 student 帳號（從 register 註冊的）改密碼仍可

---

## 風險與緩解

| 風險 | 緩解 |
|------|------|
| Microsoft 端打回的 id_token 簽章未驗證 | MVP 不驗（token 是 HTTPS 從 token endpoint 拿，已是端對端加密）；v2.2 加 jwks 驗證 |
| state 用 HMAC + timestamp，有 replay window 10 分鐘 | 對 SSO 場景已夠（CSRF 是主要威脅，timestamp 防 replay 足以） |
| 學號改名 / 換 email | external_id (oid) 永久不變，可作為主識別；username 可同步更新 |
| 學校 IT 拒絕配 client_id | 此時整個 OIDC 功能停用，本機登入照常 — 影響零 |
| 學生離校後 Entra 帳號停用 | Microsoft 端登入直接被擋，使用者進不到我們的 SSO callback，無需我們處理 |
| 同一個學號既被 admin 用 provision 建過、又透過 OIDC 登入 | callback 邏輯：先用 external_id 找，沒有則用 email 找，匹配到 local 帳號則升級該 user 的 auth_source 為 "sso_oidc"（並警告 admin） |

---

## 未來考慮（不在本 plan 內）

### 1. id_token 簽章驗證（jwks）
- 抓 `https://login.microsoftonline.com/{tenant_id}/discovery/v2.0/keys`
- 用 RS256 驗 id_token signature
- 加入 cache 避免每次 callback 都打外部請求

### 2. SLO（Single Logout）
- Microsoft 支援 OIDC RP-initiated logout
- 點本平台「登出」時順便登出 Microsoft session

### 3. Group claim 對應 role
- Microsoft Entra group → 本機 role 自動對應
- 例如：MCU 內「教師」group → 本機 `role=teacher`
- 目前所有 OIDC 登入預設 `role=student`，admin 須手動提權

### 4. 其他 SSO provider
- Google for Education（用 OIDC，類似 Microsoft）
- 自架 Keycloak（多協定 federation）

### 5. v1.1 審查發現的 6 個品質升級項目（待 v2.2 或之後處理）

- **I8: redirect_uri 上線時要重新註冊**
  - 開發階段用 `http://localhost:8002/api/v1/sso/oidc/callback`
  - 正式環境必須換成真實 domain，要重新跟 IT 申請註冊新的 redirect_uri
  - **緩解**：申請信範本內請 IT **一次申請 dev + prod 兩個 redirect_uri**（Microsoft App Registration 一次可掛多個 redirect_uri）

- **S12: 加 `nonce` 參數防 id_token replay**
  - OIDC 規範強烈建議；對 confidential client（有 client_secret）不是必須但更穩
  - 改動：`get_login_url` 加 nonce 參數，`validate_ticket` 驗 id_token 的 nonce claim

- **S13: 給 OIDC state 一個獨立 KEK（`SSO_STATE_SECRET`）**
  - 目前重用 `JWT_SECRET_KEY`，功能正確但金鑰再利用是安全瑕疵
  - 加 `settings.SSO_STATE_SECRET`，沿用 fail-fast field_validator 模式

- **S14: admin-ui 使用者管理列表加「登入方式」欄位**
  - 新增 `auth_source` 後，admin 應能在使用者表格看到「local / sso_oidc / sso_cas」
  - 改動：`admin-ui` 表格 schema 加一欄、`/admin/users` 回傳含 auth_source

- **S15: 驗證 checklist 加「Email 衝突」情境**
  - 測試：admin provision `T1090099@mcu.edu.tw` (local) → 該學生 OIDC 登入 → 驗證升級為 sso_oidc 且 audit 有紀錄

- **S16: admin 雙身分 UX 提醒**
  - admin 本人若也是學校員工，可能想用 SSO 看「普通使用者視角」，但同瀏覽器會雙 token 衝突
  - 修法：在 admin 設定頁加一行說明「若需測試使用者體驗，請開隱身視窗或登出後重登」

### 6. 訪客登入（低優先，後期實作機率低）
- 學生 / 老師 / admin 已透過 OIDC 與本機路徑覆蓋
- 若未來真的有需求，新增 `auth_source="guest"` + admin 配發 + 不寫 audit log + token 用量照計
- 目前不規劃

---

## 預估工作量

| 階段 | 工時 |
|------|------|
| A. 後端架構（不需 IT 資料） | 3 小時 |
| B. 前端整合（不需 IT 資料） | 1.5 小時 |
| C. 申請信範本 + 文件 | 30 分鐘 |
| **可先做的合計** | **約 5 小時** |
| D. 拿到資料後填值 + 重啟 + 測試 | 30 分鐘 |
| **總合** | **約 5.5 小時** |
