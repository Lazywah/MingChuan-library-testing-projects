"""
==============================================================================
Module 8: 背景排程器 (Background Job Scheduler)
==============================================================================
ZH: 用途：定時清理超時的 running 任務，防止 Worker 斷線後任務卡死。
EN: Purpose: Periodically clean up timed-out running jobs to prevent Worker
    disconnection from leaving jobs stuck in "running" state forever.
==============================================================================
"""

import asyncio
import logging
from datetime import datetime, timezone, timedelta

from .config import settings, SCHEDULER_POLICY
from .database import SessionLocal
from . import models

logger = logging.getLogger(__name__)

_scheduler_running = False
_scheduler_task = None

CHECK_INTERVAL_SECONDS = 300  # ZH: 每 5 分鐘檢查一次 | EN: Check every 5 minutes


async def _timeout_cleanup_loop():
    """
    ZH: 定時掃描長時間停在 running 的任務，超過閾值即標記為 failed。
    EN: Periodically scan jobs stuck in running state beyond the timeout threshold.
    ZH: 典型觸發情境：GPU Worker 意外斷線，任務永遠不會回報完成。
    EN: Typical trigger: GPU Worker crashes, job never reports completion.
    """
    logger.info(
        f"ZH: 排程器啟動，超時閾值={settings.JOB_TIMEOUT_MINUTES} 分鐘 | "
        f"EN: Scheduler started, timeout={settings.JOB_TIMEOUT_MINUTES} min"
    )

    while _scheduler_running:
        try:
            _cleanup_timed_out_jobs()
        except Exception as e:
            logger.error(f"ZH: 超時清理發生錯誤 | EN: Timeout cleanup error: {e}", exc_info=True)

        await asyncio.sleep(CHECK_INTERVAL_SECONDS)

    logger.info("ZH: 排程器已停止 | EN: Scheduler stopped")


def _cleanup_timed_out_jobs():
    """ZH: 執行一次超時清理，在同步上下文中操作 DB | EN: One-shot timeout cleanup (sync DB access)"""
    db = SessionLocal()
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=settings.JOB_TIMEOUT_MINUTES)

        stuck_jobs = (
            db.query(models.TrainingJob)
            .filter(
                models.TrainingJob.status == "running",
                models.TrainingJob.started_at < cutoff,
            )
            .all()
        )

        if not stuck_jobs:
            return

        for job in stuck_jobs:
            job.status = "failed"
            job.error_message = (
                f"Timeout: job exceeded {settings.JOB_TIMEOUT_MINUTES} minutes without completion. "
                f"Worker may have disconnected."
            )
            job.completed_at = datetime.now(timezone.utc)
            logger.warning(
                f"ZH: 任務超時，標記為 failed: {job.id[:8]} (node={job.gpu_server}) | "
                f"EN: Job timed out, marked failed: {job.id[:8]} (node={job.gpu_server})"
            )

        db.commit()
        logger.info(f"ZH: 本次清理了 {len(stuck_jobs)} 個超時任務 | EN: Cleaned up {len(stuck_jobs)} timed-out jobs")
    finally:
        db.close()


# ==============================================================================
# ZH: 排程器生命週期控制
# EN: Scheduler lifecycle control
# ==============================================================================

async def start_scheduler():
    global _scheduler_task, _scheduler_running
    _scheduler_running = True
    _scheduler_task = asyncio.create_task(_timeout_cleanup_loop())
    logger.info("ZH: 排程器背景工作已啟動 | EN: Scheduler background task started")


async def stop_scheduler():
    global _scheduler_task, _scheduler_running
    _scheduler_running = False
    if _scheduler_task:
        _scheduler_task.cancel()
        try:
            await _scheduler_task
        except asyncio.CancelledError:
            pass
    logger.info("ZH: 排程器已停止 | EN: Scheduler stopped")
