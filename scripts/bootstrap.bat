@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
REM ============================================================================
REM  一鍵啟動平台 (Windows .bat) — 全新機器
REM  前提：① 已跑過 python scripts\setup_env.py 產生 .env
REM        ② 已跑過 build-all.sh 把 base images build 好（要用 Lab/訓練才需要）
REM  本腳本依「正確順序」自動完成：
REM     AI模型層 → pull 3 模型 → 核心層 → 等就緒 → 建 admin → 驗證KB → 健康檢查
REM ============================================================================

REM ===== 可調整 =========================================================
set "USE_GPU=1"           REM 1 = Ollama 用 GPU(疊 override)；0 = CPU(無 NVIDIA GPU 請設 0)
REM =====================================================================

REM 切到專案根目錄（本腳本位於 scripts\ 下）
pushd "%~dp0.." || ( echo [錯誤] 找不到專案根目錄 & pause & exit /b 1 )

echo ============================================================
echo   圖書館 AI 基地 — 平台一鍵啟動
echo ============================================================

REM ---- (前置) Docker 與 .env 檢查 ----
docker info >nul 2>&1
if errorlevel 1 ( echo [錯誤] Docker 沒在執行，請先開啟 Docker Desktop。 & popd & pause & exit /b 1 )
if not exist ".env" ( echo [錯誤] 找不到 .env，請先執行： python scripts\setup_env.py & popd & pause & exit /b 1 )

REM ---- [1/6] AI 模型層 ----
echo.
echo [1/6] 啟動 AI 模型層 (ollama / portkey / open-webui) ...
if "%USE_GPU%"=="1" (
  docker compose -f docker-compose.ai-models.yml -f docker-compose.ai-models.gpu.yml up -d
  if errorlevel 1 (
    echo       [提醒] GPU 模式啟動失敗，改用 CPU 模式 ...
    docker compose -f docker-compose.ai-models.yml up -d
  )
) else (
  docker compose -f docker-compose.ai-models.yml up -d
)
if errorlevel 1 ( echo [錯誤] AI 模型層啟動失敗 & popd & pause & exit /b 1 )

REM ---- [2/6] 等 Ollama 就緒 ----
echo.
echo [2/6] 等待 Ollama 就緒 ...
set /a _t=0
:wait_ollama
docker exec ai-platform-ollama ollama list >nul 2>&1
if not errorlevel 1 goto ollama_ok
set /a _t+=1
if !_t! geq 30 ( echo [錯誤] Ollama 逾時未就緒 & popd & pause & exit /b 1 )
timeout /t 2 >nul
goto wait_ollama
:ollama_ok
echo       Ollama OK

REM ---- [3/6] pull 3 個本機模型（已存在會略過；首次很久）----
echo.
echo [3/6] 下載 / 確認 3 個本機模型（首次下載約數 GB，請耐心等）...
echo       - llama3:latest        (chat / 簡報)
docker exec ai-platform-ollama ollama pull llama3:latest
echo       - nomic-embed-text     (小基 RAG 向量)
docker exec ai-platform-ollama ollama pull nomic-embed-text
echo       - qwen2.5:7b           (小基 客服 / 程式家教)
docker exec ai-platform-ollama ollama pull qwen2.5:7b

REM ---- [4/6] 核心層（模型已就緒 → scheduler 啟動時自動匯入 KB）----
echo.
echo [4/6] 啟動核心層 (nginx / job-scheduler) ...
docker compose up -d --build
if errorlevel 1 ( echo [錯誤] 核心層啟動失敗（常見：.env 機密未設定）& popd & pause & exit /b 1 )

echo       等待 scheduler 健康檢查 ...
set /a _t=0
:wait_sched
set "_h="
for /f "tokens=*" %%i in ('docker inspect -f "{{.State.Health.Status}}" ai-platform-scheduler 2^>nul') do set "_h=%%i"
if "!_h!"=="healthy" goto sched_ok
set /a _t+=1
if !_t! geq 40 ( echo       [警告] 健康檢查逾時，仍繼續 & goto sched_ok )
timeout /t 2 >nul
goto wait_sched
:sched_ok
echo       scheduler OK

REM ---- [5/6] 建立管理員 ----
echo.
echo [5/6] 建立 / 重設管理員帳號 ...
call "%~dp0create-admin.bat" auto
if errorlevel 1 ( echo [錯誤] 建立 admin 失敗 & popd & pause & exit /b 1 )

REM ---- [6/6] 驗證知識庫 + 健康檢查 ----
echo.
echo [6/6] 驗證知識庫 (KB) ...
docker exec ai-platform-scheduler python -c "from app.database import SessionLocal; from app import models; db=SessionLocal(); print('       KB chunks =', db.query(models.KnowledgeChunk).count())" 2>nul
echo       （若 KB chunks 為 0：用 admin token 打 POST /api/v1/assistant/reindex 重建）

echo.
echo ============================================================
echo   [完成] 平台已啟動
echo     使用者平台 : http://localhost/train/
echo     管理員平台 : http://localhost:8888/   （帳密見 scripts\create-admin.bat）
echo   ^>^> 請登入管理員後「立即」修改密碼。
echo     （選用）GPU 訓練 Worker： cd gpu-worker ^&^& docker compose up -d --build
echo ============================================================
echo.
docker ps --format "table {{.Names}}\t{{.Status}}"
popd
echo.
pause
