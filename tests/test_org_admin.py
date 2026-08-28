"""
ZH: 組織對照表的管理端編輯（v3.8）。

ZH: 這一支釘的重點只有一個：**主鍵就是使用者存的那個字串**
    （`users.department` 存系名、`users.unit` 存 `org_units.path`），
    而且**沒有外鍵**。所以動到主鍵的操作都有同一個失敗模式 ——
    填過舊值的人不會報錯，他們只是**從分組統計裡消失**，沒有人會發現。

ZH: 因此兩件事要被釘死：
      1. 改名時使用者要一起搬（而且回報搬了幾個）。
      2. 沒有刪除端點，只能停用。
"""
import pytest

from app import models
from conftest import make_user, auth_headers


@pytest.fixture
def adm(client, db):
    make_user(db, username="orgadmin", email="orgadmin@example.com", role="admin")
    return auth_headers(client, "orgadmin", "password123")


@pytest.fixture
def seeded(db):
    """ZH: 兩個系、一個單位，外加一個填了系的使用者。"""
    db.add(models.OrgDepartment(name="資訊工程學系", college="資訊學院", campus=None, active=1))
    db.add(models.OrgDepartment(name="會計學系", college="管理學院", campus=None, active=1))
    db.add(models.OrgUnit(path="總務處/事務組", name="事務組", parent="總務處",
                          campus=None, active=1))
    u = make_user(db, username="stu1", email="stu1@example.com", role="student")
    u.department = "資訊工程學系"
    db.commit()
    return u


# ── 讀取 ────────────────────────────────────────────────────────────────
class TestListing:
    def test_departments_carry_the_head_count(self, client, adm, seeded):
        """
        ZH: 人數要跟著出來 —— 停用或改名之前，管理者要看得到影響範圍。
            沒有這個數字的話，那兩個操作等於閉著眼睛按。
        """
        d = client.get("/api/v1/admin/org/departments", headers=adm).json()
        by = {r["name"]: r for r in d["rows"]}
        assert by["資訊工程學系"]["users"] == 1
        assert by["會計學系"]["users"] == 0

    def test_units_count_by_path_not_name(self, client, db, adm, seeded):
        """
        ZH: 🔴 官網底下有兩個「事務組」，所以人數一定要用 path 比對。
            用 name 比對的話，兩個同名單位的人數會互相汙染。
        """
        other = make_user(db, username="stf1", email="stf1@example.com", role="staff")
        other.unit = "總務處/事務組"
        db.add(models.OrgUnit(path="金門分部/事務組", name="事務組", parent="金門分部",
                              campus=None, active=1))
        db.commit()
        rows = {r["path"]: r for r in
                client.get("/api/v1/admin/org/units", headers=adm).json()["rows"]}
        assert rows["總務處/事務組"]["users"] == 1
        assert rows["金門分部/事務組"]["users"] == 0, "同名不同路徑的單位人數被算在一起了"

    def test_non_admin_is_refused(self, client, db, seeded):
        make_user(db, username="plain", email="plain@example.com", role="student")
        h = auth_headers(client, "plain", "password123")
        assert client.get("/api/v1/admin/org/departments", headers=h).status_code == 403


# ── 改名連動 ────────────────────────────────────────────────────────────
class TestRenameMovesUsers:
    def test_renaming_a_department_moves_its_users(self, client, db, adm, seeded):
        """
        ZH: 🔴 這支測試是整個檔案存在的理由。
            不連動的話，那個學生的 `department` 還指著舊名字，
            而舊名字已經不在對照表裡 —— 他從此不屬於任何學院，
            **畫面上不會有任何錯誤**。
        """
        r = client.put("/api/v1/admin/org/departments", headers=adm, json={"rows": [
            {"key": "資訊工程學系", "name": "資訊工程學系（改）",
             "college": "資訊學院", "campus": "桃園", "active": 1},
        ]})
        assert r.status_code == 200, r.text
        assert r.json()["renamed"] == 1
        assert r.json()["moved_users"] == 1, "改名了卻沒有搬動使用者"

        db.expire_all()
        assert db.get(models.User, seeded.id).department == "資訊工程學系（改）"
        assert db.get(models.OrgDepartment, "資訊工程學系") is None
        assert db.get(models.OrgDepartment, "資訊工程學系（改）") is not None

    def test_renaming_a_unit_moves_its_users(self, client, db, adm, seeded):
        """ZH: 單位改名要換 path，使用者存的也是 path。"""
        s = make_user(db, username="stf2", email="stf2@example.com", role="staff")
        s.unit = "總務處/事務組"
        db.commit()
        r = client.put("/api/v1/admin/org/units", headers=adm, json={"rows": [
            {"key": "總務處/事務組", "name": "庶務組", "parent": "總務處",
             "campus": None, "active": 1},
        ]})
        assert r.status_code == 200, r.text
        assert r.json()["moved_users"] == 1
        db.expire_all()
        assert db.get(models.User, s.id).unit == "總務處/庶務組"

    def test_rename_onto_an_existing_name_is_refused(self, client, adm, seeded):
        """
        ZH: **陽性對照**：上面兩條若是因為「改名根本沒生效」而過，
            這一條會抓到 —— 撞名必須被擋下，而不是安靜地合併兩個系。
        """
        r = client.put("/api/v1/admin/org/departments", headers=adm, json={"rows": [
            {"key": "資訊工程學系", "name": "會計學系",
             "college": "資訊學院", "campus": None, "active": 1},
        ]})
        assert r.status_code == 409, r.text


# ── 編輯與新增 ──────────────────────────────────────────────────────────
class TestEditAndAdd:
    def test_setting_campus_does_not_touch_users(self, client, db, adm, seeded):
        """ZH: 學院與校區是**推導**出來的，不存在 users 上 —— 改它不該動到任何人。"""
        r = client.put("/api/v1/admin/org/departments", headers=adm, json={"rows": [
            {"key": "資訊工程學系", "name": "資訊工程學系",
             "college": "資訊學院", "campus": "桃園", "active": 1},
        ]})
        assert r.status_code == 200, r.text
        assert r.json() == {"added": 0, "updated": 1, "renamed": 0, "moved_users": 0}
        db.expire_all()
        assert db.get(models.OrgDepartment, "資訊工程學系").campus == "桃園"
        assert db.get(models.User, seeded.id).department == "資訊工程學系"

    def test_unchanged_row_is_not_counted(self, client, adm, seeded):
        """
        ZH: **陽性對照**：全部照原樣送回去，`updated` 必須是 0。
            否則上面那條的「updated == 1」只是「每一列都算一次」而已。
        """
        r = client.put("/api/v1/admin/org/departments", headers=adm, json={"rows": [
            {"key": "會計學系", "name": "會計學系", "college": "管理學院",
             "campus": None, "active": 1},
        ]})
        assert r.json()["updated"] == 0

    def test_add_new_department(self, client, adm, seeded):
        r = client.put("/api/v1/admin/org/departments", headers=adm, json={"rows": [
            {"key": None, "name": "新設學系", "college": "資訊學院",
             "campus": "台北", "active": 1},
        ]})
        assert r.status_code == 200, r.text
        assert r.json()["added"] == 1

    def test_unit_path_is_derived_not_taken_from_the_client(self, client, db, adm, seeded):
        """
        ZH: path 由 `parent/name` 推 —— 前端送什麼 path 都不算數。
            兩邊各自組的話，組法遲早不一致，而那天不會有錯誤訊息。
        """
        client.put("/api/v1/admin/org/units", headers=adm, json={"rows": [
            {"key": None, "name": "出納組", "parent": "會計室",
             "path": "亂/寫/的/路徑", "campus": None, "active": 1},
        ]})
        assert db.get(models.OrgUnit, "會計室/出納組") is not None
        assert db.get(models.OrgUnit, "亂/寫/的/路徑") is None


# ── 驗證與「不能刪」 ────────────────────────────────────────────────────
class TestGuards:
    def test_unknown_campus_is_refused(self, client, db, adm, seeded):
        """
        ZH: 打錯的校區存進去之後，那一列會在任何以校區分組的報表裡自成一格，
            看起來像學校多了一個校區。
        """
        r = client.put("/api/v1/admin/org/departments", headers=adm, json={"rows": [
            {"key": "會計學系", "name": "會計學系", "college": "管理學院",
             "campus": "火星校區", "active": 1},
        ]})
        assert r.status_code == 400
        db.expire_all()
        assert db.get(models.OrgDepartment, "會計學系").campus is None, "被拒絕了卻寫進去了"

    def test_blank_campus_becomes_null_not_empty_string(self, client, db, adm, seeded):
        """ZH: 「沒填」與「填了空字串」在分組時會是兩格，看起來像多一個沒名字的校區。"""
        client.put("/api/v1/admin/org/departments", headers=adm, json={"rows": [
            {"key": "會計學系", "name": "會計學系", "college": "管理學院",
             "campus": "   ", "active": 1},
        ]})
        db.expire_all()
        assert db.get(models.OrgDepartment, "會計學系").campus is None

    def test_deactivating_keeps_the_row_and_the_users(self, client, db, adm, seeded):
        """
        ZH: 停用 = 不進下拉，但**列還在、人還對得上**。
            這正是為什麼不提供刪除。
        """
        client.put("/api/v1/admin/org/departments", headers=adm, json={"rows": [
            {"key": "資訊工程學系", "name": "資訊工程學系",
             "college": "資訊學院", "campus": None, "active": 0},
        ]})
        db.expire_all()
        assert db.get(models.OrgDepartment, "資訊工程學系").active == 0
        assert db.get(models.User, seeded.id).department == "資訊工程學系"

    def test_there_is_no_delete_endpoint(self, client, adm, seeded):
        """
        ZH: 🔴 刻意沒有刪除。真的刪掉一列，填過它的人不會有任何錯誤 ——
            他們只是從分組統計裡消失。哪天有人加了 DELETE，這條會失敗，
            那時請連同「為什麼只能停用」一起重新想過，而不是把測試刪掉。
        """
        for url in ("/api/v1/admin/org/departments/資訊工程學系",
                    "/api/v1/admin/org/units/總務處%2F事務組"):
            r = client.delete(url, headers=adm)
            assert r.status_code in (404, 405), f"{url} 竟然可以刪：{r.status_code}"

    def test_blank_name_is_refused(self, client, adm, seeded):
        r = client.put("/api/v1/admin/org/departments", headers=adm, json={"rows": [
            {"key": None, "name": "  ", "college": "資訊學院"},
        ]})
        assert r.status_code == 400


# ── 匯出／匯入 ──────────────────────────────────────────────────────────
class TestExport:
    def test_export_round_trips(self, client, adm, seeded):
        """ZH: 匯出的東西要能原封不動匯回去 —— 全部 unchanged 才算真的對稱。"""
        d = client.get("/api/v1/admin/org/export", headers=adm).json()
        assert d["version"] == 1
        assert {r["name"] for r in d["departments"]} == {"資訊工程學系", "會計學系"}

        r = client.post("/api/v1/admin/org/import?dry_run=true", headers=adm, json=d)
        assert r.status_code == 200, r.text
        rep = r.json()
        assert rep["departments"]["added"] == [] and rep["departments"]["updated"] == []
        assert rep["departments"]["unchanged"] == 2
        assert rep["units"]["unchanged"] == 1

    def test_export_carries_no_head_count(self, client, adm, seeded):
        """
        ZH: 人數是衍生資料。帶著它的話，兩台機器匯出的檔案內容會不同，
            進版控之後每次都有 diff 而那個 diff 不代表設定有變。
        """
        d = client.get("/api/v1/admin/org/export", headers=adm).json()
        assert all("users" not in r for r in d["departments"])


class TestImport:
    def _file(self, depts=None, units=None):
        return {"version": 1,
                "departments": depts if depts is not None else [],
                "units": units if units is not None else []}

    def test_dry_run_is_the_default_and_writes_nothing(self, client, db, adm, seeded):
        """
        ZH: 🔴 這張表牽動全站分群，所以預設是「先給你看」而不是「直接套用」。
            不帶參數呼叫時**必須**是預覽。
        """
        r = client.post("/api/v1/admin/org/import", headers=adm,
                        json=self._file(depts=[{"name": "全新的系", "college": "資訊學院"}]))
        assert r.status_code == 200, r.text
        assert r.json()["dry_run"] is True
        assert r.json()["departments"]["added"] == ["全新的系"]
        db.expire_all()
        assert db.get(models.OrgDepartment, "全新的系") is None, "預覽竟然寫進去了"

    def test_apply_actually_writes(self, client, db, adm, seeded):
        """ZH: **陽性對照** —— 上面那條若是因為「匯入根本不會寫」而過，這條會抓到。"""
        r = client.post("/api/v1/admin/org/import?dry_run=false", headers=adm,
                        json=self._file(depts=[{"name": "全新的系", "college": "資訊學院",
                                                "campus": "台北", "active": 1}]))
        assert r.status_code == 200, r.text
        db.expire_all()
        got = db.get(models.OrgDepartment, "全新的系")
        assert got is not None and got.campus == "台北"

    def test_import_never_deletes_rows_missing_from_the_file(self, client, db, adm, seeded):
        """
        ZH: 🔴 這支是整段的重點。匯入一個**只有一個系**的檔案，
            資料庫裡另外那個系必須原封不動 —— 連同填過它的使用者。
            會刪的話，那些人會安靜地從分組統計裡消失。
        """
        r = client.post("/api/v1/admin/org/import?dry_run=false", headers=adm,
                        json=self._file(depts=[{"name": "會計學系", "college": "管理學院"}]))
        assert r.status_code == 200, r.text
        db.expire_all()
        assert db.get(models.OrgDepartment, "資訊工程學系") is not None, "檔案沒提到的列被刪掉了"
        assert db.get(models.User, seeded.id).department == "資訊工程學系"
        # ZH: 而且要**回報**有幾列沒被檔案涵蓋 —— 那是「兩邊不同步」的訊號。
        assert r.json()["untouched_in_db"]["departments"] == 1

    def test_active_flag_travels(self, client, db, adm, seeded):
        """ZH: 停用要能靠檔案帶過去 —— 那是「不刪除」之下唯一的下架方式。"""
        client.post("/api/v1/admin/org/import?dry_run=false", headers=adm,
                    json=self._file(depts=[{"name": "會計學系", "college": "管理學院",
                                            "active": 0}]))
        db.expire_all()
        assert db.get(models.OrgDepartment, "會計學系").active == 0

    def test_unit_path_is_recomputed_not_trusted(self, client, db, adm, seeded):
        """ZH: 檔案裡的 path 不採用 —— 舊版檔案組出來的 path 可能與現在的規則不同。"""
        client.post("/api/v1/admin/org/import?dry_run=false", headers=adm,
                    json=self._file(units=[{"path": "騙人的/路徑", "name": "出納組",
                                            "parent": "會計室"}]))
        db.expire_all()
        assert db.get(models.OrgUnit, "會計室/出納組") is not None
        assert db.get(models.OrgUnit, "騙人的/路徑") is None

    def test_bad_version_is_refused(self, client, adm, seeded):
        r = client.post("/api/v1/admin/org/import?dry_run=false", headers=adm,
                        json={"version": 999, "departments": [], "units": []})
        assert r.status_code == 400

    def test_bad_campus_is_refused_and_nothing_is_written(self, client, db, adm, seeded):
        r = client.post("/api/v1/admin/org/import?dry_run=false", headers=adm,
                        json=self._file(depts=[
                            {"name": "先寫得進去的系", "college": "資訊學院"},
                            {"name": "壞的系", "college": "資訊學院", "campus": "火星"},
                        ]))
        assert r.status_code == 400
        db.expire_all()
        # ZH: 🔴 整批要一起失敗 —— 前半寫進去、後半失敗的話，
        #     管理者會拿到一個**改到一半**的對照表而且不知道停在哪。
        assert db.get(models.OrgDepartment, "先寫得進去的系") is None, "整批匯入沒有一起回滾"

    def test_missing_arrays_are_refused(self, client, adm, seeded):
        r = client.post("/api/v1/admin/org/import", headers=adm, json={"version": 1})
        assert r.status_code == 400

    def test_non_admin_cannot_import_or_export(self, client, db, seeded):
        make_user(db, username="plain2", email="plain2@example.com", role="student")
        h = auth_headers(client, "plain2", "password123")
        assert client.get("/api/v1/admin/org/export", headers=h).status_code == 403
        assert client.post("/api/v1/admin/org/import", headers=h,
                           json=self._file()).status_code == 403
