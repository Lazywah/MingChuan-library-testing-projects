# ==============================================================================
# ZH: 平台健檢看門狗 / Platform health watchdog
# ==============================================================================
# ZH: 為什麼需要這支：2026-09-17 與 09-20 各發生一次 **Docker Desktop 自己退出**，
#     留下死掉的 socket（`%LOCALAPPDATA%\Docker\run\dockerInference` 等），
#     之後再怎麼按都起不來。第二次從 09-20 掛到 09-23 才被發現 ——
#     **三天沒有人知道平台是死的**，因為沒有任何東西會講話。
#
# ZH: 這支做四件事，順序不能顛倒：
#       1. 探活（打本機的 /health，不經過 DNS 與 TLS —— 那兩層自己也會壞，
#          用它們探活會把「憑證過期」誤判成「平台掛了」）
#       2. 不通就**修一次**：daemon 死了就清孤兒 socket 重啟 Docker Desktop；
#          daemon 活著只是容器沒起來就 `docker compose up -d`
#       3. 不管成功失敗都寫一行 log
#       4. **寄信**：修不好就求救，修好了也講一聲（收件人＝ .env 的 WATCHDOG_ALERT_TO）
#
# ZH: 🔴 寄信這一段**不經過平台**，直接用 SMTP（curl smtps://）。
#     平台的告警信是平台自己寄的 —— 平台死透的時候那條路也是死的，
#     而看門狗要講的正是「平台死透了」。這支如果也走平台，就等於沒有告警。
#     ⚠ SMTP 是 465 隱含 TLS（校園網掐 587 的 STARTTLS，2026-08-30 查出來的），
#     `Send-MailMessage` 與 System.Net.Mail 都只會 STARTTLS，對 465 連不上。
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
#   ... -TestMail      寄一封測試信（繞過節流），裝設時驗證寄信這條路通不通
# ==============================================================================
[CmdletBinding()]
param(
    [switch]$DryRun,
    [switch]$Simulate,
    [switch]$Install,
    [switch]$Uninstall,
    [switch]$Loop,
    [switch]$InstallStartup,
    [switch]$UninstallStartup,
    [switch]$TestMail
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
# ZH: 同一種告警信最短間隔（小時）。與平台的 admin_alert_min_hours 取同一個數字 ——
#     兩邊不一樣的話，接手的人會以為其中一邊壞了。
$AlertMinHours = 6
$EnvFile = Join-Path $RepoRoot '.env'

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

function Get-EnvValue([string]$Key) {
    <# ZH: 從根 .env 讀一個值。設定單一來源＝根 .env（與 start-worker.sh 同原則）。#>
    if (-not (Test-Path $EnvFile)) { return '' }
    foreach ($line in Get-Content $EnvFile -Encoding UTF8) {
        if ($line -match "^\s*$([regex]::Escape($Key))\s*=(.*)$") { return $Matches[1].Trim() }
    }
    return ''
}

function Send-WatchdogMail([string]$Kind, [string]$Subject, [string]$Body) {
    <# ZH: 直接用 SMTP 寄信 —— 不經過平台。
       ZH: 為什麼不呼叫平台的告警端點：平台的告警是平台自己寄的，平台死透的時候
           那條路也是死的，而看門狗要講的正是「平台死透了」。
       ZH: 為什麼用 curl.exe 不用 Send-MailMessage：這裡的 SMTP 是 465 隱含 TLS
           （校園網掐 587 的 STARTTLS，2026-08-30 查出來的）。Send-MailMessage 與
           System.Net.Mail 都只會 STARTTLS，對 465 連不上。curl 的 smtps:// 才對。
       ZH: 節流：同一種告警 $AlertMinHours 小時內只寄一次。平台掛著沒人修的時候，
           每 10 分鐘一封信只會讓人把這個寄件者設成封鎖。
    #>
    $to = Get-EnvValue 'WATCHDOG_ALERT_TO'
    $user = Get-EnvValue 'SMTP_USERNAME'
    if (-not $to) { $to = $user }
    $server = Get-EnvValue 'SMTP_SERVER'
    $port = Get-EnvValue 'SMTP_PORT'
    $pass = Get-EnvValue 'SMTP_PASSWORD'
    $from = Get-EnvValue 'SMTP_FROM_EMAIL'
    if (-not $from) { $from = $user }
    if (-not $to -or -not $server -or -not $user -or -not $pass) {
        Write-Log 'WARN' '寄不了信：SMTP 設定不完整（看 .env 的 SMTP_* 與 WATCHDOG_ALERT_TO）'
        return
    }

    $state = @{}
    if (Test-Path $StateFile) {
        try {
            (Get-Content $StateFile -Raw | ConvertFrom-Json).PSObject.Properties |
                ForEach-Object { $state[$_.Name] = $_.Value }
        } catch { }
    }
    $key = "lastAlert_$Kind"
    if ($state.ContainsKey($key)) {
        try {
            $since = ((Get-Date) - [datetime]$state[$key]).TotalHours
            if ($since -lt $AlertMinHours) {
                Write-Log 'INFO' ("告警 {0} 在 {1:N1} 小時前寄過（節流 {2} 小時），這次不寄" -f $Kind, $since, $AlertMinHours)
                return
            }
        } catch { }
    }

    # ZH: 郵件本文用暫存檔餵給 curl。寫成 UTF-8 無 BOM ——
    #     BOM 會被當成信件內容，收到的信開頭會多三個怪字元。
    $tmp = Join-Path $env:TEMP ("watchdog-mail-{0}.txt" -f [guid]::NewGuid().ToString('N'))
    $sbj = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($Subject))
    $lines = @(
        "From: MCU AI Base watchdog <$from>",
        "To: $to",
        "Subject: =?UTF-8?B?$sbj?=",
        "MIME-Version: 1.0",
        "Content-Type: text/plain; charset=UTF-8",
        "",
        $Body
    )
    [IO.File]::WriteAllText($tmp, ($lines -join "`r`n"), (New-Object Text.UTF8Encoding $false))
    try {
        $out = & curl.exe --silent --show-error --ssl-reqd --url "smtps://${server}:${port}" --user "${user}:${pass}" --mail-from $from --mail-rcpt $to --upload-file $tmp --max-time 60 2>&1
        if ($LASTEXITCODE -eq 0) {
            Write-Log 'INFO' "告警信已寄出（$Kind -> $to）"
            $state[$key] = (Get-Date).ToString('o')
            try { [pscustomobject]$state | ConvertTo-Json | Set-Content -Path $StateFile -Encoding UTF8 } catch { }
        } else {
            $msg = ($out -join ' ')
            if ($pass) { $msg = $msg.Replace($pass, '<hidden>') }
            if ($msg.Length -gt 200) { $msg = $msg.Substring(0, 200) }
            Write-Log 'ERROR' ("告警信寄不出去（curl {0}）：{1}" -f $LASTEXITCODE, $msg)
        }
    } catch {
        Write-Log 'ERROR' "告警信寄不出去：$($_.Exception.Message)"
    } finally {
        Remove-Item $tmp -Force -ErrorAction SilentlyContinue
    }
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
    # ZH: 這個檔裡還有告警節流的 key（lastAlert_*），整份覆寫會把它們洗掉，
    #     於是每修一次就會再寄一次信。要先讀再合併。
    if ($DryRun) { return }
    try {
        $state = @{}
        if (Test-Path $StateFile) {
            (Get-Content $StateFile -Raw | ConvertFrom-Json).PSObject.Properties |
                ForEach-Object { $state[$_.Name] = $_.Value }
        }
        $state['lastAttempt'] = (Get-Date).ToString('o')
        [pscustomobject]$state | ConvertTo-Json | Set-Content -Path $StateFile -Encoding UTF8
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

if ($TestMail) {
    # ZH: 裝設時驗證寄信這條路通不通。繞過節流 —— 測試時被節流擋掉會讓人
    #     以為設定錯了，然後去改一個本來就對的東西。
    $AlertMinHours = 0
    $body = @"
這是 scripts\health_watchdog.ps1 -TestMail 寄出的測試信。

收到這封＝平台真的掛掉而且看門狗修不好時，你會收到通知。
寄件路徑：curl smtps://（465 隱含 TLS），不經過平台本身。

時間：$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')
機器：$env:COMPUTERNAME
"@
    Send-WatchdogMail 'test' '[MCU AI Base] 看門狗寄信測試' $body
    return
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
    # ZH: 剛修過又掛著 ＝ 修不好。這是最該寄信的時刻（節流見 Send-WatchdogMail）。
    if (-not $DryRun) {
        $body = @"
看門狗在 $mins 分鐘前已經嘗試修復過一次，平台現在仍然沒有回應。需要人工處理。

探活位址：$HealthUrl
紀錄檔　：$LogFile
機器　　：$env:COMPUTERNAME
時間　　：$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')

先看 log 的最後幾行，再看 docker ps -a。
Docker Desktop 自己退出留下死 socket 的處理方式見 docs/04-operations.md 第 4 節。
"@
        Send-WatchdogMail 'down' '[MCU AI Base] 平台掛了，而且自動修復沒有用' $body
    }
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
    # ZH: 自己修好了也要講一聲 —— 不然「平台曾經掛過」只存在 log 裡，
    #     而沒有人會固定去看 log。這一封是「發生過、已經好了」，不是求救。
    $body = @"
平台在 $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') 前後沒有回應，看門狗已自動修復，現在服務正常。

紀錄檔：$LogFile
機器　：$env:COMPUTERNAME

這封只是告知。如果短時間內一直收到，代表有反覆發生的問題要查。
"@
    Send-WatchdogMail 'recovered' '[MCU AI Base] 平台曾經掛掉，已自動修復' $body
} else {
    Write-Log 'ERROR' '修復之後平台仍然沒有回應 —— 需要人工處理'
    $body = @"
看門狗偵測到平台沒有回應，嘗試修復之後仍然不通。需要人工處理。

探活位址：$HealthUrl
紀錄檔　：$LogFile
機器　　：$env:COMPUTERNAME
時間　　：$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')
"@
    Send-WatchdogMail 'down' '[MCU AI Base] 平台掛了，自動修復失敗' $body
}
