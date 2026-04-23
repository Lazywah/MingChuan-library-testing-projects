# 📚 文檔總覽 | Documentation Index

本目錄依系統層級分類，方便快速查閱對應文件。

---

## 📂 目錄結構

```text
docs/
├── 服務層-部署與維護/          ← 服務層工作站的安裝、啟動、SSO 與日常維護
│   ├── 01-環境設置指南.md
│   ├── 04-系統管理與維護.md
│   └── 09-SSO整合設定指南.md
│
├── 資源層-GPU部署/            ← GPU 伺服器的硬體設定、工具安裝與外網部署
│   └── 03-GPU伺服器部署指南.md
│
├── API與開發/                 ← 開發者需要的 API 文檔、架構說明與擴展指引
│   ├── 02-API使用手冊.md
│   ├── 05-開發者指南.md
│   ├── 06-專案架構與檔案說明.md
│   └── 07-工具組件統整.md
│
└── 使用者指南/                ← 非技術使用者 (研究員/學生) 的操作指引
    └── 08-使用者操作手冊.md
```

---

## 🗺️ 依角色快速導覽

| 您的身份 | 建議閱讀 |
|---------|---------|
| **首次部署者** | `服務層-部署與維護/01-環境設置指南.md` → `資源層-GPU部署/03-GPU伺服器部署指南.md` |
| **系統管理員** | `服務層-部署與維護/04-系統管理與維護.md` + `09-SSO整合設定指南.md` |
| **後端開發者** | `API與開發/05-開發者指南.md` + `02-API使用手冊.md` + `06-專案架構與檔案說明.md` |
| **一般使用者** | `使用者指南/08-使用者操作手冊.md` |

---

## 📦 相關工具包

| 目錄 | 說明 |
|------|------|
| `gpu-setup/` | GPU 伺服器初始化腳本（獨立於 CodeSpace，可直接複製到 GPU 機器使用） |

---

## 🏗️ CodeSpace 專案檔案層級分類

整個專案依照部署位置分為三個主要層級：

### 1. 💻 工作站 (Local Workstation)
開發者本機或管理員操作端，主要用於代碼開發、測試與遠端部署。
- `docs/`：專案文件與開發指南。
- `scripts/`：部署腳本（如 `deploy.sh`）。
- `tests/`：自動化測試與 E2E 測試腳本。
- `.env.example` / `README.md` / `.gitignore`：開發環境說明與配置範本。

### 2. ☁️ 服務層 (Service Layer)
核心伺服器，負責 API 路由、排程管理、資料持久化與前端靜態資源託管。
- `docker-compose.yml` / `docker-compose.ai-models.yml`：微服務編排檔。
- `infrastructure/`：基礎設施配置（Nginx、SQL Schema）。
- `job-scheduler/`：FastAPI 後端核心服務（認證、排程、CRUD）。
- `web-ui/`：前端介面（HTML/CSS/JS）。
- `portkey/`：LLM 網關配置。
- `data/`：(運行時產生) SQLite 資料庫與持久化資料。
- `.env`：正式環境變數。

### 3. 🚀 高階 GPU (High-End GPU Layer)
負責實際執行 AI 模型訓練與高耗能運算的資源節點。
- `gpu-setup/`：GPU 伺服器初始化與 SSH 安全強化腳本。
- (訓練腳本通常由服務層透過 SSH 指令派發或共享目錄至此層運行)

---

## 🛠️ 各層級部署步驟與工具

### 💻 工作站 (Local Workstation)
*   **初次部署**：
    1. 安裝 Git, Python 3, Docker (若需本機測試)。
    2. 執行 `git clone` 取得專案代碼。
    3. 複製 `.env.example` 為 `.env` 並填寫本機開發參數。
*   **往後部署 / 日常維護**：
    *   **工具**：VS Code, Git, `pytest` (執行 `tests/`)。
    *   **步驟**：開發新功能後，提交版本控制，或透過 `scripts/deploy.sh` 等工具將更新推送到服務層。

### ☁️ 服務層 (Service Layer)
*   **初次部署**：
    1. 安裝 Docker 與 Docker Compose Plugin。
    2. 將專案代碼 (包含正確的 `.env` 與金鑰) 放置於伺服器上。
    3. 執行 `docker-compose up -d` 啟動所有服務 (Nginx, job-scheduler 等)。
*   **往後部署 / 更新**：
    *   **工具**：Docker, `docker-compose`, `git pull`。
    *   **步驟**：取得最新代碼後，執行 `docker-compose up -d --build` 重建並重啟更新的容器。若僅更新前端 `web-ui`，通常無需重啟容器，Nginx 會直接讀取新檔案。

### 🚀 高階 GPU (High-End GPU Layer)
*   **初次部署**：
    1. 準備一台安裝好 Ubuntu 的實體 GPU 伺服器。
    2. 將 `gpu-setup/` 工具包傳送至伺服器。
    3. 執行 `sudo bash setup.sh` 一鍵安裝 NVIDIA 驅動、CUDA、Python 與 OpenSSH。
    4. (若位於外網) 執行 `sudo bash ssh-hardening.sh` 強化連線安全。
    5. 將 GPU 節點的 IP 與金鑰登記至服務層的 `scheduler_policy.yaml`。
*   **往後部署 / 擴展**：
    *   **工具**：SSH, `gpu-setup` 腳本, `nvidia-smi`。
    *   **步驟**：若需擴充算力新增節點，對新機器重複初次部署步驟即可。GPU 層作為運算節點，本身不包含業務邏輯代碼，不需隨服務層頻繁更新。
