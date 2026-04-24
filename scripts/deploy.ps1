# ==============================================================================
# ZH: AI 訓練平台 - 一鍵部署腳本 (Windows PowerShell)
# EN: AI Training Platform - One-click Deployment Script (Windows PowerShell)
# ZH: 用途：在全新環境中快速部署所有服務
# EN: Purpose: Quickly deploy all services in a fresh environment
# ZH: 執行方式：.\scripts\deploy.ps1
# EN: Usage: .\scripts\deploy.ps1
# ==============================================================================

$ErrorActionPreference = "Stop"

Write-Host "======================================"
Write-Host " AI 訓練平台 - 部署腳本 | Deploy Script"
Write-Host "======================================"

# ZH: Step 1: 檢查前置條件 | EN: Step 1: Check prerequisites
Write-Host ""
Write-Host "📋 Step 1: 檢查前置條件 | Checking prerequisites..."
if (!(Get-Command "docker" -ErrorAction SilentlyContinue)) {
    Write-Host "❌ Docker 未安裝 | Docker not installed" -ForegroundColor Red
    exit 1
}
if (!(Get-Command "docker-compose" -ErrorAction SilentlyContinue) -and !(docker compose version 2>$null)) {
    Write-Host "❌ Docker Compose 未安裝 | Docker Compose not installed" -ForegroundColor Red
    exit 1
}
Write-Host "✅ Docker 和 Docker Compose 已安裝 | Docker & Compose installed" -ForegroundColor Green

# ZH: Step 2: 建立 .env | EN: Step 2: Create .env
Write-Host ""
Write-Host "📋 Step 2: 檢查 .env | Checking .env..."
if (-Not (Test-Path ".env")) {
    Copy-Item ".env.example" -Destination ".env"
    Write-Host "⚠️  已從 .env.example 建立 .env，請修改設定 | Created .env from example, please edit" -ForegroundColor Yellow
} else {
    Write-Host "✅ .env 已存在 | .env exists" -ForegroundColor Green
}

# ZH: Step 3: 建立資料目錄 | EN: Step 3: Create data directory
Write-Host ""
Write-Host "📋 Step 3: 建立資料目錄 | Creating data directory..."
if (-Not (Test-Path "data")) {
    New-Item -ItemType Directory -Force -Path "data" | Out-Null
}
Write-Host "✅ data/ 目錄就緒 | data/ directory ready" -ForegroundColor Green

# ZH: Step 4: 建構並啟動服務 | EN: Step 4: Build and start services
Write-Host ""
Write-Host "📋 Step 4: 建構並啟動服務 | Building and starting services..."
docker compose up -d --build

# ZH: Step 5: 等待服務就緒 | EN: Step 5: Wait for services
Write-Host ""
Write-Host "📋 Step 5: 等待服務就緒 | Waiting for services..."
Start-Sleep -Seconds 10

# ZH: Step 6: 健康檢查 | EN: Step 6: Health check
Write-Host ""
Write-Host "📋 Step 6: 健康檢查 | Health check..."
try {
    $response = Invoke-WebRequest -Uri "http://localhost/health" -UseBasicParsing -ErrorAction Stop
    if ($response.StatusCode -eq 200) {
        Write-Host "✅ Gateway & Job Scheduler 正常 | Gateway & Scheduler healthy" -ForegroundColor Green
    } else {
        Write-Host "⚠️  健康檢查回應異常，狀態碼: $($response.StatusCode)" -ForegroundColor Yellow
    }
} catch {
    Write-Host "⚠️  Job Scheduler 或網關尚未就緒，請查看日誌 | Not ready, check logs" -ForegroundColor Yellow
    Write-Host "   docker compose logs job-scheduler nginx"
}

Write-Host ""
Write-Host "======================================"
Write-Host " 部署完成 | Deployment Complete"
Write-Host "======================================"
Write-Host " 🌐 訓練儀表板(TRAIN_HUD): http://localhost/train/"
Write-Host " 🌐 Open WebUI (備援): http://localhost:8080"
Write-Host " 📡 API Docs: http://localhost:8002/docs"
Write-Host " 🔍 Health: http://localhost/health"
Write-Host "======================================"
