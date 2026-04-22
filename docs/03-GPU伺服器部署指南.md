# 03 - GPU 伺服器部署指南 | GPU Server Deployment Guide

## 概覽 | Overview

本平台的資源層包含 **2 台 GPU 伺服器**，透過 SSH 接收並執行訓練任務。

| 項目 | 規格 |
|------|------|
| CPU | AMD EPYC Genoa 32-core+ |
| RAM | 256GB ECC DDR5 |
| GPU | NVIDIA RTX 5090 (32GB GDDR7) × 2 |
| OS | Ubuntu 24.04 LTS |
| 網路 | 內網 (同子網) 或外網 (公網 IP / VPN) |

## Mock → 真實模式切換 | Mock to Real Mode Switch

### 當前狀態：Mock 模式

`.env` 中 `GPU_MOCK_MODE=true`，所有 GPU 操作由 `MockGPUClient` 模擬。

### 切換步驟 (GPU 就緒後)

1. **在 GPU 伺服器上安裝 NVIDIA 驅動**
```bash
# 在 GPU 伺服器上執行:
sudo apt update && sudo apt install -y nvidia-driver-550
sudo reboot
nvidia-smi  # 確認驅動安裝成功
```

2. **建立 SSH 金鑰對**
```bash
# 在服務層工作站上執行:
ssh-keygen -t rsa -b 4096 -f ~/.ssh/gpu_key -N ""
ssh-copy-id -i ~/.ssh/gpu_key.pub gpu_admin@192.168.1.100
ssh-copy-id -i ~/.ssh/gpu_key.pub gpu_admin@192.168.1.101
```

3. **測試 SSH 連線**
```bash
ssh -i ~/.ssh/gpu_key gpu_admin@192.168.1.100 nvidia-smi
ssh -i ~/.ssh/gpu_key gpu_admin@192.168.1.101 nvidia-smi
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
```bash
docker-compose restart job-scheduler
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

在 GPU 伺服器端編輯 `/etc/ssh/sshd_config`：

```bash
Port 2222                          # 改為非標準 Port，避免掃描攻擊
PermitRootLogin no                 # 禁止 root 直接登入
PasswordAuthentication no          # 只允許金鑰認證，禁用密碼
AllowUsers gpu_admin               # 只允許特定帳號連入
MaxAuthTries 3                     # 最多嘗試 3 次

# 套用設定
sudo systemctl restart sshd
```

防火牆白名單 (僅允許服務層 IP 連入)：

```bash
sudo ufw default deny incoming
sudo ufw allow from 您的服務層公網IP to any port 2222
sudo ufw enable
```

建議額外安裝 Fail2Ban 自動封鎖暴力攻擊：

```bash
sudo apt install -y fail2ban
sudo systemctl enable fail2ban
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

## 疑難排解 | Troubleshooting

### SSH 連線失敗

```bash
# 確認 SSH 服務運行中
ssh gpu_admin@192.168.1.100 echo "OK"

# 若使用非標準 Port
ssh -p 2222 gpu_admin@140.123.45.67 echo "OK"

# 確認金鑰權限
ls -la ~/.ssh/gpu_key  # 應為 600
```

### GPU 查詢失敗

```bash
# 在 GPU 伺服器上執行
nvidia-smi --query-gpu=index,utilization.gpu --format=csv
```

---

## 大規模叢集擴展 | Large-Scale Scaling (HPC)

當節點數量超過 5 台或需要更精細的資源配份時，建議從 SSH 模式切換為 **HPC 調度架構**：

1. **Slurm 調度器**：透過 `job-scheduler/app/gpu_client.py` 中的 `SlurmGPUClient` 介面進行對接，實現多節點任務衝突管理。
2. **NVIDIA DCGM 監控**：部署 DCGM Exporter 以獲取 GPU 健康與功率數據，支援大規模機房的異常攔截。

> [!NOTE]
> 關於上述進階組件的詳細規格與使用方法，請參考：
> [07-工具組件統整.md](file:///c:/Users/User/Desktop/school/大學/圖書館-AI基地/CodeSpace/docs/07-工具組件統整.md)

