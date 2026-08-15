"""
ZH: 配額提權 / 撤銷 API 整合測試
EN: Quota grant / revoke API integration tests

ZH: 為什麼有這個檔案：
    這兩個端點從上線起就是壞的 —— admin.py 呼叫 quota_service.grant / .revoke，
    但 quota_service 只有 grant_quota / revoke_quota，每次呼叫都 AttributeError → 500。
    沒有任何測試覆蓋，所以沒人發現。這裡的測試刻意不只驗「沒有拋例外」，
    而是驗**配額數字真的動了** —— 名字改對但語意接錯的話，只驗狀態碼會全部綠燈。

EN: These two endpoints were broken from day one (wrong function names → 500) with
    zero test coverage. Tests here assert the *effect* on effective quota, not just
    status codes, so a call that returns 200 without changing anything still fails.
"""
import json

import pytest
from conftest import make_user, auth_headers

from app import models


def _admin(client, db):
    """ZH: 建立管理員，回傳 (headers, admin_user) | EN: Create admin, return headers + user"""
    admin = make_user(db, username="qadmin", email="qadmin@example.com", role="admin")
    return auth_headers(client, "qadmin", "password123"), admin


def _student(db, username="qstudent"):
    return make_user(db, username=username, email=f"{username}@example.com")


def _grant(client, headers, user_id, gb=20, reason="專題需要額外空間"):
    return client.post("/api/v1/admin/quota/grant", headers=headers,
                       json={"user_id": user_id, "extra_quota_gb": gb, "reason": reason})


def _effective(client, headers, user_id):
    r = client.get(f"/api/v1/admin/quota/{user_id}", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()["effective_quota_gb"]


# ══════════════════════════════════════════════════════════════════
# POST /admin/quota/grant
# ══════════════════════════════════════════════════════════════════

class TestQuotaGrant:
    def test_grant_succeeds(self, client, db):
        """ZH: 迴歸測試 —— 修正前這裡是 AttributeError → 500"""
        headers, _ = _admin(client, db)
        stu = _student(db)
        r = _grant(client, headers, stu.id)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["extra_quota_gb"] == 20
        assert body["id"] and body["granted_at"]

    def test_grant_increases_effective_quota(self, client, db):
        """ZH: 不只回 200，配額數字要真的變 —— 這是語意驗證，不是狀態碼驗證"""
        headers, _ = _admin(client, db)
        stu = _student(db)
        before = _effective(client, headers, stu.id)
        _grant(client, headers, stu.id, gb=20)
        assert _effective(client, headers, stu.id) == before + 20

    def test_grant_records_granting_admin(self, client, db):
        headers, admin = _admin(client, db)
        stu = _student(db)
        gid = _grant(client, headers, stu.id).json()["id"]
        db.expire_all()
        row = db.query(models.QuotaGrant).filter(models.QuotaGrant.id == gid).one()
        assert row.granted_by == admin.id
        assert row.user_id == stu.id
        assert row.revoked_at is None

    def test_grant_unknown_user_returns_404(self, client, db):
        headers, _ = _admin(client, db)
        assert _grant(client, headers, "no-such-user").status_code == 404

    @pytest.mark.parametrize("gb,reason", [
        (0, "理由夠長的說明"),      # extra_quota_gb 必須 > 0
        (-5, "理由夠長的說明"),
        (20, "短"),                  # reason 至少 5 字
    ])
    def test_grant_rejects_invalid_payload(self, client, db, gb, reason):
        headers, _ = _admin(client, db)
        stu = _student(db)
        assert _grant(client, headers, stu.id, gb=gb, reason=reason).status_code == 422

    def test_student_cannot_grant(self, client, db):
        stu = _student(db)
        headers = auth_headers(client, "qstudent")
        assert _grant(client, headers, stu.id).status_code == 403


# ══════════════════════════════════════════════════════════════════
# DELETE /admin/quota/grant/{grant_id}
# ══════════════════════════════════════════════════════════════════

class TestQuotaRevoke:
    def test_revoke_succeeds(self, client, db):
        """ZH: 迴歸測試 —— 修正前這裡也是 AttributeError → 500"""
        headers, _ = _admin(client, db)
        stu = _student(db)
        gid = _grant(client, headers, stu.id).json()["id"]
        r = client.delete(f"/api/v1/admin/quota/grant/{gid}", headers=headers)
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "revoked"

    def test_revoke_restores_base_quota(self, client, db):
        headers, _ = _admin(client, db)
        stu = _student(db)
        base = _effective(client, headers, stu.id)
        gid = _grant(client, headers, stu.id, gb=20).json()["id"]
        assert _effective(client, headers, stu.id) == base + 20
        client.delete(f"/api/v1/admin/quota/grant/{gid}", headers=headers)
        assert _effective(client, headers, stu.id) == base

    def test_revoke_is_soft_delete(self, client, db):
        """ZH: 撤銷不刪列，只寫 revoked_at —— 審計要留得住"""
        headers, _ = _admin(client, db)
        stu = _student(db)
        gid = _grant(client, headers, stu.id).json()["id"]
        client.delete(f"/api/v1/admin/quota/grant/{gid}", headers=headers)
        db.expire_all()
        row = db.query(models.QuotaGrant).filter(models.QuotaGrant.id == gid).one()
        assert row.revoked_at is not None

    def test_revoke_unknown_grant_returns_404(self, client, db):
        headers, _ = _admin(client, db)
        r = client.delete("/api/v1/admin/quota/grant/no-such-id", headers=headers)
        assert r.status_code == 404

    def test_revoke_twice_returns_404_not_500(self, client, db):
        """ZH: 重複撤銷必須是 404（找不到可撤銷的），不能變成伺服器錯誤"""
        headers, _ = _admin(client, db)
        stu = _student(db)
        gid = _grant(client, headers, stu.id).json()["id"]
        assert client.delete(f"/api/v1/admin/quota/grant/{gid}", headers=headers).status_code == 200
        assert client.delete(f"/api/v1/admin/quota/grant/{gid}", headers=headers).status_code == 404

    def test_student_cannot_revoke(self, client, db):
        headers, _ = _admin(client, db)
        stu = _student(db)
        gid = _grant(client, headers, stu.id).json()["id"]
        stu_headers = auth_headers(client, "qstudent")
        r = client.delete(f"/api/v1/admin/quota/grant/{gid}", headers=stu_headers)
        assert r.status_code == 403


# ══════════════════════════════════════════════════════════════════
# 稽核記錄 admin_actions
# ══════════════════════════════════════════════════════════════════
# ZH: models.AdminAction.action 的註解早就把 grant_quota / revoke_quota 列進去了，
#     但這兩個動作原本完全沒寫稽核。這組測試釘住「有寫」。

class TestQuotaAuditLog:
    def _actions(self, db, action=None):
        db.expire_all()
        q = db.query(models.AdminAction)
        if action:
            q = q.filter(models.AdminAction.action == action)
        return q.order_by(models.AdminAction.timestamp).all()

    def test_grant_writes_audit_row(self, client, db):
        headers, admin = _admin(client, db)
        stu = _student(db)
        gid = _grant(client, headers, stu.id).json()["id"]
        rows = self._actions(db, "grant_quota")
        assert len(rows) == 1
        assert rows[0].admin_id == admin.id
        assert rows[0].target_user == stu.id
        payload = json.loads(rows[0].payload)
        assert payload["grant_id"] == gid
        assert payload["extra_quota_gb"] == 20

    def test_revoke_writes_audit_row_with_revoking_admin(self, client, db):
        """ZH: revoked_by 沒有欄位可放（QuotaGrant 只有 revoked_at），
               「誰撤銷的」唯一的落點就是這筆稽核列 —— 掉了就永遠查不到。"""
        headers, admin = _admin(client, db)
        stu = _student(db)
        gid = _grant(client, headers, stu.id).json()["id"]
        client.delete(f"/api/v1/admin/quota/grant/{gid}", headers=headers)
        rows = self._actions(db, "revoke_quota")
        assert len(rows) == 1
        assert rows[0].admin_id == admin.id
        assert rows[0].target_user == stu.id
        assert json.loads(rows[0].payload)["grant_id"] == gid

    def test_failed_revoke_writes_no_audit_row(self, client, db):
        """ZH: 稽核列與領域變更同交易 —— 撤銷失敗不該留下孤兒稽核列"""
        headers, _ = _admin(client, db)
        before = len(self._actions(db))
        client.delete("/api/v1/admin/quota/grant/no-such-id", headers=headers)
        assert len(self._actions(db)) == before

    def test_audit_endpoint_can_filter_quota_actions(self, client, db):
        """ZH: /admin/audit?action=grant_quota 查得到 —— 這是稽核列的實際用途"""
        headers, _ = _admin(client, db)
        stu = _student(db)
        gid = _grant(client, headers, stu.id).json()["id"]
        client.delete(f"/api/v1/admin/quota/grant/{gid}", headers=headers)
        for action in ("grant_quota", "revoke_quota"):
            r = client.get(f"/api/v1/admin/audit?action={action}", headers=headers)
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["total"] == 1, f"{action} 查不到稽核列"
            assert body["items"][0]["action"] == action
