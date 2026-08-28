"""
ZH: 互動式 GPU 實驗室（v3.9）—— 獨佔鎖。

ZH: 這一支存在的理由：服務層那張卡有**兩個互不知情的分配者**——
      · 批次訓練由 `gpu-worker` 派，它只看自己行程內的 `_busy_gpus`
      · 互動式實驗室是長駐容器，worker 完全不知道它存在
    不擋的話兩邊會搶同一張卡，學生拿到 CUDA OOM 而且**看不出是被誰佔走**。

ZH: 因此要釘死的是：
      1. 實驗室借走卡之後，**同機** worker 領不到工作（任務留在佇列排隊）。
      2. **異地** worker 不受影響 —— 台北的節點有自己的卡。
         （這條是陽性對照：閘門寫成「有實驗室就全擋」的話，
           遠端節點會永遠領不到工作，而且沒有任何錯誤訊息。）
      3. 實驗室關掉／啟動失敗都要把卡還回去。
      4. 借不到卡時回 **409** 並講出是誰在用，不是 500。

ZH: ⚠ 容器層真正組 `device_requests` 的那幾行**這裡測不到**（假的 lifecycle
    把 `start()` 整個換掉了）。那部分是用真實容器實測的：
    2026-08-28 在 `cs-<admin>` 裡跑出 `cuda 可用: True` 並完成一次
    2048×2048 的 GPU 矩陣乘法。這裡只驗「`gpu_index` 有沒有被交下去」。
"""
import pytest

from app import crud, models
from app.services import lab_manager as lm
from app.routers.worker import TakeJobRequest, take_job
from conftest import make_user, auth_headers


class _FakeLifecycle:
    """ZH: 假的容器層 —— 只記下別人叫它做什麼，不碰真的 docker。"""

    def __init__(self):
        self.started = []
        self.stopped = []
        self.client = None

    # ZH: 命名規則用**真的那一份**，不要在假物件裡重抄
    _container_name = lm.CodeServerLifecycle._container_name
    _volume_name = lm.CodeServerLifecycle._volume_name

    def _ensure_volume(self, user_id, session=lm.DEFAULT_SESSION):
        return self._volume_name(user_id, session)

    def start(self, user_id, config):
        self.started.append((user_id, config))
        session = config.get("session", lm.DEFAULT_SESSION)
        return "cid-" + session, self._container_name(user_id, session)

    def stop(self, container_id):
        self.stopped.append(container_id)


@pytest.fixture
def fake_lc(monkeypatch):
    lc = _FakeLifecycle()
    monkeypatch.setattr(lm, "get_lifecycle", lambda: lc)
    monkeypatch.setattr(lm, "_wait_until_ready", lambda *a, **k: True)
    return lc


@pytest.fixture
def student(db):
    return make_user(db, username="gpustu", email="gpustu@example.com", role="student")


def _ask_for_work(db, same_host: bool):
    """ZH: 模擬 worker 來要工作。回領到的 job_id 或 None。"""
    r = take_job(TakeJobRequest(node_id="n1", shares_service_storage=same_host,
                                available_gpus=["0"], pool_type="batch"),
                 db=db, _=None)
    return (r["job"] or {}).get("job_id")


def _pending_job(db, user_id):
    j = models.TrainingJob(user_id=user_id, status="pending",
                           job_name="t", model_name="m", pool_type="batch")
    db.add(j)
    db.commit()
    db.refresh(j)
    return j


# ── 借卡與還卡 ──────────────────────────────────────────────────────────
class TestClaimAndRelease:
    def test_gpu_lab_claims_a_card_cpu_lab_does_not(self, db, student, fake_lc):
        """ZH: 不要 GPU 時行為必須與 v3.8 逐字相同 —— 不佔卡、不換映像。"""
        lm.start_session(db, student.id, want_gpu=False)
        row = db.query(models.LabSession).filter(
            models.LabSession.user_id == student.id).first()
        assert row.gpu_index is None
        assert "code-server-gpu" not in row.base_image
        assert crud.gpus_held_by_labs(db) == set()

        lm.stop_session(db, student.id)
        lm.start_session(db, student.id, want_gpu=True)
        db.expire_all()
        row = db.query(models.LabSession).filter(
            models.LabSession.user_id == student.id).first()
        assert row.gpu_index == 0
        assert "code-server-gpu" in row.base_image
        assert crud.gpus_held_by_labs(db) == {0}

    def test_the_card_index_is_handed_to_the_container_layer(self, db, student, fake_lc):
        """
        ZH: 容器層才是真的把 `--gpus` 掛上去的地方。這裡驗「有沒有交下去」——
            交錯的話容器會起來但沒有 GPU，而畫面上一切正常。
        """
        lm.start_session(db, student.id, want_gpu=True)
        _uid, cfg = fake_lc.started[-1]
        assert cfg["gpu_index"] == 0

        lm.stop_session(db, student.id)
        lm.start_session(db, student.id, want_gpu=False)
        _uid, cfg = fake_lc.started[-1]
        assert cfg["gpu_index"] is None, "CPU 實驗室竟然也帶了卡號"

    def test_stopping_releases_the_card(self, db, student, fake_lc):
        """
        ZH: ⚠ 這條要驗**欄位本身**，不能只驗 `gpus_held_by_labs`。
            那支只看 starting/running，所以停止之後就算欄位還留著舊卡號，
            它也照樣回空集合 —— 變異測試證實了這一點：
            把 `stop_session` 裡的 `row.gpu_index = None` 拿掉，
            第一版的這條測試**照樣過**。那等於沒測到。

        ZH: 清欄位的用途是**可查性**（見 stop_session 的註解）：
            留著舊卡號的話，查問題的人看不出這一列現在到底佔不佔卡。
        """
        lm.start_session(db, student.id, want_gpu=True)
        assert crud.gpus_held_by_labs(db) == {0}
        lm.stop_session(db, student.id)
        db.expire_all()
        assert crud.gpus_held_by_labs(db) == set()
        row = db.query(models.LabSession).filter(
            models.LabSession.user_id == student.id).first()
        assert row.gpu_index is None, "停止之後欄位還留著舊卡號"

    def test_a_failed_start_releases_the_card(self, db, student, monkeypatch, fake_lc):
        """
        ZH: 🔴 啟動失敗沒還卡的話，那一列會留著卡號 ——
            查問題的人看不出它到底佔不佔卡，而下次 reuse 這一列會帶著舊卡號。
        """
        def boom(*a, **k):
            raise RuntimeError("docker 掛了")
        monkeypatch.setattr(fake_lc, "start", boom)

        with pytest.raises(RuntimeError):
            lm.start_session(db, student.id, want_gpu=True)
        db.expire_all()
        row = db.query(models.LabSession).filter(
            models.LabSession.user_id == student.id).first()
        assert row.gpu_index is None
        assert crud.gpus_held_by_labs(db) == set()


# ── 借不到的時候 ────────────────────────────────────────────────────────
class TestGpuBusy:
    def test_second_gpu_lab_is_refused_with_reason_lab(self, db, student, fake_lc):
        other = make_user(db, username="gpustu2", email="gpustu2@example.com")
        lm.start_session(db, student.id, want_gpu=True)
        with pytest.raises(lm.GpuBusyError) as e:
            lm.start_session(db, other.id, want_gpu=True)
        assert e.value.reason == "lab"

    def test_running_job_blocks_the_lab_with_reason_job(self, db, student, fake_lc):
        j = _pending_job(db, student.id)
        j.status, j.gpu_id = "running", 0
        db.commit()
        with pytest.raises(lm.GpuBusyError) as e:
            lm.start_session(db, student.id, want_gpu=True)
        assert e.value.reason == "job"

    def test_a_pending_job_does_not_block_the_lab(self, db, student, fake_lc):
        """
        ZH: **陽性對照。** pending 還沒拿到卡 —— 把它也算成佔用的話，
            佇列裡只要有任務，實驗室就永遠借不到 GPU。
        """
        _pending_job(db, student.id)
        lm.start_session(db, student.id, want_gpu=True)   # 不該拋
        assert crud.gpus_held_by_labs(db) == {0}

    def test_cpu_lab_still_works_while_the_gpu_is_busy(self, db, student, fake_lc):
        """ZH: GPU 忙不該擋到一般實驗室 —— 那是使用者的退路。"""
        other = make_user(db, username="gpustu3", email="gpustu3@example.com")
        lm.start_session(db, student.id, want_gpu=True)
        lm.start_session(db, other.id, want_gpu=False)    # 不該拋
        assert crud.gpus_held_by_labs(db) == {0}

    def test_the_api_answers_409_not_500(self, client, db, student, fake_lc):
        """
        ZH: 🔴 借不到卡**不是故障**。回 500 的話使用者會以為平台壞了而去回報問題。
            409 + 講出是誰在用，他才知道是等一下就好還是該找管理員。
        """
        other = make_user(db, username="gpustu4", email="gpustu4@example.com")
        lm.start_session(db, other.id, want_gpu=True)
        h = auth_headers(client, "gpustu", "password123")
        r = client.post("/api/v1/lab/start", headers=h, json={"gpu": True})
        assert r.status_code == 409, r.text
        assert "實驗室" in r.json()["detail"]


# ── 派工閘門 ────────────────────────────────────────────────────────────
class TestDispatchGate:
    def test_same_host_worker_gets_nothing_while_a_lab_holds_the_card(
            self, db, student, fake_lc):
        j = _pending_job(db, student.id)
        assert _ask_for_work(db, same_host=True) == j.id, "前置：本來領得到"

        j.status, j.gpu_id = "pending", None
        db.commit()
        lm.start_session(db, student.id, want_gpu=True)
        assert _ask_for_work(db, same_host=True) is None, "實驗室佔著卡卻還派工"

    def test_remote_worker_is_not_blocked(self, db, student, fake_lc):
        """
        ZH: 🔴 **陽性對照，而且是最重要的一條。**
            閘門若寫成「有實驗室就全部擋」，台北那 30 台會永遠領不到工作，
            而且**不會有任何錯誤訊息** —— 只會看起來像沒人送單。
        """
        j = _pending_job(db, student.id)
        lm.start_session(db, student.id, want_gpu=True)
        assert _ask_for_work(db, same_host=False) == j.id

    def test_the_card_is_dispatchable_again_after_the_lab_stops(
            self, db, student, fake_lc):
        j = _pending_job(db, student.id)
        lm.start_session(db, student.id, want_gpu=True)
        assert _ask_for_work(db, same_host=True) is None

        lm.stop_session(db, student.id)
        db.expire_all()
        j.status, j.gpu_id = "pending", None
        db.commit()
        assert _ask_for_work(db, same_host=True) == j.id

    def test_a_cpu_lab_does_not_block_dispatch(self, db, student, fake_lc):
        """ZH: **陽性對照**：CPU 實驗室不佔卡，所以不該影響派工。"""
        j = _pending_job(db, student.id)
        lm.start_session(db, student.id, want_gpu=False)
        assert _ask_for_work(db, same_host=True) == j.id


# ── 卡號轉換 ────────────────────────────────────────────────────────────
class TestGpuIndexParsing:
    @pytest.mark.parametrize("raw,expected", [
        ("0", 0), (" 1 ", 1), (0, 0),
        ("GPU-2b3c", -1),      # ZH: 認不得的格式
        (None, -1), ("", -1),
    ])
    def test_gpu_index(self, raw, expected):
        """
        ZH: 認不得的格式回 -1 而不是拋錯 —— 這支只被「排除佔用中的卡」用到，
            寧可讓它通過也不要讓整個節點領不到工作。
        """
        from app.routers.worker import _gpu_index
        assert _gpu_index(raw) == expected
