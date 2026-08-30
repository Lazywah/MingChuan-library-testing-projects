# -*- coding: utf-8 -*-
"""
ZH: 學系／學院的英文名要送到管理端（v3.9）。

ZH: 🔴 這支存在的主因是 admin.py 的使用者列表是**手工建構**的 ——
    在 schema 加了欄位而忘了在那裡帶上，它會**靜靜地永遠回 None**。
    程式碼裡就有一句警告說這個坑踩過兩次（metrics、has_model）。

ZH: 另外釘住「行政單位刻意不做」—— 英文名只有 53/97，做了會讓同一欄
    一半英文一半中文。日後有人「順手」補上去時，這支會提醒他先補資料。
"""
import pytest
from conftest import auth_headers, make_user

from app import models


@pytest.fixture()
def admin_headers(client, db):
    make_user(db, username="org-admin", email="org-admin@example.com", role="admin")
    return auth_headers(client, "org-admin", "password123")


@pytest.fixture()
def org(db):
    db.add(models.OrgDepartment(name="資訊工程學系", college="資訊學院",
                                name_en="Computer Science", college_en="College of Computing"))
    db.add(models.OrgDepartment(name="沒有英文名的系", college="資訊學院",
                                name_en=None, college_en="College of Computing"))
    db.commit()


def _user(db, name, dept):
    u = make_user(db, username=name, email=f"{name}@example.com", role="student")
    u.department = dept
    db.commit()
    return u


def test_user_list_carries_english_department(client, db, admin_headers, org):
    """ZH: 🔴 列表是手工建構的——schema 有欄位不代表它會被填。"""
    _user(db, "cs-1", "資訊工程學系")

    rows = client.get("/api/v1/admin/users?limit=500", headers=admin_headers).json()

    me = [r for r in rows if r["username"] == "cs-1"][0]
    assert me["department"] == "資訊工程學系"
    assert me["department_en"] == "Computer Science"


def test_no_english_name_is_null_not_empty(client, db, admin_headers, org):
    """ZH: 對照表沒填英文名 → None，前端據此退回中文。"""
    _user(db, "cs-2", "沒有英文名的系")

    rows = client.get("/api/v1/admin/users?limit=500", headers=admin_headers).json()

    assert [r for r in rows if r["username"] == "cs-2"][0]["department_en"] is None


def test_department_not_in_mapping(client, db, admin_headers, org):
    """ZH: department 是自由字串沒有外鍵 —— 對不到是正常情況，不可以爆掉。"""
    _user(db, "cs-3", "打錯字的系")

    rows = client.get("/api/v1/admin/users?limit=500", headers=admin_headers).json()

    me = [r for r in rows if r["username"] == "cs-3"][0]
    assert me["department"] == "打錯字的系"
    assert me["department_en"] is None


def test_analytics_group_has_english(client, db, admin_headers, org):
    _user(db, "cs-4", "資訊工程學系")

    r = client.get("/api/v1/admin/analytics?group_by=department&days=0",
                   headers=admin_headers).json()

    g = {x["group"]: x for x in r["group_stats"]}
    assert g["資訊工程學系"]["group_en"] == "Computer Science"


def test_analytics_college_has_english(client, db, admin_headers, org):
    _user(db, "cs-5", "資訊工程學系")

    r = client.get("/api/v1/admin/analytics?group_by=college&days=0",
                   headers=admin_headers).json()

    g = {x["group"]: x for x in r["group_stats"]}
    assert g["資訊學院"]["group_en"] == "College of Computing"


def test_unit_grouping_has_no_english_on_purpose(client, db, admin_headers, org):
    """ZH: 🔴 行政單位**刻意不做**（擁有者裁定 2026-08-30）。

    ZH: 英文名只有 53/97 —— 做了會讓同一欄一半英文一半中文，比全中文更難讀。
        日後要打開的話，**先把 44 個缺的英文名補齊**，再改這裡與這支測試。
    """
    u = _user(db, "cs-6", "資訊工程學系")
    u.unit = "圖書館"
    db.commit()
    # ZH: ⚠ org_units.path 是 NOT NULL（單位有層級），造測試資料時要帶上。
    db.add(models.OrgUnit(name="圖書館", name_en="Library", path="圖書館"))
    db.commit()

    r = client.get("/api/v1/admin/analytics?group_by=unit&days=0",
                   headers=admin_headers).json()

    g = {x["group"]: x for x in r["group_stats"]}
    assert g["圖書館"]["group_en"] is None, "行政單位現在不該送英文名"
