"""
ZH: 兩個歷史欄位的行為釘樁（v3.8）。

ZH: 這兩條守的都是「**下次有人好意動它**」的情況,不是現在會壞的東西。
"""
import io
import pathlib

from conftest import make_user

from app import models


REPO = pathlib.Path(__file__).resolve().parents[1]


class TestNoStartupDeletionOfTestAccounts:
    def test_main_does_not_bulk_delete_by_the_test_flag(self):
        """
        ZH: v3.8 移除了「每次服務啟動就刪掉所有 is_test_account=1 的帳號」。

        ZH: 移除的理由是它從來沒被觸發過（沒有任何一行把旗標設成 1）卻一直上著膛,
            而且它 `db.delete(u)` 直接刪、不走正規路徑（不封存 Lab、不解 FK）。

        ZH: 這條測試讀原始碼而不是跑 lifespan —— 開機事件在測試裡很難重現,
            而要防的東西（那個查詢重新出現）在原始碼層面看得一清二楚。
        """
        src = io.open(REPO / "job-scheduler" / "app" / "main.py", encoding="utf-8").read()
        code = "\n".join(l for l in src.splitlines() if not l.strip().startswith("#"))
        assert "is_test_account" not in code, (
            "main.py 又出現 is_test_account 的程式碼 —— "
            "開機批次刪帳號的機制被加回來了嗎？"
        )

    def test_the_flag_itself_still_exists(self):
        """ZH: 旗標保留 —— auth.py 用它把測試帳號排除在實體登入紀錄之外。"""
        assert "is_test_account" in models.User.__table__.columns

    def test_a_flagged_account_is_just_a_normal_row(self, db):
        """ZH: 帶旗標不再有任何破壞性後果。"""
        user = make_user(db)
        user.is_test_account = 1
        db.commit()
        db.refresh(user)
        assert user.is_test_account == 1
        assert db.query(models.User).filter_by(id=user.id).first() is not None


class TestOnlineStatusIsInert:
    def test_the_column_is_never_written(self, client, db):
        """
        ZH: `online_status` 自 v2.1 起 deprecated,而且**沒有任何地方寫它** ——
            所以它永遠是 0。讀它會得到「所有人都離線」這個錯誤但看起來合理的答案。

        ZH: 擁有者裁定保留欄位（2026-08-27）,所以這裡釘的是「它是惰性的」:
            登入一次之後它仍然是 0。哪天有人讓它開始有值,這條會紅 ——
            那時要一併決定「線上狀態的真相到底在哪」,不要變成兩個來源。
        """
        user = make_user(db)
        assert user.online_status == 0
        # ZH: 真的走一次登入 —— 那是唯一會更新「線上相關」欄位的路徑。
        #     不走的話這條就只是 0 == 0 的恆真斷言,守不住任何東西。
        resp = client.post("/api/v1/auth/login",
                           data={"username": "testuser", "password": "password123"})
        assert resp.status_code == 200, resp.text
        db.refresh(user)
        assert user.last_login_time is not None, "登入沒有寫 last_login_time —— 這條測試沒走到登入"
        assert user.online_status == 0, "有人開始寫 online_status 了；線上狀態會變成兩個真相"
