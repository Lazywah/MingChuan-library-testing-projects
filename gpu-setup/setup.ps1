# ==============================================================================
# AI 訓練平台 - GPU 伺服器初始化腳本 (Windows)
# AI Training Platform - GPU Server Initialization Script
#
# 用途：在全新的 Windows 11 GPU 伺服器上一鍵安裝必要工具
# 執行：以系統管理員身分執行 .\setup.ps1
# ==============================================================================

$ErrorActionPreference = "Stop"

Write-Host "======================================"
Write-Host "  AI 平台 - GPU 伺服器初始化開始"
Write-Host "======================================"

# 檢查系統管理員權限
if (-NOT ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host "❌ 錯誤: 請以系統管理員身分 (Run as Administrator) 執行此腳本！" -ForegroundColor Red
    exit 1
}

# --------------------------------------------------
# 1. NVIDIA 驅動 + CUDA Toolkit
# --------------------------------------------------
Write-Host "[1/5] 檢查 NVIDIA 驅動與 CUDA Toolkit..."
if (Get-Command "nvcc" -ErrorAction SilentlyContinue) {
    Write-Host "✅ CUDA 已安裝" -ForegroundColor Green
} else {
    Write-Host "⚠️ CUDA 未安裝。嘗試使用 winget 安裝 CUDA Toolkit..." -ForegroundColor Yellow
    winget install -e --id Nvidia.CUDA --accept-package-agreements --accept-source-agreements
}

# --------------------------------------------------
# 2. Python 環境
# --------------------------------------------------
Write-Host "[2/5] 安裝 Python 環境..."
if (Get-Command "python" -ErrorAction SilentlyContinue) {
    Write-Host "✅ Python 已安裝" -ForegroundColor Green
} else {
    Write-Host "⏳ 正在使用 winget 安裝 Python 3.11..."
    winget install -e --id Python.Python.3.11 --accept-package-agreements --accept-source-agreements
}

# --------------------------------------------------
# 3. SSH 服務 (確保排程器可遠端連入)
# --------------------------------------------------
Write-Host "[3/5] 設定 OpenSSH Server..."
$sshStatus = Get-WindowsCapability -Online | Where-Object Name -like 'OpenSSH.Server*'
if ($sshStatus.State -ne 'Installed') {
    Write-Host "⏳ 正在安裝 OpenSSH.Server..."
    Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0 | Out-Null
}
Set-Service -Name sshd -StartupType 'Automatic'
Start-Service sshd
Write-Host "✅ OpenSSH 服務已啟動並設定為自動執行" -ForegroundColor Green

# --------------------------------------------------
# 4. 深度學習框架 (PyTorch)
# --------------------------------------------------
Write-Host "[4/5] 安裝 PyTorch (CUDA 12.4)..."
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124

# --------------------------------------------------
# 5. 安裝驗證
# --------------------------------------------------
Write-Host "[5/5] 驗證安裝結果..."
Write-Host ""
Write-Host "--- NVIDIA Driver ---"
if (Get-Command "nvidia-smi" -ErrorAction SilentlyContinue) {
    nvidia-smi
} else {
    Write-Host "⚠️ 找不到 nvidia-smi，請確認顯示卡驅動是否已安裝！" -ForegroundColor Red
}

Write-Host ""
Write-Host "--- CUDA Version ---"
if (Get-Command "nvcc" -ErrorAction SilentlyContinue) {
    nvcc --version
}

Write-Host ""
Write-Host "--- Python Version ---"
python --version

Write-Host ""
Write-Host "--- PyTorch GPU Check ---"
python -c "import torch; print(f'CUDA Available: {torch.cuda.is_available()}, GPU Count: {torch.cuda.device_count()}')"

Write-Host ""
Write-Host "--- SSH Status ---"
Get-Service sshd | Select-Object Status, Name, DisplayName

Write-Host ""
Write-Host "======================================"
Write-Host "  ✅ GPU 伺服器初始化完成！"
Write-Host ""
Write-Host "  下一步："
Write-Host "  1. 建議重新開機 (Restart-Computer)"
Write-Host "  2. 回服務層設定 scheduler_policy.yaml"
Write-Host "======================================"
