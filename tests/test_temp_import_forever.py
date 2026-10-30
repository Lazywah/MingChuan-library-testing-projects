# -*- coding: utf-8 -*-
"""
ZH: 批次匯入臨時帳號的到期日 —— v4.44 起是檔案的第 5 欄，每一列自己的
    （擁有者 2026-10-30；在此之前是整批共用的表單欄位＋「整批永久」勾選）。

ZH: 這一族守的仍然只有一件事：**「忘記填到期日」不可以變成「開了一批
    永遠不會消失的帳號」。** 空白不是永久 —— 要永久就明寫「永久」。
    單筆那條路的同一條規則在 schemas.AdminTempUserCreate.one_of_expiry；
    匯入這條是另外手寫的，兩份會不會漂開只有測試看得出來。

@node tests/test_temp_import_forever.py
"""
import datetime
import io
import json

import pytest

from conftest import make_user, auth_headers


@pytest.fixture
def admin_headers(client, db):
    make_user(db, username="adm", email="adm@example.com", role="admin")
    return auth_headers(client, "adm", "password123")


def _csv(rows):
    head = "username,email,password,role,expires\n"
    return (head + "\n".join(",".join(r) for r in rows)).encode("utf-8")


def _post(client, headers, rows, purpose="長官視察", dry_run=False, name="t.csv", blob=None):
    data = blob if blob is not None else _csv(rows)
    return client.post("/api/v1/admin/users/temporary/import", headers=headers,
                       data={"purpose": purpose, "dry_run": "true" if dry_run else "false"},
                       files={"file": (name, io.BytesIO(data), "text/csv")})


def _days(n):
    return (datetime.date.today() + datetime.timedelta(days=n)).isoformat()


# ── 永久：真的沒有到期日 ─────────────────────────────────────────────────

def test_forever_cell_creates_accounts_without_an_expiry(client, db, admin_headers):
    """ZH: 🔴 永久 = `expires_at` 是 NULL，不是一個很遠的日期。"""
    from app import models
    r = _post(client, admin_headers, [["g1", "g1@example.com", "", "學生", "永久"],
                                      ["g2", "g2@example.com", "", "學生", "永久"]])
    assert r.status_code == 200, r.text
    assert r.json()["never_expires_count"] == 2
    users = db.query(models.User).filter(models.User.username.in_(["g1", "g2"])).all()
    assert len(users) == 2
    assert all(u.expires_at is None for u in users)
    # ZH: 用途仍然要留著 —— 永久的臨時帳號更需要有人說得出它為什麼在。
    assert all(u.temp_purpose == "長官視察" for u in users)


def test_one_file_can_mix_dated_and_forever(client, db, admin_headers):
    """ZH: v4.44 新能力：同一個檔案裡有些永久、有些有期限（原本要分兩次匯入）。"""
    from app import models
    r = _post(client, admin_headers, [["m1", "", "", "訪客", _days(10)],
                                      ["m2", "", "", "訪客", "永久"]])
    assert r.status_code == 200, r.text
    got = {c["username"]: c["expires_on"] for c in r.json()["created"]}
    assert got == {"m1": _days(10), "m2": None}
    assert db.query(models.User).filter_by(username="m1").one().expires_at is not None
    assert db.query(models.User).filter_by(username="m2").one().expires_at is None


def test_audit_says_which_rows_were_permanent(client, db, admin_headers):
    """ZH: 稽核紀錄要分得出「永久」與「漏寫」——兩者的 expires_on 都是 null。"""
    from app import models
    r = _post(client, admin_headers, [["g1", "", "", "學生", "永久"]])
    assert r.status_code == 200, r.text
    act = db.query(models.AdminAction).filter_by(action="create_temp_account").first()
    payload = json.loads(act.payload)
    assert payload["expires_on"] is None
    assert payload["never_expires"] is True
    assert payload["batch_import"] is True


# ── 忘記填不等於永久 ─────────────────────────────────────────────────────

def test_blank_expiry_is_rejected_not_forever(client, db, admin_headers):
    """ZH: 🔴 整族測試的核心。空白 → 那一列驗不過，整批不建。"""
    from app import models
    r = _post(client, admin_headers, [["g1", "", "", "學生", "永久"],
                                      ["g2", "", "", "學生", ""]])
    assert r.status_code == 400, r.text
    assert db.query(models.User).filter(models.User.username.in_(["g1", "g2"])).count() == 0


def test_old_four_column_file_is_rejected(client, db, admin_headers):
    """ZH: 🔴 舊範例檔（沒有到期日欄）匯進來 → 擋下，而不是整批變成永久。"""
    blob = "username,email,password,role\ng1,,,學生\n".encode("utf-8")
    r = _post(client, admin_headers, None, blob=blob, dry_run=True)
    assert r.status_code == 200, r.text
    row = r.json()["rows"][0]
    assert r.json()["ok"] is False
    assert any("到期日空白" in e for e in row["errors"])


def test_preview_shows_each_rows_expiry(client, db, admin_headers):
    """ZH: 預覽要看得到每一列建到哪天 —— 送出前最後一個看得到「永久」的地方。"""
    r = _post(client, admin_headers, [["p1", "", "", "學生", _days(5)],
                                      ["p2", "", "", "學生", "永久"]], dry_run=True)
    rows = {x["username"]: x for x in r.json()["rows"]}
    assert rows["p1"]["expires_on"] == _days(5) and rows["p1"]["never_expires"] is False
    assert rows["p2"]["expires_on"] is None and rows["p2"]["never_expires"] is True


# ── 日期的寫法 ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("cell", [
    lambda d: d.isoformat(),
    lambda d: "%d/%d/%d" % (d.year, d.month, d.day),
    lambda d: d.strftime("%Y.%m.%d"),
])
def test_common_date_spellings_are_accepted(client, db, admin_headers, cell):
    d = datetime.date.today() + datetime.timedelta(days=20)
    r = _post(client, admin_headers, [["d1", "", "", "學生", cell(d)]], dry_run=True)
    assert r.json()["rows"][0]["expires_on"] == d.isoformat(), r.text


def test_xlsx_date_cell_is_read_as_a_date(client, db, admin_headers):
    """ZH: Excel 裡打的日期是日期型 —— str() 會變成 `2026-12-31 00:00:00`，要能認。"""
    import openpyxl
    d = datetime.date.today() + datetime.timedelta(days=15)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["帳號名稱", "信箱", "密碼", "身分", "到期日"])
    ws.append(["x1", "", "", "學生", datetime.datetime(d.year, d.month, d.day)])
    buf = io.BytesIO()
    wb.save(buf)
    r = _post(client, admin_headers, None, blob=buf.getvalue(), name="t.xlsx", dry_run=True)
    assert r.status_code == 200, r.text
    assert r.json()["rows"][0]["expires_on"] == d.isoformat()


@pytest.mark.parametrize("cell,why", [
    ("明年", "到期日看不懂"),
    ("2026-13-40", "到期日看不懂"),
])
def test_garbage_dates_are_rejected(client, db, admin_headers, cell, why):
    r = _post(client, admin_headers, [["z1", "", "", "學生", cell]], dry_run=True)
    assert any(why in e for e in r.json()["rows"][0]["errors"])


def test_a_far_future_date_is_accepted(client, db, admin_headers):
    """ZH: v4.42 拿掉 90 天上限 —— 遠一點的日期也收。"""
    r = _post(client, admin_headers, [["f1", "", "", "學生", _days(200)]])
    assert r.status_code == 200, r.text


def test_a_past_date_is_still_rejected(client, db, admin_headers):
    """ZH: 下限沒有跟著鬆掉：過去的日子＝建一個一出生就死的帳號。"""
    r = _post(client, admin_headers, [["f2", "", "", "學生", _days(-1)]])
    assert r.status_code == 400, r.text


def test_purpose_is_still_required_for_permanent(client, db, admin_headers):
    """ZH: 永久**不是**豁免用途 —— 沒有理由的永久帳號正是要防的東西。"""
    from app import models
    r = _post(client, admin_headers, [["g1", "", "", "學生", "永久"]], purpose="  ")
    assert r.status_code == 400, r.text
    assert db.query(models.User).filter_by(username="g1").first() is None


def test_template_has_the_expiry_column(client, admin_headers):
    """ZH: 範例檔要有第 5 欄，而且示範日期不能是過去（寫死的日期總有一天會過期）。"""
    r = client.get("/api/v1/admin/users/temporary/import-template?fmt=csv", headers=admin_headers)
    lines = r.content.decode("utf-8-sig").splitlines()
    assert "到期日" in lines[0]
    assert lines[1].split(",")[4] >= datetime.date.today().isoformat()
    assert lines[2].split(",")[4] == "永久"
