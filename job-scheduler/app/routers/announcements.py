"""
==============================================================================
Router: 公告路由群組 (Announcements Routes) — v2.2 新增
==============================================================================
ZH: 用途：管理首頁公告（admin 編輯、user 觀看）
EN: Manage homepage announcements (admin edits, users view)

ZH: 端點清單：
    GET    /api/v1/announcements             → 公告列表（user 用，僅 visible）
    GET    /api/v1/admin/announcements       → 全部公告（含隱藏，admin 用）
    POST   /api/v1/admin/announcements       → 新增公告
    PUT    /api/v1/admin/announcements/{id}  → 編輯
    DELETE /api/v1/admin/announcements/{id}  → 刪除

ZH: 認證：
    /announcements (GET)          → 公開，任何登入使用者可看
    /admin/announcements/*        → 需 admin 角色
==============================================================================
"""

import logging
import os
import pathlib
import re
import shutil
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from .. import crud, models, schemas
from ..auth import get_current_user
from ..database import get_db
from ..rate_limit import limiter
from .admin import require_admin

logger = logging.getLogger(__name__)

router = APIRouter(tags=["公告 Announcements"])

# ==============================================================================
# ZH: 附件（v3.9，擁有者裁定 2026-08-30）
# ==============================================================================
# ZH: 自成一個目錄，**不跟資料集共用**。資料集是按人算、吃學生那 2 GB 個人配額；
#     公告附件是管理員放的，算到學生頭上是錯的。
ANNOUNCEMENT_DIR = "/data/announcements"

# ZH: 🔴 副檔名白名單。**`.html` 與 `.svg` 絕對不可以加進來** ——
#     那兩種在瀏覽器裡會執行 script，而且是在**我們自己的網域下**執行。
#     那不是附件，那是一個 XSS 入口。
# ZH: 下面的下載端點另外掛了 Content-Disposition: attachment 與 nosniff，
#     兩道一起才擋得住（白名單擋「傳得進來」，標頭擋「開起來會執行」）。
ALLOWED_EXT = {".pdf", ".docx", ".xlsx", ".pptx", ".png", ".jpg", ".jpeg", ".zip"}


def _ann_dir(ann_id: int) -> str:
    return os.path.join(ANNOUNCEMENT_DIR, str(int(ann_id)))


def _total_bytes() -> int:
    """ZH: 目前所有公告附件佔的空間。總量上限是全站的，所以這裡掃整個目錄。"""
    root = pathlib.Path(ANNOUNCEMENT_DIR)
    if not root.exists():
        return 0
    return sum(p.stat().st_size for p in root.rglob("*") if p.is_file())


def _attach_files(db: Session, rows: list) -> list:
    """ZH: 把附件掛到公告物件上，讓回應帶得出來。

    ZH: 🔴 為什麼不用 ORM 的 relationship：**這個專案的 models.py 全站零個
        relationship**，全部都是明確查詢。為了一個欄位破例，等於在這個檔案裡
        引入一套別的地方都沒有的慣例 —— 接手的人會以為其他表也有關聯可用。

    ZH: 一次查完再分組，不要每則公告查一次（N+1）。
    ZH: ⚠ 掛的是**沒有對應到資料表欄位**的屬性。Pydantic 的 from_attributes
        讀得到它；沒有掛的話它讀不到，就會安靜地落回預設值 `[]` ——
        附件明明存在卻不出現，而且沒有錯誤。踩過一次。
    """
    if not rows:
        return rows
    by_ann: dict = {}
    files = (
        db.query(models.AnnouncementFile)
        .filter(models.AnnouncementFile.announcement_id.in_([a.id for a in rows]))
        .order_by(models.AnnouncementFile.uploaded_at.asc())
        .all()
    )
    for fr in files:
        by_ann.setdefault(fr.announcement_id, []).append(fr)
    for a in rows:
        a.files = by_ann.get(a.id, [])
    return rows


def _purge_files(ann_id: int) -> None:
    """ZH: 把一則公告的附件從磁碟上刪掉。

    ZH: 🔴 FK 的 CASCADE 只清資料庫的列，檔案不會跟著消失。
        沒有這一支就是製造孤兒 —— 而孤兒不會有任何錯誤訊息，
        只會在某天有人去看磁碟用量時才發現。
    ZH: 刪不掉不要讓整個請求失敗：公告本身已經刪成功了，
        為了殘留的檔案回 500 會讓管理員以為公告沒刪掉而重按一次。
    """
    try:
        shutil.rmtree(_ann_dir(ann_id), ignore_errors=True)
    except Exception:                                    # pragma: no cover
        logger.warning("ZH: 公告 %s 的附件目錄刪除失敗", ann_id)


@router.get("", response_model=list[schemas.AnnouncementResponse])
def list_announcements(
    limit: int = Query(20, ge=1, le=100, description="ZH: 最多回幾則 | EN: Max items"),
    db: Session = Depends(get_db),
    _: models.User = Depends(get_current_user),
) -> Any:
    """
    ZH: 公告列表（給 user UI 首頁用）
    EN: Announcement list (for user UI homepage)

    僅回 is_visible=1 的；置頂的排最前，其餘按 posted_at desc。

    @node job-scheduler/app/routers/announcements.py::list_announcements
    """
    pinned = (
        db.query(models.Announcement)
        .filter(models.Announcement.is_visible == 1, models.Announcement.is_pinned == 1)
        .order_by(models.Announcement.posted_at.desc())
        .all()
    )
    normal = (
        db.query(models.Announcement)
        .filter(models.Announcement.is_visible == 1, models.Announcement.is_pinned == 0)
        .order_by(models.Announcement.posted_at.desc())
        .limit(max(0, limit - len(pinned)))
        .all()
    )
    return _attach_files(db, pinned + normal)


# ==============================================================================
# Admin 子路由（掛在 /api/v1/admin/announcements）
# 因為 require_admin 在 admin.py 已定義，這裡複用
# ==============================================================================
admin_router = APIRouter(tags=["公告管理 Admin Announcements"])


@admin_router.get("", response_model=list[schemas.AnnouncementResponse])
def admin_list_announcements(
    include_hidden: bool = Query(True, description="ZH: 是否含隱藏 | EN: include hidden"),
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
) -> Any:
    """ZH: admin 看到的全部公告（含隱藏 / 草稿）

    @node job-scheduler/app/routers/announcements.py::admin_list_announcements
    """
    q = db.query(models.Announcement)
    if not include_hidden:
        q = q.filter(models.Announcement.is_visible == 1)
    return _attach_files(db, q.order_by(
        models.Announcement.is_pinned.desc(),
        models.Announcement.posted_at.desc(),
    ).all())


@admin_router.post("", response_model=schemas.AnnouncementResponse, status_code=201)
def admin_create_announcement(
    payload: schemas.AnnouncementCreate,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin),
) -> Any:
    """ZH: 新增公告

    @node job-scheduler/app/routers/announcements.py::admin_create_announcement
    """
    a = models.Announcement(
        title=payload.title,
        body=payload.body,
        posted_by=current_admin.id,
        is_pinned=payload.is_pinned,
        is_visible=payload.is_visible,
    )
    db.add(a); db.commit(); db.refresh(a)
    return a


@admin_router.put("/{ann_id}", response_model=schemas.AnnouncementResponse)
def admin_update_announcement(
    ann_id: int,
    payload: schemas.AnnouncementCreate,
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
) -> Any:
    """ZH: 編輯公告

    @node job-scheduler/app/routers/announcements.py::admin_update_announcement
    """
    a = db.query(models.Announcement).filter(models.Announcement.id == ann_id).first()
    if not a:
        raise HTTPException(status_code=404, detail="ZH: 找不到這則公告 | EN: Announcement not found")
    a.title = payload.title
    a.body = payload.body
    a.is_pinned = payload.is_pinned
    a.is_visible = payload.is_visible
    db.commit(); db.refresh(a)
    return a


@admin_router.delete("/{ann_id}", status_code=204)
def admin_delete_announcement(
    ann_id: int,
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
) -> None:
    """ZH: 刪除公告

    @node job-scheduler/app/routers/announcements.py::admin_delete_announcement
    """
    a = db.query(models.Announcement).filter(models.Announcement.id == ann_id).first()
    if not a:
        raise HTTPException(status_code=404, detail="ZH: 找不到這則公告 | EN: Announcement not found")
    db.delete(a); db.commit()
    # ZH: ⚠ 資料庫的列由 CASCADE 清掉，**磁碟上的檔案要自己刪**（見 _purge_files）。
    _purge_files(ann_id)


# ==============================================================================
# ZH: 附件端點
# ==============================================================================
@router.get("/{ann_id}/files/{file_id}")
def download_file(
    ann_id: int,
    file_id: int,
    db: Session = Depends(get_db),
    _: models.User = Depends(get_current_user),
) -> Any:
    """ZH: 下載公告附件 | EN: Download an announcement attachment

    ZH: 🔴 走 API 不走靜態路徑，理由有兩個：
        ① 附件要跟著公告的「公開」旗標 —— **草稿的附件不可以外流**。
           靜態路徑做不到這件事（nginx 不知道那則公告有沒有公開）。
        ② 靜態路徑猜得到。這裡用資料庫的 id 對應磁碟檔名，猜不到。

    ZH: ⚠ 權限與公告本身一致（要登入）。之後若把公告改成公開，
        這裡把 `get_current_user` 拿掉即可 —— is_visible 的檢查在下面，
        不會因此鬆掉。

    @node job-scheduler/app/routers/announcements.py::download_file
    """
    row = (
        db.query(models.AnnouncementFile)
        .filter(models.AnnouncementFile.id == file_id,
                models.AnnouncementFile.announcement_id == ann_id)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="ZH: 找不到這個附件 | EN: Attachment not found")

    ann = db.query(models.Announcement).filter(models.Announcement.id == ann_id).first()
    # ZH: 🔴 草稿（is_visible=0）的附件一律 404，不回 403 ——
    #     403 等於承認「這裡有東西但你不能看」，那本身就是資訊。
    if not ann or ann.is_visible != 1:
        raise HTTPException(status_code=404, detail="ZH: 找不到這個附件 | EN: Attachment not found")

    path = os.path.join(_ann_dir(ann_id), row.stored_name)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="ZH: 附件的檔案不見了 | EN: Attachment file is missing")

    # ZH: 🔴 一律當附件下載，**不要讓瀏覽器內嵌開啟**。
    #     nosniff 是第二道：少了它，瀏覽器會去猜內容型別，
    #     於是一個副檔名合法但內容是 HTML 的檔案仍然可能被當成網頁執行。
    return FileResponse(
        path,
        filename=row.filename,
        media_type="application/octet-stream",
        headers={"X-Content-Type-Options": "nosniff"},
    )


@admin_router.post("/{ann_id}/files", response_model=schemas.AnnouncementFileOut, status_code=201)
@limiter.limit("30/hour")
async def admin_upload_file(
    request: Request,
    ann_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
) -> Any:
    """ZH: 上傳公告附件 | EN: Upload an announcement attachment

    @node job-scheduler/app/routers/announcements.py::admin_upload_file
    """
    ann = db.query(models.Announcement).filter(models.Announcement.id == ann_id).first()
    if not ann:
        raise HTTPException(status_code=404, detail="ZH: 找不到這則公告 | EN: Announcement not found")
    if not file.filename:
        raise HTTPException(status_code=400, detail="ZH: 沒有收到檔名 | EN: No filename provided")

    # ZH: ⚠ 先用 pathlib.Path(...).name 砍掉目錄成分 —— 防路徑穿越。
    #     `../../etc/passwd` 這種檔名到這裡只會剩下 `passwd`。
    base = pathlib.Path(file.filename).name
    ext = pathlib.Path(base).suffix.lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(
            status_code=400,
            detail=f"ZH: 不允許的檔案類型「{ext}」，可用：{', '.join(sorted(ALLOWED_EXT))} | "
                   f"EN: File type '{ext}' not allowed. Permitted: {', '.join(sorted(ALLOWED_EXT))}",
        )

    max_mb = crud.get_setting(db, "announcement_file_max_mb")
    total_gb = crud.get_setting(db, "announcement_total_gb")

    os.makedirs(_ann_dir(ann_id), exist_ok=True)
    # ZH: 磁碟上的檔名只留安全字元 + 一段 uuid。uuid 是為了同名檔案不互相覆蓋 ——
    #     管理員連傳兩份 `公告.pdf` 時，第二份不該把第一份吃掉。
    stored = uuid.uuid4().hex + ext
    path = os.path.join(_ann_dir(ann_id), stored)

    # ZH: 🔴 邊寫邊算大小，**不要信 file.size**。分塊上傳時它是 None，
    #     而 Content-Length 是客戶端說了算的數字 —— 拿它當閘門等於沒有閘門。
    #     超過就當場停手並刪掉半個檔案。
    written = 0
    limit = max_mb * 1024 * 1024
    existing = _total_bytes()
    total_limit = total_gb * 1024 ** 3
    try:
        with open(path, "wb") as out:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                written += len(chunk)
                if written > limit:
                    raise HTTPException(
                        status_code=413,
                        detail=f"ZH: 檔案超過單檔上限 {max_mb} MB | "
                               f"EN: File exceeds the {max_mb} MB per-file limit")
                if existing + written > total_limit:
                    raise HTTPException(
                        status_code=413,
                        detail=f"ZH: 公告附件總量已達上限 {total_gb} GB | "
                               f"EN: Announcement attachments have reached the {total_gb} GB cap")
                out.write(chunk)
    except Exception:
        # ZH: 失敗就把半個檔案清掉。留著的話它會一直算進總量，
        #     而列表上看不到它 —— 「明明沒幾個附件卻說滿了」。
        try:
            os.remove(path)
        except OSError:
            pass
        raise

    row = models.AnnouncementFile(
        announcement_id=ann_id, filename=base[:200], stored_name=stored,
        size_bytes=written, content_type=file.content_type,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@admin_router.delete("/{ann_id}/files/{file_id}", status_code=204)
def admin_delete_file(
    ann_id: int,
    file_id: int,
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
) -> None:
    """ZH: 刪除單一附件 | EN: Delete one attachment

    @node job-scheduler/app/routers/announcements.py::admin_delete_file
    """
    row = (
        db.query(models.AnnouncementFile)
        .filter(models.AnnouncementFile.id == file_id,
                models.AnnouncementFile.announcement_id == ann_id)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="ZH: 找不到這個附件 | EN: Attachment not found")
    # ZH: ⚠ 先刪檔再刪列。反過來的話，刪檔失敗就再也找不到那個檔名了。
    try:
        os.remove(os.path.join(_ann_dir(ann_id), row.stored_name))
    except OSError:
        pass                      # ZH: 檔案已經不在也算刪成功——目的達成了
    db.delete(row)
    db.commit()
