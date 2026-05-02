from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional
import logging

from ..database import get_db
from .. import crud, models

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Worker 節點通訊 Worker Nodes"])

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
def take_job(req: TakeJobRequest, db: Session = Depends(get_db)):
    """
    ZH: Worker 節點請求任務
    EN: Worker node requesting a job
    """
    if not req.available_gpus:
        return {"job": None}
        
    # ZH: 取得 pending 任務 (依照優先權或建立時間) | EN: Get pending jobs
    pending_jobs = crud.get_pending_jobs(db)
    if not pending_jobs:
        return {"job": None}
        
    job = pending_jobs[0]
    gpu_id = req.available_gpus[0]
    
    # ZH: 標記為 running | EN: Mark as running
    crud.update_job_status(
        db, job.id,
        status="running",
        gpu_server=req.node_id,
        gpu_id=gpu_id
    )
    
    # ZH: 解析 Config | EN: Parse config
    import json
    config = {}
    if job.config:
        try:
            config = json.loads(job.config)
        except:
            pass
            
    return {
        "job": {
            "job_id": job.id,
            "script_path": job.script_path or "/workspace/train.py",
            "dataset_path": job.dataset_path,
            "config": config,
            "gpu_id": gpu_id
        }
    }

@router.post("/jobs/{job_id}/update")
def update_job(job_id: str, payload: JobUpdatePayload, db: Session = Depends(get_db)):
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
