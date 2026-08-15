"""
==============================================================================
Service: 退信回收 (Bounce Reader) — v3.5
==============================================================================
ZH: 用途：把「非同步退信」變成程式看得到的事實。

    為什麼需要：SMTP 的 sendmail() 不拋錯只代表**中繼伺服器收下了**。
    「網域存在但信箱不存在」會被中繼接受，稍後才由對方 mail server 發一封
    退信（DSN, Delivery Status Notification）到**我們的寄件信箱**——那封信
    不會回到程式裡，所以 email_log 只會停在 `sent`。
    本模組用 IMAP 讀寄件信箱，把退信解析出來、回填 email_log，
    讓「誰的信箱不存在」變成有紀錄的事實，而不是靠猜。

    設計原則（沿用平台定調）：不預測信箱真假，只依事實跑事件。
    這裡處理的就是那個「事實」的來源。

    ⚠️ 安全與界線：
      - **唯讀 + 標記已讀**。絕不刪信、絕不移動、絕不寄信。
      - 只讀退信（寄件者為 MAILER-DAEMON/postmaster 或 multipart/report），
        其餘信件一律跳過不解析、不留存內容。
      - 只從退信取出：收件地址、狀態碼、診斷字串、原信 Message-ID。
        **不留存退信全文**，也不碰信箱裡的其他個人郵件。
      - 憑證沿用 .env 的 SMTP_* （Gmail 應用程式密碼 IMAP 通用），
        可用 IMAP_* 覆寫；一律不寫進版控。

EN: Turn asynchronous bounces (DSNs sitting in our own sender mailbox) into
    facts the code can see, by reading them over IMAP and back-filling
    email_log. Read-only: marks messages \\Seen, never deletes or moves them,
    parses only bounce messages, and stores only the delivery-status fields.
==============================================================================
"""

from __future__ import annotations

import email
import imaplib
import logging
import re
from datetime import datetime, timezone
from email.message import Message

from sqlalchemy.orm import Session

from .. import models
from ..config import settings

logger = logging.getLogger(__name__)

# ZH: IMAP 進度游標存 SystemConfig（跨重啟保留，避免每次重掃整個信箱）
CURSOR_KEY = "bounce_imap_cursor"      # 格式 "<UIDVALIDITY>:<lastUID>"

# ZH: 常見的退信寄件者 local-part（大小寫不拘）
_DAEMON_SENDERS = ("mailer-daemon", "postmaster", "mail-daemon", "mailerdaemon")

# ZH: 純文字退信的後援樣式（沒有標準 DSN 結構時才用）
_RE_STATUS = re.compile(r"\b([45]\.\d{1,3}\.\d{1,3})\b")
_RE_ADDR = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_RE_MSGID = re.compile(r"Message-I[Dd]\s*:\s*(<[^>]+>)")


class BounceReaderError(Exception):
    """ZH: 可預期的退信讀取錯誤（未設定、登入失敗、資料夾不存在）"""


# ==============================================================================
# 設定
# ==============================================================================
def imap_config() -> dict:
    """
    ZH: 取 IMAP 連線設定。預設沿用 SMTP 的帳密（Gmail 應用程式密碼 IMAP 通用），
        主機由 SMTP 主機推導（smtp.gmail.com → imap.gmail.com），可用 IMAP_* 覆寫。
    EN: IMAP settings, defaulting to the SMTP credentials and a host derived from
        the SMTP host; IMAP_* env vars override.

    @node job-scheduler/app/services/bounce_reader.py::imap_config
    """
    host = (getattr(settings, "IMAP_SERVER", "") or "").strip()
    if not host:
        smtp = (settings.SMTP_SERVER or "").strip().lower()
        # ZH: 只做最常見的 smtp.→imap. 推導；其他情況請明確設 IMAP_SERVER
        host = ("imap." + smtp[5:]) if smtp.startswith("smtp.") else ""
    return {
        "host": host,
        "port": int(getattr(settings, "IMAP_PORT", 0) or 993),
        "user": (getattr(settings, "IMAP_USERNAME", "") or settings.SMTP_USERNAME or "").strip(),
        "password": (getattr(settings, "IMAP_PASSWORD", "") or settings.SMTP_PASSWORD or ""),
        "folder": (getattr(settings, "IMAP_FOLDER", "") or "INBOX").strip(),
    }


# ==============================================================================
# 解析
# ==============================================================================
def is_bounce(msg: Message) -> bool:
    """ZH: 這封是不是退信？兩個判準取聯集：標準 DSN 結構、或寄件者是郵件守護程式。

    @node job-scheduler/app/services/bounce_reader.py::is_bounce
    """
    ctype = (msg.get_content_type() or "").lower()
    params = (msg.get("Content-Type") or "").lower()
    if ctype == "multipart/report" and "delivery-status" in params:
        return True
    sender = (msg.get("From") or "").lower()
    return any(d in sender for d in _DAEMON_SENDERS)


def _walk_delivery_status(msg: Message) -> list[dict]:
    """
    ZH: 解析標準 DSN 的 message/delivery-status 區塊（RFC 3464）。
        每個 recipient 區塊給一筆：Final-Recipient / Action / Status / Diagnostic-Code。

    @node job-scheduler/app/services/bounce_reader.py::_walk_delivery_status
    """
    out: list[dict] = []
    for part in msg.walk():
        if (part.get_content_type() or "").lower() != "message/delivery-status":
            continue
        # ZH: delivery-status 的 payload 是「一組 header 區塊」：第一塊是 per-message，
        #     其後每塊對應一個收件人。用 get_payload() 取得已解析的子 Message。
        blocks = part.get_payload()
        if not isinstance(blocks, list):
            continue
        for blk in blocks:
            recipient = (blk.get("Final-Recipient") or blk.get("Original-Recipient") or "")
            if not recipient:
                continue
            # ZH: 格式為 "rfc822; someone@example.com"
            addr = recipient.split(";", 1)[-1].strip().strip("<>")
            out.append({
                "recipient": addr,
                "action": (blk.get("Action") or "").strip().lower(),
                "status": (blk.get("Status") or "").strip(),
                "diagnostic": (blk.get("Diagnostic-Code") or "").strip()[:400],
            })
    return out


def _original_message_id(msg: Message) -> str | None:
    """
    ZH: 從退信裡挖出**原信**的 Message-ID。DSN 會把原信（或其 header）夾在
        message/rfc822 或 text/rfc822-headers 區塊裡。

    @node job-scheduler/app/services/bounce_reader.py::_original_message_id
    """
    for part in msg.walk():
        ctype = (part.get_content_type() or "").lower()
        if ctype == "message/rfc822":
            inner = part.get_payload()
            if isinstance(inner, list) and inner:
                mid = inner[0].get("Message-ID")
                if mid:
                    return mid.strip()
        elif ctype == "text/rfc822-headers":
            try:
                raw = part.get_payload(decode=True) or b""
                m = _RE_MSGID.search(raw.decode("utf-8", "replace"))
                if m:
                    return m.group(1).strip()
            except Exception:  # noqa: BLE001
                continue
    return None


def _plaintext_fallback(msg: Message) -> list[dict]:
    """
    ZH: 沒有標準 DSN 結構時的後援 —— 從純文字內容抓 5.x.x/4.x.x 狀態碼與地址。
        刻意保守：抓不到狀態碼就不猜，回空（寧可漏抓，不要誤判成退信）。

    @node job-scheduler/app/services/bounce_reader.py::_plaintext_fallback
    """
    text = ""
    for part in msg.walk():
        if (part.get_content_type() or "").lower() == "text/plain":
            try:
                text += (part.get_payload(decode=True) or b"").decode("utf-8", "replace")
            except Exception:  # noqa: BLE001
                continue
    m = _RE_STATUS.search(text)
    if not m:
        return []
    status = m.group(1)
    # ZH: 排除我們自己的寄件地址，剩下的第一個地址視為收件人
    ours = (settings.SMTP_FROM_EMAIL or "").lower()
    addrs = [a for a in _RE_ADDR.findall(text) if a.lower() != ours]
    if not addrs:
        return []
    return [{"recipient": addrs[0], "action": "failed", "status": status,
             "diagnostic": text.strip()[:400]}]


def parse_bounce(raw: bytes) -> dict | None:
    """
    ZH: 解析一封退信 → {"message_id":…, "recipients":[{recipient,status,action,diagnostic}]}
        不是退信、或解析不出收件人 → 回 None（呼叫端跳過，不留任何內容）。
    EN: Parse one bounce message; returns None for anything that isn't a parsable bounce.

    @node job-scheduler/app/services/bounce_reader.py::parse_bounce
    """
    try:
        msg = email.message_from_bytes(raw)
    except Exception as e:  # noqa: BLE001
        logger.debug("退信解析失敗（略過）：%s", e)
        return None
    if not is_bounce(msg):
        return None
    recipients = _walk_delivery_status(msg) or _plaintext_fallback(msg)
    if not recipients:
        return None
    return {"message_id": _original_message_id(msg), "recipients": recipients}


def classify_status(status: str, action: str = "") -> str:
    """
    ZH: RFC 3463 狀態碼 → 我們的 email_log.status
          5.x.x / action=failed  → bounced  （永久失敗：信箱不存在、網域不存在）
          4.x.x / action=delayed → deferred （暫時失敗：稍後可能仍會送達，不代表不存在）
        ⚠ 只有 bounced 才是「這個地址不存在」的事實；deferred 不是。
    EN: map DSN status class to our log status; only 5.x.x is a definitive failure.

    @node job-scheduler/app/services/bounce_reader.py::classify_status
    """
    s = (status or "").strip()
    if s.startswith("5"):
        return "bounced"
    if s.startswith("4"):
        return "deferred"
    return "bounced" if (action or "").startswith("fail") else "deferred"


# ==============================================================================
# 回填
# ==============================================================================
def apply_bounce(db: Session, parsed: dict) -> int:
    """
    ZH: 把一封退信的結果寫回 email_log。對應優先序：
          ① 原信 Message-ID（唯一可靠）
          ② 退不出 Message-ID 時 → 用收件地址找**最近一筆 sent**（次佳，會註明是推測對應）
        回填筆數。找不到對應也不新增假紀錄（我們只回填事實，不編造寄件紀錄）。
    EN: Back-fill email_log; prefer Message-ID, fall back to the latest `sent` row
        for that address. Never fabricates a row when no match is found.

    @node job-scheduler/app/services/bounce_reader.py::apply_bounce
    """
    n = 0
    now = datetime.now(timezone.utc)
    mid = parsed.get("message_id")
    for rec in parsed["recipients"]:
        row = None
        if mid:
            row = (db.query(models.EmailLog)
                     .filter(models.EmailLog.message_id == mid).first())
        guessed = False
        if row is None and rec.get("recipient"):
            row = (db.query(models.EmailLog)
                     .filter(models.EmailLog.to_email.ilike(rec["recipient"]),
                             models.EmailLog.status == "sent")
                     .order_by(models.EmailLog.created_at.desc()).first())
            guessed = row is not None
        if row is None:
            logger.info("收到退信但對不到寄件紀錄（不新增假紀錄）：%s", rec.get("recipient"))
            continue
        row.status = classify_status(rec.get("status", ""), rec.get("action", ""))
        row.bounced_at = now
        detail = f"[{rec.get('status') or '?'}] {rec.get('diagnostic') or ''}".strip()
        if guessed:
            detail += "（以收件地址推測對應：該退信未夾帶原信 Message-ID）"
        row.detail = detail[:400]
        n += 1
    if n:
        db.commit()
    return n


# ==============================================================================
# IMAP 掃描
# ==============================================================================
def scan_bounces(db: Session, max_messages: int = 200) -> dict:
    """
    ZH: 連上寄件信箱，讀游標之後的新信，解析退信並回填 email_log。
        **唯讀**：只把處理過的信標記為已讀（\\Seen），絕不刪除或移動。
        進度以 IMAP UID 游標記在 SystemConfig，重啟不會重掃。
    EN: Scan the sender mailbox for new bounces and back-fill the log. Read-only:
        marks processed messages \\Seen; never deletes or moves anything.

    @node job-scheduler/app/services/bounce_reader.py::scan_bounces
    """
    from .. import crud

    cfg = imap_config()
    if not cfg["host"] or not cfg["user"] or not cfg["password"]:
        raise BounceReaderError(
            "IMAP 未設定：需要 IMAP_SERVER（或可由 SMTP_SERVER 推導）與帳密。"
            "預設沿用 SMTP_USERNAME / SMTP_PASSWORD。")

    scanned = bounces = applied = 0
    try:
        M = imaplib.IMAP4_SSL(cfg["host"], cfg["port"])
    except Exception as e:  # noqa: BLE001
        raise BounceReaderError(f"IMAP 連線失敗（{cfg['host']}:{cfg['port']}）：{e}")
    try:
        try:
            M.login(cfg["user"], cfg["password"])
        except Exception as e:  # noqa: BLE001
            raise BounceReaderError(f"IMAP 登入失敗：{e}（Gmail 需使用應用程式密碼並開啟 IMAP）")
        typ, _ = M.select(cfg["folder"], readonly=False)
        if typ != "OK":
            raise BounceReaderError(f"IMAP 資料夾開啟失敗：{cfg['folder']}")

        # ZH: UIDVALIDITY 變了代表信箱重建，舊游標作廢 → 從頭掃一次
        typ, data = M.status(cfg["folder"], "(UIDVALIDITY)")
        uidvalidity = ""
        if typ == "OK" and data and data[0]:
            m = re.search(rb"UIDVALIDITY\s+(\d+)", data[0])
            uidvalidity = m.group(1).decode() if m else ""

        cursor = (crud.get_system_config(db, CURSOR_KEY, "") or "")
        last_uid = 0
        if cursor and ":" in cursor:
            cv, cu = cursor.split(":", 1)
            if cv == uidvalidity and cu.isdigit():
                last_uid = int(cu)

        # ZH: ① 先只取「新信的 UID 清單」（只回編號，不下載內容）→ 用來推進游標
        typ, data = M.uid("SEARCH", None, f"UID {last_uid + 1}:*")
        all_new = (data[0].split() if (typ == "OK" and data and data[0]) else [])
        # ZH: "UID n:*" 在沒有更新的信時仍會回最後一封 → 自行過濾
        all_new = [u for u in all_new if int(u) > last_uid]

        # ZH: ② ⭐ 伺服器端先篩退信，**只下載退信的內容**。
        #     不這樣做的話，等於把信箱裡的私人郵件全部抓下來再判斷 —— 即使不留存，
        #     也違反「只讀退信」這條界線。篩選條件取聯集：郵件守護程式寄件者 + 標準 DSN。
        # EN: server-side filter so only bounce bodies are ever downloaded; fetching every
        #     message would pull the user's personal mail through us, even if discarded.
        wanted: set = set()
        for crit in ('(FROM "mailer-daemon")', '(FROM "postmaster")',
                     '(HEADER Content-Type "report-type=delivery-status")'):
            try:
                typ, d = M.uid("SEARCH", None, f"UID {last_uid + 1}:*", crit)
                if typ == "OK" and d and d[0]:
                    wanted |= {u for u in d[0].split() if int(u) > last_uid}
            except Exception as e:  # noqa: BLE001 - 某條件不被伺服器支援就跳過該條件
                logger.debug("IMAP 篩選條件不支援（略過）：%s / %s", crit, e)

        uids = sorted(wanted, key=lambda x: int(x))[-max_messages:]
        max_seen = max([last_uid] + [int(u) for u in all_new])
        for uid in uids:
            scanned += 1
            typ, fetched = M.uid("FETCH", uid, "(BODY.PEEK[])")
            if typ != "OK" or not fetched or not isinstance(fetched[0], tuple):
                continue
            parsed = parse_bounce(fetched[0][1])
            if not parsed:
                continue          # ZH: 不是退信 → 不解析、不留存、不標記
            bounces += 1
            applied += apply_bounce(db, parsed)
            # ZH: 只對「確認是退信且已處理」的信標記已讀，其他人的信不動
            try:
                M.uid("STORE", uid, "+FLAGS", "(\\Seen)")
            except Exception as e:  # noqa: BLE001
                logger.debug("標記已讀失敗（不影響回填）：%s", e)

        if max_seen > last_uid and uidvalidity:
            crud.set_system_config(db, CURSOR_KEY, f"{uidvalidity}:{max_seen}")
    finally:
        try:
            M.logout()
        except Exception:  # noqa: BLE001
            pass

    logger.info("退信掃描完成：讀取 %d 封、退信 %d 封、回填 %d 筆", scanned, bounces, applied)
    return {"scanned": scanned, "bounces": bounces, "applied": applied,
            "host": cfg["host"], "folder": cfg["folder"]}
