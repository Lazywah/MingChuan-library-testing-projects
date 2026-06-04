"""
==============================================================================
Router: 模型清單路由 (Public Models Router)
==============================================================================
ZH: 用途：提供「使用者端可見」的模型清單，依工具 (tool_type) 動態回傳。
    各 AI 工具 (chat / presentation / ...) 的模型下拉改由前端動態抓取此端點，
    來源為 admin 的 Model 資料表 (公開且標記適用該工具者)。
EN: Purpose: Serve the user-facing model list, filtered dynamically by tool_type.
    Each AI tool's model dropdown fetches this endpoint (source: admin Model table,
    public models tagged as applicable to that tool).
==============================================================================
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import crud, schemas, models
from ..auth import get_current_user
from ..database import get_db

router = APIRouter(tags=["模型清單 Models"])


@router.get("", response_model=list[schemas.PublicModel])
def list_models(
    tool_type: str = "chat",
    db: Session = Depends(get_db),
    _: models.User = Depends(get_current_user),
):
    """ZH: 列出某工具可用的公開模型 | EN: List public models available for a tool.

    value = api_model_id or name（送給 /chat/completions 的 model_id）
    label = name（顯示用）
    """
    mdls = crud.list_public_models(db, tool_type)
    return [
        schemas.PublicModel(
            value=(m.api_model_id or m.name),
            label=m.name,
            model_type=m.model_type,
            api_provider=m.api_provider,
        )
        for m in mdls
    ]
