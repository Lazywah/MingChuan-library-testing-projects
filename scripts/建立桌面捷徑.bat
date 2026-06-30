@echo off
chcp 65001 >nul
REM ============================================================
REM  建立「AI 基地」桌面捷徑（v2.8）
REM  ZH: 在桌面建立一個捷徑，雙擊即開啟本平台登入頁。
REM      共用機台安全考量：捷徑只指向「我們自己的登入頁」，
REM      不嵌任何帳號/密碼 —— 每位學生自己登入、用完按「結束使用」。
REM  EN: Create a desktop shortcut that opens THIS platform's login.
REM      No credentials embedded (shared-machine safe).
REM ============================================================

REM --- 請改成你部署機器的網址（使用者端，nginx :80）---
REM     例如：http://192.168.1.50/  或  http://codespace.lib.mcu.edu.tw/
set "PLATFORM_URL=http://localhost/"

REM --- 捷徑名稱 ---
set "SHORTCUT_NAME=AI 基地"

set "DESKTOP=%USERPROFILE%\Desktop"
set "TARGET=%DESKTOP%\%SHORTCUT_NAME%.url"

(
  echo [InternetShortcut]
  echo URL=%PLATFORM_URL%
  echo IconIndex=0
) > "%TARGET%"

if exist "%TARGET%" (
  echo [OK] 已建立捷徑： "%TARGET%"
  echo      指向： %PLATFORM_URL%
) else (
  echo [失敗] 無法建立捷徑，請確認權限或路徑。
)

echo.
echo 提醒：共用電腦建議讓瀏覽器以「無痕／訪客」開啟，或設定關閉時清除 Cookie，
echo       並關閉「儲存密碼」功能，避免下一位使用者延續上一位的 MYAI 登入。
pause
