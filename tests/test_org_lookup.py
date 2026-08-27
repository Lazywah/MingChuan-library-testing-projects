"""
ZH: 組織對照（v3.8）—— 學系→學院、行政單位、校區。

ZH: 這支測試守的是**「不猜」與「不被種子蓋掉」**這兩件事:
    推不出學院時要回 None（塞一個錯的學院進去沒有人看得出來）,
    管理者改過的對照不能在下次重開機時被種子資料覆蓋。
"""
import pytest
from conftest import make_user

from app import crud, models, org_seed


class TestSeed:
    def test_seeds_an_empty_database(self, db):
        out = crud.seed_org_tables(db)
        assert out["departments"] == sum(len(v) for v in org_seed.COLLEGES.values())
        assert out["units"] == len(org_seed.UNITS)

    def test_second_run_changes_nothing(self, db):
        crud.seed_org_tables(db)
        assert crud.seed_org_tables(db) == {"departments": 0, "units": 0}

    def test_admin_edits_survive_a_reseed(self, db):
        """
        ZH: 🔴 這條是種子資料最容易出的錯:每次啟動都對齊種子的話,
            管理者改過的名字會在下次重開時**安靜地**被蓋回去。
        """
        crud.seed_org_tables(db)
        row = db.query(models.OrgDepartment).filter_by(name="資訊工程學系").first()
        row.college = "我改過的學院"
        db.commit()

        crud.seed_org_tables(db)          # ZH: 模擬重開機
        again = db.query(models.OrgDepartment).filter_by(name="資訊工程學系").first()
        assert again.college == "我改過的學院"

    def test_duplicate_unit_names_are_kept_apart_by_path(self, db):
        """ZH: 官網底下真的有兩個「事務組」與兩個「處長室」。"""
        crud.seed_org_tables(db)
        paths = sorted(u.path for u in
                       db.query(models.OrgUnit).filter_by(name="事務組").all())
        assert paths == ["總務處/事務組", "金門分部/事務組"]
        assert len(db.query(models.OrgUnit).filter_by(name="處長室").all()) == 2

    def test_every_unit_parent_actually_exists(self, db):
        """ZH: 上層打錯的話那個單位會從樹狀選單裡消失,而畫面上看不出來。"""
        crud.seed_org_tables(db)
        names = {u.name for u in db.query(models.OrgUnit).all()}
        parents = {u.parent for u in db.query(models.OrgUnit).all() if u.parent}
        assert parents <= names


class TestCollegeDerivation:
    def test_known_department(self, db):
        crud.seed_org_tables(db)
        assert crud.college_of(db, "資訊工程學系") == "電機資訊學院"

    @pytest.mark.parametrize("value", [None, "", "   ", "外星人學系", "資訊學院"])
    def test_unknown_returns_none_and_does_not_guess(self, db, value):
        """
        ZH: 查不到是正常情況(舊系名、錯字、沒填),不是錯誤。
            回 None 讓呼叫端顯示「未分類」—— 硬塞一個學院進去沒有人看得出來錯了。
            `資訊學院` 特別列進來:那是 2023 年的舊學院名,現在叫電機資訊學院。
        """
        crud.seed_org_tables(db)
        assert crud.college_of(db, value) is None

    def test_whitespace_is_tolerated(self, db):
        crud.seed_org_tables(db)
        assert crud.college_of(db, "  資訊工程學系  ") == "電機資訊學院"


class TestOrgOptions:
    def test_shape(self, db):
        crud.seed_org_tables(db)
        opts = crud.org_options(db)
        assert opts["campuses"] == org_seed.CAMPUSES
        assert len(opts["departments"]) == 51
        assert len(opts["units"]) == 97
        assert all({"name", "college", "campus"} <= set(d) for d in opts["departments"])

    def test_inactive_rows_are_hidden(self, db):
        """ZH: 停招的系留在表裡（舊資料還指著它），但不進下拉。"""
        crud.seed_org_tables(db)
        row = db.query(models.OrgDepartment).filter_by(name="資訊工程學系").first()
        row.active = 0
        db.commit()
        names = [d["name"] for d in crud.org_options(db)["departments"]]
        assert "資訊工程學系" not in names
        # ZH: 但推導仍然要通 —— 還沒轉系的人不該變成「未分類」。
        assert crud.college_of(db, "資訊工程學系") == "電機資訊學院"

    def test_campus_is_not_guessed(self, db):
        """
        ZH: 種子資料的校區一律留空 —— 官網教學單位頁沒有標校區,
            唯一找得到的校區分布用的是已經不存在的舊學院名。
            由管理者選(擁有者裁定 2026-08-27)。
        """
        crud.seed_org_tables(db)
        assert all(d["campus"] is None for d in crud.org_options(db)["departments"])


class TestUserColumns:
    def test_unit_is_storable(self, db):
        user = make_user(db)
        user.unit = "資訊網路處/桃園資訊服務組"
        db.commit()
        db.refresh(user)
        assert user.unit == "資訊網路處/桃園資訊服務組"

    def test_college_is_not_a_user_column(self):
        """ZH: 學院刻意不存進 users —— 改對照表要全站生效,不必回填幾千筆。"""
        assert "college" not in models.User.__table__.columns

    def test_campus_is_not_a_user_column_either(self):
        """
        ZH: campus 一開始是 users 的單一欄位,同一天改成 user_campuses 關聯表 ——
            教職員可以同時在台北與桃園有課,單一欄位表達不了。
            這條釘住「不要再加回去」:兩個地方都存校區就會漂開。
        """
        assert "campus" not in models.User.__table__.columns


class TestUserCampuses:
    def test_student_is_limited_to_one(self, db):
        user = make_user(db, role="student")
        with pytest.raises(ValueError) as e:
            crud.set_user_campuses(db, user, ["台北", "桃園"])
        assert "學生" in str(e.value)

    def test_student_may_have_exactly_one(self, db):
        user = make_user(db, role="student")
        assert crud.set_user_campuses(db, user, ["桃園"]) == ["桃園"]

    def test_staff_may_have_several(self, db):
        """ZH: 教職員同時在台北與桃園有課是常態,這是改成關聯表的理由。"""
        user = make_user(db, username="s1", email="s1@example.com", role="staff")
        assert crud.set_user_campuses(db, user, ["桃園", "台北"]) == ["台北", "桃園"]

    def test_order_follows_the_canonical_list_not_insertion(self, db):
        """ZH: 顯示順序要穩定,否則同一個人在不同頁面上的校區順序會不一樣。"""
        user = make_user(db, username="s2", email="s2@example.com", role="teacher")
        assert crud.set_user_campuses(db, user, ["美國分校", "台北", "金門"]) ==             ["台北", "金門", "美國分校"]

    def test_unknown_campus_is_rejected(self, db):
        """ZH: 打錯的校區名存進去,分組統計會多出一個沒人看得懂的類別而且不報錯。"""
        user = make_user(db, username="s3", email="s3@example.com", role="teacher")
        with pytest.raises(ValueError):
            crud.set_user_campuses(db, user, ["台中"])

    def test_setting_replaces_rather_than_appends(self, db):
        user = make_user(db, username="s4", email="s4@example.com", role="teacher")
        crud.set_user_campuses(db, user, ["台北", "桃園"])
        assert crud.set_user_campuses(db, user, ["金門"]) == ["金門"]

    def test_duplicates_in_the_input_are_collapsed(self, db):
        user = make_user(db, username="s5", email="s5@example.com", role="student")
        assert crud.set_user_campuses(db, user, ["台北", "台北"]) == ["台北"]

    def test_empty_clears(self, db):
        user = make_user(db, username="s6", email="s6@example.com", role="teacher")
        crud.set_user_campuses(db, user, ["台北"])
        assert crud.set_user_campuses(db, user, []) == []
