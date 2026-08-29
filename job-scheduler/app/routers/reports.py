"""
==============================================================================
Router: 問題回報 (Issue Reports) — v3.4 新增
==============================================================================
ZH: 用途：使用者送出問題 → 管理端可見、可回應 → 使用者看得到回應
EN: User submits an issue → visible in admin UI → admin replies → user sees it

ZH: 端點清單：
    POST   /api/v1/reports                → 送出回報（登入即可，限流）
    GET    /api/v1/reports/mine           → 自己的歷史回報 + 管理者回應
    GET    /api/v1/admin/reports          → 全部回報（admin，可依 status 篩）
    PUT    /api/v1/admin/reports/{id}     → 改狀態 / 寫回應

ZH: 這一版的範圍（刻意的）：
    - **單則回應**：管理者寫一段回覆，使用者看得到，不能再回。
      來回對話串要多一張表 + 未讀狀態 + 通知，範圍差很多。
    - **不寄信、不通知**：回報只在管理介面可見。使用者自己回頁面看回應。

⚠ ZH: **不存任何使用者沒看到的欄位——包括 IP。**
    report.html 把診斷資訊整段攤開，並寫著「要別人交出診斷資訊，就不能讓他
    不知道交了什麼」。後端偷偷補欄位會讓那句話變成假的。見 models.IssueReport。
==============================================================================
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import models, schemas
from ..auth import get_current_user
from ..database import get_db
from ..rate_limit import limiter
from .admin import require_admin

logger = logging.getLogger(__name__)

router = APIRouter(tags=["問題回報 Issue Reports"])

# ZH: 診斷 JSON 的大小上限。前端那份約 400 bytes；給 20 倍餘裕，
#     但不是無上限——這是使用者可寫入的欄位。
MAX_DIAGNOSTICS_BYTES = 8000


@router.post("", response_model=schemas.IssueReportResponse, status_code=201)
@limiter.limit("5/hour")   # ZH: 防灌爆。回報是低頻動作，5/hour 對真實使用者綽綽有餘。
async def create_report(
    request: Request,
    payload: schemas.IssueReportCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> Any:
    """ZH: 送出問題回報

    ZH: username_at_report 是**快照**：帳號日後被刪，user_id 會 SET NULL，
        但管理者仍需要知道這筆是誰報的（問題可能還在）。

    @node job-scheduler/app/routers/reports.py::create_report
    """
    diag = json.dumps(payload.diagnostics, ensure_ascii=False)
    if len(diag.encode("utf-8")) > MAX_DIAGNOSTICS_BYTES:
        raise HTTPException(status_code=413, detail="診斷資訊過大")

    r = models.IssueReport(
        user_id=current_user.id,
        username_at_report=current_user.username,
        # ZH: 主旨與類別已經在 schema 過濾過（空白→None、未知代碼→None）。
        #     這裡不再補預設值 —— 補了等於替使用者宣稱他選了某個類別。
        subject=payload.subject,
        category=payload.category,
        body=payload.body,
        diagnostics=diag,
        status="open",
    )
    db.add(r); db.commit(); db.refresh(r)
    logger.info(f"Issue report #{r.id} submitted by {current_user.username}")
    return r


# ZH: ⚠ /mine 必須定義在任何 /{id} 之前，否則會被當成 id 吃掉。
#     這個 router 目前沒有 GET /{id}，但下一個人加的時候就會踩到，
#     所以位置先擺對（同一個坑在 jobs 的 /pool-availability 上踩過）。
@router.get("/mine", response_model=list[schemas.IssueReportResponse])
def list_my_reports(
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> Any:
    """ZH: 自己的歷史回報（含管理者回應），最新的在前

    @node job-scheduler/app/routers/reports.py::list_my_reports
    """
    return (
        db.query(models.IssueReport)
        .filter(models.IssueReport.user_id == current_user.id)
        .order_by(models.IssueReport.created_at.desc())
        .limit(limit)
        .all()
    )


# ==============================================================================
# Admin 子路由（掛在 /api/v1/admin/reports）
# ==============================================================================
admin_router = APIRouter(tags=["問題回報管理 Admin Issue Reports"])


@admin_router.get("", response_model=list[schemas.IssueReportResponse])
def admin_list_reports(
    status: Optional[str] = Query(None, description="ZH: open / in_progress / resolved；不給＝全部"),
    category: Optional[str] = Query(None, description="ZH: quota/account/train/lab/other；不給＝全部"),
    limit: int = Query(200, ge=1, le=500),
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
) -> Any:
    """ZH: 全部回報。未處理的排最前，其餘按時間新到舊。

    ZH: 排序刻意不只用時間 —— 管理者打開這一頁是要找**待辦**，
        而待辦被埋在一堆已解決的裡面等於沒有列表。

    @node job-scheduler/app/routers/reports.py::admin_list_reports
    """
    if status is not None and status not in schemas.ISSUE_STATUSES:
        raise HTTPException(status_code=400, detail=f"未知的 status：{status}")
    # ZH: 未知的類別**明講**，不要安靜地回全部 —— 靜默忽略的話，
    #     前後端的代碼一旦漂開，管理者會以為「這個類別真的沒有回報」。
    if category is not None and category not in schemas.IssueReportCreate.CATEGORIES:
        raise HTTPException(status_code=400, detail=f"未知的 category：{category}")

    q = db.query(models.IssueReport)
    if status:
        q = q.filter(models.IssueReport.status == status)
    if category:
        q = q.filter(models.IssueReport.category == category)
    rows = q.order_by(models.IssueReport.created_at.desc()).limit(limit).all()

    order = {"open": 0, "in_progress": 1, "resolved": 2}
    rows.sort(key=lambda r: order.get(r.status, 9))
    return rows


@admin_router.get("/summary")
def admin_reports_summary(
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
) -> Any:
    """ZH: 各狀態的計數（給側邊分頁的未處理徽章用，不必抓整份列表）

    @node job-scheduler/app/routers/reports.py::admin_reports_summary
    """
    counts = {s: 0 for s in schemas.ISSUE_STATUSES}
    for st, n in (db.query(models.IssueReport.status,
                           func.count(models.IssueReport.id))
                  .group_by(models.IssueReport.status).all()):
        counts[st] = n
    return {"counts": counts, "open": counts.get("open", 0)}


@admin_router.put("/{report_id}", response_model=schemas.IssueReportResponse)
def admin_update_report(
    report_id: int,
    payload: schemas.AdminIssueReportUpdate,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin),
) -> Any:
    """ZH: 改狀態 / 寫回應（兩者皆可選，可只改其一）

    @node job-scheduler/app/routers/reports.py::admin_update_report
    """
    r = db.query(models.IssueReport).filter(models.IssueReport.id == report_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="ZH: 找不到這則回報 | EN: Report not found")

    if payload.status is not None:
        r.status = payload.status
    if payload.admin_reply is not None:
        # ZH: 空字串＝清掉回應（打錯字想收回）。這時 replied_by/at 也要一起清，
        #     否則使用者端會看到「已回覆但沒有內容」。
        text = payload.admin_reply.strip()
        r.admin_reply = text or None
        r.replied_by = current_admin.id if text else None
        r.replied_at = datetime.now(timezone.utc) if text else None

    db.commit(); db.refresh(r)
    return r
