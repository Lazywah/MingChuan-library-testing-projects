# 03 - GPU 伺服器部署指南 | GPU Server Deployment Guide

## 概覽 | Overview

本平台的資源層包含 **2 台 GPU 伺服器**，透過 SSH 接收並執行訓練任務。

| 項目 | 規格 |
|------|------|
| CPU | AMD EPYC Genoa 32-core+ |
| RAM | 256GB ECC DDR5 |
| GPU | NVIDIA RTX 5090 (32GB GDDR7) × 2 |
| OS | Ubuntu 24.04 LTS |
| 網路 | 僅內網 (與服務層同一子網) |

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

4. **修改 `.env`**
```env
GPU_MOCK_MODE=false
GPU_SERVER_1_HOST=192.168.1.100
GPU_SERVER_2_HOST=192.168.1.101
GPU_SERVER_USERNAME=gpu_admin
SSH_KEY_PATH=/root/.ssh/gpu_key
```

5. **重啟服務**
```bash
docker-compose restart job-scheduler
```

## 訓練腳本存放 | Training Script Location

訓練腳本應存放在服務層的集中式儲存器中，GPU 伺服器透過 NFS/SMB 掛載存取。

```
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

# 確認金鑰權限
ls -la ~/.ssh/gpu_key  # 應為 600
```

### GPU 查詢失敗
```bash
# 在 GPU 伺服器上執行
nvidia-smi --query-gpu=index,utilization.gpu --format=csv
```
