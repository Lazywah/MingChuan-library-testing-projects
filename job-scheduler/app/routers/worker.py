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

from fastapi import APIRouter, Depends, HTTPException, status, Header, Request
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

    @node job-scheduler/app/routers/worker.py::verify_worker_token
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
    # ZH: v3.6 —— 節點是否與服務層同機。**預設 False（安全的一邊）**：
    #     舊版 worker 不會送這個欄位，於是自動被當成「不同機」，
    #     Notebook 任務不會被派給它——寧可不派，也不要派出去訓練在空目錄上。
    shares_service_storage: bool = False
    available_gpus: List[str]
    pool_type: Optional[str] = "batch"   # v3.0 領取端節點所屬池 batch/interactive


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

    @node job-scheduler/app/routers/worker.py::take_job
    """
    if not req.available_gpus:
        return {"job": None}

    # ZH: v3.2 節點管理閘門 — 節點被停用或在可排程時段外（含停派緩衝）時不派新工。
    #     心跳照常、執行中任務不受影響（drain：跑完為止）。未註冊節點＝允許（向後相容）。
    # EN: v3.2 node-management gate — no new dispatch when the node is disabled or
    #     outside its schedule window (incl. dispatch buffer). Heartbeats and
    #     running jobs are unaffected (drain policy). Unregistered node = allowed.
    node_cfg = crud.get_gpu_node(db, req.node_id)
    gate = crud.node_dispatch_state(node_cfg)
    if not gate["allowed"]:
        logger.debug("Node %s dispatch blocked (%s)", req.node_id, gate["reason"])
        return {"job": None}

    pending_jobs = crud.get_pending_jobs(db)
    if not pending_jobs:
        return {"job": None}

    # ZH: v3.0 本地 GPU 路由分流（首選對應池 + batch 墊底）
    #   領取端池 = interactive → 只領 interactive 任務（服務層 GPU 不跑重量級 batch 訓練）
    #   領取端池 = batch        → 一律可領 batch 任務；interactive 任務「只有互動池目前沒有
    #                             在線 worker 時」才代領（墊底），避免任務卡死也不搶互動池的活
    # EN: v3.0 local-GPU routing — prefer matching pool, batch backfills interactive
    #     only when no interactive worker is online. See create_job/pool_has_online_worker.
    # ZH: v3.2 池別以 admin 覆蓋值優先（換池免改 worker env）| EN: v3.2 admin override wins
    taker_pool = crud.effective_pool(node_cfg, req.pool_type)
    interactive_up = crud.pool_has_online_worker(db, "interactive") if taker_pool == "batch" else False

    def _pool_allows(job) -> bool:
        """@node job-scheduler/app/routers/worker.py::take_job.<nested@119>._pool_allows"""
        job_pool = crud.normalize_pool(getattr(job, "pool_type", "batch"))
        if taker_pool == "interactive":
            return job_pool == "interactive"
        # taker_pool == "batch"
        if job_pool == "interactive":
            return not interactive_up   # 只在互動池沒人時墊底
        return True

    gpu_id_str = req.available_gpus[0]
    # H-7: ZH: gpu_id 欄位定義為 Integer，存入時轉型，回傳 Worker 時仍用字串
    # EN: Column is Integer; cast before storing, return original string to worker
    gpu_id_int = int(gpu_id_str) if gpu_id_str.isdigit() else 0

    # H-6: ZH: 若第一筆任務已被其他節點搶佔，依序嘗試下一筆，直到搶佔成功或清單用盡
    # EN: If top job was already claimed, walk the list until one succeeds or all are taken
    for job in pending_jobs:
        # ZH: v3.0 池路由過濾（首選對應池 + batch 墊底）
        # EN: v3.0 pool routing filter (prefer matching pool, batch backfills)
        if not _pool_allows(job):
            continue

        # ZH: v3.6 —— Notebook/Lab 模式的任務需要使用者的 `home_<uid>` volume，
        #     而那是**本機** Docker volume。派給不同機的節點時，docker 會在那台
        #     **自動建立一個空的**同名 volume：不報錯、資料不在、訓練出沒有意義的結果。
        #     **寧可不派**（留給同機節點），也不要派出去在空目錄上訓練。
        if crud.job_needs_lab_volume(job) and not req.shares_service_storage:
            logger.info(
                "Job %s needs the user's Lab volume; node %s is not co-located with the "
                "service layer - leaving it pending", job.id[:8], req.node_id
            )
            continue

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

        # ZH: v3.6 —— per-user home volume 只在與服務層同機時才有意義（見上方派工閘門）。
        #     不同機時**不掛**：掛一個空 volume 只會讓腳本以為「資料夾是空的」，
        #     比缺少掛載更難查。
        if job.user_id and req.shares_service_storage:
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
    request: Request,
    db: Session = Depends(get_db),
    _: None = Depends(verify_worker_token),
):
    """
    ZH: Worker 定期上報節點存活與 GPU 使用率（建議每 30 秒一次）
        v3.2：記錄來源 IP 供 NODE_ID 撞名偵測（多台機器抄同一個範本 NODE_ID 的地雷）
    EN: Worker periodically reports liveness and GPU utilization (recommend every 30s)

    @node job-scheduler/app/routers/worker.py::worker_heartbeat
    """
    source_ip = request.client.host if request.client else None
    crud.upsert_worker_heartbeat(
        db, payload.node_id, payload.available_gpus, payload.gpu_utilization or 0.0,
        gpus_detail=payload.gpus_detail, pool_type=payload.pool_type,
        source_ip=source_ip, shares_storage=payload.shares_service_storage,
    )
    logger.debug(f"Heartbeat from {payload.node_id}, gpus={payload.available_gpus}, pool={payload.pool_type}")
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

    @node job-scheduler/app/routers/worker.py::update_job
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
