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

    # ZH: v2.8 用本次抓到的「最新一列餘額」更新 myai_accounts.points，讓當前餘額隨交易變新
    #     （供低點數提醒即時判斷）；只更新本窗口有活動的人，其餘維持不變。
    bal_updated = _refresh_points_from_tx(db, rows)

    logger.info("MYAI tx-sync: fetched=%d created=%d bal_updated=%d (days=%d)",
                len(rows), created, bal_updated, days)
    return {"status": "ok", "fetched": len(rows), "created": created,
            "skipped": len(rows) - created, "balance_updated": bal_updated, "days": days}


def _refresh_points_from_tx(db: Session, rows: list[dict]) -> int:
    """ZH: 以每位使用者(vendor_sn)在本批交易中最新一列的餘額，更新 myai_accounts.points。
       EN: update myai_accounts.points to each user's latest tx balance in this batch."""
    latest: dict[str, tuple] = {}   # vendor_sn -> (occurred_at, balance)
    for r in rows:
        sn, occ = r.get("vendor_sn"), r.get("occurred_at")
        if not sn or occ is None:
            continue
        if sn not in latest or occ > latest[sn][0]:
            latest[sn] = (occ, r["balance"])
    updated = 0
    for sn, (_occ, bal) in latest.items():
        acc = db.query(models.MyaiAccount).filter(models.MyaiAccount.vendor_sn == sn).first()
        if acc and acc.points != bal:
            acc.points = bal
            updated += 1
    if updated:
        db.commit()
    return updated


# ==============================================================================
# ZH: v3.3 自動開通（首次登入即為學生建立 MYAI 帳號並綁定）
# EN: v3.3 auto-provision — create the student's MYAI account on first login & bind
# ------------------------------------------------------------------------------
# ZH: 使用廠商管理端「批次註冊」正式功能（非繞過註冊頁的 CAPTCHA）：
#       POST /mcu/gt_sdk/admin_168/user/register_batch_check   ← 上傳 xlsx（驗證/預覽）
#       → 確認送出（第二段）
#     Excel 格式（官方範本 register_batch.xlsx，**無標題列**，使用者已確認欄序）：
#       A=email、B=暱稱、C=密碼、D=備註
#     ⚠️ 這是對廠商端的「寫入」。原「唯讀」界線由使用者於 2026-08-05 有意識放寬，
#        僅限此官方批次註冊功能；transfer/top_up/delete 一律仍禁止。
# EN: Uses the vendor's official admin bulk-registration feature (not a CAPTCHA bypass).
#     Template columns (no header): A=email, B=nickname, C=password, D=remark.
# ==============================================================================
# ==============================================================================
# ⚠️⚠️ 端點辨識（2026-08-06 實地確認頁面標題）—— 廠商管理端有 **三個** Excel 上傳功能，
#      長得幾乎一樣，用錯會造成不可逆的點數損失。務必只用 register_*：
#
#   /user/register_batch         → 「批次註冊」✅ 本模組唯一該用的
#   /user/get_credit_batch       → 「批次**回收**點數」⛔ 名單＝**被扣點的人**
#                                   （點數從名單上的帳號收回管理者，是扣點不是發放）
#   /user/transfer_credit_batch  → 「批次轉移點數」⛔ 名單＝**收到點數的人**
#                                   （點數**從管理者自己的帳號**轉出給名單上的帳號＝發放）
#
#   ⚠️ 兩者的名單語意**完全相反**，誤用方向錯誤即造成不可逆損失：
#      · 把註冊名單誤送 get_credit  → 一次扣光全部學生的點數
#      · 把註冊名單誤送 transfer    → 從管理者帳號一次發出大量點數（池子被掏空）
#   三者各有獨立的 *_check 確認端點與 *.xlsx 範本，欄位格式亦不同，不可混用。
#   下方 _assert_register_endpoint() 會在每次送出前硬性驗證路徑，避免日後誤改。
# EN: THREE similar Excel-upload features; only register_* is used here. The two
#     credit endpoints have OPPOSITE list semantics — get_credit deducts FROM the
#     listed accounts; transfer_credit grants TO them from the admin's own balance.
#     Either misuse is irreversible.
# ==============================================================================
REGISTER_BATCH_PATH = "/mcu/gt_sdk/admin_168/user/register_batch"
REGISTER_BATCH_CHECK_PATH = "/mcu/gt_sdk/admin_168/user/register_batch_check"

# ZH: 明確列為禁用，若不慎被填進上面兩個常數，防呆會擋下
_FORBIDDEN_BATCH_TOKENS = ("credit", "transfer", "delete", "top_up", "topup")


def _assert_register_endpoint(path: str) -> None:
    """
    ZH: 送出前硬性驗證：路徑必須是註冊端點，且不得含任何點數/轉移/刪除字樣。
        目的是防止日後有人改錯常數、或複製貼上到別的批次功能而造成點數損失。
    EN: Hard guard — the upload target must be the registration endpoint and must
        not contain credit/transfer/delete tokens (irreversible point loss otherwise).
    """
    p = (path or "").lower()
    if "register_batch" not in p:
        raise MyaiSyncError(f"拒絕送出：目標端點不是批次註冊（{path}）")
    for bad in _FORBIDDEN_BATCH_TOKENS:
        if bad in p:
            raise MyaiSyncError(f"拒絕送出：端點含禁用字樣 '{bad}'（{path}）—— 可能誤用點數相關功能")


def gen_initial_password(length: int = 12) -> str:
    """
    ZH: 產生 MYAI 初始密碼。廠商規則 8~20 字元；此處固定 12 碼並保證含大小寫+數字。
        刻意不用學號（公開資訊 → 任何人可登入他人帳號）。排除易混淆字元 0/O/1/l/I。
    EN: Random initial password (vendor allows 8-20). Never the student id (public).
    """
    import secrets as _secrets
    lower = "abcdefghijkmnopqrstuvwxyz"
    upper = "ABCDEFGHJKLMNPQRSTUVWXYZ"
    digits = "23456789"
    pool = lower + upper + digits
    while True:
        pwd = "".join(_secrets.choice(pool) for _ in range(length))
        if (any(c in lower for c in pwd) and any(c in upper for c in pwd)
                and any(c in digits for c in pwd)):
            return pwd


def build_register_xlsx(rows: list[dict]) -> bytes:
    """
    ZH: 依官方範本格式產生上傳用 xlsx（無標題列；A=email B=暱稱 C=密碼 D=備註）。
    EN: Build the upload workbook matching the vendor template (no header row).

    rows: [{"email":..., "nickname":..., "password":..., "remark":...}, ...]
    """
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    for r in rows:
        ws.append([
            (r.get("email") or "").strip(),
            (r.get("nickname") or "").strip(),
            (r.get("password") or "").strip(),
            (r.get("remark") or "").strip(),
        ])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


async def register_batch(rows: list[dict]) -> dict:
    """
    ZH: 送出批次註冊。**第一段**上傳 xlsx 至 register_batch_check（驗證/預覽）。
        ⚠️ **第二段（確認送出）尚未實作** —— 該頁的實際欄位/token 需真實 POST 一次才看得到，
        使用者尚未授權對廠商寫入測試。目前僅回傳第一段回應供解析與人工確認。
        待實測後在此補上確認步驟（找 confirm form 的 action + hidden 欄位再 POST）。
    EN: Step 1 uploads the workbook to register_batch_check (validate/preview).
        Step 2 (confirm) is intentionally NOT implemented until we can observe the
        real response shape; the caller must treat this as "submitted for check".

    回傳 {"ok": bool, "status": int, "html": str}
    """
    # ZH: 防呆 —— 廠商還有「批次回收點數 / 批次轉移點數」兩個長得一樣的 Excel 上傳功能，
    #     用錯會造成不可逆的點數損失。送出前硬性驗證目標端點。
    _assert_register_endpoint(REGISTER_BATCH_CHECK_PATH)
    _assert_register_endpoint(REGISTER_BATCH_PATH)

    xlsx = build_register_xlsx(rows)

    async def _do(client):
        return await client.post(
            REGISTER_BATCH_CHECK_PATH,
            files={"upload_xls": ("register_batch.xlsx", xlsx,
                                  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            headers={"Referer": settings.MYAI_BASE_URL.rstrip("/") + REGISTER_BATCH_PATH},
        )

    def _valid(r):
        return r.status_code == 200 and "Unauthorized" not in r.text[:200]

    r = await _session_request(_do, _valid)
    return {"ok": _valid(r), "status": r.status_code, "html": r.text}


def _nickname_for(user) -> str:
    """ZH: 暱稱優先用平台顯示名，退回 username（學號）| EN: nickname for the vendor account"""
    for attr in ("display_name", "full_name", "name"):
        v = (getattr(user, attr, None) or "").strip()
        if v:
            return v[:60]
    return (user.username or "")[:60]


def store_initial_password(db: Session, acc, plaintext: str) -> None:
    """ZH: 加密暫存初始密碼（AES-256-GCM，同 user_secrets 的 KEK）並記發放時間。
       EN: Encrypt-at-rest the generated initial password with the shared KEK."""
    from . import secrets_service
    acc.init_pwd_enc = secrets_service.encrypt_value(plaintext)
    acc.init_pwd_at = datetime.now(timezone.utc)
    acc.init_pwd_ack = 0
    db.commit()


def read_initial_password(db: Session, acc, retention_days: int) -> str | None:
    """
    ZH: 讀出未逾期且未被確認修改的初始密碼；逾期/已確認則就地清除並回 None。
        （學生始終可用 MYAI 自己的「忘記密碼」+ 學校信箱自助重設，故到期清除不會鎖死人。）
    EN: Return the initial password if still within retention and unacknowledged;
        otherwise purge it in place. Students can always self-serve via MYAI's own
        forgot-password using their school email.
    """
    if not acc or not acc.init_pwd_enc:
        return None
    if acc.init_pwd_ack:
        clear_initial_password(db, acc)
        return None
    issued = acc.init_pwd_at
    if issued is not None and issued.tzinfo is None:
        issued = issued.replace(tzinfo=timezone.utc)
    if issued is None or (datetime.now(timezone.utc) - issued) > timedelta(days=retention_days):
        clear_initial_password(db, acc)
        return None
    from . import secrets_service
    try:
        return secrets_service.decrypt_value(acc.init_pwd_enc)
    except Exception as e:  # noqa: BLE001 - 金鑰換過/資料損壞 → 當作沒有
        logger.warning("初始密碼解密失敗（視為不存在）: %s", e)
        return None


def clear_initial_password(db: Session, acc) -> None:
    """ZH: 清除暫存的初始密碼（學生按「已修改」或逾期）| EN: purge the stored initial password"""
    acc.init_pwd_enc = None
    acc.init_pwd_at = None
    db.commit()


def purge_expired_initial_passwords(db: Session, retention_days: int) -> int:
    """ZH: 批次清除逾期初始密碼（背景任務呼叫）| EN: purge expired initial passwords"""
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    rows = (
        db.query(models.ExternalAiAccount)
        .filter(models.ExternalAiAccount.init_pwd_enc.isnot(None))
        .all()
    )
    n = 0
    for acc in rows:
        issued = acc.init_pwd_at
        if issued is not None and issued.tzinfo is None:
            issued = issued.replace(tzinfo=timezone.utc)
        if acc.init_pwd_ack or issued is None or issued < cutoff:
            acc.init_pwd_enc = None
            acc.init_pwd_at = None
            n += 1
    if n:
        db.commit()
        logger.info("已清除 %d 筆逾期/已確認的 MYAI 初始密碼", n)
    return n


async def provision_user(db: Session, user) -> dict:
    """
    ZH: v3.3 自動開通主流程（首次 SSO 登入後以背景任務呼叫，**不阻塞登入**）。
        狀態機（每一步都可安全重入，重複呼叫不會重複建號）：
          disabled      → 功能旗標關閉
          bound         → 已有綁定，什麼都不用做
          linked_only   → 廠商端已有此 email（先前已註冊）→ 只補綁定，不建號
          created       → 呼叫廠商批次註冊建號 + 綁定 + 暫存初始密碼
          failed        → 廠商端失敗（保留錯誤訊息供 admin 檢視）
    EN: Auto-provision orchestrator; idempotent, runs in background after SSO login.
    """
    from .. import crud
    if not crud.get_setting(db, "myai_autoprovision"):
        return {"status": "disabled"}

    email = (user.email or "").strip()
    if not email or email.endswith("@unknown"):
        return {"status": "skipped", "reason": "no_usable_email"}

    acc = (db.query(models.ExternalAiAccount)
             .filter(models.ExternalAiAccount.user_id == user.id).first())
    if acc and acc.vendor_username:
        return {"status": "bound"}

    # ZH: 廠商端已存在同 email → 只建綁定（避免重複註冊；使用者確認重複會被跳過）
    exist = (db.query(models.MyaiAccount)
               .filter(models.MyaiAccount.email.ilike(email)).first())
    if exist:
        if not acc:
            acc = models.ExternalAiAccount(user_id=user.id, vendor_username=email,
                                           status="active", note="auto-provision(linked)")
            db.add(acc)
        acc.vendor_username = email
        acc.myai_vendor_sn = exist.vendor_sn
        db.commit()
        return {"status": "linked_only", "email": email}

    # ZH: 真正建號 —— 走廠商管理端官方批次註冊
    password = gen_initial_password()
    rows = [{"email": email, "nickname": _nickname_for(user),
             "password": password, "remark": "auto-provision"}]
    try:
        res = await register_batch(rows)
    except Exception as e:  # noqa: BLE001
        logger.error("MYAI 自動開通失敗 %s: %s", email, e)
        return {"status": "failed", "error": str(e)[:200]}
    if not res.get("ok"):
        return {"status": "failed", "error": f"廠商回應 {res.get('status')}"}

    if not acc:
        acc = models.ExternalAiAccount(user_id=user.id, vendor_username=email,
                                       status="active", note="auto-provision")
        db.add(acc)
    acc.vendor_username = email
    db.commit()
    db.refresh(acc)
    store_initial_password(db, acc, password)
    logger.info("MYAI 自動開通完成: %s", email)
    return {"status": "created", "email": email}


def provision_status(db: Session, user) -> dict:
    """
    ZH: 學生端查詢自己的開通狀態。**只在保留期內、且尚未確認修改**時才回傳初始密碼。
        身分一律由 JWT 推導（呼叫端傳 user 物件），查不到別人的。
    EN: Per-user provisioning status; the initial password is returned only while
        within the retention window and not yet acknowledged.
    """
    from .. import crud
    acc = (db.query(models.ExternalAiAccount)
             .filter(models.ExternalAiAccount.user_id == user.id).first())
    if not acc:
        return {"provisioned": False, "email": None, "initial_password": None}
    days = crud.get_setting(db, "myai_init_pwd_days")
    pwd = read_initial_password(db, acc, days)
    return {
        "provisioned": True,
        "email": acc.vendor_username,
        "initial_password": pwd,                     # None = 已確認/逾期/本來就沒有
        "acknowledged": bool(acc.init_pwd_ack),
        "retention_days": days,
    }


def acknowledge_initial_password(db: Session, user) -> bool:
    """ZH: 學生按「我已修改密碼」→ 立即銷毀暫存的初始密碼"""
    acc = (db.query(models.ExternalAiAccount)
             .filter(models.ExternalAiAccount.user_id == user.id).first())
    if not acc:
        return False
    acc.init_pwd_ack = 1
    clear_initial_password(db, acc)
    return True


# ==============================================================================
# ZH: v3.4 MYAI 即時使用狀態（四象限）—— 交叉比對「MYAI 近期用量」×「平台在線」
# EN: v3.4 live MYAI usage quadrants — recent vendor usage × platform online
# ------------------------------------------------------------------------------
# ZH: 用途有二：
#   (a) 監控：現在有多少人真的在用 MYAI、用哪些模型
#   (b) 稽核：**有用量但人不在平台** → 可能在別台電腦使用，或共用機台沒登出被盜用
#       （呼應共用機台換手問題；這象限刻意標紅）
#   ⚠️ 資料新鮮度受輪詢限制：交易來自每 N 分鐘輪詢廠商，故「當前」實為「近即時」，
#      最壞情況落後一個輪詢週期。UI 需明示上次同步時間，別讓人誤以為是即時推播。
# ==============================================================================
ONLINE_WINDOW_MINUTES = 10      # ZH: 平台在線判定（對齊 admin 的 _ONLINE_THRESHOLD）
USAGE_WINDOW_MINUTES = 15       # ZH: MYAI「近期有用量」判定（含輪詢延遲的緩衝）


def live_usage_quadrants(db: Session, usage_minutes: int = USAGE_WINDOW_MINUTES,
                         online_minutes: int = ONLINE_WINDOW_MINUTES) -> dict:
    """
    ZH: 回傳四象限狀態。象限＝(MYAI 近期有 ai_usage) × (平台近期在線)
          using_active   ✅✅ 正常使用中
          using_offplat  ✅❌ **有用量但人不在平台**（稽核重點）
          online_idle    ❌✅ 在平台但沒用 AI
          （❌❌ 閒置者不列出，避免清單無意義地變長）
        身分關聯：external_ai_accounts 的 myai_vendor_sn 優先、退回 vendor_username(email)。
        未綁定但有用量的廠商帳號另列 unlinked（多半是老師/管理者或尚未綁定的學生）。
    EN: Cross-tab of recent vendor usage × platform presence; unlinked vendor rows listed separately.
    """
    now = datetime.now(timezone.utc)
    usage_cut = now - timedelta(minutes=max(1, usage_minutes))
    online_cut = now - timedelta(minutes=max(1, online_minutes))

    # ZH: 近期 ai_usage 逐筆（只取扣點事件；login/transfer 不算「在使用」）
    rows = (
        db.query(models.MyaiTransaction)
        .filter(models.MyaiTransaction.event_type == "ai_usage")
        .filter(models.MyaiTransaction.occurred_at >= usage_cut.replace(tzinfo=None))
        .all()
    )
    # 依廠商帳號彙總：最後一次活動、期間內筆數與消耗點數、用過的模型
    by_vendor: dict = {}
    for t in rows:
        key = (t.vendor_sn or "").strip() or (t.email or "").strip().lower()
        if not key:
            continue
        agg = by_vendor.setdefault(key, {
            "vendor_sn": t.vendor_sn, "email": t.email, "name": t.name,
            "last_at": None, "events": 0, "points": 0, "models": set(),
        })
        agg["events"] += 1
        agg["points"] += abs(t.points_delta or 0)
        if t.model:
            agg["models"].add(t.model)
        occ = t.occurred_at
        if occ is not None and (agg["last_at"] is None or occ > agg["last_at"]):
            agg["last_at"] = occ
            agg["email"] = t.email or agg["email"]
            agg["name"] = t.name or agg["name"]

    # ZH: 綁定表 → 平台使用者（sn 與 email 兩種索引都建，對應查詢順序）
    accs = db.query(models.ExternalAiAccount).all()
    user_ids = {a.user_id for a in accs}
    users = {u.id: u for u in db.query(models.User).filter(models.User.id.in_(user_ids)).all()} if user_ids else {}
    by_sn, by_email = {}, {}
    for a in accs:
        u = users.get(a.user_id)
        if not u:
            continue
        if a.myai_vendor_sn:
            by_sn[str(a.myai_vendor_sn).strip()] = u
        if a.vendor_username:
            by_email[a.vendor_username.strip().lower()] = u

    def _online(u) -> bool:
        last = getattr(u, "last_activity", None)
        if not last:
            return False
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        return last >= online_cut

    used_user_ids = set()
    using_active, using_offplat, unlinked = [], [], []
    for key, agg in by_vendor.items():
        u = by_sn.get(key) or by_email.get(key)
        last_at = agg["last_at"]
        item = {
            "vendor_sn": agg["vendor_sn"],
            "email": agg["email"],
            "vendor_name": agg["name"],
            "last_used_at": last_at.isoformat() if last_at else None,
            "events": agg["events"],
            "points_used": agg["points"],
            "models": sorted(agg["models"]),
            "username": getattr(u, "username", None),
            "user_id": getattr(u, "id", None),
            "role": getattr(u, "role", None),
        }
        if u is None:
            unlinked.append(item)
            continue
        used_user_ids.add(u.id)
        (using_active if _online(u) else using_offplat).append(item)

    # ZH: 在平台但近期沒動 MYAI（只列非 admin，admin 開著後台不算「使用者在用」）
    online_idle = []
    for u in db.query(models.User).filter(models.User.role != "admin").all():
        if u.id in used_user_ids or not _online(u):
            continue
        la = u.last_activity
        if la is not None and la.tzinfo is None:
            la = la.replace(tzinfo=timezone.utc)
        online_idle.append({
            "username": u.username, "user_id": u.id, "email": u.email,
            "last_activity": la.isoformat() if la else None,
        })

    latest_sync = db.query(models.MyaiTransaction.synced_at).order_by(
        models.MyaiTransaction.synced_at.desc()).first()
    return {
        "using_active": sorted(using_active, key=lambda x: x["last_used_at"] or "", reverse=True),
        "using_offplat": sorted(using_offplat, key=lambda x: x["last_used_at"] or "", reverse=True),
        "online_idle": sorted(online_idle, key=lambda x: x["last_activity"] or "", reverse=True),
        "unlinked": sorted(unlinked, key=lambda x: x["last_used_at"] or "", reverse=True),
        "usage_window_minutes": usage_minutes,
        "online_window_minutes": online_minutes,
        "last_tx_sync": latest_sync[0].isoformat() if latest_sync and latest_sync[0] else None,
    }


def has_online_users(db: Session, online_minutes: int = ONLINE_WINDOW_MINUTES) -> bool:
    """
    ZH: 平台上是否有「非 admin」使用者在線 —— 給輪詢迴圈判斷要不要跳過這一輪。
        排除 admin 的理由：管理者開著後台不代表有學生在用 MYAI，否則永遠不會休息。
    EN: Whether any non-admin user is active; drives the poll-skip optimization.
    """
    cut = (datetime.now(timezone.utc) - timedelta(minutes=max(1, online_minutes))).replace(tzinfo=None)
    return db.query(models.User).filter(
        models.User.role != "admin",
        models.User.last_activity.isnot(None),
        models.User.last_activity >= cut,
    ).first() is not None
