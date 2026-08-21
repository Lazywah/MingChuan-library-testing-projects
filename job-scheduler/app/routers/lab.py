"""
==============================================================================
Router: Lab Module（v2.0 — code-server session 管理）
==============================================================================
ZH: 用途：使用者啟動 / 停止 / 查詢自己的 code-server 工作階段
EN: Purpose: User-facing endpoints to start/stop/inspect their code-server session

ZH: 端點清單：
    POST  /api/v1/lab/start      → 啟動自己的 code-server
    POST  /api/v1/lab/stop       → 停止自己的 code-server
    GET   /api/v1/lab/status     → 查詢狀態 + 配額 + 注入 secrets（masked）
    POST  /api/v1/lab/heartbeat  → 更新 last_activity（aibase-runner extension 每 5 分鐘）
    GET   /api/v1/lab/nodes      → 取得線上 GPU 節點（給 VS Code extension 選節點）
    GET   /api/v1/lab/_authz     → 內部端點，給 nginx auth_request 驗證 /code/{user_id}/

ZH: 認證：所有端點（除 _authz）使用 JWT
==============================================================================
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, status, Header, Request
from sqlalchemy.orm import Session

from .. import crud, models, schemas
from ..auth import get_current_user
from ..database import get_db
from ..services import lab_manager, secrets_service, quota_service
from ..rate_limit import limiter

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Lab 模組 Lab Module"])


# ==============================================================================
# ZH: POST /lab/start - 啟動 code-server
# ==============================================================================
@router.post("/start")
@limiter.limit("5/minute")
def start_lab(
    request: Request,
    payload: dict = Body(default={}),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    ZH: 啟動使用者的 code-server 容器，回傳 URL 與 one-time password
    EN: Start user's code-server container, returns URL and one-time password

    v2.1 修正：base_image 從 query param 改為 JSON body 欄位 (前端 POST body 才會被收到)

    @node job-scheduler/app/routers/lab.py::start_lab
    """
    base_image = (payload or {}).get("base_image")
    # ZH: v3.6 多份存檔。沒帶＝預設那一份（既有前端不必改）。
    session = (payload or {}).get("session") or lab_manager.DEFAULT_SESSION
    # ZH: 🔴 一次只開一份 —— 先關掉其他正在跑的。
    #     **要回報關掉了哪一個**：使用者按下「開啟 B」而 A 被靜靜關掉，
    #     他會以為 A 壞了。
    switched_from = lab_manager._stop_other_running(db, current_user.id, keep=session)
    try:
        result = lab_manager.start_session(db, current_user.id, base_image=base_image,
                                           session=session)
    except PermissionError as e:
        raise HTTPException(status_code=429, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))

    if switched_from:
        result["switched_from"] = switched_from
    return result


# ==============================================================================
# ZH: POST /lab/stop - 主動停止 code-server
# ==============================================================================
@router.post("/stop")
def stop_lab(
    payload: dict = Body(default={}),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """ZH: 主動關閉自己的 session（volume 保留）| EN: Stop own session

    @node job-scheduler/app/routers/lab.py::stop_lab
    """
    session = (payload or {}).get("session") or lab_manager.DEFAULT_SESSION
    stopped = lab_manager.stop_session(db, current_user.id, reason="user_requested",
                                       session=session)
    return {"status": "stopped" if stopped else "no_active_session"}


# ==============================================================================
# ZH: GET /lab/status - 查詢狀態 + 配額 + 注入 secrets
# ==============================================================================
@router.get("/status")
def lab_status(
    session: Optional[str] = None,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    ZH: 回傳完整 session 狀態（給設定頁與 VS Code extension 顯示用）
    EN: Return full session status (for settings page & VS Code extension)

    @node job-scheduler/app/routers/lab.py::lab_status
    """
    # ZH: 🔴 沒指定存檔時要回**正在跑的那一份**，不是死板的 default。
    #     否則上方狀態卡會寫「未啟動」，而同一頁的存檔清單標著「執行中」。
    info = lab_manager.get_status(
        db, current_user.id,
        session=session or lab_manager.current_session_name(db, current_user.id))
    # 補上配額資訊
    info["effective_quota_gb"] = quota_service.get_effective_quota_gb(db, current_user.id)
    return info


# ==============================================================================
# ZH: POST /lab/heartbeat - extension 每 5 分鐘呼叫，更新 last_activity
# ==============================================================================
@router.post("/heartbeat")
def lab_heartbeat(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """ZH: 更新使用者 session 的 last_activity 防 idle timeout

    @node job-scheduler/app/routers/lab.py::lab_heartbeat
    """
    lab_manager.touch_activity(db, current_user.id)
    return {"status": "ok", "at": datetime.now(timezone.utc).isoformat()}


# ==============================================================================
# ZH: GET /lab/nodes - 線上 GPU 節點清單（給 VS Code extension）
# ==============================================================================
@router.get("/nodes")
def lab_nodes(
    pool: str = "batch",
    db: Session = Depends(get_db),
    _: models.User = Depends(get_current_user),
):
    """
    ZH: 列出線上 GPU 節點，可依 pool_type 篩選
    EN: List online GPU nodes, filterable by pool_type

    Pool types: "batch"（高階 GPU server）/ "interactive"（v2.1 才啟用）

    @node job-scheduler/app/routers/lab.py::lab_nodes
    """
    nodes = crud.get_online_worker_nodes(db, timeout_seconds=90)
    # 依 pool_type 篩選
    filtered = [n for n in nodes if getattr(n, "pool_type", "batch") == pool]
    return [
        {
            "node_id": n.node_id,
            "available_gpus": n.available_gpus,
            "gpu_utilization": n.gpu_utilization,
            "last_seen": n.last_seen.isoformat() if n.last_seen else None,
            "pool_type": getattr(n, "pool_type", "batch"),
        }
        for n in filtered
    ]


# ==============================================================================
# ZH: GET /lab/_authz - nginx auth_request 內部端點
# EN: GET /lab/_authz - internal endpoint for nginx auth_request
# ==============================================================================
@router.get("/_authz")
def lab_authz(
    request: Request,
    x_original_uri: Optional[str] = Header(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    ZH: nginx 驗證使用者是否可訪問 /code/{user_id}/ 或 /code/{user_id}-{存檔}/
    EN: nginx validates access to /code/{user_id}/ or /code/{user_id}-{workspace}/

    驗證 / Verification:
        1. JWT 必須有效（get_current_user 自動處理）
        2. URI 內的 {user_id} 必須等於 current_user.id
        3. 使用者必須有 running session

    @node job-scheduler/app/routers/lab.py::lab_authz
    """
    # 從 nginx 傳入的 X-Original-URI 取出 user_id
    if not x_original_uri or not x_original_uri.startswith("/code/"):
        raise HTTPException(status_code=403, detail="ZH: 路徑不合法 | EN: Invalid path")

    parts = x_original_uri.lstrip("/").split("/")
    if len(parts) < 2 or parts[0] != "code":
        raise HTTPException(status_code=403, detail="ZH: 路徑格式不正確 | EN: Invalid path structure")

    requested_user_id = parts[1]
    # ZH: v3.6 多份存檔 —— 網址是 `/code/<uid>/`（預設那一份）或
    #     `/code/<uid>-<存檔>/`。**比對的是前綴是不是自己的 id**，
    #     而且一定要用 `<id>-` 這個形式，不能只用 startswith(<id>)：
    #     那樣 `<id>` 是別人 id 的前綴時就會被放行。
    #     （user_id 是 UUID，本來就不會互為前綴；但判準不該建立在那件事上。）
    requested_session = None
    if requested_user_id.startswith(current_user.id + "-"):
        requested_session = requested_user_id[len(current_user.id) + 1:]
        requested_user_id = current_user.id
    if requested_user_id != current_user.id:
        raise HTTPException(
            status_code=403,
            detail="ZH: 你的登入資訊沒有權限存取這個人的實驗室 | EN: JWT does not authorize access to this user's lab"
        )

    # ZH: v3.6 —— 問的是「**這一份**在不在跑」，不是「這個人有沒有在跑」。
    #     不指定的話，A 存檔在跑時 B 存檔的網址也會被放行 —— 而 B 的容器根本不存在，
    #     nginx 會 proxy 到一個不存在的主機名，使用者看到的是 502 而不是「還沒啟動」。
    if not lab_manager.is_user_session_alive(
            db, current_user.id,
            session=requested_session or lab_manager.DEFAULT_SESSION):
        raise HTTPException(status_code=404, detail="ZH: 目前沒有執行中的實驗室 | EN: No active session")

    # nginx 預期 200 OK + 自訂 header（auth_request_set $auth_user $upstream_http_x_lab_user）
    from fastapi.responses import Response
    response = Response(status_code=200)
    response.headers["X-Lab-User"] = current_user.id
    return response


# ==============================================================================
# ZH: v3.6 多份存檔 | EN: v3.6 Multiple workspaces
# ==============================================================================

@router.get("/sessions")
def list_my_sessions(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    ZH: 列出自己的所有存檔。

    ZH: 沒有任何一份時**至少回一份 default** —— 既有使用者的資料都在那一份底下，
        列表空白會讓他以為東西不見了。

    @node job-scheduler/app/routers/lab.py::list_my_sessions
    """
    # ZH: 補 default 這件事已經收進 list_sessions（它保證一定在裡面）。
    #     這裡刻意不再放一份後備 —— 兩處各自定義「default 長什麼樣」遲早會漂開。
    return {"sessions": lab_manager.list_sessions(db, current_user.id),
            "max": lab_manager.MAX_SESSIONS_PER_USER}


@router.post("/sessions")
def create_my_session(
    payload: schemas.LabSessionCreate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    ZH: 新增一份存檔（只建紀錄；容器與 volume 等到啟動時才建）。

    @node job-scheduler/app/routers/lab.py::create_my_session
    """
    try:
        return lab_manager.create_session(db, current_user.id, payload.display_name)
    except ValueError as e:
        raise HTTPException(status_code=400, # ZH: `e` 本身已經是「ZH: … | EN: …」的形狀（見 lab_manager 的 ValueError），
        #     所以直接用，不要再包一層 —— 包了會變成 ZH 半邊裡還有一組 ZH/EN。
        detail=str(e))


@router.delete("/sessions/{session_name}")
def delete_my_session(
    session_name: str,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    ZH: 刪掉一份存檔（連同它的檔案）。**預設那一份不能刪**、執行中的不能刪。

    @node job-scheduler/app/routers/lab.py::delete_my_session
    """
    try:
        ok = lab_manager.delete_session(db, current_user.id, session_name)
    except ValueError as e:
        raise HTTPException(status_code=409, # ZH: `e` 本身已經是「ZH: … | EN: …」的形狀（見 lab_manager 的 ValueError），
        #     所以直接用，不要再包一層 —— 包了會變成 ZH 半邊裡還有一組 ZH/EN。
        detail=str(e))
    if not ok:
        raise HTTPException(status_code=404,
                            detail="ZH: 找不到這一份存檔 | EN: No such workspace")
    return {"status": "deleted", "session_name": session_name}
