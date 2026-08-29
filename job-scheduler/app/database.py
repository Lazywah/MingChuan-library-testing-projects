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

    @node job-scheduler/app/database.py::set_sqlite_pragma
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

    @node job-scheduler/app/database.py::get_db
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

    @node job-scheduler/app/database.py::init_db
    """
    # ZH: 確保資料庫目錄存在 | EN: Ensure database directory exists
    db_dir = os.path.dirname(settings.DATABASE_PATH)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)
        logger.info(f"ZH: 建立資料庫目錄 {db_dir} | EN: Created database directory {db_dir}")

    # ZH: 匯入 models 以註冊所有表 | EN: Import models to register all tables
    from . import models  # noqa: F401
    Base.metadata.create_all(bind=engine)

    # ZH: 手動遷移 - 自動補齊新增的欄位 (供開發使用) | EN: Manual migration - auto append new columns
    from sqlalchemy import text, inspect
    try:
        with engine.begin() as conn:
            # --- users 表遷移 | users table migrations ---
            try: conn.execute(text("ALTER TABLE users ADD COLUMN last_login_time DATETIME"))
            except Exception: pass
            try: conn.execute(text("ALTER TABLE users ADD COLUMN last_login_ip VARCHAR"))
            except Exception: pass
            try: conn.execute(text("ALTER TABLE users ADD COLUMN online_status INTEGER DEFAULT 0"))
            except Exception: pass
            try: conn.execute(text("ALTER TABLE users ADD COLUMN is_test_account INTEGER DEFAULT 0"))
            except Exception: pass
            try: conn.execute(text("ALTER TABLE users ADD COLUMN tutorial_dismissed INTEGER DEFAULT 0"))
            except Exception: pass
            try: conn.execute(text("ALTER TABLE users ADD COLUMN department VARCHAR"))
            except Exception: pass
            try: conn.execute(text("ALTER TABLE users ADD COLUMN login_count INTEGER DEFAULT 0"))
            except Exception: pass
            try: conn.execute(text("ALTER TABLE users ADD COLUMN lifetime_tokens_used INTEGER DEFAULT 0"))
            except Exception: pass

            # --- models 表遷移 | models table migrations ---
            try: conn.execute(text("ALTER TABLE models ADD COLUMN model_type VARCHAR DEFAULT 'local'"))
            except Exception: pass
            try: conn.execute(text("ALTER TABLE models ADD COLUMN api_provider VARCHAR"))
            except Exception: pass
            try: conn.execute(text("ALTER TABLE models ADD COLUMN api_endpoint VARCHAR"))
            except Exception: pass
            try: conn.execute(text("ALTER TABLE models ADD COLUMN api_model_id VARCHAR"))
            except Exception: pass
            try: conn.execute(text("ALTER TABLE models ADD COLUMN tool_types VARCHAR DEFAULT 'chat'"))
            except Exception: pass
            # --- chat_history 表遷移 | chat_history table migrations ---
            try: conn.execute(text("ALTER TABLE chat_history ADD COLUMN tool_type VARCHAR DEFAULT 'chat'"))
            except Exception: pass

            # --- training_jobs 表遷移（v1 Notebook 欄位，先前漏 ALTER）---
            # --- training_jobs migrations (v1 Notebook columns, missed in v1) ---
            try: conn.execute(text("ALTER TABLE training_jobs ADD COLUMN docker_image VARCHAR"))
            except Exception: pass
            try: conn.execute(text("ALTER TABLE training_jobs ADD COLUMN inline_code TEXT"))
            except Exception: pass
            try: conn.execute(text("ALTER TABLE training_jobs ADD COLUMN entry_args TEXT"))
            except Exception: pass
            try: conn.execute(text("ALTER TABLE training_jobs ADD COLUMN preferred_node VARCHAR"))
            except Exception: pass

            # --- v2.0 Lab 模組欄位 | v2.0 Lab module columns ---
            try: conn.execute(text("ALTER TABLE users ADD COLUMN disk_quota_gb INTEGER DEFAULT 10"))
            except Exception: pass
            try: conn.execute(text("ALTER TABLE worker_heartbeats ADD COLUMN pool_type VARCHAR DEFAULT 'batch'"))
            except Exception: pass
            try: conn.execute(text("ALTER TABLE worker_heartbeats ADD COLUMN gpus_detail TEXT DEFAULT '[]'"))
            except Exception: pass
            # --- v3.0 本地 GPU 路由分流：任務的目標節點池 | v3.0 job target pool for local-GPU routing ---
            try: conn.execute(text("ALTER TABLE training_jobs ADD COLUMN pool_type VARCHAR DEFAULT 'batch'"))
            except Exception: pass

            # --- Phase E 清理 v1 Notebook 表 | Phase E drop v1 notebooks table ---
            # ZH: 注意 — 不刪除 training_jobs 的 docker_image/inline_code/entry_args/preferred_node 4 欄位
            #     因為 v2.0 Lab 的「Run on GPU」仍會使用這些欄位
            # EN: NOTE — keep training_jobs.{docker_image,inline_code,entry_args,preferred_node}
            #     because v2.0 Lab's "Run on GPU" still uses these columns
            try: conn.execute(text("DROP TABLE IF EXISTS notebooks"))
            except Exception: pass

            # --- v2.1 SSO OIDC 整合欄位 | v2.1 SSO OIDC integration columns ---
            try: conn.execute(text("ALTER TABLE users ADD COLUMN auth_source VARCHAR DEFAULT 'local'"))
            except Exception: pass
            try: conn.execute(text("ALTER TABLE users ADD COLUMN external_id VARCHAR"))
            except Exception: pass

            # --- v2.1 在線狀態修正 | v2.1 online status fix ---
            # ZH: 取代既有 online_status 持久化邏輯，改用 last_activity 動態判斷
            # EN: Replace persistent online_status with dynamic last_activity
            # --- v3.5 介面偏好（跟帳號走）| v3.5 per-account UI preferences ---
            try: conn.execute(text("ALTER TABLE users ADD COLUMN ui_font_scale INTEGER DEFAULT 100"))
            except Exception: pass
            try: conn.execute(text("ALTER TABLE users ADD COLUMN ui_lang VARCHAR DEFAULT 'zh'"))
            except Exception: pass
            try: conn.execute(text("ALTER TABLE users ADD COLUMN ui_theme VARCHAR DEFAULT 'yellow'"))
            except Exception: pass

            try: conn.execute(text("ALTER TABLE users ADD COLUMN last_activity DATETIME"))
            except Exception: pass

            # --- v2.8 MYAI 綁定：external_ai_accounts 加廠商穩定鍵 ---
            # EN: v2.8 MYAI binding: add stable vendor key to external_ai_accounts
            try: conn.execute(text("ALTER TABLE external_ai_accounts ADD COLUMN myai_vendor_sn VARCHAR"))
            except Exception: pass

            # --- v3.3 MYAI 自動開通：初始密碼暫存（加密）+ 保存期/已修改旗標 ---
            # EN: v3.3 MYAI auto-provision: encrypted initial password + retention/ack
            try: conn.execute(text("ALTER TABLE external_ai_accounts ADD COLUMN init_pwd_enc BLOB"))
            except Exception: pass
            try: conn.execute(text("ALTER TABLE external_ai_accounts ADD COLUMN init_pwd_at DATETIME"))
            except Exception: pass
            try: conn.execute(text("ALTER TABLE external_ai_accounts ADD COLUMN init_pwd_ack INTEGER DEFAULT 0"))
            except Exception: pass

            # --- v3.9 組織對照表的英文名（空的退回中文顯示）---
            try: conn.execute(text("ALTER TABLE org_departments ADD COLUMN name_en VARCHAR"))
            except Exception: pass
            try: conn.execute(text("ALTER TABLE org_departments ADD COLUMN college_en VARCHAR"))
            except Exception: pass
            try: conn.execute(text("ALTER TABLE org_units ADD COLUMN name_en VARCHAR"))
            except Exception: pass

            # --- v3.9 初始點數發放：紀錄兼冪等鍵（有 granted_at 就永不再發）---
            try: conn.execute(text("ALTER TABLE external_ai_accounts ADD COLUMN credit_granted_at DATETIME"))
            except Exception: pass
            try: conn.execute(text("ALTER TABLE external_ai_accounts ADD COLUMN credit_granted_pts INTEGER"))
            except Exception: pass
            try: conn.execute(text("ALTER TABLE external_ai_accounts ADD COLUMN credit_grant_note TEXT"))
            except Exception: pass

            # --- v3.5 退信回收：Message-ID 對應 + 退信時間 ---
            try: conn.execute(text("ALTER TABLE email_log ADD COLUMN message_id VARCHAR"))
            except Exception: pass
            try: conn.execute(text("ALTER TABLE email_log ADD COLUMN bounced_at DATETIME"))
            except Exception: pass

            # --- v3.2 GPU 節點管理：心跳來源 IP + 撞名偵測（gpu_nodes 新表由 create_all 建）---
            # EN: v3.2 GPU node mgmt: heartbeat source IP + duplicate-NODE_ID detection
            try: conn.execute(text("ALTER TABLE worker_heartbeats ADD COLUMN source_ip VARCHAR"))
            except Exception: pass
            try: conn.execute(text("ALTER TABLE worker_heartbeats ADD COLUMN ip_conflict_until DATETIME"))
            except Exception: pass
            # --- v3.6 節點是否與服務層同機（Lab volume 看得到與否）---
            try: conn.execute(text("ALTER TABLE worker_heartbeats ADD COLUMN shares_storage INTEGER DEFAULT 0"))
            except Exception: pass
            # --- v3.6 訓練產出（模型檔）回傳到服務層 ---
            try: conn.execute(text("ALTER TABLE training_jobs ADD COLUMN artifact_bytes INTEGER"))
            except Exception: pass
            # --- v3.6 任務指向的資料集（取代由客戶端傳路徑）---
            try: conn.execute(text("ALTER TABLE training_jobs ADD COLUMN dataset_id VARCHAR"))
            except Exception: pass
            # --- v3.6 使用者自帶的訓練程式 ---
            try: conn.execute(text("ALTER TABLE training_jobs ADD COLUMN script_source TEXT"))
            except Exception: pass
            # --- v3.7 臨時帳號：到期時間與用途 ---
            try: conn.execute(text("ALTER TABLE users ADD COLUMN expires_at DATETIME"))
            except Exception: pass
            try: conn.execute(text("ALTER TABLE users ADD COLUMN temp_purpose VARCHAR"))
            except Exception: pass
            # --- v3.8 組織欄位：行政單位與校區（學院由 org_departments 推導，不存欄位）---
            # --- v3.8 初次登入設定完成時間 ---
            # ZH: 🔴 **回填放在同一個 try 裡是刻意的。** ADD COLUMN 只有第一次會成功,
            #     第二次起會拋錯 → 下面那行 UPDATE 就不會跑。
            #     所以「把既有帳號一次標成已完成」剛好只執行一次。
            #     把 UPDATE 拆到外面的話,每次重啟都會把新帳號也標成已完成,
            #     於是**彈窗永遠不會出現**,而且畫面上看不出哪裡壞了。
            # ZH: 擁有者裁定：彈窗只對**新帳號**跳,現有帳號不跳。
            try:
                conn.execute(text("ALTER TABLE users ADD COLUMN onboarded_at DATETIME"))
                conn.execute(text("UPDATE users SET onboarded_at = CURRENT_TIMESTAMP"))
            except Exception: pass
            # --- v3.8 管理權限旗標（與 role 拆開）---
            # ZH: 回填同樣放在 ADD COLUMN 的 try 裡 —— 只跑第一次。
            #     既有的 role='admin' 帳號轉成 is_admin=1;**role 本身不動**,
            #     那個帳號的實際身分是什麼只有擁有者知道,不該由我猜。
            try:
                conn.execute(text("ALTER TABLE users ADD COLUMN is_admin INTEGER DEFAULT 0 NOT NULL"))
                conn.execute(text("UPDATE users SET is_admin = 1 WHERE role = 'admin'"))
            except Exception: pass
            # --- v3.8 role 的來源（自動判定 vs 管理者設定）---
            try: conn.execute(text("ALTER TABLE users ADD COLUMN role_source VARCHAR"))
            except Exception: pass
            try: conn.execute(text("ALTER TABLE users ADD COLUMN unit VARCHAR"))
            except Exception: pass
            # ZH: campus 同一天內從單一欄位改成 user_campuses 關聯表（教職員可多校區）。
            #     這個欄位從來沒有被寫入過任何值就被換掉了,所以直接移除 ——
            #     留著不用的欄位就是下一個 online_status（deprecated 了三版還在表上）。
            #     SQLite 3.35+ 才支援 DROP COLUMN;舊版會失敗而欄位留著,不影響功能。
            try: conn.execute(text("ALTER TABLE users DROP COLUMN campus"))
            except Exception: pass
            # --- v3.8 Lab 封存銷毀前的提醒（寄出時間，分第一封與最後一封）---
            try: conn.execute(text("ALTER TABLE archived_lab_volumes ADD COLUMN reminded_first_at DATETIME"))
            except Exception: pass
            try: conn.execute(text("ALTER TABLE archived_lab_volumes ADD COLUMN reminded_final_at DATETIME"))
            except Exception: pass
            # --- v3.6 實驗室多份存檔：使用者取的名字 ---
            try: conn.execute(text("ALTER TABLE lab_sessions ADD COLUMN display_name VARCHAR"))
            except Exception: pass
            # ZH: v3.9 互動式 GPU 實驗室佔用的卡號（NULL = CPU 實驗室）。
            #     `/worker/take` 會依它把卡從可派清單裡排掉。
            try: conn.execute(text("ALTER TABLE lab_sessions ADD COLUMN gpu_index INTEGER"))
            except Exception: pass

            # ZH: v3.9 凍結原因（自動解凍要靠它分辨「超配額」與「管理員手動」）
            try: conn.execute(text("ALTER TABLE user_storage_state ADD COLUMN frozen_reason VARCHAR"))
            except Exception: pass

    except Exception as e:
        logger.warning(f"Manual DB migration skipped or partially failed: {e}")

    # --- 動態模型清單 — Seed 預設 AI 模型（僅當不存在時）| Seed default AI models (only if absent) ---
    # ZH: 本機 Ollama Llama3 預設公開 (chat+presentation 皆可用)；雲端模型先建檔但不公開，
    #     待管理員接入 API key 後再於管理頁公開 (is_public=1)。
    # EN: Local Ollama Llama3 is public by default; cloud models are seeded but unpublished
    #     until an admin connects API keys and publishes them.
    try:
        from .models import Model
        _db = SessionLocal()
        try:
            _default_models = [
                # (name, api_model_id, model_type, api_provider, is_public, tool_types, description)
                ("Ollama Llama3", "llama3:latest", "api", "ollama", 1, "chat,presentation", "本機 Ollama Llama3（預設可用）"),
                ("Claude 3.5 Sonnet", "claude-3-5-sonnet", "api", "anthropic", 0, "chat", "Anthropic Claude（需管理員接入 API key 後公開）"),
                ("Gemini 1.5 Pro", "gemini-1.5-pro", "api", "google", 0, "chat", "Google Gemini（需管理員接入 API key 後公開）"),
            ]
            for name, mid, mtype, provider, pub, tools, desc in _default_models:
                if not _db.query(Model).filter(Model.name == name).first():
                    _db.add(Model(
                        name=name, api_model_id=mid, model_type=mtype,
                        api_provider=provider, is_public=pub, tool_types=tools,
                        description=desc, uploaded_by="system",
                    ))
            _db.commit()
        finally:
            _db.close()
    except Exception as e:
        logger.warning(f"Seed default models skipped: {e}")

    # --- v2.5 外部 AI 分流 — Seed external_ai_url 設定鍵（僅當不存在時）---
    # ZH: 預設指向 MYAI 教育平台；清空 = 未啟用，使用者端中介頁顯示「即將開放」。
    #     admin 可於管理頁隨時改網址或清空（總開關/回退）。
    # EN: Defaults to MYAI Education Platform; empty = disabled (landing shows "coming soon").
    #     Admin can change/clear the URL anytime in the admin page (kill switch / rollback).
    try:
        from .models import SystemConfig
        _db = SessionLocal()
        try:
            if not _db.query(SystemConfig).filter(SystemConfig.key == "external_ai_url").first():
                _db.add(SystemConfig(
                    key="external_ai_url", value="https://www.myai168.com/tw/ai/",
                    description="外部 AI 平台網址（空=未啟用，退回即將開放）",
                ))
                _db.commit()
        finally:
            _db.close()
    except Exception as e:
        logger.warning(f"Seed external_ai_url skipped: {e}")

    # --- v3.8 組織對照種子（學系→學院、行政單位）---
    # ZH: 只在表是空的時候填。種子是初值不是真相 —— 管理者改過的名字
    #     不會在下次重開時被蓋回去（見 crud.seed_org_tables 與 org_seed.py 檔頭）。
    try:
        from . import crud as _crud
        _db = SessionLocal()
        try:
            _crud.seed_org_tables(_db)
        finally:
            _db.close()
    except Exception as e:  # noqa: BLE001 - 種子失敗不該擋住開機
        logger.warning(f"Seed org tables skipped: {e}")

    logger.info(f"ZH: 資料庫初始化完成 ({settings.DATABASE_PATH}) | EN: Database initialized ({settings.DATABASE_PATH})")
