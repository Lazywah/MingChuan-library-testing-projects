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
from . import models, crud

logger = logging.getLogger(__name__)

_scheduler_running = False
_scheduler_task = None
_lab_scan_task = None        # v2.0: 每分鐘掃描 lab session idle/hard-limit
_storage_scan_task = None    # v2.0: 每日 03:00 執行儲存生命週期掃描
_myai_sync_task = None       # v2.8: 每 N 小時 headless 同步 myai168 帳號/Token
_myai_balance_task = None    # v2.8: 每 N 分輕量輪詢交易日誌更新餘額（低點數提醒用）

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
        # v3.1 step 6：逾時分鐘改 runtime 讀 SystemConfig（admin 可即時調），.env 為 fallback
        timeout_min = crud.get_setting(db, "job_timeout_minutes")
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=timeout_min)

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
                f"Timeout: job exceeded {timeout_min} minutes without completion. "
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

                # ZH: v3.3 每日一併做兩件保留期清理（掛在既有每日任務，不另開背景迴圈）
                #   1. 逾期的 Lab 封存 volume → 真正銷毀
                #   2. 逾期/已確認修改的 MYAI 初始密碼 → 清除密文
                # EN: v3.3 daily retention purges (piggyback on the existing daily task)
                try:
                    from .services import lab_manager as _lm
                    n = _lm.purge_expired_archives(db)
                    if n:
                        logger.info(f"ZH: 已銷毀 {n} 筆逾期 Lab 封存")
                except Exception as e:  # noqa: BLE001
                    logger.error(f"ZH: Lab 封存清理錯誤: {e}")
                try:
                    from .services import myai_sync as _ms
                    days = crud.get_setting(db, "myai_init_pwd_days")
                    _ms.purge_expired_initial_passwords(db, days)
                except Exception as e:  # noqa: BLE001
                    logger.error(f"ZH: MYAI 初始密碼清理錯誤: {e}")
            finally:
                db.close()
        except Exception as e:
            logger.error(f"ZH: 儲存生命週期掃描錯誤 | EN: Storage scan error: {e}", exc_info=True)

    logger.info("ZH: 儲存生命週期迴圈已停止")


# ==============================================================================
# ZH: v2.8 MYAI 廠商平台自動同步迴圈（每 N 小時，唯讀）
# EN: v2.8 MYAI vendor auto-sync loop (every N hours, read-only)
# ==============================================================================

async def _myai_sync_loop():
    """ZH: headless 同步 myai168 帳號/Token。帳密未設則不啟用（帳密是 .env，非 runtime）。
       v3.1 step 6：同步間隔改由 SystemConfig(myai_sync_interval_hours) 每輪重讀，admin 可即時調；
       設為 0＝暫停（迴圈仍在，每 5 分鐘回看是否被重新啟用）。失敗只記 log，不影響其他排程。"""
    from .config import settings
    if not (settings.MYAI_ADMIN_EMAIL and settings.MYAI_ADMIN_PASSWORD):
        logger.info("ZH: MYAI 自動同步未啟用（帳密未設）")
        return
    logger.info("ZH: MYAI 自動同步迴圈啟動（間隔由 SystemConfig 即時控制）")
    from .services import myai_sync

    PAUSE_RECHECK_SECONDS = 300  # ZH: 間隔=0(暫停)時，每 5 分鐘回頭看有沒有被重新啟用

    # ZH: 開機先等服務穩定再首次同步 | EN: initial delay so services settle
    try:
        await asyncio.sleep(60)
    except asyncio.CancelledError:
        return

    while _scheduler_running:
        db = SessionLocal()
        try:
            interval_hours = crud.get_setting(db, "myai_sync_interval_hours")
            if interval_hours <= 0:
                sleep_s = PAUSE_RECHECK_SECONDS   # ZH: 暫停中，稍後回看
            else:
                try:
                    res = await myai_sync.sync(db)
                    logger.info(f"ZH: MYAI 自動同步完成 | EN: MYAI auto-sync done: {res}")
                except Exception as e:  # noqa: BLE001
                    logger.error(f"ZH: MYAI 自動同步錯誤 | EN: MYAI auto-sync error: {e}")
                sleep_s = interval_hours * 3600
        finally:
            db.close()
        try:
            await asyncio.sleep(sleep_s)
        except asyncio.CancelledError:
            break

    logger.info("ZH: MYAI 自動同步迴圈已停止")


async def _myai_balance_loop():
    """ZH: 每 MYAI_BALANCE_POLL_MINUTES 分鐘，輕量抓近 MYAI_BALANCE_POLL_DAYS 天交易日誌，
       更新各人餘額（供低點數提醒即時判斷）。一個請求涵蓋全體、cookie 重用故成本低。
       帳密未設或間隔<=0 則不啟用。失敗只記 log。"""
    from .config import settings
    if not (settings.MYAI_ADMIN_EMAIL and settings.MYAI_ADMIN_PASSWORD) or settings.MYAI_BALANCE_POLL_MINUTES <= 0:
        logger.info("ZH: MYAI 餘額輪詢未啟用（帳密未設或 MYAI_BALANCE_POLL_MINUTES=0）")
        return
    interval = settings.MYAI_BALANCE_POLL_MINUTES * 60
    days = max(1, settings.MYAI_BALANCE_POLL_DAYS)
    logger.info(f"ZH: MYAI 餘額輪詢迴圈啟動 (每 {settings.MYAI_BALANCE_POLL_MINUTES}m, 近 {days}d)")
    from .services import myai_sync

    try:
        await asyncio.sleep(90)   # 開機後晚一點啟動，錯開首次全量同步
    except asyncio.CancelledError:
        return

    # ZH: v3.4 依「平台是否有非 admin 使用者在線」調整節奏：
    #       有人在線 → 用較短的 active 間隔（四象限更即時）
    #       沒人在線 → **完全跳過請求**，每 IDLE_RECHECK 回頭看一眼有沒有人上線
    #     ⚠️ 廠商的交易日誌是「一次撈全體」（無分頁），故**不能**改成「只查在線者」——
    #        那會變成 N 個請求，反而更貴。正確省法是「沒人時不發請求」。
    # EN: v3.4 adaptive cadence — poll faster while users are online, skip entirely when
    #     nobody is. (The vendor log is fetched all-users-at-once; per-user filtering
    #     would multiply requests instead of reducing them.)
    IDLE_RECHECK_SECONDS = 300
    while _scheduler_running:
        sleep_s = interval
        try:
            db = SessionLocal()
            try:
                if not myai_sync.has_online_users(db):
                    sleep_s = IDLE_RECHECK_SECONDS
                    logger.debug("ZH: 平台無使用者在線，略過本輪 MYAI 輪詢")
                else:
                    active_min = crud.get_setting(db, "myai_active_poll_minutes")
                    res = await myai_sync.sync_transactions(db, days=days)
                    logger.debug(f"ZH: MYAI 餘額輪詢: {res}")
                    sleep_s = max(60, int(active_min) * 60)
            finally:
                db.close()
        except Exception as e:  # noqa: BLE001
            logger.warning(f"ZH: MYAI 餘額輪詢錯誤（略過）: {e}")
        try:
            await asyncio.sleep(sleep_s)
        except asyncio.CancelledError:
            break

    logger.info("ZH: MYAI 餘額輪詢迴圈已停止")


# ==============================================================================
# ZH: 排程器生命週期控制
# EN: Scheduler lifecycle control
# ==============================================================================

async def start_scheduler():
    global _scheduler_task, _lab_scan_task, _storage_scan_task, _myai_sync_task, _myai_balance_task, _scheduler_running
    _scheduler_running = True
    _scheduler_task    = asyncio.create_task(_timeout_cleanup_loop())
    _lab_scan_task     = asyncio.create_task(_lab_session_scan_loop())
    _storage_scan_task = asyncio.create_task(_storage_lifecycle_loop())
    _myai_sync_task    = asyncio.create_task(_myai_sync_loop())
    _myai_balance_task = asyncio.create_task(_myai_balance_loop())
    logger.info("ZH: 排程器背景工作已啟動 (timeout + lab + storage + myai + myai餘額) | EN: Scheduler started (5 tasks)")


async def stop_scheduler():
    global _scheduler_task, _lab_scan_task, _storage_scan_task, _myai_sync_task, _myai_balance_task, _scheduler_running
    _scheduler_running = False
    for task in (_scheduler_task, _lab_scan_task, _storage_scan_task, _myai_sync_task, _myai_balance_task):
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
    logger.info("ZH: 排程器已停止 | EN: Scheduler stopped")
