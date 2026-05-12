"""
ZH: CRUD 單元測試
EN: CRUD unit tests

ZH: 直接測試 crud.py 函式，不經過 HTTP 層
EN: Tests crud.py functions directly, bypassing the HTTP layer
"""
import pytest
from datetime import datetime, timezone, timedelta
from conftest import make_user

from app import crud, schemas, models


class TestUserCRUD:
    def test_create_user_creates_token_record(self, db):
        user = make_user(db)
        assert user.id is not None
        assert user.role == "student"

        usage = crud.get_token_usage(db, user.id)
        assert usage is not None
        assert usage.tokens_used == 0
        assert usage.tokens_limit > 0

    def test_create_user_hashes_password(self, db):
        user = make_user(db, username="u2", email="u2@example.com")
        assert user.hashed_password != "password123"
        assert crud.verify_password("password123", user.hashed_password)

    def test_get_user_by_username(self, db):
        make_user(db, username="findme", email="findme@example.com")
        found = crud.get_user_by_username(db, "findme")
        assert found is not None
        assert found.username == "findme"

    def test_get_user_by_username_not_found(self, db):
        assert crud.get_user_by_username(db, "nobody") is None

    def test_get_user_by_email(self, db):
        make_user(db, username="eu", email="eu@example.com")
        found = crud.get_user_by_email(db, "eu@example.com")
        assert found is not None

    def test_update_user_email(self, db):
        user = make_user(db, username="uu", email="uu@example.com")
        updated = crud.update_user(db, user, schemas.UserUpdate(email="new@example.com"))
        assert updated.email == "new@example.com"

    def test_update_user_password(self, db):
        user = make_user(db, username="pw", email="pw@example.com")
        crud.update_user(db, user, schemas.UserUpdate(password="newpass999"))
        db.refresh(user)
        assert crud.verify_password("newpass999", user.hashed_password)

    def test_duplicate_username_raises(self, db):
        make_user(db, username="dup", email="dup1@example.com")
        with pytest.raises(Exception):
            make_user(db, username="dup", email="dup2@example.com")


class TestTokenUsageCRUD:
    def test_increment_token_usage(self, db):
        user = make_user(db, username="tu1", email="tu1@example.com")
        crud.increment_token_usage(db, user.id, 100)
        usage = crud.get_token_usage(db, user.id)
        assert usage.tokens_used == 100

    def test_increment_accumulates(self, db):
        user = make_user(db, username="tu2", email="tu2@example.com")
        crud.increment_token_usage(db, user.id, 50)
        crud.increment_token_usage(db, user.id, 75)
        usage = crud.get_token_usage(db, user.id)
        assert usage.tokens_used == 125

    def test_increment_updates_lifetime_tokens(self, db):
        user = make_user(db, username="lt", email="lt@example.com")
        crud.increment_token_usage(db, user.id, 200)
        db.refresh(user)
        assert user.lifetime_tokens_used == 200

    def test_monthly_reset_triggers(self, db):
        user = make_user(db, username="mr", email="mr@example.com")
        # ZH: 手動把 reset_date 設成過去，觸發月度重置
        # EN: Manually set reset_date to the past to trigger monthly reset
        usage = crud.get_token_usage(db, user.id)
        usage.tokens_used = 999
        usage.reset_date = datetime.now(timezone.utc) - timedelta(days=1)
        db.commit()

        crud.increment_token_usage(db, user.id, 10)
        db.refresh(usage)
        assert usage.tokens_used == 10  # ZH: 重置後只有新增的 10


class TestJobCRUD:
    def _job_in(self, name="job1"):
        return schemas.JobCreate(
            job_name=name,
            model_name="test-model",
            gpu_required=1,
            config={"epochs": 5, "batch_size": 32},
            priority=1,
        )

    def test_create_job(self, db):
        user = make_user(db, username="jc", email="jc@example.com")
        job = crud.create_job(db, self._job_in(), user.id)
        assert job.id is not None
        assert job.status == "pending"
        assert job.user_id == user.id

    def test_get_job(self, db):
        user = make_user(db, username="gj", email="gj@example.com")
        job = crud.create_job(db, self._job_in(), user.id)
        found = crud.get_job(db, job.id)
        assert found.id == job.id

    def test_get_job_not_found(self, db):
        assert crud.get_job(db, "nonexistent-id") is None

    def test_cancel_job_pending(self, db):
        user = make_user(db, username="cj", email="cj@example.com")
        job = crud.create_job(db, self._job_in(), user.id)
        cancelled = crud.cancel_job(db, job.id)
        assert cancelled.status == "cancelled"
        assert cancelled.completed_at is not None

    def test_cancel_running_job_returns_none(self, db):
        user = make_user(db, username="crj", email="crj@example.com")
        job = crud.create_job(db, self._job_in(), user.id)
        crud.update_job_status(db, job.id, "running")
        result = crud.cancel_job(db, job.id)
        assert result is None  # ZH: running 不能取消

    def test_get_pending_jobs_priority_order(self, db):
        user = make_user(db, username="prio", email="prio@example.com")
        low = crud.create_job(db, schemas.JobCreate(job_name="low", model_name="m", priority=0), user.id)
        high = crud.create_job(db, schemas.JobCreate(job_name="high", model_name="m", priority=5), user.id)
        jobs = crud.get_pending_jobs(db)
        assert jobs[0].id == high.id  # ZH: 高優先級排前面

    def test_append_job_log(self, db):
        user = make_user(db, username="log", email="log@example.com")
        job = crud.create_job(db, self._job_in(), user.id)
        crud.append_job_log(db, job.id, "Epoch 1/5")
        crud.append_job_log(db, job.id, "Epoch 2/5")
        db.refresh(job)
        assert "Epoch 1/5" in job.logs
        assert "Epoch 2/5" in job.logs

    def test_update_job_progress(self, db):
        user = make_user(db, username="prog", email="prog@example.com")
        job = crud.create_job(db, self._job_in(), user.id)
        crud.update_job_progress(db, job.id, 42.5)
        db.refresh(job)
        assert job.progress == 42.5

    def test_queue_position(self, db):
        user = make_user(db, username="qp", email="qp@example.com")
        j1 = crud.create_job(db, schemas.JobCreate(job_name="j1", model_name="m", priority=1), user.id)
        j2 = crud.create_job(db, schemas.JobCreate(job_name="j2", model_name="m", priority=1), user.id)
        pos1 = crud.get_queue_position(db, j1.id)
        pos2 = crud.get_queue_position(db, j2.id)
        assert pos1 == 1
        assert pos2 == 2
