#!/bin/bash
# ==============================================================================
# AI 訓練平台 - GPU 伺服器初始化腳本
# AI Training Platform - GPU Server Initialization Script
#
# 用途：在全新的 GPU 伺服器上一鍵安裝所有必要工具
# 適用：Ubuntu 22.04 / 24.04 LTS
# 執行：sudo bash setup.sh
# ==============================================================================

set -e  # 任一指令失敗即停止

echo "======================================"
echo "  AI 平台 - GPU 伺服器初始化開始"
echo "======================================"

# --------------------------------------------------
# 1. 系統更新
# --------------------------------------------------
echo "[1/7] 系統更新中..."
sudo apt update && sudo apt upgrade -y

# --------------------------------------------------
# 2. NVIDIA 驅動 + CUDA Toolkit
# --------------------------------------------------
echo "[2/7] 安裝 NVIDIA Driver + CUDA Toolkit..."
sudo apt install -y nvidia-driver-550 nvidia-cuda-toolkit

# --------------------------------------------------
# 3. Python 環境
# --------------------------------------------------
echo "[3/7] 安裝 Python 3 環境..."
sudo apt install -y python3 python3-pip python3-venv

# --------------------------------------------------
# 4. SSH 服務 (確保排程器可遠端連入)
# --------------------------------------------------
echo "[4/7] 設定 OpenSSH Server..."
sudo apt install -y openssh-server
sudo systemctl enable sshd
sudo systemctl start sshd

# --------------------------------------------------
# 5. 深度學習框架 (PyTorch + CUDA 12.4)
# --------------------------------------------------
echo "[5/7] 安裝 PyTorch (CUDA 12.4)..."
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124

# --------------------------------------------------
# 6. 選配工具
# --------------------------------------------------
echo "[6/7] 安裝輔助工具 (NFS, tmux, htop, nvtop)..."
sudo apt install -y nfs-common tmux htop nvtop

# --------------------------------------------------
# 7. 安裝驗證
# --------------------------------------------------
echo "[7/7] 驗證安裝結果..."
echo ""
echo "--- NVIDIA Driver ---"
nvidia-smi
echo ""
echo "--- CUDA Version ---"
nvcc --version
echo ""
echo "--- Python Version ---"
python3 --version
echo ""
echo "--- PyTorch GPU Check ---"
python3 -c "import torch; print(f'CUDA Available: {torch.cuda.is_available()}, GPU Count: {torch.cuda.device_count()}')"
echo ""
echo "--- SSH Status ---"
sudo systemctl status sshd --no-pager
echo ""

echo "======================================"
echo "  ✅ GPU 伺服器初始化完成！"
echo ""
echo "  下一步："
echo "  1. 重啟機器: sudo reboot"
echo "  2. 確認 nvidia-smi 正常顯示"
echo "  3. 回服務層設定 scheduler_policy.yaml"
echo "======================================"
