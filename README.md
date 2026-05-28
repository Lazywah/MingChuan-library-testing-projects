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
   ├── /train/   → web-ui (學生 / 老師)  │
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
#    http://localhost/train/       → 使用者介面
#    http://localhost:8888/         → admin 介面
#    http://localhost:8002/docs     → API Swagger
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
| [`06-user-guide.md`](docs/06-user-guide.md) | 使用者介面操作手冊 | 學生 / 老師 |
| [`07-development.md`](docs/07-development.md) | 開發指南、檔案結構、新增模組、i18n、方法學 | 開發者 |
| [`08-status-and-roadmap.md`](docs/08-status-and-roadmap.md) | 專案現況、已知 bug、v2.2 計畫 | 所有人 |
| [`archive/`](docs/archive/) | 歷史 plan / audit（v2.0 Lab、v2.1 SSO、AUDIT 等）| 想了解設計脈絡的人 |

---

## 核心功能（v2.1）

- **SSO 登入**：Microsoft Entra ID OIDC、Mock SSO、CAS（3 種 provider，yaml 切換）
- **AI 助手**：LLM 對話、Token 額度管理、SSE 串流
- **GPU 任務排程**：Pull 架構、Worker 主動領取、隔離容器執行
- **v2.0 Lab**：code-server (VS Code in Browser) + Secrets (AES-256-GCM) + per-user volume
- **管理員介面**：使用者管理（3-tab 依 auth_source）、配額、Storage 生命週期、Audit log

---

## License

Internal use only.
