"""
ZH: 初次登入設定（v3.8）—— 新帳號第一次登入時收校區與學系／行政單位。

ZH: 擁有者裁定：只對**新帳號**跳，現有帳號不跳（回填成已完成）。
"""
import pytest
from conftest import make_user, auth_headers

from app import crud, models


class TestWhoIsAskedWhat:
    @pytest.mark.parametrize("role,field", [
        ("student", "department"),
        ("teacher", "department"),
        ("staff", "unit"),
        ("admin", "unit"),
        ("guest", None),
    ])
    def test_field_by_role(self, role, field):
        """
        ZH: 擁有者只指定了「學生問學系、職員問行政單位」。
            teacher→學系、admin→行政單位、guest→只問校區 是實作時的判斷。

        ZH: 訪客刻意不問組織欄位 —— 他不屬於任何系所或單位,硬問只會逼他亂填,
            而亂填的資料會污染分組統計而且看不出來。
        """
        assert crud.onboarding_spec(role)["org_field"] == field

    def test_campus_is_always_asked(self):
        for r in ["student", "teacher", "staff", "admin", "guest"]:
            assert crud.onboarding_spec(r)["campus"] is True


class TestCompletion:
    def test_student_completes(self, db):
        crud.seed_org_tables(db)
        u = make_user(db)
        crud.complete_onboarding(db, u, ["桃園"], "資訊工程學系")
        assert u.onboarded_at is not None
        assert u.department == "資訊工程學系"
        assert crud.campuses_of(db, u.id) == ["桃園"]

    def test_staff_stores_a_unit_path_not_a_name(self, db):
        """ZH: 單位有撞名（兩個「事務組」）,所以存的是路徑。"""
        crud.seed_org_tables(db)
        u = make_user(db, username="st", email="st@example.com", role="staff")
        crud.complete_onboarding(db, u, ["台北", "桃園"], "總務處/事務組")
        assert u.unit == "總務處/事務組"
        assert crud.campuses_of(db, u.id) == ["台北", "桃園"]

    def test_guest_needs_only_a_campus(self, db):
        crud.seed_org_tables(db)
        u = make_user(db, username="g", email="g@example.com", role="guest")
        crud.complete_onboarding(db, u, ["台北"], None)
        assert u.onboarded_at is not None
        assert (u.department, u.unit) == (None, None)

    def test_campus_is_mandatory(self, db):
        crud.seed_org_tables(db)
        u = make_user(db)
        with pytest.raises(ValueError, match="校區"):
            crud.complete_onboarding(db, u, [], "資訊工程學系")
        assert u.onboarded_at is None, "驗證失敗卻標成已完成 —— 之後再也不會問他"

    def test_org_field_is_mandatory_when_it_applies(self, db):
        crud.seed_org_tables(db)
        u = make_user(db)
        with pytest.raises(ValueError, match="學系"):
            crud.complete_onboarding(db, u, ["台北"], "")
        assert u.onboarded_at is None

    @pytest.mark.parametrize("bad", ["外星人學系", "資訊學院", "  "])
    def test_free_text_departments_are_rejected(self, db, bad):
        """ZH: 自由文字會讓分組統計長出一堆打錯字的類別,而且不會報錯。"""
        crud.seed_org_tables(db)
        u = make_user(db)
        with pytest.raises(ValueError):
            crud.complete_onboarding(db, u, ["台北"], bad)

    def test_student_still_cannot_pick_two_campuses(self, db):
        """ZH: 彈窗不是繞過規則的後門 —— 走的是同一支 set_user_campuses。"""
        crud.seed_org_tables(db)
        u = make_user(db)
        with pytest.raises(ValueError, match="學生"):
            crud.complete_onboarding(db, u, ["台北", "桃園"], "資訊工程學系")


class TestEndpoint:
    def test_requires_login(self, client):
        assert client.post("/api/v1/system/onboarding", json={}).status_code == 401

    def test_round_trip(self, client, db):
        crud.seed_org_tables(db)
        make_user(db)
        r = client.post("/api/v1/system/onboarding",
                        json={"campuses": ["台北"], "org_value": "資訊工程學系"},
                        headers=auth_headers(client))
        assert r.status_code == 200, r.text
        assert r.json()["campuses"] == ["台北"]

    def test_validation_error_reaches_the_user(self, client, db):
        """ZH: 訊息是給人看的,不能只回 400 —— 使用者要知道該補什麼。"""
        crud.seed_org_tables(db)
        make_user(db)
        r = client.post("/api/v1/system/onboarding",
                        json={"campuses": [], "org_value": "資訊工程學系"},
                        headers=auth_headers(client))
        assert r.status_code == 400
        assert "校區" in r.json()["detail"]

    def test_me_reports_onboarding_state_and_campuses(self, client, db):
        """
        ZH: 🔴 `campuses` 來自關聯表,不是 users 的欄位 —— 直接回 ORM 物件的話
            pydantic 找不到那個屬性,會**靜靜地永遠回空陣列**。
            這條就是釘住那件事:設定過之後它必須有值。
        """
        crud.seed_org_tables(db)
        make_user(db)
        h = auth_headers(client)
        before = client.get("/api/v1/auth/me", headers=h).json()
        assert before["onboarded_at"] is None and before["campuses"] == []

        client.post("/api/v1/system/onboarding",
                    json={"campuses": ["金門"], "org_value": "資訊工程學系"}, headers=h)
        after = client.get("/api/v1/auth/me", headers=h).json()
        assert after["onboarded_at"] is not None
        assert after["campuses"] == ["金門"], "關聯表的值沒有被填進 /auth/me"
