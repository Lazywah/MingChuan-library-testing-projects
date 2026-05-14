"""
Alembic migrations environment for AI 訓練平台.

ZH: 說明：
    - target_metadata 指向 app.models 的 Base.metadata，支援 autogenerate
    - sqlalchemy.url 優先讀取環境變數 DATABASE_PATH，fallback 到 alembic.ini
    - 使用 run_migrations_online 模式（連線 SQLite）
EN: Notes:
    - target_metadata points to app.models Base.metadata for autogenerate support
    - sqlalchemy.url reads DATABASE_PATH env var first, falls back to alembic.ini
    - Uses online migration mode (connects to SQLite)
"""
import os
import sys
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from alembic import context

# ZH: 將 job-scheduler 根目錄加入 sys.path，讓 `from app.xxx import` 正常運作
# EN: Add job-scheduler root to sys.path so `from app.xxx import` works
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ZH: 匯入所有 ORM 模型，讓 autogenerate 能偵測到所有表
# EN: Import all ORM models so autogenerate can detect all tables
from app.database import Base  # noqa: F401
import app.models  # noqa: F401  — registers all model classes against Base

# Alembic Config object
config = context.config

# Setup logging from alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ZH: autogenerate 依賴此 metadata | EN: autogenerate relies on this metadata
target_metadata = Base.metadata


def _get_db_url() -> str:
    """
    ZH: 取得資料庫連線 URL。
        優先讀取環境變數 DATABASE_PATH（如 /data/app.db），
        fallback 到 alembic.ini 的 sqlalchemy.url。
    EN: Get DB URL. Reads DATABASE_PATH env var first (e.g. /data/app.db),
        falls back to alembic.ini sqlalchemy.url.
    """
    db_path = os.environ.get("DATABASE_PATH")
    if db_path:
        return f"sqlite:///{db_path}"
    return config.get_main_option("sqlalchemy.url")


def run_migrations_offline() -> None:
    """
    ZH: 離線模式：輸出 SQL 到 stdout，不實際連線 DB（適合 review / CI）
    EN: Offline mode: emit SQL to stdout without connecting to DB (useful for review/CI)
    """
    url = _get_db_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,   # ZH: SQLite ALTER TABLE 需要 batch 模式
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """
    ZH: 線上模式：直接連線 DB 並執行 migration
    EN: Online mode: connect to DB and run migrations
    """
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = _get_db_url()

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,   # ZH: SQLite 不支援 ALTER COLUMN，必須用 batch
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
