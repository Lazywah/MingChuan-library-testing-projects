"""
ZH: v3.5 介面偏好（字級 / 語言）—— **跟帳號走，不是跟裝置走**。
EN: v3.5 per-account UI preferences (font scale / language).

ZH: 這一支守的重點是「跟帳號走」這個承諾本身：
    偏好必須在 /auth/me 回得到（前端才不必多一次往返），
    而且必須是**每個帳號各自一份**——共用一份的話在共用機台上會互相蓋掉。
"""
from conftest import auth_headers, make_user


def test_defaults_are_zh_and_100(client, db):
    make_user(db)
    h = auth_headers(client)
    me = client.get("/api/v1/auth/me", headers=h).json()
    assert me["ui_font_scale"] == 100
    assert me["ui_lang"] == "zh"
    assert me["ui_theme"] == "yellow"


def test_update_and_read_back(client, db):
    make_user(db)
    h = auth_headers(client)

    r = client.patch("/api/v1/auth/me/preferences",
                     json={"ui_font_scale": 130, "ui_lang": "en"}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["ui_font_scale"] == 130
    assert r.json()["ui_lang"] == "en"

    # ZH: 重點是**下一次登入**（新 token）拿到的還是這一份——那才是「跟帳號走」。
    me = client.get("/api/v1/auth/me", headers=auth_headers(client)).json()
    assert (me["ui_font_scale"], me["ui_lang"]) == (130, "en")


def test_partial_update_keeps_the_other(client, db):
    """ZH: 兩個欄位都可選。只改語言不該把字級洗回 100。"""
    make_user(db)
    h = auth_headers(client)
    client.patch("/api/v1/auth/me/preferences", json={"ui_font_scale": 120}, headers=h)
    out = client.patch("/api/v1/auth/me/preferences", json={"ui_lang": "en"},
                       headers=h).json()
    assert out["ui_font_scale"] == 120
    assert out["ui_lang"] == "en"


def test_each_account_has_its_own(client, db):
    """ZH: 共用機台上兩個人輪流用同一台。偏好共用一份就會互相蓋掉。"""
    make_user(db, username="alice", email="a@example.com")
    make_user(db, username="bob", email="b@example.com")
    ha, hb = auth_headers(client, "alice"), auth_headers(client, "bob")

    client.patch("/api/v1/auth/me/preferences",
                 json={"ui_font_scale": 150, "ui_lang": "en"}, headers=ha)

    bob = client.get("/api/v1/auth/me", headers=hb).json()
    assert (bob["ui_font_scale"], bob["ui_lang"]) == (100, "zh"), "bob 的偏好被 alice 蓋掉了"
    alice = client.get("/api/v1/auth/me", headers=ha).json()
    assert (alice["ui_font_scale"], alice["ui_lang"]) == (150, "en")


def test_out_of_range_font_scale_rejected(client, db):
    """ZH: 範圍 80–150。不擋的話 300% 會把版面撐爛，而使用者自己改不回來
    （設定介面本身也被撐爛了）。"""
    make_user(db)
    h = auth_headers(client)
    for bad in (0, 79, 151, 1000, -20):
        r = client.patch("/api/v1/auth/me/preferences",
                         json={"ui_font_scale": bad}, headers=h)
        assert r.status_code == 422, f"{bad} 沒有被擋下"


def test_unknown_language_rejected(client, db):
    make_user(db)
    h = auth_headers(client)
    assert client.patch("/api/v1/auth/me/preferences",
                        json={"ui_lang": "jp"}, headers=h).status_code == 422


def test_anonymous_cannot_change(client, db):
    assert client.patch("/api/v1/auth/me/preferences",
                        json={"ui_lang": "en"}).status_code in (401, 403)


def test_boundaries_accepted(client, db):
    """ZH: 反向守門——80 與 150 是合法的，別把邊界一起擋掉。"""
    make_user(db)
    h = auth_headers(client)
    for ok in (80, 150):
        r = client.patch("/api/v1/auth/me/preferences",
                         json={"ui_font_scale": ok}, headers=h)
        assert r.status_code == 200, f"{ok} 被誤擋"


def test_theme_follows_the_account(client, db):
    """ZH: 色系原本九個頁面各寫一份切換處理，**只有首頁那份會存與還原**——
    症狀是「有些頁面換了顏色，其他頁面還沒變」。現在跟字級／語言同一條路。
    """
    make_user(db)
    h = auth_headers(client)
    out = client.patch("/api/v1/auth/me/preferences", json={"ui_theme": "blue"},
                       headers=h).json()
    assert out["ui_theme"] == "blue"
    assert client.get("/api/v1/auth/me", headers=auth_headers(client)).json()["ui_theme"] == "blue"


def test_unknown_theme_rejected(client, db):
    make_user(db)
    h = auth_headers(client)
    assert client.patch("/api/v1/auth/me/preferences", json={"ui_theme": "pink"},
                        headers=h).status_code == 422


def test_theme_partial_update_keeps_others(client, db):
    """ZH: 三個欄位都可選——只改色系不該把字級或語言洗掉。"""
    make_user(db)
    h = auth_headers(client)
    client.patch("/api/v1/auth/me/preferences",
                 json={"ui_font_scale": 130, "ui_lang": "en"}, headers=h)
    out = client.patch("/api/v1/auth/me/preferences", json={"ui_theme": "blue"},
                       headers=h).json()
    assert (out["ui_font_scale"], out["ui_lang"], out["ui_theme"]) == (130, "en", "blue")
