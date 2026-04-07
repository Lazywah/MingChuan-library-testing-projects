# AI 訓練平台 MVP | AI Training Platform MVP

> **ZH**: 面向 10 位學生的 AI 訓練平台，提供 LLM 推理 (雲端 API) 與 GPU 訓練任務排程。  
> **EN**: AI training platform for 10 students, offering LLM inference (cloud APIs) and GPU training job scheduling.

---

## 🏗️ 架構概覽 | Architecture Overview

```
使用層 (10 workstations)  →  Nginx (:80)  →  Open WebUI (聊天)
                                           →  Portkey (LLM Gateway → Claude/Gemini/ChatGPT)
                                           →  Job Scheduler (Auth + 任務排程)
                                                    ↓
                                              SQLite (WAL)
                                                    ↓ SSH
資源層 (2 GPU servers)   ←  訓練腳本執行
```

## 🚀 快速啟動 | Quick Start

### 前置條件 | Prerequisites
- Docker 24.x+
- Docker Compose 2.x+

### 啟動步驟 | Startup Steps

```bash
# 1. 複製環境設定 | Copy env config
cp .env.example .env
# 然後修改 .env 中的設定值 | Then edit values in .env

# 2. 啟動所有服務 (包含核心與 AI 對話模塊) | Start all services
docker-compose -f docker-compose.yml -f docker-compose.ai-models.yml up -d --build

# 3. 確認服務狀態 | Check service status
docker-compose ps

# 4. 健康檢查 | Health check
curl http://localhost:8002/health
```

### 存取服務 | Access Services

| 服務 Service | URL | 說明 Description |
|-------------|-----|-------------------|
| Open WebUI | http://localhost/ | AI 聊天介面 (預設入口) \| Chat interface |
| TRAIN_HUD | http://localhost/train/ | 訓練管理面板 (方案 C) \| Training HUD |
| Job Scheduler API | http://localhost:8002/docs | Swagger API 文件 \| API docs |
| Nginx Gateway | http://localhost/health | 統一入口健康檢查 \| Gateway Health |

## ✍️ 內容開發與撰寫位置 | Where to Write
| 目標 Task | 檔案路徑 File Path | 說明 Note |
|-----------|--------------------|-----------|
| **修改 UI 視覺/語系** | `web-ui/` | 包含 html, css, js (i18n 字典) |
| **調整 GPU/排程政策** | `job-scheduler/app/scheduler_policy.yaml` | 增減伺服器與調整併發數 |
| **API 與後端邏輯** | `job-scheduler/app/` | FastAPI 路由與處理器 |
| **更新說明文件** | `docs/` | 所有的 Markdown 指南 |

## 📚 文檔 | Documentation

| 文件 | 說明 |
|------|------|
| [01-環境設置指南](docs/01-環境設置指南.md) | Docker、.env 設定 |
| [02-API使用手冊](docs/02-API使用手冊.md) | 所有 API 端點說明 |
| [03-GPU伺服器部署指南](docs/03-GPU伺服器部署指南.md) | SSH、Mock 切換 |
| [04-系統管理與維護](docs/04-系統管理與維護.md) | 備份、監控 |
| [05-開發者指南](docs/05-開發者指南.md) | 模組架構、擴展方式 |
| [06-專案架構與檔案說明](docs/06-專案架構與檔案說明.md) | 專案結構概覽與說明 |

## 🧩 模組架構 | Module Architecture

| 模組 | 檔案 | 職責 |
|------|------|------|
| Module 1 | `config.py` | 統一設定管理 |
| Module 2 | `database.py` | SQLite 連線 (WAL) |
| Module 3 | `models.py` | ORM 資料模型 (6 表) |
| Module 4 | `schemas.py` | 請求/回應驗證 |
| Module 5 | `crud.py` | 資料庫操作 |
| Module 6 | `auth.py` | JWT 認證 + RBAC |
| Module 7 | `gpu_client.py` | GPU 通訊 (Mock/SSH) |
| Module 8 | `scheduler.py` | 背景排程器 |
| Module 9 | `main.py` | 應用入口 |

## 🧪 測試 | Testing

```bash
pip install -r tests/requirements.txt
python tests/end_to_end_test.py
```

## 📄 License

Internal use only.
