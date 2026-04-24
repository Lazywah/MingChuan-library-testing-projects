# ==============================================================================
# AI 訓練平台 - GPU 伺服器 SSH 安全強化腳本 (Windows)
# 適用場景：GPU 伺服器暴露於外網時使用
# 執行：以系統管理員身分執行 .\ssh-hardening.ps1 [PortNumber]
# ==============================================================================

param (
    [int]$SshPort = 2222
)

$ErrorActionPreference = "Stop"

Write-Host "======================================"
Write-Host "  SSH 安全強化開始 (Port: $SshPort)"
Write-Host "======================================"

# 檢查系統管理員權限
if (-NOT ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host "❌ 錯誤: 請以系統管理員身分 (Run as Administrator) 執行此腳本！" -ForegroundColor Red
    exit 1
}

$sshdConfigPath = "$env:ProgramData\ssh\sshd_config"

if (-Not (Test-Path $sshdConfigPath)) {
    Write-Host "❌ 找不到 sshd_config，請確認已安裝 OpenSSH Server。" -ForegroundColor Red
    exit 1
}

# 備份原始設定
Copy-Item $sshdConfigPath "$sshdConfigPath.bak" -Force
Write-Host "[✓] 已備份 sshd_config 到 $sshdConfigPath.bak" -ForegroundColor Green

# 修改 SSH 設定
$config = Get-Content $sshdConfigPath

# 更新 Port
if ($config -match "^#?Port\s+\d+") {
    $config = $config -replace "^#?Port\s+\d+", "Port $SshPort"
} else {
    $config += "Port $SshPort"
}

# 關閉密碼登入 (強制使用金鑰)
if ($config -match "^#?PasswordAuthentication\s+(yes|no)") {
    $config = $config -replace "^#?PasswordAuthentication\s+(yes|no)", "PasswordAuthentication no"
} else {
    $config += "PasswordAuthentication no"
}

# 關閉 Root 登入 (Windows 中通常指 Administrator，這裡設定為 no 以符合標準安全策略)
if ($config -match "^#?PermitRootLogin\s+(yes|no)") {
    $config = $config -replace "^#?PermitRootLogin\s+(yes|no)", "PermitRootLogin no"
} else {
    $config += "PermitRootLogin no"
}

Set-Content -Path $sshdConfigPath -Value $config
Write-Host "[✓] SSH 設定已更新 (Port $SshPort, 停用密碼登入)" -ForegroundColor Green

# 重啟 SSH 服務
Restart-Service sshd
Write-Host "[✓] SSH 服務已重啟" -ForegroundColor Green

# 設定 Windows 防火牆
$ruleName = "OpenSSH Server (sshd) - Port $SshPort"
$existingRule = Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue

if ($existingRule) {
    Set-NetFirewallRule -DisplayName $ruleName -LocalPort $SshPort -Action Allow
} else {
    New-NetFirewallRule -DisplayName $ruleName -Direction Inbound -LocalPort $SshPort -Protocol TCP -Action Allow | Out-Null
}

Write-Host "[✓] 防火牆已更新 (允許 Inbound TCP $SshPort)" -ForegroundColor Green

Write-Host "======================================"
Write-Host "  ✅ SSH 安全強化完成！"
Write-Host ""
Write-Host "  SSH Port 已改為: $SshPort"
Write-Host "  連線指令: ssh -p $SshPort username@本機IP"
Write-Host ""
Write-Host "  ⚠️ 警告: 請確認您的 SSH 金鑰已部署到 authorized_keys！"
Write-Host "     路徑: `$env:USERPROFILE\.ssh\authorized_keys`"
Write-Host "     如果沒有設定金鑰，您將完全無法登入！"
Write-Host "======================================"
