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

## 🚀 快速啟動 | Quick Start

### 前置條件 | Prerequisites
- Docker 24.x+
- Docker Compose 2.x+

### 啟動步驟 | Startup Steps

```bash
# 1. 複製環境設定 | Copy env config
cp .env.example .env

# 2. 啟動所有服務 | Start all services
docker-compose -f docker-compose.yml -f docker-compose.ai-models.yml up -d --build

# 3. 確認服務狀態 | Check status
docker-compose ps
```

### 存取服務 | Access Services

| 服務 Service | 入口路徑 URL | 說明 Description |
|-------------|------------|-------------------|
| **TRAIN_HUD** | http://localhost/train/ | **主要入口**：包含 AI 助手與任務管理 |
| Open WebUI | http://localhost/ | 輔助介面：原始對話介面 |
| API Docs | http://localhost:8002/docs | 後端 Swagger API 文件 |
| Gateway Health | http://localhost/health | 閘道器健康檢查 (Nginx) |

## ✍️ 內容開發與撰寫位置 | Where to Write
| 目標 Task | 檔案路徑 File Path | 說明 Note |
|-----------|--------------------|-----------|
| **修改 UI 視覺/邏輯** | `web-ui/` | 儀表板與 AI 助手的 HTML/CSS/JS |
| **調整 GPU/排程政策** | `job-scheduler/app/scheduler_policy.yaml` | 伺服器規格與併發限制 |
| **API 與聊天邏輯** | `job-scheduler/app/routers/` | 包含 `jobs.py` 與 `chat.py` |
| **更新說明文件** | `docs/` | 全套 Markdown 指南 |

## 📚 文檔 | Documentation

| 文件 | 說明 |
|------|------|
| [01-環境設置指南](docs/01-環境設置指南.md) | 啟動流程與存取 URL |
| [02-API使用手冊](docs/02-API使用手冊.md) | **新增**：AI 助手 API 說明 |
| [03-GPU伺服器部署指南](docs/03-GPU伺服器部署指南.md) | 實體伺服器連線 |
| [04-系統管理與維護](docs/04-系統管理與維護.md) | 備份、監控與維護 |
| [05-開發者指南](docs/05-開發者指南.md) | 模組擴展方式 |
| [06-專案架構與檔案說明](docs/06-專案架構與檔案說明.md) | **更新**：檔案結構說明 |

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
