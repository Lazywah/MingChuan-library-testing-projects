# 開發待處理事項 (Development Backlog)

> **說明**：此檔案記錄已知問題、技術債、功能擴充計畫。  
> 每個項目標示優先級 `[P1 緊急 / P2 重要 / P3 一般]` 與目前狀態。  
> 完成後請移至本文末的 **已完成** 區段並標記日期。

---

## 🔴 P1 緊急

_（目前無未完成的 P1 項目）_

---

## 🟠 P2 重要

### 系統設定 — 輸入框式管理介面
- **狀態**：待開發
- **背景**：已移除危險的「直接編輯原始設定檔」功能（`PUT /system/files/{filename}`），
  該功能允許管理員透過 textarea 覆蓋 `.env`，包含 `JWT_SECRET_KEY` 等關鍵憑證。
- **目標**：以個別輸入框取代，每個可調整的設定值有獨立 API 端點，
  並加入型別驗證與白名單限制。
- **需要建立的端點範例**：
  ```
  GET  /api/v1/system/config/scheduler   → 讀取排程器設定
  PATCH /api/v1/system/config/scheduler  → 更新排程器設定（允許欄位白名單）
  GET  /api/v1/system/config/token-quota → 讀取 Token 額度設定
  PATCH /api/v1/system/config/token-quota → 更新 Token 額度設定
  ```
- **前端**：`admin-ui/index.html` 已有佔位卡片（`<!-- 系統設定管理（開發中） -->`）
- **影響檔案**：`job-scheduler/app/routers/system.py`（已有空 router 待填充）、
  `admin-ui/index.html`、`admin-ui/admin.js`

---

### CORS 正式環境設定
- **狀態**：待設定（開發環境已修復）
- **問題**：目前 `CORS_ORIGINS` 未設定時，使用萬用字元 `*`，
  此時 `allow_credentials=False`（已修復，不再崩潰），
  但正式環境需填入明確來源才能讓 JWT Cookie 正常運作。
- **待辦**：上線前在 `docker-compose.yml` 設定：
  ```yaml
  CORS_ORIGINS: http://your-domain.com,http://your-domain.com:8888
  ```
- **影響檔案**：`docker-compose.yml`、`.env`

---

### SMTP 郵件服務設定
- **狀態**：待設定
- **問題**：目前 SMTP 設定已正確注釋（`# SMTP_PORT=587`），
  但尚未填入真實 SMTP 憑證，管理員配發帳號時仍需手動複製密碼。
- **待辦**：
  1. 取得 SMTP 服務（Gmail App Password 或其他 SMTP Relay）
  2. 在 `.env` 取消注釋並填入正確憑證：
     ```
     SMTP_SERVER=smtp.gmail.com
     SMTP_PORT=587
     SMTP_USERNAME=your-email@gmail.com
     SMTP_PASSWORD=your-app-password
     SMTP_FROM_EMAIL=your-email@gmail.com
     ```
  3. 設定完成後，`provision_user` 和 `reset_user_account` 回應中的
     `temp_password` 欄位將自動改為 `[已寄送至 Email]`，密碼不再出現在 API 回應中
- **影響檔案**：`.env`

---

## 🟡 P3 一般

### 系統架構圖 / 循序圖調整（diagrams）
- **狀態**：暫停（使用者決定先處理 GPU 工作站問題）
- **問題**：
  1. 系統架構圖（`docs/diagrams/`）的連線仍覆蓋部分物件方塊
  2. 循序圖的說明方格位置需要重新排版
- **影響檔案**：`docs/diagrams/` 下的 draw.io 檔案

---

### GPU Worker — `report_update` 僅在 2xx/4xx 停止重試
- **狀態**：已實作重試機制（`retries=3, backoff=2s`），
  但目前 4xx 回應（例如 job_id 不存在）不重試，此為預期行為。
- **後續考量**：若需要更細緻的重試策略（如區分 404 vs 401），
  可擴充 `report_update()` 的 `retries` 邏輯。
- **影響檔案**：`gpu-worker/worker.py`

---

### Token 月度重置的 TOCTOU（低風險）
- **狀態**：已部分修復
- **說明**：`try_deduct_tokens()` 的月度重置仍是非原子操作（先 flush 再 UPDATE），
  理論上在月份切換瞬間的極端併發下，可能有兩個請求同時重置。
  實務上此情形發生機率極低（月底/月初的瞬間），目前接受此風險。
- **若要完全解決**：需要 DB-level scheduled reset（例如 APScheduler cron job），
  而非在請求中即時重置。

---

### 系統架構與維護文件更新
- **狀態**：待更新
- **待辦**：`docs/00-系統架構與連線流程說明.md` 與 `docs/00-專案現況與開發進度.md`
  尚未反映以下重大架構變更：
  - Worker Pull Model（已取代 SSH Push Model）
  - `scheduler_policy.yaml` 移除靜態 `nodes:` 設定
  - 系統設定管理介面已停用，待改為輸入框方式
  - GPU Worker 的心跳自動上報機制

---

## ✅ 已完成

| 日期 | 項目 | 說明 |
|------|------|------|
| 2026-05-14 | **TOCTOU Token 競爭條件** | `crud.py` 新增 `try_deduct_tokens()`（原子 UPDATE），`jobs.py` 使用新函式，`chat.py` 串流結束後改用 SQL-level UPDATE |
| 2026-05-14 | **CORS wildcard + credentials 衝突** | `main.py` 新增 `_allow_credentials` 邏輯，萬用字元時強制關閉 credentials |
| 2026-05-14 | **`report_update()` 無重試** | `gpu-worker/worker.py` 加入最多 3 次重試 + 線性退避 |
| 2026-05-14 | **明文 `temp_password` 洩漏** | `admin.py` 兩處配發/重置端點：有設定 Email 時回傳遮蔽提示，無 Email 才回傳明文 |
| 2026-05-14 | **系統設定檔直接編輯移除** | 移除 `PUT /system/files/{filename}` 等 3 個端點，前端改為「開發中」佔位卡 |
| 2026-05-14 | **`.env` SMTP 格式錯誤** | `SMTP_PORT=#587` 導致 pydantic ValidationError，改為正確行首注釋 `# SMTP_PORT=587` |
| 2026-05-14 | **GPU Worker 3 項 Bug 修復** | `--gpus` 引號 bug、預設 URL 缺 `:8002`、容器無 GPU utility 權限 |
| 2026-05-14 | **`.env` 死變數清除** | 移除 SSH 時代殘留的 8 個無效環境變數 |
| 2026-05-14 | **`scheduler_policy.yaml` 靜態節點清除** | 移除過時的 `nodes:` IP 列表，改為心跳自動上報說明 |
| 2026-05-14 | **`gpu-worker/.env.example` 建立** | 提供部署範本，明確標示換主機唯一必改項為 `SERVICE_LAYER_URL` |
| 2026-05-14 | **`DEFAULT_IMAGE` CUDA 版本更新** | `pytorch:2.6.0-cuda12.4` → `pytorch:2.7.0-cuda12.8`（RTX 5090 / Blackwell sm_120 支援） |
| 2026-05-14 | **C-1: `/register` 速率限制** | `auth.py` 加入 `@limiter.limit("5/minute")`，端點改為 async |
| 2026-05-14 | **C-2: `/forgot-password` 速率限制** | `auth.py` 加入 `@limiter.limit("3/hour")`，端點改為 async |
| 2026-05-14 | **C-3: `/usage/increment` 開放問題** | 改為 `require_role("admin")` 限制；使用原子 `try_deduct_tokens()` 取代先加後查 |
| 2026-05-14 | **C-4: 自助註冊可設 `role=admin`** | `schemas.py` `UserCreate` 加入 `@field_validator("role")`，公開註冊只允許 student |
| 2026-05-14 | **C-5: `datasets.py` 路徑穿越** | 使用 `pathlib.Path(filename).name` + `os.path.realpath` 雙重檢查 |
| 2026-05-14 | **C-6: SSO mock `admin/admin`** | `sso_policy.yaml` 移除硬編碼管理員憑證 |
| 2026-05-14 | **C-7: `renderJobs` XSS** | `app.js` 結構用 innerHTML，`jobName/jobId/modelName` 改用 `textContent`；`onclick` 改 `addEventListener` |
| 2026-05-14 | **C-8: `createBubble` XSS** | `app.js` 用 `textContent` 取代 `innerHTML` 渲染對話泡泡 |
| 2026-05-14 | **C-9: SSE EventSource 無法攜帶 JWT** | `app.js` 改用 `fetch` + `ReadableStream`，支援 `Authorization` header |
| 2026-05-14 | **C-10: `fetchJobs` 取錯欄位** | `app.js` `data.items` → `data.jobs`，修正任務列表永遠空白 |
| 2026-05-14 | **C-11: forgot-password 顯示 undefined** | `auth.py` SMTP 未設定時回傳 `temp_password`；`app.js` 依回應動態切換顯示方式 |
| 2026-05-14 | **H-1: `scheduler.py` 硬編碼間隔** | 改為從 `SCHEDULER_POLICY.scheduling.job_check_interval_seconds` 讀取，預設 300 |
| 2026-05-14 | **H-2: 登入 log 洩漏 Email** | `auth.py` login log 移除 email 欄位，只記錄 username/role/IP |
| 2026-05-14 | **H-3: SSO mock 計時攻擊** | `auth.py` 改用 `hmac.compare_digest` 進行 mock 密碼比對 |
| 2026-05-14 | **H-4: datasets 無副檔名白名單** | `datasets.py` 加入 `ALLOWED_EXTENSIONS` 集合，拒絕可執行檔 |
| 2026-05-14 | **H-5: datasets 無個人儲存限制** | `datasets.py` 上傳前計算目錄大小，超過 2 GB 拒絕 |
| 2026-05-14 | **H-6: `take_job` 搶佔失敗後不嘗試下一筆** | `worker.py` 改為迴圈遍歷 pending_jobs，直到搶佔成功或清單用盡 |
| 2026-05-14 | **H-7: `gpu_id` 型別不一致** | `worker.py` 存入 DB 時 cast 為 int，回傳 Worker 時保留原始字串 |
| 2026-05-14 | **H-9: `requirements.txt` 含廢棄 `paramiko`** | 移除 `paramiko==3.4.0`（SSH 時代遺留，無任何 import 引用） |
| 2026-05-14 | **M-9: datasets 無速率限制** | `datasets.py` 加入 `@limiter.limit("10/hour")` |
| 2026-05-15 | **H-8: `ChatHistory.tokens_used` 未寫入** | `chat.py` 將 `estimated` 計算移至 `db.add()` 之前，assistant 行帶入完整往返 Token 用量 |
| 2026-05-15 | **個人數據分析（管理員介面）** | `admin.py` 新增 `GET /admin/users/{user_id}/analytics`；`admin-ui/index.html` + `admin.js` 新增個人分析 Modal（4 項統計卡、工具分布長條圖、Top-10 Sessions 表格）；同步修正 `handleAuthError` 未定義 bug |
