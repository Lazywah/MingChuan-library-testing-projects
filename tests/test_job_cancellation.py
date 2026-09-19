# -*- coding: utf-8 -*-
"""
ZH: v4.14（方案二 2.2）取消／停止機制。

ZH: 這一整套在防的是**同一件事**：平台認為結束了，而容器還在跑。
    在此之前那個落差沒有任何機制去彌合 ——
      · 取消只准取消還沒開跑的單
      · 逾時只把資料庫標成 failed，沒有人去停容器
      · 而那個殭屍跑完會回報 completed，把 failed 翻回去

@node tests/test_job_cancellation.py
"""
import pytest

from app import crud, models
from conftest import make_user

# ZH: 與 tests/test_api.py 同一組 —— worker 端點走 Authorization: Bearer。
WORKER_HEADERS = {"Authorization": "Bearer test-worker-token-16c"}


def _mk_job(db, job_id, status):
    """ZH: 建一張指定狀態的單。

    ZH: ⚠ 一定要有**真的**使用者 —— 測試引擎與正式環境一樣開著外鍵約束
        （conftest 的 `_fk_on`），隨手塞一個 user_id 會 IntegrityError。

    @node tests/test_job_cancellation.py::_mk_job
    """
    user = db.query(models.User).first() or make_user(db)
    job = models.TrainingJob(id=job_id, user_id=user.id, job_name="t",
                             model_name="m", status=status, priority=0)
    db.add(job)
    db.commit()
    return job


# ==============================================================================
# ZH: 終態守衛
# ==============================================================================
class TestTerminalStateGuard:
    """ZH: 終態不可逆 —— 殭屍容器的回報不能覆蓋平台的判定。"""

    def _job(self, db, status="running"):
        """@node tests/test_job_cancellation.py::TestTerminalStateGuard._job"""
        return _mk_job(db, "j-" + status, status)

    @pytest.mark.parametrize("terminal", ["failed", "cancelled", "completed"])
    def test_zombie_cannot_revive_a_terminal_job(self, db, terminal):
        """ZH: 🔴 這是本次修正的核心：逾時標成 failed 之後，還在跑的容器
            跑完回報 completed —— 必須被擋下來。"""
        job = self._job(db, terminal)
        crud.update_job_status(db, job.id, status="completed")
        db.refresh(job)
        assert job.status == terminal

    def test_running_to_terminal_still_works(self, db):
        """ZH: 守衛不能擋住正常的結束路徑。"""
        job = self._job(db, "running")
        crud.update_job_status(db, job.id, status="completed")
        db.refresh(job)
        assert job.status == "completed"

    def test_same_terminal_status_is_not_a_violation(self, db):
        """ZH: worker 的 report_update 會重試，同一個終態送兩次是正常的。"""
        job = self._job(db, "completed")
        crud.update_job_status(db, job.id, status="completed")
        db.refresh(job)
        assert job.status == "completed"

    def test_completed_at_is_not_overwritten(self, db):
        """ZH: 不只狀態 —— 時間戳被蓋掉的話，「它其實在 14:00 就被判逾時了」
            這個事實也跟著不見。"""
        job = self._job(db, "running")
        crud.update_job_status(db, job.id, status="failed")
        db.refresh(job)
        first = job.completed_at
        assert first is not None
        crud.update_job_status(db, job.id, status="completed")
        db.refresh(job)
        assert job.completed_at == first


# ==============================================================================
# ZH: 取消
# ==============================================================================
class TestCancelRunning:
    """ZH: running 也要取消得掉。"""

    def _job(self, db, status):
        """@node tests/test_job_cancellation.py::TestCancelRunning._job"""
        return _mk_job(db, "c-" + status, status)

    @pytest.mark.parametrize("status", ["pending", "queued", "running"])
    def test_cancellable_states(self, db, status):
        """ZH: running 是本次新增的 —— 在此之前它不在這份清單裡。"""
        job = self._job(db, status)
        assert crud.cancel_job(db, job.id) is not None
        db.refresh(job)
        assert job.status == "cancelled"

    @pytest.mark.parametrize("status", ["completed", "failed", "cancelled"])
    def test_finished_jobs_are_not_cancellable(self, db, status):
        """ZH: 已經結束的沒有東西可以取消。"""
        job = self._job(db, status)
        assert crud.cancel_job(db, job.id) is None


# ==============================================================================
# ZH: 指令通道
# ==============================================================================
class TestControlEndpoint:
    """ZH: worker 問「這張單還要不要跑」。"""

    def _mk(self, db, job_id, status):
        """@node tests/test_job_cancellation.py::TestControlEndpoint._mk"""
        _mk_job(db, job_id, status)

    def _get(self, client, job_id):
        """@node tests/test_job_cancellation.py::TestControlEndpoint._get"""
        return client.get("/api/v1/worker/jobs/%s/control" % job_id,
                          headers=WORKER_HEADERS)

    @pytest.mark.parametrize("status,expected", [
        ("pending", "continue"),
        ("running", "continue"),
        ("cancelled", "stop"),
        ("failed", "stop"),
        ("completed", "stop"),
    ])
    def test_action_follows_status(self, client, db, status, expected):
        """@node tests/test_job_cancellation.py::TestControlEndpoint.test_action_follows_status"""
        self._mk(db, "ctl-" + status, status)
        r = self._get(client, "ctl-" + status)
        assert r.status_code == 200
        assert r.json()["action"] == expected

    def test_unknown_job_is_told_to_stop(self, client):
        """ZH: 資料庫裡沒有這張單 = 孤兒容器，沒有人在等它的結果卻佔著一張卡。"""
        r = self._get(client, "does-not-exist")
        assert r.status_code == 200
        assert r.json()["action"] == "stop"

    def test_control_requires_the_worker_token(self, client):
        """ZH: 這支能讓別人停掉任意一張單，不能是公開的。"""
        r = client.get("/api/v1/worker/jobs/whatever/control")
        assert r.status_code in (401, 403, 422)
