"""
==============================================================================
Router: Notebook 路由群組 (Notebook Routes)
==============================================================================
ZH: 用途：管理使用者的 Notebook 草稿（每人一份持久化儲存）與 GPU 節點列表查詢
EN: Purpose: Manage per-user notebook drafts (one persistent draft per user)
    and query available GPU worker nodes for the frontend selector

ZH: 端點清單：
    GET  /api/v1/notebooks/mine      → 載入使用者 Notebook
    PUT  /api/v1/notebooks/mine      → 儲存 / 更新 Notebook（auto-save）
    GET  /api/v1/notebooks/nodes     → 列出在線 GPU Worker 節點

EN: Endpoint list:
    GET  /api/v1/notebooks/mine      → Load user's notebook
    PUT  /api/v1/notebooks/mine      → Save / update notebook (auto-save)
    GET  /api/v1/notebooks/nodes     → List online GPU worker nodes
==============================================================================
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime
import json
import logging

from .. import crud, schemas, models
from ..auth import get_current_user
from ..database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Notebook"])


# ==============================================================================
# ZH: GET /mine - 載入使用者 Notebook
# EN: GET /mine - Load user's notebook
# ==============================================================================
@router.get("/mine", response_model=schemas.NotebookResponse)
def get_my_notebook(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    ZH: 取得目前使用者的 Notebook（若尚未建立則回傳預設空白）
    EN: Get current user's notebook (returns default empty notebook if none exists)
    """
    notebook = crud.get_notebook(db, user_id=current_user.id)

    if not notebook:
        # ZH: 尚未建立，回傳含一個預設 code 格的空白 Notebook
        # EN: Not yet created — return blank notebook with one default code cell
        default_cell = {
            "id": "cell-1",
            "type": "code",
            "content": "# ZH: 在此撰寫你的訓練腳本\n# EN: Write your training script here\nimport torch\nprint(f\"PyTorch {torch.__version__}, CUDA available: {torch.cuda.is_available()}\")\n"
        }
        return {
            "cells": [default_cell],
            "environment": {
                "framework": "pytorch",
                "mode": "training",
                "preferred_node": "auto",
                "docker_image": None
            },
            "updated_at": None
        }

    # ZH: 解析 JSON 欄位 | EN: Parse JSON fields
    try:
        cells = json.loads(notebook.cells) if notebook.cells else []
    except json.JSONDecodeError:
        cells = []

    try:
        environment = json.loads(notebook.environment) if notebook.environment else {}
    except json.JSONDecodeError:
        environment = {}

    return {
        "cells":       cells,
        "environment": environment,
        "updated_at":  notebook.updated_at
    }


# ==============================================================================
# ZH: PUT /mine - 儲存 / 更新 Notebook（前端 auto-save 呼叫，debounce 2s）
# EN: PUT /mine - Save / update notebook (called by frontend auto-save, debounce 2s)
# ==============================================================================
@router.put("/mine", response_model=schemas.NotebookResponse)
def save_my_notebook(
    payload: schemas.NotebookSave,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    ZH: 儲存使用者 Notebook（upsert，前端每 2 秒靜止後自動呼叫）
    EN: Save user's notebook (upsert; called automatically after 2s idle by frontend)
    """
    cells_json = json.dumps(
        [cell.model_dump() for cell in payload.cells],
        ensure_ascii=False
    )
    env_json = json.dumps(payload.environment, ensure_ascii=False)

    notebook = crud.save_notebook(
        db,
        user_id=current_user.id,
        cells_json=cells_json,
        env_json=env_json
    )

    logger.debug(
        "Notebook saved for user %s (%d cells)",
        current_user.username, len(payload.cells)
    )

    return {
        "cells":       payload.cells,
        "environment": payload.environment,
        "updated_at":  notebook.updated_at
    }


# ==============================================================================
# ZH: GET /nodes - 列出在線 GPU Worker 節點（供前端 GPU 選擇器使用）
# EN: GET /nodes - List online GPU worker nodes (for frontend GPU selector)
# ==============================================================================
@router.get("/nodes", response_model=schemas.WorkerNodeListResponse)
def list_worker_nodes(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    ZH: 列出目前在線的 GPU Worker 節點（最後心跳在 90 秒內）
    EN: List currently online GPU worker nodes (last heartbeat within 90s)
    """
    nodes = crud.get_online_worker_nodes(db, timeout_seconds=90)

    node_list = []
    for node in nodes:
        try:
            gpus = json.loads(node.available_gpus) if node.available_gpus else []
        except json.JSONDecodeError:
            gpus = []

        node_list.append({
            "node_id":        node.node_id,
            "available_gpus": gpus,
            "gpu_utilization": node.gpu_utilization or 0.0,
            "last_seen":      node.last_seen,
            "is_online":      node.is_online,
        })

    return {"nodes": node_list}
