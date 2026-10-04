"""
Router: 管理端 AI（/api/v1/admin/ai）
====================================

ZH: v4.37（擁有者 2026-10-04）。只有管理員能用；只能查、不能改（工具全部唯讀）；
    只用本機模型（見 services/admin_ai.py）。每一次提問都進稽核 —— 它讀得到所有人的資料，
    「誰、什麼時候、查了誰」要留得住。

@node job-scheduler/app/routers/admin_ai.py
"""
import json
import time
from typing import Dict

from fastapi import APIRouter, Body, Depends, HTTPException, status
from sqlalchemy.orm import Session

from .. import models
from ..auth import require_admin
from ..database import get_db
from ..services import admin_ai

router = APIRouter(tags=["管理端 AI Admin AI"])

# ZH: 依管理員計（不依 IP —— Docker 後面所有人 IP 一樣）。本機模型一次要幾秒，
#     這只是防止連按把 GPU 佔住，不是計費。
_WINDOW_SECONDS = 600
_MAX_PER_WINDOW = 40
_hits: Dict[str, list] = {}


def _rate_ok(admin_id: str) -> bool:
    """@node job-scheduler/app/routers/admin_ai.py::_rate_ok"""
    now = time.monotonic()
    hits = [t for t in _hits.get(admin_id, []) if now - t < _WINDOW_SECONDS]
    ok = len(hits) < _MAX_PER_WINDOW
    if ok:
        hits.append(now)
    _hits[admin_id] = hits
    return ok


@router.post("/ask", summary="管理端 AI：用一句話查平台狀況（唯讀）")
def ask_admin_ai(
    payload: dict = Body(..., description='{"question": "…"}'),
    db: Session = Depends(get_db),
    admin: models.User = Depends(require_admin),
):
    """@node job-scheduler/app/routers/admin_ai.py::ask_admin_ai"""
    question = str((payload or {}).get("question") or "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="ZH: 請輸入問題 | EN: Please enter a question")
    if not _rate_ok(admin.id):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                            detail="ZH: 問太快了，休息幾分鐘再問 | EN: Too many questions - wait a few minutes")
    try:
        result = admin_ai.ask(db, question)
    except admin_ai.AdminAiError as e:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e))
    # ZH: 稽核：問了什麼、用了哪個查詢。不存回答本身（那是摘要，原始資料隨時可以再查）。
    db.add(models.AdminAction(
        admin_id=admin.id, admin_username=admin.username, target_user=None, action="ai_query",
        payload=json.dumps({"question": question[:500], "tool": result.get("tool"),
                            "args": result.get("args"), "routed_by": result.get("routed_by"),
                            "model": result.get("model"), "elapsed": result.get("elapsed")},
                           ensure_ascii=False)))
    db.commit()
    return result
