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
# ZH: v2.0 — SECRETS_MASTER_KEY 須通過 config.py 驗證 (≥32 chars, 非黑名單)
# EN: v2.0 — SECRETS_MASTER_KEY must pass config.py validator (≥32 chars, not blacklisted)
os.environ.setdefault("SECRETS_MASTER_KEY", "test-secrets-master-key-with-32-chars-aaa")
os.environ.setdefault("DATABASE_PATH", "/tmp/test_ai_platform.db")
os.environ.setdefault("PORTKEY_ENABLED", "false")  # ZH: 測試時不呼叫真實 LLM
os.environ["RATELIMIT_ENABLED"] = "False"  # ZH: 測試時停用速率限制，避免跨測試累積

# ZH: 測試絕不碰真實外部服務。config.py 會讀 repo 根目錄的 .env，那裡面是**正式環境**
#     的 SMTP 與 Ollama 設定 —— 不覆蓋的話跑測試會真的寄信、真的連 Ollama。
#     用直接指派而非 setdefault：環境變數的優先序高於 .env，setdefault 對「.env 有值
#     但 os.environ 沒有」的情況無效。
# EN: Tests must never touch real external services; .env holds PRODUCTION SMTP/Ollama.
#     Direct assignment (not setdefault) — env vars outrank .env in pydantic-settings.
os.environ["SMTP_SERVER"] = ""                        # ZH: 空值 → send_email 走 mock，不實際寄出
os.environ["SMTP_USERNAME"] = ""                      # ZH: 測試不該把正式帳密載進記憶體
os.environ["SMTP_PASSWORD"] = ""
os.environ["OLLAMA_BASE_URL"] = "http://127.0.0.1:1"  # ZH: 立即連線被拒，不做 DNS 查詢

# ZH: ── MYAI 廠商 API ──
#     實測踩過：跑測試時 lifespan/scheduler 真的打了
#     GET https://www.myai168.com/.../export_user_list 並回 200，把廠商的 7 筆
#     使用者資料同步進測試 DB。**憑證為空**是最有效的閘門——myai_sync 在
#     _login() 一開頭就檢查，沒有帳密直接放棄，不會發出任何請求。
#     BASE_URL 指向關閉埠是第二道，防止有人日後改了憑證檢查的位置。
os.environ["MYAI_ADMIN_EMAIL"] = ""
os.environ["MYAI_ADMIN_PASSWORD"] = ""
os.environ["MYAI_BASE_URL"] = "http://127.0.0.1:1"
os.environ["MYAI_SYNC_INTERVAL_HOURS"] = "0"          # ZH: 0 = 關閉自動同步
os.environ["MYAI_BALANCE_POLL_MINUTES"] = "0"         # ZH: 0 = 關閉餘額輪詢

# ZH: ── IMAP 退信回收 ──
#     bounce_reader 的主機預設由 SMTP 主機推導（smtp.x → imap.x），SMTP_SERVER
#     已清空所以推導不出來；但 .env 若明確設了 IMAP_SERVER 就會繞過推導直接連。
#     連帶清掉帳密：測試沒有任何理由持有正式信箱的登入資訊。
os.environ["IMAP_SERVER"] = ""
os.environ["IMAP_USERNAME"] = ""
os.environ["IMAP_PASSWORD"] = ""

# ZH: ── 內部 Token 計量 ──
#     這一條與上面幾條的性質不同：上面是「不要碰外部服務」，這一條是
#     **不要讓測試繼承正式環境的功能開關**。
#     .env 設 INTERNAL_TOKEN_ACCOUNTING=false（正式環境用廠商計量），而
#     tests/test_chat.py 有兩個測試就是在測內部計量的行為（配額擋下、串流後扣量）。
#     開關關著時 chat.py 的整段配額檢查被跳過，測試永遠紅 —— 而且錯誤訊息是
#     「AI 服務尚未啟動」，會把人誤導成「要先起 docker-compose.ai-models.yml」。
#     實際上那兩個測試連 httpx 都 mock 掉了，不需要任何服務。
#     測試要測的開關必須由測試自己決定，不能由部署環境決定。
os.environ["INTERNAL_TOKEN_ACCOUNTING"] = "true"
# ZH: 為什麼是 127.0.0.1:1 而不是留著預設：預設值 ai-platform-ollama:11434 是 docker
#     內部主機名，在容器外每個 embedding 請求都要等一次 DNS 解析失敗。啟動時的知識庫
#     匯入有 40 個 chunk，等於每個測試多花約 60 秒（client fixture 是 function scope，
#     每個測試都重跑一次 lifespan）。指向 localhost 的關閉埠則是立即 ECONNREFUSED。

from app.database import Base, get_db
from app.main import app

# ZH: lifespan 啟動時會匯入知識庫（v2.6 support assistant），那要打 Ollama。
#     測試環境沒有 Ollama，8 個檔案切成 40 個 chunk 每個都等一次連線失敗，
#     **每建立一次 TestClient 就要 91 秒**——而 client fixture 是 function scope，
#     等於每個測試都付一次。實測：跳過之後單一測試從 92s 降到 1s 出頭。
#     這裡換成 no-op 而不是改 app 程式碼：匯入與被測邏輯無關，
#     且 test_rag_service.py 只測純函式（chunk/cosine/rank/build_*），不碰這支。
#     真要測匯入的話，該測試自己 monkeypatch 回來。
# EN: Startup KB ingest needs Ollama (absent in tests) and costs ~91s per TestClient.
#     Replaced with a no-op here; no app code changed. test_rag_service.py only
#     exercises pure helpers and never calls this.
from app.services import rag_service as _rag_service


async def _skip_kb_ingest(db, force: bool = False):
    return {"status": "skipped-in-tests", "chunks": 0, "files": 0, "failed": 0}


_rag_service.ingest_knowledge_base = _skip_kb_ingest

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
    """
    ZH: 建立測試使用者。
        role != student 時不能直接丟給 schemas.UserCreate —— UserCreate 有
        role_must_be_student 驗證器（公開註冊只允許 student，teacher/admin 由管理端
        佈建）。所以一律以 student 建立再改 role，等於走「管理端佈建」那條路徑，
        密碼雜湊等邏輯仍由 crud.create_user 負責。
        不這樣做的話，所有 make_user(role="admin"/"teacher") 都會 ValidationError ——
        test_admin.py 15 個、test_api.py 1 個測試就是這樣一起紅的。
    EN: UserCreate rejects non-student roles (public-registration guard), so create as
        student then promote — mirroring admin-side provisioning.
    """
    from app import crud, schemas
    user_in = schemas.UserCreate(username=username, email=email,
                                  password=password, role="student")
    user = crud.create_user(db, user_in)
    if role != "student":
        user.role = role
        db.commit()
        db.refresh(user)
    return user


def auth_headers(client, username="testuser", password="password123"):
    """ZH: 登入並回傳 Authorization header | EN: Login and return auth headers"""
    resp = client.post("/api/v1/auth/login",
                       data={"username": username, "password": password})
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
