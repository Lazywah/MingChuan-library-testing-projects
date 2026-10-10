"""
ZH: v4.41 寄信紀錄分頁（擁有者 2026-10-10：寄信紀錄與管理動作 10 條一頁）。

ZH: 管理動作那支（/admin/audit）本來就有 offset／total；寄信紀錄原本只有 limit，
    前端一次撈 50 筆 —— 紀錄一多，更早的就永遠看不到了。

@node tests/test_email_log_paging.py
"""
from datetime import datetime, timedelta, timezone

import pytest

from conftest import auth_headers, make_user

from app import models


@pytest.fixture()
def admin_headers(client, db):
    make_user(db, username="mail-admin", email="mail-admin@example.com", role="admin")
    return auth_headers(client, "mail-admin", "password123")


@pytest.fixture()
def mails(db):
    """ZH: 23 封，時間由舊到新 —— 第 0 封最舊、第 22 封最新。"""
    base = datetime.now(timezone.utc) - timedelta(days=1)
    for i in range(23):
        db.add(models.EmailLog(to_email="u%02d@example.com" % i, kind="login_alert",
                               status="failed" if i % 5 == 0 else "sent",
                               created_at=base + timedelta(minutes=i)))
    db.commit()


def _get(client, h, **q):
    qs = "&".join("%s=%s" % kv for kv in q.items())
    r = client.get("/api/v1/admin/email-log?" + qs, headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def test_pages_are_newest_first_and_do_not_overlap(client, admin_headers, mails):
    p1 = _get(client, admin_headers, limit=10, offset=0)
    p2 = _get(client, admin_headers, limit=10, offset=10)
    p3 = _get(client, admin_headers, limit=10, offset=20)
    assert p1["total"] == 23
    assert [len(p["logs"]) for p in (p1, p2, p3)] == [10, 10, 3]
    assert p1["logs"][0]["to_email"] == "u22@example.com", "第一頁第一筆是最新的"
    seen = [m["to_email"] for p in (p1, p2, p3) for m in p["logs"]]
    assert len(seen) == len(set(seen)) == 23, "三頁加起來剛好每一封一次，沒有重複也沒有漏"


def test_total_follows_the_status_filter(client, admin_headers, mails):
    """ZH: 有篩選時，total 是篩選後的筆數 —— 不然頁數會算錯，最後幾頁是空的。"""
    body = _get(client, admin_headers, limit=10, offset=0, status="failed")
    assert body["total"] == 5
    assert all(m["status"] == "failed" for m in body["logs"])


def test_offset_past_the_end_is_empty_not_an_error(client, admin_headers, mails):
    """ZH: 前端停在最後一頁時資料變少（別人刪了）→ 回空清單，由前端退回上一頁。"""
    body = _get(client, admin_headers, limit=10, offset=100)
    assert body["logs"] == [] and body["total"] == 23


def test_old_callers_without_offset_still_work(client, admin_headers, mails):
    """ZH: 不帶 offset 的舊呼叫法照舊（預設 0）。"""
    body = _get(client, admin_headers, limit=5)
    assert len(body["logs"]) == 5 and body["offset"] == 0
