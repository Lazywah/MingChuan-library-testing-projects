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
import re
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy.orm import Session

from .. import models
from ..config import settings

logger = logging.getLogger(__name__)

# ZH: admin 交易日誌路徑（全體、逐筆、含備註/模型；filter: date_start/date_end/keyword）
ADMIN_TX_PATH = "/mcu/ai/admin/transaction"

# ZH: 交易列解析 —— 頁面為 server-render 的 <b>欄位：</b>值 形式（不取 IP）
TX_ROW = re.compile(
    r"<b>時間：</b>\s*(?P<time>.*?)\s*"
    r"<b>點數：</b>\s*(?P<pts>-?\d+)\s*"
    r"<b>餘額：</b>\s*(?P<bal>\d+)\s*"
    r"<b>備註：</b>\s*(?P<note>.*?)\s*"
    r"<b>帳號：</b>\s*(?P<email>\S+?)\s*"
    r"<b>顯示名稱：</b>\s*(?P<name>.*?)\s*"
    r"<b>\s*序號：</b>\s*(?P<sn>\d+)",
    re.S,
)


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

    # ZH: 交易日誌同步（逐筆、含模型；失敗不影響帳號同步）
    # EN: also sync the per-event transaction log (best-effort)
    tx = {"fetched": 0, "created": 0}
    try:
        tx = await sync_transactions(db, days=settings.MYAI_TX_SYNC_DAYS)
    except Exception as e:  # noqa: BLE001
        logger.warning("MYAI tx-sync skipped: %s", e)

    return {
        "status": "ok",
        "total": len(records),
        "created": created,
        "updated": updated,
        "matched_created": match["matched_created"],
        "backfilled": match["backfilled"],
        "tx_fetched": tx.get("fetched", 0),
        "tx_created": tx.get("created", 0),
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


# ==============================================================================
# ZH: v2.8 交易日誌同步 —— 逐筆(全體、含模型)；不存 IP
# EN: v2.8 transaction-log sync — per event (all users, incl. model); no IP
# ==============================================================================
def _classify(note: str, pts: int) -> tuple[str, str | None]:
    """ZH: 由備註判斷事件類型與模型 | EN: classify event/model from note."""
    low = (note or "").lower()
    if "login" in low:
        return "login", None
    if note.startswith("Transfer"):
        return "transfer", None
    if pts < 0:
        return "ai_usage", note.strip() or None
    return "other", None


def parse_transactions(html: str) -> list[dict]:
    """ZH: 解析交易日誌 HTML → list[dict]（不含 IP）| EN: parse tx log HTML."""
    out: list[dict] = []
    for m in TX_ROW.finditer(html):
        t = (m.group("time") or "").strip()
        try:
            pts = int(m.group("pts"))
        except (TypeError, ValueError):
            pts = 0
        try:
            bal = int(m.group("bal"))
        except (TypeError, ValueError):
            bal = 0
        note = (m.group("note") or "").strip()
        email = (m.group("email") or "").strip()
        name = (m.group("name") or "").strip()
        sn = (m.group("sn") or "").strip()
        try:
            occ = datetime.strptime(t, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            occ = None
        ev, model = _classify(note, pts)
        out.append({
            "occurred_at": occ, "vendor_sn": sn, "email": email, "name": name,
            "points_delta": pts, "balance": bal, "note": note,
            "event_type": ev, "model": model,
            "dedup_key": f"{t}|{sn}|{pts}|{note}",   # ZH: 去重鍵（不含 IP）
        })
    return out


async def fetch_transactions_html(date_start: str, date_end: str) -> str:
    """ZH: headless 登入 → GET admin 交易日誌(日期範圍) → 回 HTML。唯讀。
       EN: headless-login then GET the admin transaction log for a date range."""
    if not settings.MYAI_ADMIN_EMAIL or not settings.MYAI_ADMIN_PASSWORD:
        raise MyaiSyncError("MYAI_ADMIN_EMAIL / MYAI_ADMIN_PASSWORD 未設定（請填入 .env）")
    base = settings.MYAI_BASE_URL.rstrip("/")
    login_page = settings.MYAI_LOGIN_PATH.rsplit("/", 1)[0] + "/login"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/149.0 Safari/537.36",
        "Referer": base + login_page, "Origin": base,
        "X-Requested-With": "XMLHttpRequest", "Accept": "text/html, */*",
    }
    async with httpx.AsyncClient(base_url=base, follow_redirects=True,
                                 timeout=httpx.Timeout(30.0), headers=headers) as client:
        try:
            await client.get(login_page)
            await client.post(settings.MYAI_LOGIN_PATH, data={
                "email": settings.MYAI_ADMIN_EMAIL, "password": settings.MYAI_ADMIN_PASSWORD})
        except httpx.HTTPError as e:
            raise MyaiSyncError(f"登入請求失敗：{e}")
        try:
            r = await client.get(ADMIN_TX_PATH, params={"date_start": date_start, "date_end": date_end})
        except httpx.HTTPError as e:
            raise MyaiSyncError(f"交易日誌請求失敗：{e}")
        if r.status_code != 200:
            raise MyaiSyncError(f"交易日誌回應 {r.status_code}（可能登入失敗或權限不足）")
        return r.text


async def sync_transactions(db: Session, days: int = 90) -> dict:
    """ZH: 抓近 N 天交易日誌 → 解析 → 去重 upsert（不存 IP）。回統計。
       EN: fetch last N days of the tx log, parse, dedup-insert (no IP)."""
    days = max(1, min(int(days or 90), 730))
    end = datetime.now()
    start = end - timedelta(days=days)
    html = await fetch_transactions_html(start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"))
    rows = parse_transactions(html)
    existing = {k for (k,) in db.query(models.MyaiTransaction.dedup_key).all()}
    now = datetime.now(timezone.utc)
    created = 0
    for r in rows:
        if r["dedup_key"] in existing:
            continue
        db.add(models.MyaiTransaction(synced_at=now, **r))
        existing.add(r["dedup_key"])
        created += 1
    db.commit()
    logger.info("MYAI tx-sync: fetched=%d created=%d (days=%d)", len(rows), created, days)
    return {"status": "ok", "fetched": len(rows), "created": created,
            "skipped": len(rows) - created, "days": days}
