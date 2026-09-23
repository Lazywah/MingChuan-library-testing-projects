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

ZH: 🔴 v4.23 改掉 v3.9 留下的一條死路：**超配額的人本來連實驗室都開不了**，
    而 home volume 裡的檔案**只能從實驗室裡刪**（平台沒有別的檔案管理介面）。
    於是：超配額 → 進不去 → 刪不掉 → 永遠出不來，凍滿 30 天還會往 archived 掉。
    現在超配額走**清理模式**：進得去，但不給 GPU、不給開新存檔。
    管理員手動凍結／90 天未登入仍然整個擋住 —— 那是處置，出路是找管理員。

ZH: v4.23 同時把守衛補到另外兩條會讓佔用長大的路：上傳資料集、送訓練任務。
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
    def test_over_quota_user_may_enter_to_clean_up(self, db, user, wire):
        """
        ZH: 🔴 超配額的人**進得去**（v4.23）—— 那是他唯一的清理工具。
            擋掉的話他刪不了檔案，就永遠出不來（v3.9 的死路）。
        ZH: 但他還是 frozen —— 「放他進來」不等於「解開了」。
        """
        w = wire(user.id)
        lm.refresh_storage_usage(db)
        sl.daily_scan(db)
        assert sl.get_or_create_state(db, user.id).state == "frozen"

        out = lm.start_session(db, user.id)
        assert w.started
        assert out["storage_cleanup_mode"] is True, "進來了卻沒講這是清理模式"
        assert sl.get_or_create_state(db, user.id).state == "frozen"

    def test_over_quota_user_cannot_take_a_gpu(self, db, user, wire):
        """ZH: 清理模式不給 GPU —— 超配額的人先整理，卡讓給別人。"""
        wire(user.id)
        lm.refresh_storage_usage(db)
        sl.daily_scan(db)

        with pytest.raises(lm.StorageFrozenError) as e:
            lm.start_session(db, user.id, want_gpu=True)
        assert e.value.blocked == "lab_gpu"
        # ZH: 訊息要帶得出數字 —— 使用者才知道要刪多少。
        assert e.value.used_gb == 3.0 and e.value.quota_gb == 1

    def test_over_quota_user_cannot_open_a_new_workspace(self, db, user, wire):
        """ZH: 開新存檔是「再長大」，不是清理 —— 既有的那幾份才給開。"""
        wire(user.id)
        lm.refresh_storage_usage(db)
        sl.daily_scan(db)

        with pytest.raises(lm.StorageFrozenError) as e:
            lm.start_session(db, user.id, session="another")
        assert e.value.blocked == "lab_new_session"

    def test_the_default_workspace_is_not_treated_as_new(self, db, user, wire):
        """ZH: 預設那一份是主要工作區，不是「新存檔」——
           它的 DB 列不在時也要放他進來，不然他連清理都做不到。"""
        wire(user.id)
        lm.refresh_storage_usage(db)
        sl.daily_scan(db)
        db.query(models.LabSession).filter(
            models.LabSession.user_id == user.id,
            models.LabSession.session_name == lm.DEFAULT_SESSION).delete()
        db.commit()

        out = lm.start_session(db, user.id)          # 不該拋
        assert out["storage_cleanup_mode"] is True

    def test_admin_freeze_still_blocks_the_lab_entirely(self, db, user, wire):
        """ZH: **陽性對照** —— 清理模式只給超配額，管理員的處置不受影響。"""
        wire(user.id)
        wire.state["size"] = 0
        lm.refresh_storage_usage(db)
        adm = make_user(db, username="frzadm0", email="frzadm0@example.com", role="admin")
        sl.freeze(db, user.id, admin_id=adm.id, reason="manual")

        with pytest.raises(lm.StorageFrozenError) as e:
            lm.start_session(db, user.id)
        assert e.value.blocked == "lab"

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
        # ZH: v4.23 之後一般實驗室是放行的（清理模式），所以這裡打 GPU ——
        #     被擋的那一刻訊息裡**一定要有數字**，這才是這條要釘的事。
        r = client.post("/api/v1/lab/start", headers=h, json={"gpu": True})
        assert r.status_code == 409, r.text
        d = r.json()["detail"]
        assert "3.0 GB" in d and "1 GB" in d
        assert "2.0" in d, f"沒有告訴他要刪多少：{d}"
        assert "CPU" in d, f"沒告訴他還能開一般實驗室整理：{d}"


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


# ── 會讓佔用長大的另外兩條路（v4.23）────────────────────────────────────
class TestTheOtherWritePaths:
    """
    ZH: 🔴 只擋實驗室是擋不住的：超配額的人照樣可以上傳資料集、送訓練任務，
        而那兩件事都會讓佔用再長大。v3.9 只做了實驗室那一條。

    ZH: 判準是**會不會讓佔用變多**，不是「是不是寫入」——
        刪檔案也是寫入，但那正是我們要他去做的事。
    """

    def _freeze(self, db, user, wire):
        """@node tests/test_storage_freeze_enforcement.py::TestTheOtherWritePaths._freeze"""
        wire(user.id)
        lm.refresh_storage_usage(db)
        sl.daily_scan(db)
        assert sl.get_or_create_state(db, user.id).state == "frozen"

    def test_upload_is_refused_with_the_numbers(self, client, db, user, wire):
        self._freeze(db, user, wire)
        h = auth_headers(client, "frz", "password123")
        r = client.post("/api/v1/datasets/upload", headers=h,
                        files={"file": ("d.csv", b"a,b\n1,2\n", "text/csv")})
        assert r.status_code == 409, r.text
        d = r.json()["detail"]
        assert "3.0 GB" in d and "1 GB" in d and "2.0" in d

    def test_job_submit_is_refused(self, client, db, user, wire):
        self._freeze(db, user, wire)
        h = auth_headers(client, "frz", "password123")
        r = client.post("/api/v1/jobs", headers=h, json={
            "job_name": "t", "model_name": "m", "gpu_required": 1,
            "config": {"epochs": 1}})
        assert r.status_code == 409, r.text
        assert "3.0 GB" in r.json()["detail"]

    def test_an_active_user_is_not_refused(self, client, db, user, wire):
        """ZH: **陽性對照** —— 沒被凍結的人不可以被這道守衛擋到。"""
        w = wire(user.id)
        wire.state["size"] = 0
        lm.refresh_storage_usage(db)
        sl.daily_scan(db)
        h = auth_headers(client, "frz", "password123")
        r = client.post("/api/v1/datasets/upload", headers=h,
                        files={"file": ("d.csv", b"a,b\n1,2\n", "text/csv")})
        assert r.status_code != 409, r.text

    def test_admin_frozen_user_is_told_to_ask_an_admin(self, client, db, user, wire):
        """ZH: 管理員凍結的人刪檔案也解不開 —— 這兩條路的措辭也不能叫他去刪。"""
        wire(user.id)
        wire.state["size"] = 0
        lm.refresh_storage_usage(db)
        adm = make_user(db, username="frzadm3", email="frzadm3@example.com", role="admin")
        sl.freeze(db, user.id, admin_id=adm.id, reason="manual")

        h = auth_headers(client, "frz", "password123")
        r = client.post("/api/v1/jobs", headers=h, json={
            "job_name": "t", "model_name": "m", "gpu_required": 1,
            "config": {"epochs": 1}})
        assert r.status_code == 409
        d = r.json()["detail"]
        assert "管理員" in d and "刪" not in d


# ── 關掉實驗室的那一刻重量（v4.23）──────────────────────────────────────
class TestStoppingTheLabReMeasures:
    """
    ZH: 🔴 清理模式的出口就在這裡：他刪完檔案會把實驗室關掉，
        那一刻重量最準，也最省事 —— 不必為了解凍再開一次。
        沒有這一段的話，他得等隔天 03:00，而中間完全不知道自己解開了沒。
    """

    def test_deleting_then_stopping_unfreezes(self, db, user, wire):
        wire(user.id)
        lm.refresh_storage_usage(db)
        sl.daily_scan(db)
        lm.start_session(db, user.id)          # 清理模式進來
        assert sl.get_or_create_state(db, user.id).state == "frozen"

        wire.state["size"] = 0                 # 他刪掉檔案
        assert lm.stop_session(db, user.id) is True
        assert sl.get_or_create_state(db, user.id).state == "active"

    def test_still_over_quota_stays_frozen_after_stop(self, db, user, wire):
        """ZH: **陽性對照** —— 刪得不夠多的人，關掉實驗室也不會被放出來。"""
        wire(user.id)
        lm.refresh_storage_usage(db)
        sl.daily_scan(db)
        lm.start_session(db, user.id)

        wire.state["size"] = 2 * GB            # 還是 > 1 GB
        lm.stop_session(db, user.id)
        assert sl.get_or_create_state(db, user.id).state == "frozen"

    def test_measuring_failure_does_not_break_stopping(self, db, user, wire, monkeypatch):
        """
        ZH: 🔴 量測要跑 docker exec du，會失敗也會慢。
            不能讓「量不到」變成「關不掉實驗室」—— 那會把使用者困在計時的 session 裡。
        """
        wire(user.id)
        lm.refresh_storage_usage(db)
        sl.daily_scan(db)
        lm.start_session(db, user.id)

        def _boom(*a, **k):
            """@node tests/test_storage_freeze_enforcement.py::TestStoppingTheLabReMeasures.<nested>._boom"""
            raise RuntimeError("docker 掛了")

        monkeypatch.setattr(lm, "refresh_storage_usage", _boom)
        assert lm.stop_session(db, user.id) is True
