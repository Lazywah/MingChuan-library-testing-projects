"""
==============================================================================
Module 2: SQLite 資料庫連線管理 (Database Connection Management)
==============================================================================
ZH: 用途：管理 SQLite 引擎、Session 生命週期、WAL 模式啟用
EN: Purpose: Manage SQLite engine, Session lifecycle, WAL mode activation

ZH: 流程：
    1. create_engine() 建立 SQLite 連線引擎 (啟用 WAL + FK)
    2. 每次 API 請求透過 get_db() 取得 Session
    3. 請求結束後自動關閉 Session
    4. init_db() 在應用啟動時建立所有表
EN: Flow:
    1. create_engine() creates SQLite engine (with WAL + FK enabled)
    2. Each API request gets a Session via get_db()
    3. Session auto-closes after request completes
    4. init_db() creates all tables on app startup

ZH: 模組化設計：
    - 可替換為 PostgreSQL：僅需修改此檔案的 engine URL
    - Session 透過 FastAPI Depends 注入，與業務邏輯解耦
    - WAL 模式確保讀寫不互鎖 (適合 10 位並發使用者)
EN: Modular design:
    - Swappable to PostgreSQL: only change engine URL in this file
    - Session injected via FastAPI Depends, decoupled from business logic
    - WAL mode ensures read/write don't block each other (suits 10 concurrent users)
==============================================================================
"""

from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker
from .config import settings
import logging
import os

logger = logging.getLogger(__name__)

# ==============================================================================
# ZH: 資料庫 URL 建構 | EN: Database URL construction
# ==============================================================================
SQLALCHEMY_DATABASE_URL = f"sqlite:///{settings.DATABASE_PATH}"

# ==============================================================================
# ZH: 建立 SQLAlchemy 引擎
# EN: Create SQLAlchemy engine
# ZH: check_same_thread=False : 允許多執行緒 (FastAPI 需要)
# EN: check_same_thread=False : allow multi-threading (required by FastAPI)
# ZH: timeout=30 : 寫入鎖等待最多 30 秒
# EN: timeout=30 : wait up to 30 seconds for write lock
# ==============================================================================
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={
        "check_same_thread": False,
        "timeout": 30
    },
    pool_pre_ping=True,
    echo=False  # ZH: 設為 True 可開啟 SQL 語句日誌 | EN: Set True to log SQL statements
)


# ==============================================================================
# ZH: SQLite 連線事件：每次建立連線時自動啟用最佳化設定
# EN: SQLite connection event: auto-enable optimizations on each connection
# ==============================================================================
@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_conn, connection_record):
    """
    ZH: 設定 SQLite PRAGMA (每次新連線自動執行)
    EN: Set SQLite PRAGMAs (auto-executed on each new connection)
    """
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")       # ZH: 寫前日誌模式 | EN: Write-Ahead Logging
    cursor.execute("PRAGMA synchronous=NORMAL")      # ZH: 加速寫入 | EN: Faster writes
    cursor.execute("PRAGMA cache_size=10000")        # ZH: 10MB 快取 | EN: 10MB cache
    cursor.execute("PRAGMA foreign_keys=ON")         # ZH: 啟用外鍵約束 | EN: Enable foreign keys
    cursor.close()


# ==============================================================================
# ZH: Session 工廠 | EN: Session factory
# ==============================================================================
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# ==============================================================================
# ZH: ORM Base 類別 - 所有 Model 繼承此類別
# EN: ORM Base class - all Models inherit from this
# ==============================================================================
Base = declarative_base()


def get_db():
    """
    ZH: FastAPI 依賴注入函式 - 提供資料庫 Session
    EN: FastAPI dependency injection function - provides database Session

    ZH: 用法 (在路由中)：
        @app.get("/users")
        def get_users(db: Session = Depends(get_db)):
            ...
    EN: Usage (in routes):
        @app.get("/users")
        def get_users(db: Session = Depends(get_db)):
            ...
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """
    ZH: 初始化資料庫 - 建立所有表 (若不存在)
    EN: Initialize database - create all tables (if not exist)

    ZH: 在 app/main.py 的 startup 事件中呼叫
    EN: Called in app/main.py startup event
    """
    # ZH: 確保資料庫目錄存在 | EN: Ensure database directory exists
    db_dir = os.path.dirname(settings.DATABASE_PATH)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)
        logger.info(f"ZH: 建立資料庫目錄 {db_dir} | EN: Created database directory {db_dir}")

    # ZH: 匯入 models 以註冊所有表 | EN: Import models to register all tables
    from . import models  # noqa: F401
    Base.metadata.create_all(bind=engine)
    logger.info(f"ZH: 資料庫初始化完成 ({settings.DATABASE_PATH}) | EN: Database initialized ({settings.DATABASE_PATH})")
