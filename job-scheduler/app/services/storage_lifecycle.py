"""
==============================================================================
Service: 使用者儲存生命週期狀態機 | User Storage Lifecycle State Machine
==============================================================================
ZH: 用途：管理使用者 home volume 從 active 到 archive / pending_delete 的轉換
    狀態：active → frozen → archived → pending_delete
    永不自動硬刪：pending_delete 仍需 admin 二次確認 + 密碼

EN: Purpose: Manage user home-volume lifecycle from active to archive/delete
    States: active → frozen → archived → pending_delete
    Never auto-delete: pending_delete still requires admin re-confirmation

ZH: 學期保護：scheduler_policy.yaml 中 academic_calendar 控制是否執行歸檔/刪除
EN: Academic protection: academic_calendar in yaml controls archive/delete eligibility
==============================================================================
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tarfile
from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from .. import models
from ..config import SCHEDULER_POLICY
from . import quota_service

logger = logging.getLogger(__name__)


# ==============================================================================
# ZH: 學期日曆判斷 | Academic calendar check
# ==============================================================================

def is_archival_allowed_today() -> bool:
    """
    ZH: 今日是否在「允許執行歸檔 / 刪除」的月份內（暑假）
    EN: Is today within the archival months (typically July-August)?
    """
    cal = SCHEDULER_POLICY.get("academic_calendar", {})
    archival_months = cal.get("archival_months", [7, 8])
    return datetime.now(timezone.utc).month in archival_months


def is_semester_today() -> bool:
    """
    ZH: 今日是否在學期月份內（保護學生資料）
    EN: Is today within a semester month (data is protected)
    """
    cal = SCHEDULER_POLICY.get("academic_calendar", {})
    semester_months = cal.get("semester_months", [9, 10, 11, 12, 1, 2, 3, 4, 5, 6])
    return datetime.now(timezone.utc).month in semester_months


# ==============================================================================
# ZH: 狀態取得 / 建立 | State get/init
# ==============================================================================

def get_or_create_state(db: Session, user_id: str) -> models.UserStorageState:
    """ZH: 取得或建立 storage state | EN: Get or create storage state"""
    state = db.query(models.UserStorageState).filter(
        models.UserStorageState.user_id == user_id
    ).first()
    if state is None:
        state = models.UserStorageState(
            user_id=user_id,
            state="active",
            state_since=datetime.now(timezone.utc),
            current_size_gb=0.0,
        )
        db.add(state)
        db.commit()
        db.refresh(state)
    return state


def list_states(db: Session, filter_state: Optional[str] = None) -> list[dict]:
    """ZH: 列出所有使用者儲存狀態，供 admin Lab「儲存生命週期」面板。
       EN: List all user storage states for the admin Lab storage panel."""
    q = db.query(models.UserStorageState)
    if filter_state and filter_state not in ("all", ""):
        q = q.filter(models.UserStorageState.state == filter_state)
    out: list[dict] = []
    for s in q.all():
        out.append({
            "user_id": s.user_id,
            "state": s.state,
            "current_size_gb": s.current_size_gb,
            "state_since": s.state_since.isoformat() if s.state_since else None,
            "archive_path": s.archive_path,
            "notes": s.notes,
        })
    return out


# ==============================================================================
# ZH: 狀態轉換 | State transitions
# ==============================================================================

def freeze(db: Session, user_id: str, admin_id: Optional[str] = None,
           reason: str = "manual") -> bool:
    """
    ZH: 將使用者切到 frozen 狀態（唯讀模式）
    EN: Move user to frozen state (read-only mode)

    觸發場景：
        - 超過配額
        - 90 天未登入
        - admin 手動
    """
    state = get_or_create_state(db, user_id)
    if state.state == "frozen":
        return False
    old_state = state.state
    state.state = "frozen"
    state.state_since = datetime.now(timezone.utc)
    state.notes = f"frozen ({reason}) at {state.state_since.isoformat()}"

    if admin_id:
        _log_admin_action(db, admin_id, user_id, "freeze",
                          {"old_state": old_state, "reason": reason})

    db.commit()
    logger.info("User %s storage state: %s → frozen (reason=%s)",
                user_id[:8], old_state, reason)
    # TODO: 實際暫停容器、移除寫入權限（v2.0 透過 Docker 重啟以唯讀掛載實現）
    return True


def archive(db: Session, user_id: str, admin_id: Optional[str] = None,
            reason: str = "manual") -> bool:
    """
    ZH: 將 frozen 使用者歸檔到 HDD（壓縮 tar.gz）
    EN: Archive a frozen user to HDD as compressed tar.gz

    學期中（semester_months）禁止執行此轉換
    Not allowed during semester months
    """
    if not is_archival_allowed_today() and not admin_id:
        logger.info("Archive skipped for %s (in semester, no admin override)",
                    user_id[:8])
        return False

    state = get_or_create_state(db, user_id)
    if state.state != "frozen":
        logger.warning("Cannot archive: user %s not in frozen state (current=%s)",
                       user_id[:8], state.state)
        return False

    # ZH: 實際歸檔（v2.0 為 stub，需配合宿主機 archive 目錄）
    # EN: Actual archival (v2.0 stub, requires host archive dir)
    archive_dir = os.environ.get("AIBASE_ARCHIVE_DIR", "/data/archive")
    try:
        os.makedirs(archive_dir, exist_ok=True)
    except OSError:
        pass
    archive_path = os.path.join(archive_dir, f"home_{user_id}.tar.gz")

    state.state = "archived"
    state.state_since = datetime.now(timezone.utc)
    state.archive_path = archive_path
    state.notes = f"archived ({reason}) → {archive_path}"

    if admin_id:
        _log_admin_action(db, admin_id, user_id, "archive",
                          {"reason": reason, "archive_path": archive_path})

    db.commit()
    logger.info("User %s archived → %s", user_id[:8], archive_path)
    # TODO: 實際 docker run --rm -v home_<uid>:/src -v archive:/dest alpine tar czf ...
    return True


def restore(db: Session, user_id: str, admin_id: str) -> bool:
    """
    ZH: 從 archived 還原為 active（管理員操作）
    EN: Restore archived user back to active (admin op)
    """
    state = get_or_create_state(db, user_id)
    if state.state not in ("archived", "frozen", "pending_delete"):
        return False

    old_state = state.state
    state.state = "active"
    state.state_since = datetime.now(timezone.utc)
    state.notes = f"restored from {old_state} by admin {admin_id[:8]}"

    _log_admin_action(db, admin_id, user_id, "restore",
                      {"old_state": old_state, "archive_path": state.archive_path})

    db.commit()
    logger.info("User %s restored from %s to active by admin %s",
                user_id[:8], old_state, admin_id[:8])
    return True


def mark_pending_delete(db: Session, user_id: str, admin_id: str,
                       reason: str = "manual") -> bool:
    """
    ZH: 將使用者標記為 pending_delete，等待 admin 二次確認真正刪除
    EN: Mark user as pending_delete; waiting for admin re-confirmation
    """
    state = get_or_create_state(db, user_id)
    old_state = state.state
    state.state = "pending_delete"
    state.state_since = datetime.now(timezone.utc)
    state.notes = f"pending delete ({reason}) — requires admin confirmation"

    _log_admin_action(db, admin_id, user_id, "mark_pending_delete",
                      {"old_state": old_state, "reason": reason})
    db.commit()
    logger.warning("User %s marked pending_delete by admin %s",
                   user_id[:8], admin_id[:8])
    return True


def permanent_delete(db: Session, user_id: str, admin_id: str,
                     admin_password_verified: bool) -> bool:
    """
    ZH: 永久刪除（需先通過 admin 二次驗證）
    EN: Permanent delete (requires admin re-verification)

    Args:
        admin_password_verified: 必須先呼叫 /api/v1/admin/verify 取得 True
    """
    if not admin_password_verified:
        raise PermissionError("Admin password re-verification required for permanent delete")

    state = get_or_create_state(db, user_id)
    if state.state != "pending_delete":
        raise ValueError(f"User must be in pending_delete state (current: {state.state})")

    # ZH: dump metadata 到 audit log（刪除前最後快照）
    # EN: Dump metadata to audit log (last snapshot before delete)
    _log_admin_action(db, admin_id, user_id, "permanent_delete", {
        "archive_path": state.archive_path,
        "current_size_gb": state.current_size_gb,
        "state_since": state.state_since.isoformat() if state.state_since else None,
        "notes": state.notes,
    })

    # ZH: 標為已刪除（保留 audit），實際磁碟刪除由運維人員執行
    # EN: Mark as deleted (audit preserved); actual disk wipe by ops
    state.state = "deleted"
    state.state_since = datetime.now(timezone.utc)
    state.notes = f"PERMANENTLY DELETED by admin {admin_id[:8]} at {state.state_since.isoformat()}"
    db.commit()

    logger.critical("PERMANENT DELETE executed: user %s by admin %s",
                    user_id[:8], admin_id[:8])
    return True


# ==============================================================================
# ZH: 背景掃描 — 每日 03:00 執行
# EN: Background scan — runs daily at 03:00
# ==============================================================================

def daily_scan(db: Session) -> dict:
    """
    ZH: 每日狀態轉換掃描；學期中只執行 active → frozen，暑假執行完整轉換
    EN: Daily state-transition scan; semester = only active→frozen,
        summer = full chain

    Returns: 統計 dict
    """
    stats = {"active_to_frozen": 0, "frozen_to_archived": 0,
             "archived_to_pending_delete": 0}
    now = datetime.now(timezone.utc)
    in_semester = is_semester_today()

    # ZH: active → frozen（學期中也執行：超配額或 90 天未登入）
    # EN: active → frozen (active even in semester: over-quota or 90d inactive)
    users = db.query(models.User).all()
    for user in users:
        if user.role == "teacher":          # 教師例外，預設不歸檔
            continue
        state = get_or_create_state(db, user.id)
        if state.state != "active":
            continue
        effective_quota = quota_service.get_effective_quota_gb(db, user.id)

        # 超配額觸發
        if state.current_size_gb > effective_quota:
            freeze(db, user.id, reason="quota_exceeded")
            stats["active_to_frozen"] += 1
            continue

        # 90 天未登入觸發
        if user.last_login_time:
            last = user.last_login_time
            if last.tzinfo is None:
                last = last.replace(tzinfo=timezone.utc)
            if (now - last) > timedelta(days=90):
                freeze(db, user.id, reason="inactive_90d")
                stats["active_to_frozen"] += 1

    # ZH: 學期中不再執行更深的轉換
    # EN: Don't run deeper transitions during semester
    if in_semester:
        logger.info("daily_scan in semester — stopped at active→frozen: %s", stats)
        return stats

    # ZH: frozen → archived（30 天無動作）
    # EN: frozen → archived (30 days no activity)
    frozen_states = db.query(models.UserStorageState).filter(
        models.UserStorageState.state == "frozen"
    ).all()
    for s in frozen_states:
        state_since = s.state_since
        if state_since and state_since.tzinfo is None:
            state_since = state_since.replace(tzinfo=timezone.utc)
        if state_since and (now - state_since) > timedelta(days=30):
            archive(db, s.user_id, reason="frozen_30d_no_action")
            stats["frozen_to_archived"] += 1

    # ZH: archived → pending_delete（1 年無動作；不自動執行，僅標記）
    # EN: archived → pending_delete (1 year no action; only flag, never auto-delete)
    archived_states = db.query(models.UserStorageState).filter(
        models.UserStorageState.state == "archived"
    ).all()
    for s in archived_states:
        state_since = s.state_since
        if state_since and state_since.tzinfo is None:
            state_since = state_since.replace(tzinfo=timezone.utc)
        if state_since and (now - state_since) > timedelta(days=365):
            # 不呼叫 mark_pending_delete（那需要 admin_id），改直接設 state
            s.state = "pending_delete"
            s.state_since = now
            s.notes = f"auto-flagged pending_delete after 1 year archived (awaiting admin)"
            db.commit()
            stats["archived_to_pending_delete"] += 1

    logger.info("daily_scan summary: %s", stats)
    return stats


# ==============================================================================
# ZH: Audit log 寫入 | Audit log helper
# ==============================================================================

def _log_admin_action(db: Session, admin_id: str, target_user: Optional[str],
                      action: str, payload: dict) -> None:
    """ZH: 寫一筆 admin_actions 記錄 | EN: Write admin_actions row"""
    import json
    db.add(models.AdminAction(
        admin_id=admin_id,
        target_user=target_user,
        action=action,
        payload=json.dumps(payload, ensure_ascii=False),
        timestamp=datetime.now(timezone.utc),
    ))
    db.commit()
