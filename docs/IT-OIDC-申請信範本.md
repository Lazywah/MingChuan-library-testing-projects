# IT SSO（OIDC / Microsoft Entra ID）申請說明

> 用途：向校內 IT 申請 Microsoft Entra ID 的 App Registration，讓「圖書館 AI 基地」平台能用學校帳號單一登入（SSO）。
> 本平台走 **OpenID Connect（OIDC）Authorization Code Flow + Client Secret**（Web / confidential client），**不是** SPA、**不用** PKCE。

---

## 一、可直接寄給 IT 的申請信（複製即用）

> 主旨：申請 Microsoft Entra ID App Registration（校內 SSO 串接）
>
> 您好，
>
> 我們要讓「圖書館 AI 基地」平台以學校帳號登入，需在 Microsoft Entra ID 註冊一個 App Registration。相關資訊如下：
>
> **一、請協助建立的 App**
> - App 顯示名稱：`圖書館 AI 基地 SSO`（名稱可依貴單位慣例調整）
> - 帳戶類型：**單一租戶**（僅本校 Entra 目錄內的帳號可登入）
> - 平台類型：**Web**
> - Redirect URI（callback，請一次登記以下兩筆，Entra 允許多筆並存）：
>   - 開發：`http://localhost:8002/api/v1/sso/oidc/callback`
>   - 正式：`https://<正式網域>/api/v1/sso/oidc/callback` ← 正式網域確定後補上
> - 需要的委派權限（delegated / OpenID）：`openid`、`email`、`profile`
>   （若貴租戶預設關閉使用者自行同意，煩請一併「授予管理員同意」）
>
> **二、煩請回覆給我們的三項資訊**
> - Application (client) ID
> - 一組 Client secret 的「值」（Value）— 我們理解此值僅在建立當下顯示一次
> - Directory (tenant) ID（我們目前掌握為 `30f2f0eb-3fc8-4a5a-94b5-fffa8944532e`，煩請確認一致）
>
> **三、想與您確認的一點（影響帳號對應）**
> 我們會以登入者 id_token 內的 `email`（若無則 `preferred_username`）的「@ 前半段」作為系統帳號（學號）。
> 煩請確認登入者會回傳 email 或 UPN，且其 @ 前半段即為學號。
>
> **四、以下項目我們用不到，不需為此設定**（供參考，避免多做）
> - 不需要啟用 implicit / hybrid（Authentication 頁的「ID tokens / Access tokens」勾選）
> - 不需要 SPA 平台或 PKCE
> - 不需要憑證 / federated credential（我們使用 client secret）
> - 不需要 post-logout redirect URI
>
> 感謝協助，若需補充任何資訊請告知。

---

## 二、IT 回覆後，我方要做的事

> 🔴 **client_id / client_secret 一律填進「根目錄 `.env`」，絕不要填進 `sso_policy.yaml`**（該檔會進版控）。

1. 在根目錄 `.env` 填入（`.env` 已 gitignore）：
   ```
   OIDC_CLIENT_ID=<IT 給的 Application (client) ID>
   OIDC_CLIENT_SECRET=<IT 給的 Client secret 值>
   OIDC_REDIRECT_URI=http://localhost:8002/api/v1/sso/oidc/callback   # 正式上線改成 https://<正式網域>/api/v1/sso/oidc/callback
   ```
2. 編輯 `job-scheduler/app/sso_policy.yaml`：
   - `provider: mock` → `provider: oidc`
   - `mock_mode: true` → `mock_mode: false`（⚠ 沒改 false 會強制走 mock、覆蓋 provider）
3. 重啟 job-scheduler（`app/` 為熱掛載，**不需 rebuild**）。
4. 驗證：`GET /api/v1/sso/providers` 回傳應含 `"oidc"`（先前為 `[]`）。

> 機敏值由 `config.py` 於啟動時以環境變數覆寫 `sso_policy.yaml` 的 `PENDING` 佔位；未設環境變數時維持 PENDING → OIDC 停用、fallback mock。

---

## 三、快速檢查清單

**要給 IT：** App 名稱、帳戶類型（單一租戶）、平台（Web）、Redirect URI（dev + prod）、委派權限（openid/email/profile）。

**要跟 IT 拿：** client_id、client_secret（只顯示一次，且會過期，記換發時程）、tenant_id（確認一致）。

**要跟 IT 確認：** id_token 的 email / UPN，其 `@` 前半段 = 學號。

**不需要：** implicit/hybrid、SPA/PKCE、憑證登入、post-logout redirect URI、jwks 簽章設定。

---

## 四、技術背景（供 IT 或後續維護者參考）

- Authority：`https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0`
- 授權請求：`response_type=code`、`response_mode=query`、`scope=openid email profile`、含 `state`（HMAC stateless，CSRF 防護）
- Token 交換：server 端 POST `/token`，帶 `client_secret` + `redirect_uri`（`redirect_uri` 在授權與換 token 兩處必須完全一致，且與 Entra 註冊一致）
- 取用 claims：`email`（無則 `preferred_username`）、`name`；SSO 登入者 `role` 預設 `student`，管理員須另於 DB 提權
- 實作位置：`job-scheduler/app/routers/sso.py`、`job-scheduler/app/sso_client.py`、設定 `job-scheduler/app/sso_policy.yaml`

> 已知硬化缺口（非 IT 事項，供內部排期）：目前 id_token 未驗簽章 / `aud` / `iss` / `exp`、未使用 nonce。因 code 由 server 端經 TLS 直接與 Microsoft 換取、不經瀏覽器，風險可控；規劃於後續版本加入 jwks 簽章驗證。
