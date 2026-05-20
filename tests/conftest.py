"""
ZH: pytest 測試夾具 (Fixtures)
EN: pytest test fixtures
ZH: 提供獨立的記憶體資料庫，每個測試函式使用全新的 DB，互不干擾
EN: Provides isolated in-memory DB per test function for full isolation
"""
import sys
import os

# ZH: 將 job-scheduler 加入 Python 路徑，使 `from app.xxx import` 可正常運作
# EN: Add job-scheduler to Python path so `from app.xxx import` works
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "job-scheduler"))

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

# ZH: 設定測試環境變數，覆蓋部份設定
# EN: Set test env vars to override settings
# ZH: C3 修復：secrets 須通過 config.py 的長度與黑名單驗證 (JWT ≥32, Worker ≥16)
# EN: C3 fix: secrets must satisfy config.py length & blacklist (JWT ≥32, Worker ≥16)
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-with-32-chars-padding-aaa")
os.environ.setdefault("WORKER_API_TOKEN", "test-worker-token-16c")
os.environ.setdefault("DATABASE_PATH", "/tmp/test_ai_platform.db")
os.environ.setdefault("PORTKEY_ENABLED", "false")  # ZH: 測試時不呼叫真實 LLM
os.environ["RATELIMIT_ENABLED"] = "False"  # ZH: 測試時停用速率限制，避免跨測試累積

from app.database import Base, get_db
from app.main import app

# ZH: 使用每次測試都獨立的記憶體 SQLite
# EN: Use isolated in-memory SQLite per test
TEST_DB_URL = "sqlite:///:memory:"


@pytest.fixture(scope="function")
def db_engine():
    engine = create_engine(
        TEST_DB_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,  # share one connection so in-memory tables persist
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture(scope="function")
def db(db_engine):
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(scope="function")
def client(db_engine):
    """
    ZH: TestClient，注入測試 DB，不啟動真實 lifespan（避免 /data 路徑問題）
    EN: TestClient with injected test DB, skips real lifespan to avoid /data path issues
    """
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)

    def override_get_db():
        session = SessionLocal()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    # ZH: raise_server_exceptions=True 讓測試能看到後端例外
    # EN: raise_server_exceptions=True surfaces backend exceptions in tests
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c
    app.dependency_overrides.clear()


# ── Helper factories ───────────────────────────────────────────────────────────

def make_user(db, username="testuser", email="test@example.com",
              password="password123", role="student"):
    from app import crud, schemas
    user_in = schemas.UserCreate(username=username, email=email,
                                  password=password, role=role)
    return crud.create_user(db, user_in)


def auth_headers(client, username="testuser", password="password123"):
    """ZH: 登入並回傳 Authorization header | EN: Login and return auth headers"""
    resp = client.post("/api/v1/auth/login",
                       data={"username": username, "password": password})
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
