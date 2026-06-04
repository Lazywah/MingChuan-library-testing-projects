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

    gpu_id_str = req.available_gpus[0]
    # H-7: ZH: gpu_id 欄位定義為 Integer，存入時轉型，回傳 Worker 時仍用字串
    # EN: Column is Integer; cast before storing, return original string to worker
    gpu_id_int = int(gpu_id_str) if gpu_id_str.isdigit() else 0

    # H-6: ZH: 若第一筆任務已被其他節點搶佔，依序嘗試下一筆，直到搶佔成功或清單用盡
    # EN: If top job was already claimed, walk the list until one succeeds or all are taken
    for job in pending_jobs:
        # ZH: 若任務指定偏好節點且與當前節點不符則跳過（讓對應節點來領）
        # EN: If job has a preferred_node and it doesn't match this node, skip it
        if job.preferred_node and job.preferred_node != req.node_id:
            logger.debug(
                "Job %s prefers node %s, skipping node %s",
                job.id[:8], job.preferred_node, req.node_id
            )
            continue

        result = db.execute(
            update(models.TrainingJob)
            .where(models.TrainingJob.id == job.id)
            .where(models.TrainingJob.status == "pending")
            .values(
                status="running",
                gpu_server=req.node_id,
                gpu_id=gpu_id_int,
                started_at=datetime.now(timezone.utc),
            )
        )
        db.commit()

        if result.rowcount == 0:
            logger.info(f"Job {job.id[:8]} already claimed by another worker, trying next")
            continue  # H-6: try next job

        db.refresh(job)

        config = {}
        if job.config:
            try:
                config = json.loads(job.config)
            except json.JSONDecodeError:
                logger.warning(f"Failed to parse config for job {job.id[:8]}")

        entry_args = None
        if job.entry_args:
            try:
                entry_args = json.loads(job.entry_args)
            except json.JSONDecodeError:
                logger.warning(f"Failed to parse entry_args for job {job.id[:8]}")

        # ZH: v2.0 — 為 GPU 容器注入該使用者的 secrets 與掛載 per-user / shared volumes
        # EN: v2.0 — inject user's secrets + per-user volume + shared models for GPU container
        extra_env: dict = {}
        volume_mounts: list = []
        try:
            from ..services import secrets_service
            extra_env = secrets_service.build_docker_env(db, job.user_id) if job.user_id else {}
        except Exception as e:
            logger.warning(f"Failed to build secret env for job {job.id[:8]}: {e}")

        if job.user_id:
            # ZH: per-user home volume → /home/coder（與 code-server 共用）
            # EN: per-user home volume → /home/coder (shared with code-server)
            volume_mounts.append({
                "name":   f"home_{job.user_id}",
                "target": "/home/coder",
                "mode":   "rw",
            })

        # ZH: 共享模型快取 → /opt/models (read-only)
        # EN: shared model cache → /opt/models (read-only)
        volume_mounts.append({
            "name":   "shared_models",
            "target": "/opt/models",
            "mode":   "ro",
        })

        logger.info(
            f"Worker {req.node_id} claimed job {job.id[:8]} on GPU {gpu_id_str} "
            f"| {len(extra_env)} secret(s) | {len(volume_mounts)} mount(s)"
        )
        return {
            "job": {
                "job_id":       job.id,
                "script_path":  job.script_path or "/workspace/train.py",
                "dataset_path": job.dataset_path,
                "config":       config,
                "gpu_id":       gpu_id_str,       # ZH: 字串格式，供 Worker 執行 docker --gpus | EN: String for worker's docker --gpus
                # ZH: Notebook 欄位 | EN: Notebook fields
                "docker_image": job.docker_image,  # ZH: 自訂 Image，None 代表使用預設 | EN: Custom image, None = use default
                "inline_code":  job.inline_code,   # ZH: 前端合併的 shell script | EN: Compiled shell script from frontend
                "entry_args":   entry_args,        # ZH: 非 Python 工具的入口指令 | EN: Entry command for non-Python tools
                # ZH: v2.0 Lab 欄位 | EN: v2.0 Lab fields
                "extra_env":     extra_env,        # ZH: 注入容器的環境變數 (含 secrets) | EN: Env vars to inject (with secrets)
                "volume_mounts": volume_mounts,    # ZH: 額外 docker -v 掛載 | EN: Additional docker -v mounts
            }
        }

    return {"job": None}


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
        db, payload.node_id, payload.available_gpus, payload.gpu_utilization or 0.0,
        gpus_detail=payload.gpus_detail,
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
