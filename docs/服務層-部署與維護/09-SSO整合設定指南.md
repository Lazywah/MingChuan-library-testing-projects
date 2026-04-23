# 09 - SSO 整合設定指南

## 架構說明

本平台支援兩種 SSO 登入模式：
1. **Mock 模式 (開發用)**：免實際 CAS 伺服器，模擬校園 SSO 登入流程並使用內建的模擬假資料。
2. **Real CAS 模式 (正式用)**：對接真實校園單一登入 CAS 認證機制，取得使用者資料並自動為其建立系統帳號。

此雙模式架構與 GPU 的雙模式 (Mock/SSH) 概念一致，皆為「積木式」開發設計，方便日後開發與部署無縫切換。

---

## 模式切換方式

要切換 SSO 模式，請修改 `.env` 檔案中的：
```env
# ------------------------------------------------------------------------------
# SSO 校園登入設定
# ------------------------------------------------------------------------------
SSO_MOCK_MODE=true  # true 表示 Mock 模式，false 表示 Real 模式
```
> 若修改 `.env`，請記得重啟容器 `docker compose restart job-scheduler`。

---

## 參數設定檔 (sso_policy.yaml)

SSO 的相關參數 (如 CAS 伺服器網址、Mock 用戶資料) 獨立放置於 `job-scheduler/app/sso_policy.yaml` 檔案中。設定檔結構如下：

```yaml
mock_mode: true  # 是否優先啟用模擬模式（此處會被 .env 中的 SSO_MOCK_MODE 覆蓋）

# 真實 CAS 伺服器配置
cas:
  server_url: "https://sso.school.edu.tw/cas"   # 您校園登入系統的網址
  service_url: "http://您的對外主機IP/api/v1/sso/callback" # CAS 返回驗證的網址，需與主機對外 IP 一致
  version: "3.0"

# 開發模擬環境配置
mock:
  users:
    - student_id: "T1090001"
      password: "T1090001"
      name: "林小明"
      email: "T1090001@school.edu.tw"
      role: "student"
    - student_id: "admin"
      password: "admin"
      name: "系統管理員"
      email: "admin@school.edu.tw"
      role: "admin"

### 🔒 雙重驗證機制 (Dual-Auth)
本系統實作了**混合式驗證**：
1. **SSO 驗證**：若使用者透過 SSO 登錄，系統會先對比 `sso_policy.yaml` 中的名單。
2. **資料庫驗證**：使用者亦可於之後在「系統設定」中修改個人密碼，新密碼會寫入資料庫。登入時，後端會同時驗證資料庫 hash 與 SSO 預設密碼，確保使用者不會因忘記新密碼而無法進入系統。
```

### 上線須知

準備好對接真實校園 SSO 的時候，請遵循以下步驟：
1. 在 `.env` 中修改 `SSO_MOCK_MODE=false`
2. 打開 `sso_policy.yaml`，將 `cas.server_url` 修改為真實學校 SSO URL
3. 將 `cas.service_url` 的 `http://localhost` 修改為正式環境對外的網址或 IP
4. 重啟服務

系統收到真實使用者的 Ticket 後，將會向 CAS Server 驗證，並自動將新登入者資料寫入至本地資料庫中 (表單 `users`)，隨後自動分配預設 Token 額度。
