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
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import Optional
import asyncio

from .. import crud, schemas, models
from ..auth import get_current_user
from ..database import get_db
from ..config import SCHEDULER_POLICY

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
#   2. 政策檢查（scheduler_policy.yaml）：
#      a. allow_students        → 學生申請開關
#      b. max_concurrent_jobs   → 叢集執行中任務上限（admin/teacher 免檢）
#      c. max_epochs_per_job    → 單筆任務迭代次數上限
#      d. max_batch_size        → 單筆任務批次大小上限
#   3. 計算預估 Token 消耗 (epochs × 1000)
#   4. 扣減 Token 額度 (超額則拒絕)
#   5. 建立 Job 記錄 (status=pending)
#   6. 回傳 job_id 和佇列位置
#   7. 排程器背景迴圈會自動取出並執行
# EN: Flow:
#   1. Verify JWT → get user
#   2. Policy checks (scheduler_policy.yaml):
#      a. allow_students        → student submission gate
#      b. max_concurrent_jobs   → cluster-wide running jobs cap (admin/teacher bypass)
#      c. max_epochs_per_job    → per-job epochs cap
#      d. max_batch_size        → per-job batch size cap
#   3. Estimate token cost (epochs × 1000)
#   4. Deduct token quota (reject if exceeded)
#   5. Create job record (status=pending)
#   6. Return job_id and queue position
#   7. Scheduler background loop auto-picks and executes
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
    policy = SCHEDULER_POLICY.get("scheduling", {})

    # ------------------------------------------------------------------
    # ZH: 政策檢查 a — 學生申請開關
    # EN: Policy check a — student submission gate
    # ------------------------------------------------------------------
    if current_user.role == "student" and not policy.get("allow_students", True):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="ZH: 目前停止開放學生申請 GPU 排程任務，請聯繫教師或管理員 | "
                   "EN: Student job submissions are currently disabled, contact a teacher or admin"
        )

    # ------------------------------------------------------------------
    # ZH: 政策檢查 b — 叢集執行中任務上限（admin / teacher 免檢）
    # EN: Policy check b — cluster running jobs cap (admin/teacher bypass)
    # ------------------------------------------------------------------
    if current_user.role not in ("admin", "teacher"):
        max_concurrent = policy.get("max_concurrent_jobs", 4)
        running_count = crud.get_running_jobs_count(db)
        if running_count >= max_concurrent:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"ZH: 叢集目前已有 {running_count}/{max_concurrent} 個任務執行中，"
                       f"請稍後再試 | "
                       f"EN: Cluster at capacity ({running_count}/{max_concurrent} running), "
                       f"please try again later"
            )

    # ------------------------------------------------------------------
    # ZH: 政策檢查 c — 單筆任務迭代次數上限
    # EN: Policy check c — per-job epochs cap
    # ------------------------------------------------------------------
    max_epochs = policy.get("max_epochs_per_job", 1000)
    if job.config and "epochs" in job.config:
        try:
            epochs_val = int(job.config["epochs"])
            if epochs_val > max_epochs:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"ZH: epochs {epochs_val} 超過上限 {max_epochs} | "
                           f"EN: epochs {epochs_val} exceeds maximum allowed {max_epochs}"
                )
        except (TypeError, ValueError):
            pass  # ZH: 非整數值由後續訓練框架處理 | EN: Non-int handled by training framework

    # ------------------------------------------------------------------
    # ZH: 政策檢查 d — 單筆任務批次大小上限
    # EN: Policy check d — per-job batch size cap
    # ------------------------------------------------------------------
    max_batch = policy.get("max_batch_size", 512)
    if job.config and "batch_size" in job.config:
        try:
            batch_val = int(job.config["batch_size"])
            if batch_val > max_batch:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"ZH: batch_size {batch_val} 超過上限 {max_batch} | "
                           f"EN: batch_size {batch_val} exceeds maximum allowed {max_batch}"
                )
        except (TypeError, ValueError):
            pass  # ZH: 非整數值由後續訓練框架處理 | EN: Non-int handled by training framework

    # ZH: 計算預估 Token 消耗 | EN: Calculate estimated token cost
    estimated_tokens = crud.estimate_job_tokens(job.config)

    # ZH: 原子性配額檢查 + 扣減（單一 SQL UPDATE，消除 TOCTOU 競爭條件）
    # EN: Atomic quota check + deduction (single SQL UPDATE, eliminates TOCTOU race)
    if not crud.try_deduct_tokens(db, user_id=current_user.id, tokens=estimated_tokens):
        usage = crud.get_token_usage(db, user_id=current_user.id)
        remaining = (usage.tokens_limit - usage.tokens_used) if usage else 0
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"ZH: Token 配額不足。剩餘: {remaining}, "
                   f"需要: {estimated_tokens} | "
                   f"EN: Insufficient quota. Remaining: {remaining}, "
                   f"Required: {estimated_tokens}"
        )

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
        # ZH: 列表不回傳 logs（可能很大）；詳細日誌請用 GET /{job_id}
        # EN: List excludes logs (potentially huge); use GET /{job_id} for full logs
        job_list.append({
            "job_id": job.id,
            "job_name": job.job_name,
            "model_name": job.model_name,
            "user_id": job.user_id,
            "status": job.status,
            "priority": job.priority,
            "progress": job.progress,
            "gpu_server": job.gpu_server,
            "gpu_id": job.gpu_id,
            "started_at": job.started_at,
            "completed_at": job.completed_at,
            "created_at": job.created_at,
            "error_message": job.error_message,
            "output_path": job.output_path,
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


# ==============================================================================
# ZH: GET /{job_id}/stream - 串流任務日誌與指標 (SSE)
# EN: GET /{job_id}/stream - Stream job logs and metrics via Server-Sent Events
# ==============================================================================
@router.get("/{job_id}/stream")
async def stream_job_logs(
    job_id: str,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    ZH: 串流任務日誌與指標 (SSE)
    EN: Stream job logs and metrics via Server-Sent Events
    """
    job = crud.get_job(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
        
    if current_user.role == "student" and job.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Permission denied")

    async def event_generator():
        # First yield the full history
        history_data = {
            "status": job.status,
            "progress": job.progress,
            "logs": job.logs or "",
            "metrics": json.loads(job.metrics) if job.metrics else []
        }
        yield f"data: {json.dumps(history_data)}\n\n"
        
        # Then poll for updates
        last_log_len = len(job.logs) if job.logs else 0
        last_metrics_len = len(history_data["metrics"])
        
        while True:
            # Re-fetch from DB
            db.refresh(job)
            
            new_logs = ""
            if job.logs and len(job.logs) > last_log_len:
                new_logs = job.logs[last_log_len:]
                last_log_len = len(job.logs)
                
            current_metrics = []
            if job.metrics:
                try:
                    all_metrics = json.loads(job.metrics)
                    if len(all_metrics) > last_metrics_len:
                        current_metrics = all_metrics[last_metrics_len:]
                        last_metrics_len = len(all_metrics)
                except:
                    pass

            # Only yield if there's an update or job finished
            if new_logs or current_metrics or job.status in ("completed", "failed", "cancelled"):
                update_data = {
                    "status": job.status,
                    "progress": job.progress,
                    "new_logs": new_logs,
                    "new_metrics": current_metrics
                }
                yield f"data: {json.dumps(update_data)}\n\n"
                
            if job.status in ("completed", "failed", "cancelled"):
                break
                
            await asyncio.sleep(1)

    return StreamingResponse(event_generator(), media_type="text/event-stream")
