"""
==============================================================================
Service: 配額管理 + Session 累積時長 | Quota & Session Usage
==============================================================================
ZH: 用途：
    1. 計算使用者有效配額（base + 未過期/未撤銷的 quota_grants）
    2. 追蹤每日 session 使用秒數，提供「今日可用 / 已用」查詢
    3. Lab Manager 啟動 session 前的配額檢查

EN: Purpose:
    1. Compute effective quota (base + active grants)
    2. Track daily session usage; provides today's quota check
    3. Pre-flight check before Lab Manager starts a session
==============================================================================
"""

from __future__ import annotations

import logging
from datetime import datetime, date, timezone
from typing import Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from .. import models
from ..config import SCHEDULER_POLICY

logger = logging.getLogger(__name__)


# ==============================================================================
# ZH: 配額計算 | Quota calculation
# ==============================================================================

def get_base_quota_gb(role: str) -> int:
    """
    ZH: 從 scheduler_policy.yaml 取得角色預設配額
    EN: Read role-default quota from scheduler_policy.yaml
    """
    defaults = SCHEDULER_POLICY.get("default_disk_quota_gb", {})
    fallback = {"student": 10, "teacher": 50, "admin": 100}
    return int(defaults.get(role, fallback.get(role, 10)))


def get_effective_quota_gb(db: Session, user_id: str) -> int:
    """
    ZH: 計算使用者有效配額 = User.disk_quota_gb + 仍生效的 QuotaGrant 總和
    EN: Effective quota = User.disk_quota_gb + sum(active QuotaGrants)

    生效條件 / Active conditions:
        - revoked_at IS NULL
        - expires_at IS NULL OR expires_at > now
    """
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        return 0

    base = user.disk_quota_gb if user.disk_quota_gb is not None else get_base_quota_gb(user.role)

    now = datetime.now(timezone.utc)
    extra = sum(
        g.extra_quota_gb for g in db.query(models.QuotaGrant).filter(
            models.QuotaGrant.user_id == user_id,
            models.QuotaGrant.revoked_at.is_(None),
            or_(
                models.QuotaGrant.expires_at.is_(None),
                models.QuotaGrant.expires_at > now,
            ),
        ).all()
    )

    return base + extra


def grant_quota(
    db: Session,
    user_id: str,
    granted_by: str,
    extra_quota_gb: int,
    reason: str,
    expires_at: Optional[datetime] = None,
) -> models.QuotaGrant:
    """
    ZH: 新增配額提權紀錄
    EN: Create a new quota grant
    """
    if extra_quota_gb <= 0:
        raise ValueError("extra_quota_gb must be positive")
    if not reason or not reason.strip():
        raise ValueError("reason is required for audit")

    grant = models.QuotaGrant(
        user_id=user_id,
        granted_by=granted_by,
        extra_quota_gb=extra_quota_gb,
        reason=reason.strip(),
        expires_at=expires_at,
    )
    db.add(grant)
    db.commit()
    db.refresh(grant)
    logger.info(
        "Quota grant: +%d GB to user %s by admin %s (expires=%s)",
        extra_quota_gb, user_id[:8], granted_by[:8], expires_at,
    )
    return grant


def revoke_quota(db: Session, grant_id: str) -> bool:
    """
    ZH: 撤銷一筆配額提權（不刪除，保留審計）
    EN: Revoke a quota grant (soft delete, audit preserved)
    """
    grant = db.query(models.QuotaGrant).filter(models.QuotaGrant.id == grant_id).first()
    if not grant or grant.revoked_at is not None:
        return False
    grant.revoked_at = datetime.now(timezone.utc)
    db.commit()
    return True


def list_grants(db: Session, user_id: str, include_inactive: bool = False) -> list:
    """ZH: 列出某使用者的配額提權紀錄 | EN: List grants for a user"""
    q = db.query(models.QuotaGrant).filter(models.QuotaGrant.user_id == user_id)
    if not include_inactive:
        now = datetime.now(timezone.utc)
        q = q.filter(
            models.QuotaGrant.revoked_at.is_(None),
            or_(
                models.QuotaGrant.expires_at.is_(None),
                models.QuotaGrant.expires_at > now,
            ),
        )
    return q.order_by(models.QuotaGrant.granted_at.desc()).all()


# ==============================================================================
# ZH: Session 時間管理 | Session time management
# ==============================================================================

def get_session_limits(role: str) -> dict:
    """
    ZH: 取得角色對應的 session 時間限制（從 scheduler_policy.yaml）
    EN: Get session limits for role (from scheduler_policy.yaml)

    Returns:
        {"idle_timeout_min": 30 | None,
         "hard_limit_min":   90 | None,
         "daily_limit_min": 360 | None}
    """
    limits_map = SCHEDULER_POLICY.get("session_limits", {})
    fallback = {
        "student": {"idle_timeout_min": 30, "hard_limit_min": 90, "daily_limit_min": 360},
        "teacher": {"idle_timeout_min": 120, "hard_limit_min": None, "daily_limit_min": None},
        "admin":   {"idle_timeout_min": None, "hard_limit_min": None, "daily_limit_min": None},
    }
    return limits_map.get(role, fallback.get(role, fallback["student"]))


def get_today_usage(db: Session, user_id: str) -> models.UserSessionUsage:
    """
    ZH: 取得（或建立）今日的累積使用紀錄
    EN: Get or create today's UserSessionUsage row
    """
    today = date.today()
    row = db.query(models.UserSessionUsage).filter(
        models.UserSessionUsage.user_id == user_id,
        models.UserSessionUsage.date == today,
    ).first()
    if row is None:
        row = models.UserSessionUsage(
            user_id=user_id, date=today, total_seconds=0, session_count=0,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def can_start_session(db: Session, user_id: str) -> tuple[bool, str]:
    """
    ZH: 檢查使用者是否可開新 session（每日上限）
    EN: Check if user can start a new session (daily limit)

    Returns:
        (allowed: bool, reason: str)
    """
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        return False, "user_not_found"

    limits = get_session_limits(user.role)
    daily_limit_min = limits.get("daily_limit_min")
    if daily_limit_min is None:
        return True, ""

    usage = get_today_usage(db, user_id)
    if usage.total_seconds >= daily_limit_min * 60:
        return False, f"daily_limit_reached:{daily_limit_min}min"
    return True, ""


def increment_usage(db: Session, user_id: str, seconds: int) -> None:
    """
    ZH: 增加今日累積使用秒數（session 結束時呼叫）
    EN: Increment today's accumulated session seconds (call on session end)
    """
    if seconds <= 0:
        return
    usage = get_today_usage(db, user_id)
    usage.total_seconds = (usage.total_seconds or 0) + seconds
    usage.session_count = (usage.session_count or 0) + 1
    db.commit()


def get_today_remaining_minutes(db: Session, user_id: str) -> Optional[int]:
    """
    ZH: 取得今日剩餘可用分鐘（None = 不限制）
    EN: Today's remaining minutes (None = unlimited)
    """
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        return 0
    limits = get_session_limits(user.role)
    daily_limit_min = limits.get("daily_limit_min")
    if daily_limit_min is None:
        return None
    usage = get_today_usage(db, user_id)
    used_min = (usage.total_seconds or 0) // 60
    return max(0, daily_limit_min - used_min)
