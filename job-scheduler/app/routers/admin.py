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
    result = []
    for j in jobs:
        d = dict(j.__dict__)
        d.pop('_sa_instance_state', None)
        result.append(d)
    return result

@router.get("/models")
def get_all_models(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
) -> Any:
    verify_admin(current_user)
    mdls = db.query(models.Model).order_by(models.Model.created_at.desc()).all()
    result = []
    for m in mdls:
        d = dict(m.__dict__)
        d.pop('_sa_instance_state', None)
        result.append(d)
    return result

@router.get("/cluster/stats")
def get_cluster_stats(
    current_user: models.User = Depends(get_current_user)
) -> Any:
    verify_admin(current_user)
    # ZH: 目前為 Pull 模式，若無即時收集機制，可回傳空陣列 | EN: Pull mode, return empty list
    return []


@router.put("/users/{user_id}")
def admin_update_user(
    user_id: str,
    update_data: schemas.AdminUserUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
) -> Any:
    """ZH: 管理員修改使用者資訊 | EN: Admin update user details"""
    verify_admin(current_user)
    
    db_user = db.query(models.User).filter(models.User.id == user_id).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")
    
    if update_data.email is not None:
        db_user.email = update_data.email
    if update_data.role is not None:
        db_user.role = update_data.role
    if update_data.is_active is not None:
        db_user.is_active = update_data.is_active
    if update_data.password is not None and update_data.password.strip():
        db_user.hashed_password = crud.get_password_hash(update_data.password)
    
    # Token limit update
    if update_data.tokens_limit is not None:
        usage = crud.get_token_usage(db, user_id)
        if usage:
            usage.tokens_limit = update_data.tokens_limit
    
    db.commit()
    db.refresh(db_user)
    
    usage = crud.get_token_usage(db, user_id)
    return {
        "id": db_user.id,
        "username": db_user.username,
        "email": db_user.email,
        "role": db_user.role,
        "is_active": db_user.is_active,
        "tokens_used": usage.tokens_used if usage else 0,
        "tokens_limit": usage.tokens_limit if usage else 0
    }


@router.put("/users/batch/tokens")
def batch_update_token_limit(
    new_limit: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
) -> Any:
    """ZH: 批量更新所有使用者的 Token 月度上限 | EN: Batch update all users' monthly token limit"""
    verify_admin(current_user)
    
    updated = db.query(models.TokenUsage).update(
        {models.TokenUsage.tokens_limit: new_limit}
    )
    db.commit()
    return {"updated_count": updated, "new_limit": new_limit}


@router.post("/users/{user_id}/delete")
def admin_delete_user(
    user_id: str,
    payload: schemas.AdminDeleteUser,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
) -> Any:
    """ZH: 管理員刪除使用者 (需驗證密碼) | EN: Admin delete user (requires password)"""
    verify_admin(current_user)
    
    # ZH: 驗證管理員密碼 | EN: Verify admin password
    if not crud.verify_password(payload.admin_password, current_user.hashed_password):
        raise HTTPException(status_code=403, detail="Invalid admin password")
    
    # ZH: 禁止刪除自己 | EN: Cannot delete self
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")
    
    db_user = db.query(models.User).filter(models.User.id == user_id).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # ZH: 刪除關聯的 Token 用量記錄 | EN: Delete associated token usage
    db.query(models.TokenUsage).filter(models.TokenUsage.user_id == user_id).delete()
    # ZH: 刪除使用者 | EN: Delete user
    db.delete(db_user)
    db.commit()
    
    return {"message": f"User {db_user.username} deleted", "deleted_id": user_id}


@router.post("/verify")
def admin_verify_action(
    payload: schemas.AdminVerify,
    current_user: models.User = Depends(get_current_user)
) -> Any:
    """ZH: 管理員權限動作驗證 (解鎖編輯等) | EN: Admin action verification (e.g. unlock edit)"""
    verify_admin(current_user)
    
    # ZH: 驗證管理員密碼 | EN: Verify admin password
    if not crud.verify_password(payload.admin_password, current_user.hashed_password):
        raise HTTPException(status_code=403, detail="Invalid admin password")
        
    return {"message": "Verification successful"}

@router.post("/users/provision")
def provision_user(
    data: schemas.AdminProvisionUser,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
) -> Any:
    """ZH: 管理員初始化帳號（預先建立，待 SSO 接管）| EN: Admin provision user account"""
    verify_admin(current_user)
    
    # ZH: 檢查重複 | EN: Check duplicates
    if crud.get_user_by_username(db, data.username):
        raise HTTPException(status_code=400, detail="Username already exists")
    if crud.get_user_by_email(db, data.email):
        raise HTTPException(status_code=400, detail="Email already exists")
    
    # ZH: 產生臨時密碼 | EN: Generate temp password
    import secrets
    temp_password = secrets.token_urlsafe(12)
    
    # ZH: 建立使用者 | EN: Create user
    user_create = schemas.UserCreate(
        username=data.username,
        email=data.email,
        password=temp_password,
        role=data.role or "student"
    )
    db_user = crud.create_user(db, user_create)
    db_user.is_test_account = 1
    db.commit()
    
    return {
        "id": db_user.id,
        "username": db_user.username,
        "email": db_user.email,
        "role": db_user.role,
        "temp_password": temp_password
    }


@router.post("/users/{user_id}/reset")
def reset_user_account(
    user_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
) -> Any:
    """ZH: 初始化帳號 — 重置密碼 + 歸零 Token 用量 | EN: Initialize account — reset password + clear token usage"""
    verify_admin(current_user)
    
    db_user = db.query(models.User).filter(models.User.id == user_id).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # ZH: 產生新臨時密碼 | EN: Generate new temp password
    import secrets
    temp_password = secrets.token_urlsafe(12)
    db_user.hashed_password = crud.get_password_hash(temp_password)
    
    # ZH: 歸零 Token 用量 | EN: Clear token usage
    usage = crud.get_token_usage(db, user_id)
    if usage:
        usage.tokens_used = 0
    
    db.commit()
    
    return {
        "username": db_user.username,
        "temp_password": temp_password,
        "message": f"Account {db_user.username} has been initialized"
    }
