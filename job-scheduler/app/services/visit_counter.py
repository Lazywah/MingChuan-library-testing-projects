"""
==============================================================================
Service: 網站到訪計數 | Site visit counter
==============================================================================
ZH: 首頁那三個數字：本日 / 當月 / 歷史（擁有者需求 2026-09-23）。

ZH: 🔴 **算的是「人次」，不是「人數」，而且以「天」為去重單位。**
    同一個人今天來十次算 1，明天再來算 2。所以：
      · 本日 = 今天有幾個不重複的訪客
      · 當月 = 本月每天的不重複訪客**加總**（同一個人跨三天＝3）
      · 歷史 = 全部加總
    介面上的字就要寫「到訪人次」。寫成「人數」的話，一個每天來的人
    會讓那個數字每天 +1，而看的人會以為是有新的人進來。

ZH: 🔴 **不存 IP，也不存任何可以反推到個人的東西。**
    存的是 `sha256(伺服器密鑰 | 日期 | 訪客識別)` 的前 32 個字元。
    日期在雜湊裡面，所以**跨天的兩筆對不起來** —— 這張表沒辦法拿來
    追一個人的到訪軌跡，它只能回答「今天有沒有算過這一位」。
    與 `models.MyaiVisit` 同一條原則。

ZH: 訪客識別怎麼來（依序）：
      1. 前端 localStorage 裡的隨機 id（`visitor_id`）—— 最準：
         校園是 NAT，幾百個人共用一個對外 IP，只看 IP 會把他們算成一個人。
      2. 沒有的話退回 `IP + User-Agent`（關掉網站資料、或不跑 JS 的情況）。
    ⚠ 前端的 id 是可以被清掉、也可以被偽造的 —— 所以這個數字是
    **「大概有多少人來過」，不是稽核級的計數**。真的要防灌水得登入才算，
    而那會把「有多少人看過首頁」這個問題本身消滅掉。

ZH: ⚠ 明顯的機器人（curl / python-requests / 各家 crawler）不算。
    判準只看 User-Agent，擋得掉誠實的爬蟲，擋不掉裝成瀏覽器的 ——
    這一層的目的是不要讓監控探針把數字撐大，不是資安。

@node job-scheduler/app/services/visit_counter.py
==============================================================================
"""

from __future__ import annotations

import hashlib
import logging
import re
from datetime import date, datetime, timedelta

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import models
from ..config import settings
from ..gpu_schedule import TZ_TAIPEI

logger = logging.getLogger(__name__)

# ZH: 去重用的那張表要留多久。彙總（site_visit_days）是永久的，
#     這張只是「今天算過誰」的暫存 —— 留太久只是白佔空間。
#     45 天：比「本月」長，出事時還回得去看前一個月的明細。
RETAIN_DAYS = 45

# ZH: 機器人判準。⚠ 故意不含 "Mozilla" 這種所有瀏覽器都有的字。
_BOT = re.compile(
    r"bot|crawler|spider|crawling|slurp|curl/|wget|python-requests|httpx|"
    r"go-http-client|java/|okhttp|headlesschrome|lighthouse|uptime|monitor",
    re.IGNORECASE)


def taipei_today() -> date:
    """ZH: 今天（台北）。

    ZH: 🔴 一定要用台北時間，不能用 UTC。台北是 UTC+8，所以每天早上
        08:00 之前的到訪在 UTC 還是「昨天」—— 上班前來的人會被算到前一天，
        而每個月的 1 號早上會被算進上個月。

    @node job-scheduler/app/services/visit_counter.py::taipei_today
    """
    return datetime.now(TZ_TAIPEI).date()


def is_bot(user_agent: str | None) -> bool:
    """ZH: 看起來像機器人嗎？

    @node job-scheduler/app/services/visit_counter.py::is_bot
    """
    return bool(user_agent) and bool(_BOT.search(user_agent))


def visitor_hash(day: date, visitor_id: str | None,
                 ip: str | None, user_agent: str | None) -> str:
    """ZH: 算出今天的訪客雜湊（見檔頭：不存 IP、跨天對不起來）。

    ZH: ⚠ 密鑰用 `JWT_SECRET_KEY` —— 不另外生一把。多一把金鑰就多一個
        「換機器時忘了帶」的東西，而這裡要的只是「別人算不出這個雜湊」。

    @node job-scheduler/app/services/visit_counter.py::visitor_hash
    """
    who = (visitor_id or "").strip()[:64]
    if not who:
        # ZH: 退回 IP + UA。同一個 NAT 出口 + 同一種瀏覽器會被算成一個人 ——
        #     那是**低估**，不是高估，這個方向比較不會騙人。
        who = f"{ip or '?'}|{(user_agent or '?')[:120]}"
    raw = f"{settings.JWT_SECRET_KEY}|{day.isoformat()}|{who}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def _prune(db: Session, today: date) -> int:
    """ZH: 清掉過期的去重列。回傳刪了幾列。

    ZH: ⚠ 只刪 `site_visitors`（去重暫存），**不動 `site_visit_days`** ——
        那是彙總，刪掉就等於把歷史數字改小了。

    @node job-scheduler/app/services/visit_counter.py::_prune
    """
    cutoff = today - timedelta(days=RETAIN_DAYS)
    n = (db.query(models.SiteVisitor)
           .filter(models.SiteVisitor.day < cutoff)
           .delete(synchronize_session=False))
    if n:
        logger.info("ZH: 清掉 %d 列過期的到訪去重紀錄（%s 之前）", n, cutoff)
    return n


def record_visit(db: Session, *, visitor_id: str | None = None,
                 ip: str | None = None, user_agent: str | None = None) -> dict:
    """
    ZH: 記一次到訪（同一位訪客當天只算一次），回傳三個數字。

    ZH: 🔴 **不管有沒有算到都回同一組數字。** 重複到訪、機器人、寫入撞車 ——
        三種情況前端拿到的都是「目前的計數」。讓前端去分辨「這次有沒有被算到」
        沒有任何用處，卻會讓它多一條錯誤處理。

    ZH: ⚠ 併發：兩個請求同時插入同一個 (day, hash) 會撞主鍵。
        撞到就當成「已經算過」—— 那正是事實。

    @node job-scheduler/app/services/visit_counter.py::record_visit
    """
    today = taipei_today()
    if is_bot(user_agent):
        return get_stats(db)

    h = visitor_hash(today, visitor_id, ip, user_agent)
    seen = db.get(models.SiteVisitor, {"day": today, "visitor_hash": h})
    if seen is not None:
        return get_stats(db)

    row = db.get(models.SiteVisitDay, today)
    is_new_day = row is None
    try:
        db.add(models.SiteVisitor(day=today, visitor_hash=h))
        if row is None:
            row = models.SiteVisitDay(day=today, visits=0)
            db.add(row)
        row.visits = (row.visits or 0) + 1
        # ZH: 換日的第一筆順便清一次過期去重列 —— 不必為了這件事多開一個排程，
        #     而且一天只會跑一次（`is_new_day` 才做）。
        if is_new_day:
            _prune(db, today)
        db.commit()
    except IntegrityError:
        # ZH: 同一位訪客的兩個請求同時進來。已經算過了，不是錯誤。
        db.rollback()
    return get_stats(db)


def get_stats(db: Session) -> dict:
    """
    ZH: 三個數字：本日 / 當月 / 歷史（到訪人次，見檔頭）。

    ZH: ⚠ 「當月」是**本月 1 號到今天**，不是最近 30 天。
        使用者看到「當月」會去對月曆，用滾動 30 天的話月初那幾天
        會出現比「本日」還小之類的怪事。

    @node job-scheduler/app/services/visit_counter.py::get_stats
    """
    today = taipei_today()
    month_start = today.replace(day=1)

    def _sum(since: date | None) -> int:
        """@node job-scheduler/app/services/visit_counter.py::get_stats.<nested>._sum"""
        q = db.query(func.coalesce(func.sum(models.SiteVisitDay.visits), 0))
        if since is not None:
            q = q.filter(models.SiteVisitDay.day >= since)
        return int(q.scalar() or 0)

    row = db.get(models.SiteVisitDay, today)
    return {
        "today": int(row.visits) if row else 0,
        "month": _sum(month_start),
        "total": _sum(None),
        "as_of": today.isoformat(),
    }
