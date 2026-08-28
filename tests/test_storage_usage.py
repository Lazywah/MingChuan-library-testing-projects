"""
ZH: 儲存用量的量測與回寫（v3.9）。

ZH: 🔴 這一支的來歷：`UserStorageState.current_size_gb` 在 v3.9 之前
    **沒有任何地方更新它** —— 欄位預設 0.0、建立 state 時寫 0.0，然後就沒有了。
    於是 `storage_lifecycle.daily_scan` 裡的

        if state.current_size_gb > effective_quota:

    永遠是 `0.0 > 10`，**「超配額 → 凍結」那條分支從上線到現在一次都沒有執行過**。
    數字是假的，流程看起來卻很完整 —— 學生看到「配額 10 GB」，
    實際上可以一直寫到把主機磁碟吃光。

ZH: 所以要釘的是：
      1. 量到的用量要**真的寫回**那個欄位。
      2. 量不到時**不要寫 0** —— 寫 0 的話 Docker 抖一下就會讓所有人歸零，
         而那看起來完全正常，沒有人會發現配額判定又失效了。
      3. 一個人的**每一份存檔**都要算進去（`archive_user_lab` 踩過同一個坑）。
      4. 數字對了之後，凍結分支要真的會動。

ZH: ⚠ 這裡不碰真的 docker：`_volume_size` 與 volumes.get 都換成假的。
    真實環境的驗證是 2026-08-28 手動做的 ——
    灌 600 MB 進 volume，掃描後用量由 0.339 → 0.925 GB。
"""
import pytest

from app import models
from app.services import lab_manager as lm, storage_lifecycle as sl
from conftest import make_user

GB = 1024 ** 3


def _vol(user_id, session=lm.DEFAULT_SESSION):
    """
    ZH: 用**真的那份命名規則**算 volume 名，不要在測試裡重抄一次。

    ZH: ⚠ `_volume_name` 是**實例方法**。第一版我把它當靜態的直接呼叫，
        於是 `user_id` 收到的其實是 session 名，名字全部對不上 ——
        測試因此紅得莫名其妙（`unmeasurable: 1`）。
    """
    return lm.CodeServerLifecycle._volume_name(None, user_id, session)


class _FakeVolumes:
    """ZH: 只有 `known` 裡的 volume 存在，其餘 volumes.get 會拋（＝沒開過那份存檔）。"""

    def __init__(self, known):
        self.known = set(known)

    def get(self, name):
        if name not in self.known:
            raise RuntimeError("no such volume")
        return object()


class _FakeClient:
    def __init__(self, known):
        self.volumes = _FakeVolumes(known)


class _FakeLc:
    _volume_name = lm.CodeServerLifecycle._volume_name

    def __init__(self, known):
        self.client = _FakeClient(known)


@pytest.fixture
def user(db):
    return make_user(db, username="stor1", email="stor1@example.com", role="student")


def _wire(monkeypatch, known, sizes):
    """ZH: known = 存在的 volume；sizes = {volume: bytes}（None 代表量不到）。"""
    monkeypatch.setattr(lm, "get_lifecycle", lambda: _FakeLc(known))
    monkeypatch.setattr(lm, "_volume_size", lambda v: sizes.get(v))


# ── 量測 ────────────────────────────────────────────────────────────────
class TestMeasure:
    def test_counts_every_workspace_not_just_default(self, db, user, monkeypatch):
        """
        ZH: 🔴 一個人可以有好幾份存檔。只算 default 的話，
            開了三份的人會被低估成三分之一 —— 而低估的方向正好是
            「不會觸發任何限制」，所以沒有人會發現。
            （`archive_user_lab` 當初就是只處理 `home_<uid>` 而留下孤兒 volume。）
        """
        db.add(models.LabSession(user_id=user.id, session_name="ws2",
                                 volume_name="x", base_image="i"))
        db.commit()
        d = _vol(user.id, lm.DEFAULT_SESSION)
        w = _vol(user.id, "ws2")
        _wire(monkeypatch, {d, w}, {d: 1 * GB, w: 2 * GB})

        assert lm.user_storage_bytes(db, user.id) == 3 * GB

    def test_missing_volumes_are_skipped(self, db, user, monkeypatch):
        """ZH: 沒開過的存檔沒有 volume —— 跳過，不是算成 0 也不是拋錯。"""
        d = _vol(user.id, lm.DEFAULT_SESSION)
        _wire(monkeypatch, {d}, {d: 5 * GB})
        assert lm.user_storage_bytes(db, user.id) == 5 * GB

    def test_returns_none_when_nothing_can_be_measured(self, db, user, monkeypatch):
        """
        ZH: 🔴 **量不到要回 None，不能回 0。**
            回 0 的話，Docker 出問題時每個人的用量都會變成 0，
            而 0 看起來完全正常 —— 配額判定會安靜地失效，
            這正是這整支測試要防的那一類問題再發生一次。
        """
        _wire(monkeypatch, set(), {})
        assert lm.user_storage_bytes(db, user.id) is None


# ── 回寫 ────────────────────────────────────────────────────────────────
class TestRefresh:
    def test_the_number_actually_lands_in_the_column(self, db, user, monkeypatch):
        d = _vol(user.id, lm.DEFAULT_SESSION)
        _wire(monkeypatch, {d}, {d: 2 * GB})
        db.add(models.LabSession(user_id=user.id, session_name=lm.DEFAULT_SESSION,
                                 volume_name=d, base_image="i"))
        db.commit()

        out = lm.refresh_storage_usage(db)
        assert out["updated"] == 1
        st = sl.get_or_create_state(db, user.id)
        assert st.current_size_gb == 2.0

    def test_unmeasurable_users_keep_their_previous_value(self, db, user, monkeypatch):
        """
        ZH: **陽性對照。** 上面那條若是因為「反正都會寫」而過，這條會抓到 ——
            量不到的人必須**保留上一次的值**，不能被覆蓋成 0。
        """
        db.add(models.LabSession(user_id=user.id, session_name=lm.DEFAULT_SESSION,
                                 volume_name="v", base_image="i"))
        db.commit()
        st = sl.get_or_create_state(db, user.id)
        st.current_size_gb = 7.5
        db.commit()

        _wire(monkeypatch, set(), {})          # 全部量不到
        out = lm.refresh_storage_usage(db)
        assert out["unmeasurable"] == 1
        db.expire_all()
        assert sl.get_or_create_state(db, user.id).current_size_gb == 7.5, "量不到卻把值蓋掉了"

    def test_users_who_never_opened_a_lab_are_not_scanned(self, db, monkeypatch):
        """ZH: 沒開過 Lab 的人沒有 volume，掃了必定沒有結果 —— 不要浪費在必定落空的查詢上。"""
        make_user(db, username="nolab", email="nolab@example.com")
        _wire(monkeypatch, set(), {})
        assert lm.refresh_storage_usage(db)["checked"] == 0


# ── 讓那條死掉的分支活過來 ──────────────────────────────────────────────
class TestQuotaBranchIsAliveAgain:
    def test_over_quota_now_freezes(self, db, user, monkeypatch):
        """
        ZH: 🔴 **這是整件事的重點。** 在 v3.9 之前這條分支的左邊永遠是 0.0，
            所以它從上線到現在一次都沒有執行過。
        """
        user.disk_quota_gb = 1
        d = _vol(user.id, lm.DEFAULT_SESSION)
        db.add(models.LabSession(user_id=user.id, session_name=lm.DEFAULT_SESSION,
                                 volume_name=d, base_image="i"))
        db.commit()
        _wire(monkeypatch, {d}, {d: 3 * GB})       # 3 GB > 1 GB

        lm.refresh_storage_usage(db)
        stats = sl.daily_scan(db)
        assert stats["active_to_frozen"] == 1
        assert sl.get_or_create_state(db, user.id).state == "frozen"

    def test_within_quota_is_left_alone(self, db, user, monkeypatch):
        """
        ZH: **陽性對照。** 上面那條若是因為「每個人都會被凍結」而過，這條會抓到。
        """
        user.disk_quota_gb = 10
        d = _vol(user.id, lm.DEFAULT_SESSION)
        db.add(models.LabSession(user_id=user.id, session_name=lm.DEFAULT_SESSION,
                                 volume_name=d, base_image="i"))
        db.commit()
        _wire(monkeypatch, {d}, {d: 3 * GB})       # 3 GB < 10 GB

        lm.refresh_storage_usage(db)
        stats = sl.daily_scan(db)
        assert stats["active_to_frozen"] == 0
        assert sl.get_or_create_state(db, user.id).state == "active"

    def test_the_scan_would_still_be_dead_without_the_refresh(self, db, user, monkeypatch):
        """
        ZH: 🔴 這條把**缺陷本身**釘起來：不先量用量就直接跑 daily_scan，
            `current_size_gb` 還是 0.0 → 明明已經 3 GB 超過 1 GB 的配額，
            卻**什麼都不會發生**。這就是 v3.9 之前每一天的實際狀況。

        ZH: 這也是為什麼 scheduler 裡量測要排在 daily_scan **前面**。
        """
        user.disk_quota_gb = 1
        d = _vol(user.id, lm.DEFAULT_SESSION)
        db.add(models.LabSession(user_id=user.id, session_name=lm.DEFAULT_SESSION,
                                 volume_name=d, base_image="i"))
        db.commit()
        _wire(monkeypatch, {d}, {d: 3 * GB})

        stats = sl.daily_scan(db)                  # 故意不先 refresh
        assert stats["active_to_frozen"] == 0
        assert sl.get_or_create_state(db, user.id).current_size_gb == 0.0
