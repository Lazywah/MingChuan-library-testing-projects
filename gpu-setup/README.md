# GPU 伺服器初始化工具包 | GPU Server Setup Kit

本目錄包含 **資源層 GPU 伺服器** 的初始化工具，與服務層的 CodeSpace 獨立。

## 📦 檔案說明

| 檔案 | 說明 |
|------|------|
| `setup.ps1` | 一鍵安裝腳本，在新的 Windows GPU 機器上執行即可安裝所有必要工具 |
| `ssh-hardening.ps1` | SSH 安全強化腳本（適用於外網部署的 GPU 伺服器） |

## 🚀 使用方式

### 1. 將本目錄複製到 GPU 伺服器

```powershell
# 從服務層工作站複製到 GPU 伺服器
scp -r gpu-setup\ gpu_admin@192.168.1.100:C:\Users\gpu_admin\Desktop\
```

### 2. 執行初始化

```powershell
# 在 GPU 伺服器上以系統管理員身分開啟 PowerShell 並執行

# ⚠️ 若首次執行 .ps1 被擋，請先解除執行限制：
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser

cd C:\Users\gpu_admin\Desktop\gpu-setup
.\setup.ps1
```

> ⚠️ **RTX 5090 使用者注意**：腳本已針對 Blackwell 架構調整，將自動安裝 CUDA 12.8+ 與 PyTorch `cu128` 版本。若 `winget` 中無合適的 CUDA 版本，腳本會引導您從 NVIDIA 官網手動下載。

### 3. 重啟並驗證

```powershell
Restart-Computer
# 重啟後確認
nvidia-smi
python -c "import torch; print(torch.cuda.is_available())"
```

## 🔒 外網部署額外步驟

若 GPU 伺服器需暴露於外網或需要鎖定連線來源，請額外執行安全強化（需系統管理員身分）：

```powershell
# 請將 192.168.1.50 替換為您服務層 (Ubuntu) 的真實 IP
.\ssh-hardening.ps1 -SshPort 2222 -ServiceLayerIP "192.168.1.50"
```

> 詳細說明請參考：`docs/資源層-GPU部署/03-GPU伺服器部署指南.md`
