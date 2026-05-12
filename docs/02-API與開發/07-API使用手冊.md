# 07 - API 使用手冊 | API Reference

## 📑 目錄 | Table of Contents
- [認證 API \| Authentication API](#認證-api--authentication-api)
- [訓練任務 API \| Training Jobs API](#訓練任務-api--training-jobs-api)
- [AI 助手 API \| AI Assistant API (Chat)](#ai-助手-api--ai-assistant-api-chat)
- [資料集 API \| Datasets API](#資料集-api--datasets-api)
- [系統 API \| System API](#系統-api--system-api)
- [管理員 API \| Admin API](#管理員-api--admin-api)（使用者管理、任務管理、模型管理、分析）
- [錯誤碼 \| Error Codes](#錯誤碼--error-codes)

---

> **Base URL**: `http://localhost:8002`  
> **Swagger UI**: `http://localhost:8002/docs`

> [!NOTE]
> **Windows 用戶注意**：若您在 PowerShell 中執行以下範例，請將 `curl` 替換為 `curl.exe`，以避免與內建的 `Invoke-WebRequest` 衝突。

## 認證 API | Authentication API

### POST `/api/v1/auth/register` — 使用者註冊

```bash
curl -X POST http://localhost:8002/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "username": "student01",
    "email": "student01@example.com",
    "password": "mypassword",
    "role": "student"
  }'
```

回應 (201):
```json
{
  "id": "uuid-string",
  "username": "student01",
  "email": "student01@example.com",
  "role": "student",
  "is_active": 1,
  "created_at": "2026-04-07T00:00:00"
}
```

### POST `/api/v1/auth/login` — 使用者登入

```bash
curl -X POST http://localhost:8002/api/v1/auth/login \
  -d "username=student01&password=mypassword"
```

回應 (200):
```json
{
  "access_token": "eyJhbGciOi...",
  "token_type": "bearer"
}
```

### GET `/api/v1/auth/me` — 取得當前使用者資訊

```bash
curl http://localhost:8002/api/v1/auth/me \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### PUT `/api/v1/auth/me` — 變更個人資料

```bash
curl -X PUT http://localhost:8002/api/v1/auth/me \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "new.email@example.com",
    "password": "newpassword123"
  }'
```

### GET `/api/v1/auth/usage` — 查詢 Token 用量

```bash
curl http://localhost:8002/api/v1/auth/usage \
  -H "Authorization: Bearer YOUR_TOKEN"
```

回應:
```json
{
  "user_id": "uuid",
  "tokens_used": 5000,
  "tokens_limit": 5000000,
  "usage_percentage": 0.1,
  "reset_date": "2026-05-01T00:00:00"
}
```

### POST `/api/v1/auth/logout` — 使用者登出

```bash
curl -X POST http://localhost:8002/api/v1/auth/logout \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### POST `/api/v1/auth/forgot-password` — 忘記密碼 (發送重設信件)

```bash
curl -X POST http://localhost:8002/api/v1/auth/forgot-password \
  -H "Content-Type: application/json" \
  -d '{"email": "student01@example.com"}'
```

---

## 訓練任務 API | Training Jobs API

### POST `/api/v1/jobs` — 提交訓練任務

```bash
curl -X POST http://localhost:8002/api/v1/jobs \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "job_name": "ResNet50 訓練",
    "model_name": "resnet50",
    "gpu_required": 1,
    "config": {"epochs": 10, "batch_size": 32},
    "priority": 1
  }'
```

回應 (201):
```json
{
  "job_id": "uuid-string",
  "status": "pending",
  "queue_position": 1
}
```

### GET `/api/v1/jobs` — 列出任務

```bash
# ZH: 列出所有任務 (預設 20 筆) | EN: List all jobs (default 20)
curl "http://localhost:8002/api/v1/jobs" -H "Authorization: Bearer TOKEN"

# ZH: 按狀態篩選 + 分頁 | EN: Filter by status + pagination
curl "http://localhost:8002/api/v1/jobs?status=running&limit=10&offset=0" \
  -H "Authorization: Bearer TOKEN"
```

### GET `/api/v1/jobs/{job_id}` — 查詢任務狀態

```bash
curl "http://localhost:8002/api/v1/jobs/JOB_ID" \
  -H "Authorization: Bearer TOKEN"
```

回應:
```json
{
  "job_id": "uuid",
  "job_name": "ResNet50 訓練",
  "status": "running",
  "progress": 60.0,
  "gpu_server": "GPU-Server-1",
  "gpu_id": 0,
  "started_at": "2026-04-07T01:00:00",
  "completed_at": null,
  "error_message": null
}
```

### DELETE `/api/v1/jobs/{job_id}` — 取消任務

```bash
curl -X DELETE "http://localhost:8002/api/v1/jobs/JOB_ID" \
  -H "Authorization: Bearer TOKEN"
```

> ⚠️ ZH: 僅 pending/queued 狀態的任務可取消 | EN: Only pending/queued jobs can be cancelled

---

## AI 助手 API | AI Assistant API (Chat)

本區塊 API 提供對話式 AI 功能，支援串流輸出與歷史紀錄存儲。

### POST `/api/v1/chat/completions` — 發送對話請求

與底層 LLM 進行對話，支援 SSE (Server-Sent Events) 串流。

```bash
curl -X POST http://localhost:8002/api/v1/chat/completions \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "model_id": "gemini-1.5-pro",
    "messages": [
      {"role": "user", "content": "你好，請介紹一下什麼是 GPU 叢集？"}
    ],
    "stream": true
  }'
```

**參數說明**:
- `model_id`: 模型識別碼 (如 `gemini-1.5-pro`, `llama3:latest`)。
- `messages`: 對話歷史陣列。
- `stream`: 是否使用串流模式。
- `user_id`: (由後端從 Token 解析) 自動帶入。

**SSE 異常處理 | Error Handling**:
當發生配額超限 (Quota Exceeded) 或系統錯誤時，SSE 串流可能會發送一個包含 `error` 欄位的 JSON 區塊而非 `choices`：
```json
data: {"error": "Token quota exceeded", "details": "Your monthly quota is depleted."}
```
前端必須攔截此 JSON 並正確顯示錯誤提示，而非將其作為模型文字輸出。 

### GET `/api/v1/chat/history` — 獲取歷史紀錄

取得當前使用者在系統內的對話歷史。

```bash
curl http://localhost:8002/api/v1/chat/history \
  -H "Authorization: Bearer YOUR_TOKEN"
```

回應: `List[ChatMessage]` 格式之陣列。

---

## 資料集 API | Datasets API

### POST `/api/v1/datasets/upload` — 上傳資料集並取得推薦參數

支援上傳 `.csv`, `.jsonl`, `.zip` 格式的資料集。系統將自動解析檔案並回傳建議的 hyperparameters。

```bash
curl -X POST http://localhost:8002/api/v1/datasets/upload \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -F "file=@/path/to/your/dataset.csv"
```

回應 (200):
```json
{
  "message": "Upload successful",
  "dataset_path": "/data/datasets/<uuid>_<filename>",
  "suggested_config": {
    "epochs": 5,
    "batch_size": 16,
    "learning_rate": 0.001
  }
}
```

---

## 系統 API | System API

### GET `/health` — 健康檢查

```bash
curl http://localhost:8002/health
```

### GET `/api/v1/system/files` — 取得系統設定檔列表 (Admin Only)

```bash
curl http://localhost:8002/api/v1/system/files \
  -H "Authorization: Bearer ADMIN_TOKEN"
```

### GET `/api/v1/system/files/{filename}` — 讀取特定設定檔內容 (Admin Only)

```bash
curl http://localhost:8002/api/v1/system/files/.env \
  -H "Authorization: Bearer ADMIN_TOKEN"
```

### PUT `/api/v1/system/files/{filename}` — 儲存特定設定檔內容 (Admin Only)

```bash
curl -X PUT http://localhost:8002/api/v1/system/files/.env \
  -H "Authorization: Bearer ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"content": "SMTP_SERVER=smtp.gmail.com\n..."}'
```

---

## 管理員 API | Admin API

> ⚠️ 以下端點僅限 `role: admin` 的使用者存取，否則回傳 403。

### GET `/api/v1/admin/users` — 取得全部使用者

```bash
curl http://localhost:8002/api/v1/admin/users \
  -H "Authorization: Bearer ADMIN_TOKEN"
```

回應 (200): 包含 `username`, `email`, `role`, `online_status`, `last_login_ip`, `last_login_time`, `tokens_used`, `tokens_limit` 等欄位的陣列。

### GET `/api/v1/admin/jobs` — 取得全部任務

```bash
curl http://localhost:8002/api/v1/admin/jobs \
  -H "Authorization: Bearer ADMIN_TOKEN"
```

### GET `/api/v1/admin/models` — 取得全部模型

```bash
curl http://localhost:8002/api/v1/admin/models \
  -H "Authorization: Bearer ADMIN_TOKEN"
```

### PUT `/api/v1/admin/users/{user_id}` — 修改使用者資訊

```bash
curl -X PUT http://localhost:8002/api/v1/admin/users/USER_ID \
  -H "Authorization: Bearer ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "new@example.com",
    "role": "teacher",
    "is_active": 1,
    "tokens_limit": 2000000,
    "password": "newpass123"
  }'
```

> 所有欄位均為選填，只傳入需要修改的欄位即可。`password` 留空則不變更。

### POST `/api/v1/admin/users/provision` — 配發帳號

管理員建立永久帳號，回傳臨時密碼並透過 Email 通知使用者。

```bash
curl -X POST http://localhost:8002/api/v1/admin/users/provision \
  -H "Authorization: Bearer ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "username": "student01",
    "email": "student01@school.edu.tw",
    "role": "student",
    "password": "optional-custom-password"
  }'
```

回應: `{"id": "uuid", "username": "...", "email": "...", "role": "...", "temp_password": "..."}`

### POST `/api/v1/admin/users/{user_id}/reset` — 初始化帳號

重設密碼為新隨機值，同時歸零 Token 用量，透過 Email 寄送新密碼。

```bash
curl -X POST http://localhost:8002/api/v1/admin/users/USER_ID/reset \
  -H "Authorization: Bearer ADMIN_TOKEN"
```

### POST `/api/v1/admin/users/{user_id}/delete` — 刪除使用者

需提供管理員本人密碼驗證，防止誤操作。

```bash
curl -X POST http://localhost:8002/api/v1/admin/users/USER_ID/delete \
  -H "Authorization: Bearer ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"admin_password": "YOUR_ADMIN_PASSWORD"}'
```

### POST `/api/v1/admin/verify` — 管理員密碼驗證

用於解鎖高風險操作前的身份確認，回傳成功才可繼續。

```bash
curl -X POST http://localhost:8002/api/v1/admin/verify \
  -H "Authorization: Bearer ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"admin_password": "YOUR_ADMIN_PASSWORD"}'
```

回應: `{"message": "Verification successful"}`

### PUT `/api/v1/admin/users/batch/tokens` — 批量更新 Token

支援兩種操作：`reset_usage`（歸零用量）與 `set_limit`（設定月度上限）。

```bash
# 歸零選定使用者的用量
curl -X PUT http://localhost:8002/api/v1/admin/users/batch/tokens \
  -H "Authorization: Bearer ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"user_ids": ["uuid-1", "uuid-2"], "action": "reset_usage", "value": 0}'

# 設定選定使用者的月度上限
curl -X PUT http://localhost:8002/api/v1/admin/users/batch/tokens \
  -H "Authorization: Bearer ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"user_ids": ["uuid-1", "uuid-2"], "action": "set_limit", "value": 2000000}'
```

### POST `/api/v1/admin/jobs/{job_id}/cancel` — 強制取消任務

僅限 `pending` / `queued` 狀態的任務可取消。

```bash
curl -X POST http://localhost:8002/api/v1/admin/jobs/JOB_ID/cancel \
  -H "Authorization: Bearer ADMIN_TOKEN"
```

### PUT `/api/v1/admin/jobs/{job_id}/priority` — 修改任務優先級

優先級範圍 0–5，數字越大越優先。僅限 `pending` / `queued` 狀態。

```bash
curl -X PUT http://localhost:8002/api/v1/admin/jobs/JOB_ID/priority \
  -H "Authorization: Bearer ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"priority": 5}'
```

回應: `{"job_id": "...", "priority": 5, "old_priority": 1, "message": "Priority updated"}`

### POST `/api/v1/admin/models` — 新增模型

```bash
# API 模型（雲端）
curl -X POST http://localhost:8002/api/v1/admin/models \
  -H "Authorization: Bearer ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Claude 3.5 Sonnet",
    "model_type": "api",
    "api_provider": "anthropic",
    "api_model_id": "claude-sonnet-4-6",
    "is_public": 1
  }'

# 本地模型
curl -X POST http://localhost:8002/api/v1/admin/models \
  -H "Authorization: Bearer ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "ResNet50",
    "model_type": "local",
    "framework": "PyTorch",
    "storage_path": "/models/resnet50",
    "is_public": 0
  }'
```

### PUT `/api/v1/admin/models/{model_id}` — 更新模型資訊

```bash
curl -X PUT http://localhost:8002/api/v1/admin/models/MODEL_ID \
  -H "Authorization: Bearer ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"description": "更新後的描述", "is_public": 1}'
```

### DELETE `/api/v1/admin/models/{model_id}` — 刪除模型

```bash
curl -X DELETE http://localhost:8002/api/v1/admin/models/MODEL_ID \
  -H "Authorization: Bearer ADMIN_TOKEN"
```

### GET `/api/v1/admin/cluster/stats` — 叢集資源狀態

```bash
curl http://localhost:8002/api/v1/admin/cluster/stats \
  -H "Authorization: Bearer ADMIN_TOKEN"
```

> 目前為 Worker Pull 模式，回傳即時節點狀態陣列。

### GET `/api/v1/admin/analytics` — 數據分析總覽

```bash
# 全校數據
curl "http://localhost:8002/api/v1/admin/analytics" \
  -H "Authorization: Bearer ADMIN_TOKEN"

# 篩選特定學系
curl "http://localhost:8002/api/v1/admin/analytics?department=資訊工程學系" \
  -H "Authorization: Bearer ADMIN_TOKEN"
```

回應包含：各學系 Token 用量、工具使用佔比、總登入次數等統計數據。

---

## 錯誤碼 | Error Codes

| 狀態碼 | 說明 |
|--------|------|
| 400 | 請求格式錯誤 / 使用者已存在 |
| 401 | 未認證 / Token 無效 |
| 403 | 權限不足 |
| 404 | 資源不存在 |
| 429 | Token 配額超出 |
| 500 | 伺服器內部錯誤 |
| 503 | 服務不可用 |
