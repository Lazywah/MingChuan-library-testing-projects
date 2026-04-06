"""
==============================================================================
Router: 訓練任務路由群組 (Training Job Routes)
==============================================================================
ZH: 用途：處理訓練任務的提交、查詢、列表、取消的 HTTP 端點
EN: Purpose: Handle HTTP endpoints for job submission, query, list, and cancel

ZH: 端點清單：
    POST   /api/v1/jobs             → 提交新訓練任務
    GET    /api/v1/jobs             → 列出使用者任務 (支援篩選/分頁)
    GET    /api/v1/jobs/{job_id}    → 查詢單一任務狀態
    DELETE /api/v1/jobs/{job_id}    → 取消任務

ZH: 模組化設計：
    - 此 Router 可獨立加入/移除，不影響 Auth Router
    - 掛載方式：app.include_router(jobs_router, prefix="/api/v1/jobs")
    - 權限控制：所有端點都需要 JWT 認證
    - admin/teacher 可查看所有任務，student 只能查看自己的
EN: Modular design:
    - This Router can be added/removed independently
    - Mount: app.include_router(jobs_router, prefix="/api/v1/jobs")
    - Auth: all endpoints require JWT authentication
    - admin/teacher can view all jobs, student can only view their own
==============================================================================
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import Optional

from .. import crud, schemas, models
from ..auth import get_current_user
from ..database import get_db

import json
import logging

logger = logging.getLogger(__name__)

# ==============================================================================
# ZH: 建立 Router 實例 | EN: Create Router instance
# ==============================================================================
router = APIRouter(tags=["訓練任務 Training Jobs"])


# ==============================================================================
# ZH: POST / - 提交新訓練任務
# EN: POST / - Submit new training job
# ZH: 流程：
#   1. 驗證 JWT → 取得使用者
#   2. 計算預估 Token 消耗 (epochs × 1000)
#   3. 扣減 Token 額度 (超額則拒絕)
#   4. 建立 Job 記錄 (status=pending)
#   5. 回傳 job_id 和佇列位置
#   6. 排程器背景迴圈會自動取出並執行
# EN: Flow:
#   1. Verify JWT → get user
#   2. Estimate token cost (epochs × 1000)
#   3. Deduct token quota (reject if exceeded)
#   4. Create job record (status=pending)
#   5. Return job_id and queue position
#   6. Scheduler background loop auto-picks and executes
# ==============================================================================
@router.post("", response_model=schemas.JobResponse, status_code=status.HTTP_201_CREATED)
def submit_job(
    job: schemas.JobCreate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    ZH: 提交新的訓練任務
    EN: Submit a new training job
    """
    # ZH: 計算預估 Token 消耗 | EN: Calculate estimated token cost
    epochs = 10
    if job.config and "epochs" in job.config:
        epochs = job.config["epochs"]
    estimated_tokens = epochs * 1000  # ZH: 簡化計算 | EN: Simplified calculation

    # ZH: 檢查 Token 額度 | EN: Check token quota
    usage = crud.get_token_usage(db, user_id=current_user.id)
    if usage and (usage.tokens_used + estimated_tokens) > usage.tokens_limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"ZH: Token 配額不足。剩餘: {usage.tokens_limit - usage.tokens_used}, "
                   f"需要: {estimated_tokens} | "
                   f"EN: Insufficient quota. Remaining: {usage.tokens_limit - usage.tokens_used}, "
                   f"Required: {estimated_tokens}"
        )

    # ZH: 扣減 Token | EN: Deduct tokens
    crud.increment_token_usage(db, user_id=current_user.id, tokens=estimated_tokens)

    # ZH: 建立任務 | EN: Create job
    db_job = crud.create_job(db=db, job=job, user_id=current_user.id)

    # ZH: 計算佇列位置 | EN: Calculate queue position
    queue_pos = crud.get_queue_position(db, db_job.id)

    logger.info(
        f"ZH: 使用者 {current_user.username} 提交任務 {db_job.id[:8]} "
        f"(模型: {job.model_name}, Token: {estimated_tokens}) | "
        f"EN: User {current_user.username} submitted job {db_job.id[:8]} "
        f"(model: {job.model_name}, tokens: {estimated_tokens})"
    )

    return {
        "job_id": db_job.id,
        "status": db_job.status,
        "queue_position": queue_pos
    }


# ==============================================================================
# ZH: GET / - 列出任務 (支援篩選 + 分頁)
# EN: GET / - List jobs (supports filtering + pagination)
# ==============================================================================
@router.get("", response_model=schemas.JobListResponse)
def list_jobs(
    status_filter: Optional[str] = Query(None, alias="status", description="ZH: 篩選狀態 | EN: Filter by status"),
    limit: int = Query(20, ge=1, le=100, description="ZH: 每頁數量 | EN: Items per page"),
    offset: int = Query(0, ge=0, description="ZH: 偏移量 | EN: Offset"),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    ZH: 列出訓練任務 (student 看自己的，admin/teacher 看全部)
    EN: List training jobs (student sees own, admin/teacher sees all)
    """
    if current_user.role in ("admin", "teacher"):
        jobs, total = crud.get_all_jobs(db, status=status_filter, limit=limit, offset=offset)
    else:
        jobs, total = crud.get_jobs_by_user(
            db, user_id=current_user.id, status=status_filter, limit=limit, offset=offset
        )

    job_list = []
    for job in jobs:
        job_list.append({
            "job_id": job.id,
            "job_name": job.job_name,
            "status": job.status,
            "progress": job.progress,
            "gpu_server": job.gpu_server,
            "gpu_id": job.gpu_id,
            "started_at": job.started_at,
            "completed_at": job.completed_at,
            "error_message": job.error_message,
            "output_path": job.output_path,
            "logs": job.logs,
        })

    return {"total": total, "jobs": job_list}


# ==============================================================================
# ZH: GET /{job_id} - 查詢單一任務狀態
# EN: GET /{job_id} - Query single job status
# ==============================================================================
@router.get("/{job_id}", response_model=schemas.JobStatusResponse)
def get_job_status(
    job_id: str,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    ZH: 查詢特定訓練任務的詳細狀態
    EN: Query detailed status of a specific training job
    """
    job = crud.get_job(db, job_id=job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="ZH: 找不到任務 | EN: Job not found"
        )

    # ZH: 權限檢查：student 只能看自己的 | EN: Permission: student can only view own
    if current_user.role == "student" and job.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="ZH: 無權限查看此任務 | EN: Not authorized to view this job"
        )

    return {
        "job_id": job.id,
        "job_name": job.job_name,
        "status": job.status,
        "progress": job.progress,
        "gpu_server": job.gpu_server,
        "gpu_id": job.gpu_id,
        "started_at": job.started_at,
        "completed_at": job.completed_at,
        "error_message": job.error_message,
        "output_path": job.output_path,
        "logs": job.logs,
    }


# ==============================================================================
# ZH: DELETE /{job_id} - 取消任務
# EN: DELETE /{job_id} - Cancel job
# ZH: 限制：僅 pending/queued 狀態可取消
# EN: Constraint: only pending/queued jobs can be cancelled
# ==============================================================================
@router.delete("/{job_id}", response_model=schemas.JobCancelResponse)
def cancel_job(
    job_id: str,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    ZH: 取消訓練任務 (僅 pending/queued 可取消)
    EN: Cancel training job (only pending/queued can be cancelled)
    """
    job = crud.get_job(db, job_id=job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="ZH: 找不到任務 | EN: Job not found"
        )

    # ZH: 權限：student 只能取消自己的，admin 可取消所有 | EN: student=own, admin=all
    if current_user.role == "student" and job.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="ZH: 無權限取消此任務 | EN: Not authorized to cancel this job"
        )

    if job.status not in ("pending", "queued"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"ZH: 無法取消 '{job.status}' 狀態的任務 | "
                   f"EN: Cannot cancel job with status '{job.status}'"
        )

    cancelled_job = crud.cancel_job(db, job_id=job_id)
    logger.info(
        f"ZH: 使用者 {current_user.username} 取消任務 {job_id[:8]} | "
        f"EN: User {current_user.username} cancelled job {job_id[:8]}"
    )

    return {"job_id": cancelled_job.id, "status": cancelled_job.status}
