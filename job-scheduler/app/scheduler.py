"""
==============================================================================
Module 8: 背景排程器 (Background Job Scheduler)
==============================================================================
ZH: 用途：背景迴圈，定期檢查任務佇列，自動分配 GPU 並執行訓練
EN: Purpose: Background loop, periodically checks job queue, auto-assigns GPUs

ZH: 流程：
    ┌─────────────────────────────────────────────────────┐
    │ 排程器背景迴圈 (每 JOB_CHECK_INTERVAL 秒)            │
    │                                                       │
    │ 1. 查詢正在執行的任務數量 (running_count)              │
    │ 2. 若 running_count < MAX_CONCURRENT_JOBS (4)        │
    │ 3. 取出最高優先級的 pending 任務                       │
    │ 4. 依序嘗試分配 GPU：                                 │
    │    a. 連線 GPU 伺服器                                 │
    │    b. 查詢可用 GPU                                    │
    │    c. 分配成功 → status=running → 啟動訓練            │
    │    d. 分配失敗 → status=queued (等待下次檢查)          │
    │ 5. 等待 interval 秒後重複                             │
    └─────────────────────────────────────────────────────┘

ZH: 模組化設計：
    - 排程邏輯完全獨立，不依賴 HTTP 路由
    - 透過 start_scheduler() / stop_scheduler() 控制生命週期
    - GPU Client 透過工廠函式注入，可替換為任何後端
    - 移除此模組不會影響 Auth 和 CRUD 功能
EN: Modular design:
    - Scheduling logic is fully independent, not tied to HTTP routes
    - Lifecycle controlled via start_scheduler() / stop_scheduler()
    - GPU Client injected via factory function, swappable to any backend
    - Removing this module won't affect Auth and CRUD features
==============================================================================
"""

import asyncio
import logging
from typing import Optional

from .config import settings
from .database import SessionLocal
from . import crud
from .gpu_client import get_gpu_client, BaseGPUClient

logger = logging.getLogger(__name__)

# ==============================================================================
# ZH: 全域排程器狀態 | EN: Global scheduler state
# ==============================================================================
_scheduler_task: Optional[asyncio.Task] = None
_scheduler_running: bool = False


async def _process_single_job(job, db):
    """
    ZH: 處理單一訓練任務 (分配 GPU → 執行 → 監控進度 → 更新狀態)
    EN: Process a single training job (assign GPU → execute → monitor → update)
    """
    gpu_client: Optional[BaseGPUClient] = None

    try:
        # ZH: Step 1: 嘗試連線 GPU 伺服器 | EN: Step 1: Try connecting to GPU server
        servers = [
            (settings.GPU_SERVER_1_HOST, "GPU-Server-1"),
            (settings.GPU_SERVER_2_HOST, "GPU-Server-2"),
        ]

        assigned_server = None
        assigned_gpu = None

        for host, name in servers:
            gpu_client = get_gpu_client(
                host=host,
                mock_mode=settings.GPU_MOCK_MODE,
                username=settings.GPU_SERVER_USERNAME,
                key_path=settings.SSH_KEY_PATH
            )

            if await gpu_client.connect():
                available = await gpu_client.get_available_gpus()
                if available:
                    assigned_server = name
                    assigned_gpu = available[0]
                    logger.info(
                        f"ZH: 任務 {job.id[:8]} 分配到 {name} GPU-{assigned_gpu} | "
                        f"EN: Job {job.id[:8]} assigned to {name} GPU-{assigned_gpu}"
                    )
                    break
                else:
                    gpu_client.disconnect()

        if not assigned_server:
            # ZH: 沒有可用 GPU → 排隊等待 | EN: No GPU available → queue for later
            crud.update_job_status(db, job.id, status="queued")
            logger.info(f"ZH: 任務 {job.id[:8]} 排隊中 (無可用 GPU) | "
                        f"EN: Job {job.id[:8]} queued (no GPU available)")
            return

        # ZH: Step 2: 更新狀態為 running | EN: Step 2: Update status to running
        crud.update_job_status(
            db, job.id,
            status="running",
            gpu_server=assigned_server,
            gpu_id=assigned_gpu
        )

        # ZH: Step 3: 執行訓練 | EN: Step 3: Execute training
        import json
        config = json.loads(job.config) if job.config else {}
        script = job.script_path or "/workspace/train.py"

        result = await gpu_client.execute_training(script, config)
        output_path = result.get("output_path", "")

        # ZH: Step 4: 監控進度直到完成 | EN: Step 4: Monitor progress until done
        while True:
            progress = await gpu_client.check_job_progress()
            crud.update_job_progress(db, job.id, progress=progress)

            if progress >= 100.0:
                break

        # ZH: Step 5: 標記完成 | EN: Step 5: Mark as completed
        crud.update_job_status(
            db, job.id,
            status="completed",
            output_path=output_path
        )
        crud.update_job_progress(db, job.id, progress=100.0)
        logger.info(f"ZH: 任務 {job.id[:8]} 完成 | EN: Job {job.id[:8]} completed")

    except Exception as e:
        logger.error(f"ZH: 任務 {job.id[:8]} 失敗: {e} | EN: Job {job.id[:8]} failed: {e}")
        crud.update_job_status(
            db, job.id,
            status="failed",
            error_message=str(e)
        )
    finally:
        if gpu_client:
            gpu_client.disconnect()


async def _scheduler_loop():
    """
    ZH: 排程器主迴圈 (背景 asyncio task)
    EN: Scheduler main loop (background asyncio task)
    """
    global _scheduler_running
    logger.info("ZH: 排程器啟動 | EN: Scheduler started")

    while _scheduler_running:
        try:
            db = SessionLocal()
            try:
                # ZH: 查詢正在執行的任務數 | EN: Get running job count
                running_count = crud.get_running_jobs_count(db)

                # ZH: 若有空閒位置，處理待處理任務 | EN: If slots available, process pending jobs
                slots_available = settings.MAX_CONCURRENT_JOBS - running_count

                if slots_available > 0:
                    pending_jobs = crud.get_pending_jobs(db)

                    for job in pending_jobs[:slots_available]:
                        # ZH: 每個任務在獨立的 asyncio task 中執行
                        # EN: Each job runs in its own asyncio task
                        asyncio.create_task(_process_single_job(job, db))

                    if pending_jobs:
                        logger.debug(
                            f"ZH: 排程檢查: {running_count} 執行中, "
                            f"{len(pending_jobs)} 待處理, {slots_available} 空位 | "
                            f"EN: Schedule check: {running_count} running, "
                            f"{len(pending_jobs)} pending, {slots_available} slots"
                        )
            finally:
                db.close()

        except Exception as e:
            logger.error(f"ZH: 排程器迴圈錯誤: {e} | EN: Scheduler loop error: {e}")

        # ZH: 等待下次檢查 | EN: Wait for next check
        await asyncio.sleep(settings.JOB_CHECK_INTERVAL)

    logger.info("ZH: 排程器已停止 | EN: Scheduler stopped")


# ==============================================================================
# ZH: 排程器生命週期控制 (積木式 - 可在 main.py 中啟用/停用)
# EN: Scheduler lifecycle control (building-block - enable/disable in main.py)
# ==============================================================================

async def start_scheduler():
    """
    ZH: 啟動排程器背景任務
    EN: Start scheduler background task

    ZH: 在 main.py 的 @app.on_event("startup") 中呼叫
    EN: Called in main.py's @app.on_event("startup")
    """
    global _scheduler_task, _scheduler_running
    _scheduler_running = True
    _scheduler_task = asyncio.create_task(_scheduler_loop())
    logger.info(
        f"ZH: 排程器已啟動 (間隔={settings.JOB_CHECK_INTERVAL}秒, "
        f"最大並發={settings.MAX_CONCURRENT_JOBS}) | "
        f"EN: Scheduler started (interval={settings.JOB_CHECK_INTERVAL}s, "
        f"max_concurrent={settings.MAX_CONCURRENT_JOBS})"
    )


async def stop_scheduler():
    """
    ZH: 停止排程器背景任務
    EN: Stop scheduler background task

    ZH: 在 main.py 的 @app.on_event("shutdown") 中呼叫
    EN: Called in main.py's @app.on_event("shutdown")
    """
    global _scheduler_task, _scheduler_running
    _scheduler_running = False
    if _scheduler_task:
        _scheduler_task.cancel()
        try:
            await _scheduler_task
        except asyncio.CancelledError:
            pass
    logger.info("ZH: 排程器已停止 | EN: Scheduler stopped")
