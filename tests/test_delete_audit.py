"""
ZH: 刪除帳號要留稽核（v3.8）。

ZH: 這條是**實地發現**的：2026-08-27 開發機上一個帳號不見了,
    翻遍 admin_actions 只有 export_users / create_temp_account / extend_temp_account ——
    刪除是管理端破壞性最強的動作,卻是唯一完全不留痕跡的。
    而且刪除流程還會把先前提到那個人的紀錄 target_user 洗成 NULL,
    連間接的線索都沒有。
"""
import json

import pytest
from conftest import make_user, auth_headers

from app import models


@pytest.fixture
def admin_and_victim(db):
    adm = make_user(db, username="adm", email="adm@example.com", role="staff")
    adm.is_admin = 1
    victim = make_user(db, username="victim", email="victim@example.com")
    victim.department = "資訊工程學系"
    db.commit()
    return adm, victim


def _delete(client, victim_id):
    return client.post(f"/api/v1/admin/users/{victim_id}/delete",
                       json={"admin_password": "password123"},
                       headers=auth_headers(client, "adm", "password123"))


class TestDeletionIsAudited:
    def test_a_row_is_written(self, client, db, admin_and_victim):
        adm, victim = admin_and_victim
        assert _delete(client, victim.id).status_code == 200

        rows = db.query(models.AdminAction).filter_by(action="delete_user").all()
        assert len(rows) == 1, "刪除帳號沒有留下稽核紀錄"
        assert rows[0].admin_id == adm.id

    def test_the_snapshot_survives_the_deletion(self, client, db, admin_and_victim):
        """
        ZH: 🔴 身分資訊放在 payload 而不是 target_user,理由有兩個:
              1. target_user 是 FK,指向的列下一行就要被刪 —— 填了會 IntegrityError
              2. 刪除流程會把既有紀錄的 target_user 洗成 NULL,放那裡也留不住
            payload 是 Text,不受影響。
        """
        adm, victim = admin_and_victim
        vid, vname, vmail = victim.id, victim.username, victim.email
        _delete(client, vid)

        row = db.query(models.AdminAction).filter_by(action="delete_user").first()
        assert row.target_user is None, "target_user 是 FK,指向已刪除的列會炸"
        p = json.loads(row.payload)
        assert p["deleted_user_id"] == vid
        assert p["username"] == vname
        assert p["email"] == vmail
        assert p["role"] == "student"
        assert p["department"] == "資訊工程學系"

    def test_the_user_really_is_gone(self, client, db, admin_and_victim):
        """ZH: 陽性對照 —— 確認稽核不是寫在「其實沒刪成功」的情況下。"""
        adm, victim = admin_and_victim
        vid = victim.id
        _delete(client, vid)
        assert db.query(models.User).filter_by(id=vid).first() is None

    def test_a_failed_delete_writes_nothing(self, client, db, admin_and_victim):
        """ZH: 密碼錯就該擋在最前面,不能留下一筆「刪了」的假紀錄。"""
        adm, victim = admin_and_victim
        r = client.post(f"/api/v1/admin/users/{victim.id}/delete",
                        json={"admin_password": "wrong-password"},
                        headers=auth_headers(client, "adm", "password123"))
        assert r.status_code == 403
        assert db.query(models.AdminAction).filter_by(action="delete_user").count() == 0
        assert db.query(models.User).filter_by(id=victim.id).first() is not None

    def test_deleting_yourself_is_refused_and_unaudited(self, client, db, admin_and_victim):
        adm, _ = admin_and_victim
        r = client.post(f"/api/v1/admin/users/{adm.id}/delete",
                        json={"admin_password": "password123"},
                        headers=auth_headers(client, "adm", "password123"))
        assert r.status_code == 400
        assert db.query(models.AdminAction).filter_by(action="delete_user").count() == 0


class TestOlderAuditRowsStillLoseTheirTarget:
    def test_unlinking_is_unchanged_but_now_recoverable(self, client, db, admin_and_victim):
        """
        ZH: 解參照的行為**沒有改**（那是 FK 的必要處理）——
            但現在多了一筆 delete_user,所以「這個 target 是誰」查得回來了。
            這條把兩件事的關係釘住:舊紀錄仍會失去 target,而快照補上那個缺口。
        """
        adm, victim = admin_and_victim
        db.add(models.AdminAction(admin_id=adm.id, target_user=victim.id,
                                  action="grant_profile_unlock", payload="{}"))
        db.commit()
        vid = victim.id
        _delete(client, vid)

        old = db.query(models.AdminAction).filter_by(action="grant_profile_unlock").first()
        assert old.target_user is None, "解參照沒發生的話刪除會 IntegrityError"

        snap = db.query(models.AdminAction).filter_by(action="delete_user").first()
        assert json.loads(snap.payload)["deleted_user_id"] == vid, \
            "舊紀錄失去 target 之後,只剩這一筆查得出那個人是誰"
