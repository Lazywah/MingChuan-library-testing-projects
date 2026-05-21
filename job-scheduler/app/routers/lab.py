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
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, Header, Request
from sqlalchemy.orm import Session

from .. import crud, models
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
    base_image: Optional[str] = None,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    ZH: 啟動使用者的 code-server 容器，回傳 URL 與 one-time password
    EN: Start user's code-server container, returns URL and one-time password
    """
    try:
        result = lab_manager.start_session(db, current_user.id, base_image=base_image)
    except PermissionError as e:
        raise HTTPException(status_code=429, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))

    return result


# ==============================================================================
# ZH: POST /lab/stop - 主動停止 code-server
# ==============================================================================
@router.post("/stop")
def stop_lab(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """ZH: 主動關閉自己的 session（volume 保留）| EN: Stop own session"""
    stopped = lab_manager.stop_session(db, current_user.id, reason="user_requested")
    return {"status": "stopped" if stopped else "no_active_session"}


# ==============================================================================
# ZH: GET /lab/status - 查詢狀態 + 配額 + 注入 secrets
# ==============================================================================
@router.get("/status")
def lab_status(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    ZH: 回傳完整 session 狀態（給設定頁與 VS Code extension 顯示用）
    EN: Return full session status (for settings page & VS Code extension)
    """
    info = lab_manager.get_status(db, current_user.id)
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
    """ZH: 更新使用者 session 的 last_activity 防 idle timeout"""
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
    ZH: nginx 驗證使用者是否可訪問 /code/{user_id}/
    EN: nginx validates user can access /code/{user_id}/

    驗證 / Verification:
        1. JWT 必須有效（get_current_user 自動處理）
        2. URI 內的 {user_id} 必須等於 current_user.id
        3. 使用者必須有 running session
    """
    # 從 nginx 傳入的 X-Original-URI 取出 user_id
    if not x_original_uri or not x_original_uri.startswith("/code/"):
        raise HTTPException(status_code=403, detail="Invalid path")

    parts = x_original_uri.lstrip("/").split("/")
    if len(parts) < 2 or parts[0] != "code":
        raise HTTPException(status_code=403, detail="Invalid path structure")

    requested_user_id = parts[1]
    if requested_user_id != current_user.id:
        raise HTTPException(
            status_code=403,
            detail="JWT does not authorize access to this user's lab"
        )

    if not lab_manager.is_user_session_alive(db, current_user.id):
        raise HTTPException(status_code=404, detail="No active session")

    # nginx 預期 200 OK + 自訂 header（auth_request_set $auth_user $upstream_http_x_lab_user）
    from fastapi.responses import Response
    response = Response(status_code=200)
    response.headers["X-Lab-User"] = current_user.id
    return response
