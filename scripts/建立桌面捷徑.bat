@echo off
chcp 65001 >nul
setlocal enableextensions
REM ============================================================
REM  建立「AI 基地」桌面捷徑（v2.8，共用機台安全版）
REM  ZH: 在桌面建立捷徑，以「無痕／InPrivate」模式開啟本平台。
REM      共用機台關鍵：學生用完直接關閉視窗 → cookie/localStorage/
REM      sessionStorage 全清（本平台 + MYAI 一起），不靠手動登出、
REM      不靠 IT 設定。Chrome 為主、Edge 次之，偵測到誰就建誰。
REM  EN: Desktop shortcuts that open THIS platform in Incognito/InPrivate.
REM      Closing the window wipes cookies + storage for both us and MYAI.
REM ============================================================

REM --- 請改成你部署機器的使用者端網址（nginx :80）---
REM     例如：http://192.168.1.50/  或  http://codespace.lib.mcu.edu.tw/
set "PLATFORM_URL=http://localhost/"

REM --- 捷徑輸出資料夾（預設桌面；測試可用環境變數 SHORTCUT_DIR 覆蓋）---
if not defined SHORTCUT_DIR set "SHORTCUT_DIR=%USERPROFILE%\Desktop"

REM --- 偵測 Chrome（為主）---
set "CHROME="
for %%P in (
  "%ProgramFiles%\Google\Chrome\Application\chrome.exe"
  "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"
  "%LocalAppData%\Google\Chrome\Application\chrome.exe"
) do if not defined CHROME if exist "%%~P" set "CHROME=%%~P"

REM --- 偵測 Edge（次之，Win11 內建）---
set "EDGE="
for %%P in (
  "%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"
  "%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"
) do if not defined EDGE if exist "%%~P" set "EDGE=%%~P"

set "MADE=0"

if defined CHROME (
  set "SC_NAME=AI 基地（Chrome 無痕）"
  set "SC_TARGET=%CHROME%"
  set "SC_ARGS=--incognito %PLATFORM_URL%"
  call :mkshortcut
)
if defined EDGE (
  set "SC_NAME=AI 基地（Edge InPrivate）"
  set "SC_TARGET=%EDGE%"
  set "SC_ARGS=--inprivate %PLATFORM_URL%"
  call :mkshortcut
)

if "%MADE%"=="0" (
  echo [失敗] 找不到 Chrome 或 Edge，請確認已安裝，或手動建立捷徑。
) else (
  echo.
  echo 完成。捷徑指向： %PLATFORM_URL%
  echo 共用機台用法：請學生一律雙擊此捷徑開啟；用完「直接關閉視窗」即清空，
  echo               連 MYAI 的登入也會一起消失。
)
echo.
pause
goto :eof

:mkshortcut
REM 用 PowerShell + WScript.Shell 建 .lnk（可帶啟動參數，.url 不行）
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$d=$env:SHORTCUT_DIR; if(-not (Test-Path $d)){New-Item -ItemType Directory -Force -Path $d ^| Out-Null}; $p=Join-Path $d ($env:SC_NAME + '.lnk'); $w=New-Object -ComObject WScript.Shell; $s=$w.CreateShortcut($p); $s.TargetPath=$env:SC_TARGET; $s.Arguments=$env:SC_ARGS; $s.IconLocation=$env:SC_TARGET + ',0'; $s.Save()"
if exist "%SHORTCUT_DIR%\%SC_NAME%.lnk" (
  echo [OK] 已建立： "%SC_NAME%.lnk"  ^(%SC_TARGET% %SC_ARGS%^)
  set "MADE=1"
) else (
  echo [失敗] 無法建立： "%SC_NAME%.lnk"
)
goto :eof
