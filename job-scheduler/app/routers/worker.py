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
from .. import crud, models
from ..config import settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Worker 節點通訊 Worker Nodes"])


def verify_worker_token(authorization: Optional[str] = Header(None)):
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


@router.post("/take", response_model=TakeJobResponse)
def take_job(req: TakeJobRequest, db: Session = Depends(get_db), _: None = Depends(verify_worker_token)):
    """
    ZH: Worker 節點請求任務（原子搶佔，防止多節點重複領取）
    EN: Worker claims a job atomically, preventing double-dispatch across nodes
    """
    if not req.available_gpus:
        return {"job": None}

    # ZH: 取得最高優先級的 pending 任務 ID
    # EN: Get the highest-priority pending job ID
    pending_jobs = crud.get_pending_jobs(db)
    if not pending_jobs:
        return {"job": None}

    job = pending_jobs[0]
    gpu_id = req.available_gpus[0]

    # ZH: 原子搶佔：只有當 status 仍為 "pending" 時才更新
    # EN: Atomic claim: only update if status is still "pending"
    # ZH: 若另一 Worker 已搶先，rowcount=0，直接回傳 None
    # EN: If another worker claimed it first, rowcount=0, return None
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

@router.post("/jobs/{job_id}/update")
def update_job(job_id: str, payload: JobUpdatePayload, db: Session = Depends(get_db), _: None = Depends(verify_worker_token)):
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
        # If completing or failing
        crud.update_job_status(
            db, job_id,
            status=payload.status,
            output_path=payload.output_path,
            error_message=payload.error_message
        )
        if payload.status == "completed":
            crud.update_job_progress(db, job_id, progress=100.0)
            
    return {"status": "ok"}
