"""
ZH: 使用者端與管理端的登入 cookie 必須分開（v3.8）。

ZH: 🔴 來歷（2026-08-27 稽核）：兩端共用 `ai_hud_token`，而 **cookie 規格不區分 port**。
    `:80` 與 `:8888` 是同一個 host，所以**後登入的那一邊會覆蓋先登入的**。
    實測：擁有者在使用者端登入 `Lazy` 之後，管理端的 cookie 身分也變成 `Lazy`，
    管理端 API 開始回 403。

ZH: 為什麼當時沒有立刻爆掉：兩個 UI 都送 `Authorization: Bearer`。
    真正吃到影響的是**依賴 cookie 的路徑** —— 目前是 nginx 對 Lab `/code/`
    的 `auth_request`；而且 Bearer 過期時 `_extract_token` 會退回讀 cookie，
    那時身分就會變成「另一邊最後登入的人」。

ZH: 判斷來源靠 nginx 送的 `X-AIBase-Surface: admin`。
    **不能用 Host** —— nginx 傳的 `$host` 不含 port，兩個 server 區塊看起來一樣。
"""
import pytest

from app.auth import ADMIN_COOKIE, USER_COOKIE
from conftest import make_user


ADMIN_HDR = {"X-AIBase-Surface": "admin"}


@pytest.fixture
def two_users(db):
    make_user(db, username="stu", email="stu@example.com", role="student")
    make_user(db, username="adm", email="adm@example.com", role="admin")


def _login(client, username, headers=None):
    return client.post("/api/v1/auth/login",
                       data={"username": username, "password": "password123"},
                       headers=headers or {})


class TestCookieNamesAreSeparate:
    def test_the_two_names_differ(self):
        """ZH: 這條看起來廢話，但它釘住「不要有人為了省事又把兩個改成同一個」。"""
        assert USER_COOKIE != ADMIN_COOKIE

    def test_user_surface_sets_the_user_cookie(self, client, two_users):
        r = _login(client, "stu")
        assert r.status_code == 200, r.text
        assert USER_COOKIE in r.cookies, dict(r.cookies)
        assert ADMIN_COOKIE not in r.cookies

    def test_admin_surface_sets_the_admin_cookie(self, client, two_users):
        r = _login(client, "adm", ADMIN_HDR)
        assert r.status_code == 200, r.text
        assert ADMIN_COOKIE in r.cookies, dict(r.cookies)
        assert USER_COOKIE not in r.cookies


class TestLoggingInOnOneSurfaceDoesNotClobberTheOther:
    def test_user_login_does_not_change_the_admin_identity(self, client, two_users):
        """
        ZH: 🔴 這就是稽核當時實際發生的事，也是這整支測試存在的理由。
        """
        # 1) 管理端登入 → 拿到管理端 cookie
        r_adm = _login(client, "adm", ADMIN_HDR)
        admin_cookie = r_adm.cookies[ADMIN_COOKIE]

        # 2) 使用者端登入另一個人 → 只該動到使用者端那個
        r_stu = _login(client, "stu")
        assert USER_COOKIE in r_stu.cookies
        assert ADMIN_COOKIE not in r_stu.cookies, \
            "使用者端登入竟然動到管理端的 cookie —— 這正是要修的那個 bug"

        # 3) 帶著兩個 cookie 打 /auth/me：管理端表頭要認到 adm，沒有表頭要認到 stu
        jar = {USER_COOKIE: r_stu.cookies[USER_COOKIE], ADMIN_COOKIE: admin_cookie}
        as_admin = client.get("/api/v1/auth/me", cookies=jar, headers=ADMIN_HDR).json()
        as_user = client.get("/api/v1/auth/me", cookies=jar).json()
        assert as_admin["username"] == "adm", as_admin
        assert as_user["username"] == "stu", as_user

    def test_admin_logout_does_not_clear_the_user_cookie(self, client, two_users):
        """
        ZH: 反過來的錯同樣要擋：登出時若把名稱寫死，在管理端登出會清掉
            **使用者端**的 cookie 而留下自己的 —— 而且畫面上完全看不出來。
        """
        r_adm = _login(client, "adm", ADMIN_HDR)
        r_stu = _login(client, "stu")
        jar = {USER_COOKIE: r_stu.cookies[USER_COOKIE],
               ADMIN_COOKIE: r_adm.cookies[ADMIN_COOKIE]}

        out = client.post("/api/v1/auth/logout", cookies=jar, headers=ADMIN_HDR)
        assert out.status_code == 200, out.text
        # ZH: 被清掉的 cookie 會以 max-age=0 出現在 Set-Cookie 裡
        killed = out.headers.get("set-cookie", "")
        assert ADMIN_COOKIE in killed, f"沒有清掉管理端的 cookie：{killed}"
        assert USER_COOKIE not in killed, f"竟然清掉了使用者端的 cookie：{killed}"


class TestSurfaceDetection:
    """ZH: 判斷來源的規則本身。沒有表頭時一律當使用者端（直連 :8002 的走 Bearer）。"""

    @pytest.mark.parametrize("hdr,expected", [
        ({}, USER_COOKIE),
        ({"X-AIBase-Surface": "admin"}, ADMIN_COOKIE),
        ({"X-AIBase-Surface": "ADMIN"}, ADMIN_COOKIE),      # 大小寫不拘
        ({"X-AIBase-Surface": " admin "}, ADMIN_COOKIE),    # 前後空白
        ({"X-AIBase-Surface": "user"}, USER_COOKIE),
        ({"X-AIBase-Surface": ""}, USER_COOKIE),
    ])
    def test_cookie_name_for(self, hdr, expected):
        from app.auth import cookie_name_for

        class _Req:
            def __init__(self, h): self.headers = h
        assert cookie_name_for(_Req(hdr)) == expected

    def test_bearer_still_wins_over_any_cookie(self, client, two_users):
        """
        ZH: **陽性對照。** 上面那些如果是因為「cookie 根本沒被讀」而過，
            就證明不了什麼。這條確認 Bearer 仍然優先 ——
            那是兩個 UI 平常走的路徑，不能因為這次改動而變。
        """
        tok = _login(client, "adm", ADMIN_HDR).json()["access_token"]
        # ZH: 故意帶一個屬於別人的使用者端 cookie，Bearer 應該蓋過它
        stu_cookie = _login(client, "stu").cookies[USER_COOKIE]
        me = client.get("/api/v1/auth/me",
                        cookies={USER_COOKIE: stu_cookie},
                        headers={"Authorization": f"Bearer {tok}"}).json()
        assert me["username"] == "adm", me
