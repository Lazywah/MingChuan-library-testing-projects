# ==============================================================================
# ZH: 平台健檢看門狗 / Platform health watchdog
# ==============================================================================
# ZH: 為什麼需要這支：2026-09-17 與 09-20 各發生一次 **Docker Desktop 自己退出**，
#     留下死掉的 socket（`%LOCALAPPDATA%\Docker\run\dockerInference` 等），
#     之後再怎麼按都起不來。第二次從 09-20 掛到 09-23 才被發現 ——
#     **三天沒有人知道平台是死的**，因為沒有任何東西會講話。
#
# ZH: 這支做三件事，順序不能顛倒：
#       1. 探活（打本機的 /health，不經過 DNS 與 TLS —— 那兩層自己也會壞，
#          用它們探活會把「憑證過期」誤判成「平台掛了」）
#       2. 不通就**修一次**：daemon 死了就清孤兒 socket 重啟 Docker Desktop；
#          daemon 活著只是容器沒起來就 `docker compose up -d`
#       3. 不管成功失敗都寫一行 log
#
# ZH: 🔴 **一次只修一次。** 用 `.watchdog-state.json` 記下上次嘗試的時間，
#     15 分鐘內不重複 —— 沒有這個節流的話，修不好的狀況會變成每 10 分鐘
#     殺一次 Docker、起一次 Docker，比原本的故障更糟。
#
# ZH: ⚠ 這支**只能在使用者已登入時跑**。Docker Desktop 是 GUI 程式，
#     Windows 上沒有 session 就起不來 —— 所以排程工作設成「只有登入時執行」
#     是正確的，不是妥協。
#
# 用法 / Usage:
#   powershell -ExecutionPolicy Bypass -File scripts\health_watchdog.ps1
#   ... -DryRun        只探活與判斷，**不動任何東西**（裝設時先用這個）
#   ... -Simulate      假裝探活失敗，驗證修復那一段會走到哪（配 -DryRun 用）
#   ... -Install       註冊 Windows 排程工作（登入時 + 每 10 分鐘）
#   ... -Uninstall     移除排程工作
# ==============================================================================
[CmdletBinding()]
param(
    [switch]$DryRun,
    [switch]$Simulate,
    [switch]$Install,
    [switch]$Uninstall,
    [switch]$Loop,
    [switch]$InstallStartup,
    [switch]$UninstallStartup
)

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.Encoding]::UTF8

$RepoRoot   = Split-Path -Parent $PSScriptRoot
$LogFile    = Join-Path $RepoRoot 'data\watchdog.log'
$StateFile  = Join-Path $RepoRoot 'data\.watchdog-state.json'
$TaskName   = 'MCU AI Base health watchdog'
$HealthUrl  = 'http://localhost:8002/health'
$DockerExe  = 'C:\Program Files\Docker\Docker\Docker Desktop.exe'
# ZH: 兩次修復嘗試之間至少要隔這麼久（見檔頭的節流說明）
$CooldownMinutes = 15

function Write-Log([string]$Level, [string]$Message) {
    $line = '{0} [{1}] {2}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Level, $Message
    try {
        $dir = Split-Path -Parent $LogFile
        if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
        # ZH: log 自己也要有上限 —— 每 10 分鐘一行，一年約 5 萬行。
        #     超過 5000 行就砍掉前半（留後面的，出事時要看的是最近的）。
        if ((Test-Path $LogFile) -and ((Get-Item $LogFile).Length -gt 500KB)) {
            $keep = Get-Content $LogFile -Tail 2000
            Set-Content -Path $LogFile -Value $keep -Encoding UTF8
        }
        Add-Content -Path $LogFile -Value $line -Encoding UTF8
    } catch { }
    Write-Host $line
}

function Test-Platform {
    <# ZH: 平台活著嗎。只看本機的 /health —— 不經 DNS/TLS（理由見檔頭）。#>
    try {
        $r = Invoke-WebRequest -Uri $HealthUrl -TimeoutSec 10 -UseBasicParsing
        return ($r.StatusCode -eq 200)
    } catch {
        return $false
    }
}

function Test-DockerDaemon {
    try {
        $null = & docker version --format '{{.Server.Version}}' 2>$null
        return ($LASTEXITCODE -eq 0)
    } catch {
        return $false
    }
}

function Get-LastAttempt {
    if (-not (Test-Path $StateFile)) { return $null }
    try { return [datetime]((Get-Content $StateFile -Raw | ConvertFrom-Json).lastAttempt) }
    catch { return $null }
}

function Set-LastAttempt {
    if ($DryRun) { return }
    try {
        @{ lastAttempt = (Get-Date).ToString('o') } | ConvertTo-Json |
            Set-Content -Path $StateFile -Encoding UTF8
    } catch { }
}

function Repair-Docker {
    <# ZH: 清孤兒 socket 並重啟 Docker Desktop。這就是 09-17 / 09-20 兩次
        人工做的那套動作，寫成腳本避免下次又要從記憶裡挖。#>
    Write-Log 'WARN' 'Docker daemon 沒有回應 —— 清孤兒 socket 並重啟 Docker Desktop'
    if ($DryRun) { Write-Log 'INFO' '（DryRun：這裡會殺掉 docker 程序、改名兩個目錄、重啟 Docker Desktop）'; return }

    Get-Process | Where-Object { $_.Name -like '*docker*' -or $_.Name -like 'com.docker*' } |
        ForEach-Object { try { Stop-Process -Id $_.Id -Force -ErrorAction Stop } catch { } }
    Start-Sleep -Seconds 8

    $stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
    foreach ($d in @("$env:LOCALAPPDATA\Docker\run", "$env:LOCALAPPDATA\docker-secrets-engine")) {
        if (Test-Path $d) {
            try {
                Rename-Item -Path $d -NewName "$(Split-Path $d -Leaf).broken-$stamp" -ErrorAction Stop
                Write-Log 'INFO' "已改名孤兒目錄：$d"
            } catch {
                Write-Log 'ERROR' "改名失敗 $d ：$($_.Exception.Message)"
            }
        }
    }

    Start-Process $DockerExe
    Write-Log 'INFO' 'Docker Desktop 已重新啟動，等待 daemon…'
    for ($i = 0; $i -lt 36; $i++) {
        Start-Sleep -Seconds 5
        if (Test-DockerDaemon) { Write-Log 'INFO' "daemon 回來了（約 $($i*5) 秒）"; return }
    }
    Write-Log 'ERROR' 'daemon 等了 3 分鐘還是沒起來 —— 需要人工處理'
}

function Start-Stack {
    <# ZH: 起服務。AI 模型那組要先起（知識庫與 MYAI 的 LLM 都靠它），
        再起主服務 —— 順序反過來時知識庫會是空的。#>
    Write-Log 'INFO' '啟動服務堆疊（先 AI models，再主服務）'
    if ($DryRun) { Write-Log 'INFO' '（DryRun：這裡會跑兩次 docker compose up -d）'; return }
    Push-Location $RepoRoot
    try {
        & docker compose -f docker-compose.ai-models.yml -f docker-compose.ai-models.gpu.yml up -d 2>&1 |
            Select-Object -Last 2 | ForEach-Object { Write-Log 'INFO' "  $_" }
        & docker compose up -d 2>&1 |
            Select-Object -Last 3 | ForEach-Object { Write-Log 'INFO' "  $_" }
    } catch {
        Write-Log 'ERROR' "compose up 失敗：$($_.Exception.Message)"
    } finally {
        Pop-Location
    }
}

# ── 開機自動執行（免提權的備案）──────────────────────────────────────────
# ZH: `-Install` 用的是 Windows 排程工作，**需要一次 UAC**。不想提權時用這一條：
#     在「啟動」資料夾放一個捷徑，登入後自己跑一個 `-Loop` 的常駐迴圈。
#
# ZH: 兩者的差別要知道，不要以為是同一件事：
#       排程工作   Windows 會管它（跑掛了會依設定重試、有執行歷程可查）
#       啟動捷徑   沒有人管它。迴圈的行程被關掉就沒有了，而且不會有人知道
#     所以**排程工作是比較好的那個**；這條是「至少有東西在看」的退路。
if ($InstallStartup) {
    $startup = [Environment]::GetFolderPath('Startup')
    $lnk = Join-Path $startup 'MCU AI Base watchdog.lnk'
    $sh = New-Object -ComObject WScript.Shell
    $s = $sh.CreateShortcut($lnk)
    $s.TargetPath = 'powershell.exe'
    $s.Arguments = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$PSCommandPath`" -Loop"
    $s.WorkingDirectory = $RepoRoot
    $s.Description = 'MCU AI Base 平台健檢看門狗（每 10 分鐘）'
    $s.Save()
    Write-Log 'INFO' "已在啟動資料夾放上捷徑：$lnk"
    return
}
if ($UninstallStartup) {
    $lnk = Join-Path ([Environment]::GetFolderPath('Startup')) 'MCU AI Base watchdog.lnk'
    if (Test-Path $lnk) { Remove-Item $lnk -Force; Write-Log 'INFO' "已移除啟動捷徑：$lnk" }
    else { Write-Log 'INFO' '啟動資料夾裡沒有捷徑' }
    return
}

# ── 註冊 / 移除排程工作 ───────────────────────────────────────────────────
if ($Install) {
    $action  = New-ScheduledTaskAction -Execute 'powershell.exe' `
        -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$PSCommandPath`""
    # ZH: 登入時跑一次（開機後 Docker Desktop 也才剛起來，給它 3 分鐘），
    #     之後每 10 分鐘一次。RepetitionDuration 給 (almost) 永久。
    $atLogon = New-ScheduledTaskTrigger -AtLogOn
    $atLogon.Delay = 'PT3M'
    $every   = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) `
        -RepetitionInterval (New-TimeSpan -Minutes 10)
    # ZH: 🔴 只有登入時執行 —— Docker Desktop 是 GUI 程式，沒有 session 起不來。
    $principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive
    $settings  = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries -StartWhenAvailable `
        -ExecutionTimeLimit (New-TimeSpan -Minutes 10) `
        -MultipleInstances IgnoreNew
    Register-ScheduledTask -TaskName $TaskName -Action $action `
        -Trigger @($atLogon, $every) -Principal $principal -Settings $settings -Force | Out-Null
    Write-Log 'INFO' "已註冊排程工作「$TaskName」（登入後 3 分鐘 + 每 10 分鐘）"
    return
}
if ($Uninstall) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    Write-Log 'INFO' "已移除排程工作「$TaskName」"
    return
}

# ── 常駐迴圈（啟動捷徑用）────────────────────────────────────────────────
# ZH: 登入後 3 分鐘才開始第一次 —— Docker Desktop 也才剛被叫起來，
#     太早探活會得到一個「還在開機」的假故障，然後白白修一次。
if ($Loop) {
    Write-Log 'INFO' '看門狗常駐迴圈啟動（每 10 分鐘一次，先等 3 分鐘讓 Docker Desktop 起來）'
    Start-Sleep -Seconds 180
    while ($true) {
        try {
            & $PSCommandPath
        } catch {
            Write-Log 'ERROR' "迴圈內發生例外（繼續跑）：$($_.Exception.Message)"
        }
        Start-Sleep -Seconds 600
    }
}

# ── 主流程 ───────────────────────────────────────────────────────────────
$healthy = if ($Simulate) { $false } else { Test-Platform }

if ($healthy) {
    Write-Log 'OK' '平台正常（/health 200）'
    return
}

Write-Log 'WARN' "平台沒有回應：$HealthUrl$(if ($Simulate) { '（-Simulate 假裝的）' })"

# ZH: 節流 —— 修不好的狀況不要變成每 10 分鐘殺一次 Docker（見檔頭）。
$last = Get-LastAttempt
if ($last -and ((Get-Date) - $last).TotalMinutes -lt $CooldownMinutes) {
    $mins = [int]((Get-Date) - $last).TotalMinutes
    Write-Log 'WARN' "$mins 分鐘前才剛修過，這次只記錄不動作（冷卻 $CooldownMinutes 分鐘）—— 連續出現代表需要人工處理"
    return
}
Set-LastAttempt

if (-not (Test-DockerDaemon)) {
    Repair-Docker
} else {
    Write-Log 'INFO' 'daemon 活著，只是服務沒起來'
}
Start-Stack

# ZH: 修完要**再驗一次**。不驗的話 log 上只會看到「我修了」，
#     而修了沒好與修好了在紀錄上長得一模一樣。
if ($DryRun) { Write-Log 'INFO' '（DryRun：結束，沒有動任何東西）'; return }
Start-Sleep -Seconds 20
if (Test-Platform) {
    Write-Log 'OK' '修復成功，平台恢復服務'
} else {
    Write-Log 'ERROR' '修復之後平台仍然沒有回應 —— 需要人工處理'
}
