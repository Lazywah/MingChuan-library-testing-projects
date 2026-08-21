# -*- coding: utf-8 -*-
"""
ZH: 稽核紀錄要回**名字**，不是只回 UUID。

ZH: 稽核的用途就是「誰、對誰、做了什麼」。只回 `admin_id` 的話，
    看的人得再去查一次那是誰 —— 而那正是他打開那一頁想省下的動作。

ZH: 另一半同樣重要：**查不到就回 None，不要拿 UUID 充當名字**。
    回 UUID 的話畫面會顯示一串亂碼，而它看起來像個正常的使用者名稱。
"""
import pathlib
import sys

import pytest

from conftest import make_user, auth_headers

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "job-scheduler"))
from app import models   # noqa: E402


@pytest.fixture
def admin_headers(client, db):
    make_user(db, username="root", email="root@example.com", role="admin")
    return auth_headers(client, "root")


def _act(db, admin_id, target_id, action="grant_quota"):
    db.add(models.AdminAction(admin_id=admin_id, target_user=target_id, action=action))
    db.commit()


def test_audit_returns_usernames(client, db, admin_headers):
    """ZH: 兩邊的名字都要有。"""
    make_user(db, username="alice", email="a@example.com")
    root = db.query(models.User).filter_by(username="root").first()
    alice = db.query(models.User).filter_by(username="alice").first()
    _act(db, root.id, alice.id)

    items = client.get("/api/v1/admin/audit", headers=admin_headers).json()["items"]
    row = items[0]
    assert row["admin_username"] == "root", row
    assert row["target_username"] == "alice", row


def test_target_of_a_deleted_account_is_none(client, db, admin_headers):
    """ZH: 帳號被刪除之後，那些紀錄的 target_username 要是 None。

    ZH: ⚠ 我原本想測的是「id 還在但查不到」，寫完才發現**那不可能發生**：
        `admin_actions.target_user` 有指向 users 的外鍵（NO ACTION），
        插一個不存在的 id 會直接 IntegrityError。
        而刪帳號的流程會先把 `target_user` 設成 NULL 再刪
        （見 admin.py 的「解開稽核類外鍵參照」）——
        **選解參照而不是刪紀錄，是為了保留稽核軌跡**。

    ZH: 所以真正要驗的是：解參照之後那一列仍然在、而且不會顯示成亂碼。
        （測試連正確的程式碼都失敗時，先問「這個情境真的存在嗎」，
          不要為了讓它綠而去改產品。）
    """
    make_user(db, username="alice", email="a@example.com")
    root = db.query(models.User).filter_by(username="root").first()
    alice = db.query(models.User).filter_by(username="alice").first()
    _act(db, root.id, alice.id, action="before_delete")

    # 模擬刪帳號時的解參照
    db.query(models.AdminAction).filter(
        models.AdminAction.target_user == alice.id
    ).update({models.AdminAction.target_user: None}, synchronize_session=False)
    db.commit()

    items = client.get("/api/v1/admin/audit", headers=admin_headers).json()["items"]
    row = [i for i in items if i["action"] == "before_delete"][0]
    assert row["target_username"] is None, row
    assert row["admin_username"] == "root", row      # 做這件事的人還在，名字要留著


def test_null_target_is_also_none(client, db, admin_headers):
    """ZH: 陰性對照 —— 本來就沒有對象的動作（target_user 是 NULL）也要回 None。"""
    root = db.query(models.User).filter_by(username="root").first()
    _act(db, root.id, None, action="no_target_case")

    items = client.get("/api/v1/admin/audit", headers=admin_headers).json()["items"]
    row = [i for i in items if i["action"] == "no_target_case"][0]
    assert row["target_username"] is None, row


def test_names_do_not_cost_a_query_per_row(client, db, admin_headers):
    """ZH: 100 筆不該變成 200 次查詢 —— 一次撈完再對照。

    ZH: 這條測的是**行為的可觀察後果**：同一個人的多筆紀錄，
        名字必須全部都對。逐筆查也會對，所以這裡真正釘住的是
        「不會因為批次撈而漏掉某些列」。
    """
    make_user(db, username="alice", email="a@example.com")
    root = db.query(models.User).filter_by(username="root").first()
    alice = db.query(models.User).filter_by(username="alice").first()
    for i in range(5):
        _act(db, root.id, alice.id, action=f"act_{i}")

    items = client.get("/api/v1/admin/audit", headers=admin_headers).json()["items"]
    mine = [i for i in items if i["action"].startswith("act_")]
    assert len(mine) == 5
    assert all(i["admin_username"] == "root" for i in mine), mine
    assert all(i["target_username"] == "alice" for i in mine), mine
