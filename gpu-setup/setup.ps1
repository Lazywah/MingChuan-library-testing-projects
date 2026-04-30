# ==============================================================================
# AI 訓練平台 - GPU 伺服器初始化腳本 (Windows 11 / RTX 50 系列)
# AI Training Platform - GPU Server Initialization Script
#
# 用途：在全新的 Windows 11 GPU 伺服器上一鍵安裝必要工具
# 適用：RTX 5090 / 5080 (Blackwell 架構, CUDA 12.8+)
#
# 執行方式 (以系統管理員身分開啟 PowerShell)：
#   Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
#   .\setup.ps1
#
# 或一次性繞過：
#   powershell -ExecutionPolicy Bypass -File .\setup.ps1
# ==============================================================================

$ErrorActionPreference = "Stop"

Write-Host "======================================"
Write-Host "  AI 平台 - GPU 伺服器初始化開始"
Write-Host "  適用：RTX 50 系列 (Blackwell / CUDA 12.8+)"
Write-Host "======================================"

# 檢查系統管理員權限
if (-NOT ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host "❌ 錯誤: 請以系統管理員身分 (Run as Administrator) 執行此腳本！" -ForegroundColor Red
    Write-Host ""
    Write-Host "💡 若遇到 .ps1 無法執行的問題，請先執行：" -ForegroundColor Yellow
    Write-Host "   Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser" -ForegroundColor Yellow
    exit 1
}

# ==============================================================================
# 輔助函式：刷新 PATH 環境變數 (安裝新工具後，讓當前 Session 立即找到)
# ==============================================================================
function Refresh-Path {
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
    Write-Host "   [✓] 已刷新 PATH 環境變數" -ForegroundColor DarkGray
}

# --------------------------------------------------
# 1. NVIDIA 驅動檢查
# --------------------------------------------------
Write-Host ""
Write-Host "[1/5] 檢查 NVIDIA 驅動..." 
if (Get-Command "nvidia-smi" -ErrorAction SilentlyContinue) {
    $driverInfo = nvidia-smi --query-gpu=driver_version --format=csv,noheader 2>$null
    Write-Host "✅ NVIDIA 驅動已安裝 (版本: $driverInfo)" -ForegroundColor Green
} else {
    Write-Host "❌ 找不到 nvidia-smi！請先從 NVIDIA 官網安裝最新版驅動 (≥570)。" -ForegroundColor Red
    Write-Host "   下載網址: https://www.nvidia.com/Download/index.aspx" -ForegroundColor Yellow
    Write-Host "   RTX 5090 需要 R570+ 版驅動才能正確辨識硬體。" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "   安裝完驅動後，請重新開機再執行本腳本。" -ForegroundColor Yellow
    exit 1
}

# --------------------------------------------------
# 2. CUDA Toolkit (RTX 5090 需要 12.8+)
# --------------------------------------------------
Write-Host ""
Write-Host "[2/5] 檢查 CUDA Toolkit (RTX 50 系列需要 ≥12.8)..."
$cudaOK = $false
if (Get-Command "nvcc" -ErrorAction SilentlyContinue) {
    $nvccOutput = nvcc --version 2>&1 | Select-String "release"
    Write-Host "✅ CUDA 已安裝: $nvccOutput" -ForegroundColor Green
    # 檢查版本是否 >= 12.8
    if ($nvccOutput -match "release (\d+)\.(\d+)") {
        $major = [int]$Matches[1]
        $minor = [int]$Matches[2]
        if ($major -gt 12 -or ($major -eq 12 -and $minor -ge 8)) {
            $cudaOK = $true
        } else {
            Write-Host "⚠️ 偵測到 CUDA $major.$minor，但 RTX 5090 需要 ≥12.8。" -ForegroundColor Yellow
            Write-Host "   請升級 CUDA Toolkit。" -ForegroundColor Yellow
        }
    }
} else {
    Write-Host "⚠️ CUDA 未安裝或不在 PATH 中。" -ForegroundColor Yellow
}

if (-not $cudaOK) {
    Write-Host ""
    Write-Host "📥 嘗試使用 winget 安裝 CUDA Toolkit..." -ForegroundColor Cyan
    $wingetResult = winget search "Nvidia.CUDA" 2>&1
    if ($wingetResult -match "12\.[89]|1[3-9]\.\d") {
        Write-Host "   找到符合版本，正在安裝..."
        winget install -e --id Nvidia.CUDA --accept-package-agreements --accept-source-agreements
        Refresh-Path
    } else {
        Write-Host "⚠️ winget 中可能沒有 CUDA 12.8+ 版本。" -ForegroundColor Yellow
        Write-Host "   請手動從 NVIDIA 官網下載安裝：" -ForegroundColor Yellow
        Write-Host "   https://developer.nvidia.com/cuda-downloads" -ForegroundColor Cyan
        Write-Host ""
        Write-Host "   安裝完成後，請確認以下路徑已加入系統 PATH：" -ForegroundColor Yellow
        Write-Host '   C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.8\bin' -ForegroundColor Yellow
        Write-Host ""
        Read-Host "   安裝完 CUDA 後按 Enter 繼續 (或按 Ctrl+C 中斷)"
        Refresh-Path
    }
}

# --------------------------------------------------
# 3. Python 環境
# --------------------------------------------------
Write-Host ""
Write-Host "[3/5] 安裝 Python 環境..."
if (Get-Command "python" -ErrorAction SilentlyContinue) {
    $pyVer = python --version 2>&1
    Write-Host "✅ $pyVer 已安裝" -ForegroundColor Green
} else {
    Write-Host "⏳ 正在使用 winget 安裝 Python 3.11..."
    winget install -e --id Python.Python.3.11 --accept-package-agreements --accept-source-agreements
    Refresh-Path
    
    # 再次檢查
    if (-not (Get-Command "python" -ErrorAction SilentlyContinue)) {
        Write-Host "⚠️ Python 安裝後仍無法找到。可能需要重啟終端或手動加入 PATH。" -ForegroundColor Yellow
        Write-Host "   預設安裝路徑：" -ForegroundColor Yellow
        Write-Host '   C:\Users\<使用者名稱>\AppData\Local\Programs\Python\Python311\' -ForegroundColor Yellow
        Read-Host "   請確認 PATH 後按 Enter 繼續"
        Refresh-Path
    }
}

# --------------------------------------------------
# 4. SSH 服務 (確保排程器可遠端連入)
# --------------------------------------------------
Write-Host ""
Write-Host "[4/5] 設定 OpenSSH Server..."
$sshStatus = Get-WindowsCapability -Online | Where-Object Name -like 'OpenSSH.Server*'
if ($sshStatus.State -ne 'Installed') {
    Write-Host "⏳ 正在安裝 OpenSSH.Server..."
    Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0 | Out-Null
}
Set-Service -Name sshd -StartupType 'Automatic'
Start-Service sshd
Write-Host "✅ OpenSSH 服務已啟動並設定為自動執行" -ForegroundColor Green

# 處理 Administrator 帳號的特殊 SSH 金鑰路徑
$currentUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
if ($currentUser -match "\\Administrator$" -or $currentUser -match "\\gpu_admin$") {
    $adminKeyFile = "$env:ProgramData\ssh\administrators_authorized_keys"
    $userKeyFile = "$env:USERPROFILE\.ssh\authorized_keys"

    Write-Host ""
    Write-Host "⚠️ 偵測到您使用的是管理員群組帳號 ($currentUser)" -ForegroundColor Yellow
    Write-Host "   Windows OpenSSH 對管理員群組有特殊的金鑰路徑規則：" -ForegroundColor Yellow
    Write-Host "   若帳號屬於 Administrators 群組，金鑰必須放在：" -ForegroundColor Yellow
    Write-Host "   $adminKeyFile" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "   若您已將公鑰放在 $userKeyFile，" -ForegroundColor Yellow
    Write-Host "   系統可能會忽略它。建議同時複製到上方路徑。" -ForegroundColor Yellow
    
    # 如果使用者已有 authorized_keys，自動複製到 admin 路徑
    if (Test-Path $userKeyFile) {
        Copy-Item $userKeyFile $adminKeyFile -Force -ErrorAction SilentlyContinue
        # 設定正確的 ACL 權限
        $acl = Get-Acl $adminKeyFile
        $acl.SetAccessRuleProtection($true, $false)
        $adminRule = New-Object System.Security.AccessControl.FileSystemAccessRule("Administrators", "FullControl", "Allow")
        $systemRule = New-Object System.Security.AccessControl.FileSystemAccessRule("SYSTEM", "FullControl", "Allow")
        $acl.AddAccessRule($adminRule)
        $acl.AddAccessRule($systemRule)
        Set-Acl $adminKeyFile $acl
        Write-Host "   [✓] 已自動複製金鑰至 $adminKeyFile" -ForegroundColor Green
    }
}

# --------------------------------------------------
# 5. 深度學習框架 (PyTorch for CUDA 12.8 / Blackwell)
# --------------------------------------------------
Write-Host ""
Write-Host "[5/5] 安裝 PyTorch (CUDA 12.8 - Blackwell 架構)..."
Write-Host "   ⚠️ RTX 5090 需要 PyTorch 2.7.0+ 搭配 CUDA 12.8 才能正確使用 GPU" -ForegroundColor Yellow
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu128

# --------------------------------------------------
# 驗證安裝結果
# --------------------------------------------------
Write-Host ""
Write-Host "======================================"
Write-Host "  驗證安裝結果"
Write-Host "======================================"

Write-Host ""
Write-Host "--- NVIDIA Driver ---"
if (Get-Command "nvidia-smi" -ErrorAction SilentlyContinue) {
    nvidia-smi
} else {
    Write-Host "⚠️ 找不到 nvidia-smi！" -ForegroundColor Red
}

Write-Host ""
Write-Host "--- CUDA Version ---"
if (Get-Command "nvcc" -ErrorAction SilentlyContinue) {
    nvcc --version
} else {
    Write-Host "⚠️ 找不到 nvcc，CUDA 可能未正確加入 PATH。" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "--- Python Version ---"
if (Get-Command "python" -ErrorAction SilentlyContinue) {
    python --version
} else {
    Write-Host "⚠️ 找不到 python！" -ForegroundColor Red
}

Write-Host ""
Write-Host "--- PyTorch GPU Check ---"
if (Get-Command "python" -ErrorAction SilentlyContinue) {
    python -c "import torch; print(f'PyTorch: {torch.__version__}'); print(f'CUDA Available: {torch.cuda.is_available()}'); print(f'GPU Count: {torch.cuda.device_count()}'); print(f'GPU Name: {torch.cuda.get_device_name(0) if torch.cuda.is_available() else \"N/A\"}')"
} else {
    Write-Host "⚠️ 無法執行 PyTorch 檢查 (Python 未安裝)" -ForegroundColor Red
}

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
Write-Host "  3. 執行 .\ssh-hardening.ps1 -ServiceLayerIP `"服務層IP`""
Write-Host "======================================"
