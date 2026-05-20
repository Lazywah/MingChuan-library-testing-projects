"""
ZH: API 整合測試（透過 TestClient 測試 HTTP 端點）
EN: API integration tests (HTTP endpoints via TestClient)
"""
import pytest
from conftest import make_user, auth_headers


# ══════════════════════════════════════════════════════════════════
# Auth Endpoints
# ══════════════════════════════════════════════════════════════════

class TestAuthRegister:
    def test_register_success(self, client):
        r = client.post("/api/v1/auth/register", json={
            "username": "newuser", "email": "new@example.com", "password": "pass1234"
        })
        assert r.status_code == 201
        data = r.json()
        assert data["username"] == "newuser"
        assert data["role"] == "student"
        assert "hashed_password" not in data

    def test_register_duplicate_username(self, client, db):
        make_user(db, username="dup", email="dup@example.com")
        r = client.post("/api/v1/auth/register", json={
            "username": "dup", "email": "dup2@example.com", "password": "pass1234"
        })
        assert r.status_code == 400

    def test_register_duplicate_email(self, client, db):
        make_user(db, username="u1", email="shared@example.com")
        r = client.post("/api/v1/auth/register", json={
            "username": "u2", "email": "shared@example.com", "password": "pass1234"
        })
        assert r.status_code == 400

    def test_register_invalid_email(self, client):
        r = client.post("/api/v1/auth/register", json={
            "username": "bad", "email": "not-an-email", "password": "pass1234"
        })
        assert r.status_code == 422


class TestAuthLogin:
    def test_login_success(self, client, db):
        make_user(db)
        r = client.post("/api/v1/auth/login",
                        data={"username": "testuser", "password": "password123"})
        assert r.status_code == 200
        assert "access_token" in r.json()
        assert r.json()["token_type"] == "bearer"

    def test_login_wrong_password(self, client, db):
        make_user(db)
        r = client.post("/api/v1/auth/login",
                        data={"username": "testuser", "password": "wrong"})
        assert r.status_code == 401

    def test_login_nonexistent_user(self, client):
        r = client.post("/api/v1/auth/login",
                        data={"username": "nobody", "password": "pass"})
        assert r.status_code == 401

    def test_unauthorized_without_token(self, client):
        r = client.get("/api/v1/auth/me")
        assert r.status_code == 401


class TestAuthMe:
    def test_get_me(self, client, db):
        make_user(db)
        headers = auth_headers(client)
        r = client.get("/api/v1/auth/me", headers=headers)
        assert r.status_code == 200
        data = r.json()
        assert data["username"] == "testuser"
        assert data["role"] == "student"

    def test_update_me_email(self, client, db):
        make_user(db)
        headers = auth_headers(client)
        r = client.put("/api/v1/auth/me", json={"email": "updated@example.com"},
                       headers=headers)
        assert r.status_code == 200
        assert r.json()["email"] == "updated@example.com"

    def test_token_usage_endpoint(self, client, db):
        make_user(db)
        headers = auth_headers(client)
        r = client.get("/api/v1/auth/usage", headers=headers)
        assert r.status_code == 200
        data = r.json()
        assert data["tokens_used"] == 0
        assert data["tokens_limit"] > 0
        assert "reset_date" in data


# ══════════════════════════════════════════════════════════════════
# Jobs Endpoints
# ══════════════════════════════════════════════════════════════════

JOB_PAYLOAD = {
    "job_name": "Test Job",
    "model_name": "test-model",
    "gpu_required": 1,
    "config": {"epochs": 3, "batch_size": 16},
    "priority": 1,
}


class TestJobsEndpoints:
    def test_submit_job(self, client, db):
        make_user(db)
        headers = auth_headers(client)
        r = client.post("/api/v1/jobs", json=JOB_PAYLOAD, headers=headers)
        assert r.status_code == 201
        data = r.json()
        assert "job_id" in data
        assert data["status"] == "pending"

    def test_list_jobs_empty(self, client, db):
        make_user(db)
        headers = auth_headers(client)
        r = client.get("/api/v1/jobs", headers=headers)
        assert r.status_code == 200
        assert r.json()["total"] == 0

    def test_list_jobs_after_submit(self, client, db):
        make_user(db)
        headers = auth_headers(client)
        client.post("/api/v1/jobs", json=JOB_PAYLOAD, headers=headers)
        r = client.get("/api/v1/jobs", headers=headers)
        assert r.json()["total"] == 1

    def test_list_jobs_no_logs_field(self, client, db):
        make_user(db)
        headers = auth_headers(client)
        client.post("/api/v1/jobs", json=JOB_PAYLOAD, headers=headers)
        r = client.get("/api/v1/jobs", headers=headers)
        jobs = r.json()["jobs"]
        assert len(jobs) == 1
        assert "logs" not in jobs[0], "List response must NOT include logs field"

    def test_get_job_status(self, client, db):
        make_user(db)
        headers = auth_headers(client)
        created = client.post("/api/v1/jobs", json=JOB_PAYLOAD, headers=headers).json()
        job_id = created["job_id"]
        r = client.get(f"/api/v1/jobs/{job_id}", headers=headers)
        assert r.status_code == 200
        assert r.json()["status"] == "pending"
        assert "logs" in r.json()  # ZH: 詳情頁有 logs

    def test_cancel_job(self, client, db):
        make_user(db)
        headers = auth_headers(client)
        created = client.post("/api/v1/jobs", json=JOB_PAYLOAD, headers=headers).json()
        job_id = created["job_id"]
        r = client.delete(f"/api/v1/jobs/{job_id}", headers=headers)
        assert r.status_code == 200
        assert r.json()["status"] == "cancelled"

    def test_cancel_nonexistent_job(self, client, db):
        make_user(db)
        headers = auth_headers(client)
        r = client.delete("/api/v1/jobs/nonexistent-id", headers=headers)
        assert r.status_code == 404

    def test_student_cannot_see_other_job(self, client, db):
        make_user(db, username="student1", email="s1@example.com")
        make_user(db, username="student2", email="s2@example.com")
        h1 = auth_headers(client, "student1", "password123")
        h2 = auth_headers(client, "student2", "password123")
        created = client.post("/api/v1/jobs", json=JOB_PAYLOAD, headers=h1).json()
        job_id = created["job_id"]
        r = client.get(f"/api/v1/jobs/{job_id}", headers=h2)
        assert r.status_code == 403

    def test_teacher_can_see_all_jobs(self, client, db):
        make_user(db, username="student", email="st@example.com")
        make_user(db, username="teacher", email="tc@example.com", role="teacher")
        sh = auth_headers(client, "student", "password123")
        th = auth_headers(client, "teacher", "password123")
        client.post("/api/v1/jobs", json=JOB_PAYLOAD, headers=sh)
        r = client.get("/api/v1/jobs", headers=th)
        assert r.json()["total"] == 1

    def test_token_deducted_on_submit(self, client, db):
        make_user(db)
        headers = auth_headers(client)
        before = client.get("/api/v1/auth/usage", headers=headers).json()["tokens_used"]
        client.post("/api/v1/jobs", json=JOB_PAYLOAD, headers=headers)
        after = client.get("/api/v1/auth/usage", headers=headers).json()["tokens_used"]
        assert after > before  # ZH: 提交任務後 Token 應被扣減


# ══════════════════════════════════════════════════════════════════
# Worker Endpoints
# ══════════════════════════════════════════════════════════════════

WORKER_HEADERS = {"Authorization": "Bearer test-worker-token-16c"}


class TestWorkerEndpoints:
    def test_take_job_no_pending(self, client):
        r = client.post("/api/v1/worker/take",
                        json={"node_id": "node-1", "available_gpus": ["0"]},
                        headers=WORKER_HEADERS)
        assert r.status_code == 200
        assert r.json()["job"] is None

    def test_take_job_returns_pending(self, client, db):
        make_user(db)
        headers = auth_headers(client)
        client.post("/api/v1/jobs", json=JOB_PAYLOAD, headers=headers)

        r = client.post("/api/v1/worker/take",
                        json={"node_id": "node-1", "available_gpus": ["0"]},
                        headers=WORKER_HEADERS)
        assert r.status_code == 200
        job = r.json()["job"]
        assert job is not None
        assert "job_id" in job
        assert job["gpu_id"] == "0"

    def test_take_job_marks_running(self, client, db):
        from app import crud
        make_user(db)
        headers = auth_headers(client)
        created = client.post("/api/v1/jobs", json=JOB_PAYLOAD, headers=headers).json()

        client.post("/api/v1/worker/take",
                    json={"node_id": "node-1", "available_gpus": ["0"]},
                    headers=WORKER_HEADERS)

        job = crud.get_job(db, created["job_id"])
        assert job.status == "running"
        assert job.gpu_server == "node-1"

    def test_take_job_atomic_no_double_dispatch(self, client, db):
        """ZH: 模擬兩個 Worker 同時搶同一個任務，只有一個能成功"""
        make_user(db)
        headers = auth_headers(client)
        client.post("/api/v1/jobs", json=JOB_PAYLOAD, headers=headers)

        r1 = client.post("/api/v1/worker/take",
                         json={"node_id": "node-1", "available_gpus": ["0"]},
                         headers=WORKER_HEADERS)
        r2 = client.post("/api/v1/worker/take",
                         json={"node_id": "node-2", "available_gpus": ["0"]},
                         headers=WORKER_HEADERS)

        # ZH: 只有一個拿到任務，另一個拿到 None
        # EN: Only one should get the job, the other gets None
        jobs = [r1.json()["job"], r2.json()["job"]]
        non_null = [j for j in jobs if j is not None]
        assert len(non_null) == 1, "Exactly one worker should claim the job"

    def test_worker_invalid_token(self, client):
        r = client.post("/api/v1/worker/take",
                        json={"node_id": "node-1", "available_gpus": ["0"]},
                        headers={"Authorization": "Bearer wrong-token"})
        assert r.status_code == 401

    def test_update_job_progress(self, client, db):
        make_user(db)
        headers = auth_headers(client)
        created = client.post("/api/v1/jobs", json=JOB_PAYLOAD, headers=headers).json()
        job_id = created["job_id"]

        client.post("/api/v1/worker/take",
                    json={"node_id": "node-1", "available_gpus": ["0"]},
                    headers=WORKER_HEADERS)

        r = client.post(f"/api/v1/worker/jobs/{job_id}/update",
                        json={"progress": 50.0, "log": "Epoch 2/4"},
                        headers=WORKER_HEADERS)
        assert r.status_code == 200

        from app import crud
        job = crud.get_job(db, job_id)
        assert job.progress == 50.0
        assert "Epoch 2/4" in job.logs

    def test_update_job_completed(self, client, db):
        from app import crud
        make_user(db)
        headers = auth_headers(client)
        created = client.post("/api/v1/jobs", json=JOB_PAYLOAD, headers=headers).json()
        job_id = created["job_id"]

        client.post("/api/v1/worker/take",
                    json={"node_id": "node-1", "available_gpus": ["0"]},
                    headers=WORKER_HEADERS)
        client.post(f"/api/v1/worker/jobs/{job_id}/update",
                    json={"status": "completed", "progress": 100.0,
                          "output_path": "/workspace/outputs/model.pt"},
                    headers=WORKER_HEADERS)

        job = crud.get_job(db, job_id)
        assert job.status == "completed"
        assert job.progress == 100.0
        assert job.output_path == "/workspace/outputs/model.pt"


# ══════════════════════════════════════════════════════════════════
# Health Check
# ══════════════════════════════════════════════════════════════════

class TestHealth:
    def test_health_check(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "healthy"
