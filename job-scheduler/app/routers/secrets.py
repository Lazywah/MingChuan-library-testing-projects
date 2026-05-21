"""
==============================================================================
Router: Secrets Module（v2.0 — 使用者 API key 管理）
==============================================================================
ZH: 用途：使用者管理自己的 secrets（HF_TOKEN / KAGGLE_KEY / WANDB_API_KEY 等）
    - 加密儲存（AES-256-GCM via secrets_service）
    - API 回傳一律 masked，**永不**回傳 plaintext
    - 提交 GPU Job / 啟動 code-server 時自動注入容器 env

EN: Purpose: User-facing endpoints for managing personal secrets
    - Encrypted storage (AES-256-GCM via secrets_service)
    - API always returns masked, NEVER plaintext
    - Auto-injected into containers at job submit / code-server start
==============================================================================
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import models
from ..auth import get_current_user
from ..database import get_db
from ..services import secrets_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Secrets 管理 Secrets Management"])


# ==============================================================================
# ZH: Request schemas
# ==============================================================================

class SecretPayload(BaseModel):
    value: str = Field(..., min_length=1, max_length=4096,
                       description="Secret 明文值（AES-256-GCM 加密後儲存）")


# ==============================================================================
# ZH: GET /secrets/ - 列出自己的 secrets（masked）
# ==============================================================================
@router.get("/")
def list_my_secrets(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    ZH: 列出自己的 secrets，value 永遠 masked
    EN: List own secrets; value is always masked
    """
    return secrets_service.list_secrets_masked(db, current_user.id)


# ==============================================================================
# ZH: PUT /secrets/{name} - 新增或更新（upsert）
# ==============================================================================
@router.put("/{name}")
def upsert_secret(
    name: str,
    payload: SecretPayload,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    ZH: 新增或更新 secret
    EN: Insert or update a secret

    name 必須為英數 + 底線（環境變數命名規則）
    """
    try:
        secrets_service.set_secret(db, current_user.id, name, payload.value)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"status": "ok", "name": name}


# ==============================================================================
# ZH: DELETE /secrets/{name} - 刪除某個 secret
# ==============================================================================
@router.delete("/{name}")
def delete_secret(
    name: str,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """ZH: 刪除自己的 secret | EN: Delete own secret"""
    deleted = secrets_service.delete_secret(db, current_user.id, name)
    if not deleted:
        raise HTTPException(status_code=404, detail="Secret not found")
    return {"status": "deleted", "name": name}
