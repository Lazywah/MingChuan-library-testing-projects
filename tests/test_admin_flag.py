"""
ZH: 身分（role）與管理權限（is_admin）拆開（v3.8，擁有者裁定 2026-08-27）。

ZH: 擁有者的要求只有一句：「只要使用者不能自己上管理員就好」。
    所以這支測試的主軸就是那件事,其餘是拆開後的行為釘樁。
"""
import pytest
from conftest import make_user, auth_headers

from app import models, schemas


class TestUsersCannotGrantThemselvesAdmin:
    def test_the_user_facing_schema_cannot_even_express_it(self):
        """
        ZH: 🔴 **第一道也是最強的一道防線在型別層**：使用者端的 UserUpdate
            根本沒有 is_admin 這個欄位,所以 PUT /auth/me 表達不出它。

        ZH: 這條測試釘住的是「不要為了方便把兩份 schema 合成一份」——
            合了之後,擋提權就只剩執行期的 if,而那種 if 會在重構時消失。
        """
        assert "is_admin" not in schemas.UserUpdate.model_fields
        assert "role" not in schemas.UserUpdate.model_fields
        # ZH: 管理端那份才有
        assert "is_admin" in schemas.AdminUserUpdate.model_fields

    def test_put_me_with_is_admin_is_silently_ignored(self, client, db):
        """
        ZH: **實際打一次。** 型別層擋掉之後,多送的欄位會被 pydantic 丟掉,
            不是 400 —— 所以要驗的是「送了也沒用」,不是「會報錯」。
        """
        user = make_user(db)
        assert user.is_admin == 0
        r = client.put("/api/v1/auth/me",
                       json={"email": "x@example.com", "is_admin": 1, "role": "admin"},
                       headers=auth_headers(client))
        assert r.status_code == 200, r.text
        db.refresh(user)
        assert user.is_admin == 0, "🔴 使用者自己把自己升成管理員了"
        assert user.role == "student", "🔴 使用者自己改了角色"

    def test_onboarding_cannot_grant_it_either(self, client, db):
        """ZH: 初次設定彈窗是使用者自己送的,同樣不能是後門。"""
        from app import crud
        crud.seed_org_tables(db)
        user = make_user(db)
        r = client.post("/api/v1/system/onboarding",
                        json={"campuses": ["台北"], "org_value": "資訊工程學系",
                              "is_admin": 1, "role": "admin"},
                        headers=auth_headers(client))
        assert r.status_code == 200, r.text
        db.refresh(user)
        assert (user.is_admin, user.role) == (0, "student")

    def test_sso_never_grants_it(self, db):
        """ZH: 自動判定只給 student/teacher/guest,不給管理權限。"""
        from app.routers.sso import _finalize_sso_login
        from app import crud
        _finalize_sso_login(db, {"username": "t9", "email": "t9@mail.mcu.edu.tw",
                                 "role": "student", "auth_source": "sso_oidc",
                                 "external_id": "t9"})
        u = crud.get_user_by_username(db, "t9")
        assert (u.role, u.is_admin) == ("teacher", 0)


class TestGateUsesTheFlag:
    def test_role_admin_without_the_flag_is_refused(self, client, db):
        """
        ZH: **陽性對照的另一半。** 舊的判定是 `role == "admin"`,
            所以一個 role=admin 但沒有旗標的帳號,在舊實作下會通過。
            這條證明判定真的換成旗標了。
        """
        u = make_user(db, username="fake", email="fake@example.com", role="admin")
        u.is_admin = 0
        db.commit()
        r = client.get("/api/v1/admin/users",
                       headers=auth_headers(client, "fake", "password123"))
        assert r.status_code == 403

    def test_student_with_the_flag_is_allowed(self, client, db):
        """ZH: 這就是擁有者要的:身分是學生,但有管理權限。"""
        u = make_user(db, username="devstudent", email="dev@example.com", role="student")
        u.is_admin = 1
        db.commit()
        r = client.get("/api/v1/admin/users",
                       headers=auth_headers(client, "devstudent", "password123"))
        assert r.status_code == 200, r.text

    def test_revoking_takes_effect_immediately(self, client, db):
        """ZH: 判定讀資料庫不是讀 JWT,所以取消權限不必等舊 token 過期。"""
        u = make_user(db, username="tmpadm", email="tmpadm@example.com")
        u.is_admin = 1
        db.commit()
        h = auth_headers(client, "tmpadm", "password123")
        assert client.get("/api/v1/admin/users", headers=h).status_code == 200
        u.is_admin = 0
        db.commit()
        assert client.get("/api/v1/admin/users", headers=h).status_code == 403


class TestAdminCanSetIt:
    def test_admin_grants_and_revokes(self, client, db):
        adm = make_user(db, username="a1", email="a1@example.com", role="staff")
        adm.is_admin = 1
        db.commit()
        target = make_user(db, username="t1", email="t1@example.com")
        h = auth_headers(client, "a1", "password123")

        assert client.put(f"/api/v1/admin/users/{target.id}",
                          json={"is_admin": 1}, headers=h).status_code == 200
        db.refresh(target)
        assert target.is_admin == 1
        assert target.role == "student", "設管理權限不該動到身分"

        client.put(f"/api/v1/admin/users/{target.id}", json={"is_admin": 0}, headers=h)
        db.refresh(target)
        assert target.is_admin == 0


class TestOnlyOneGate:
    def test_there_is_a_single_require_admin_implementation(self):
        """
        ZH: v3.8 之前全站有**三份** require_admin 的複製實作（admin / external_ai
            各一份,assistant 還有一段行內的）,三份都寫 `role == "admin"` ——
            拆開身分與權限時要改三個地方才算改完,而漏掉一個不會有任何症狀,
            只會留下一個仍用舊判準的入口。
        """
        import pathlib, io as _io
        root = pathlib.Path(__file__).resolve().parents[1] / "job-scheduler" / "app"
        defs = []
        for f in root.rglob("*.py"):
            for i, line in enumerate(_io.open(f, encoding="utf-8"), 1):
                if line.startswith("def require_admin("):
                    defs.append(f"{f.name}:{i}")
        assert defs == ["auth.py:193"] or len(defs) == 1, f"不只一份: {defs}"


class TestAdminCreationPathsGrantTheFlag:
    """
    ZH: 🔴 拆開身分與權限時,我**差點漏掉建立管理員的兩條路**。
        兩條漏掉的後果都是「鎖死而且沒有救援」：

          main.py 的開機自動建立 —— 全新部署的第一個管理員進不去管理端
          create-admin.bat      —— 那是「忘記密碼／所有管理員都被刪掉」的救援腳本

        症狀是登入後只顯示「這個帳號不是管理員」,完全看不出是建帳號時漏設旗標。
        是全套測試 66 個失敗把這件事炸出來的,不是我自己想到的。
    """

    def _read(self, *parts):
        import pathlib, io as _io
        return _io.open(pathlib.Path(__file__).resolve().parents[1].joinpath(*parts),
                        encoding="utf-8", errors="replace").read()

    def test_bootstrap_admin_gets_the_flag(self):
        src = self._read("job-scheduler", "app", "main.py")
        i = src.index('username="admin"')
        block = src[i:i + 600]
        assert "is_admin=1" in block, (
            "main.py 開機自動建立的管理員沒有設 is_admin —— 全新部署會進不去管理端"
        )

    def test_rescue_script_grants_the_flag(self):
        src = self._read("scripts", "create-admin.bat")
        assert "is_admin=1" in src, (
            "create-admin.bat 沒有設 is_admin —— 這是所有管理員都被刪掉時的救援路徑，"
            "它失效等於鎖死之後沒有救援"
        )
