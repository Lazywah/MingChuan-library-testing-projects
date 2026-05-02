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
        # ZH: 未來可在此加入超時任務的清理邏輯
        # EN: Timeout cleanup logic can be added here in the future
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
