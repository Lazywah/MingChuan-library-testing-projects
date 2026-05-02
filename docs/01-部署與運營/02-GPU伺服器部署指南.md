# 03 - GPU 伺服器部署指南 | GPU Server Deployment Guide

## 概覽 | Overview

本平台的資源層包含 **2 台 GPU 伺服器**，透過 **Worker Agent (主動輪詢)** 架構，接收並執行訓練任務。

| 項目 | 規格 |
|------|------|
| CPU | AMD EPYC Genoa 32-core+ |
| RAM | 256GB ECC DDR5 |
| GPU | NVIDIA RTX 5090 (32GB GDDR7) × 2 |
| OS | Windows 11 |
| 網路 | 內網 (同子網) 或外網 (公網 IP / VPN) |

## 架構轉變聲明：一鍵式 Worker Agent (Pull 模式)

> [!IMPORTANT]
> **重要變更**：本平台的 GPU 伺服器部署已全面從「主機透過 SSH 遠端派發任務 (Push)」升級為「**Worker Agent 主動輪詢 (Pull)**」架構。
> 未來 GPU 伺服器上**不需設定 SSH 或防火牆**，所有訓練任務均由本地端的 Worker 透過 `docker-compose up -d` 啟動後，主動連線至主機領取任務，並動態啟動隔離的 Docker 容器來執行。這確保了伺服器環境的極致乾淨與跨網域的安全性。

---

## 🔧 GPU 伺服器必裝工具 | Required Tools on GPU Server

> [!IMPORTANT]
> 由於我們採用**純 Docker 架構**，您**不需**在伺服器上安裝 Python、CUDA Toolkit 或是深度學習套件。

### 必備基礎環境 (Required)

| 工具 | 用途 | 安裝方式 |
|------|------|----------|
| **NVIDIA Driver** (≥570) | GPU 硬體驅動，`nvidia-smi` 為系統偵測 GPU 的核心指令 | [NVIDIA 官網](https://www.nvidia.com/Download/index.aspx)手動下載 |
| **WSL 2** | Windows Subsystem for Linux，為 Docker 提供 Linux 核心與 GPU 直通支援 | PowerShell 執行 `wsl --install` 後重啟 |
| **Docker Desktop** | 容器化執行引擎 | [Docker 官網](https://www.docker.com/products/docker-desktop/)下載，並在設定中啟用 **Use the WSL 2 based engine** |

> [!WARNING]
> **RTX 5090 (Blackwell 架構) 使用者注意事項**：
> 雖然 Windows 宿主機不需要安裝 CUDA Toolkit，但您後續拉取 (Pull) 的 Docker 映像檔，其內部的 CUDA 版本必須 **≥12.8**（或至少 12.4 但需特別注意相容性），否則容器內的 PyTorch 將無法識別 RTX 5090。

---

## 🚀 從零開始建構：完整部署步驟 | From-Zero Deployment Steps

為了確保極致乾淨與隔離的訓練環境，請在一台**全新安裝 Windows 11** 的高階伺服器上，嚴格按照以下順序進行操作。

### Step 1: 基礎作業系統與驅動 (OS & Drivers)
1. **安裝 Windows 11**：完成系統初始設定。
2. **安裝 NVIDIA 驅動程式**：
   - 前往 [NVIDIA 官方驅動下載頁面](https://www.nvidia.com/Download/index.aspx)。
   - 選擇您的 GPU 型號 (例如 RTX 5090)，下載並安裝最新的 Game Ready 或 Studio 驅動程式（建議版本 ≥570）。
   - 安裝完成後**重新開機**。
   - 驗證：開啟 PowerShell，輸入 `nvidia-smi`，確認能正常顯示 GPU 型號與驅動版本。

### Step 2: 安裝 WSL 2 (Windows Subsystem for Linux)
Docker 依賴 WSL 2 才能在 Windows 上順暢執行 Linux 容器並直通 GPU。
1. 以**系統管理員身分**開啟 PowerShell。
2. 執行以下指令進行安裝：
   ```powershell
   wsl --install
   ```
3. 安裝完成後，**必須重新開機**。
4. 重啟後，系統可能會提示建立 Ubuntu 的預設使用者帳號，請依畫面指示完成設定。

### Step 3: 安裝與配置 Docker Desktop
1. 前往 [Docker 官方網站](https://www.docker.com/products/docker-desktop/) 下載 Docker Desktop for Windows。
2. 執行安裝程式，安裝過程中請務必**勾選「Use WSL 2 instead of Hyper-V (recommended)」**。
3. 安裝完成後啟動 Docker Desktop，進入右上方齒輪 **Settings**：
   - 選擇 **General**，確認有勾選 `Use the WSL 2 based engine`。
   - 選擇 **Resources > WSL Integration**，確認 `Enable integration with my default WSL distro` 已開啟。
   - 點擊 `Apply & restart`。

### Step 4: 複製 Worker 配置檔與設定
1. 在 GPU 伺服器上建立一個工作目錄（例如桌面上的 `gpu-worker` 資料夾）。
2. 將專案中的 `CodeSpace/gpu-worker` 資料夾內的所有內容複製過來，包含：
   - `docker-compose.yml`
   - `Dockerfile`
   - `requirements.txt`
   - `worker.py`
3. 以記事本開啟 `docker-compose.yml`，修改 `environment` 區塊以符合您的環境：
   ```yaml
       environment:
         - SERVICE_LAYER_URL=http://192.168.1.50:8002  # ⚠️ 務必改為您的主機 IP 與 Port
         - API_TOKEN=mcu-secret-token                  # ⚠️ 需與主機端設定的 Token 一致
         - NODE_ID=gpu-node-01                         # 命名這台伺服器 (例如 gpu-node-02)
         - STORAGE_MOUNT_PATH=C:\storage               # ⚠️ 設定共享儲存磁碟機路徑
   ```

### Step 5: 掛載共享儲存區 (Storage Mount)
由於訓練腳本與資料集存放於主機端，GPU 伺服器必須能夠存取這些檔案：
1. 請確保 `STORAGE_MOUNT_PATH` 指向的目錄（例如 `C:\storage`）已經正確掛載了主機的網路芳鄰 (SMB) 或是 NFS 目錄。
2. 該目錄內應包含 `/scripts`, `/datasets`, 與 `/outputs` 等子資料夾。

### Step 6: 一鍵啟動 Worker
1. 開啟 PowerShell，切換到 `gpu-worker` 資料夾所在位置：
   ```powershell
   cd C:\Users\YourUser\Desktop\gpu-worker
   ```
2. 啟動 Docker 容器：
   ```powershell
   docker-compose up -d --build
   ```
3. **驗證啟動與連線**：
   ```powershell
   docker-compose logs -f
   ```
   如果日誌中顯示 `Polling http://192.168.1.50:8002...`，代表 Worker 已經成功啟動，正自動與主機端索取最新的 AI 訓練任務了！
如果看到 `Polling http://192.168.1.50:8002...` 代表 Worker 已經成功啟動並開始向主機要任務了！

---

## 🌍 外網 GPU 部署 | WAN GPU Deployment

若 GPU 伺服器位於外部網路（雲端主機、校外機房、VPN），**您不需要做任何網路穿透或 SSH 設定**。

### 架構差異

```text
┌──────────────────┐        Internet          ┌──────────────────┐
│  服務層工作站      │ ←── API 請求 (Port 80) ──│ 遠端 GPU Server   │
│  (Docker Host)    │                          │ 公網 140.x.x.x   │
└──────────────────┘                          └──────────────────┘
```

> [!TIP]
> 因為是 GPU 伺服器**主動往外連線**主機，所以 GPU 伺服器本身可以放在 NAT 或防火牆後方，完全不用開放任何對外 Port，這是最安全的做法！唯一要注意的是主機端的 API 必須允許 GPU 伺服器的 IP 存取。

---

## ✅ 配置完成後功能總覽 | Features After Configuration

### 核心能力

完成上述配置後，您的平台將具備以下能力：

#### 1. 🖥️ 訓練任務全自動派發 (Docker 化)
使用者在前端提交任務後，主機會將任務放入 Queue 中。
- Worker 定期偵測本地端 GPU 使用率 (低於 10% 視為空閒)
- 若有空閒 GPU，Worker 領取任務，並在本地動態下達 `docker run` 指令啟動訓練容器
- 即時解析訓練日誌中的進度百分比並回報前端
- 任務完成後容器自動銷毀 (`--rm`)，保持環境乾淨

#### 2. 🔄 任務生命週期管理

```text
使用者提交任務
      ↓
  [pending] → 加入主機資料庫的佇列
      ↓
  [running] → Worker 領取任務並啟動 Docker 容器
      ↓
  [completed] / [failed] → Worker 回報結果與產出路徑
```

---

## 疑難排解 | Troubleshooting

### Worker 無法連線主機

```powershell
# 檢查網路是否通暢
curl http://192.168.1.50:8002/health

# 若無回應，請檢查主機端的防火牆是否開啟了對應的 Port (例如 8002)
```

### GPU 查詢失敗

```powershell
# 在 GPU 伺服器上執行，確保 NVIDIA 驅動正常運作
nvidia-smi --query-gpu=index,utilization.gpu --format=csv
```

### Docker 容器無法識別 GPU (PyTorch 無法載入)

```powershell
# 1. 確認 Docker Desktop 的 WSL2 整合是否有開啟。
# 2. 確認映像檔內部的 CUDA 版本是否過舊。若為 RTX 50 系列，建議使用包含 cu128 的映像檔。
# 測試使用官方較新版 PyTorch Image：
docker run --rm --gpus all pytorch/pytorch:2.6.0-cuda12.4-cudnn9-runtime python -c "import torch; print(torch.cuda.is_available(), torch.cuda.device_count())"

# 如果上述指令返回 True 和數量，代表透傳成功。
```

> [!TIP]
> **映像檔冷啟動提醒**：
> 首次派發任務時，如果 GPU 伺服器上沒有該 Docker 映像檔，Docker 會自動進行 Pull，這可能需要幾分鐘的時間。若有特定的底層 Image (例如 `pytorch/pytorch:latest`)，可以提前手動在 GPU 伺服器上執行 `docker pull` 以加速首次啟動。

---

## 大規模叢集擴展 | Large-Scale Scaling (HPC)

當節點數量超過 5 台或需要更精細的資源配份時，建議從原生的 Worker 架構升級為更成熟的 **K3s/Kubernetes 叢集** 或是 **Slurm 調度器** 結合 Docker 的方案。這部分超出了本指南的範圍，但我們保留了相容的擴充彈性。

