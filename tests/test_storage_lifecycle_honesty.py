"""
ZH: 儲存生命週期 —— 它到底做了什麼、以及它**不**做什麼（v3.8）。

ZH: 這一整支的來歷（2026-08-27 稽核）：
      · `freeze()` 的 docstring 寫「切到 frozen 狀態（**唯讀模式**）」，
        但它只改 `user_storage_state.state`，**使用者照樣讀寫**。
      · `archive()` 更嚴重：它算出 `/data/archive/home_<uid>.tar.gz`、
        把那個路徑寫進 DB **與管理稽核**、log 印「archived → …」，
        然後 return True —— 而那個檔案**從來沒有被建立過**。
        真正的危險不是「沒備份」，是**有人相信那個備份存在**而去砍掉 volume。
      · 管理端那四支端點**全部忽略回傳值**，一律回 `{"status": "…"}`，
        連函式明確拒絕的情況也報成功。

ZH: 這裡釘的是「誠實」，不是「功能完整」——
    真的要實作 archive 是另一件事（擁有者尚未決定）。
"""
import pytest

from app import crud, models
from app.services import storage_lifecycle as sl
from conftest import make_user, auth_headers


@pytest.fixture
def user(db):
    return make_user(db, username="stor", email="stor@example.com")


# ── archive：拒絕，而不是記錄一件沒發生的事 ─────────────────────────
class TestArchiveRefuses:
    def test_archive_refuses_and_changes_nothing(self, db, user):
        """
        ZH: 🔴 核心：實際打包還沒實作 → 一律拒絕，
            **不改狀態、不寫 archive_path、不寫稽核**。
        """
        sl.freeze(db, user.id)                       # 先進 frozen（archive 的前置條件）
        audits_before = db.query(models.AdminAction).count()

        assert sl.archive(db, user.id, admin_id="admin-1") is False

        st = sl.get_or_create_state(db, user.id)
        assert st.state == "frozen", "被拒絕了卻改了狀態"
        assert not st.archive_path, "寫了一個不存在的檔案路徑"
        assert db.query(models.AdminAction).count() == audits_before, \
            "被拒絕了卻留下一筆『已歸檔』的稽核"

    def test_the_guards_still_run_and_are_distinguishable(self, db, user):
        """
        ZH: 「不是 frozen 狀態」要與「未實作」分得出來 ——
            兩者都回 False，但日誌訊息不同，維運才查得下去。
            這裡至少確認前置守衛沒有被我的改動跳過。
        """
        # ZH: active 狀態直接被守衛擋下（連「未實作」那一步都走不到）
        assert sl.archive(db, user.id, admin_id="admin-1") is False
        assert sl.get_or_create_state(db, user.id).state == "active"


# ── freeze：行為不變，但不可以宣稱擋住了 ────────────────────────────
class TestFreezeIsOnlyAMarker:
    def test_freeze_still_marks_the_state(self, db, user):
        """ZH: 行為刻意不動 —— 每日排程會自動呼叫它，改成拋錯會打斷迴圈。"""
        assert sl.freeze(db, user.id, reason="quota_exceeded") is True
        assert sl.get_or_create_state(db, user.id).state == "frozen"

    def test_nothing_outside_this_module_reads_the_state(self):
        """
        ZH: 這條釘的是「為什麼 frozen 目前只是帳面紀錄」——
            `user_storage_state` 除了管理端的列表之外沒有人在讀，
            所以沒有任何地方會因為 frozen 而限制使用者。

        ZH: 哪天真的做了限制（例如登入時擋、Lab 掛載改唯讀），
            這條會失敗 —— 那時候請**連同 freeze 的 docstring 一起改**，
            而不是只把這個測試刪掉。
        """
        import pathlib
        import re
        root = pathlib.Path(sl.__file__).parent.parent
        hits = []
        for f in root.rglob("*.py"):
            if f.name in ("storage_lifecycle.py", "models.py"):
                continue
            src = f.read_text(encoding="utf-8")
            # ZH: 只找「真的讀狀態」的用法，不算 import 與管理端的列表端點
            for m in re.finditer(r'UserStorageState', src):
                line = src[:m.start()].count("\n") + 1
                ctx = src.split("\n")[line - 1]
                if "list_storage_states" in ctx or ctx.strip().startswith("#"):
                    continue
                hits.append(f"{f.name}:{line}")
        assert not [h for h in hits if not h.startswith("admin.py")], \
            f"有地方開始讀 storage state 了，請一併更新 freeze 的說明：{hits}"


# ── 管理端端點：不可以報假的成功 ────────────────────────────────────
class TestAdminEndpointsReportTruthfully:
    @pytest.fixture
    def adm(self, client, db):
        make_user(db, username="admin", email="admin@example.com", role="admin")
        return auth_headers(client, "admin", "password123")

    def test_archive_endpoint_reports_failure(self, client, db, adm, user):
        """
        ZH: 🔴 改之前這裡永遠回 `{"status": "archived"}` ——
            管理員會以為歸檔好了，然後去做下一步（例如砍 volume）。
        """
        sl.freeze(db, user.id)
        r = client.post("/api/v1/admin/storage/archive",
                        json={"user_id": user.id, "reason": "audit"}, headers=adm)
        assert r.status_code == 409, r.text
        assert "未歸檔" in r.json()["detail"]

    def test_freeze_endpoint_says_it_is_not_enforced(self, client, db, adm, user):
        """ZH: 回傳裡要明講「只是標記、沒有真的擋住」，否則管理者會誤判。"""
        r = client.post("/api/v1/admin/storage/freeze",
                        json={"user_id": user.id, "reason": "audit"}, headers=adm)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "frozen"
        assert body["enforced"] is False, "沒有講出『尚未真的擋住』"

    def test_freeze_endpoint_reports_unchanged_on_repeat(self, client, db, adm, user):
        """
        ZH: **陽性對照** —— 上面那條若是因為「永遠回 frozen」而過，
            就證明不了端點有在看回傳值。重複凍結時 `freeze()` 回 False，
            端點必須說 `unchanged`。
        """
        client.post("/api/v1/admin/storage/freeze",
                    json={"user_id": user.id, "reason": "audit"}, headers=adm)
        r = client.post("/api/v1/admin/storage/freeze",
                        json={"user_id": user.id, "reason": "audit"}, headers=adm)
        assert r.json()["status"] == "unchanged", r.text
