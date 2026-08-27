"""
ZH: 數據頁依學院／學系／行政單位分組（v3.8，#13 的原始需求）。
"""
import pytest
from conftest import make_user, auth_headers

from app import crud


@pytest.fixture
def people(db):
    """ZH: 三個學生同系、一個沒填、一個職員有單位 —— 分組的四種落點都涵蓋到。"""
    crud.seed_org_tables(db)
    a = make_user(db, username="s1", email="s1@example.com")
    a.department = "資訊工程學系"
    b = make_user(db, username="s2", email="s2@example.com")
    b.department = "會計學系"                      # ZH: 管理學院,驗學院真的有分開
    c = make_user(db, username="s3", email="s3@example.com")
    c.department = None                            # ZH: 未分類
    d = make_user(db, username="s4", email="s4@example.com")
    d.department = "我是舊系名"                     # ZH: 對不到對照表 → 學院是未分類
    e = make_user(db, username="st1", email="st1@example.com", role="staff")
    e.unit = "資訊網路處/桃園資訊服務組"
    adm = make_user(db, username="adm", email="adm@example.com", role="staff")
    adm.is_admin = 1
    db.commit()
    return db


def _get(client, group_by=None):
    q = f"?group_by={group_by}" if group_by else ""
    r = client.get(f"/api/v1/admin/analytics{q}",
                   headers=auth_headers(client, "adm", "password123"))
    assert r.status_code == 200, r.text
    return r.json()


class TestGrouping:
    def test_default_is_department(self, client, people):
        d = _get(client)
        assert d["group_by"] == "department"
        got = {r["group"]: r["user_count"] for r in d["group_stats"]}
        assert got["資訊工程學系"] == 1 and got["會計學系"] == 1
        assert got["我是舊系名"] == 1

    def test_college_is_derived_from_the_lookup(self, client, people):
        d = _get(client, "college")
        got = {r["group"]: r["user_count"] for r in d["group_stats"]}
        assert got["電機資訊學院"] == 1, "資訊工程學系沒有被歸到電機資訊學院"
        assert got["管理學院"] == 1, "會計學系沒有被歸到管理學院"

    def test_unit_grouping(self, client, people):
        d = _get(client, "unit")
        got = {r["group"]: r["user_count"] for r in d["group_stats"]}
        assert got["資訊網路處/桃園資訊服務組"] == 1

    def test_bad_dimension_is_refused(self, client, people):
        r = client.get("/api/v1/admin/analytics?group_by=role",
                       headers=auth_headers(client, "adm", "password123"))
        assert r.status_code == 400

    def test_requires_admin(self, client, people):
        r = client.get("/api/v1/admin/analytics",
                       headers=auth_headers(client, "s1", "password123"))
        assert r.status_code == 403


class TestNobodyDisappears:
    @pytest.mark.parametrize("dim", ["department", "college", "unit"])
    def test_headcount_is_the_same_in_every_grouping(self, client, people, dim):
        """
        ZH: 🔴 這條是這支測試存在的理由。

        ZH: 學院要靠 `users.department` 外連 `org_departments` 推 ——
            用**內連**的話，對不到對照表的人（舊系名、打錯字、沒填）
            會從統計裡**安靜地消失**：人數對不上，而畫面上完全看不出少了誰。
            換算成真實情境就是「報告交出去之後才發現少算了一整批人」。
        """
        from app import models
        total = people.query(models.User).count()
        d = _get(client, dim)
        assert sum(r["user_count"] for r in d["group_stats"]) == total

    def test_unmatched_departments_land_in_the_null_bucket(self, client, people):
        """ZH: 對不到的要回 None（文案由前端決定,才翻得了中英）——不是字串 'Unknown'。"""
        d = _get(client, "college")
        null_row = [r for r in d["group_stats"] if r["group"] is None]
        assert len(null_row) == 1
        # ZH: 落在未分類的有四種人,列出來是因為我第一次寫這條時只想到前兩種:
        #       s3  —— department 是 NULL
        #       s4  —— 舊系名,對不到對照表
        #       st1 —— 職員,本來就沒有學系
        #       adm —— 同上
        #     依學院分組時「職員全部落在未分類」是正確的,不是 bug。
        assert null_row[0]["user_count"] == 4


class TestFilterStillWorks:
    def test_department_filter_narrows_before_grouping(self, client, people):
        """ZH: `department` 篩的一律是學系 —— 先篩人,再看要怎麼分組。"""
        r = client.get("/api/v1/admin/analytics?group_by=college&department=資訊工程學系",
                       headers=auth_headers(client, "adm", "password123"))
        assert r.status_code == 200, r.text
        stats = r.json()["group_stats"]
        assert len(stats) == 1
        assert stats[0]["group"] == "電機資訊學院" and stats[0]["user_count"] == 1
