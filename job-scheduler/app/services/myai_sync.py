"""
==============================================================================
Service: MYAI 廠商平台 headless 同步 (v2.8) — 唯讀
==============================================================================
ZH: 用途：以管理者帳密 headless 登入廠商 (myai168) 管理後台 → 匯出使用者清單
    (.xlsx，含「點數」= Token 餘額) → 解析 → upsert 進 myai_accounts 供平台顯示。

    流程（已實測廠商端為標準表單登入、無驗證碼、無 CSRF）：
      1. GET  /mcu/ai/user/login            （取得初始 session cookie，若有）
      2. POST /mcu/ai/user/login_info        （form: email + password）→ 設 session
      3. GET  /mcu/gt_sdk/admin_168/user/export_user_list  → .xlsx
      4. 解析 9 欄 → 以 email 對應本平台使用者

    安全：帳密只從 .env 讀 (MYAI_ADMIN_EMAIL / MYAI_ADMIN_PASSWORD)，不存明文於碼。
          全程唯讀 — 只 login + export GET，絕不呼叫 transfer/register/edit/delete。
EN: Headless-login to the vendor admin, export the user list (.xlsx incl. token
    points), parse and upsert into myai_accounts for display. Read-only.
==============================================================================
"""

from __future__ import annotations

import io
import logging
from datetime import datetime, timezone

import httpx
from sqlalchemy.orm import Session

from .. import models
from ..config import settings

logger = logging.getLogger(__name__)


class MyaiSyncError(Exception):
    """ZH: 同步流程的可預期錯誤（帳密未設、登入失敗、格式不符）| expected sync errors"""


# ZH: 廠商匯出欄位 → 我們欄位 | vendor export header → our column
COLUMN_MAP = {
    "編號": "vendor_sn",
    "類型": "user_type",
    "名稱": "name",
    "電子郵件": "email",
    "點數": "points",
    "有效期間": "expiry",
    "狀態": "status",
    "電子報": "newsletter",
    "備註": "note",
}


async def fetch_export_bytes() -> bytes:
    """ZH: headless 登入 → 取得 export_user_list 的 .xlsx bytes。失敗拋 MyaiSyncError。
       EN: headless-login then download export_user_list (.xlsx). Raises on failure."""
    if not settings.MYAI_ADMIN_EMAIL or not settings.MYAI_ADMIN_PASSWORD:
        raise MyaiSyncError("MYAI_ADMIN_EMAIL / MYAI_ADMIN_PASSWORD 未設定（請填入 .env）")

    base = settings.MYAI_BASE_URL.rstrip("/")
    login_page = settings.MYAI_LOGIN_PATH.rsplit("/", 1)[0] + "/login"  # /mcu/ai/user/login

    # ZH: 廠商有防跨站(CSP form-action 'self')→ 登入 POST 必須帶正確 Referer/Origin，
    #     否則回 200「登入結果」頁卻不發 session cookie。實測加上這組標頭才會成功。
    # EN: Vendor enforces same-origin form submits; login POST needs matching
    #     Referer/Origin or no session cookie is issued. These headers are required.
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/149.0 Safari/537.36",
        "Referer": base + login_page,
        "Origin": base,
        "X-Requested-With": "XMLHttpRequest",
        "Accept": "application/json, text/plain, */*",
    }
    async with httpx.AsyncClient(
        base_url=base, follow_redirects=True, timeout=httpx.Timeout(30.0), headers=headers,
    ) as client:
        # (1) 先 GET 登入頁，讓伺服器發初始 session cookie（無則略過）
        try:
            await client.get(login_page)
        except httpx.HTTPError:
            pass

        # (2) POST 表單登入（email + password，x-www-form-urlencoded）
        try:
            await client.post(
                settings.MYAI_LOGIN_PATH,
                data={"email": settings.MYAI_ADMIN_EMAIL, "password": settings.MYAI_ADMIN_PASSWORD},
            )
        except httpx.HTTPError as e:
            raise MyaiSyncError(f"登入請求失敗：{e}")

        # (3) 取匯出檔；用「是否為 xlsx(ZIP 魔術數字 PK)」判定登入成功與否
        try:
            r = await client.get(settings.MYAI_EXPORT_PATH)
        except httpx.HTTPError as e:
            raise MyaiSyncError(f"匯出請求失敗：{e}")

        if r.status_code != 200:
            raise MyaiSyncError(f"匯出回應 {r.status_code}（可能登入失敗或權限不足）")
        body = r.content
        if body[:2] != b"PK":  # 非 xlsx → 多半被導回登入頁(HTML)
            raise MyaiSyncError("匯出內容非 xlsx（多半是帳密錯誤被導回登入頁，請確認 .env）")
        return body


def parse_xlsx(body: bytes) -> list[dict]:
    """ZH: 解析匯出 .xlsx → list[dict]（已對應欄位、points 轉 int）。
       EN: parse the exported .xlsx into mapped dict rows."""
    from openpyxl import load_workbook  # ZH: 延遲匯入 | lazy import

    wb = load_workbook(io.BytesIO(body), read_only=True, data_only=True)
    try:
        ws = wb.active
        it = ws.iter_rows(values_only=True)
        headers = [str(h).strip() if h is not None else "" for h in next(it)]
        out: list[dict] = []
        for raw in it:
            if raw is None or all(c is None for c in raw):
                continue
            rec: dict = {}
            for h, v in zip(headers, raw):
                key = COLUMN_MAP.get(h)
                if key:
                    rec[key] = v
            if not rec.get("vendor_sn"):
                continue
            # points → int
            try:
                rec["points"] = int(float(rec.get("points") or 0))
            except (ValueError, TypeError):
                rec["points"] = 0
            # 其餘轉字串去空白
            for k in ("vendor_sn", "email", "name", "user_type", "expiry", "status", "newsletter", "note"):
                if rec.get(k) is not None:
                    rec[k] = str(rec[k]).strip()
            out.append(rec)
        return out
    finally:
        wb.close()


async def sync(db: Session) -> dict:
    """ZH: 完整同步：登入 → 匯出 → 解析 → upsert 進 myai_accounts。
       EN: full sync: login → export → parse → upsert into myai_accounts."""
    body = await fetch_export_bytes()
    records = parse_xlsx(body)
    created = updated = 0
    now = datetime.now(timezone.utc)
    for rec in records:
        sn = rec["vendor_sn"]
        row = db.query(models.MyaiAccount).filter(models.MyaiAccount.vendor_sn == sn).first()
        if row:
            for k, v in rec.items():
                setattr(row, k, v)
            row.synced_at = now
            updated += 1
        else:
            db.add(models.MyaiAccount(synced_at=now, **rec))
            created += 1
    db.commit()
    logger.info("MYAI sync: total=%d created=%d updated=%d", len(records), created, updated)

    # ZH: 同步後自動以 email 配對綁定 | EN: auto-bind by email after sync
    match = auto_match(db)
    return {
        "status": "ok",
        "total": len(records),
        "created": created,
        "updated": updated,
        "matched_created": match["matched_created"],
        "backfilled": match["backfilled"],
        "synced_at": now.isoformat(),
    }


def auto_match(db: Session) -> dict:
    """ZH: 以 email 自動配對「myai 帳號 ↔ 平台使用者」，建立/回填 external_ai_accounts 綁定。
       規則：myai.email == user.email(不分大小寫) 且該使用者尚未綁定 → 自動建綁定
       (vendor_username=email, myai_vendor_sn=vendor_sn)；已綁且 email 相符但缺 sn → 回填 sn。
       只寫本平台 DB；絕不碰廠商。回傳 {matched_created, backfilled}。
       EN: Auto-bind myai accounts to platform users by email. Writes our DB only."""
    created = backfilled = 0
    myai_rows = (
        db.query(models.MyaiAccount)
        .filter(models.MyaiAccount.email.isnot(None))
        .all()
    )
    for m in myai_rows:
        email = (m.email or "").strip()
        if not email:
            continue
        user = db.query(models.User).filter(models.User.email.ilike(email)).first()
        if not user:
            continue  # ZH: 廠商端帳號在平台無對應使用者(如純管理員) | no platform user
        acc = (
            db.query(models.ExternalAiAccount)
            .filter(models.ExternalAiAccount.user_id == user.id)
            .first()
        )
        if not acc:
            db.add(models.ExternalAiAccount(
                user_id=user.id, vendor_username=email,
                myai_vendor_sn=m.vendor_sn, status="active", note="auto-matched",
            ))
            created += 1
        elif not acc.myai_vendor_sn and (acc.vendor_username or "").strip().lower() == email.lower():
            acc.myai_vendor_sn = m.vendor_sn  # ZH: 既有綁定回填穩定鍵 | backfill stable key
            backfilled += 1
    db.commit()
    logger.info("MYAI auto-match: created=%d backfilled=%d", created, backfilled)
    return {"matched_created": created, "backfilled": backfilled}
