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
| [02-API使用手冊](docs/02-API使用手冊.md) | **更新**：包含 SSE 異常 JSON 說明 |
| [03-GPU伺服器部署指南](docs/03-GPU伺服器部署指南.md) | **更新**：加入大規模叢集擴展 (Slurm) |
| [04-系統管理與維護](docs/04-系統管理與維護.md) | 備份、監控與 Token 手動重置 |
| [05-開發者指南](docs/05-開發者指南.md) | **更新**：模組擴展方式與 i18n 開發指引 |
| [06-專案架構與檔案說明](docs/06-專案架構與檔案說明.md) | 檔案結構與目錄對應說明 |
| [07-工具組件統整](docs/07-工具組件統整.md) | **新增**：Portkey, Slurm, DCGM 等組件細節 |
| [08-使用者操作手冊](docs/08-使用者操作手冊.md) | **新增**：針對終端使用者的介面操作指引 |

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
