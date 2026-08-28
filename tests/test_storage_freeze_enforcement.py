"""
ZH: 凍結第一次真的擋住人（v3.9 乙）。

ZH: 🔴 來歷：v3.9 甲讓「超配額 → 凍結」真的會觸發之後，出現一個新的問題 ——
    管理者按下凍結、或排程自動凍結，**對方毫無感覺照樣讀寫**
    （`state` 除了管理端列表之外沒有人在讀）。
    管理者以為擋住了、學生不知道自己被凍結，**兩邊認知不一致比兩邊都沒有更糟**。

ZH: 🔴 但「只做擋住」會造出更糟的陷阱：
    唯一的解凍路徑本來是 `restore()`，要**管理員手動**操作。
    學生刪完檔案還是進不來，而凍結滿 30 天會自動走向 `archived` ——
    卡住的人會一路往下掉。
    所以擋住與自動解凍**必須一起上線**，這一支同時釘住兩邊。

ZH: 最重要的一條在 `TestManualFreezeIsNeverAutoUndone` ——
    **自動解凍絕對不可以撤銷管理員的處置。**
"""
import pytest

from app import models
from app.services import lab_manager as lm, storage_lifecycle as sl
from conftest import make_user, auth_headers

GB = 1024 ** 3


class _FakeVolumes:
    def __init__(self, known):
        self.known = set(known)

    def get(self, name):
        if name not in self.known:
            raise RuntimeError("no such volume")
        return object()


class _FakeLc:
    _container_name = lm.CodeServerLifecycle._container_name
    _volume_name = lm.CodeServerLifecycle._volume_name

    def __init__(self, known, sizes):
        self.client = type("C", (), {"volumes": _FakeVolumes(known)})()
        self.started = []

    def _ensure_volume(self, user_id, session=lm.DEFAULT_SESSION):
        return self._volume_name(user_id, session)

    def start(self, user_id, config):
        self.started.append((user_id, config))
        return "cid", self._container_name(user_id, config.get("session", lm.DEFAULT_SESSION))

    def stop(self, container_id):
        pass


def _vol(user_id, session=lm.DEFAULT_SESSION):
    """ZH: 用真的那份命名規則。`_volume_name` 是**實例方法**，要補 self。"""
    return lm.CodeServerLifecycle._volume_name(None, user_id, session)


@pytest.fixture
def user(db):
    u = make_user(db, username="frz", email="frz@example.com", role="student")
    u.disk_quota_gb = 1
    db.add(models.LabSession(user_id=u.id, session_name=lm.DEFAULT_SESSION,
                             volume_name=_vol(u.id), base_image="i"))
    db.commit()
    return u


@pytest.fixture
def wire(monkeypatch):
    """ZH: 回一個可以改用量的開關 —— 模擬學生刪檔案。"""
    state = {"size": 3 * GB}
    d_holder = {}

    def _apply(user_id):
        d = _vol(user_id)
        d_holder["d"] = d
        lc = _FakeLc({d}, None)
        monkeypatch.setattr(lm, "get_lifecycle", lambda: lc)
        monkeypatch.setattr(lm, "_wait_until_ready", lambda *a, **k: True)
        monkeypatch.setattr(lm, "_volume_size", lambda v: state["size"])
        return lc

    _apply.state = state
    return _apply


# ── 擋住 ────────────────────────────────────────────────────────────────
class TestFrozenBlocksTheLab:
    def test_over_quota_user_cannot_start(self, db, user, wire):
        wire(user.id)
        lm.refresh_storage_usage(db)
        sl.daily_scan(db)
        assert sl.get_or_create_state(db, user.id).state == "frozen"

        with pytest.raises(lm.StorageFrozenError) as e:
            lm.start_session(db, user.id)
        assert e.value.reason == "quota_exceeded"
        # ZH: 訊息要帶得出數字 —— 使用者才知道要刪多少。
        assert e.value.used_gb == 3.0
        assert e.value.quota_gb == 1

    def test_an_active_user_is_not_blocked(self, db, user, wire):
        """ZH: **陽性對照** —— 沒被凍結的人必須照常開得起來。"""
        w = wire(user.id)
        wire.state["size"] = 0            # 沒超過
        lm.refresh_storage_usage(db)
        sl.daily_scan(db)
        assert sl.get_or_create_state(db, user.id).state == "active"
        lm.start_session(db, user.id)     # 不該拋
        assert w.started

    def test_the_api_answers_409_with_the_numbers(self, client, db, user, wire):
        """
        ZH: 🔴 訊息裡**一定要有數字**。只說「你的儲存被凍結」的話，
            使用者不知道要刪到多少才夠，只能來問管理員 ——
            那等於把問題丟回給管理員，凍結就失去意義了。
        """
        wire(user.id)
        lm.refresh_storage_usage(db)
        sl.daily_scan(db)
        h = auth_headers(client, "frz", "password123")
        r = client.post("/api/v1/lab/start", headers=h, json={})
        assert r.status_code == 409, r.text
        d = r.json()["detail"]
        assert "3.0 GB" in d and "1 GB" in d
        assert "2.0" in d, f"沒有告訴他要刪多少：{d}"


# ── 自己回來 ────────────────────────────────────────────────────────────
class TestUserCanRecoverWithoutAnAdmin:
    def test_deleting_files_lets_them_back_in_immediately(self, db, user, wire):
        """
        ZH: 🔴 這條是「擋住」能不能上線的前提。
            沒有它的話，學生刪完檔案還是進不來，只能等管理員手動 restore ——
            而凍結滿 30 天會自動走向 archived。**那比不擋更糟。**

        ZH: 而且要**當場**生效，不能等隔天的排程 ——
            刪完檔案會馬上想重開，等到隔天 03:00 說不過去。
        """
        wire(user.id)
        lm.refresh_storage_usage(db)
        sl.daily_scan(db)
        assert sl.get_or_create_state(db, user.id).state == "frozen"

        wire.state["size"] = 0            # 學生刪掉檔案
        lm.start_session(db, user.id)     # 不該拋
        assert sl.get_or_create_state(db, user.id).state == "active"

    def test_the_daily_scan_also_unfreezes(self, db, user, wire):
        """ZH: 沒有主動重開的人，隔天的排程也要把他放出來。"""
        wire(user.id)
        lm.refresh_storage_usage(db)
        sl.daily_scan(db)
        assert sl.get_or_create_state(db, user.id).state == "frozen"

        wire.state["size"] = 0
        lm.refresh_storage_usage(db)
        stats = sl.daily_scan(db)
        assert stats["frozen_to_active"] == 1
        assert sl.get_or_create_state(db, user.id).state == "active"

    def test_still_over_quota_stays_frozen(self, db, user, wire):
        """ZH: **陽性對照** —— 刪得不夠多的人不可以被放出來。"""
        wire(user.id)
        lm.refresh_storage_usage(db)
        sl.daily_scan(db)

        wire.state["size"] = 2 * GB       # 還是 > 1 GB
        lm.refresh_storage_usage(db)
        assert sl.auto_unfreeze(db, user.id) is False
        assert sl.get_or_create_state(db, user.id).state == "frozen"

    def test_exactly_at_quota_is_released(self, db, user, wire):
        """
        ZH: freeze 的判定是 `size > quota`，所以解凍要用完全互補的 `<= quota`。
            兩邊都用 `>` / `<` 的話，剛好等於配額的人會在凍結與解凍之間來回震盪。
        """
        wire(user.id)
        lm.refresh_storage_usage(db)
        sl.daily_scan(db)
        wire.state["size"] = 1 * GB       # 剛好等於配額
        lm.refresh_storage_usage(db)
        assert sl.auto_unfreeze(db, user.id) is True


# ── 絕對不可以撤銷管理員的處置 ──────────────────────────────────────────
class TestManualFreezeIsNeverAutoUndone:
    def test_manual_freeze_survives_auto_unfreeze(self, db, user, wire):
        """
        ZH: 🔴 **這一條最重要。** 自動解凍把管理員的處置撤銷掉，
            是這整個功能最不該發生的事 —— 管理者會以為自己擋住了某人，
            而系統在隔天早上把他放了出來，沒有任何通知。
        """
        wire(user.id)
        wire.state["size"] = 0            # 用量遠低於配額
        lm.refresh_storage_usage(db)
        adm = make_user(db, username="frzadm", email="frzadm@example.com", role="admin")
        sl.freeze(db, user.id, admin_id=adm.id, reason="manual")

        assert sl.auto_unfreeze(db, user.id) is False
        assert sl.daily_scan(db)["frozen_to_active"] == 0
        assert sl.get_or_create_state(db, user.id).state == "frozen"

    def test_manual_freeze_tells_them_to_contact_an_admin(self, client, db, user, wire):
        """ZH: 管理員凍結的人不會自己解開 —— 不能叫他去刪檔案，要叫他找管理員。"""
        wire(user.id)
        wire.state["size"] = 0
        lm.refresh_storage_usage(db)
        adm = make_user(db, username="frzadm2", email="frzadm2@example.com", role="admin")
        sl.freeze(db, user.id, admin_id=adm.id, reason="manual")

        h = auth_headers(client, "frz", "password123")
        r = client.post("/api/v1/lab/start", headers=h, json={})
        assert r.status_code == 409
        d = r.json()["detail"]
        assert "管理員" in d
        assert "刪" not in d, f"叫他去刪檔案，但刪了也解不開：{d}"

    def test_inactive_90d_freeze_is_not_auto_undone_either(self, db, user, wire):
        """ZH: 90 天未登入凍結的條件跟用量無關，刪檔案不該讓他回來。"""
        wire(user.id)
        wire.state["size"] = 0
        lm.refresh_storage_usage(db)
        sl.freeze(db, user.id, reason="inactive_90d")
        assert sl.auto_unfreeze(db, user.id) is False

    def test_unknown_reason_is_not_auto_undone(self, db, user, wire):
        """
        ZH: `frozen_reason` 是 v3.9 才加的，**舊資料是 NULL**。
            不知道是誰凍的就不要自作主張 —— 往安全的方向倒。
        """
        wire(user.id)
        wire.state["size"] = 0
        lm.refresh_storage_usage(db)
        st = sl.get_or_create_state(db, user.id)
        st.state, st.frozen_reason = "frozen", None
        db.commit()
        assert sl.auto_unfreeze(db, user.id) is False
