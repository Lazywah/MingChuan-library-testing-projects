# GPU 伺服器初始化工具包 | GPU Server Setup Kit

本目錄包含 **資源層 GPU 伺服器** 的初始化工具，與服務層的 CodeSpace 獨立。

## 📦 檔案說明

| 檔案 | 說明 |
|------|------|
| `setup.sh` | 一鍵安裝腳本，在新的 GPU 機器上執行即可安裝所有必要工具 |
| `ssh-hardening.sh` | SSH 安全強化腳本（適用於外網部署的 GPU 伺服器） |

## 🚀 使用方式

### 1. 將本目錄複製到 GPU 伺服器

```bash
# 從服務層工作站複製到 GPU 伺服器
scp -r gpu-setup/ gpu_admin@192.168.1.100:~/
```

### 2. 執行初始化

```bash
# 在 GPU 伺服器上執行
cd ~/gpu-setup
sudo bash setup.sh
```

### 3. 重啟並驗證

```bash
sudo reboot
# 重啟後確認
nvidia-smi
python3 -c "import torch; print(torch.cuda.is_available())"
```

## 🔒 外網部署額外步驟

若 GPU 伺服器需暴露於外網，請額外執行安全強化：

```bash
sudo bash ssh-hardening.sh
```

> 詳細說明請參考：`docs/資源層-GPU部署/03-GPU伺服器部署指南.md`
