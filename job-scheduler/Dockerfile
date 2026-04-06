# ==============================================================================
# ZH: AI 訓練平台 - Job Scheduler 容器映像建構檔
# EN: AI Training Platform - Job Scheduler Dockerfile
#
# ZH: 用途：建構包含 FastAPI 應用的 Python 容器
# EN: Purpose: Build Python container with FastAPI application
# ZH: 基礎映像：Python 3.11 slim + openssh-client (SSH 連線 GPU)
# EN: Base image: Python 3.11 slim + openssh-client (SSH to GPU)
# ==============================================================================

FROM python:3.11-slim

# ZH: 安裝系統依賴 | EN: Install system dependencies
RUN apt-get update && apt-get install -y \
    openssh-client \
    curl \
    && rm -rf /var/lib/apt/lists/*

# ZH: 設定工作目錄 | EN: Set working directory
WORKDIR /app

# ZH: 先複製依賴清單 (利用 Docker 快取層) | EN: Copy deps first (Docker layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ZH: 複製應用程式碼 | EN: Copy application code
COPY app/ /app/app/

# ZH: 建立 SSH 目錄 | EN: Create SSH directory
RUN mkdir -p /root/.ssh && chmod 700 /root/.ssh

# ZH: 建立資料目錄 | EN: Create data directory
RUN mkdir -p /data

# ZH: 開放 API 埠 | EN: Expose API port
EXPOSE 8000

# ZH: 健康檢查 | EN: Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# ZH: 啟動應用 | EN: Start application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
