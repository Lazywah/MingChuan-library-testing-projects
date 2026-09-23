# -*- coding: utf-8 -*-
"""
ZH: v4.22 —— 「不再提醒」跟著帳號走（users.ui_dismissed）。

ZH: 為什麼不放瀏覽器：localStorage 綁的是**瀏覽器設定檔 + 網域**，與帳號無關。
    圖書館的公用電腦上，第一個人按掉之後，後面每個人都不會再看到說明 ——
    而那些人正是最需要看到的（擁有者 2026-09-21 指出）。

ZH: 這一族守的：整份覆蓋（不是增量，否則「取消」沒有表達方式）、
    格式驗證（使用者送上來的字串不該變成塞任意資料的地方）、
    以及缺值行為（沒送就不動，不要當成清空）。

@node tests/test_ui_dismissed.py
"""
import pytest

from conftest import make_user, auth_headers


@pytest.fixture
def headers(client, db):
    make_user(db)
    return auth_headers(client)


def _patch(client, headers, **body):
    return client.patch("/api/v1/auth/me/preferences", json=body, headers=headers)


# ── 讀寫 ────────────────────────────────────────────────────────────────

def test_default_is_empty(client, db, headers):
    me = client.get("/api/v1/auth/me", headers=headers).json()
    assert me["ui_dismissed"] == ""


def test_saved_value_comes_back_on_me(client, db, headers):
    """ZH: 🔴 要能從 /auth/me 回來 —— 前端就是搭它的便車讀的（不另外發請求）。"""
    assert _patch(client, headers, ui_dismissed="myai").status_code == 200
    assert client.get("/api/v1/auth/me", headers=headers).json()["ui_dismissed"] == "myai"


def test_replace_not_append(client, db, headers):
    """ZH: 整份覆蓋 —— 增量的話「取消不再提醒」就沒有表達方式了。"""
    _patch(client, headers, ui_dismissed="myai,lab")
    _patch(client, headers, ui_dismissed="lab")
    assert client.get("/api/v1/auth/me", headers=headers).json()["ui_dismissed"] == "lab"


def test_can_be_cleared(client, db, headers):
    _patch(client, headers, ui_dismissed="myai")
    assert _patch(client, headers, ui_dismissed="").status_code == 200
    assert client.get("/api/v1/auth/me", headers=headers).json()["ui_dismissed"] == ""


def test_absent_field_does_not_touch_it(client, db, headers):
    """ZH: 🔴 沒送這個欄位時**不要動它** —— 改字級時順手清空的話，
       使用者會發現「我調了字級，說明彈窗又冒出來了」。"""
    _patch(client, headers, ui_dismissed="myai")
    assert _patch(client, headers, ui_font_scale=125).status_code == 200
    me = client.get("/api/v1/auth/me", headers=headers).json()
    assert me["ui_dismissed"] == "myai" and me["ui_font_scale"] == 125


# ── 格式 ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("bad", [
    "<script>x</script>",          # ZH: 不該變成塞任意字串的地方
    "MyAI",                        # ZH: 只收小寫（避免同一個 key 兩種寫法）
    "a" * 201,                     # ZH: 長度上限
    "a b",                         # ZH: 空白
])
def test_bad_values_are_refused(client, db, headers, bad):
    assert _patch(client, headers, ui_dismissed=bad).status_code == 422


@pytest.mark.parametrize("ok", ["myai", "myai,lab", "a-b_c", ""])
def test_good_values_are_accepted(client, db, headers, ok):
    assert _patch(client, headers, ui_dismissed=ok).status_code == 200


# ── 實際用到的 key ──────────────────────────────────────────────────────

def test_the_tour_key_round_trips(client, db, headers):
    """
    ZH: v4.26 引導導覽用 `tour` 這個 key 記「看過了」。

    ZH: 🔴 為什麼值得一條測試：`_sane_dismissed` 只收 [a-z0-9_,-]，而
        `prefs.js` 的 dismiss **是靜默失敗的**（存不回去只記在本機）。
        所以若哪天有人把 key 改成大寫或帶空白，症狀是
        「每次登入都被導覽一次」，而且後端 log 與前端 console 都乾乾淨淨。
    """
    assert _patch(client, headers, ui_dismissed="tour").status_code == 200
    assert client.get("/api/v1/auth/me", headers=headers).json()["ui_dismissed"] == "tour"

    # ZH: 與別的 key 並存（導覽 + MYAI 的離站提醒）
    assert _patch(client, headers, ui_dismissed="myai,tour").status_code == 200
    assert client.get("/api/v1/auth/me", headers=headers).json()["ui_dismissed"] == "myai,tour"


# ── 隔離 ────────────────────────────────────────────────────────────────

def test_one_users_dismissal_does_not_affect_another(client, db):
    """ZH: 🔴 這正是搬到帳號上的理由 —— 公用電腦換人登入就換一份。"""
    make_user(db, username="a1", email="a1@example.com")
    make_user(db, username="b2", email="b2@example.com")
    ha = auth_headers(client, "a1")
    hb = auth_headers(client, "b2")

    _patch(client, ha, ui_dismissed="myai")
    assert client.get("/api/v1/auth/me", headers=ha).json()["ui_dismissed"] == "myai"
    assert client.get("/api/v1/auth/me", headers=hb).json()["ui_dismissed"] == ""
