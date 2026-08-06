> # ⛔ 此文件已過時，僅作歷史紀錄，請勿再寄出
>
> **實際情況與本文假設不符**：MCU 用的是**自建 OIDC 伺服器 `auth.mcu.edu.tw`**，
> **不是** Microsoft Entra ID。依本文向 IT 申請 Entra App Registration 會得到錯誤結果
> （實測 `AADSTS700016`）。憑證已於 2026-08 取得並完成串接。
>
> 現行設定與上線步驟請看 [`03-deployment.md`](03-deployment.md) §2 與
> [`00-本機完整部署指南.md`](00-本機完整部署指南.md) §9。
>
> 保留本檔的原因：記錄當時與 IT 往來的問題清單（憑證類型、redirect URI、帳號對應），
> 日後若要向 IT 申請 **prod 主機名 + TLS 憑證**仍可參考其提問結構。

---

# IT SSO（OIDC / Microsoft Entra ID）申請說明

> 用途：向校內 IT 申請 Microsoft Entra ID 的 App Registration，讓「圖書館 AI 基地」平台能用學校帳號單一登入（SSO）。
> 本平台走 **OpenID Connect（OIDC）Authorization Code Flow**（Web / confidential client），**不是** SPA、**不用** PKCE。
> Client 端驗證方式：**首選 client secret；若貴租戶政策禁止建立 client secret，則改用憑證（certificate credential，private_key_jwt）**——屆時我方提供公鑰供上傳、私鑰自行保管（詳見下方申請信第二、五點）。

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
>   - 開發：`http://localhost/api/v1/sso/oidc/callback`（走 nginx :80，非 :8002；Entra 對 localhost 允許 http）
>   - 正式：`https://<正式網域>/api/v1/sso/oidc/callback` ← 正式網域確定後補上（非 localhost 只能 https）
> - 需要的委派權限（delegated / OpenID）：`openid`、`email`、`profile`
>   （若貴租戶預設關閉使用者自行同意，煩請一併「授予管理員同意」）
>
> **二、煩請回覆給我們的資訊**
> - Application (client) ID
> - Directory (tenant) ID（我們目前掌握為 `30f2f0eb-3fc8-4a5a-94b5-fffa8944532e`，煩請確認一致）
> - Client 端驗證憑據，二擇一：
>   - **(首選) Client secret 的「值」（Value）** — 我們理解此值僅在建立當下顯示一次；也想請您一併告知貴租戶允許的**到期上限**（以便我方安排換發）。
>   - **(備案) 若貴租戶政策禁止建立 client secret**（Entra 會顯示「Client secrets are blocked by a tenant-wide policy」），請告知，我方改用**憑證**：由我方產生金鑰對、將**公鑰憑證（.cer）**寄給您上傳至此 App，私鑰由我方保管、不外流。
>
> **三、想與您確認的兩點**
> 1.（影響帳號對應）我們會以登入者 id_token 內的 `email`（若無則 `preferred_username`）的「@ 前半段」作為系統帳號（學號）。煩請確認登入者會回傳 email 或 UPN，且其 @ 前半段即為學號。
> 2.（影響驗證方式）貴租戶是否允許本 App 建立 client secret？若不允許，我方走上述憑證備案。
>
> **四、以下項目我們用不到，不需為此設定**（供參考，避免多做）
> - 不需要啟用 implicit / hybrid（Authentication 頁的「ID tokens / Access tokens」勾選）
> - 不需要 SPA 平台或 PKCE
> - 不需要 federated credential（若走憑證，是傳統的 certificate credential，非 workload identity federation）
> - 不需要 post-logout redirect URI
>
> **五、若走憑證備案，我方會提供**
> - 一份 **X.509 公鑰憑證（.cer / .pem）** 供上傳至此 App Registration 的「Certificates & secrets → Certificates」。私鑰不會提供、由我方安全保管。
>
> 感謝協助，若需補充任何資訊請告知。

---

## 二、IT 回覆後，我方要做的事

> 🔴 **client_id / client_secret 一律填進「根目錄 `.env`」，絕不要填進 `sso_policy.yaml`**（該檔會進版控）。

1. 在根目錄 `.env` 填入（`.env` 已 gitignore）：
   ```
   OIDC_CLIENT_ID=<IT 給的 Application (client) ID>
   OIDC_CLIENT_SECRET=<IT 給的 Client secret 值>
   OIDC_REDIRECT_URI=http://localhost/api/v1/sso/oidc/callback   # 正式上線改成 https://<正式網域>/api/v1/sso/oidc/callback
   ```
2. 編輯 `job-scheduler/app/sso_policy.yaml`：
   - `provider: mock` → `provider: oidc`
   - `mock_mode: true` → `mock_mode: false`（⚠ 沒改 false 會強制走 mock、覆蓋 provider）
3. 重啟 job-scheduler（`app/` 為熱掛載，**不需 rebuild**）。
4. 驗證：`GET /api/v1/sso/providers` 回傳應含 `"oidc"`（先前為 `[]`）。

> 機敏值由 `config.py` 於啟動時以環境變數覆寫 `sso_policy.yaml` 的 `PENDING` 佔位；未設環境變數時維持 PENDING → OIDC 停用、fallback mock。

> ⚠️ **若走憑證備案（非 client secret）**：現行 `sso_client.py` 的 token 交換只實作 client_secret，尚未支援憑證。走此路需先做程式改動：
> 1. 產金鑰對（`openssl req -x509 -newkey rsa:2048 ...`），公鑰 .cer 給 IT 上傳、私鑰以 read-only volume 掛入容器（gitignore、限檔權）。
> 2. `sso_client.py` `validate_ticket()` 的 token POST 改帶 `client_assertion_type` + `client_assertion`（用私鑰簽 JWT，header 含 `x5t` 憑證指紋；可用既有 `python-jose`）。
> 3. `config.py`／`OIDC_ENABLED`／PENDING 判定改看「私鑰是否備妥」而非 `client_secret`。
> 4. `.env` 改放私鑰路徑 + 憑證指紋，取代 `OIDC_CLIENT_SECRET`。
> 瀏覽器側流程（授權導向、redirect_uri、state、callback）完全不變。

---

## 三、快速檢查清單

**要給 IT：** App 名稱、帳戶類型（單一租戶）、平台（Web）、Redirect URI（dev + prod）、委派權限（openid/email/profile）。

**要跟 IT 拿：** client_id、tenant_id（確認一致）、以及 client 驗證憑據二擇一——client_secret（只顯示一次、會過期，記換發時程）**或**（政策禁 secret 時）由我方交公鑰、IT 上傳憑證。

**要跟 IT 確認：**（1）id_token 的 email / UPN，其 `@` 前半段 = 學號；（2）租戶是否允許建立 client secret（決定走 secret 還是憑證）。

**不需要：** implicit/hybrid、SPA/PKCE、federated credential（workload identity）、post-logout redirect URI、jwks 簽章設定。

---

## 四、技術背景（供 IT 或後續維護者參考）

- Authority：`https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0`
- 授權請求：`response_type=code`、`response_mode=query`、`scope=openid email profile`、含 `state`（HMAC stateless，CSRF 防護）
- Token 交換：server 端 POST `/token`，帶 client 驗證憑據（首選 `client_secret`；憑證備案則為 `client_assertion_type=urn:ietf:params:oauth:client-assertion-type:jwt-bearer` + 私鑰簽的 `client_assertion` JWT）+ `redirect_uri`（`redirect_uri` 在授權與換 token 兩處必須完全一致，且與 Entra 註冊一致）
- 取用 claims：`email`（無則 `preferred_username`）、`name`；SSO 登入者 `role` 預設 `student`，管理員須另於 DB 提權
- 實作位置：`job-scheduler/app/routers/sso.py`、`job-scheduler/app/sso_client.py`、設定 `job-scheduler/app/sso_policy.yaml`

> 已知硬化缺口（非 IT 事項，供內部排期）：目前 id_token 未驗簽章 / `aud` / `iss` / `exp`、未使用 nonce。因 code 由 server 端經 TLS 直接與 Microsoft 換取、不經瀏覽器，風險可控；規劃於後續版本加入 jwks 簽章驗證。
