"""
==============================================================================
Router: Worker 節點通訊路由 (Worker Node Communication Routes)
==============================================================================
ZH: 用途：GPU Worker 節點透過此路由領取任務、回報進度與上報心跳
EN: Purpose: GPU Worker nodes use these routes to claim jobs, report progress,
    and send heartbeats for cluster health monitoring

ZH: 端點清單：
    POST /take                 → Worker 領取最高優先級 pending 任務（原子搶佔）
    POST /jobs/{id}/update     → Worker 回報任務進度、日誌、狀態
    POST /heartbeat            → Worker 定期上報節點存活與 GPU 使用率
ZH: 認證：所有端點使用靜態 API Token（Bearer），由 verify_worker_token Depends 驗證
EN: Auth: All endpoints use static API Token (Bearer), enforced via verify_worker_token
==============================================================================
"""

from fastapi import APIRouter, Depends, HTTPException, status, Header
from sqlalchemy.orm import Session
from sqlalchemy import update
from pydantic import BaseModel
from typing import List, Optional
import json
import hmac
import logging
from datetime import datetime, timezone

from ..database import get_db
from .. import crud, models, schemas
from ..config import settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Worker 節點通訊 Worker Nodes"])


# ==============================================================================
# ZH: Worker 認證 | EN: Worker Authentication
# ==============================================================================

def verify_worker_token(authorization: Optional[str] = Header(None)) -> None:
    """
    ZH: 驗證 Worker 節點的靜態 API Token（使用 hmac.compare_digest 防計時攻擊）
    EN: Validate Worker API token using hmac.compare_digest to prevent timing attacks
    """
    if not authorization:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Missing Worker API Token")
    expected = f"Bearer {settings.WORKER_API_TOKEN}"
    if not hmac.compare_digest(authorization, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Invalid Worker API Token")


# ==============================================================================
# ZH: 請求 / 回應模型 (定義於此因為是 Worker 專屬) | EN: Request/Response models
# ==============================================================================

class TakeJobRequest(BaseModel):
    node_id: str
    available_gpus: List[str]


class TakeJobResponse(BaseModel):
    job: Optional[dict] = None


class JobUpdatePayload(BaseModel):
    status: Optional[str] = None
    progress: Optional[float] = None
    log: Optional[str] = None
    output_path: Optional[str] = None
    error_message: Optional[str] = None


# ==============================================================================
# ZH: 端點 | EN: Endpoints
# ==============================================================================

@router.post("/take", response_model=TakeJobResponse)
def take_job(
    req: TakeJobRequest,
    db: Session = Depends(get_db),
    _: None = Depends(verify_worker_token),
):
    """
    ZH: Worker 節點請求任務（原子搶佔，防止多節點重複領取）
    EN: Worker claims a job atomically, preventing double-dispatch across nodes
    """
    if not req.available_gpus:
        return {"job": None}

    pending_jobs = crud.get_pending_jobs(db)
    if not pending_jobs:
        return {"job": None}

    job = pending_jobs[0]
    gpu_id = req.available_gpus[0]

    # ZH: 原子搶佔：只有當 status 仍為 "pending" 時才更新，rowcount=0 代表已被搶佔
    # EN: Atomic claim: only succeeds if status is still "pending"; rowcount=0 means already taken
    result = db.execute(
        update(models.TrainingJob)
        .where(models.TrainingJob.id == job.id)
        .where(models.TrainingJob.status == "pending")
        .values(
            status="running",
            gpu_server=req.node_id,
            gpu_id=gpu_id,
            started_at=datetime.now(timezone.utc),
        )
    )
    db.commit()

    if result.rowcount == 0:
        logger.info(f"Job {job.id[:8]} already claimed by another worker, skipping")
        return {"job": None}

    db.refresh(job)

    config = {}
    if job.config:
        try:
            config = json.loads(job.config)
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse config for job {job.id[:8]}")

    logger.info(f"Worker {req.node_id} claimed job {job.id[:8]} on GPU {gpu_id}")
    return {
        "job": {
            "job_id": job.id,
            "script_path": job.script_path or "/workspace/train.py",
            "dataset_path": job.dataset_path,
            "config": config,
            "gpu_id": gpu_id,
        }
    }


@router.post("/heartbeat")
def worker_heartbeat(
    payload: schemas.WorkerHeartbeatPayload,
    db: Session = Depends(get_db),
    _: None = Depends(verify_worker_token),
):
    """
    ZH: Worker 定期上報節點存活與 GPU 使用率（建議每 30 秒一次）
    EN: Worker periodically reports liveness and GPU utilization (recommend every 30s)
    """
    crud.upsert_worker_heartbeat(
        db, payload.node_id, payload.available_gpus, payload.gpu_utilization or 0.0
    )
    logger.debug(f"Heartbeat from {payload.node_id}, gpus={payload.available_gpus}")
    return {"status": "ok", "node_id": payload.node_id}


@router.post("/jobs/{job_id}/update")
def update_job(
    job_id: str,
    payload: JobUpdatePayload,
    db: Session = Depends(get_db),
    _: None = Depends(verify_worker_token),
):
    """
    ZH: Worker 回報任務進度與狀態
    EN: Worker reports job progress and status
    """
    job = crud.get_job(db, job_id=job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if payload.progress is not None:
        crud.update_job_progress(db, job_id, progress=payload.progress)

    if payload.log:
        crud.append_job_log(db, job_id, payload.log)

    if payload.status:
        crud.update_job_status(
            db, job_id,
            status=payload.status,
            output_path=payload.output_path,
            error_message=payload.error_message,
        )
        if payload.status == "completed":
            crud.update_job_progress(db, job_id, progress=100.0)

    return {"status": "ok"}
