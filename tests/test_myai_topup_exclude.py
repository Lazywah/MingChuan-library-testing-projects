"""
ZH: v4.41 手動補齊可以排除特定帳號（擁有者 2026-10-13：例如已停用的臨時帳號 12360013
    不該拿到 4 萬點），以及同一天抓到的「確認框看不見、整頁卡住」。

ZH: 守的三件事：
    1. 🔴 **送出時也照排除名單算** —— 後端送出前會重新同步、重新算名單；
       只有預覽排除的話，被移除的人會在真的送出那一刻被算回來，點數收不回來。
    2. 回傳的 excluded 只列「本來會補、因為排除才沒補」的人。
    3. 管理端帳號頁的彈窗不能掛 data-view —— 掛了的話切到 MYAI 檢視時，
       確認框 display:none 卻仍是 modal，整頁被鎖住而且看不到要輸入的地方。

@node tests/test_myai_topup_exclude.py
"""
import json
import re

import pytest

from conftest import auth_headers, make_user, repo_file

from app import crud, models
from app.services import myai_sync as M


def _bind(db, username, points=0):
    email = "%s@example.com" % username
    sn = "sn-" + username
    u = models.User(username=username, email=email, hashed_password="x", role="student")
    db.add(u)
    db.flush()
    db.add(models.MyaiAccount(vendor_sn=sn, email=email, points=points))
    db.add(models.ExternalAiAccount(user_id=u.id, vendor_username=email,
                                    myai_vendor_sn=sn, status="active"))
    db.commit()
    return u


@pytest.fixture()
def no_vendor(monkeypatch):
    """ZH: 不連廠商：同步什麼都不做；轉點記下送出的名單。"""
    sent = []

    async def fake_sync(db):
        return {"status": "ok"}

    async def fake_transfer(rows, confirm_grant=False):
        sent.append(list(rows))
        return {"ok": True, "granted": True, "count": len(rows),
                "points": sum(r["points"] for r in rows)}

    monkeypatch.setattr(M, "sync", fake_sync)
    monkeypatch.setattr(M, "transfer_credit_batch", fake_transfer)
    return sent


@pytest.mark.asyncio
async def test_preview_excludes_and_recomputes_totals(db, no_vendor):
    _bind(db, "a1", 0)
    _bind(db, "a2", 1000)
    _bind(db, "dead", 0)
    r = await M.manual_topup(db, 5000, None, dry_run=True, exclude=["DEAD@example.com"])
    emails = [x["email"] for x in r["rows"]]
    assert "dead@example.com" not in emails, "排除比對要不分大小寫"
    assert r["count"] == 2 and r["points"] == 5000 + 4000
    assert r["excluded"] == ["dead@example.com"]
    assert no_vendor == [], "預覽不能送出任何東西"


@pytest.mark.asyncio
async def test_real_send_also_honours_the_exclusion(db, no_vendor):
    """ZH: 🔴 這一條是重點：送出時後端重算名單，排除名單必須一起生效。"""
    _bind(db, "b1", 0)
    _bind(db, "dead2", 0)
    r = await M.manual_topup(db, 3000, None, dry_run=False, exclude=["dead2@example.com"])
    assert r["status"] == "done"
    assert [x["email"] for x in no_vendor[0]] == ["b1@example.com"], "被排除的人不能出現在送出的名單"
    row = db.query(models.AdminAction).filter(models.AdminAction.action == "myai_manual_topup").one()
    payload = json.loads(row.payload)
    assert payload["excluded"] == ["dead2@example.com"], "稽核要記下這次排除了誰"


@pytest.mark.asyncio
async def test_excluding_someone_not_on_the_list_is_not_echoed(db, no_vendor):
    """ZH: 已經在水位以上（本來就不補）的人，排除了也不列 —— 不然畫面多一個點了沒作用的「復原」。"""
    _bind(db, "rich", 99999)
    _bind(db, "c1", 0)
    r = await M.manual_topup(db, 5000, None, dry_run=True, exclude=["rich@example.com"])
    assert r["excluded"] == []
    assert r["count"] == 1


def test_api_passes_exclude_through(client, db, monkeypatch, no_vendor):
    make_user(db, username="tu-admin", email="tu-admin@example.com", role="admin")
    h = auth_headers(client, "tu-admin", "password123")
    _bind(db, "d1", 0)
    _bind(db, "dead3", 0)
    r = client.post("/api/v1/admin/myai/topup", headers=h,
                    json={"target": 100, "dry_run": True, "exclude": ["dead3@example.com"]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["excluded"] == ["dead3@example.com"]
    assert [x["email"] for x in body["rows"]] == ["d1@example.com"]


def test_people_page_dialogs_are_not_view_scoped():
    """ZH: 🔴 2026-10-13 事故：pw-dialog 標了 data-view="platform"，切到 MYAI 檢視時被
        display:none !important —— 「確認補齊」的 showModal() 成功但框是 0×0，
        而 modal 把整頁設成 inert：沒有輸入框、什麼都點不動。"""
    html = repo_file("admin-ui-V1", "people.html").read_text(encoding="utf-8")
    bad = re.findall(r"<dialog[^>]*\bdata-view=", html)
    assert bad == [], "彈窗不能掛 data-view：%s" % bad
