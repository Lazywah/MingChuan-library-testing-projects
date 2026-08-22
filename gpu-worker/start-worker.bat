@echo off
rem ==============================================================================
rem GPU Worker 啟動包裝 (Windows) / GPU Worker launcher
rem 強制帶 --env-file ..\.env，讓設定單一來源＝根 .env，避免誤讀本地 gpu-worker\.env
rem 造成 token 漂移→靜默 401。用法同 start-worker.sh：
rem   start-worker.bat                    等同 up -d
rem   start-worker.bat down               停止
rem   start-worker.bat logs -f            看日誌
rem 遠端 GPU 主機：用**本目錄的** worker.env.example，不要用根 .env.example：
rem   copy worker.env.example worker.env    然後把裡面標了「← 改我」的幾行填好
rem   set WORKER_ENV_FILE=worker.env
rem   start-worker.bat
rem 為什麼不用根 .env.example：那份 266 行、是整個平台的設定，而且它的
rem 預設值是給「與服務層同機」用的 —— 其中 SHARES_SERVICE_STORAGE=true
rem 照抄到遠端節點會造成「不報錯但訓練結果沒有意義」。
rem ==============================================================================
chcp 65001 >nul
setlocal
cd /d "%~dp0"

if defined WORKER_ENV_FILE (
  set "ENV_FILE=%WORKER_ENV_FILE%"
) else (
  set "ENV_FILE=..\.env"
)

if not exist "%ENV_FILE%" (
  echo [X] env file not found: %ENV_FILE%
  echo     co-located: run  python scripts\setup_env.py  in CodeSpace\ to generate ..\.env
  echo     remote GPU host: copy worker.env.example to worker.env, fill it, set WORKER_ENV_FILE=worker.env, re-run
  exit /b 1
)

rem 無參數 → 預設 up -d
set "ARGS=%*"
if "%ARGS%"=="" set "ARGS=up -d"

echo ^> docker compose --env-file "%ENV_FILE%" %ARGS%
docker compose --env-file "%ENV_FILE%" %ARGS%
set "RC=%ERRORLEVEL%"

rem ==============================================================================
rem ZH: 啟動後檢查 —— 只對「會把 worker 跑起來」的子指令做。
rem ZH: 為什麼需要：`up -d` 回 0 只代表**容器建立成功**。設定填錯時 worker.py 會
rem     exit 1、容器進重啟迴圈，但 compose 仍只印一句 Started，看起來完全正常。
rem     裝第 17 台的人不會知道要去 docker logs。
rem ZH: 判準用日誌裡的固定標記（worker.py 兩條路各印一句），不用容器狀態 ——
rem     重啟迴圈裡取樣會忽 running 忽 restarting，不可靠。
rem ==============================================================================
for /f "tokens=1" %%c in ("%ARGS%") do set "SUB=%%c"
if /i not "%SUB%"=="up" if /i not "%SUB%"=="start" if /i not "%SUB%"=="run" if /i not "%SUB%"=="restart" goto :done
if not "%RC%"=="0" goto :done

set "VERDICT="
for /l %%i in (1,1,20) do (
  if not defined VERDICT (
    docker logs --tail 80 mcu-gpu-worker 2>&1 | findstr /c:"Worker refuses to start" >nul && set "VERDICT=bad"
  )
  if not defined VERDICT (
    docker logs --tail 80 mcu-gpu-worker 2>&1 | findstr /c:"Config check passed" >nul && set "VERDICT=good"
  )
  if not defined VERDICT ping -n 2 127.0.0.1 >nul
)

if "%VERDICT%"=="good" (
  echo [OK] worker running, config check passed
  goto :done
)
echo.
if "%VERDICT%"=="bad" (
  echo [X] worker refused to start - bad configuration, see the log below
) else (
  echo [?] could not confirm startup within 20s - printing the log tail
)
echo ------------------------------------------------------------------------------
docker logs --tail 40 mcu-gpu-worker 2>&1
echo ------------------------------------------------------------------------------
endlocal
exit /b 1

:done
endlocal
exit /b %RC%
