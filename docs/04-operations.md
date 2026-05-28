# 04 — 維運 | Operations

日常維護：admin UI、備份、監控、配額、Token 重置、整合工具。

---

## 1. Admin UI（首選工具）

http://localhost:8888/ → 用 admin 帳號登入。**80% 維運工作從這裡做完，不需 SSH**。

| 分頁 | 用途 |
|---|---|
| **儀表板** | 叢集 GPU 即時狀態（Worker heartbeat、利用率、佇列長度）|
| **使用者管理** | 3-tab 分頁（本機 / 學校 SSO / Mock SSO）；Provision、重設密碼、批次調額度 |
| **全域任務** | 列出所有使用者的任務、強制取消、調優先級 |
| **模型管理** | 新增 / 編輯 / 刪除可用 LLM 模型 |
| **資料分析** | 使用量分布（學系、工具類別）|
| **設定檔管理** | 線上讀寫 `.env` / `docker-compose*.yml` / `*.yaml` |
| **審計記錄** | admin 行為 log（配額 grant、強制停 lab、permanent-delete）|

> 改 `.env` 等底層變數後，仍需 SSH `docker compose restart` 才會生效。

---

## 2. 資料庫備份

### 手動
```bash
cp data/ai_platform.db backups/ai_platform_$(date +%Y%m%d_%H%M%S).db
```

### 排程（Linux crontab）
```bash
# 每天 03:00 備份，保留 30 天
0 3 * * * cp /opt/ai-platform/data/ai_platform.db /opt/ai-platform/backups/daily_$(date +\%Y\%m\%d).db
0 4 * * * find /opt/ai-platform/backups/ -name 'daily_*.db' -mtime +30 -delete
```

### 完全重置（⚠️ 永久刪除）
```bash
docker compose stop job-scheduler
rm data/ai_platform.db*           # 含 -journal / -wal / -shm
docker compose up -d job-scheduler
```
啟動時自動建空表（依 `models.py`）。

---

## 3. 日誌

```bash
# 即時追蹤
docker compose logs -f job-scheduler
docker compose logs -f nginx

# 最近 100 行
docker compose logs --tail=100 job-scheduler

# 搜特定錯誤
docker compose logs job-scheduler 2>&1 | grep -iE "error|exception|traceback" | tail -30
```

---

## 4. 監控

```bash
docker compose ps                 # 容器狀態
docker stats                       # 即時 CPU / RAM
curl http://localhost/health       # API 健康
```

### Lab session 監控
```bash
docker ps --filter "label=aibase.role=code-server" \
  --format "table {{.Names}}\t{{.Status}}\t{{.Image}}"
```

每個 cs-`<user_id>` 容器對應一個 lab session；scheduler 每 60s 掃描閒置 30 分鐘的自動關閉。

---

## 5. Token 管理

Token 每月在 `TOKEN_RESET_DAY`（預設 1 號）自動重置為 0。手動操作：

### 批次歸零（推薦用 admin UI）
```bash
docker exec ai-platform-scheduler python -c "
import sqlite3
conn = sqlite3.connect('/data/ai_platform.db')
conn.execute('UPDATE token_usage SET tokens_used = 0')
conn.commit()
print('all reset')
"
```

### 調某使用者額度
```bash
docker exec ai-platform-scheduler python -c "
import sqlite3
conn = sqlite3.connect('/data/ai_platform.db')
conn.execute(\"UPDATE token_usage SET tokens_limit=10000000 WHERE user_id='USER_UUID'\")
conn.commit()
"
```

### Lab 每日配額（360 min）
若使用者測試遇到 `daily_limit_reached:360min`：
```bash
docker compose exec job-scheduler python -c "
from app.database import SessionLocal
from app import models
db = SessionLocal()
for r in db.query(models.UserSessionUsage).all():
    db.delete(r)
db.commit()
print('cleared')
"
```

---

## 6. 資料庫查閱

### 推薦工具
下載 `data/ai_platform.db` → 用 **DB Browser for SQLite** 開啟。

### 常用 CLI
```bash
# 列出所有使用者
docker exec ai-platform-scheduler python -c "
import sqlite3
c = sqlite3.connect('/data/ai_platform.db')
for r in c.execute('SELECT username, role, auth_source, is_active FROM users').fetchall():
    print(r)
"

# 最近 5 個任務
docker exec ai-platform-scheduler python -c "
import sqlite3
c = sqlite3.connect('/data/ai_platform.db')
for r in c.execute('SELECT job_id, status, progress FROM training_jobs ORDER BY created_at DESC LIMIT 5').fetchall():
    print(r)
"
```

---

## 7. 儲存空間

| 目錄 | 用途 | 預估 |
|---|---|---|
| `data/` | SQLite DB | < 100 MB |
| Docker volumes (`home_<user_id>`) | 每位使用者的 Lab 工作區 | 預設 10 GB / user (`disk_quota_gb`) |
| Docker volume `shared_models` | 預下載模型 cache | 0-200 GB |
| Open WebUI volume | LLM 對話紀錄 | 1-5 GB |
| Ollama volume | 本地模型權重 | 5-50 GB |

清理：
```bash
docker system prune -f         # 移除 unused 容器 / 網路 / image
docker volume prune -f         # 移除 dangling volume
```

### v2.0 Storage 生命週期（per-user volume）

四階段：`active` / `frozen` / `archived` / `pending_delete`。透過 admin UI 或 API 操作：
- **凍結**：停 lab session 但保留檔案
- **歸檔**：移到 HDD 區
- **還原**：從 frozen / archived 帶回 active
- **永久刪**：需 admin 密碼二次驗證、寫 audit log

詳見 [`05-api-reference.md`](05-api-reference.md) admin lab endpoints。

---

## 8. 整合工具總覽

| 工具 | 位置 | 用途 | 完成度 |
|---|---|---|---|
| **Open WebUI** | `docker-compose.ai-models.yml`，port 3000 | LLM 對話 UI（類 ChatGPT） | ✅ 100% |
| **Portkey** | 同上，port 8000 | LLM API gateway（分流 Anthropic / OpenAI / Google / Ollama）| ✅ 100% |
| **Ollama** | 同上，port 11434 | 本地推理引擎（GGUF 模型） | ✅ 100% |
| **Dartmouth Token Tracking** | Open WebUI functions | 對話即時顯示 Token 使用量 | ✅ 100% |
| **gpu-worker** | `gpu-worker/` Docker container | 每 5s pull 任務、隔離容器執行 | ✅ 100% |
| **code-server** | 動態建 `cs-<user_id>` container | VS Code in Browser | ✅ 100% |
| **JupyterHub** | 規劃中 | 替代方案 — 已被 v2.0 Lab 取代 | ⛔ 0% |
| **Slurm** | `gpu_client.py` 抽象介面 | 大叢集 HPC 排程 | 🟡 15% |
| **NVIDIA DCGM** | 規劃中 | GPU 監控 → Prometheus / Grafana | ⛔ 0% |

### LLM API key 取得

| 服務 | 申請網址 |
|---|---|
| Anthropic Claude | https://console.anthropic.com/ |
| OpenAI GPT | https://platform.openai.com/ |
| Google Gemini | https://aistudio.google.com/ |
| Microsoft Azure OpenAI | https://portal.azure.com/ |

填到 `docker-compose.ai-models.yml` 的 `portkey` 環境變數區。

---

## 9. 常用維運場景

| 場景 | 動作 |
|---|---|
| 學生忘記密碼 | admin UI → 使用者管理 → 找該 user → Reset → 系統寄信 |
| Lab 卡住、要強制停 | admin UI → Lab Sessions → Force Stop（或 API `POST /admin/lab/sessions/<uid>/force-stop`）|
| 某學生濫用 Token | admin UI → 該 user → 調 `tokens_limit` |
| 學期末清空使用量 | admin UI → 批次選使用者 → Batch Reset Usage |
| 升級 base image | `docker build ...` 後重新 `docker push`；既有 cs container 不動，下次重啟才換 |
| 換 GPU 節點 | 新節點上 `docker compose up -d`（gpu-worker），舊節點 `docker compose down` |
| 切換 SSO provider | 改 `sso_policy.yaml` → `docker compose restart job-scheduler` |
| 修補 cookie / nginx 設定 | 改 `infrastructure/nginx.conf` → `docker compose exec nginx nginx -s reload` |

---

## 下一步

- [`05-api-reference.md`](05-api-reference.md) — admin API 完整端點
- [`08-status-and-roadmap.md`](08-status-and-roadmap.md) — 已知議題（jobs polling、Lab 安全強化）
