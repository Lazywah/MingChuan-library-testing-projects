"""
ZH: 依信箱網域自動判角色（v3.8，擁有者裁定 2026-08-27）。

ZH: 🔴 這支測試存在的理由：判定的輸入是**我們自己組出來的信箱**,不是學校給的。
    MCU 的 userinfo 只回 {"sub": 學號},email 是依 sub 的長相推的
    （8 碼純數字→學生網域,英文開頭→教職員網域）。
    所以真實規則是「sub 開頭是英文字母就給 teacher」——
    這件事必須被測試寫下來,不然下一個人會以為學校真的給了身分。
"""
import pytest
from conftest import make_user

from app import crud, models
from app.routers.sso import _finalize_sso_login


class TestTheRule:
    @pytest.mark.parametrize("email,expected", [
        ("12361114@me.mcu.edu.tw", "student"),
        ("someone@mail.mcu.edu.tw", "teacher"),
    ])
    def test_known_domains(self, email, expected):
        assert crud.role_from_email(email) == expected

    @pytest.mark.parametrize("email", [
        "someone@gmail.com", "b@yahoo.com.tw", "c@hotmail.com",
        "d@some-company.co.jp", "e@mcu.edu.tw",
    ])
    def test_external_domains_are_guests(self, email):
        """
        ZH: 訪客（擁有者 2026-08-27 追加）。

        ZH: 🔴 **刻意不用「已知公開信箱清單」判定。** 列 gmail/yahoo/outlook 那種清單
            一定會過期 —— 漏掉一個 hotmail,那個人就會被當成校內學生。
            改成反過來問「它是不是校內網域」,所以 hotmail 與任何沒見過的網域
            （含 some-company.co.jp）都自動落到訪客。

        ZH: `e@mcu.edu.tw` 特別列進來:那是學校主網域但**不在** email_rules 裡
            （規則只有 me. 與 mail. 兩個子網域）,所以它也是訪客。
            要改的話是加進 sso_policy.yaml,不是在程式裡特判。
        """
        assert crud.role_from_email(email) == "guest"

    def test_a_lookalike_domain_is_not_elevated(self):
        """ZH: 網域比對必須**完整相等**不是「包含」—— 這種東西絕不能拿到 teacher。"""
        assert crud.role_from_email("x@MAIL.MCU.EDU.TW.evil.com") == "guest"

    @pytest.mark.parametrize("email", [
        None, "", "   ", "12361114@unknown", "no-at-sign",
    ])
    def test_no_usable_address_falls_back_to_student(self, email):
        """
        ZH: **沒有地址**（SSO 推不出信箱）給 student 而不是 guest ——
            那個人是走學校 SSO 進來的,他就是校內的人,只是我們推不出他的信箱。
            判成訪客會把真實學生鎖在較低權限,而且他不知道為什麼。

        ZH: ⚠️ 這一條是實作時的判斷,不是擁有者明講的。
        """
        assert crud.role_from_email(email) == "student"

    def test_admin_and_staff_are_never_assigned_automatically(self):
        """ZH: admin 與 staff 一律手動。任何信箱都不該推出這兩個。"""
        for e in ["admin@mail.mcu.edu.tw", "root@me.mcu.edu.tw",
                  "a@mcu.edu.tw", "b@gmail.com", "", None]:
            assert crud.role_from_email(e) not in ("admin", "staff")

    def test_guest_account_records_its_source_too(self, db):
        """ZH: 訪客也要記來源 —— 複查時要分得出「自動判成訪客」與「管理者設的」。"""
        from app.routers.sso import _finalize_sso_login
        _finalize_sso_login(db, {"username": "guest01", "email": "guest01@gmail.com",
                                 "role": "student", "auth_source": "sso_oidc",
                                 "external_id": "guest01"})
        u = crud.get_user_by_username(db, "guest01")
        assert (u.role, u.role_source) == ("guest", "sso_email")

    def test_the_yaml_label_staff_maps_to_the_role_teacher(self):
        """
        ZH: 命名陷阱釘樁:sso_policy.yaml 的 label `"staff"` 意思是「教職員」,
            而平台的 role `"staff"` 指的是「職員」—— 兩者同名但不同義。
            擁有者裁定教職員網域先給 teacher,所以這個對應**刻意不是同名對同名**。
        """
        from app.services.myai_sync import classify_email
        assert classify_email("someone@mail.mcu.edu.tw")["label"] == "staff"
        assert crud.role_from_email("someone@mail.mcu.edu.tw") == "teacher"


class TestRoleSourceIsRecorded:
    def _login(self, db, sub, email):
        return _finalize_sso_login(db, {
            "username": sub, "email": email, "role": "student",
            "auth_source": "sso_oidc", "external_id": sub,
        })

    def test_new_sso_account_records_that_it_was_automatic(self, db):
        """
        ZH: **陽性對照。** 現有帳號的 role_source 全是 None,而「欄位永遠是 None」
            正是 v3.6 踩過兩次的坑（schema 加了但手工建構處沒加）。
            這條證明真的走過建帳號之後它會有值。
        """
        self._login(db, "aateacher", "aateacher@mail.mcu.edu.tw")
        u = crud.get_user_by_username(db, "aateacher")
        assert u.role == "teacher"
        assert u.role_source == "sso_email"

    def test_student_path_too(self, db):
        self._login(db, "12361114", "12361114@me.mcu.edu.tw")
        u = crud.get_user_by_username(db, "12361114")
        assert (u.role, u.role_source) == ("student", "sso_email")

    def test_existing_account_is_not_re_evaluated(self, db):
        """
        ZH: 規則只在**建帳號時**套用。已經存在的帳號不重判 ——
            管理者手動調整過的角色不能在下次登入時被自動判定蓋掉。
        """
        user = make_user(db, username="olduser", email="olduser@mail.mcu.edu.tw")
        user.role = "student"
        user.role_source = "admin"
        user.auth_source = "sso_oidc"
        db.commit()

        self._login(db, "olduser", "olduser@mail.mcu.edu.tw")
        db.refresh(user)
        assert user.role == "student", "既有帳號的角色被自動判定蓋掉了"
        assert user.role_source == "admin"


class TestAdminOverrideMarksItManual:
    def test_changing_role_flips_the_source(self, client, db):
        """ZH: 管理者確認過就不該再出現在複查清單裡。"""
        from conftest import auth_headers
        admin = make_user(db, username="adm", email="adm@example.com", role="admin")
        target = make_user(db, username="tgt", email="tgt@example.com")
        target.role_source = "sso_email"
        db.commit()

        resp = client.put(f"/api/v1/admin/users/{target.id}",
                          json={"role": "teacher"},
                          headers=auth_headers(client, "adm", "password123"))
        assert resp.status_code == 200, resp.text
        db.refresh(target)
        assert (target.role, target.role_source) == ("teacher", "admin")
