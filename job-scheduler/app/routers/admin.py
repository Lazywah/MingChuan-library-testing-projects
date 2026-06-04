"""
==============================================================================
Router: 管理員路由群組 (Admin Routes)
==============================================================================
ZH: 用途：提供管理員專屬的使用者、任務、模型管理與數據分析端點
EN: Purpose: Admin-only endpoints for user/job/model management and analytics

ZH: 所有端點均需 JWT 認證且 role=admin，透過 require_admin Depends 強制執行
EN: All endpoints require JWT auth and role=admin, enforced via require_admin Depends

ZH: 端點清單：
    GET    /users                → 列出所有使用者（含 Token 狀態，JOIN 單查詢，支援分頁）
    PUT    /users/{id}           → 更新使用者（email/role/active/limit/password）
    PUT    /users/batch/tokens   → 批量設定 Token
    POST   /users/{id}/delete    → 刪除使用者（需驗管理員密碼）
    POST   /users/{id}/reset     → 初始化帳號（重置密碼 + 歸零用量）
    POST   /users/provision      → 配發新帳號
    POST   /verify               → 管理員密碼驗證
    GET    /jobs                 → 列出所有任務（支援分頁）
    POST   /jobs/{id}/cancel     → 強制取消任務
    PUT    /jobs/{id}/priority   → 調整任務優先級
    GET    /models               → 列出所有模型
    POST   /models               → 新增模型
    PUT    /models/{id}          → 更新模型
    DELETE /models/{id}          → 刪除模型
    GET    /cluster/stats        → 叢集 GPU 節點狀態（Worker heartbeat）
    GET    /analytics            → 數據分析（學系/工具分布）
==============================================================================
"""

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timezone
from typing import Any, Optional
import csv
import io
import logging

from .. import models, schemas, crud
from ..auth import get_current_user
from ..config import SSO_POLICY
from ..database import get_db
from ..services import email_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["管理員 Admin"])


# ==============================================================================
# ZH: 管理員身份驗證 Depends（取代舊的普通函式，確保注入鏈完整）
# EN: Admin auth Depends (replaces plain function to stay within FastAPI DI chain)
# ==============================================================================

def require_admin(current_user: models.User = Depends(get_current_user)) -> models.User:
    """ZH: 確保呼叫者為 admin，否則拋出 403 | EN: Ensure caller is admin, raise 403 otherwise"""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Forbidden: Admins only")
    return current_user


# ==============================================================================
# ZH: 使用者管理 | EN: User Management
# ==============================================================================

# v2.1 在線狀態修正：admin 不再讀 DB 內 online_status 欄位（會 stale），
# 改用 last_activity 動態計算「10 分鐘內活躍 = 在線」
from datetime import timedelta as _td
_ONLINE_THRESHOLD = _td(minutes=10)

def _compute_online(user: models.User) -> Optional[int]:
    """
    ZH: 用 last_activity 動態判斷在線
    EN: Compute online from last_activity

    v2.1 修正：admin 從未登入過 user UI（last_login_time 為 None）→ 回 None，
    讓 admin UI 顯示「—」而非誤導性的「離線」。
    admin 一旦登入過 user UI（即使後來離線），仍回 0/1 正常計算。
    """
    if user.role == "admin" and user.last_login_time is None:
        return None
    last = getattr(user, "last_activity", None)
    if not last:
        return 0
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    return 1 if (datetime.now(timezone.utc) - last) < _ONLINE_THRESHOLD else 0


def _yaml_mock_usernames() -> set:
    """
    ZH: 從 SSO_POLICY 抓出目前 yaml 內所有 mock SSO 帳號的 student_id 集合
    EN: Set of student_ids currently allowed via mock SSO in yaml

    v2.1: 用於 filter 已從 yaml 移除但 DB 仍有 row 的 sso_mock 使用者
    (保留 orphan row 不破壞既有聊天歷史 / 任務 FK，僅在列表中隱藏)
    """
    try:
        users = (SSO_POLICY or {}).get("mock", {}).get("users", []) or []
        return {str(u.get("student_id")) for u in users if u.get("student_id")}
    except Exception as e:
        logger.warning(f"_yaml_mock_usernames failed: {e}")
        return set()


@router.get("/users", response_model=list[schemas.AdminUserListItem])
def get_all_users(
    skip: int = Query(0, ge=0, description="ZH: 跳過筆數 | EN: Records to skip"),
    limit: int = Query(100, ge=1, le=500, description="ZH: 每頁筆數 | EN: Records per page"),
    auth_source: Optional[str] = Query(
        None,
        description=(
            "ZH: 依登入來源過濾（local / sso_oidc / sso_cas / sso_mock）"
            " | EN: Filter by auth_source"
        ),
    ),
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
) -> Any:
    """
    ZH: 列出所有使用者，單次 JOIN 查詢避免 N+1，支援分頁
    EN: List all users with token usage via single JOIN query, supports pagination

    v2.1 擴充：
    - 可用 ?auth_source=local|sso_oidc|sso_mock 過濾分類
    - sso_mock 帳號額外做 yaml filter：若 username 已從 sso_policy.yaml 移除則隱藏
    """
    query = (
        db.query(models.User, models.TokenUsage)
        .outerjoin(models.TokenUsage, models.TokenUsage.user_id == models.User.id)
    )
    if auth_source:
        query = query.filter(models.User.auth_source == auth_source)
    rows = (
        query.order_by(models.User.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )

    # v2.1 yaml filter: 若使用者已從 yaml 移除，從列表隱藏（DB row 仍保留）
    yaml_usernames = _yaml_mock_usernames()

    result = []
    for u, t in rows:
        if u.auth_source == "sso_mock" and u.username not in yaml_usernames:
            continue  # yaml 已移除 → 列表隱藏
        result.append(
            schemas.AdminUserListItem(
                id=u.id,
                username=u.username,
                email=u.email,
                role=u.role,
                is_active=u.is_active,
                online_status=_compute_online(u),  # v2.1: 動態計算
                last_login_time=u.last_login_time,
                last_login_ip=u.last_login_ip,
                department=u.department,
                created_at=u.created_at,
                tokens_used=t.tokens_used if t else 0,
                tokens_limit=t.tokens_limit if t else 0,
                auth_source=getattr(u, "auth_source", "local") or "local",  # v2.1: 3-tab 分頁
            )
        )
    return result


# ==============================================================================
# v2.2: 使用者管理 Excel/CSV 匯出（欄位 + 範圍 admin 可勾選）
# v2.2: User-management export to Excel/CSV (admin chooses columns + scope)
# ==============================================================================

# 欄位白名單 — 防止 admin 隨便丟未授權欄位名稱（避免存取 hashed_password 等敏感欄）
# Whitelist of allowed export columns — prevents injection of sensitive attribute names
_EXPORT_COLUMNS = {
    # key: (顯示標題, getter function)
    "username":            ("帳號名稱", lambda u, t: u.username),
    "email":               ("Email", lambda u, t: u.email),
    "role":                ("角色", lambda u, t: u.role),
    "auth_source":         ("登入來源", lambda u, t: getattr(u, "auth_source", "local") or "local"),
    "is_active":           ("是否啟用", lambda u, t: bool(u.is_active)),
    "department":          ("學系", lambda u, t: u.department or ""),
    "last_login_time":     ("最後登入時間", lambda u, t: u.last_login_time.isoformat() if u.last_login_time else ""),
    "last_login_ip":       ("最後登入 IP", lambda u, t: u.last_login_ip or ""),
    "created_at":          ("建立日期", lambda u, t: u.created_at.isoformat() if u.created_at else ""),
    "login_count":         ("登入次數", lambda u, t: u.login_count or 0),
    "tokens_used":         ("Token 已用", lambda u, t: (t.tokens_used if t else 0)),
    "tokens_limit":        ("Token 配額", lambda u, t: (t.tokens_limit if t else 0)),
    "lifetime_tokens_used":("歷史累計 Token", lambda u, t: u.lifetime_tokens_used or 0),
    "online_status":       ("線上狀態", lambda u, t: _compute_online(u)),
}


@router.get("/users/export", summary="v2.2 — 匯出使用者管理資料 (Excel / CSV)")
def export_users(
    columns: str = Query(
        "username,email,role,auth_source,is_active,department,last_login_time,tokens_used,tokens_limit",
        description="ZH: 逗號分隔欄位名稱 (見 _EXPORT_COLUMNS 白名單) | EN: comma-separated column names",
    ),
    fmt: str = Query("xlsx", pattern="^(xlsx|csv)$", description="ZH: xlsx 或 csv | EN: xlsx | csv"),
    scope: str = Query("filter", pattern="^(filter|all)$", description="ZH: filter=套用 auth_source 篩選 / all=全部 | EN: filter | all"),
    auth_source: Optional[str] = Query(None, description="ZH: 當 scope=filter 時的篩選值 | EN: filter value when scope=filter"),
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin),
) -> Any:
    """
    ZH: 把使用者管理列表匯出成 Excel (.xlsx) 或 CSV。
    EN: Export user-management list as Excel (.xlsx) or CSV.

    使用範例 / Examples:
      GET /api/v1/admin/users/export?fmt=xlsx&columns=username,email,tokens_used
      GET /api/v1/admin/users/export?fmt=csv&scope=filter&auth_source=local

    安全 / Security:
      - 限 admin (require_admin)
      - 欄位走白名單 (_EXPORT_COLUMNS)，避免拉到 hashed_password 等敏感欄位
      - 寫入 audit log
    """
    # 解析 + 驗證 columns
    requested = [c.strip() for c in columns.split(",") if c.strip()]
    if not requested:
        raise HTTPException(status_code=400, detail="columns 不可為空 / columns must not be empty")
    unknown = [c for c in requested if c not in _EXPORT_COLUMNS]
    if unknown:
        raise HTTPException(
            status_code=400,
            detail=f"未知欄位 / Unknown columns: {unknown}. 允許 / Allowed: {list(_EXPORT_COLUMNS)}",
        )

    # 查資料（沿用 get_all_users 的 join + filter 邏輯）
    query = (
        db.query(models.User, models.TokenUsage)
        .outerjoin(models.TokenUsage, models.TokenUsage.user_id == models.User.id)
    )
    if scope == "filter" and auth_source:
        query = query.filter(models.User.auth_source == auth_source)
    rows = query.order_by(models.User.created_at.desc()).all()

    # v2.1 yaml filter（同 get_all_users）
    yaml_usernames = _yaml_mock_usernames()
    visible = [
        (u, t) for u, t in rows
        if not (u.auth_source == "sso_mock" and u.username not in yaml_usernames)
    ]

    # 組標題列 + 資料列
    headers = [_EXPORT_COLUMNS[c][0] for c in requested]
    data_rows = [
        [_EXPORT_COLUMNS[c][1](u, t) for c in requested]
        for u, t in visible
    ]

    # audit log
    try:
        import json as _json
        db.add(models.AdminAction(
            admin_id=current_admin.id,
            target_user=None,
            action="export_users",
            payload=_json.dumps({
                "format": fmt,
                "scope": scope,
                "auth_source": auth_source,
                "columns": requested,
                "row_count": len(visible),
            }, ensure_ascii=False),
            timestamp=datetime.now(timezone.utc),
        ))
        db.commit()
    except Exception as e:
        # audit log 失敗不阻止匯出
        logger.warning(f"audit log write failed for export_users: {e}")
        db.rollback()

    # 產生檔案
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"users-export-{timestamp}.{fmt}"

    if fmt == "csv":
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(headers)
        writer.writerows(data_rows)
        # 加 UTF-8 BOM 讓 Excel 開 CSV 時正確顯示中文
        content = ("﻿" + buf.getvalue()).encode("utf-8")
        return StreamingResponse(
            io.BytesIO(content),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    # fmt == "xlsx"
    try:
        from openpyxl import Workbook
    except ImportError:
        raise HTTPException(status_code=500, detail="openpyxl 未安裝 / openpyxl not installed; pip install openpyxl")

    wb = Workbook()
    ws = wb.active
    ws.title = "Users"
    ws.append(headers)
    for row in data_rows:
        ws.append(row)

    # 簡單格式化：標題列粗體 + 凍結首列
    from openpyxl.styles import Font, PatternFill
    for cell in ws[1]:
        cell.font = Font(bold=True)
        cell.fill = PatternFill("solid", fgColor="DDEBF7")
    ws.freeze_panes = "A2"

    # auto width（粗略）
    for col_idx, col_name in enumerate(headers, start=1):
        max_len = max(
            [len(str(col_name))]
            + [len(str(row[col_idx - 1])) for row in data_rows[:200]]  # 看前 200 行
        )
        ws.column_dimensions[ws.cell(row=1, column=col_idx).column_letter].width = min(max_len + 2, 40)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/users/export/columns", summary="v2.2 — 列出可匯出的欄位清單（給前端 UI 用）")
def export_users_columns(
    _: models.User = Depends(require_admin),
) -> Any:
    """ZH: 回傳 [{key, label}, ...] 給前端 modal 動態建勾選清單"""
    return [{"key": k, "label": v[0]} for k, v in _EXPORT_COLUMNS.items()]


@router.put("/users/batch/tokens")
def batch_update_tokens(
    payload: schemas.BatchTokenUpdate,
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
) -> Any:
    """
    ZH: 管理員批量更新指定使用者的 Token 狀態
    EN: Admin batch update token state for specified users

    ZH: action = reset_usage → 將 tokens_used 歸零
    ZH: action = set_limit   → 將 tokens_limit 設為 payload.value
    """
    if not payload.user_ids:
        raise HTTPException(status_code=400, detail="user_ids cannot be empty")
    if payload.action not in ("reset_usage", "set_limit"):
        raise HTTPException(status_code=400, detail="action must be 'reset_usage' or 'set_limit'")

    now = datetime.now(timezone.utc)

    if payload.action == "reset_usage":
        updated = (
            db.query(models.TokenUsage)
            .filter(models.TokenUsage.user_id.in_(payload.user_ids))
            .update(
                {models.TokenUsage.tokens_used: 0, models.TokenUsage.last_updated: now},
                synchronize_session=False,
            )
        )
    else:  # set_limit
        updated = (
            db.query(models.TokenUsage)
            .filter(models.TokenUsage.user_id.in_(payload.user_ids))
            .update(
                {models.TokenUsage.tokens_limit: payload.value, models.TokenUsage.last_updated: now},
                synchronize_session=False,
            )
        )

    db.commit()
    logger.info("batch_update_tokens: action=%s value=%s updated=%d", payload.action, payload.value, updated)
    return {"updated_count": updated, "action": payload.action, "value": payload.value}


@router.put("/users/{user_id}")
def admin_update_user(
    user_id: str,
    update_data: schemas.AdminUserUpdate,
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
) -> Any:
    """ZH: 管理員修改使用者資訊 | EN: Admin update user details"""
    db_user = db.query(models.User).filter(models.User.id == user_id).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")

    if update_data.email is not None:
        db_user.email = update_data.email
    if update_data.role is not None:
        db_user.role = update_data.role
    if update_data.is_active is not None:
        db_user.is_active = update_data.is_active
    if update_data.department is not None:
        db_user.department = update_data.department
    if update_data.password is not None and update_data.password.strip():
        db_user.hashed_password = crud.get_password_hash(update_data.password)

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
        "tokens_limit": usage.tokens_limit if usage else 0,
    }


@router.post("/users/{user_id}/delete")
def admin_delete_user(
    user_id: str,
    payload: schemas.AdminDeleteUser,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
) -> Any:
    """ZH: 管理員刪除使用者 (需驗證密碼) | EN: Admin delete user (requires password verification)"""
    if not crud.verify_password(payload.admin_password, current_user.hashed_password):
        raise HTTPException(status_code=403, detail="Invalid admin password")
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")

    db_user = db.query(models.User).filter(models.User.id == user_id).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")

    db.query(models.TokenUsage).filter(models.TokenUsage.user_id == user_id).delete()
    db.delete(db_user)
    db.commit()

    logger.info(f"User {db_user.username} deleted by admin {current_user.username}")
    return {"message": f"User {db_user.username} deleted", "deleted_id": user_id}


@router.post("/verify")
def admin_verify_action(
    payload: schemas.AdminVerify,
    current_user: models.User = Depends(require_admin),
) -> Any:
    """ZH: 管理員密碼驗證（解鎖敏感操作）| EN: Admin password verification (unlock sensitive actions)"""
    if not crud.verify_password(payload.admin_password, current_user.hashed_password):
        raise HTTPException(status_code=403, detail="Invalid admin password")
    return {"message": "Verification successful"}


@router.post("/users/provision")
def provision_user(
    data: schemas.AdminProvisionUser,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
) -> Any:
    """ZH: 管理員配發新帳號（預先建立，待 SSO 接管）| EN: Admin provision a new user account"""
    if crud.get_user_by_username(db, data.username):
        raise HTTPException(status_code=400, detail="Username already exists")
    if crud.get_user_by_email(db, data.email):
        raise HTTPException(status_code=400, detail="Email already exists")

    import secrets
    temp_password = data.password if data.password else secrets.token_urlsafe(12)

    user_create = schemas.UserCreate(
        username=data.username,
        email=data.email,
        password=temp_password,
        role=data.role or "student",
    )
    db_user = crud.create_user(db, user_create)
    db_user.is_test_account = 0
    db.commit()

    email_queued = bool(db_user.email)
    if email_queued:
        background_tasks.add_task(
            email_service.send_temp_password,
            db_user.email, db_user.username, temp_password, True,
        )

    # ZH: 僅在無法發送 Email 時才在回應中回傳明文密碼，避免密碼出現在瀏覽器記錄中
    # EN: Only return plaintext password when email cannot be sent (avoids it appearing in browser logs)
    logger.info(
        "provision_user: created %s (email_queued=%s)", db_user.username, email_queued
    )
    return {
        "id": db_user.id,
        "username": db_user.username,
        "email": db_user.email,
        "role": db_user.role,
        "temp_password": temp_password if not email_queued else "[已寄送至 Email | sent via email]",
        "email_sent": email_queued,
    }


@router.post("/users/{user_id}/reset")
def reset_user_account(
    user_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
) -> Any:
    """ZH: 初始化帳號 — 重置密碼 + 歸零 Token 用量 | EN: Reset password and clear token usage"""
    db_user = db.query(models.User).filter(models.User.id == user_id).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")

    import secrets
    temp_password = secrets.token_urlsafe(12)
    db_user.hashed_password = crud.get_password_hash(temp_password)

    usage = crud.get_token_usage(db, user_id)
    if usage:
        usage.tokens_used = 0

    db.commit()

    email_queued = bool(db_user.email)
    if email_queued:
        background_tasks.add_task(
            email_service.send_temp_password,
            db_user.email, db_user.username, temp_password, False,
        )

    logger.info(
        "reset_user_account: %s reset by admin %s (email_queued=%s)",
        db_user.username, current_user.username, email_queued,
    )
    return {
        "username": db_user.username,
        "temp_password": temp_password if not email_queued else "[已寄送至 Email | sent via email]",
        "email_sent": email_queued,
        "message": f"Account {db_user.username} has been initialized",
    }


# ==============================================================================
# ZH: 任務管理 | EN: Job Management
# ==============================================================================

@router.get("/jobs", response_model=list[schemas.AdminJobListItem])
def get_all_jobs(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
) -> Any:
    """ZH: 列出所有任務，支援分頁 | EN: List all jobs with pagination"""
    jobs = (
        db.query(models.TrainingJob)
        .order_by(models.TrainingJob.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return [
        schemas.AdminJobListItem(
            job_id=j.id,
            job_name=j.job_name,
            model_name=j.model_name,
            user_id=j.user_id,
            status=j.status,
            priority=j.priority,
            progress=j.progress,
            gpu_server=j.gpu_server,
            created_at=j.created_at,
            started_at=j.started_at,
            completed_at=j.completed_at,
            error_message=j.error_message,
        )
        for j in jobs
    ]


@router.post("/jobs/{job_id}/cancel")
def admin_cancel_job(
    job_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
) -> Any:
    """ZH: 管理員強制取消任務 | EN: Admin force-cancel a job"""
    job = db.query(models.TrainingJob).filter(models.TrainingJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status not in ("pending", "queued"):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot cancel job with status '{job.status}'. Only pending/queued jobs can be cancelled.",
        )

    job.status = "cancelled"
    db.commit()
    db.refresh(job)

    logger.info(f"Admin {current_user.username} cancelled job {job_id[:8]}")
    return {"job_id": job.id, "status": job.status, "message": "Job cancelled"}


@router.put("/jobs/{job_id}/priority")
def admin_update_job_priority(
    job_id: str,
    data: schemas.AdminJobPriority,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
) -> Any:
    """ZH: 管理員修改任務優先級 | EN: Admin update job priority"""
    job = db.query(models.TrainingJob).filter(models.TrainingJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status not in ("pending", "queued"):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot reprioritize job with status '{job.status}'.",
        )

    old_priority = job.priority
    job.priority = data.priority
    db.commit()
    db.refresh(job)

    logger.info(f"Admin {current_user.username} changed job {job_id[:8]} priority: {old_priority} -> {data.priority}")
    return {"job_id": job.id, "priority": job.priority, "old_priority": old_priority}


# ==============================================================================
# ZH: 模型管理 | EN: Model Management
# ==============================================================================

@router.get("/models")
def get_all_models(
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
) -> Any:
    """ZH: 列出所有模型 | EN: List all models"""
    mdls = db.query(models.Model).order_by(models.Model.created_at.desc()).all()
    return [
        {
            "id": m.id, "name": m.name, "model_type": m.model_type,
            "description": m.description, "framework": m.framework,
            "storage_path": m.storage_path, "size_bytes": m.size_bytes,
            "uploaded_by": m.uploaded_by, "is_public": m.is_public,
            "tool_types": m.tool_types or "chat",
            "api_provider": m.api_provider, "api_endpoint": m.api_endpoint,
            "api_model_id": m.api_model_id, "created_at": m.created_at,
        }
        for m in mdls
    ]


@router.post("/models")
def admin_create_model(
    data: schemas.AdminModelCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
) -> Any:
    """ZH: 管理員新增模型 | EN: Admin create model"""
    if db.query(models.Model).filter(models.Model.name == data.name).first():
        raise HTTPException(status_code=400, detail=f"Model '{data.name}' already exists")

    new_model = models.Model(
        name=data.name, model_type=data.model_type or "local",
        description=data.description, framework=data.framework,
        storage_path=data.storage_path or "", is_public=data.is_public or 0,
        tool_types=data.tool_types or "chat",
        uploaded_by=current_user.id, api_provider=data.api_provider,
        api_endpoint=data.api_endpoint, api_model_id=data.api_model_id,
    )
    db.add(new_model)
    db.commit()
    db.refresh(new_model)

    logger.info(f"Admin {current_user.username} created model '{data.name}'")
    return {"id": new_model.id, "name": new_model.name, "model_type": new_model.model_type}


@router.put("/models/{model_id}")
def admin_update_model(
    model_id: str,
    data: schemas.AdminModelUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
) -> Any:
    """ZH: 管理員更新模型資訊 | EN: Admin update model info"""
    mdl = db.query(models.Model).filter(models.Model.id == model_id).first()
    if not mdl:
        raise HTTPException(status_code=404, detail="Model not found")

    if data.name is not None:
        dup = db.query(models.Model).filter(
            models.Model.name == data.name, models.Model.id != model_id
        ).first()
        if dup:
            raise HTTPException(status_code=400, detail=f"Model name '{data.name}' already taken")
        mdl.name = data.name

    for field in ("description", "model_type", "framework", "storage_path",
                  "is_public", "tool_types", "api_provider", "api_endpoint", "api_model_id"):
        val = getattr(data, field, None)
        if val is not None:
            setattr(mdl, field, val)

    db.commit()
    db.refresh(mdl)

    logger.info(f"Admin {current_user.username} updated model '{mdl.name}'")
    return {"id": mdl.id, "name": mdl.name, "model_type": mdl.model_type}


@router.delete("/models/{model_id}")
def admin_delete_model(
    model_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
) -> Any:
    """ZH: 管理員刪除模型 | EN: Admin delete model"""
    mdl = db.query(models.Model).filter(models.Model.id == model_id).first()
    if not mdl:
        raise HTTPException(status_code=404, detail="Model not found")

    model_name = mdl.name
    db.delete(mdl)
    db.commit()

    logger.info(f"Admin {current_user.username} deleted model '{model_name}'")
    return {"message": f"Model '{model_name}' deleted", "deleted_id": model_id}


# ==============================================================================
# ZH: 叢集狀態 | EN: Cluster Status
# ==============================================================================

@router.get("/cluster/stats")
def get_cluster_stats(
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
) -> Any:
    """ZH: 取得 Worker 節點最新心跳狀態 | EN: Get latest Worker node heartbeat status"""
    nodes = db.query(models.WorkerHeartbeat).order_by(models.WorkerHeartbeat.last_seen.desc()).all()
    return [
        {
            "node_id": n.node_id,
            "available_gpus": n.available_gpus,
            "gpu_utilization": n.gpu_utilization,
            "last_seen": n.last_seen,
            "status": "online" if n.is_online else "offline",
        }
        for n in nodes
    ]


# ==============================================================================
# ZH: 數據分析 | EN: Analytics
# ==============================================================================

@router.get("/users/{user_id}/analytics")
def get_user_analytics(
    user_id: str,
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
) -> Any:
    """
    ZH: 取得指定使用者的細粒度數據分析（Token、Sessions、工具分布）
    EN: Detailed per-user analytics — token quota, sessions, tool breakdown
    """
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    usage = crud.get_token_usage(db, user_id)

    # ZH: 依工具類型彙總訊息數與 Token 消耗 | EN: Aggregate by tool_type
    tool_rows = (
        db.query(
            models.ChatHistory.tool_type,
            func.count(models.ChatHistory.id).label("message_count"),
            func.sum(models.ChatHistory.tokens_used).label("tokens_sum"),
        )
        .filter(models.ChatHistory.user_id == user_id)
        .group_by(models.ChatHistory.tool_type)
        .all()
    )

    # ZH: Top-10 Sessions（依 Token 消耗降冪）| EN: Top-10 sessions by token cost
    session_rows = (
        db.query(
            models.ChatHistory.session_id,
            func.min(models.ChatHistory.created_at).label("started_at"),
            func.count(models.ChatHistory.id).label("message_count"),
            func.sum(models.ChatHistory.tokens_used).label("tokens_sum"),
        )
        .filter(models.ChatHistory.user_id == user_id)
        .group_by(models.ChatHistory.session_id)
        .order_by(func.sum(models.ChatHistory.tokens_used).desc())
        .limit(10)
        .all()
    )

    # ZH: 對話 Session 總數 | EN: Total distinct sessions
    total_sessions = (
        db.query(func.count(func.distinct(models.ChatHistory.session_id)))
        .filter(models.ChatHistory.user_id == user_id)
        .scalar()
    ) or 0

    tokens_used  = usage.tokens_used  if usage else 0
    tokens_limit = usage.tokens_limit if usage else 0
    usage_pct    = round(tokens_used / tokens_limit * 100, 1) if tokens_limit > 0 else 0.0

    return {
        "user": {
            "id":                   user.id,
            "username":             user.username,
            "email":                user.email,
            "role":                 user.role,
            "department":           user.department,
            "is_active":            user.is_active,
            "login_count":          user.login_count,
            "lifetime_tokens_used": user.lifetime_tokens_used,
            "last_login_time":      user.last_login_time,
            "last_login_ip":        user.last_login_ip,
            "created_at":           user.created_at,
        },
        "token_quota": {
            "tokens_used":  tokens_used,
            "tokens_limit": tokens_limit,
            "usage_pct":    usage_pct,
            "reset_date":   usage.reset_date if usage else None,
        },
        "total_sessions": total_sessions,
        "tool_breakdown": [
            {
                "tool_type":     r.tool_type or "chat",
                "message_count": r.message_count,
                "tokens_sum":    int(r.tokens_sum or 0),
            }
            for r in tool_rows
        ],
        "top_sessions": [
            {
                "session_id":    r.session_id,
                "started_at":    r.started_at,
                "message_count": r.message_count,
                "tokens_sum":    int(r.tokens_sum or 0),
            }
            for r in session_rows
        ],
    }


@router.get("/analytics")
def get_analytics(
    department: Optional[str] = Query("all"),
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
) -> Any:
    """ZH: 取得管理員分析數據（學系/工具用量）| EN: Get admin analytics (department/tool usage)"""
    base_q = db.query(
        models.User.department,
        func.count(models.User.id).label("user_count"),
        func.sum(models.User.login_count).label("total_logins"),
        func.sum(models.User.lifetime_tokens_used).label("total_tokens"),
    )

    if department != "all":
        rows = base_q.filter(models.User.department == department).group_by(models.User.department).all()
    else:
        rows = base_q.group_by(models.User.department).all()

    dept_stats = [
        {
            "department": r.department or "Unknown",
            "user_count": r.user_count,
            "total_logins": r.total_logins or 0,
            "total_tokens": r.total_tokens or 0,
        }
        for r in rows
    ]

    tool_q = db.query(
        models.ChatHistory.tool_type,
        func.count(models.ChatHistory.id).label("usage_count"),
    )
    if department != "all":
        tool_q = tool_q.join(models.User, models.ChatHistory.user_id == models.User.id).filter(
            models.User.department == department
        )
    tool_stats = tool_q.group_by(models.ChatHistory.tool_type).all()

    return {
        "department_filter": department,
        "department_stats": dept_stats,
        "tools_breakdown": [
            {"tool_type": s.tool_type or "chat", "usage_count": s.usage_count}
            for s in tool_stats
        ],
    }


# ==============================================================================
# ZH: v2.0 Lab 模組 — 13 個 admin endpoints
# EN: v2.0 Lab module — 13 admin endpoints
# ==============================================================================

from pydantic import BaseModel, Field
from ..services import quota_service, storage_lifecycle, lab_manager, secrets_service


# ---- pydantic 請求 / 回應模型 ----

class QuotaGrantRequest(BaseModel):
    user_id: str
    extra_quota_gb: int = Field(..., gt=0)
    reason: str = Field(..., min_length=5)
    expires_at: Optional[datetime] = None


class StorageStateActionRequest(BaseModel):
    user_id: str
    reason: Optional[str] = None
    admin_password: Optional[str] = None  # 永久刪除需驗證


# ---- 配額提權 ----

@router.post("/quota/grant")
def grant_quota(
    payload: QuotaGrantRequest,
    db: Session = Depends(get_db),
    admin: models.User = Depends(require_admin),
) -> Any:
    """ZH: 為使用者額外提權配額（保留歷史） | EN: Grant extra disk quota to user"""
    target = db.query(models.User).filter(models.User.id == payload.user_id).first()
    if not target:
        raise HTTPException(404, "Target user not found")
    grant = quota_service.grant(
        db,
        user_id=payload.user_id,
        extra_quota_gb=payload.extra_quota_gb,
        granted_by=admin.id,
        reason=payload.reason,
        expires_at=payload.expires_at,
    )
    return {"id": grant.id, "extra_quota_gb": grant.extra_quota_gb, "granted_at": grant.granted_at}


@router.delete("/quota/grant/{grant_id}")
def revoke_quota(
    grant_id: str,
    db: Session = Depends(get_db),
    admin: models.User = Depends(require_admin),
) -> Any:
    """ZH: 撤銷一筆配額提權 | EN: Revoke a quota grant"""
    success = quota_service.revoke(db, grant_id=grant_id, revoked_by=admin.id)
    if not success:
        raise HTTPException(404, "Grant not found or already revoked")
    return {"status": "revoked", "grant_id": grant_id}


@router.get("/quota/{user_id}")
def get_user_quota(
    user_id: str,
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
) -> Any:
    """ZH: 查看使用者目前生效配額與所有提權紀錄 | EN: View user effective quota + all grants"""
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(404, "User not found")
    grants = quota_service.list_grants(db, user_id=user_id)
    return {
        "user_id": user_id,
        "base_quota_gb": user.disk_quota_gb,
        "effective_quota_gb": quota_service.get_effective_quota_gb(db, user_id),
        "grants": [
            {
                "id": g.id,
                "extra_quota_gb": g.extra_quota_gb,
                "reason": g.reason,
                "granted_by": g.granted_by,
                "granted_at": g.granted_at,
                "expires_at": g.expires_at,
                "revoked_at": g.revoked_at,
            }
            for g in grants
        ],
    }


# ---- 儲存生命週期 ----

@router.post("/storage/freeze")
def storage_freeze(
    payload: StorageStateActionRequest,
    db: Session = Depends(get_db),
    admin: models.User = Depends(require_admin),
    request: Any = None,
) -> Any:
    """ZH: 凍結使用者儲存（停用 lab session 但保留檔案） | EN: Freeze storage"""
    storage_lifecycle.freeze(db, user_id=payload.user_id, admin_id=admin.id, reason=payload.reason)
    return {"status": "frozen", "user_id": payload.user_id}


@router.post("/storage/archive")
def storage_archive(
    payload: StorageStateActionRequest,
    db: Session = Depends(get_db),
    admin: models.User = Depends(require_admin),
) -> Any:
    """ZH: 歸檔到冷儲存（HDD） | EN: Archive to cold storage"""
    storage_lifecycle.archive(db, user_id=payload.user_id, admin_id=admin.id, reason=payload.reason)
    return {"status": "archived", "user_id": payload.user_id}


@router.post("/storage/restore")
def storage_restore(
    payload: StorageStateActionRequest,
    db: Session = Depends(get_db),
    admin: models.User = Depends(require_admin),
) -> Any:
    """ZH: 從凍結/歸檔還原 | EN: Restore from frozen/archived"""
    storage_lifecycle.restore(db, user_id=payload.user_id, admin_id=admin.id, reason=payload.reason)
    return {"status": "active", "user_id": payload.user_id}


@router.post("/storage/permanent-delete")
def storage_permanent_delete(
    payload: StorageStateActionRequest,
    db: Session = Depends(get_db),
    admin: models.User = Depends(require_admin),
) -> Any:
    """ZH: 永久刪除（需 admin 密碼驗證） | EN: Permanent delete (requires admin password)"""
    if not payload.admin_password:
        raise HTTPException(400, "admin_password required for permanent delete")
    if not crud.verify_password(payload.admin_password, admin.hashed_password):
        raise HTTPException(403, "Admin password verification failed")
    storage_lifecycle.permanent_delete(db, user_id=payload.user_id, admin_id=admin.id, reason=payload.reason)
    return {"status": "deleted", "user_id": payload.user_id}


@router.get("/storage/states")
def list_storage_states(
    state: Optional[str] = Query(None, description="active/frozen/archived/pending_delete"),
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
) -> Any:
    """ZH: 列出所有使用者儲存狀態 | EN: List all storage states"""
    states = storage_lifecycle.list_states(db, filter_state=state)
    return {"states": states}


# ---- Lab Sessions 監控 ----

@router.get("/lab/sessions")
def list_lab_sessions(
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
) -> Any:
    """ZH: 列出當前所有 lab sessions | EN: List all current lab sessions"""
    sessions = lab_manager.list_all_sessions(db)
    return {"sessions": sessions}


@router.post("/lab/sessions/{user_id}/force-stop")
def force_stop_session(
    user_id: str,
    db: Session = Depends(get_db),
    admin: models.User = Depends(require_admin),
) -> Any:
    """ZH: 強制停止特定使用者 lab session | EN: Force-stop a user's lab session"""
    success = lab_manager.force_stop(db, user_id=user_id, admin_id=admin.id)
    if not success:
        raise HTTPException(404, "Session not found or already stopped")
    return {"status": "stopped", "user_id": user_id}


# ---- Secrets 監控（admin 也不可看 value） ----

@router.get("/secrets/{user_id}/names")
def list_user_secret_names(
    user_id: str,
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
) -> Any:
    """ZH: 列出某使用者的 secret 名稱（不回 value） | EN: List user secret names (no values)"""
    secrets_meta = secrets_service.list_secrets_masked(db, user_id=user_id)
    return {"user_id": user_id, "secrets": secrets_meta}


@router.delete("/secrets/{user_id}/{name}")
def admin_delete_user_secret(
    user_id: str,
    name: str,
    db: Session = Depends(get_db),
    admin: models.User = Depends(require_admin),
) -> Any:
    """ZH: 管理員刪除使用者的特定 secret（離校等情境） | EN: Admin delete a user's secret"""
    success = secrets_service.delete_secret(db, user_id=user_id, name=name, admin_id=admin.id)
    if not success:
        raise HTTPException(404, "Secret not found")
    return {"status": "deleted", "user_id": user_id, "name": name}


# ---- Audit log ----

@router.get("/audit")
def get_audit_log(
    admin_id: Optional[str] = Query(None),
    target_user: Optional[str] = Query(None),
    action: Optional[str] = Query(None),
    limit: int = Query(100, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
) -> Any:
    """ZH: 查詢 admin 操作審計 log（支援篩選與分頁） | EN: Query admin audit log"""
    q = db.query(models.AdminAction)
    if admin_id:
        q = q.filter(models.AdminAction.admin_id == admin_id)
    if target_user:
        q = q.filter(models.AdminAction.target_user == target_user)
    if action:
        q = q.filter(models.AdminAction.action == action)
    total = q.count()
    rows = q.order_by(models.AdminAction.timestamp.desc()).offset(offset).limit(limit).all()
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": [
            {
                "id": r.id,
                "admin_id": r.admin_id,
                "target_user": r.target_user,
                "action": r.action,
                "payload": r.payload,
                "timestamp": r.timestamp,
                "ip_address": r.ip_address,
            }
            for r in rows
        ],
    }
