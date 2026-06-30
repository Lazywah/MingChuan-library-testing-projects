"""
==============================================================================
Router: 外部 AI 分流路由 (External AI Routing) — v2.5
==============================================================================
ZH: 用途：自家 AI 助手成熟前，以合作廠商 (myai168) 暫時替代給非 admin 使用者。
    廠商無 API/SSO，僅能導流 + 帳號後台造冊，故：
      - 使用者端 GET /me：回傳廠商網址 + 該使用者被指派的廠商帳號名（導流用）。
      - 管理端 /admin/*：admin 維護「平台帳號 ↔ 廠商帳號」對應表 + 設定廠商網址。
    安全原則：只存廠商帳號名，絕不存廠商密碼。
EN: Purpose: Temporarily route non-admin users to a partner vendor (myai168)
    until the in-house AI matures. Vendor has no API/SSO — only redirect +
    back-office provisioning. User endpoint returns URL + assigned vendor
    username; admin endpoints manage the mapping table and the vendor URL.
    Security: store vendor username only, never the vendor password.
==============================================================================
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Any
import csv
import io

from .. import crud, schemas, models
from ..auth import get_current_user
from ..database import get_db
from ..services import myai_sync

router = APIRouter(tags=["外部 AI External-AI"])

EXTERNAL_AI_URL_KEY = "external_ai_url"


def require_admin(current_user: models.User = Depends(get_current_user)) -> models.User:
    """ZH: 確保呼叫者為 admin | EN: Ensure caller is admin"""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Forbidden: Admins only")
    return current_user


# ==============================================================================
# ZH: 使用者端 | EN: User-facing
# ==============================================================================

@router.get("/me", response_model=schemas.ExternalAiMe)
def get_my_external_ai(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> Any:
    """ZH: 取得自己的外部 AI 導流資訊（網址 + 指派帳號 + 狀態）
       EN: Get my external-AI redirect info (url + assigned account + status)"""
    url = crud.get_system_config(db, EXTERNAL_AI_URL_KEY, "")

    # v2.8 廠商 Token 餘額：以 email 對應 myai_accounts（不分大小寫）
    myai_points = myai_expiry = myai_status = None
    if current_user.email:
        m = (
            db.query(models.MyaiAccount)
            .filter(models.MyaiAccount.email.ilike(current_user.email))
            .first()
        )
        if m:
            myai_points, myai_expiry, myai_status = m.points, m.expiry, m.status

    acc = crud.get_external_account_by_user_id(db, current_user.id)
    if not acc:
        vendor, status = None, "not_provisioned"
    elif (acc.status or "active") != "active":
        vendor, status = acc.vendor_username, "disabled"
    else:
        vendor, status = acc.vendor_username, "active"

    return schemas.ExternalAiMe(
        url=url, vendor_username=vendor, status=status,
        myai_points=myai_points, myai_expiry=myai_expiry, myai_status=myai_status,
    )


# ==============================================================================
# ZH: 管理端 — 廠商網址設定 | EN: Admin — vendor URL setting
# ==============================================================================

@router.get("/admin/url", response_model=schemas.ExternalAiUrl)
def get_external_url(
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
) -> Any:
    return schemas.ExternalAiUrl(url=crud.get_system_config(db, EXTERNAL_AI_URL_KEY, ""))


@router.put("/admin/url", response_model=schemas.ExternalAiUrl)
def set_external_url(
    payload: schemas.ExternalAiUrl,
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
) -> Any:
    crud.set_system_config(
        db, EXTERNAL_AI_URL_KEY, payload.url.strip(),
        description="外部 AI 平台網址（空=未啟用，退回即將開放）",
    )
    return schemas.ExternalAiUrl(url=crud.get_system_config(db, EXTERNAL_AI_URL_KEY, ""))


# ==============================================================================
# ZH: 管理端 — 對應表 CRUD | EN: Admin — mapping CRUD
# ==============================================================================

@router.get("/admin/accounts", response_model=list[schemas.ExternalAiAccountResponse])
def list_accounts(
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
) -> Any:
    return crud.list_external_accounts(db)


@router.post("/admin/accounts", response_model=schemas.ExternalAiAccountResponse)
def create_account(
    payload: schemas.ExternalAiAccountCreate,
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
) -> Any:
    try:
        acc = crud.create_external_account(
            db, payload.platform_username.strip(), payload.vendor_username.strip(),
            payload.status or "active", payload.note,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return schemas.ExternalAiAccountResponse(
        id=acc.id, user_id=acc.user_id, platform_username=payload.platform_username.strip(),
        vendor_username=acc.vendor_username, status=acc.status, note=acc.note,
        updated_at=acc.updated_at,
    )


@router.put("/admin/accounts/{account_id}", response_model=schemas.ExternalAiAccountResponse)
def update_account(
    account_id: str,
    payload: schemas.ExternalAiAccountUpdate,
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
) -> Any:
    acc = crud.update_external_account(
        db, account_id,
        vendor_username=(payload.vendor_username.strip() if payload.vendor_username else None),
        status=payload.status, note=payload.note,
    )
    if not acc:
        raise HTTPException(status_code=404, detail="mapping not found")
    user = db.query(models.User).filter(models.User.id == acc.user_id).first()
    return schemas.ExternalAiAccountResponse(
        id=acc.id, user_id=acc.user_id,
        platform_username=(user.username if user else None),
        vendor_username=acc.vendor_username, status=acc.status, note=acc.note,
        updated_at=acc.updated_at,
    )


@router.delete("/admin/accounts/{account_id}")
def delete_account(
    account_id: str,
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
) -> Any:
    if not crud.delete_external_account(db, account_id):
        raise HTTPException(status_code=404, detail="mapping not found")
    return {"ok": True}


# ==============================================================================
# ZH: 管理端 — CSV 批次匯入造冊結果 | EN: Admin — CSV bulk import
# ==============================================================================

@router.post("/admin/import", response_model=schemas.ExternalAiImportResult)
def import_accounts_csv(
    payload: dict,
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
) -> Any:
    """ZH: 接收 CSV 文字 (欄位: platform_username,vendor_username)，逐行 upsert。
       EN: Accept CSV text (cols: platform_username,vendor_username), upsert per row."""
    text = (payload or {}).get("csv", "")
    result = schemas.ExternalAiImportResult()
    if not text or not text.strip():
        result.errors.append("empty CSV")
        return result
    reader = csv.reader(io.StringIO(text))
    for idx, row in enumerate(reader, start=1):
        if not row or all(not c.strip() for c in row):
            continue
        # 跳過表頭 | skip header
        if idx == 1 and row[0].strip().lower() in ("platform_username", "username", "平台帳號"):
            continue
        if len(row) < 2 or not row[0].strip() or not row[1].strip():
            result.errors.append(f"第 {idx} 行格式錯誤 (需 platform_username,vendor_username)")
            continue
        try:
            outcome = crud.upsert_external_account_by_username(db, row[0].strip(), row[1].strip())
            if outcome == "created":
                result.created += 1
            elif outcome == "updated":
                result.updated += 1
            else:
                result.skipped += 1
        except ValueError as e:
            result.errors.append(f"第 {idx} 行: {e}")
    return result


# ==============================================================================
# ZH: v2.8 MYAI 廠商平台 headless 同步（唯讀）| EN: v2.8 MYAI headless sync (read-only)
# ==============================================================================

@router.post("/admin/sync-myai")
async def sync_myai(
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
) -> Any:
    """ZH: 立即 headless 登入廠商 → 匯出使用者(含 Token 點數) → 同步進 myai_accounts。
       EN: Trigger headless login → export → upsert into myai_accounts."""
    try:
        return await myai_sync.sync(db)
    except myai_sync.MyaiSyncError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"同步失敗：{e}")


@router.get("/admin/myai-accounts")
def list_myai_accounts(
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
) -> Any:
    """ZH: 列出已同步的廠商帳號/Token（供 admin 顯示）| EN: list synced MYAI accounts."""
    rows = (
        db.query(models.MyaiAccount)
        .order_by(models.MyaiAccount.points.desc())
        .all()
    )
    last = max((r.synced_at for r in rows), default=None)
    return {
        "synced_at": last.isoformat() if last else None,
        "count": len(rows),
        "accounts": [
            {
                "vendor_sn": r.vendor_sn, "email": r.email, "name": r.name,
                "user_type": r.user_type, "points": r.points, "expiry": r.expiry,
                "status": r.status, "newsletter": r.newsletter, "note": r.note,
            }
            for r in rows
        ],
    }
