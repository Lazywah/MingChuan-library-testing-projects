from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Any
import logging

from .. import models, schemas, crud
from ..auth import get_current_user
from ..database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(tags=["管理員 Admin"])

def verify_admin(current_user: models.User):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Forbidden: Admins only")

@router.get("/users")
def get_all_users(
    db: Session = Depends(get_db), 
    current_user: models.User = Depends(get_current_user)
) -> Any:
    verify_admin(current_user)
    users = db.query(models.User).order_by(models.User.created_at.desc()).all()
    # 手動加上 Token 狀態
    result = []
    for u in users:
        usage = crud.get_token_usage(db, u.id)
        u_dict = {
            "id": u.id,
            "username": u.username,
            "email": u.email,
            "role": u.role,
            "is_active": u.is_active,
            "online_status": u.online_status,
            "last_login_time": u.last_login_time,
            "last_login_ip": u.last_login_ip,
            "created_at": u.created_at,
            "tokens_used": usage.tokens_used if usage else 0,
            "tokens_limit": usage.tokens_limit if usage else 0
        }
        result.append(u_dict)
    return result

@router.get("/jobs")
def get_all_jobs(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
) -> Any:
    verify_admin(current_user)
    jobs = db.query(models.TrainingJob).order_by(models.TrainingJob.created_at.desc()).all()
    return jobs

@router.get("/models")
def get_all_models(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
) -> Any:
    verify_admin(current_user)
    mdls = db.query(models.Model).order_by(models.Model.created_at.desc()).all()
    return mdls

@router.get("/cluster/stats")
def get_cluster_stats(
    current_user: models.User = Depends(get_current_user)
) -> Any:
    verify_admin(current_user)
    # ZH: 目前為 Pull 模式，若無即時收集機制，可回傳空陣列 | EN: Pull mode, return empty list
    return []
