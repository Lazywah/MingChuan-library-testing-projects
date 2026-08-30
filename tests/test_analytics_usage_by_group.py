# -*- coding: utf-8 -*-
"""
ZH: 各系／院／單位的使用統計（v3.9）。

ZH: 這支釘的是**算術**，而算錯的統計最危險 —— 它看起來永遠是合理的，
    沒有人會發現，然後有人拿它去做決定。

ZH: 四件最容易算錯的事：
    1. 分母搞混：佔比（比全平台）與滲透率（比自己這一組的人數）不是同一件事
    2. 管理員補的點被算成「使用量」
    3. 活躍人數用各項相加 → 同一個人被算好幾次，可能超過總人數
    4. 期間篩選對 myai_transactions 要用廠商當地時間，不是 UTC
"""
from datetime import datetime, timedelta, timezone

import pytest
from conftest import auth_headers, make_user

from app import models


@pytest.fixture()
def admin_headers(client, db):
    make_user(db, username="ana-admin", email="ana-admin@example.com", role="admin")
    return auth_headers(client, "ana-admin", "password123")


def _user(db, name, dept):
    """ZH: ⚠ make_user 不吃 department（它走 UserCreate，那裡沒有這個欄位），
       所以建完再填上去。"""
    u = make_user(db, username=name, email=f"{name}@example.com", role="student")
    u.department = dept
    db.commit()
    return u


def _get(client, headers, **kw):
    q = "&".join(f"{k}={v}" for k, v in kw.items())
    r = client.get(f"/api/v1/admin/analytics?{q}", headers=headers)
    assert r.status_code == 200, r.text
    return {g["group"]: g for g in r.json()["group_stats"]}


def test_visits_counted_per_department(client, db, admin_headers):
    a = _user(db, "s-a", "資管系")
    b = _user(db, "s-b", "英語系")
    now = datetime.now(timezone.utc)
    for _ in range(3):
        db.add(models.MyaiVisit(user_id=a.id, occurred_at=now))
    db.add(models.MyaiVisit(user_id=b.id, occurred_at=now))
    db.commit()

    g = _get(client, admin_headers, group_by="department", days=30)

    assert g["資管系"]["myai_visits"] == 3
    assert g["英語系"]["myai_visits"] == 1


def test_lab_cpu_and_gpu_are_separate(client, db, admin_headers):
    """ZH: 分得開才有意義 —— 這正是舊資料做不到的事。"""
    a = _user(db, "s-c", "資管系")
    now = datetime.now(timezone.utc)
    db.add(models.LabUsageLog(user_id=a.id, used_gpu=1, started_at=now))
    db.add(models.LabUsageLog(user_id=a.id, used_gpu=1, started_at=now))
    db.add(models.LabUsageLog(user_id=a.id, used_gpu=0, started_at=now))
    db.commit()

    g = _get(client, admin_headers, group_by="department", days=30)

    assert g["資管系"]["lab_gpu"] == 2
    assert g["資管系"]["lab_cpu"] == 1


def test_topups_are_not_counted_as_usage(client, db, admin_headers):
    """ZH: 🔴 管理員補點是**加**點（points_delta 為正），那不是使用量。

    ZH: 算進去的話，「被補過點的系」會看起來用得特別多 ——
        而那正好是**用得少所以要補**的那些系。方向剛好相反。
    """
    a = _user(db, "s-d", "資管系")
    db.add(models.ExternalAiAccount(user_id=a.id, vendor_username="s-d",
                                    myai_vendor_sn="sn-d", status="active"))
    now = datetime.now()          # ZH: 廠商時間是 naive，跟著它
    db.add(models.MyaiTransaction(vendor_sn="sn-d", occurred_at=now,
                                  points_delta=-500, dedup_key="k1"))
    db.add(models.MyaiTransaction(vendor_sn="sn-d", occurred_at=now,
                                  points_delta=+9000, dedup_key="k2"))
    db.commit()

    g = _get(client, admin_headers, group_by="department", days=30)

    # ZH: 只有那 500 是「用掉的」
    assert g["資管系"]["myai_points"] == 500
    assert g["資管系"]["myai_tx"] == 2      # ZH: 筆數照算兩筆，那是事實


def test_active_users_never_exceeds_user_count(client, db, admin_headers):
    """ZH: 🔴 同一個人做了很多事，仍然只是一個人。

    ZH: 用各項相加的話，一個既跳轉又開實驗室的人會被算兩次，
        於是「有用的人 3/2」這種數字會出現 —— 而百分比會超過 100%。
    """
    a = _user(db, "s-e", "資管系")
    now = datetime.now(timezone.utc)
    db.add(models.MyaiVisit(user_id=a.id, occurred_at=now))
    db.add(models.LabUsageLog(user_id=a.id, used_gpu=1, started_at=now))
    db.add(models.TrainingJob(user_id=a.id, job_name="j", model_name="m",
                              created_at=now))
    db.commit()

    g = _get(client, admin_headers, group_by="department", days=30)

    row = g["資管系"]
    assert row["active_users_min"] == 1
    assert row["active_users_min"] <= row["user_count"]
    assert row["adoption"] <= 100.0


def test_two_ratios_use_different_denominators(client, db, admin_headers):
    """ZH: 🔴 佔比與滲透率必須是**兩個不同的數字**。

    ZH: 大系（10 人用 100 次）佔比高但滲透率低；
        小系（2 人全用、共 10 次）佔比低但滲透率 100%。
        兩個都給，才看得出「哪個系推得成功」與「誰貢獻最多」。
    """
    big = [_user(db, f"big{i}", "大系") for i in range(10)]
    small = [_user(db, f"sml{i}", "小系") for i in range(2)]
    now = datetime.now(timezone.utc)
    # ZH: 大系只有 2 個人在用，但用得兇
    for u in big[:2]:
        for _ in range(50):
            db.add(models.MyaiVisit(user_id=u.id, occurred_at=now))
    # ZH: 小系兩個人都在用，但總量少
    for u in small:
        for _ in range(5):
            db.add(models.MyaiVisit(user_id=u.id, occurred_at=now))
    db.commit()

    g = _get(client, admin_headers, group_by="department", days=30)

    assert g["大系"]["share_visits"] > g["小系"]["share_visits"]     # 佔比：大系贏
    assert g["大系"]["adoption"] < g["小系"]["adoption"]             # 滲透：小系贏
    assert g["小系"]["adoption"] == 100.0


def test_period_filter_excludes_old_rows(client, db, admin_headers):
    a = _user(db, "s-f", "資管系")
    now = datetime.now(timezone.utc)
    db.add(models.MyaiVisit(user_id=a.id, occurred_at=now))
    db.add(models.MyaiVisit(user_id=a.id, occurred_at=now - timedelta(days=90)))
    db.commit()

    recent = _get(client, admin_headers, group_by="department", days=30)
    everything = _get(client, admin_headers, group_by="department", days=0)

    assert recent["資管系"]["myai_visits"] == 1
    assert everything["資管系"]["myai_visits"] == 2


def test_tracking_since_is_reported(client, db, admin_headers):
    """ZH: 前端要能講「自 X 日起才有資料」，否則 0 會被當成「沒人用」。"""
    a = _user(db, "s-g", "資管系")
    db.add(models.MyaiVisit(user_id=a.id,
                            occurred_at=datetime.now(timezone.utc)))
    db.commit()

    r = client.get("/api/v1/admin/analytics?days=0", headers=admin_headers).json()

    assert r["tracking_since"]["myai_visits"] is not None
    # ZH: 沒有資料的那張回 None，不是回一個假的日期
    assert r["tracking_since"]["lab_usage"] is None
