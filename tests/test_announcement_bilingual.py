# -*- coding: utf-8 -*-
"""
ZH: 公告的中英雙語（v3.9）。

ZH: 這裡釘的是**後端那一半**：欄位存得進去、空字串正規化成 null。
    「英文空的就顯示中文」那條規則在前端（news.js 的 pickLang），
    後端只負責誠實回報**有沒有英文版** —— 兩邊的分工要分清楚，
    否則之後會有人在後端也做一次退回，然後兩份實作各自漂走。
"""
from conftest import auth_headers, make_user

import pytest


@pytest.fixture()
def admin_headers(client, db):
    make_user(db, username="bi-admin", email="bi-admin@example.com", role="admin")
    return auth_headers(client, "bi-admin", "password123")


def _create(client, admin_headers, **kw):
    payload = {"title": "中文標題", "body": "中文內容", "is_pinned": 0, "is_visible": 1}
    payload.update(kw)
    r = client.post("/api/v1/admin/announcements", headers=admin_headers, json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def test_english_version_round_trips(client, db, admin_headers):
    a = _create(client, admin_headers,
                title_en="English title", body_en="English body")

    assert a["title_en"] == "English title"
    assert a["body_en"] == "English body"
    # ZH: 中文欄位不受影響
    assert a["title"] == "中文標題"


def test_missing_english_is_null_not_empty_string(client, db, admin_headers):
    """ZH: 🔴 前端的空欄位送來是 ""，要正規化成 null。

    ZH: 存成 "" 的話，資料庫裡看不出「沒翻譯」與「翻譯成空字串」的差別；
        而前端判斷「有沒有英文版」看的是 truthy —— 兩者行為一樣，
        但之後任何人寫 `if title_en is not None` 就會得到錯的答案。
    """
    a = _create(client, admin_headers, title_en="", body_en="   ")

    assert a["title_en"] is None
    assert a["body_en"] is None


def test_english_only_partly_filled(client, db, admin_headers):
    """ZH: 只翻標題沒翻內文是常有的事，兩邊要各自獨立。"""
    a = _create(client, admin_headers, title_en="Only the title", body_en=None)

    assert a["title_en"] == "Only the title"
    assert a["body_en"] is None


def test_update_can_clear_english(client, db, admin_headers):
    """ZH: 編輯時把英文清空要真的清掉 —— 不然改錯了救不回來。"""
    a = _create(client, admin_headers, title_en="EN", body_en="EN body")

    r = client.put(f"/api/v1/admin/announcements/{a['id']}", headers=admin_headers,
                   json={"title": "中文標題", "body": "中文內容",
                         "title_en": "", "body_en": "",
                         "is_pinned": 0, "is_visible": 1})

    assert r.status_code == 200, r.text
    assert r.json()["title_en"] is None
    assert r.json()["body_en"] is None


def test_list_returns_english_fields(client, db, admin_headers):
    """ZH: 使用者端的清單要拿得到英文欄位，前端才挑得了語言。"""
    a = _create(client, admin_headers, title_en="English title")

    rows = client.get("/api/v1/announcements", headers=admin_headers).json()

    me = [r for r in rows if r["id"] == a["id"]][0]
    assert me["title_en"] == "English title"
