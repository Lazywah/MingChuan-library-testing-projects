"""
==============================================================================
Module 9: FastAPI 主應用入口 (Main Application Entry Point)
==============================================================================
ZH: 用途：組裝所有模組、啟動 / 關閉服務、掛載路由
EN: Purpose: Assemble all modules, start/stop services, mount routes

ZH: 流程：
    1. 建立 FastAPI app 實例
    2. 掛載 CORS 中介層 (允許跨域)
    3. 掛載 Auth Router (/api/v1/auth/*)
    4. 掛載 Jobs Router (/api/v1/jobs/*)
    5. 註冊 startup 事件 → init_db() + start_scheduler()
    6. 註冊 shutdown 事件 → stop_scheduler()
    7. 提供 /health 健康檢查端點
EN: Flow:
    1. Create FastAPI app instance
    2. Mount CORS middleware (allow cross-origin)
    3. Mount Auth Router (/api/v1/auth/*)
    4. Mount Jobs Router (/api/v1/jobs/*)
    5. Register startup event → init_db() + start_scheduler()
    6. Register shutdown event → stop_scheduler()
    7. Provide /health endpoint

ZH: 模組化設計 (積木式組裝)：
    - 每個 Router 獨立掛載，註解掉 include_router 即可移除功能
    - startup/shutdown 事件中的模組也可獨立控制
    - 新增功能只需：1. 建立 Router  2. 在此 include_router
EN: Modular design (building-block assembly):
    - Each Router independently mounted, comment out include_router to remove
    - Modules in startup/shutdown also independently controllable
    - Adding features: 1. Create Router  2. include_router here
==============================================================================
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .database import init_db
from .scheduler import start_scheduler, stop_scheduler
from .config import settings, SCHEDULER_POLICY
from .routers import auth, jobs

import logging

# ==============================================================================
# ZH: 日誌設定 | EN: Logging configuration
# ==============================================================================
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)


# ==============================================================================
# ZH: 應用生命週期管理 (FastAPI lifespan)
# EN: Application lifecycle management (FastAPI lifespan)
# ==============================================================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    ZH: 應用啟動 / 關閉時的生命週期管理
    EN: Application startup / shutdown lifecycle management

    ZH: 啟動順序：
        1. 初始化資料庫 (建表)
        2. 啟動背景排程器
    EN: Startup order:
        1. Initialize database (create tables)
        2. Start background scheduler
    """
    # ---- ZH: 啟動 | EN: Startup ----
    logger.info("=" * 60)
    logger.info("ZH: AI 訓練平台 Job Scheduler 啟動中... | EN: Starting AI Training Platform Job Scheduler...")
    logger.info("=" * 60)

    # ZH: Module 2: 初始化資料庫 | EN: Module 2: Initialize database
    init_db()

    # ZH: Module 8: 啟動排程器 | EN: Module 8: Start scheduler
    await start_scheduler()

    sched_config = SCHEDULER_POLICY.get("scheduling", {})
    logger.info(
        f"ZH: 服務就緒 | EN: Service ready | "
        f"GPU_MOCK={SCHEDULER_POLICY.get('mock_mode', True)} | "
        f"MAX_JOBS={sched_config.get('max_concurrent_jobs', 4)}"
    )

    yield  # ZH: 應用運行中 | EN: Application running

    # ---- ZH: 關閉 | EN: Shutdown ----
    logger.info("ZH: 服務關閉中... | EN: Shutting down...")
    await stop_scheduler()
    logger.info("ZH: 服務已關閉 | EN: Service stopped")


# ==============================================================================
# ZH: 建立 FastAPI 應用實例 | EN: Create FastAPI app instance
# ==============================================================================
app = FastAPI(
    title="AI 訓練平台 Job Scheduler",
    description=(
        "ZH: AI 訓練平台的核心服務，提供使用者認證、Token 額度管理、訓練任務排程。\n"
        "EN: Core service of AI Training Platform, providing auth, token quota, and job scheduling."
    ),
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",       # ZH: Swagger UI 路徑 | EN: Swagger UI path
    redoc_url="/redoc",     # ZH: ReDoc 路徑 | EN: ReDoc path
)


# ==============================================================================
# ZH: CORS 中介層 (跨域資源共享)
# EN: CORS middleware (Cross-Origin Resource Sharing)
# ZH: 允許 Open WebUI 及其他前端跨域呼叫 API
# EN: Allows Open WebUI and other frontends to call API cross-origin
# ==============================================================================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],           # ZH: 開發環境允許所有來源 | EN: Dev allows all origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==============================================================================
# ZH: 掛載路由 (積木式 - 註解掉即可移除功能)
# EN: Mount routes (building-block - comment out to remove features)
# ==============================================================================

# ZH: Module 4 路由：認證 + Token 管理 | EN: Module 4 routes: Auth + Token
app.include_router(auth.router, prefix="/api/v1/auth")

# ZH: Module 5 路由：訓練任務管理 | EN: Module 5 routes: Training job management
app.include_router(jobs.router, prefix="/api/v1/jobs")

# ZH: 新增聊天助理路由 | EN: Chat assistant routes
from .routers import chat
app.include_router(chat.router, prefix="/api/v1/chat")


# ==============================================================================
# ZH: 健康檢查端點 | EN: Health check endpoint
# ZH: 用於 Docker healthcheck 和 Nginx upstream 檢查
# EN: Used by Docker healthcheck and Nginx upstream check
# ==============================================================================
@app.get("/health", tags=["系統 System"])
def health_check():
    """
    ZH: 服務健康檢查
    EN: Service health check
    """
    sched_config = SCHEDULER_POLICY.get("scheduling", {})
    return {
        "status": "healthy",
        "service": "job-scheduler",
        "version": "1.0.0",
        "gpu_mock_mode": SCHEDULER_POLICY.get("mock_mode", True),
        "max_concurrent_jobs": sched_config.get("max_concurrent_jobs", 4)
    }


# ==============================================================================
# ZH: 根路徑 | EN: Root path
# ==============================================================================
@app.get("/", tags=["系統 System"])
def root():
    """
    ZH: API 根路徑 - 回傳服務資訊
    EN: API root - returns service info
    """
    return {
        "service": "AI Training Platform - Job Scheduler",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health"
    }
