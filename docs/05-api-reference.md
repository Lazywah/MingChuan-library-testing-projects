# 05 — API 參考 | API Reference

> **Base URL**: `http://localhost:8002`  •  **Swagger UI**: `http://localhost:8002/docs`
>
> 大部分端點需 `Authorization: Bearer <JWT>` header。SSO callback、`/lab/_authz`、`/code/` 自動接受 HttpOnly cookie `ai_hud_token`。
>
> Windows PowerShell 用 `curl.exe` 代替 `curl`（避免與 `Invoke-WebRequest` 衝突）。

---

## 認證 Auth

| 方法 | 路徑 | 用途 |
|---|---|---|
| POST | `/api/v1/auth/register` | 自助註冊（強制 `role=student`） |
| POST | `/api/v1/auth/login` | 本機登入，回 JWT + set HttpOnly cookie |
| POST | `/api/v1/auth/logout` | 清 `last_activity` + delete cookie |
| GET | `/api/v1/auth/me` | 取當前使用者 |
| PUT | `/api/v1/auth/me` | 變更 email / department（SSO 帳號改密碼會被拒絕）|
| GET | `/api/v1/auth/usage` | Token 使用量 |
| POST | `/api/v1/auth/forgot-password` | 寄重設密碼信 |

```bash
# 登入
curl -X POST http://localhost:8002/api/v1/auth/login -d "username=admin&password=xxx"
# 回應
# {"access_token": "eyJhbGciOi...", "token_type": "bearer"}

# 帶 token 取自己資訊
curl http://localhost:8002/api/v1/auth/me \
  -H "Authorization: Bearer eyJhbGciOi..."
```

---

## SSO

| 方法 | 路徑 | 用途 |
|---|---|---|
| GET | `/api/v1/sso/login` | 依 provider 跳轉登入頁（mock / cas） |
| GET | `/api/v1/sso/callback?ticket=…` | CAS / mock 的 ticket 回呼 |
| GET | `/api/v1/sso/mock-login` | Mock 模式 HTML 表單 |
| POST | `/api/v1/sso/mock-submit` | Mock 表單送出 |
| GET | `/api/v1/sso/oidc/login` | v3.1 跳學校 IdP（MCU 自建 OIDC auth.mcu.edu.tw） |
| GET | `/api/v1/sso/oidc/callback?code=…` | v2.1 OIDC 回呼，簽 JWT + cookie |
| GET | `/api/v1/sso/providers` | 列出當前啟用的 SSO（給前端決定按鈕） |
| GET | `/api/v1/sso/password-change-info` | 給設定頁用，依 auth_source 給不同 IdP 連結 |

---

## 訓練任務 Jobs

| 方法 | 路徑 | 用途 |
|---|---|---|
| POST | `/api/v1/jobs` | 提交新任務 |
| GET | `/api/v1/jobs` | 列出自己的任務 |
| GET | `/api/v1/jobs/{job_id}` | 任務狀態 |
| DELETE | `/api/v1/jobs/{job_id}` | 取消（僅 pending） |
| GET | `/api/v1/jobs/{job_id}/stream` | SSE 進度串流 |

```bash
# 提交 GPU 任務（aibase-runner extension 自動會用此 endpoint）
curl -X POST http://localhost:8002/api/v1/jobs \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "job_name": "LoRA fine-tune",
    "gpu_required": 1,
    "docker_image": "aibase/huggingface:2026-spring",
    "inline_code": "#!/bin/bash\npython3 -u train.py",
    "preferred_node": "gpu-node-01"
  }'
```

**進階欄位**：

| 欄位 | 說明 |
|---|---|
| `docker_image` | 7 個 aibase/* 學期鎖定 image，或自訂 |
| `inline_code` | shell script，以 `bash -eu` 執行 |
| `entry_args` | 非 Python 工具的入口指令陣列 |
| `preferred_node` | GPU 節點 ID，或 `null` / `"auto"` |

提交時自動注入該 user 的 secrets 為 env vars + 掛載 per-user volume (`/home/coder`) + shared models cache (`/opt/models` ro)。

---

## AI 助手 Chat

| 方法 | 路徑 | 用途 |
|---|---|---|
| POST | `/api/v1/chat/completions` | 對話（支援 SSE）|
| GET | `/api/v1/chat/history` | 取自己的對話歷史 |
| GET | `/api/v1/chat/sessions` | 列出會話 |

```bash
curl -X POST http://localhost:8002/api/v1/chat/completions \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "model_id": "gemini-1.5-pro",
    "messages": [{"role": "user", "content": "你好"}],
    "stream": true
  }'
```

**SSE 異常**：配額用完時 SSE 串流會送一個含 `error` 欄位的 JSON：
```
data: {"error": "Token quota exceeded", "details": "Your monthly quota is depleted."}
```
前端需攔截、不當作模型輸出顯示。

---

## 資料集 Datasets

| 方法 | 路徑 | 用途 |
|---|---|---|
| POST | `/api/v1/datasets/upload` | 上傳 `.csv` / `.jsonl` / `.zip`，自動分析回建議 hyperparams |

```bash
curl -X POST http://localhost:8002/api/v1/datasets/upload \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -F "file=@/path/to/data.csv"
# 回 { "dataset_path": "...", "suggested_config": {"epochs":5,"batch_size":16,...} }
```

---

## v2.0 Lab

| 方法 | 路徑 | 用途 |
|---|---|---|
| POST | `/api/v1/lab/start` | 啟動 code-server（5/min rate limit）|
| POST | `/api/v1/lab/stop` | 停止 session（檔案保留在 volume）|
| GET | `/api/v1/lab/status` | 狀態 + 配額 + 已注入 secrets (masked) |
| POST | `/api/v1/lab/heartbeat` | code-server extension 每 5 分鐘 |
| GET | `/api/v1/lab/nodes` | 列線上 GPU 節點（給 extension 選節點）|
| GET | `/api/v1/lab/_authz` | nginx auth_request 內部用，不對外 |

```bash
curl -X POST http://localhost:8002/api/v1/lab/start \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"base_image":"aibase/code-server:2026-spring"}'
# 回 { "status":"starting", "code_url":"/code/<uid>/?folder=...", "expires_at":"..." }
```

---

## v2.0 Secrets

> AES-256-GCM 加密，admin 也讀不到 plaintext。提交 GPU job 自動以 env vars 注入容器。

| 方法 | 路徑 | 用途 |
|---|---|---|
| GET | `/api/v1/secrets/` | 列出自己的 secrets（masked value）|
| PUT | `/api/v1/secrets/{name}` | 新增 / 更新（name 必須符合 `^[A-Za-z_][A-Za-z0-9_]*$`）|
| DELETE | `/api/v1/secrets/{name}` | 刪除 |

```bash
curl -X PUT http://localhost:8002/api/v1/secrets/HF_TOKEN \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"value": "hf_xxxxxxxxxxxxxxxxxxxxx"}'
```

---

## Admin

> 全部需 `role: admin` JWT，否則 403。

### 使用者管理

```bash
# 列出（支援 ?auth_source=local|sso_oidc|sso_mock 篩選）
curl http://localhost:8002/api/v1/admin/users?auth_source=local \
  -H "Authorization: Bearer ADMIN_TOKEN"

# 改使用者
curl -X PUT http://localhost:8002/api/v1/admin/users/<uid> \
  -H "Authorization: Bearer ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"email":"new@x.tw","role":"teacher","is_active":1,"tokens_limit":2000000}'

# Provision（寄信通知 + 回臨時密碼）
curl -X POST http://localhost:8002/api/v1/admin/users/provision \
  -H "Authorization: Bearer ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"username":"T1090099","email":"x@y.edu.tw","role":"student"}'

# 重設（重置密碼 + 歸零用量）
curl -X POST http://localhost:8002/api/v1/admin/users/<uid>/reset \
  -H "Authorization: Bearer ADMIN_TOKEN"

# 刪除（需 admin password 二次驗證）
curl -X POST http://localhost:8002/api/v1/admin/users/<uid>/delete \
  -H "Authorization: Bearer ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"admin_password":"..."}'

# 批次調 Token 額度
curl -X PUT http://localhost:8002/api/v1/admin/users/batch/tokens \
  -H "Authorization: Bearer ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"user_ids":["uid1","uid2"],"tokens_limit":10000000}'
```

### Lab 配額 / Storage / Secrets 監控

```bash
# 配額 grant（reason ≥ 5 字、寫 audit log）
POST /api/v1/admin/quota/grant
DELETE /api/v1/admin/quota/grant/{grant_id}
GET /api/v1/admin/quota/{user_id}

# Storage 生命週期（active → frozen → archived → pending_delete）
POST /api/v1/admin/storage/freeze
POST /api/v1/admin/storage/archive
POST /api/v1/admin/storage/restore
POST /api/v1/admin/storage/permanent-delete   # 需 admin_password
GET  /api/v1/admin/storage/states?state=frozen

# Lab sessions
GET  /api/v1/admin/lab/sessions
POST /api/v1/admin/lab/sessions/{user_id}/force-stop

# Secrets 監控（不可看 value）
GET    /api/v1/admin/secrets/{user_id}/names
DELETE /api/v1/admin/secrets/{user_id}/{name}
```

### Audit Log

```bash
curl "http://localhost:8002/api/v1/admin/audit?action=grant_quota&limit=50" \
  -H "Authorization: Bearer ADMIN_TOKEN"
# 回 [{admin_id, target_user, action, payload, timestamp, ip_address}, ...]
```

### Cluster / Analytics

```bash
GET /api/v1/admin/cluster/stats              # GPU 節點即時狀態
GET /api/v1/admin/analytics?department=...   # 學系 / 工具用量分布
```

---

## 公告 Announcements

```bash
# 列表（要登入）
GET /api/v1/announcements?limit=20

# 下載附件（要登入；草稿的附件一律 404）
GET /api/v1/announcements/{ann_id}/files/{file_id}
```

回應一律帶 `Content-Disposition: attachment` 與 `X-Content-Type-Options: nosniff`
—— 不讓瀏覽器內嵌開啟。

管理端（需 admin）：

```bash
POST   /api/v1/admin/announcements                     # 新增（含 title_en / body_en）
PUT    /api/v1/admin/announcements/{id}
DELETE /api/v1/admin/announcements/{id}                # ⚠ 附件檔案一併刪除
POST   /api/v1/admin/announcements/{id}/files          # 上傳附件（multipart，30/hour）
DELETE /api/v1/admin/announcements/{id}/files/{fid}
```

---

## 使用統計 Usage tracking

```bash
# 記一次「從平台跳去 MYAI」（要登入，回 204）
POST /api/v1/external-ai/visit
```

> ⚠ 這支**吞掉所有例外**。記不起來不可以讓使用者去不了 MYAI ——
> 統計比不上那件事。前端也是 fire-and-forget，不 await。

```bash
# 各分類的使用數據（需 admin）
GET /api/v1/admin/analytics?group_by=department|college|unit&days=30
GET /api/v1/admin/analytics?group_by=department&start=2026-08-01&end=2026-08-31
```

每一組回傳：`user_count` / `active_users_min` / `adoption` /
`myai_visits` / `myai_points` / `jobs` / `lab_gpu` / `lab_cpu` /
`share_*` / `group_en`，另外整體回一個 `tracking_since`。

> ⚠ `active_users_min` 是**下限**（跨表去重在 SQL 端做不到，取各項最大值）。
> ⚠ `adoption` 的分母是「平台上這一組的人數」，不是全系人數。
> ⚠ `group_en` 只在依**學系／學院**分組時有值；行政單位一律 `null`。

---

## Worker（給 GPU 節點用）

> 認證使用 `Authorization: Bearer <WORKER_API_TOKEN>`（與 user JWT 不同；token 在 `.env`）。

| 方法 | 路徑 | 用途 |
|---|---|---|
| POST | `/api/v1/worker/heartbeat` | 心跳 + GPU 使用率 |
| POST | `/api/v1/worker/take` | 領取 pending job |
| POST | `/api/v1/worker/jobs/{job_id}/update` | 回報進度 / log |
| GET | `/api/v1/worker/datasets/{job_id}` | 下載該任務的資料集壓縮檔（v3.6）|
| POST | `/api/v1/worker/jobs/{job_id}/artifact` | 回傳訓練產出（模型檔）（v3.6）|

**v3.6 資料集管理（使用者端）**

| 方法 | 路徑 | 用途 |
|---|---|---|
| POST | `/api/v1/datasets/upload` | 上傳；**回傳 `dataset_id`**（另回 `dataset_path` 供舊版相容）|
| GET | `/api/v1/datasets` | 列出自己的資料集，含用量與配額 |
| DELETE | `/api/v1/datasets/{id}` | 刪除（還有任務在用時回 **409**）|

**v3.6 自帶訓練程式**

送單時帶 `script_source`（單一 .py 的**原始碼字串**，不是檔名，上限 256 KB）。
平台會把它寫進那張單專屬的目錄並執行，其餘由使用者的程式決定。

給使用者程式的約定：

| | |
|---|---|
| `/workspace/dataset` | 這張單的資料（**唯讀**）；env `DATASET_DIR` |
| `/workspace/output` | 把模型存到這裡；env `OUTPUT_DIR` |
| env `EPOCHS` | 送單時填的訓練輪數（程式可以無視）|
| 印 `Epoch 3/10` | 進度條會跟著動 |
| 印 `@@METRIC {json}` | 結構化指標（`kind` 為 dataset / epoch / summary）|
| 印 `[錯誤] …` | 失敗時會成為使用者看到的錯誤訊息 |

⚠️ **`script_source` 與 `inline_code` 是不同的東西。** 後者是「程式實驗室模式」
的判準，會觸發同機閘門（要讀 `home_<uid>`）。自帶 .py 不需要實驗室的檔案，
用錯欄位會讓它被錯誤地擋在遠端節點外。

⚠️ **掛載範圍**：走資料集這條路（內建腳本／自帶 .py）的容器**只掛這張單自己的東西**。
在 v3.6 之前掛的是共享儲存的整個根目錄 —— 那表示任何訓練容器都讀得到
**每一位使用者的資料集與每一張任務的模型**（實測確認過）。
實驗室與自訂入口那條路仍是舊的寬掛載，見 worker.py 的說明。

⚠️ **送單請用 `dataset_id`，不要用 `dataset_path`。** 路徑由客戶端傳的話，
伺服器手上只有一個字串，無從判斷是誰的——原本正是這樣，**別人的路徑照收**。
現在兩種輸入都經 `crud.resolve_dataset_for_user` 驗證所有權，不是自己的一律 403。

⚠️ 刪除與「不是自己的」都回 404（不是 403）—— 分開回等於告訴對方哪些 id 存在。

**v3.6 模型檔下載（使用者端）**

| 方法 | 路徑 | 用途 |
|---|---|---|
| GET | `/api/v1/jobs/{job_id}/model` | 下載訓練出來的模型檔 |

權限沿用 `GET /jobs/{job_id}`（學生只能碰自己的，教師／管理員可看全部）。
`GET /jobs/{job_id}` 另回 `has_model` / `model_bytes`，前端靠它決定要不要顯示下載鈕。

⚠️ 這個端點要 `Authorization` header，**純 `<a href download>` 連結按下去會 401**
（瀏覽器導覽只帶 cookie）。前端要用 fetch 取回 blob 再存檔。

⚠️ 保留規則：每位使用者最多 `ARTIFACT_KEEP_PER_USER`（預設 10）個，上傳時就淘汰最舊的；
另有 `ARTIFACT_TTL_DAYS`（預設 30）由每日 03:00 掃描清除。逾期後下載會得到 **410**（不是 404）。

**v3.6 `/worker/take` 回傳的資料集欄位**

`dataset_path` 已移除——那是**服務層容器裡**的絕對路徑，worker 在別的容器、
甚至別台機器上，拿到那個字串沒有用。改成：

| 欄位 | 意義 |
|---|---|
| `has_dataset` | 這張單有沒有資料集；要檔案就 GET 上面那個端點 |
| `dataset_filename` | 原始檔名（只供顯示與判斷副檔名）|
| `builtin_task` | 用哪一支內建訓練腳本；`null` ＝ 使用者自己帶程式 |
| `shares_service_storage`（請求端）| worker 宣告自己與服務層同機，見部署文件 |

```bash
curl -X POST http://localhost:8002/api/v1/worker/heartbeat \
  -H "Authorization: Bearer WORKER_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"node_id":"gpu-node-01","available_gpus":["0","1"],"gpu_utilization":45.2}'
```

---

## System（管理者用）

| 方法 | 路徑 | 用途 |
|---|---|---|
| GET | `/health` | 健康檢查（無需認證）|
| GET | `/api/v1/system/files` | 列出系統設定檔（admin only）|
| GET | `/api/v1/system/files/{filename}` | 讀設定檔內容 |
| PUT | `/api/v1/system/files/{filename}` | 改設定檔內容 |

---

## 錯誤碼

| 狀態碼 | 說明 |
|---|---|
| 400 | 請求格式錯誤 / 使用者已存在 |
| 401 | 未認證 / Token 無效 / Cookie 過期 |
| 403 | 權限不足（非 admin 打 admin 端點）|
| 404 | 資源不存在（FastAPI `redirect_slashes=False`，注意 trailing slash）|
| 429 | Rate limit 超出（lab/start 5/min）或 Token / 每日配額用完 |
| 500 | 伺服器內部錯誤 |
| 503 | 服務不可用（通常上游 LLM gateway 掛了）|

---

完整 OpenAPI schema 隨時在 http://localhost:8002/docs 取得（Swagger UI）。
