# 05 - SSO 整合設定指南 | SSO Integration Guide

> **適用版本**：v2.1（2026-05 新增 OIDC 支援）
> 本平台支援 3 種 SSO 模式，依學校所用的認證系統選擇。

## 📑 目錄 | Table of Contents

- [架構說明](#架構說明)
- [3 種模式比較](#3-種模式比較)
- [參數設定檔（sso_policy.yaml）結構](#參數設定檔-sso_policyyaml-結構)
- [模式 1：Mock SSO（開發測試用）](#模式-1mock-sso-開發測試用)
- [模式 2：CAS（Yale CAS 協定）](#模式-2cas-yale-cas-協定)
- [模式 3：OIDC（Microsoft Entra ID / Google / Keycloak）](#模式-3oidc-microsoft-entra-id--google--keycloak)
- [Microsoft Entra ID 對接完整流程](#microsoft-entra-id-對接完整流程)
- [密碼變更行為](#密碼變更行為依-auth_source-分流)
- [疑難排解](#疑難排解)
- [上線檢查清單](#上線檢查清單)

---

## 架構說明

```
User UI (port 80)                  Backend (FastAPI)              External IdP
─────────────────                  ────────────────              ─────────────
                                                                  ┌─────────────┐
                  ┌──────────────────────┐                       │ Microsoft   │
登入頁            │ /api/v1/sso/oidc/    │  ←─ OIDC code ──     │ Entra ID    │
[使用學校帳號登入] ──→ login → callback   │                       └─────────────┘
                  └──────────────────────┘                       ┌─────────────┐
                                                                  │ CAS Server  │
                  ┌──────────────────────┐  ←─ CAS ticket ──     │ (其他學校)  │
                  │ /api/v1/sso/login    │                       └─────────────┘
                  │       callback       │
                  └──────────────────────┘
                                                  Dev only ←──→ MockSSOClient
                                                                 (yaml 本地)
```

**設計原則**：3 個 client 都繼承 `BaseSSOClient` 抽象介面、互不知道對方存在；切換模式只需改 `sso_policy.yaml` 的 `provider` 欄位，**不必動程式碼**。

---

## 3 種模式比較

| 模式 | 適用情境 | 密碼存放 | UI 入口 |
|------|---------|---------|--------|
| **Mock** | 開發 / 測試 / 沒 SSO server 時 | 寫死於 yaml（明文） | 不曝光於 UI；直接打 URL `/api/v1/sso/login` |
| **CAS** | 學校用 Yale CAS（學術界主流） | 學校 LDAP / AD | UI 顯示「使用學校帳號登入」按鈕 |
| **OIDC** | 學校用 Microsoft 365 / Google / Keycloak | IdP（不在你的 app） | UI 顯示「使用學校帳號登入」按鈕 |

**MCU 是 OIDC**（Microsoft Entra ID 管理 mcu.edu.tw 域）。

---

## 參數設定檔（sso_policy.yaml）結構

位於 `job-scheduler/app/sso_policy.yaml`，v2.1 後完整結構：

```yaml
# ─── 兩個頂層 flag（向後相容）────────────────────────────────────────
mock_mode: true            # true 時強制走 mock（覆蓋 provider 欄位）
provider: mock             # mock | cas | oidc（mock_mode=false 時才生效）

# ─── Mock 模式設定（dev 用）────────────────────────────────────────
mock:
  users:
    - student_id: "T1090001"
      password: "T1090001"
      name: "林小明"
      email: "T1090001@school.edu.tw"
      role: "student"

# ─── CAS 模式設定（學校用 CAS server 時填）─────────────────────────
cas:
  server_url: "https://cas.school.edu.tw/cas"      # 學校 CAS URL
  service_url: "http://your-domain/api/v1/sso/callback"
  version: "3.0"

# ─── OIDC 模式設定（v2.1 新增 — MCU Microsoft Entra ID）──────────
oidc:
  tenant_id: "30f2f0eb-3fc8-4a5a-94b5-fffa8944532e"   # MCU 公開資訊
  client_id: "PENDING"          # ⏳ 等 IT 申請後填入
  client_secret: "PENDING"      # ⏳ 等 IT 申請後填入（敏感！正式環境建議改放 .env）
  redirect_uri: "http://localhost:8002/api/v1/sso/oidc/callback"
  scopes:
    - "openid"
    - "email"
    - "profile"
  password_change_url: "https://account.activedirectory.windowsazure.com/ChangePassword.aspx"
  password_reset_url:  "https://passwordreset.microsoftonline.com/"
```

> 修改後請 `docker compose restart job-scheduler` 套用。

---

## 模式 1：Mock SSO（開發測試用）

**啟用方式**：
```yaml
mock_mode: true     # 或 provider: mock
```

**使用方式**（dev 環境）：
1. 直接打瀏覽器到 `http://localhost/api/v1/sso/login`
2. 看到 HTML 表單，下拉選一個學生帳號（如 T1090001）
3. 系統自動建帳號 + 簽 JWT + 跳轉回 user UI

**重要**：v2.1 後 Mock SSO **不在 user UI 顯示按鈕**（設計上避免 admin 透過別人帳號登入）。開發者必須知道 URL 才能用。

**典型用途**：
- 後端開發者測試 SSO 流程
- E2E 測試自動化
- 第一次部署 OIDC 還沒拿到 client_id 時，admin 仍可透過 port 8888 admin-ui 用本機 username/password 進入

---

## 模式 2：CAS（Yale CAS 協定）

**啟用方式**：
```yaml
mock_mode: false
provider: cas

cas:
  server_url: "https://cas.YOUR-SCHOOL.edu.tw/cas"   # 跟學校 IT 確認
  service_url: "https://YOUR-APP-DOMAIN/api/v1/sso/callback"
  version: "3.0"     # 多數 CAS 是 3.0；少數老學校用 2.0
```

**注意事項**：
- `service_url` 必須是**對外可達的 URL**（CAS server 會 302 過來，localhost 不能用）
- `service_url` 必須**精確匹配**註冊在 CAS server 白名單的網址
- 跟 IT 申請時請告知此 URL 並確認加入白名單

**MCU 不適用**：MCU 沒有對外開放的 CAS server（嘗試 `sso.mcu.edu.tw` 得 ECONNREFUSED）。

---

## 模式 3：OIDC（Microsoft Entra ID / Google / Keycloak）

**MCU 學校用此模式**。MCU 是 Microsoft 365 Managed Tenant，所有師生 SSO 走 Microsoft Entra ID。

**啟用方式**：
```yaml
mock_mode: false
provider: oidc

oidc:
  tenant_id: "30f2f0eb-3fc8-4a5a-94b5-fffa8944532e"    # MCU Microsoft Entra Tenant ID（公開資訊）
  client_id: "<IT 提供>"
  client_secret: "<IT 提供>"
  redirect_uri: "https://YOUR-APP-DOMAIN/api/v1/sso/oidc/callback"
  scopes: ["openid", "email", "profile"]
```

**取得 client_id / client_secret 流程**：見下一節「Microsoft Entra ID 對接完整流程」。

**OIDC 與 CAS 的差異**：

| 項目 | CAS | OIDC |
|------|-----|------|
| Callback URL 名稱 | `service_url` | `redirect_uri` |
| 驗證機制 | XML over HTTP | JSON Web Token (JWT) |
| HTTPS 要求 | 建議（非強制） | **強制**（localhost 例外） |
| Client 認證 | 無（公開驗證） | `client_secret`（須保密） |
| User 屬性 | 受限（要靠 CAS server XML 擴充） | 豐富（含 oid 永久 ID、name、email） |
| MFA / 多因素 | 視 CAS server 實作 | IdP 內建（如 Microsoft MFA） |

**v2.1 的 OIDC 端點**：
| 端點 | 用途 |
|------|------|
| `GET /api/v1/sso/oidc/login` | 跳轉至 Microsoft 授權頁 |
| `GET /api/v1/sso/oidc/callback` | Microsoft 回呼，驗證 + 建本機 user + 簽 JWT |
| `GET /api/v1/sso/providers` | 列出當下啟用的 SSO providers（前端用） |
| `GET /api/v1/sso/password-change-info` | 告訴前端密碼變更 UI 該怎麼顯示 |

---

## Microsoft Entra ID 對接完整流程

### 步驟 1：寄申請信給學校 IT

範本見 `docs/dev/IT-OIDC-申請信範本.md`。重點：
- 告知對方是 **App Registration**（不是 Enterprise App）
- **redirect_uri 一次申請 dev + prod 兩個**（避免上線時還要再申請）
- 需要 scopes：`openid` + `email` + `profile`（基本）
- **不需要** admin consent 或 Graph API 寫入權限

### 步驟 2：IT 回信，給你 client_id + client_secret

- `client_id` 是公開資訊（出現在 URL 中），可以放 yaml 明文
- `client_secret` 是**敏感資訊**（等同密碼），正式環境建議改放 `.env`：

  ```yaml
  # sso_policy.yaml
  oidc:
    client_secret: "${OIDC_CLIENT_SECRET}"   # 從環境變數讀（需自己改 config.py 支援展開）
  ```

  或直接寫 yaml 明文（dev / 內網部署可接受）。

### 步驟 3：填入 yaml + 重啟

```yaml
mock_mode: false
provider: oidc
oidc:
  client_id: "abc-123-def-456-..."    # IT 給的
  client_secret: "Xyz~XYZ.123..."     # IT 給的
  redirect_uri: "https://your-app.mcu.edu.tw/api/v1/sso/oidc/callback"
```

```bash
docker compose restart job-scheduler
```

### 步驟 4：驗證 OIDC 啟用

```bash
# 確認 /providers 端點回傳 oidc
curl http://localhost/api/v1/sso/providers
# 預期: {"providers": ["oidc"]}
```

打開瀏覽器到 user UI → 應該看到「使用學校帳號登入」按鈕。

### 步驟 5：實際測試登入

1. 點「使用學校帳號登入」→ 302 跳到 `login.microsoftonline.com`
2. 用 MCU 帳號登入（學號@mcu.edu.tw + 密碼 + MFA）
3. Microsoft 302 回來 `/api/v1/sso/oidc/callback?code=...&state=...`
4. 後端驗 state、用 code 換 id_token、建本機 user
5. 302 回 user UI 帶 `?sso_token=...`
6. 前端解析 token、存 localStorage、進入 dashboard

### 步驟 6（選擇性）：升級首位 admin

OIDC 預設所有人 `role=student`。要讓某使用者變 admin：

```bash
docker compose exec job-scheduler python -c "
from app.database import SessionLocal
from app import models
db = SessionLocal()
u = db.query(models.User).filter(models.User.username == 'T1099001').first()
u.role = 'admin'
db.commit()
print(f'Upgraded {u.username} to admin')
db.close()
"
```

---

## 密碼變更行為（依 auth_source 分流）

v2.1 在 `User` 表加了 `auth_source` 欄位，前端依此分流 UI：

| auth_source | UI 行為 | 後端行為 |
|------------|---------|---------|
| `local` | 顯示「舊密碼 + 新密碼」表單，可改 | `PUT /api/v1/auth/me` 接受 password |
| `sso_mock` | 顯示「Mock 帳號無密碼可變更」 | `PUT /me` 拒絕（400） |
| `sso_cas` | 顯示「請至學校 CAS 系統」 | `PUT /me` 拒絕（400） |
| `sso_oidc` | 顯示「前往 Microsoft 變更密碼」連結 + 「為什麼不能在這裡改」說明 | `PUT /me` 拒絕（400） |

**重要**：即使前端 UI 隱藏輸入框，後端仍會**主動拒絕**（深度防禦）。這由 `crud.update_user()` 在 v2.1 加入的 SSO 檢查實現。

---

## 疑難排解

### 問題 1：`/api/v1/sso/oidc/login` 回 503 `OIDC is not configured`

**原因**：`sso_policy.yaml` 的 `client_id` / `client_secret` 仍是 `PENDING`，或 `provider` 不是 `oidc`。

**解法**：
```bash
# 確認設定
docker compose exec job-scheduler grep -E "provider|client_id|mock_mode" /app/app/sso_policy.yaml

# 看啟動 log 是否有警告
docker compose logs job-scheduler | grep -i "oidc"
```

預期看到：`OIDC enabled (redirect_uri=...)`。如果看到 `OIDC provider selected but config is incomplete`，表示 PENDING 還在。

### 問題 2：點「使用學校帳號登入」跳到 Microsoft 但被擋

可能訊息：
- `AADSTS50011: The redirect URI ... does not match` → `redirect_uri` 沒登記在 Entra App Registration 白名單
- `AADSTS700016: Application ... was not found` → `client_id` 錯
- `AADSTS7000215: Invalid client secret` → `client_secret` 錯或過期

**解法**：與 IT 確認 client_id / secret / 註冊的 redirect_uri 是否完全匹配 yaml。

### 問題 3：登入成功但回到 user UI 後沒進 dashboard

**原因**：前端 `setupSSOLogin` IIFE 沒抓到 `?sso_token=` 參數。

**解法**：
```javascript
// 瀏覽器 console 跑一下
new URLSearchParams(window.location.search).get('sso_token')
// 應該回傳 JWT 字串
```

如果 URL 沒帶 `?sso_token=`，看後端 log：`docker compose logs job-scheduler | grep "SSO"`，確認 callback 成功且發了 302。

### 問題 4：使用者進系統後密碼變更被拒絕

**這是預期行為**。SSO 使用者不能在本地改密碼。前端會顯示「您使用學校 Microsoft 帳號登入，密碼由學校統一管理」並提供 Microsoft 變更密碼連結。

如果想讓特定使用者變回 local 帳號（緊急狀況）：
```bash
docker compose exec job-scheduler python -c "
from app.database import SessionLocal
from app import models
db = SessionLocal()
u = db.query(models.User).filter(models.User.username == 'T1099001').first()
u.auth_source = 'local'
db.commit()
db.close()
"
```

注意 hashed_password 是 SSO 自動生的隨機值，使用者不知道，需先做密碼重設。

### 問題 5：state 驗證失敗（`Invalid or expired state`）

**原因**：state HMAC 簽章用 `JWT_SECRET_KEY`。如果 secret 在登入過程中改變（容器重啟換 key），原本簽好的 state 就驗不過。

**解法**：避免在使用者進行 OIDC 登入的時段重啟服務。如果不小心發生，使用者重點一次登入按鈕即可。

state 預設 10 分鐘有效，超過會自動失敗。

---

## 上線檢查清單

正式環境部署 OIDC 前確認：

- [ ] **HTTPS**：app 對外網址必須是 https（OIDC 規範強制）
- [ ] **redirect_uri**：yaml 內 redirect_uri 與 Entra 註冊的精確一致（含尾斜線、port、protocol）
- [ ] **client_secret 不在 git**：建議放 `.env` 不放 yaml；或 yaml 加進 `.gitignore`
- [ ] **JWT_SECRET_KEY 不在 git**：與 OIDC 無關但同樣重要
- [ ] **sso_policy.yaml 唯讀掛載**：`docker-compose.yml` 中 `:ro` 避免容器 RCE 後改設定
- [ ] **首個 admin 已升級**：照「步驟 6」設好 admin（OIDC 預設所有人 student）
- [ ] **本機 admin 帳號保留**：作為 SSO 故障時的緊急救援（port 8888 仍可用 username/password）
- [ ] **`/api/v1/sso/providers` 回 `["oidc"]`**：確認啟用
- [ ] **`/api/v1/sso/password-change-info` 回正確 URL**：點看是否能開 Microsoft 變更密碼頁

---

## 進階：未來升級項目（v2.2+）

| 項目 | 動機 |
|------|------|
| **id_token 簽章驗證（jwks）** | MVP 階段未驗簽（token 直接從 HTTPS token endpoint 拿，端對端加密已足夠）；v2.2 加 jwks 公鑰驗證更穩 |
| **Single Logout (SLO)** | 目前 logout 只清本機 localStorage；v2.2 可加同步登出 Microsoft session |
| **Group claim 對應 role** | Microsoft Entra group → 本機 role 自動對應（教師 group → role=teacher）|
| **SSO_STATE_SECRET 獨立** | 目前 OIDC state 重用 `JWT_SECRET_KEY`；v2.2 給 state 一個獨立 KEK |
| **同時啟用多個 IdP** | 例：學生用 MCU 帳號（OIDC）、訪客用 Google（OIDC）、admin 用本機 |

詳細實作建議見 `docs/dev/PLAN-v2.1-sso-oidc-2026-05-22.md` 的「未來考慮」章節。
