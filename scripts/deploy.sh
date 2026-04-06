#!/bin/bash
# ==============================================================================
# ZH: AI 訓練平台 - 一鍵部署腳本
# EN: AI Training Platform - One-click Deployment Script
# ZH: 用途：在全新環境中快速部署所有服務
# EN: Purpose: Quickly deploy all services in a fresh environment
# ZH: 執行方式：chmod +x scripts/deploy.sh && ./scripts/deploy.sh
# EN: Usage: chmod +x scripts/deploy.sh && ./scripts/deploy.sh
# ==============================================================================

set -e

echo "======================================"
echo " AI 訓練平台 - 部署腳本 | Deploy Script"
echo "======================================"

# ZH: Step 1: 檢查前置條件 | EN: Step 1: Check prerequisites
echo ""
echo "📋 Step 1: 檢查前置條件 | Checking prerequisites..."
if ! command -v docker &> /dev/null; then
    echo "❌ Docker 未安裝 | Docker not installed"
    exit 1
fi
if ! command -v docker compose &> /dev/null && ! command -v docker-compose &> /dev/null; then
    echo "❌ Docker Compose 未安裝 | Docker Compose not installed"
    exit 1
fi
echo "✅ Docker 和 Docker Compose 已安裝 | Docker & Compose installed"

# ZH: Step 2: 建立 .env | EN: Step 2: Create .env
echo ""
echo "📋 Step 2: 檢查 .env | Checking .env..."
if [ ! -f .env ]; then
    cp .env.example .env
    echo "⚠️  已從 .env.example 建立 .env，請修改設定 | Created .env from example, please edit"
else
    echo "✅ .env 已存在 | .env exists"
fi

# ZH: Step 3: 建立資料目錄 | EN: Step 3: Create data directory
echo ""
echo "📋 Step 3: 建立資料目錄 | Creating data directory..."
mkdir -p data
echo "✅ data/ 目錄就緒 | data/ directory ready"

# ZH: Step 4: 建構並啟動服務 | EN: Step 4: Build and start services
echo ""
echo "📋 Step 4: 建構並啟動服務 | Building and starting services..."
docker compose up -d --build

# ZH: Step 5: 等待服務就緒 | EN: Step 5: Wait for services
echo ""
echo "📋 Step 5: 等待服務就緒 | Waiting for services..."
sleep 10

# ZH: Step 6: 健康檢查 | EN: Step 6: Health check
echo ""
echo "📋 Step 6: 健康檢查 | Health check..."
if curl -sf http://localhost:8002/health > /dev/null 2>&1; then
    echo "✅ Job Scheduler 正常 | Job Scheduler healthy"
else
    echo "⚠️  Job Scheduler 尚未就緒，請查看日誌 | Not ready, check logs"
    echo "   docker compose logs job-scheduler"
fi

echo ""
echo "======================================"
echo " 部署完成 | Deployment Complete"
echo "======================================"
echo " 🌐 Open WebUI:  http://localhost:3000"
echo " 📡 API Docs:    http://localhost:8002/docs"
echo " 🔍 Health:      http://localhost:8002/health"
echo "======================================"
