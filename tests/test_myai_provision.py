"""
ZH: MYAI v3.3 自動開通 —— 初始密碼的遞送與確認段
EN: MYAI v3.3 auto-provisioning — initial-password delivery and acknowledgement

ZH: 為什麼有這個檔案：
    這條流程是**憑證遞送**（我們替學生建號時產生一次性初始密碼，加密暫存，
    學生看到後按「我已修改」即銷毀）。整條路徑原本零測試覆蓋——而這個 repo 剛
    示範過「零覆蓋的功能會壞著沒人發現」（quota 兩個端點必定 500 卻上線很久）。

    這裡釘住四件不能出錯的事：
      1. 靜態加密——DB 裡不得有明文
      2. 保留期到期／已確認 → 讀不到，且就地清除
      3. 身分由 JWT 推導 → 查不到別人的
      4. 金鑰換過導致解密失敗 → 當作沒有，不是 500
"""
from datetime import datetime, timedelta, timezone

import pytest
from conftest import make_user, auth_headers

from app import models
from app.services import myai_sync


PWD = "Init-Pw-9x7Q"


def _account(db, user, *, issued_days_ago: float = 0, ack: int = 0,
             plaintext: str = PWD):
    """ZH: 建一筆已開通、帶加密初始密碼的 ExternalAiAccount。"""
    acc = models.ExternalAiAccount(
        user_id=user.id, vendor_username=user.email, status="active",
        note="test",
    )
    db.add(acc)
    db.commit()
    db.refresh(acc)
    myai_sync.store_initial_password(db, acc, plaintext)
    if issued_days_ago:
        acc.init_pwd_at = datetime.now(timezone.utc) - timedelta(days=issued_days_ago)
    acc.init_pwd_ack = ack
    db.commit()
    db.refresh(acc)
    return acc


# ══════════════════════════════════════════════════════════════════
# 靜態加密
# ══════════════════════════════════════════════════════════════════

class TestEncryptionAtRest:
    def test_password_not_stored_in_plaintext(self, db):
        user = make_user(db, username="p1", email="p1@example.com")
        acc = _account(db, user)
        assert acc.init_pwd_enc is not None
        assert PWD.encode() not in bytes(acc.init_pwd_enc), "DB 裡出現明文初始密碼"

    def test_roundtrip_reads_back(self, db):
        user = make_user(db, username="p2", email="p2@example.com")
        acc = _account(db, user)
        assert myai_sync.read_initial_password(db, acc, 30) == PWD

    def test_store_resets_acknowledgement(self, db):
        """ZH: 重新開通應重置確認狀態，否則新密碼一發出去就被當成已確認。"""
        user = make_user(db, username="p3", email="p3@example.com")
        acc = _account(db, user, ack=1)
        myai_sync.store_initial_password(db, acc, "Another-Pw-1")
        assert acc.init_pwd_ack == 0
        assert myai_sync.read_initial_password(db, acc, 30) == "Another-Pw-1"


# ══════════════════════════════════════════════════════════════════
# 保留期與確認
# ══════════════════════════════════════════════════════════════════

class TestRetentionAndAck:
    def test_expired_returns_none_and_purges_in_place(self, db):
        """ZH: 逾期不只是讀不到——要就地清除，不留著等排程。"""
        user = make_user(db, username="p4", email="p4@example.com")
        acc = _account(db, user, issued_days_ago=31)
        assert myai_sync.read_initial_password(db, acc, 30) is None
        db.refresh(acc)
        assert acc.init_pwd_enc is None, "逾期後密文仍留在 DB"

    def test_within_retention_still_readable(self, db):
        user = make_user(db, username="p5", email="p5@example.com")
        acc = _account(db, user, issued_days_ago=29)
        assert myai_sync.read_initial_password(db, acc, 30) == PWD

    def test_acknowledged_returns_none_and_purges(self, db):
        user = make_user(db, username="p6", email="p6@example.com")
        acc = _account(db, user, ack=1)
        assert myai_sync.read_initial_password(db, acc, 30) is None
        db.refresh(acc)
        assert acc.init_pwd_enc is None

    def test_acknowledge_sets_flag_and_clears(self, db):
        user = make_user(db, username="p7", email="p7@example.com")
        acc = _account(db, user)
        assert myai_sync.acknowledge_initial_password(db, user) is True
        db.refresh(acc)
        assert acc.init_pwd_ack == 1 and acc.init_pwd_enc is None

    def test_acknowledge_without_account_returns_false(self, db):
        user = make_user(db, username="p8", email="p8@example.com")
        assert myai_sync.acknowledge_initial_password(db, user) is False

    def test_batch_purge_clears_expired_only(self, db):
        fresh = make_user(db, username="p9", email="p9@example.com")
        stale = make_user(db, username="p10", email="p10@example.com")
        a_fresh = _account(db, fresh, issued_days_ago=1)
        a_stale = _account(db, stale, issued_days_ago=99)

        n = myai_sync.purge_expired_initial_passwords(db, 30)

        db.refresh(a_fresh); db.refresh(a_stale)
        assert n >= 1
        assert a_stale.init_pwd_enc is None, "逾期的沒被清"
        assert a_fresh.init_pwd_enc is not None, "未逾期的被誤清"


# ══════════════════════════════════════════════════════════════════
# 解密失敗（金鑰換過 / 資料損壞）
# ══════════════════════════════════════════════════════════════════

class TestDecryptFailureIsNotAnError:
    def test_corrupted_ciphertext_treated_as_absent(self, db):
        """ZH: 金鑰換過會讓舊密文解不開。那該當成「沒有密碼」，不是 500。"""
        user = make_user(db, username="p11", email="p11@example.com")
        acc = _account(db, user)
        acc.init_pwd_enc = b"not-a-valid-ciphertext"
        db.commit()
        assert myai_sync.read_initial_password(db, acc, 30) is None


# ══════════════════════════════════════════════════════════════════
# HTTP 端點 + 身分隔離
# ══════════════════════════════════════════════════════════════════

BASE = "/api/v1/external-ai"


class TestProvisionEndpoints:
    def test_status_returns_password_within_retention(self, client, db):
        user = make_user(db, username="e1", email="e1@example.com")
        _account(db, user)
        r = client.get(f"{BASE}/my-provision", headers=auth_headers(client, "e1"))
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["provisioned"] is True
        assert body["initial_password"] == PWD
        assert body["acknowledged"] is False
        assert body["retention_days"] == 30      # SYSTEM_SETTINGS 的預設

    def test_ack_then_status_no_longer_returns_password(self, client, db):
        user = make_user(db, username="e2", email="e2@example.com")
        _account(db, user)
        h = auth_headers(client, "e2")

        assert client.post(f"{BASE}/my-provision/ack", headers=h).status_code == 200

        body = client.get(f"{BASE}/my-provision", headers=h).json()
        assert body["initial_password"] is None
        assert body["acknowledged"] is True
        assert body["provisioned"] is True        # 帳號還在，只是密碼銷毀了

    def test_ack_without_account_returns_404(self, client, db):
        make_user(db, username="e3", email="e3@example.com")
        r = client.post(f"{BASE}/my-provision/ack", headers=auth_headers(client, "e3"))
        assert r.status_code == 404

    def test_not_provisioned_reports_false(self, client, db):
        make_user(db, username="e4", email="e4@example.com")
        body = client.get(f"{BASE}/my-provision",
                          headers=auth_headers(client, "e4")).json()
        assert body["provisioned"] is False and body["initial_password"] is None

    def test_requires_authentication(self, client):
        assert client.get(f"{BASE}/my-provision").status_code == 401
        assert client.post(f"{BASE}/my-provision/ack").status_code == 401

    def test_cannot_see_another_users_password(self, client, db):
        """ZH: 身分一律由 JWT 推導——端點不吃任何身分參數，查不到別人的。"""
        victim = make_user(db, username="e5", email="e5@example.com")
        _account(db, victim, plaintext="VICTIM-SECRET-1")
        make_user(db, username="e6", email="e6@example.com")

        body = client.get(f"{BASE}/my-provision",
                          headers=auth_headers(client, "e6")).json()
        assert body["provisioned"] is False
        assert body["initial_password"] is None

    def test_ack_does_not_affect_another_user(self, client, db):
        victim = make_user(db, username="e7", email="e7@example.com")
        acc = _account(db, victim, plaintext="VICTIM-SECRET-2")
        make_user(db, username="e8", email="e8@example.com")

        client.post(f"{BASE}/my-provision/ack", headers=auth_headers(client, "e8"))

        db.refresh(acc)
        assert acc.init_pwd_enc is not None, "別人按確認把我的密碼清掉了"
        assert acc.init_pwd_ack == 0
