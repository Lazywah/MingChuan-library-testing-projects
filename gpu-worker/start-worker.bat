@echo off
rem ==============================================================================
rem GPU Worker 啟動包裝 (Windows) / GPU Worker launcher
rem 強制帶 --env-file ..\.env，讓設定單一來源＝根 .env，避免誤讀本地 gpu-worker\.env
rem 造成 token 漂移→靜默 401。用法同 start-worker.sh：
rem   start-worker.bat                    等同 up -d
rem   start-worker.bat down               停止
rem   start-worker.bat logs -f            看日誌
rem 遠端 GPU 主機：set WORKER_ENV_FILE=C:\path\to\your.env 後再執行本檔。
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
  echo     remote GPU host: copy root .env.example, fill it, then set WORKER_ENV_FILE and re-run
  exit /b 1
)

rem 無參數 → 預設 up -d
set "ARGS=%*"
if "%ARGS%"=="" set "ARGS=up -d"

echo ^> docker compose --env-file "%ENV_FILE%" %ARGS%
docker compose --env-file "%ENV_FILE%" %ARGS%
endlocal
