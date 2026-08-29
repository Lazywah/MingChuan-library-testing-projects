"""
ZH: 問題回報的主旨與類別（v3.9）。

ZH: 這裡守的核心是**代碼的一致性**。類別存的是固定代碼（quota/train/…），
    不是顯示文字 —— 翻譯過的字串當篩選鍵的話，介面切成英文就篩不到東西。

ZH: 🔴 最危險的失效是安靜的：前端送一個後端不認得的代碼，後端把它當成
    「沒選」存成 NULL，使用者看不到任何錯誤，管理者則以為那個類別沒有回報。
    所以三邊（後端白名單、使用者端下拉、管理端對照表）的代碼必須一致，
    下面有一支測試直接比對三份清單。
"""
import sys
import os
import re

import pytest
from conftest import make_user, auth_headers

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "job-scheduler"))

from app import models, schemas  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _post(client, hdr, **kw):
    body = {"body": "測試內容", "diagnostics": {}}
    body.update(kw)
    return client.post("/api/v1/reports", headers=hdr, json=body)


@pytest.fixture
def hdr(client, db):
    make_user(db, username="rep1", email="rep1@example.com")
    return auth_headers(client, "rep1", "password123")


# ══════════════════════════════════════════════════════════════════════════
# ZH: 一、存得進去、讀得回來
# ══════════════════════════════════════════════════════════════════════════

def test_subject_and_category_round_trip(client, hdr):
    r = _post(client, hdr, subject="前往 MYAI 後是空白頁", category="quota")
    assert r.status_code == 201, r.text
    d = r.json()
    assert d["subject"] == "前往 MYAI 後是空白頁"
    assert d["category"] == "quota"

    mine = client.get("/api/v1/reports/mine", headers=hdr).json()
    assert mine[0]["subject"] == "前往 MYAI 後是空白頁"
    assert mine[0]["category"] == "quota"


def test_both_are_optional(client, hdr):
    """ZH: v3.9 之前的回報沒有這兩欄，現在也不強迫填 —— 兩者都要能是空的。"""
    r = _post(client, hdr)
    assert r.status_code == 201
    assert r.json()["subject"] is None
    assert r.json()["category"] is None


def test_blank_subject_becomes_null(client, hdr):
    """ZH: 整串空白等於沒填。存 "" 與存 None 要是同一種狀態。"""
    r = _post(client, hdr, subject="   ")
    assert r.json()["subject"] is None


# ══════════════════════════════════════════════════════════════════════════
# ZH: 二、類別是白名單
# ══════════════════════════════════════════════════════════════════════════

def test_unknown_category_is_dropped_not_stored(client, hdr):
    """
    ZH: 亂填的類別當成沒選。不擋的話資料庫會長出一堆只出現過一次的類別，
        管理端的篩選就沒有意義了。
    """
    r = _post(client, hdr, category="我自己編的")
    assert r.status_code == 201
    assert r.json()["category"] is None


@pytest.mark.parametrize("code", sorted(schemas.IssueReportCreate.CATEGORIES))
def test_every_whitelisted_code_is_accepted(client, db, code):
    """
    ZH: 陽性對照 —— 白名單裡的每一個都要收得下。
        只測「亂填會被丟掉」的話，白名單全空也會過。
    """
    make_user(db, username="u" + code, email=code + "@example.com")
    h = auth_headers(client, "u" + code, "password123")
    assert _post(client, h, category=code).json()["category"] == code


# ══════════════════════════════════════════════════════════════════════════
# ZH: 三、管理端的類別篩選
# ══════════════════════════════════════════════════════════════════════════

def test_admin_can_filter_by_category(client, db, hdr):
    _post(client, hdr, category="quota", subject="要額度")
    _post(client, hdr, category="lab", subject="實驗室壞了")

    make_user(db, username="adm9", email="adm9@example.com", role="admin")
    a = auth_headers(client, "adm9", "password123")

    only = client.get("/api/v1/admin/reports?category=quota", headers=a).json()
    assert [x["subject"] for x in only] == ["要額度"]
    assert len(client.get("/api/v1/admin/reports", headers=a).json()) == 2


def test_unknown_category_filter_is_rejected_not_ignored(client, db):
    """
    ZH: 🔴 未知的類別要**明講**，不能安靜地回全部。
        靜默忽略的話，前後端的代碼一旦漂開，管理者會看到一整份清單
        而以為「這個類別的回報就是這些」。
    """
    make_user(db, username="adm10", email="adm10@example.com", role="admin")
    a = auth_headers(client, "adm10", "password123")
    r = client.get("/api/v1/admin/reports?category=nope", headers=a)
    assert r.status_code == 400


# ══════════════════════════════════════════════════════════════════════════
# ZH: 四、三邊的代碼一致
# ══════════════════════════════════════════════════════════════════════════

def _codes_in_js(path):
    """ZH: 從 JS 的 CATEGORIES 陣列抓第一欄（代碼）。"""
    src = open(os.path.join(ROOT, path), encoding="utf-8").read()
    m = re.search(r"CATEGORIES = \[(.*?)\];", src, re.S)
    assert m, f"{path} 裡找不到 CATEGORIES"
    return set(re.findall(r"\['(\w+)',", m.group(1)))


def test_the_three_category_lists_agree():
    """
    ZH: 🔴 後端白名單、使用者端下拉、管理端對照表 —— 三份清單必須一致。

    ZH: 不一致的失效是**安靜的**：
          · 前端多一個 → 使用者選得到，送出後被存成 NULL，沒有錯誤訊息。
          · 管理端少一個 → 那個類別的回報在篩選列上根本不存在。
        兩種都不會有人回報，因為畫面看起來完全正常。
    """
    backend = set(schemas.IssueReportCreate.CATEGORIES)
    user = _codes_in_js("web-ui-V1/report.js")
    admin = _codes_in_js("admin-ui-V1/reports.js")
    assert user == backend, f"使用者端與後端不一致：{user ^ backend}"
    assert admin == backend, f"管理端與後端不一致：{admin ^ backend}"
