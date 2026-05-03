"""
==============================================================================
Module 8: 背景排程器 (Background Job Scheduler)
==============================================================================
ZH: 用途：過去負責 SSH 推播任務，現已改為 Worker Agent (Pull) 模式。
    此模組保留供未來擴充（例如：定時清理超時任務）。
EN: Purpose: Previously handled SSH push, now replaced by Worker Agent (Pull).
    Retained for future expansions (e.g., timeout cleanup).
==============================================================================
"""

import asyncio
import logging
from typing import Optional

from .config import settings, SCHEDULER_POLICY
from .database import SessionLocal
from . import crud

logger = logging.getLogger(__name__)

async def _scheduler_loop():
    """
    ZH: 排程器主迴圈 (目前閒置，因為任務改由 Worker Agent 主動 Pull)
    EN: Scheduler main loop (currently idle, tasks are pulled by Worker Agent)
    """
    global _scheduler_running
    logger.info("ZH: 排程器啟動 (Pull 模式下僅作佔位) | EN: Scheduler started (Idle in Pull mode)")

    while _scheduler_running:
        try:
            db = SessionLocal()
            from . import models
            from datetime import datetime, timedelta
            from sqlalchemy import or_, and_
            
            # ZH: 清理超過 5 分鐘未活動的測試帳號 | EN: Clean up test accounts inactive for > 5 mins
            cutoff_time = datetime.utcnow() - timedelta(minutes=5)
            
            stale_users = db.query(models.User).filter(
                models.User.is_test_account == 1,
                or_(
                    and_(models.User.last_login_time.isnot(None), models.User.last_login_time < cutoff_time),
                    and_(models.User.last_login_time.is_(None), models.User.created_at < cutoff_time)
                )
            ).all()
            
            for u in stale_users:
                db.query(models.TokenUsage).filter(models.TokenUsage.user_id == u.id).delete()
                db.delete(u)
                logger.info(f"ZH: 自動刪除超時測試帳號: {u.username} | EN: Auto-deleted inactive test account: {u.username}")
                
            if stale_users:
                db.commit()
            db.close()
        except Exception as e:
            logger.error(f"ZH: 排程器清理錯誤: {e} | EN: Scheduler cleanup error: {e}")

        await asyncio.sleep(60)

    logger.info("ZH: 排程器已停止 | EN: Scheduler stopped")


# ==============================================================================
# ZH: 排程器生命週期控制
# EN: Scheduler lifecycle control
# ==============================================================================

async def start_scheduler():
    global _scheduler_task, _scheduler_running
    _scheduler_running = True
    _scheduler_task = asyncio.create_task(_scheduler_loop())
    logger.info(f"ZH: 排程器背景工作已啟動 | EN: Scheduler background task started")


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
