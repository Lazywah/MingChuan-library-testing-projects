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
| **系統設定**（v3.1）| 營運旋鈕即時調整：月額度/重置日/任務逾時/MYAI 同步間隔/RAG 參數/Lab 封存天數…（存 SystemConfig，**不需重啟**）|
| **GPU 節點**（v3.2）| 每台 GPU 的可排程時段、啟用開關、池別覆蓋、停派緩衝；狀態卡（離線/停用/時段外/閒置/執行中）|
| **Lab 管理 → 封存區**（v3.3）| 已刪除帳號的 Lab 資料（預設保留 30 天）：檢視 / 還原給指定使用者 / 立即銷毀 |
| **外部 AI → 即時使用**（v3.4）| MYAI 使用四象限（監控 + 稽核「有用量但人不在」）|

> 改 `.env` 等底層變數後，仍需 `docker compose restart job-scheduler` 才會生效。
> **例外**：上表「系統設定」頁的營運旋鈕存於 DB（SystemConfig），**改完即時生效、不必重啟**。

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
| **學生**忘記密碼（SSO 帳號）| 平台無法重設 → 請他到學校中央入口 <https://www1.mcu.edu.tw/ForgetPassword.aspx>（學號＋身分證字號）|
> **初次登入設定（v3.8）**：帳號 `onboarded_at` 為 NULL 時，登入後任一頁都會跳一次設定彈窗，
> 收**校區**與**學系（學生／教師）或行政單位（職員／管理員）**；訪客只問校區。
> **沒有關閉鈕、點背景也不關** —— 那兩項是分組統計的基礎資料。
>
> ⚠️ **只對新帳號跳**（擁有者裁定）：加欄位那次已把所有既有帳號一次標成已完成。
> 那個回填**寫在 `ALTER TABLE` 的同一個 try 裡**，所以只會執行一次 ——
> 拆到外面的話每次重啟都會把新帳號也標成已完成，於是彈窗永遠不出現而且看不出哪裡壞了。
>
> 要讓某個人重新設定：把他的 `users.onboarded_at` 設成 NULL。

> **身分與管理權限是兩件事（v3.8）**：`users.role` 是「你是誰」（student／teacher／staff／guest），
> `users.is_admin` 是「你能做什麼」。一個學生兼系統管理員設成 `role=student` + `is_admin=1` ——
> 合成一個欄位時他只能二選一，而選了管理員之後，數據頁的「依身分」會把這個學生算成管理員。
>
> 🔴 **使用者無法自行取得管理權限**，防線在型別層：使用者端的 `UserUpdate` schema
> **沒有 `is_admin` 也沒有 `role` 欄位**，`PUT /auth/me` 根本表達不出它；
> `crud.update_user` 是逐欄位明寫、不是 `setattr` 掃過去。
> ⚠️ 之後要加使用者可改的欄位時務必維持這個形狀 —— 改成通用的 setattr 迴圈就是開後門。
>
> 判定集中在 `auth.require_admin` **一支**（v3.8 之前有三份複製實作），
> 而且讀資料庫不是讀 JWT，**取消權限立刻生效**。
>
> ⚠️ `myai_sync` 的使用統計與 `_compute_online` **刻意仍看 `role == "admin"`** ——
> 那兩處講的是「純粹在開後台的系統操作者帳號」，不是權限判定。
> 改成 `is_admin` 會把學生兼管理員的**真實學生用量**也排除掉。
>
> 既有 `role='admin'` 的帳號在升級時自動拿到 `is_admin=1`，**`role` 不動**（那個帳號的
> 實際身分只有你知道）。管理端使用者編輯有「管理權限」勾選框可以分開設。

> **角色依信箱自動判定（v3.8）**：SSO **首次登入建帳號時**依信箱網域決定角色 ——
> `@me.mcu.edu.tw` → `student`、`@mail.mcu.edu.tw` → `teacher`、
> **其他任何可解析的網域 → `guest`（訪客）**、沒有可用地址 → `student`。
> `staff` 與 `admin` **一律由管理者手動指定**。既有帳號**不會**被重新判定。
>
> 訪客刻意**不用「已知公開信箱清單」**判定（那種清單會過期，漏掉一個 hotmail
> 就把人當成校內學生），而是反過來問「它是不是校內網域」。
> **`@mcu.edu.tw` 主網域算訪客，這是刻意的**（擁有者裁定 2026-08-27）：
> 校內身分只認 `me.mcu.edu.tw`（學生）與 `mail.mcu.edu.tw`（教職員）兩個子網域，
> 兩者都列在 `sso_policy.yaml` 的 `email_rules`。
> 之後若要把主網域或其他子網域納為校內，改那份 yaml 就好 —— **不要在程式裡特判**，
> 特判會讓「校內網域到底有哪些」變成兩個地方。
>
> 🔴 **要知道這個判定的依據是什麼**：MCU 的 userinfo 只回 `{"sub": 學號}`，**沒有 email**。
> 那個信箱是平台依 `sub` 的長相自己組出來的（8 碼純數字→學生網域、英文開頭→教職員網域）。
> 所以實際規則是「**sub 開頭是英文字母就給 teacher**」——
> 學號不是 8 碼純數字的學生會安靜地拿到 teacher。
>
> 因此每個帳號都記 `role_source`（`sso_email` 自動判 / `admin` 管理者設 / 空白 = v3.8 前建的）。
> **複查方式**：管理端使用者匯出勾「角色來源」欄，篩 `role_source=sso_email` 且 `role≠student`。
> 管理者一改角色就會轉成 `admin`，複查清單不會重複出現同一個人。

> **Lab 資料銷毀前的提醒（v3.8）**：刪帳號後 Lab volume 原地封存 `lab_archive_days`（預設 30）天，
> 逾期由每日 03:00 的背景任務真正銷毀（v3.3 就在跑）。v3.8 在銷毀前寄兩封信給
> **封存時快照下來的信箱**：剩 `lab_purge_first_days`（預設 30）天一封、剩
> `lab_purge_final_days`（預設 7）天一封。兩個都設 0 就完全不寄。
>
> ⚠️ **寄信時帳號已經不存在了**，所以信裡寫的是「聯絡管理員還原」而不是「請登入處理」——
> 還原是管理端專屬（`POST /admin/lab-archives/{volume}/restore`）。
>
> ⚠️ **沒有可用地址的封存會被跳過**（孤兒 volume 被 `--adopt` 收編時 email 是 NULL；
> SSO 推不出信箱時是 `@unknown`）。跳過**不會**標記成已提醒——之後補上地址仍會寄。
> 目前正式資料庫裡唯一那筆封存就是 email=NULL。

> **管理員告警信（v3.8）**：MYAI 自動同步失敗、退信回收失敗這兩件事以前只寫容器日誌，
> 沒有人會翻。現在會寄信給 admin「平台設定 → 寄信（SMTP）→ 管理員告警收件人」清單上的人。
> **收件人留空（預設）＝完全不寄。** 同一類告警有最短間隔（預設 6 小時），
> 避免壞掉的東西每輪寄一封把收件人洗到把規則設成全部丟垃圾桶。
> 告警到底出得去沒有，看寄信紀錄頁 `alert:*` 那幾筆的狀態——
> 收件人填錯的話會是 `blocked`／`refused`，而且**照樣計入節流**。

| **本機帳號**忘記密碼（老師/admin）| admin UI → 使用者管理 → 找該 user → Reset → 系統寄信（**需先設定 SMTP**，否則無法送達；v3.8 起可在 admin「平台設定 → 寄信（SMTP）」設，密碼仍在 `.env`）|
| Lab 卡住、要強制停 | admin UI → Lab Sessions → Force Stop（或 API `POST /admin/lab/sessions/<uid>/force-stop`）|
| 某學生濫用 Token | admin UI → 該 user → 調 `tokens_limit` |
| 學期末清空使用量 | admin UI → 批次選使用者 → Batch Reset Usage |
| 升級 base image | `docker build ...` 後重新 `docker push`；既有 cs container 不動，下次重啟才換 |
| 換 GPU 節點 | 新節點上 `./start-worker.sh up -d`（gpu-worker，會自動帶 --env-file），舊節點 `./start-worker.sh down` |
| 切換 SSO provider | 改 `sso_policy.yaml` → `docker compose restart job-scheduler` |
| 修補 cookie / nginx 設定 | 改 `infrastructure/nginx.conf` → `docker compose exec nginx nginx -s reload` |
| **停權某使用者**（懲罰）| admin UI → 該 user → `is_active=0`。**登入階段即擋下**並顯示明確訊息。⚠️ 對 SSO 使用者請用「停用」而非「刪除」——刪除不等於封鎖 |
| **刪除使用者** | admin UI → 刪除。Lab 資料會**封存 30 天**（可還原）；SSO 使用者下次登入會以新 uuid 重建 |
| **誤刪要救回 Lab 檔案** | admin UI →「Lab 管理」→ 封存清單 → 還原給指定使用者（逾期則已銷毀）|
| **GPU 機器要限時段開放** | admin UI →「GPU 節點」→ 編輯 → 設每週時段。到點只擋新派工，**執行中任務會跑完** |
| **暫停某台 GPU** | 同上，關掉「啟用」總開關 |
| **看誰正在用 MYAI** | admin UI →「外部 AI」→ 即時使用四象限。⚠️ 留意「**有用量但人不在**」那格＝可能共用機台未登出 |
| 清理孤兒 Lab volume | `docker exec ai-platform-scheduler python /app/scripts/cleanup_lab_volumes.py`（預設試跑；`--apply` 才刪）|
| 調整營運參數（額度/逾時/RAG/封存天數…）| admin UI →「管理介面」→ 系統設定（即時生效，不必重啟）|

---

## 下一步

- [`05-api-reference.md`](05-api-reference.md) — admin API 完整端點
- [`08-status-and-roadmap.md`](08-status-and-roadmap.md) — 已知議題（jobs polling、Lab 安全強化）
