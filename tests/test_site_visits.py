# -*- coding: utf-8 -*-
"""
ZH: 網站到訪人次（v4.24）—— 本日 / 當月 / 歷史。

ZH: 這一族守的是**那三個數字會不會騙人**：
      · 同一位訪客當天只算一次（重新整理不該讓數字長大）
      · 讀取端點（GET）絕對不能累加
      · 「當月」是本月 1 號到今天，不是最近 30 天
      · 日期用**台北**時間切（UTC 會把早上 08:00 之前的人算到前一天）
      · 不存 IP —— 存的是把日期揉進去的雜湊，跨天對不起來

ZH: 🔴 最重要的一條在 `TestItDoesNotLie`：數字只能往上，而且只能因為
    真的有人來才往上。一個會自己長大的計數器比沒有計數器更糟 ——
    它看起來像是有人在用。

@node tests/test_site_visits.py
"""
from datetime import date, datetime, timedelta, timezone


from app import models
from app.gpu_schedule import TZ_TAIPEI
from app.services import visit_counter as vc

UA_BROWSER = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36")


def _day(db, d: date, n: int):
    """ZH: 直接塞一天的彙總（測「當月／歷史」的加總用）。

    @node tests/test_site_visits.py::_day
    """
    db.add(models.SiteVisitDay(day=d, visits=n))
    db.commit()


# ── 去重 ────────────────────────────────────────────────────────────────
class TestOncePerVisitorPerDay:
    def test_same_visitor_twice_counts_once(self, db):
        vc.record_visit(db, visitor_id="alice", user_agent=UA_BROWSER)
        out = vc.record_visit(db, visitor_id="alice", user_agent=UA_BROWSER)
        assert out["today"] == 1

    def test_different_visitors_both_count(self, db):
        vc.record_visit(db, visitor_id="alice", user_agent=UA_BROWSER)
        out = vc.record_visit(db, visitor_id="bob", user_agent=UA_BROWSER)
        assert out["today"] == 2

    def test_no_visitor_id_falls_back_to_ip_and_ua(self, db):
        """ZH: 關掉網站資料的人沒有 id —— 退回 IP+UA，同一台仍然只算一次。"""
        vc.record_visit(db, ip="10.0.0.1", user_agent=UA_BROWSER)
        out = vc.record_visit(db, ip="10.0.0.1", user_agent=UA_BROWSER)
        assert out["today"] == 1
        out = vc.record_visit(db, ip="10.0.0.2", user_agent=UA_BROWSER)
        assert out["today"] == 2


# ── 不會自己長大 ────────────────────────────────────────────────────────
class TestItDoesNotLie:
    def test_reading_never_increments(self, client, db):
        """ZH: 🔴 GET 是唯讀。會自己長大的計數器比沒有計數器更糟。"""
        vc.record_visit(db, visitor_id="alice", user_agent=UA_BROWSER)
        first = client.get("/api/v1/system/visits").json()
        for _ in range(3):
            again = client.get("/api/v1/system/visits").json()
        assert again["today"] == first["today"] == 1
        assert again["total"] == first["total"] == 1

    def test_bots_are_not_counted(self, db):
        """ZH: 監控探針與爬蟲不算 —— 不然數字會被自己的 uptime check 撐大。"""
        for ua in ["curl/8.4.0", "python-requests/2.31", "Googlebot/2.1",
                   "Mozilla/5.0 (compatible; bingbot/2.0)"]:
            vc.record_visit(db, visitor_id=f"bot-{ua}", user_agent=ua)
        assert vc.get_stats(db)["today"] == 0

    def test_a_real_browser_is_counted(self, db):
        """ZH: **陽性對照** —— 機器人判準不可以把真的瀏覽器擋掉。"""
        vc.record_visit(db, visitor_id="alice", user_agent=UA_BROWSER)
        assert vc.get_stats(db)["today"] == 1


# ── 三個數字的定義 ──────────────────────────────────────────────────────
class TestTheThreeNumbers:
    def test_month_is_this_calendar_month_not_last_30_days(self, db):
        """
        ZH: 🔴 「當月」= 本月 1 號到今天。用滾動 30 天的話，
            月初會出現「當月比本日還小」之類對不起來的數字 ——
            而使用者看到「本月」是會去對月曆的。
        """
        today = vc.taipei_today()
        month_start = today.replace(day=1)
        _day(db, month_start - timedelta(days=1), 100)   # 上個月的最後一天
        # ZH: ⚠ 每個月 1 號跑這條時，month_start 就是今天 —— 那天不能再塞一列
        #     （會跟待會記的那一筆撞同一天，斷言就得分兩種寫法）。
        extra = 0
        if month_start != today:
            _day(db, month_start, 5)
            extra = 5
        vc.record_visit(db, visitor_id="alice", user_agent=UA_BROWSER)

        s = vc.get_stats(db)
        assert s["month"] == extra + 1, "上個月那 100 被算進當月了"
        assert s["total"] == 100 + extra + 1, "歷史要含上個月那 100"

    def test_total_includes_every_day(self, db):
        _day(db, date(2020, 1, 1), 7)
        _day(db, date(2024, 6, 30), 3)
        assert vc.get_stats(db)["total"] == 10

    def test_empty_database_is_zero_not_none(self, db):
        """ZH: 沒有任何資料時要回 0 —— None 會讓前端印出 'null'。"""
        s = vc.get_stats(db)
        assert s == {"today": 0, "month": 0, "total": 0,
                     "as_of": vc.taipei_today().isoformat()}


# ── 日界線 ──────────────────────────────────────────────────────────────
class TestTaipeiNotUtc:
    def test_today_is_taipei_date(self, db, monkeypatch):
        """
        ZH: 🔴 台北是 UTC+8 —— 早上 08:00 以前，UTC 還在「昨天」。
            用 UTC 切的話，上班前來的人會被算到前一天，
            而每個月 1 號早上的到訪會被算進上個月。
        """
        # ZH: 台北 2026-03-01 07:30 ＝ UTC 2026-02-28 23:30
        fixed = datetime(2026, 3, 1, 7, 30, tzinfo=TZ_TAIPEI)

        class _DT(datetime):
            @classmethod
            def now(cls, tz=None):
                """@node tests/test_site_visits.py::TestTaipeiNotUtc.<nested>.now"""
                return fixed if tz else fixed.replace(tzinfo=None)

        monkeypatch.setattr(vc, "datetime", _DT)
        assert vc.taipei_today() == date(2026, 3, 1)
        assert fixed.astimezone(timezone.utc).date() == date(2026, 2, 28), "前提：UTC 真的是前一天"


# ── 隱私 ────────────────────────────────────────────────────────────────
class TestPrivacy:
    def test_ip_is_never_stored(self, db):
        """ZH: 🔴 表裡不可以出現 IP —— 與 models.MyaiVisit 同一條原則。"""
        vc.record_visit(db, ip="140.136.1.23", user_agent=UA_BROWSER)
        rows = db.query(models.SiteVisitor).all()
        assert rows, "前提：真的有記到"
        for r in rows:
            assert "140.136" not in r.visitor_hash
            assert len(r.visitor_hash) == 32

    def test_the_same_person_hashes_differently_on_another_day(self, db):
        """
        ZH: 日期在雜湊裡面，所以跨天的兩筆**對不起來** ——
            這張表沒辦法拿來追一個人的到訪軌跡。
        """
        a = vc.visitor_hash(date(2026, 9, 23), "alice", None, None)
        b = vc.visitor_hash(date(2026, 9, 24), "alice", None, None)
        assert a != b


# ── 去重暫存會被清掉 ────────────────────────────────────────────────────
class TestPruning:
    def test_old_dedup_rows_are_pruned_but_totals_survive(self, db):
        """
        ZH: 🔴 清的是「今天算過誰」那張暫存，**不是彙總** ——
            清錯的話歷史數字會自己變小，而那是最難發現的一種錯
            （沒有人會記得上個月的數字是多少）。
        """
        today = vc.taipei_today()
        old = today - timedelta(days=vc.RETAIN_DAYS + 5)
        db.add(models.SiteVisitor(day=old, visitor_hash="x" * 32))
        _day(db, old, 42)
        db.commit()

        vc.record_visit(db, visitor_id="alice", user_agent=UA_BROWSER)

        assert db.query(models.SiteVisitor).filter(
            models.SiteVisitor.day == old).count() == 0, "過期的去重列沒清掉"
        assert vc.get_stats(db)["total"] == 43, "彙總被動到了"


# ── 端點 ────────────────────────────────────────────────────────────────
class TestEndpoints:
    def test_both_endpoints_are_public(self, client, db):
        """
        ZH: 🔴 刻意不要求登入 —— 它們回答的是「有多少人來過這個網站」。
            關在登入後面就只剩下「有多少人登入過」，那是另一個問題。
        """
        assert client.get("/api/v1/system/visits").status_code == 200
        r = client.post("/api/v1/system/visit", json={"visitor_id": "alice"},
                        headers={"User-Agent": UA_BROWSER})
        assert r.status_code == 200

    def test_post_returns_the_same_shape_as_get(self, client, db):
        """ZH: 前端兩條路用同一個 render()，形狀不一樣就會有一邊是空的。"""
        a = client.post("/api/v1/system/visit", json={"visitor_id": "alice"},
                        headers={"User-Agent": UA_BROWSER}).json()
        b = client.get("/api/v1/system/visits").json()
        assert set(a) == set(b) == {"today", "month", "total", "as_of"}

    def test_a_forged_visitor_id_cannot_be_absurdly_long(self, client, db):
        """ZH: 使用者送上來的字串不該變成塞任意資料的地方（截到 64 字）。"""
        r = client.post("/api/v1/system/visit", json={"visitor_id": "z" * 5000},
                        headers={"User-Agent": UA_BROWSER})
        assert r.status_code == 200
        assert all(len(x.visitor_hash) == 32 for x in db.query(models.SiteVisitor).all())
