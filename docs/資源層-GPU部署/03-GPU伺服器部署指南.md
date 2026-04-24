# 03 - GPU 伺服器部署指南 | GPU Server Deployment Guide

## 概覽 | Overview

本平台的資源層包含 **2 台 GPU 伺服器**，透過 SSH 接收並執行訓練任務。

| 項目 | 規格 |
|------|------|
| CPU | AMD EPYC Genoa 32-core+ |
| RAM | 256GB ECC DDR5 |
| GPU | NVIDIA RTX 5090 (32GB GDDR7) × 2 |
| OS | Windows 11 |
| 網路 | 內網 (同子網) 或外網 (公網 IP / VPN) |

## Mock → 真實模式切換 | Mock to Real Mode Switch

### 當前狀態：Mock 模式

`.env` 中 `GPU_MOCK_MODE=true`，所有 GPU 操作由 `MockGPUClient` 模擬。

### 切換步驟 (GPU 就緒後)

1. **在 GPU 伺服器上安裝 NVIDIA 驅動**
```powershell
# 請透過 NVIDIA 官網或 GeForce Experience 下載並安裝最新驅動
# 重新開機後，在 PowerShell 確認：
nvidia-smi  # 確認驅動安裝成功
```

2. **建立 SSH 金鑰對**
```powershell
# 在服務層工作站上執行:
ssh-keygen -t rsa -b 4096 -f "$env:USERPROFILE\.ssh\gpu_key" -N '""'
# Windows 原生沒有 ssh-copy-id，需手動將 gpu_key.pub 內容加入到 GPU 伺服器的 authorized_keys
```

3. **測試 SSH 連線**
```powershell
ssh -i "$env:USERPROFILE\.ssh\gpu_key" gpu_admin@192.168.1.100 nvidia-smi
ssh -i "$env:USERPROFILE\.ssh\gpu_key" gpu_admin@192.168.1.101 nvidia-smi
```

4. **修改 `scheduler_policy.yaml` 中的節點設定**

所有 GPU 節點的連線資訊統一定義在 `job-scheduler/app/scheduler_policy.yaml` 中：

```yaml
mock_mode: false    # 改為 false 以啟用真實連線

nodes:
  - id: "gpu-node-01"
    host: "192.168.1.100"       # 內網 IP
    port: 22                     # SSH Port
    username: "gpu_admin"
    ssh_key_path: "/root/.ssh/gpu_key"
```

5. **重啟服務**
```powershell
docker compose restart job-scheduler
```

---

## 🔧 GPU 伺服器必裝工具 | Required Tools on GPU Server

> [!IMPORTANT]
> 以下所有工具都必須安裝在**每一台 GPU 伺服器**上，服務層工作站不需要安裝這些。

### 必備項目 (Required)

| 工具 | 用途 | 安裝方式 |
|------|------|----------|
| **NVIDIA Driver** | GPU 硬體驅動，`nvidia-smi` 為系統偵測 GPU 的核心指令 | 手動下載安裝程式 |
| **CUDA Toolkit** | GPU 加速運算框架，PyTorch/TensorFlow 的底層依賴 | `winget install Nvidia.CUDA` |
| **Python 3.11+** | 訓練腳本執行環境 | `winget install Python.Python.3.11` |
| **OpenSSH Server** | 系統透過 SSH 遠端派發與執行訓練任務 | `Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0` |

### 深度學習框架 (擇一安裝)

| 框架 | 適用場景 | 安裝指令 |
|------|----------|----------|
| **PyTorch** | 學術研究、NLP、影像辨識（推薦） | `pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124` |
| **TensorFlow** | 生產部署、Keras 生態系 | `pip install tensorflow[and-cuda]` |

### 選配項目 (Optional)

| 工具 | 用途 | 安裝指令 |
|------|------|----------|
| **cuDNN** | CNN 加速庫（部分模型需要） | 從 NVIDIA 官網下載安裝 |
| **NFS/SMB Client** | 掛載服務層的集中式儲存空間 | 內建 SMB 客戶端 |

### 一鍵安裝腳本參考

```powershell
# ====== GPU 伺服器初始化腳本 ======
# 參考 \gpu-setup\setup.ps1
```

### 驗證檢查清單

安裝完成後，請逐項確認以下指令均能正常回應：

```powershell
# ✅ 驅動正常 → 應顯示 GPU 型號與記憶體
nvidia-smi

# ✅ CUDA 可用 → 應顯示 CUDA 版本
nvcc --version

# ✅ Python 正常 → 應顯示 Python 3.11+
python --version

# ✅ PyTorch 能偵測到 GPU → 應顯示 True 與 GPU 數量
python -c "import torch; print(torch.cuda.is_available(), torch.cuda.device_count())"

# ✅ SSH 服務運行中 → 應顯示 Running
Get-Service sshd
```

---

## 🌍 外網 GPU 部署 | WAN GPU Deployment

若 GPU 伺服器位於外部網路（雲端主機、校外機房、VPN），核心機制相同（SSH 連線），但需要額外注意安全性。

### 架構差異

```text
┌──────────────────┐        Internet          ┌──────────────────┐
│  服務層工作站      │ ── SSH (自訂 Port) ──→  │ 遠端 GPU Server   │
│  (Docker Host)    │                          │ 公網 140.x.x.x   │
└──────────────────┘                          └──────────────────┘
```

### 設定方式

在 `scheduler_policy.yaml` 中將 `host` 改為公網 IP 或域名，並設定非標準 `port`：

```yaml
nodes:
  - id: "gpu-cloud-01"
    host: "140.123.45.67"          # 公網 IP
    port: 2222                      # 非標準 SSH Port (安全考量)
    username: "gpu_admin"
    ssh_key_path: "/root/.ssh/gpu_key"

  - id: "gpu-cloud-02"
    host: "gpu2.school.edu.tw"     # 也可使用域名
    port: 2222
    username: "gpu_admin"
    ssh_key_path: "/root/.ssh/gpu_key"
```

### 🔒 外網安全強化 (必做)

> [!CAUTION]
> GPU 若暴露於外網，**以下措施為必要項目**，否則有被入侵的風險。

在 GPU 伺服器端執行 `gpu-setup\ssh-hardening.ps1` 腳本，或手動編輯 `C:\ProgramData\ssh\sshd_config`：

```text
Port 2222                          # 改為非標準 Port，避免掃描攻擊
PermitRootLogin no                 # 禁止 root/Administrator 直接登入
PasswordAuthentication no          # 只允許金鑰認證，禁用密碼
```

並於 PowerShell 重啟服務：
```powershell
Restart-Service sshd
```

防火牆白名單 (僅允許服務層 IP 連入)：
```powershell
New-NetFirewallRule -DisplayName "OpenSSH Server (2222)" -Direction Inbound -LocalPort 2222 -Protocol TCP -Action Allow
```

---

## 訓練腳本存放 | Training Script Location

訓練腳本應存放在服務層的集中式儲存器中，GPU 伺服器透過 NFS/SMB 掛載存取。

```text
儲存器目錄結構:
/storage/
├── scripts/     ← 訓練腳本
├── datasets/    ← 資料集
├── outputs/     ← 訓練產出 (模型權重)
└── logs/        ← 訓練日誌
```

---

## ✅ 配置完成後功能總覽 | Features After Configuration

### Mock 模式 vs 真實模式功能對照

| 功能 | Mock 模式 (開發) | 真實模式 (正式) |
|------|:-:|:-:|
| **使用者登入 / 註冊 / SSO** | ✅ | ✅ |
| **AI 助手對話 (串流)** | ✅ (模擬回音) | ✅ (接 Portkey/Ollama) |
| **Token 配額追蹤與扣減** | ✅ | ✅ |
| **任務提交與排隊** | ✅ | ✅ |
| **GPU 自動分配** | ✅ (模擬 2 張 GPU) | ✅ (查詢真實 nvidia-smi) |
| **訓練腳本遠端執行** | ✅ (模擬 15 秒完成) | ✅ (SSH 派發 `nohup python`) |
| **訓練進度即時追蹤** | ✅ (每 3 秒 +20%) | ✅ (解析 training.log 中的 %) |
| **模型產出路徑回傳** | ✅ (假路徑) | ✅ (真實 /workspace/outputs/) |
| **管理員全域監控** | ✅ | ✅ |
| **多節點負載分散** | ❌ (單一模擬節點) | ✅ (依 YAML 逐節點輪詢) |
| **GPU 健康狀態偵測** | ❌ | ✅ (nvidia-smi 利用率 < 10%) |

### 配置完成後解鎖的核心能力

完成 GPU 伺服器配置後，您的平台將具備以下**實際運算能力**：

#### 1. 🖥️ 訓練任務全自動派發
使用者在前端「運算任務」頁面提交任務後，系統會：
- 自動偵測哪台 GPU 伺服器有空閒資源
- 透過 SSH 遠端啟動 Python 訓練腳本
- 即時解析訓練日誌中的進度百分比並回傳前端
- 任務完成後自動標記為 `completed` 並記錄模型產出路徑

#### 2. 📊 多節點資源管理
- 排程器每 10 秒輪詢所有節點的 GPU 使用率
- 利用率 < 10% 的 GPU 自動納入可用池
- 支援最多 4 個任務同時運行（可在 `scheduler_policy.yaml` 調整）
- 任務依優先級排序，高優先級任務優先獲得 GPU

#### 3. 🤖 AI 助手 (需額外配置 Portkey/Ollama)
AI 助手功能**不依賴 GPU 伺服器**，而是透過 Portkey 網關連接外部 LLM API：
- 文字聊天、圖片辨識、知識搜尋等功能
- 若需本地模型推論，需額外部署 Ollama 服務

> [!NOTE]
> **AI 助手** 與 **GPU 訓練** 是兩個獨立模組。GPU 伺服器負責「訓練」，Portkey/Ollama 負責「對話」，兩者互不影響。

#### 4. 🔄 任務生命週期管理

```text
使用者提交任務
      ↓
  [pending] → 排程器偵測到空閒 GPU
      ↓
  [queued]  → 等待 GPU 分配中
      ↓
  [running] → SSH 遠端執行訓練中 (前端顯示進度條)
      ↓
  [completed] / [failed] → 結果回傳
```

---

## 疑難排解 | Troubleshooting

### SSH 連線失敗

```powershell
# 確認 SSH 服務運行中
ssh gpu_admin@192.168.1.100 echo "OK"

# 若使用非標準 Port
ssh -p 2222 gpu_admin@140.123.45.67 echo "OK"
```

### GPU 查詢失敗

```powershell
# 在 GPU 伺服器上執行
nvidia-smi --query-gpu=index,utilization.gpu --format=csv
```

### PyTorch 偵測不到 GPU

```powershell
# 確認 CUDA 版本與 PyTorch 版本匹配
python -c "import torch; print(torch.version.cuda)"
nvidia-smi  # 對比 CUDA Version 欄位

# 若版本不符，重新安裝對應版本的 PyTorch
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124
```

---

## 大規模叢集擴展 | Large-Scale Scaling (HPC)

當節點數量超過 5 台或需要更精細的資源配份時，建議從 SSH 模式切換為 **HPC 調度架構**：

1. **Slurm 調度器**：透過 `job-scheduler/app/gpu_client.py` 中的 `SlurmGPUClient` 介面進行對接，實現多節點任務衝突管理。
2. **NVIDIA DCGM 監控**：部署 DCGM Exporter 以獲取 GPU 健康與功率數據，支援大規模機房的異常攔截。

> [!NOTE]
> 關於上述進階組件的詳細規格與使用方法，請參考：
> [07-工具組件統整.md](file:///c:/Users/User/Desktop/school/大學/圖書館-AI基地/CodeSpace/docs/07-工具組件統整.md)

