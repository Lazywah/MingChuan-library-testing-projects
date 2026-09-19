# -*- coding: utf-8 -*-
"""
ZH: v4.17（方案二 2.4）配額：admission 與 placement 分層。

ZH: 改動的形狀是「把容量判斷從**送單**搬到**派工**」：
      · 送單一律收下 → 進佇列（使用者看到的是「你排第幾位」不是 429）
      · 派工時才看配額，而且看的是**每人**幾張，不是叢集幾張

ZH: 🔴 為什麼不是叢集幾張：容量本來就由「有幾張空卡」決定
    （worker 只在有空卡時才來領工作）。舊的叢集上限預設 4 ——
    30 台上線那天會有 26 台因為那一行空著。

@node tests/test_job_quota.py
"""
import pytest

from app import crud, models, schemas
from conftest import make_user

WORKER_HEADERS = {"Authorization": "Bearer test-worker-token-16c"}


def _submit(db, user, name="j"):
    """@node tests/test_job_quota.py::_submit"""
    return crud.create_job(
        db, schemas.JobCreate(job_name=name, model_name="m"), user.id)


def _take(client, node="node-q"):
    """@node tests/test_job_quota.py::_take"""
    return client.post("/api/v1/worker/take",
                       json={"node_id": node, "available_gpus": ["0"]},
                       headers=WORKER_HEADERS).json()["job"]


class TestSubmitNoLongerRejects:
    """ZH: 送單不再因為「叢集忙」而拒絕。"""

    def test_submitting_many_is_accepted(self, client, db):
        """ZH: 🔴 這是行為改變：以前第 5 張會拿到 429。"""
        user = make_user(db, username="many", email="many@example.com")
        for i in range(8):
            job = _submit(db, user, "j%d" % i)
            assert job.status == "pending"
        assert db.query(models.TrainingJob).filter(
            models.TrainingJob.status == "pending").count() == 8


class TestDispatchQuota:
    """ZH: 配額在派工端生效。"""

    def _running(self, db, user, n):
        """@node tests/test_job_quota.py::TestDispatchQuota._running"""
        for i in range(n):
            j = _submit(db, user, "run%d" % i)
            j.status = "running"
        db.commit()

    def test_user_at_cap_is_skipped(self, client, db):
        """ZH: 手上已經有 cap 張在跑 → 他的下一張不派。"""
        user = make_user(db, username="cap", email="cap@example.com")
        cap = crud.get_setting(db, "max_jobs_per_user")
        self._running(db, user, cap)
        _submit(db, user, "waiting")
        assert _take(client) is None

    def test_someone_else_gets_dispatched_instead(self, client, db):
        """ZH: 🔴 公平是靠「跳過他、讓下一個人出場」達成的 ——
            如果只是停住，那就變成一個人卡住全部人。"""
        hog = make_user(db, username="hog", email="hog@example.com")
        other = make_user(db, username="other", email="other@example.com")
        cap = crud.get_setting(db, "max_jobs_per_user")
        self._running(db, hog, cap)
        _submit(db, hog, "hog-waiting")          # ZH: 先送，排在前面
        mine = _submit(db, other, "other-job")

        taken = _take(client)
        assert taken is not None
        assert taken["job_id"] == mine.id

    def test_under_cap_is_dispatched(self, client, db):
        """@node tests/test_job_quota.py::TestDispatchQuota.test_under_cap_is_dispatched"""
        user = make_user(db, username="under", email="under@example.com")
        job = _submit(db, user, "ok")
        taken = _take(client)
        assert taken is not None and taken["job_id"] == job.id

    def test_teacher_bypasses_the_cap(self, client, db):
        """ZH: 沿用改動前送單端的同一條規則 —— 這次不順手改變誰有特權。"""
        t = make_user(db, username="teach", email="teach@example.com", role="teacher")
        cap = crud.get_setting(db, "max_jobs_per_user")
        self._running(db, t, cap)
        job = _submit(db, t, "teacher-extra")
        taken = _take(client)
        assert taken is not None and taken["job_id"] == job.id

    def test_cap_is_a_live_setting(self, client, db):
        """ZH: 管理端調大之後不必重啟就要生效。"""
        user = make_user(db, username="live", email="live@example.com")
        self._running(db, user, 2)
        job = _submit(db, user, "after-raise")

        crud.set_system_config(db, "max_jobs_per_user", "5")
        taken = _take(client)
        assert taken is not None and taken["job_id"] == job.id


class TestCountingHelper:
    def test_counts_only_running(self, db):
        """ZH: pending 不算 —— 算進去的話一個人送一堆單就把自己鎖死了。"""
        user = make_user(db, username="count", email="count@example.com")
        a = _submit(db, user, "a")
        a.status = "running"
        _submit(db, user, "b")               # ZH: 留在 pending
        c = _submit(db, user, "c")
        c.status = "completed"
        db.commit()
        assert crud.running_jobs_by_user(db).get(user.id) == 1
