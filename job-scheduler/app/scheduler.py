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
_lab_scan_task = None        # v2.0: 每分鐘掃描 lab session idle/hard-limit
_storage_scan_task = None    # v2.0: 每日 03:00 執行儲存生命週期掃描

# H-1: ZH: 從 scheduler_policy.yaml 讀取間隔，YAML 未設定則預設 300 秒
# EN: Read interval from scheduler_policy.yaml; default 300 s if not configured
CHECK_INTERVAL_SECONDS = SCHEDULER_POLICY.get("scheduling", {}).get(
    "job_check_interval_seconds", 300
)

# ZH: v2.0 lab session 掃描間隔 (秒) | EN: v2.0 lab session scan interval (sec)
LAB_SCAN_INTERVAL_SECONDS = 60


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
# ZH: v2.0 Lab session 掃描迴圈（每分鐘）
# EN: v2.0 Lab session scan loop (every minute)
# ==============================================================================

async def _lab_session_scan_loop():
    """
    ZH: 每分鐘呼叫 lab_manager.scan_and_evict() — 處理 idle 30 分鐘 / 8h hard limit
    EN: Every minute, invoke lab_manager.scan_and_evict() — handles idle/hard limit
    """
    logger.info(f"ZH: Lab session 掃描迴圈啟動 (每 {LAB_SCAN_INTERVAL_SECONDS}s)")
    # ZH: 延遲 import，避免 lab_manager 初始化 docker SDK 影響啟動順序
    # EN: Lazy import to avoid docker SDK init affecting startup order
    from .services import lab_manager

    while _scheduler_running:
        try:
            db = SessionLocal()
            try:
                lab_manager.scan_and_evict(db)
            finally:
                db.close()
        except Exception as e:
            logger.error(f"ZH: Lab session 掃描錯誤 | EN: Lab scan error: {e}", exc_info=True)
        await asyncio.sleep(LAB_SCAN_INTERVAL_SECONDS)

    logger.info("ZH: Lab session 掃描迴圈已停止")


# ==============================================================================
# ZH: v2.0 儲存生命週期掃描迴圈（每日 03:00）
# EN: v2.0 Storage lifecycle scan loop (daily 03:00)
# ==============================================================================

async def _storage_lifecycle_loop():
    """
    ZH: 每日 03:00 執行儲存生命週期掃描 — 90 天 freeze、180 天 archive、365 天 pending_delete
    EN: Daily 03:00 storage lifecycle scan — 90d freeze, 180d archive, 365d pending_delete
    """
    logger.info("ZH: 儲存生命週期迴圈啟動 (每日 03:00)")
    from .services import storage_lifecycle

    while _scheduler_running:
        now = datetime.now(timezone.utc)
        # ZH: 計算下次 03:00 觸發時間 | EN: Compute next 03:00 trigger
        next_run = now.replace(hour=3, minute=0, second=0, microsecond=0)
        if next_run <= now:
            next_run = next_run + timedelta(days=1)
        sleep_seconds = (next_run - now).total_seconds()
        logger.info(
            f"ZH: 下次儲存生命週期掃描於 {next_run.isoformat()} ({int(sleep_seconds)}s 後)"
        )
        try:
            await asyncio.sleep(sleep_seconds)
        except asyncio.CancelledError:
            break

        if not _scheduler_running:
            break

        try:
            db = SessionLocal()
            try:
                storage_lifecycle.run_daily_scan(db)
            finally:
                db.close()
        except Exception as e:
            logger.error(f"ZH: 儲存生命週期掃描錯誤 | EN: Storage scan error: {e}", exc_info=True)

    logger.info("ZH: 儲存生命週期迴圈已停止")


# ==============================================================================
# ZH: 排程器生命週期控制
# EN: Scheduler lifecycle control
# ==============================================================================

async def start_scheduler():
    global _scheduler_task, _lab_scan_task, _storage_scan_task, _scheduler_running
    _scheduler_running = True
    _scheduler_task    = asyncio.create_task(_timeout_cleanup_loop())
    _lab_scan_task     = asyncio.create_task(_lab_session_scan_loop())
    _storage_scan_task = asyncio.create_task(_storage_lifecycle_loop())
    logger.info("ZH: 排程器背景工作已啟動 (timeout + lab + storage) | EN: Scheduler started (3 tasks)")


async def stop_scheduler():
    global _scheduler_task, _lab_scan_task, _storage_scan_task, _scheduler_running
    _scheduler_running = False
    for task in (_scheduler_task, _lab_scan_task, _storage_scan_task):
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
    logger.info("ZH: 排程器已停止 | EN: Scheduler stopped")
