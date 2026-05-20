"""
ZH: 管理員 API 整合測試
EN: Admin API integration tests
"""
import pytest
from conftest import make_user, auth_headers

WORKER_HEADERS = {"Authorization": "Bearer test-worker-token-16c"}


def _admin_headers(client, db):
    """ZH: 建立管理員並取得 token | EN: Create admin user and get auth headers"""
    make_user(db, username="admin", email="admin@example.com", role="admin")
    return auth_headers(client, "admin", "password123")


# ══════════════════════════════════════════════════════════════════
# require_admin 存取控制
# ══════════════════════════════════════════════════════════════════

class TestAdminAccessControl:
    def test_student_cannot_access_admin_users(self, client, db):
        make_user(db)
        headers = auth_headers(client)
        r = client.get("/api/v1/admin/users", headers=headers)
        assert r.status_code == 403

    def test_unauthenticated_cannot_access_admin(self, client):
        r = client.get("/api/v1/admin/users")
        assert r.status_code == 401

    def test_admin_can_access_users(self, client, db):
        headers = _admin_headers(client, db)
        r = client.get("/api/v1/admin/users", headers=headers)
        assert r.status_code == 200
        assert isinstance(r.json(), list)


# ══════════════════════════════════════════════════════════════════
# GET /admin/users — JOIN 查詢 + 分頁
# ══════════════════════════════════════════════════════════════════

class TestAdminUserList:
    def test_list_contains_token_fields(self, client, db):
        headers = _admin_headers(client, db)
        r = client.get("/api/v1/admin/users", headers=headers)
        assert r.status_code == 200
        users = r.json()
        assert len(users) >= 1
        u = users[0]
        assert "tokens_used" in u
        assert "tokens_limit" in u

    def test_pagination_limit(self, client, db):
        admin_h = _admin_headers(client, db)
        for i in range(5):
            make_user(db, username=f"stu{i}", email=f"stu{i}@example.com")
        r = client.get("/api/v1/admin/users?limit=2", headers=admin_h)
        assert r.status_code == 200
        assert len(r.json()) == 2

    def test_pagination_skip(self, client, db):
        admin_h = _admin_headers(client, db)
        for i in range(3):
            make_user(db, username=f"p{i}", email=f"p{i}@example.com")
        all_r = client.get("/api/v1/admin/users", headers=admin_h)
        total = len(all_r.json())
        skipped_r = client.get(f"/api/v1/admin/users?skip={total}", headers=admin_h)
        assert skipped_r.json() == []


# ══════════════════════════════════════════════════════════════════
# PUT /admin/users/{id}
# ══════════════════════════════════════════════════════════════════

class TestAdminUpdateUser:
    def test_admin_can_update_role(self, client, db):
        admin_h = _admin_headers(client, db)
        make_user(db, username="target", email="target@example.com")

        users = client.get("/api/v1/admin/users", headers=admin_h).json()
        target = next(u for u in users if u["username"] == "target")

        r = client.put(f"/api/v1/admin/users/{target['id']}",
                       json={"role": "teacher"}, headers=admin_h)
        assert r.status_code == 200
        assert r.json()["role"] == "teacher"

    def test_admin_can_update_token_limit(self, client, db):
        admin_h = _admin_headers(client, db)
        make_user(db, username="tl", email="tl@example.com")
        users = client.get("/api/v1/admin/users", headers=admin_h).json()
        target = next(u for u in users if u["username"] == "tl")

        r = client.put(f"/api/v1/admin/users/{target['id']}",
                       json={"tokens_limit": 9999}, headers=admin_h)
        assert r.status_code == 200
        assert r.json()["tokens_limit"] == 9999

    def test_update_nonexistent_user(self, client, db):
        admin_h = _admin_headers(client, db)
        r = client.put("/api/v1/admin/users/nonexistent",
                       json={"role": "teacher"}, headers=admin_h)
        assert r.status_code == 404


# ══════════════════════════════════════════════════════════════════
# GET /admin/jobs — 分頁
# ══════════════════════════════════════════════════════════════════

class TestAdminJobList:
    JOB_PAYLOAD = {
        "job_name": "Test Job", "model_name": "test-model",
        "gpu_required": 1, "config": {"epochs": 3}, "priority": 1,
    }

    def test_admin_sees_all_jobs(self, client, db):
        admin_h = _admin_headers(client, db)
        make_user(db, username="stu", email="stu@example.com")
        stu_h = auth_headers(client, "stu", "password123")
        client.post("/api/v1/jobs", json=self.JOB_PAYLOAD, headers=stu_h)

        r = client.get("/api/v1/admin/jobs", headers=admin_h)
        assert r.status_code == 200
        assert len(r.json()) == 1

    def test_job_list_pagination(self, client, db):
        admin_h = _admin_headers(client, db)
        make_user(db, username="stu2", email="stu2@example.com")
        stu_h = auth_headers(client, "stu2", "password123")
        for _ in range(3):
            client.post("/api/v1/jobs", json=self.JOB_PAYLOAD, headers=stu_h)

        r = client.get("/api/v1/admin/jobs?limit=2", headers=admin_h)
        assert len(r.json()) == 2

    def test_admin_job_has_expected_fields(self, client, db):
        admin_h = _admin_headers(client, db)
        make_user(db, username="stu3", email="stu3@example.com")
        stu_h = auth_headers(client, "stu3", "password123")
        client.post("/api/v1/jobs", json=self.JOB_PAYLOAD, headers=stu_h)

        jobs = client.get("/api/v1/admin/jobs", headers=admin_h).json()
        assert len(jobs) == 1
        j = jobs[0]
        assert "job_id" in j
        assert "status" in j
        assert "logs" not in j  # ZH: admin 列表也不含大型 logs 欄位


# ══════════════════════════════════════════════════════════════════
# POST /admin/jobs/{id}/cancel
# ══════════════════════════════════════════════════════════════════

class TestAdminCancelJob:
    JOB_PAYLOAD = {
        "job_name": "Cancel Test", "model_name": "m",
        "gpu_required": 1, "config": {"epochs": 1},
    }

    def test_admin_can_cancel_pending_job(self, client, db):
        admin_h = _admin_headers(client, db)
        make_user(db, username="stu4", email="stu4@example.com")
        stu_h = auth_headers(client, "stu4", "password123")
        created = client.post("/api/v1/jobs", json=self.JOB_PAYLOAD, headers=stu_h).json()

        r = client.post(f"/api/v1/admin/jobs/{created['job_id']}/cancel", headers=admin_h)
        assert r.status_code == 200
        assert r.json()["status"] == "cancelled"

    def test_admin_cannot_cancel_running_job(self, client, db):
        from app import crud
        admin_h = _admin_headers(client, db)
        make_user(db, username="stu5", email="stu5@example.com")
        stu_h = auth_headers(client, "stu5", "password123")
        created = client.post("/api/v1/jobs", json=self.JOB_PAYLOAD, headers=stu_h).json()

        client.post("/api/v1/worker/take",
                    json={"node_id": "node-1", "available_gpus": ["0"]},
                    headers=WORKER_HEADERS)

        r = client.post(f"/api/v1/admin/jobs/{created['job_id']}/cancel", headers=admin_h)
        assert r.status_code == 400


# ══════════════════════════════════════════════════════════════════
# POST /admin/verify
# ══════════════════════════════════════════════════════════════════

class TestAdminVerify:
    def test_correct_password_succeeds(self, client, db):
        admin_h = _admin_headers(client, db)
        r = client.post("/api/v1/admin/verify",
                        json={"admin_password": "password123"}, headers=admin_h)
        assert r.status_code == 200

    def test_wrong_password_fails(self, client, db):
        admin_h = _admin_headers(client, db)
        r = client.post("/api/v1/admin/verify",
                        json={"admin_password": "wrong"}, headers=admin_h)
        assert r.status_code == 403


# ══════════════════════════════════════════════════════════════════
# POST /worker/heartbeat
# ══════════════════════════════════════════════════════════════════

class TestWorkerHeartbeat:
    def test_heartbeat_accepted(self, client):
        r = client.post("/api/v1/worker/heartbeat",
                        json={"node_id": "node-hb", "available_gpus": ["0", "1"],
                              "gpu_utilization": 45.0},
                        headers=WORKER_HEADERS)
        assert r.status_code == 200
        assert r.json()["node_id"] == "node-hb"

    def test_heartbeat_invalid_token(self, client):
        r = client.post("/api/v1/worker/heartbeat",
                        json={"node_id": "node-hb", "available_gpus": []},
                        headers={"Authorization": "Bearer bad-token"})
        assert r.status_code == 401

    def test_cluster_stats_after_heartbeat(self, client, db):
        make_user(db, username="adm2", email="adm2@example.com", role="admin")
        admin_h = auth_headers(client, "adm2", "password123")

        client.post("/api/v1/worker/heartbeat",
                    json={"node_id": "node-stats", "available_gpus": ["0"],
                          "gpu_utilization": 20.0},
                    headers=WORKER_HEADERS)

        r = client.get("/api/v1/admin/cluster/stats", headers=admin_h)
        assert r.status_code == 200
        nodes = r.json()
        assert any(n["node_id"] == "node-stats" for n in nodes)


# ══════════════════════════════════════════════════════════════════
# Scheduler 超時清理邏輯（直接測試 CRUD 層）
# ══════════════════════════════════════════════════════════════════

class TestSchedulerTimeout:
    def test_timeout_cleanup_marks_job_failed(self, db):
        from conftest import make_user
        from app import crud, schemas, models
        from datetime import timedelta, timezone
        from datetime import datetime

        user = make_user(db, username="tmout", email="tmout@example.com")
        job = crud.create_job(db, schemas.JobCreate(
            job_name="timeout-job", model_name="m", priority=0
        ), user.id)

        # ZH: 手動設為 running 並讓 started_at 超過閾值
        job.status = "running"
        job.started_at = datetime.now(timezone.utc) - timedelta(minutes=130)
        db.commit()

        # ZH: 直接呼叫 cleanup 函式，傳入測試 DB session 避免讀到生產資料庫
        from app.scheduler import _cleanup_timed_out_jobs
        _cleanup_timed_out_jobs(db)

        db.refresh(job)
        assert job.status == "failed"
        assert "Timeout" in job.error_message

    def test_recent_running_job_not_cleaned(self, db):
        from conftest import make_user
        from app import crud, schemas
        from datetime import timedelta, timezone
        from datetime import datetime

        user = make_user(db, username="fresh", email="fresh@example.com")
        job = crud.create_job(db, schemas.JobCreate(
            job_name="fresh-job", model_name="m", priority=0
        ), user.id)
        job.status = "running"
        job.started_at = datetime.now(timezone.utc) - timedelta(minutes=10)
        db.commit()

        from app.scheduler import _cleanup_timed_out_jobs
        _cleanup_timed_out_jobs(db)

        db.refresh(job)
        assert job.status == "running"


# ══════════════════════════════════════════════════════════════════
# 速率限制行為（需實際啟用 rate limiting）
# ══════════════════════════════════════════════════════════════════

class TestRateLimitBehavior:
    def test_rate_limit_disabled_in_tests(self, client, db):
        """ZH: 確認測試環境速率限制已停用，多次登入不觸發 429"""
        make_user(db, username="rl", email="rl@example.com")
        for _ in range(12):
            r = client.post("/api/v1/auth/login",
                            data={"username": "rl", "password": "password123"})
        assert r.status_code == 200  # ZH: 第 12 次仍應成功
