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

# H-1: ZH: 從 scheduler_policy.yaml 讀取間隔，YAML 未設定則預設 300 秒
# EN: Read interval from scheduler_policy.yaml; default 300 s if not configured
CHECK_INTERVAL_SECONDS = SCHEDULER_POLICY.get("scheduling", {}).get(
    "job_check_interval_seconds", 300
)


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


def _cleanup_timed_out_jobs(db=None):
    """ZH: 執行一次超時清理，在同步上下文中操作 DB | EN: One-shot timeout cleanup (sync DB access)"""
    _owns_db = db is None
    if _owns_db:
        db = SessionLocal()
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=settings.JOB_TIMEOUT_MINUTES)

        # ZH: SQLite 回傳 naive datetime，統一加 UTC tzinfo 再比較
        # EN: SQLite returns naive datetimes; attach UTC tzinfo before comparing
        all_running = (
            db.query(models.TrainingJob)
            .filter(models.TrainingJob.status == "running")
            .all()
        )
        stuck_jobs = []
        for job in all_running:
            started = job.started_at
            if started is None:
                continue
            if started.tzinfo is None:
                started = started.replace(tzinfo=timezone.utc)
            if started < cutoff:
                stuck_jobs.append(job)

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
        if _owns_db:
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
