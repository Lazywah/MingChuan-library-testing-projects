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
    POST /jobs/{id}/artifact   → Worker 回傳訓練產出（模型檔）
    GET  /datasets/{job_id}    → Worker 下載該任務的資料集（跨機部署用）
ZH: 認證：所有端點使用靜態 API Token（Bearer），由 verify_worker_token Depends 驗證
EN: Auth: All endpoints use static API Token (Bearer), enforced via verify_worker_token
==============================================================================
"""

from fastapi import APIRouter, Depends, HTTPException, status, Header, Request, UploadFile, File
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from sqlalchemy import update
from pydantic import BaseModel
from typing import List, Optional
import json
import hmac
import logging
import os
import pathlib
import shutil
from datetime import datetime, timezone

from ..database import get_db
from .. import crud, models, schemas
from ..config import settings
from ..services import lab_manager

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
    # ZH: v3.6 —— 一筆結構化訓練指標（dataset / epoch / summary）。
    #     沒有這個欄位的話，訓練結果只存在 GPU 主機的 result.json 上，
    #     跨機部署時服務層根本讀不到，畫面就只能說「完成」而說不出正確率。
    metric: Optional[dict] = None
    progress: Optional[float] = None
    log: Optional[str] = None
    output_path: Optional[str] = None
    error_message: Optional[str] = None


# ==============================================================================
# ZH: 端點 | EN: Endpoints
# ==============================================================================

def _gpu_index(raw) -> int:
    """
    ZH: worker 送來的 GPU 識別轉成整數卡號。轉不動回 -1（永遠不會等於任何佔用值）。

    ZH: ⚠ 回 -1 而不是拋錯：這支只被「排除佔用中的卡」用到，
        轉不動時**寧可讓它通過**也不要讓整個節點領不到工作 ——
        認不得的格式是我們的問題，不該變成節點停擺。

    @node job-scheduler/app/routers/worker.py::_gpu_index
    """
    try:
        return int(str(raw).strip())
    except (TypeError, ValueError):
        return -1


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

    # ZH: v3.9 互動式 GPU 實驗室閘門 —— 把被實驗室佔住的卡從可派清單裡拿掉。
    #
    # ZH: 🔴 為什麼一定要在這裡擋：worker 只看自己行程內的 `_busy_gpus`，
    #     它**看不到 Lab 容器**。不擋的話，同一張卡會同時跑一個訓練任務和一個
    #     互動式實驗室，兩邊搶 VRAM → 學生拿到 CUDA OOM，而且看不出是被誰佔走。
    #
    # ZH: ⚠ 只對**與服務層同機**的節點生效。台北的節點有自己的卡，
    #     服務層這邊的實驗室佔用跟它無關 —— 拿去擋它會讓遠端節點永遠領不到工作。
    #     判斷用 worker 自己宣告的 `shares_service_storage`（預設 False，安全的一邊）。
    if req.shares_service_storage:
        held = crud.gpus_held_by_labs(db)
        if held:
            usable = [g for g in req.available_gpus if _gpu_index(g) not in held]
            if not usable:
                logger.debug("Node %s: all GPUs held by interactive labs %s",
                             req.node_id, sorted(held))
                return {"job": None}
            req.available_gpus = usable

    pending_jobs = crud.get_pending_jobs(db)
    if not pending_jobs:
        return {"job": None}

    # ZH: v4.17（方案二 2.4）派工端的配額。
    #
    # ZH: 這在 v4.17 之前是**送單**時做的，而且是叢集層級的一個數字（預設 4）——
    #     30 台上線那天會有 26 台因為那一行空著。容量本來就由「有幾張空卡」
    #     決定（worker 只在有空卡時才來領工作），所以這裡要管的是**公平**：
    #     一個人同時跑幾張。沒有這一條的話，一個人送 50 張單就會佔滿整個叢集。
    #
    # ZH: 🔴 超過上限的單是**跳過**不是拒絕 —— 它留在佇列裡等這個人手上的跑完。
    #     跳過它就等於讓下一個人的單先出場，公平是這樣達成的。
    #
    # ZH: ⚠ 一次查出所有人的在跑數，不要在迴圈裡逐張問：
    #     這支每 5 秒被每一台節點各打一次。
    per_user_cap = crud.get_setting(db, "max_jobs_per_user")
    running_by_user = crud.running_jobs_by_user(db)

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

        # ZH: v4.17 配額 —— 這個人手上已經有夠多張在跑了，先讓別人的單出場。
        #     admin / teacher 免檢（沿用 v4.17 之前送單端的同一條規則，
        #     不在這次改動裡順手改變誰有特權）。
        if job.user_id and running_by_user.get(job.user_id, 0) >= per_user_cap:
            owner = db.get(models.User, job.user_id)
            if not (owner and (owner.is_admin or owner.role == "teacher")):
                logger.debug(
                    "Job %s skipped: its owner already has %d running (cap %d)",
                    job.id[:8], running_by_user.get(job.user_id, 0), per_user_cap)
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
                # ZH: 🔴 名字**一定要與 lab_manager 一致**。這裡原本自己寫
                #     `f"home_{user_id}"`，而 lab_manager 用的是把連字號換成底線的版本
                #     —— 兩個名字不同，docker 就在那台**自動建一個空的**同名 volume：
                #     不報錯、資料不在、訓練出沒有意義的結果。已在真實使用者身上發生過。
                "name":   lab_manager.volume_name_for(job.user_id),
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

        # ZH: v3.6 —— 內建任務指名映像（使用者沒自己選的話）。內建腳本需要 torchvision，
        #     不能落到 worker 的 DEFAULT_IMAGE 去賭它剛好有。
        builtin_task = crud.builtin_task_for(job)
        # ZH: v3.6 —— 使用者指定 > 內建任務指名 > 自帶程式用平台標準環境 > worker 預設。
        docker_image = (job.docker_image
                        or (crud.builtin_task_image(builtin_task) if builtin_task else None)
                        or crud.default_training_image(job))

        logger.info(
            f"Worker {req.node_id} claimed job {job.id[:8]} on GPU {gpu_id_str} "
            f"| {len(extra_env)} secret(s) | {len(volume_mounts)} mount(s)"
        )
        return {
            "job": {
                "job_id":       job.id,
                "script_path":  job.script_path or "/workspace/train.py",
                # ZH: v3.6 —— 這裡**不再**送 job.dataset_path。那是服務層容器裡的絕對路徑
                #     （/data/datasets/…），worker 在別的容器、甚至別台機器上，
                #     拿到那個字串沒有任何用處。改成「有沒有」＋原始檔名，
                #     真的要檔案就走 GET /worker/datasets/{job_id} 下載。
                # EN: v3.6 — the service-layer container path is meaningless to the worker.
                #     Send a flag + the original filename; fetch the bytes via the endpoint.
                "has_dataset":      bool(job.dataset_path),
                "dataset_filename": (pathlib.Path(job.dataset_path).name
                                     if job.dataset_path else None),
                # ZH: v3.6 內建訓練腳本（使用者只上傳資料、不寫程式時）。None ＝ 自己帶程式。
                "builtin_task":     builtin_task,
                "config":       config,
                "gpu_id":       gpu_id_str,       # ZH: 字串格式，供 Worker 執行 docker --gpus | EN: String for worker's docker --gpus
                # ZH: Notebook 欄位 | EN: Notebook fields
                "docker_image": docker_image,      # ZH: 使用者指定 > 內建任務指名 > None(worker 預設) | EN: user > task-pinned > worker default
                "inline_code":  job.inline_code,   # ZH: 前端合併的 shell script | EN: Compiled shell script from frontend
                # ZH: v3.6 使用者自帶的訓練程式。worker 會把它寫進共享儲存再執行。
                "script_source": job.script_source,
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

    # ZH: v4.15（方案二 2.5）—— 節點回報有卡壞掉。
    #
    # ZH: 🔴 一定要寄信，不能只記 log。這種故障的症狀是「某一台從此每張單都失敗」，
    #     而每一張單的錯誤訊息都不一樣（CUDA OOM / no kernel image / 初始化失敗…），
    #     從使用者回報根本拼不出「是那台機器壞了」。而容器日誌沒有人會定期翻
    #     （_alert 的註解講的就是同一件事）。
    #
    # ZH: ⚠ 節流與「收件人留空就不寄」都在 email_service.send_admin_alert 裡，
    #     所以這裡**每次心跳都呼叫是安全的** —— 不會每 30 秒寄一封。
    if payload.unhealthy_gpus:
        logger.error("ZH: 節點 %s 回報 GPU 異常：%s | EN: node %s reports unhealthy GPUs: %s",
                     payload.node_id, payload.unhealthy_gpus,
                     payload.node_id, payload.unhealthy_gpus)
        try:
            # ZH: 延遲匯入 —— routers 在 import 期就拉進 scheduler 會繞回來。
            from ..scheduler import _alert
            _alert(
                "gpu_unhealthy",
                "GPU 節點回報有卡不能用 / A GPU node reports an unusable card",
                _unhealthy_detail(payload.node_id, payload.unhealthy_gpus),
            )
        except Exception as e:
            # ZH: 告警失敗不能讓心跳跟著失敗 —— 節點會以為服務層掛了。
            logger.error("Could not send the unhealthy-GPU alert: %s", e)

    return {"status": "ok", "node_id": payload.node_id}


# ==============================================================================
# ZH: v4.14（方案二 2.2）指令通道 —— worker 問「這張單還要不要繼續」
# ==============================================================================
# ZH: 為什麼需要一支**專門**的端點，而不是只靠 /update 的回應：
#     /update 只有在容器**印東西出來**時才會被呼叫。一個安靜的訓練
#     （或一個已經卡死的容器）可以幾十分鐘不吐一行 ——
#     那正是最需要停掉它的情況，卻剛好是 /update 永遠不會來的情況。
#     所以 worker 另外開一條固定節奏的輪詢，與容器有沒有輸出無關。
#     （Buildkite agent 的 Job Cancellation Checker 是同一個結構。）
#
# ZH: 🔴 找不到這張單也回 stop —— 那是**孤兒容器**：服務層的資料庫裡沒有它，
#     代表沒有任何人在等它的結果，而它還佔著一張卡。
#
# ZH: ⚠ 這支刻意**不寫任何東西**（純讀）。它會被每個執行中的任務每隔幾秒打一次，
#     帶上寫入的話，30 台 × N 張單就變成一個沒有必要的持續寫入來源。
@router.get("/images", summary="v4.18 這個平台可能派出哪些映像（給節點預拉用）")
def dispatchable_images(
    _: None = Depends(verify_worker_token),
):
    """
    ZH: 回平台**自己會指派**的映像清單，讓節點開機時先拉起來放著。

    ZH: 🔴 為什麼由服務層回答，不是讓 worker 自己猜：選映像的規則在
        `crud.default_training_image` / `builtin_task_image` 裡，
        worker 手上沒有那份規則。各自維護一份清單的結果是
        「預拉了一堆用不到的，而真正要用的那個還是冷的」——
        那時症狀跟沒有預拉一模一樣，只是多花了頻寬。

    ZH: ⚠ 這裡**不含** worker 自己的 `DEFAULT_IMAGE`：那是節點端的設定
        （不同節點可以不一樣），由 worker 自己加進去。

    @node job-scheduler/app/routers/worker.py::dispatchable_images
    """
    images = {crud.PLATFORM_TRAINING_IMAGE}
    for task in crud.BUILTIN_TASKS:
        img = crud.builtin_task_image(task)
        if img:
            images.add(img)
    return {"images": sorted(images)}


def _unhealthy_detail(node_id: str, gpus) -> str:
    """ZH: 壞卡告警的內文。抽出來是為了用三引號寫多行，不必在字串裡處理跳脫。

    @node job-scheduler/app/routers/worker.py::_unhealthy_detail
    """
    return """節點 / node: {node}
有問題的 GPU / unhealthy: {gpus}

這張卡已經不再接受新任務。修好之後重啟該節點的 worker 即可恢復
（隔離是行程內的，重啟就會重新評估）。
The card has stopped taking work; restart that node's worker once it is fixed.""".format(
        node=node_id, gpus=", ".join(gpus))


@router.get("/jobs/{job_id}/control", summary="v4.14 worker 問這張單該不該繼續")
def job_control(
    job_id: str,
    db: Session = Depends(get_db),
    _: None = Depends(verify_worker_token),
):
    """
    ZH: 回 `{"action": "continue" | "stop"}`。
    EN: Tell the worker whether to keep running this job.

    @node job-scheduler/app/routers/worker.py::job_control
    """
    job = crud.get_job(db, job_id=job_id)
    if not job:
        logger.warning(
            "ZH: control：資料庫裡沒有任務 %s，要求 worker 停掉（孤兒容器） | "
            "EN: control: unknown job %s, telling the worker to stop",
            job_id[:8], job_id[:8],
        )
        return {"action": "stop", "reason": "unknown_job"}

    if job.status in crud.TERMINAL_JOB_STATES:
        return {"action": "stop", "reason": job.status}

    return {"action": "continue"}


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

    if payload.metric is not None:
        crud.append_job_metric(db, job_id, payload.metric)

    if payload.status:
        crud.update_job_status(
            db, job_id,
            status=payload.status,
            output_path=payload.output_path,
            error_message=payload.error_message,
        )
        if payload.status == "completed":
            crud.update_job_progress(db, job_id, progress=100.0)

    # ZH: v4.14 —— 回應順便當指令通道。容器有在印東西的時候，
    #     這條路比固定節奏的 control 輪詢更快（不必等下一次輪詢）。
    #     ⚠ 這裡要**重讀一次**狀態：上面的 update_job_status 可能因為終態守衛
    #     而沒有套用 payload，job 物件手上的值不一定是資料庫的現況。
    fresh = crud.get_job(db, job_id=job_id)
    if fresh and fresh.status in crud.TERMINAL_JOB_STATES:
        return {"status": "ok", "action": "stop", "reason": fresh.status}

    return {"status": "ok", "action": "continue"}


# ==============================================================================
# ZH: v3.6 資料集下載 | EN: v3.6 Dataset download
# ==============================================================================

# ZH: **直接引用上傳端的常數，不另抄一份。** 上傳寫到哪、下載就從哪讀；
#     抄成兩份的話，有人改了其中一個就會變成「上傳成功但下載 404」。
# EN: Import the uploader's constant instead of copying the value.
from .datasets import DATASET_DIR as DATASET_ROOT


@router.get("/datasets/{job_id}")
def download_job_dataset(
    job_id: str,
    db: Session = Depends(get_db),
    _: None = Depends(verify_worker_token),
):
    """
    ZH: Worker 下載某張任務的資料集壓縮檔。

    ZH: 為什麼需要這個端點：資料集存在**服務層**的磁碟上，而 GPU 節點可能是另一台機器。
        原本的 `dataset_path` 只是服務層容器裡的一個字串，跨機時毫無意義。

    ZH: 存取範圍：以 **job_id** 定位，不是以路徑參數定位——worker 只能拿到
        「它正在跑的那張單」對應的檔案，沒辦法用這個端點翻別人的資料夾。
        另外仍然做一次路徑歸一化檢查：DB 裡的 dataset_path 萬一被寫壞或被塞了
        `../`，也不會讀到 DATASET_ROOT 以外的東西。

    @node job-scheduler/app/routers/worker.py::download_job_dataset
    """
    job = crud.get_job(db, job_id=job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    if not job.dataset_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="This job has no dataset")

    # ZH: 路徑歸一化 + 必須落在資料集根目錄內（縱深防禦：不信任 DB 裡的字串）
    # EN: Defence in depth — never trust the stored path; it must resolve inside the root.
    root = os.path.realpath(DATASET_ROOT)
    target = os.path.realpath(job.dataset_path)
    if not (target == root or target.startswith(root + os.sep)):
        logger.error("Job %s dataset_path escapes the dataset root: %r",
                     job_id[:8], job.dataset_path)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found")

    if not os.path.isfile(target):
        # ZH: 檔案不在了（被清掉／換機沒搬過來）。這是明確的失敗，不要讓它變成
        #     「訓練跑起來但資料夾是空的」。
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Dataset file is missing on the service layer")

    logger.info("Worker downloading dataset for job %s (%s)", job_id[:8],
                pathlib.Path(target).name)
    return FileResponse(target, media_type="application/octet-stream",
                        filename=pathlib.Path(target).name)


# ==============================================================================
# ZH: v3.6 訓練產出（模型檔）| EN: v3.6 Training artifacts
# ==============================================================================
# ZH: 訓練完的 model.pt 原本只留在**運算主機**上，跨機時服務層讀不到，
#     使用者也就拿不到。worker 訓練成功後把它傳回來，存在這裡。
#
# ZH: 路徑由 job_id 推導，**不另存路徑欄位** —— 少一個會跟實體檔案漂開的字串。
#     DB 只記 `artifact_bytes`（有值＝這邊真的有那個檔）。
ARTIFACT_ROOT = os.environ.get("ARTIFACT_DIR", "/data/artifacts")
ARTIFACT_NAME = "model.pt"

# ZH: 單一檔案上限。ResNet-18 約 44 MB；留寬一點給日後較大的模型，
#     但仍然要有上限——worker 被入侵時這是唯一擋著磁碟被塞爆的東西。
MAX_ARTIFACT_BYTES = int(os.environ.get("MAX_ARTIFACT_BYTES", str(2 * 1024 ** 3)))
# ZH: 每位使用者保留幾個模型檔。**這是硬上限** —— 沒有它，一個晚上跑一百張單
#     就會佔掉幾 GB，而且沒有任何東西會擋。
ARTIFACT_KEEP_PER_USER = int(os.environ.get("ARTIFACT_KEEP_PER_USER", "10"))
# ZH: 保留天數，收拾不再使用的帳號留下的長尾（每日 03:00 掃描）。
ARTIFACT_TTL_DAYS = int(os.environ.get("ARTIFACT_TTL_DAYS", "30"))


def remove_artifact_file(job_id: str) -> None:
    """ZH: 刪掉一張單的模型檔（連同它的目錄）。找不到不算錯。

    @node job-scheduler/app/routers/worker.py::remove_artifact_file
    """
    d = os.path.join(ARTIFACT_ROOT, job_id)
    shutil.rmtree(d, ignore_errors=True)


def artifact_path(job_id: str) -> str:
    """ZH: 這張單的模型檔在服務層的位置。

    @node job-scheduler/app/routers/worker.py::artifact_path
    """
    return os.path.join(ARTIFACT_ROOT, job_id, ARTIFACT_NAME)


@router.post("/jobs/{job_id}/artifact")
async def upload_job_artifact(
    job_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _: None = Depends(verify_worker_token),
):
    """
    ZH: Worker 把訓練產出（模型檔）傳回服務層。

    ZH: 為什麼需要：檔案原本只在運算主機上。跨機部署時服務層讀不到，
        畫面就給不出下載——而「訓練完了但拿不到東西」是最令人洩氣的結果。

    ZH: 上限是**邊寫邊數**的，不信任 Content-Length（那是請求方說了算）。
        超過就刪掉半套的檔案並回 413，不留殘骸。

    @node job-scheduler/app/routers/worker.py::upload_job_artifact
    """
    job = crud.get_job(db, job_id=job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    dest = artifact_path(job_id)
    os.makedirs(os.path.dirname(dest), exist_ok=True)

    total = 0
    try:
        with open(dest, "wb") as out:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_ARTIFACT_BYTES:
                    raise ValueError("artifact exceeds the size limit")
                out.write(chunk)
    except ValueError:
        # ZH: 半套的檔案比沒有檔案更糟——它看起來像有，下載下來卻是壞的。
        try:
            os.remove(dest)
        except OSError:
            pass
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Artifact exceeds the {MAX_ARTIFACT_BYTES // 1024 ** 2} MB limit")
    except Exception as e:
        try:
            os.remove(dest)
        except OSError:
            pass
        logger.error("Job %s: could not store the artifact: %s", job_id[:8], e)
        raise HTTPException(status_code=500, detail="Could not store the artifact")

    crud.set_job_artifact(db, job_id, total)
    logger.info("Stored artifact for job %s (%.1f MB)", job_id[:8], total / 1024 ** 2)

    # ZH: 每人只留最近 N 個 —— **硬上限**，跑再多次也不會無限長。
    #     在上傳當下就淘汰，而不是等每日掃描：等一天的話，一個晚上跑一百張單
    #     就已經佔掉幾 GB 了。
    if job.user_id:
        n = crud.enforce_artifact_limits(db, job.user_id, ARTIFACT_KEEP_PER_USER,
                                         remove_artifact_file)
        if n:
            logger.info("Removed %d older artifact(s) for this user (keeping %d)",
                        n, ARTIFACT_KEEP_PER_USER)

    return {"status": "ok", "bytes": total}
