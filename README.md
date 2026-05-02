# AI 訓練平台 MVP | AI Training Platform MVP

> **ZH**: 整合了 AI 助手與 GPU 訓練任務排程的一站式平台，提供 LLM 推理與高效能運算管理。  
> **EN**: One-stop platform integrating AI Assistant and GPU training scheduling, offering LLM inference and HPC management.

---

## 🏗️ 架構概覽 | Architecture Overview

```
使用層 (Workstations)  →  Nginx (:80)  →  TRAIN_HUD (整合介面 /train/)
                                               ↓
                                         Job Scheduler (API Gateway /api/v1/)
                                               ↓
                                         Portkey (LLM Gateway) / GPU Servers
```

## 📸 介面預覽 | UI Preview

![AI Hub 四宮格導覽](file:///C:/Users/User/.gemini/antigravity/brain/fa44ed6b-0ae3-4d4a-b60a-c08d3f771e42/media__1775763352154.png)
*全新的 AI Hub 入口導覽大廳，提供直覺的分類服務*

---

## 🌟 特色功能 | Features
- **AI Hub 四宮格導覽**：直覺切換「AI模型、文書寫作、影音創作、生活翻譯」。
- **i18n 多國語言**：全系統支援中英文即時切換，包含 Aria 無障礙標籤同步。
- **高科技 HUD 視覺**：Cyberpunk 風格玻璃擬態 (Glassmorphism) 介面設計。
- **SSE 異常處理**：穩健的串流攔截機制，確保 Token 用盡時不會遺失對話進度。

---


## 🏗️ CodeSpace 專案檔案層級分類

整個專案依照部署位置分為三個主要層級：

### 1. 💻 工作站 (Workstation)
開發者本機或管理員操作端，主要用於代碼開發、測試與遠端部署。終端使用者則僅透過此層級的瀏覽器存取系統。
- `docs/`：專案文件與開發指南。
- `scripts/`：部署腳本（如 `deploy.sh`）。
- `tests/`：自動化測試與 E2E 測試腳本。
- `.env.example` / `README.md` / `.gitignore`：開發環境說明與配置範本。

### 2. ☁️ 服務層 (Service Layer)
核心伺服器 (Ubuntu)，負責 API 路由、排程管理、資料持久化與前端靜態資源託管。
- `docker-compose.yml` / `docker-compose.ai-models.yml`：微服務編排檔。
- `infrastructure/`：基礎設施配置（Nginx、SQL Schema）。
- `job-scheduler/`：FastAPI 後端核心服務（認證、排程、CRUD）。
- `web-ui/`：前端介面（HTML/CSS/JS）。
- `portkey/`：LLM 網關配置。
- `data/`：(運行時產生) SQLite 資料庫與持久化資料。
- `.env`：正式環境變數。

### 3. 🚀 GPU高階伺服器 (GPU High-End Server)
負責實際執行 AI 模型訓練與高耗能運算的資源節點 (Windows 11/Ubuntu)。
- `gpu-worker/`：GPU 伺服器專用的 Worker Agent 配置檔，提供一鍵式 Docker Compose 啟動環境。
- (訓練腳本由 GPU Worker 主動向服務層請求後於本地 Docker 容器中運行)

---

## 🛠️ 各層級部署步驟與工具

### 💻 工作站 (Workstation)
*   **初次部署**：
    1. 安裝 Git, Python 3, Docker (若需本機測試)。
    2. 執行 `git clone` 取得專案代碼。
    3. 複製 `.env.example` 為 `.env` 並填寫本機開發參數。
*   **往後部署 / 日常維護**：
    *   **工具**：VS Code, Git, `pytest` (執行 `tests/`)。
    *   **步驟**：開發新功能後，提交版本控制，或透過 `scripts/deploy.sh` 等工具將更新推送到服務層。

### ☁️ 服務層 (Service Layer)
*   **前置條件**：Docker 24.x+, Docker Compose 2.x+
*   **初次部署**：
    ```bash
    # 1. 複製環境設定
    cp .env.example .env
    
    # 2. 啟動所有服務 (Nginx, API, WebUI 等)
    docker compose -f docker-compose.yml -f docker-compose.ai-models.yml up -d --build
    
    # 3. 確認服務狀態
    docker compose ps
    ```
    **存取服務 URL**：
    - **TRAIN_HUD (主入口)**：`http://localhost/train/`
    - Open WebUI：`http://localhost/`
    - API Docs：`http://localhost:8002/docs`
    - Gateway Health：`http://localhost/health`
*   **往後部署 / 更新**：
    *   **工具**：Docker, `docker-compose`, `git pull`。
    *   **步驟**：取得最新代碼後，執行 `docker-compose up -d --build` 重建並重啟更新的容器。若僅更新前端 `web-ui`，通常無需重啟容器，Nginx 會直接讀取新檔案。

### 🚀 GPU高階伺服器 (GPU High-End Server)
*   **初次部署**：
    1. 準備一台安裝好 Windows 11 的 GPU 伺服器，並安裝好 NVIDIA 驅動、WSL 2 與 Docker Desktop。
    2. 將 `gpu-worker/` 目錄複製到該伺服器。
    3. 設定 `docker-compose.yml` 中的環境變數（主機 API 位址與 Token）。
    4. 執行 `docker-compose up -d` 啟動 Worker Agent 主動向主機領取任務。
*   **往後部署 / 擴展**：
    *   **工具**：Docker Compose。
    *   **步驟**：若需擴充算力新增節點，只需在新機器上複製 `gpu-worker` 資料夾並執行 `docker-compose up -d` 即可，主機端完全無需修改任何設定，即插即用。

---

## 📚 文檔導覽 | Documentation Index

依系統層級分類的文檔目錄，方便快速查閱。

| 子資料夾 | 文件 | 說明 |
|----------|------|------|
| **服務層-部署與維護/** | [01-環境設置指南](docs/服務層-部署與維護/01-環境設置指南.md) | 啟動流程與存取 URL |
| | [04-系統管理與維護](docs/服務層-部署與維護/04-系統管理與維護.md) | 備份、監控與 Token 手動重置 |
| | [09-SSO整合設定指南](docs/服務層-部署與維護/09-SSO整合設定指南.md) | SSO Mock/CAS 模式切換與設定 |
| | [10-正式上線轉換指南](docs/服務層-部署與維護/10-正式上線轉換指南.md) | Windows 測試 → Ubuntu 上線修改清單 |
| **資源層-GPU部署/** | [03-GPU伺服器部署指南](docs/資源層-GPU部署/03-GPU伺服器部署指南.md) | GPU 工具安裝、內外網部署與叢集擴展 |
| **API與開發/** | [02-API使用手冊](docs/API與開發/02-API使用手冊.md) | API 端點、參數與 SSE 異常說明 |
| | [05-開發者指南](docs/API與開發/05-開發者指南.md) | 模組擴展方式與 i18n 開發指引 |
| | [06-專案架構與檔案說明](docs/API與開發/06-專案架構與檔案說明.md) | 檔案結構與目錄對應說明 |
| | [07-工具組件統整](docs/API與開發/07-工具組件統整.md) | Portkey, Slurm, DCGM 等組件細節 |
| **使用者指南/** | [08-使用者操作手冊](docs/使用者指南/08-使用者操作手冊.md) | 針對終端使用者的介面操作指引 |

> **🗺️ 依角色快速導覽**
> - **首次部署者**：閱讀 `01-環境設置指南` → `03-GPU伺服器部署指南`
> - **系統管理員**：閱讀 `04-系統管理與維護` + `09-SSO整合設定指南`
> - **後端開發者**：閱讀 `05-開發者指南` + `02-API使用手冊` + `06-專案架構與檔案說明`

## 🧩 模組架構 | Module Architecture

| 模組 | 路徑 | 職責 |
|------|------|------|
| **Chat Router** | `.../routers/chat.py` | AI 助手串流代理 |
| **Jobs Router** | `.../routers/jobs.py` | 任務管理與狀態追蹤 |
| **Scheduler** | `.../scheduler.py` | 非同步任務排程核心 |
| **Auth** | `.../auth.py` | JWT 認證與權限控管 |

## 🧪 測試 | Testing

```bash
pip install -r tests/requirements.txt
python tests/end_to_end_test.py
```

## 📄 License
Internal use only.
