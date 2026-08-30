# AI 訓練平台 | AI Training Platform

> 整合 SSO 登入、AI 助手、GPU 訓練任務排程、VS Code in Browser 的學校教學平台。
> One-stop platform for school AI labs — SSO auth, LLM chat, GPU jobs, in-browser IDE.

---

## 一張圖看懂

```
工作站 (Browser)                  外部 IdP (v2.1)
   ↓ HTTP                         Microsoft Entra ID
   ▼                                    ↑ OIDC
Nginx (:80, :8888)                       │
   ├── /V0/   → web-ui (學生 / 老師)  │
   ├── /code/<uid>/ → cs-<uid> (VS Code) │
   ├── /api/v1/  → job-scheduler (FastAPI)
   │               ├─ sso / lab / secrets / jobs / chat
   │               ├─ SQLite (users / jobs / lab_sessions)
   │               ├─ Portkey (LLM Gateway)
   │               └─ lab_manager → docker.sock (per-user code-server)
   └── :8888     → admin-ui (緊急救援、本機登入)

GPU Worker (Pull) ← /api/v1/worker/take ← 任務佇列
   └── docker run --gpus all  (per-job 容器、注入 secrets)
```

---

## 5 分鐘上手

```bash
# 1. 取得程式碼 + 環境變數
git clone <repo> CodeSpace
cd CodeSpace
python scripts/setup_env.py            # 互動式生 .env + gpu-worker/.env

# 2. 啟動服務層
docker compose up -d --build

# 3. 建第一個 admin（詳見 docs/01-quick-start.md §7）
docker compose exec job-scheduler python -c "..."

# 4. 開瀏覽器
#    http://localhost/               → 使用者介面（自動轉 /V1/）
#    http://localhost:8888/          → 管理端（自動轉 /V1/）
#    http://localhost:8002/docs      → API Swagger
```

詳細步驟見 **[`docs/01-quick-start.md`](docs/01-quick-start.md)**。

---

## 文件導覽

| 文件 | 內容 | 主要讀者 |
|---|---|---|
| [`01-quick-start.md`](docs/01-quick-start.md) | 從零開始 30 分鐘部署 + 建立第一個 admin | 新部署者 |
| [`02-architecture.md`](docs/02-architecture.md) | 三層架構、模組關係、mermaid 圖、認證流程 | 所有人 |
| [`03-deployment.md`](docs/03-deployment.md) | GPU 節點 / SSO / 正式上線 / 跨 OS 注意事項 | 部署者 |
| [`04-operations.md`](docs/04-operations.md) | 日常維運：備份、監控、Token 重置、Portkey/DCGM 工具 | 管理員 |
| [`05-api-reference.md`](docs/05-api-reference.md) | API endpoints / curl 範例 / 錯誤碼 | 後端開發 |
| [`06-user-guide.md`](docs/06-user-guide.md) | **使用者操作手冊** —— 怎麼登入、怎麼用 | 學生 / 老師 / 職員 |
| [`07-development.md`](docs/07-development.md) | 開發指南、檔案結構、新增模組、i18n、方法學 | 開發者 |
| [`08-status-and-roadmap.md`](docs/08-status-and-roadmap.md) | 專案現況、已知議題、計畫 | 所有人 |
| [`12-功能說明.md`](docs/12-功能說明.md) | **有什麼功能、各在哪、邊界在哪** | 所有人 |
| [`13-操作手冊-管理員.md`](docs/13-操作手冊-管理員.md) | **管理員操作手冊** —— 含上線前檢查清單 | 管理員 |
| [`design/`](docs/design/) | 介面設計紀錄（為什麼長這樣） | 想改介面的人 |
| [`archive/`](docs/archive/) | 歷史 plan / audit | 想了解設計脈絡的人 |

> 第一次接手這個平台：先看 **12-功能說明**（知道有什麼），
> 再看 **13-操作手冊-管理員**（知道怎麼操作），最後才是架構與開發。

---

## 核心功能

> 完整清單與邊界見 **[`docs/12-功能說明.md`](docs/12-功能說明.md)**。

- **SSO 登入** —— MCU 自建 OIDC（`auth.mcu.edu.tw`），首次登入自動建帳號
- **MYAI 整合** —— 導向學校採購的 AI 平台，管理點數、初始密碼、自動開通
- **GPU 任務排程** —— 純拉取式，worker 主動領工作，隔離容器執行
- **程式實驗室** —— 瀏覽器裡的 VS Code，多份存檔、可選 GPU、時間與磁碟限制
- **站內助手「小基」** —— RAG 客服（不用登入）+ 程式家教（登入後讀自己的檔案）
- **公告** —— 中英雙版、附件、內文網址自動變連結
- **管理端** —— 帳號、平台設定、問題回報、公告、**各系院單位的使用統計**

---

## License

Internal use only.
