"""
==============================================================================
Router: 公告路由群組 (Announcements Routes) — v2.2 新增
==============================================================================
ZH: 用途：管理首頁公告（admin 編輯、user 觀看）
EN: Manage homepage announcements (admin edits, users view)

ZH: 端點清單：
    GET    /api/v1/announcements             → 公告列表（user 用，僅 visible）
    GET    /api/v1/admin/announcements       → 全部公告（含隱藏，admin 用）
    POST   /api/v1/admin/announcements       → 新增公告
    PUT    /api/v1/admin/announcements/{id}  → 編輯
    DELETE /api/v1/admin/announcements/{id}  → 刪除

ZH: 認證：
    /announcements (GET)          → 公開，任何登入使用者可看
    /admin/announcements/*        → 需 admin 角色
==============================================================================
"""

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from .. import models, schemas
from ..auth import get_current_user
from ..database import get_db
from .admin import require_admin

logger = logging.getLogger(__name__)

router = APIRouter(tags=["公告 Announcements"])


@router.get("", response_model=list[schemas.AnnouncementResponse])
def list_announcements(
    limit: int = Query(20, ge=1, le=100, description="ZH: 最多回幾則 | EN: Max items"),
    db: Session = Depends(get_db),
    _: models.User = Depends(get_current_user),
) -> Any:
    """
    ZH: 公告列表（給 user UI 首頁用）
    EN: Announcement list (for user UI homepage)

    僅回 is_visible=1 的；置頂的排最前，其餘按 posted_at desc。
    """
    pinned = (
        db.query(models.Announcement)
        .filter(models.Announcement.is_visible == 1, models.Announcement.is_pinned == 1)
        .order_by(models.Announcement.posted_at.desc())
        .all()
    )
    normal = (
        db.query(models.Announcement)
        .filter(models.Announcement.is_visible == 1, models.Announcement.is_pinned == 0)
        .order_by(models.Announcement.posted_at.desc())
        .limit(max(0, limit - len(pinned)))
        .all()
    )
    return pinned + normal


# ==============================================================================
# Admin 子路由（掛在 /api/v1/admin/announcements）
# 因為 require_admin 在 admin.py 已定義，這裡複用
# ==============================================================================
admin_router = APIRouter(tags=["公告管理 Admin Announcements"])


@admin_router.get("", response_model=list[schemas.AnnouncementResponse])
def admin_list_announcements(
    include_hidden: bool = Query(True, description="ZH: 是否含隱藏 | EN: include hidden"),
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
) -> Any:
    """ZH: admin 看到的全部公告（含隱藏 / 草稿）"""
    q = db.query(models.Announcement)
    if not include_hidden:
        q = q.filter(models.Announcement.is_visible == 1)
    return q.order_by(
        models.Announcement.is_pinned.desc(),
        models.Announcement.posted_at.desc(),
    ).all()


@admin_router.post("", response_model=schemas.AnnouncementResponse, status_code=201)
def admin_create_announcement(
    payload: schemas.AnnouncementCreate,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin),
) -> Any:
    """ZH: 新增公告"""
    a = models.Announcement(
        title=payload.title,
        body=payload.body,
        posted_by=current_admin.id,
        is_pinned=payload.is_pinned,
        is_visible=payload.is_visible,
    )
    db.add(a); db.commit(); db.refresh(a)
    return a


@admin_router.put("/{ann_id}", response_model=schemas.AnnouncementResponse)
def admin_update_announcement(
    ann_id: int,
    payload: schemas.AnnouncementCreate,
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
) -> Any:
    """ZH: 編輯公告"""
    a = db.query(models.Announcement).filter(models.Announcement.id == ann_id).first()
    if not a:
        raise HTTPException(status_code=404, detail="Announcement not found")
    a.title = payload.title
    a.body = payload.body
    a.is_pinned = payload.is_pinned
    a.is_visible = payload.is_visible
    db.commit(); db.refresh(a)
    return a


@admin_router.delete("/{ann_id}", status_code=204)
def admin_delete_announcement(
    ann_id: int,
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
) -> None:
    """ZH: 刪除公告"""
    a = db.query(models.Announcement).filter(models.Announcement.id == ann_id).first()
    if not a:
        raise HTTPException(status_code=404, detail="Announcement not found")
    db.delete(a); db.commit()
