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
import json
import logging
import os
import re
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy.orm import Session

from .. import models
from ..config import settings

logger = logging.getLogger(__name__)

# ZH: admin 交易日誌路徑（全體、逐筆、含備註/模型；filter: date_start/date_end/keyword）
ADMIN_TX_PATH = "/mcu/ai/admin/transaction"

# ZH: v2.8 交易列解析改用 lxml —— 廠商已把交易頁從 <b>欄位：</b>值 改版成 CSS grid
#     （kbx-row / kbx-cell / kbx-dt / kbx-time / kbx-muted…）。實作見 parse_transactions。
#     欄位（桌面 kbx-dt 依序）：時間 / 點數 / 餘額 / 備註 / 帳號(email + 名稱・sn:序號) / IP。
#     一律不取、不存 IP（隱私）。


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


# ── v2.8 Session 快取：登入一次、cookie 重用，只有被導回登入頁(失效)才重登。──
# ZH: 消除「每次同步都登入」→ 更快，且不再把「Login was success.」洗版進廠商交易紀錄。
#     cookie 另存到 /data（與 DB 同區、volume 保存）→ 連 scheduler 重啟都免重登。全程唯讀。
# EN: Cache the vendor session cookie and reuse it across syncs; only re-login when the
#     response looks like the login page. Persisted next to the DB so it survives restarts.

# ZH: cookie 持久化檔（放 DB 同目錄，通常是 volume 掛載的 /data）
_COOKIE_FILE = os.path.join(os.path.dirname(settings.DATABASE_PATH) or ".", "myai_session.json")


def _save_cookies(cookies) -> None:
    """ZH: 把 vendor session cookie 存成 JSON（best-effort，失敗不影響同步）。"""
    try:
        items = [{"name": c.name, "value": c.value, "domain": c.domain, "path": c.path}
                 for c in cookies.jar]
        if not items:
            return
        with open(_COOKIE_FILE, "w", encoding="utf-8") as f:
            json.dump(items, f)
    except Exception as e:  # noqa: BLE001
        logger.debug("MYAI cookie 儲存失敗（略過）：%s", e)


def _load_cookies():
    """ZH: 啟動時載入上次的 cookie；沒有或壞掉就回 None（會自動重登）。"""
    try:
        if not os.path.exists(_COOKIE_FILE):
            return None
        with open(_COOKIE_FILE, "r", encoding="utf-8") as f:
            items = json.load(f)
        jar = httpx.Cookies()
        for it in items:
            jar.set(it["name"], it["value"], domain=it.get("domain") or "", path=it.get("path") or "/")
        return jar if len(jar.jar) else None
    except Exception as e:  # noqa: BLE001
        logger.debug("MYAI cookie 載入失敗（略過，將重登）：%s", e)
        return None


_MYAI_COOKIES = _load_cookies()  # type: httpx.Cookies | None  # 啟動即載入持久化 cookie


def _login_ctx():
    """ZH: 回 (base, login_page, headers)。廠商防跨站 → 登入 POST 必須帶對的 Referer/Origin。"""
    base = settings.MYAI_BASE_URL.rstrip("/")
    login_page = settings.MYAI_LOGIN_PATH.rsplit("/", 1)[0] + "/login"  # /mcu/ai/user/login
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/149.0 Safari/537.36",
        "Referer": base + login_page,
        "Origin": base,
        "X-Requested-With": "XMLHttpRequest",
        "Accept": "application/json, text/plain, */*",
    }
    return base, login_page, headers


async def _session_request(do_fetch, is_valid):
    """ZH: 帶快取 cookie 送出請求；若被導回登入頁(is_valid=False) 才登入一次再抓。
           do_fetch(client)->Response、is_valid(Response)->bool。回最終 Response。
       EN: issue a request with cached cookies; re-login once only if invalid."""
    global _MYAI_COOKIES
    if not settings.MYAI_ADMIN_EMAIL or not settings.MYAI_ADMIN_PASSWORD:
        raise MyaiSyncError("MYAI_ADMIN_EMAIL / MYAI_ADMIN_PASSWORD 未設定（請填入 .env）")
    base, login_page, headers = _login_ctx()
    async with httpx.AsyncClient(
        base_url=base, follow_redirects=True, timeout=httpx.Timeout(30.0),
        headers=headers, cookies=_MYAI_COOKIES,
    ) as client:
        # (1) 先用快取 cookie 直接抓（多數同步不需登入）
        if _MYAI_COOKIES is not None:
            try:
                resp = await do_fetch(client)
                if is_valid(resp):
                    _MYAI_COOKIES = client.cookies
                    _save_cookies(client.cookies)
                    return resp
            except httpx.HTTPError:
                pass  # 落到重新登入
        # (2) 沒 cookie 或已失效 → 登入一次再抓
        try:
            await client.get(login_page)  # 讓伺服器發初始 cookie（無則略過）
            await client.post(
                settings.MYAI_LOGIN_PATH,
                data={"email": settings.MYAI_ADMIN_EMAIL, "password": settings.MYAI_ADMIN_PASSWORD},
            )
        except httpx.HTTPError as e:
            raise MyaiSyncError(f"登入請求失敗：{e}")
        try:
            resp = await do_fetch(client)
        except httpx.HTTPError as e:
            raise MyaiSyncError(f"資料請求失敗：{e}")
        _MYAI_COOKIES = client.cookies
        _save_cookies(client.cookies)
        return resp


async def fetch_export_bytes() -> bytes:
    """ZH: 取得 export_user_list 的 .xlsx bytes（session 快取，失效才登入）。失敗拋 MyaiSyncError。
       EN: download export_user_list (.xlsx) reusing the cached session. Raises on failure."""
    async def _do(client):
        return await client.get(settings.MYAI_EXPORT_PATH)

    def _valid(r):  # 是 xlsx(ZIP 魔術數字 PK) = 登入有效
        return r.status_code == 200 and r.content[:2] == b"PK"

    r = await _session_request(_do, _valid)
    if r.status_code != 200:
        raise MyaiSyncError(f"匯出回應 {r.status_code}（可能登入失敗或權限不足）")
    if r.content[:2] != b"PK":  # 非 xlsx → 多半被導回登入頁(HTML)
        raise MyaiSyncError("匯出內容非 xlsx（多半是帳密錯誤被導回登入頁，請確認 .env）")
    return r.content


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


def _to_int(s: str) -> int:
    """ZH: '2,100,000' / '-1,234' / '0' → int（去掉逗號等非數字字元）。"""
    try:
        return int(re.sub(r"[^\d\-]", "", (s or "").strip()) or "0")
    except ValueError:
        return 0


def parse_transactions(html: str) -> list[dict]:
    """ZH: 解析交易日誌 HTML（廠商新版 kbx-grid 版型）→ list[dict]（不取 IP）。
       EN: parse the transaction log (vendor's kbx-grid layout). No IP stored."""
    from lxml import html as lxml_html  # ZH: 延遲匯入 | lazy import

    def _has(el, token: str) -> bool:  # ZH: class 是否含某 token
        return token in (el.get("class") or "").split()

    try:
        doc = lxml_html.fromstring(html)
    except Exception:  # noqa: BLE001
        return []

    out: list[dict] = []
    for row in doc.xpath("//div[contains(concat(' ', normalize-space(@class), ' '), ' kbx-row ')]"):
        grids = row.xpath(".//div[contains(concat(' ', normalize-space(@class), ' '), ' kbx-grid ')]")
        if not grids:
            continue
        grid = grids[0]
        # ZH: 時間 —— class 恰為 'kbx-time'（IP 欄雖也含 kbx-time 但同時含 kbx-dt，排除）
        tl = grid.xpath(".//div[normalize-space(@class)='kbx-time']/text()")
        t = tl[0].strip() if tl else ""
        # ZH: 桌面欄位（kbx-cell + kbx-dt）依序：點數 / 餘額 / 備註 / 帳號 / IP
        cells = [c for c in grid.xpath(".//div") if _has(c, "kbx-cell") and _has(c, "kbx-dt")]
        if len(cells) < 4:
            continue
        pts = _to_int(cells[0].text_content())
        bal = _to_int(cells[1].text_content())
        note = cells[2].text_content().strip()
        acct = cells[3]
        # ZH: 帳號欄 = email 子 div（含 @、非 kbx-muted）＋「名稱・sn:序號」的 kbx-muted 子 div
        email = ""
        for d in acct.xpath("./div"):
            txt = d.text_content().strip()
            if "@" in txt and not _has(d, "kbx-muted"):
                email = txt
                break
        name, sn = "", ""
        muted = [d for d in acct.xpath(".//div") if _has(d, "kbx-muted")]
        if muted:
            mt = muted[0].text_content().strip()   # ZH: 例："NyaLazy・sn:1003387"
            msn = re.search(r"sn:(\d+)", mt)
            sn = msn.group(1) if msn else ""
            name = re.sub(r"・?\s*sn:\d+\s*$", "", mt).strip()
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


def _tx_logged_in(r) -> bool:
    """ZH: 交易頁(已登入)含「交易紀錄／備註」；登入頁不含 → 用來判斷 session 是否有效。
       EN: the logged-in tx page contains these labels; the login page does not."""
    if r.status_code != 200:
        return False
    t = r.text
    return ("交易紀錄" in t) or ("備註" in t)


async def fetch_transactions_html(date_start: str, date_end: str) -> str:
    """ZH: GET admin 交易日誌(日期範圍) → 回 HTML（session 快取，失效才登入）。唯讀。
       EN: GET the admin transaction log reusing the cached session. Read-only."""
    async def _do(client):
        return await client.get(ADMIN_TX_PATH, params={"date_start": date_start, "date_end": date_end})

    r = await _session_request(_do, _tx_logged_in)
    if r.status_code != 200:
        raise MyaiSyncError(f"交易日誌回應 {r.status_code}（可能登入失敗或權限不足）")
    if not _tx_logged_in(r):
        raise MyaiSyncError("交易日誌非預期內容（多半被導回登入頁，請確認 .env）")
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
