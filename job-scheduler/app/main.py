"""
==============================================================================
Module 9: FastAPI 主應用入口 (Main Application Entry Point)
==============================================================================
ZH: 用途：組裝所有模組、啟動 / 關閉服務、掛載路由
EN: Purpose: Assemble all modules, start/stop services, mount routes

ZH: 流程：
    1. 建立 FastAPI app 實例
    2. 掛載 CORS 中介層 (允許跨域)
    3. 掛載 Auth Router (/api/v1/auth/*)
    4. 掛載 Jobs Router (/api/v1/jobs/*)
    5. 註冊 startup 事件 → init_db() + start_scheduler()
    6. 註冊 shutdown 事件 → stop_scheduler()
    7. 提供 /health 健康檢查端點
EN: Flow:
    1. Create FastAPI app instance
    2. Mount CORS middleware (allow cross-origin)
    3. Mount Auth Router (/api/v1/auth/*)
    4. Mount Jobs Router (/api/v1/jobs/*)
    5. Register startup event → init_db() + start_scheduler()
    6. Register shutdown event → stop_scheduler()
    7. Provide /health endpoint

ZH: 模組化設計 (積木式組裝)：
    - 每個 Router 獨立掛載，註解掉 include_router 即可移除功能
    - startup/shutdown 事件中的模組也可獨立控制
    - 新增功能只需：1. 建立 Router  2. 在此 include_router
EN: Modular design (building-block assembly):
    - Each Router independently mounted, comment out include_router to remove
    - Modules in startup/shutdown also independently controllable
    - Adding features: 1. Create Router  2. include_router here
==============================================================================
"""

import asyncio
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from .database import init_db
from .scheduler import start_scheduler, stop_scheduler
from .config import settings, SCHEDULER_POLICY
from .rate_limit import limiter
from .routers import auth, jobs

import logging

# ==============================================================================
# ZH: 日誌設定 | EN: Logging configuration
# ==============================================================================
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)


# ==============================================================================
# ZH: 應用生命週期管理 (FastAPI lifespan)
# EN: Application lifecycle management (FastAPI lifespan)
# ==============================================================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    ZH: 應用啟動 / 關閉時的生命週期管理
    EN: Application startup / shutdown lifecycle management

    ZH: 啟動順序：
        1. 初始化資料庫 (建表)
        2. 啟動背景排程器
    EN: Startup order:
        1. Initialize database (create tables)
        2. Start background scheduler

    @node job-scheduler/app/main.py::lifespan
    """
    # ---- ZH: 啟動 | EN: Startup ----
    logger.info("=" * 60)
    logger.info("ZH: AI 訓練平台 Job Scheduler 啟動中... | EN: Starting AI Training Platform Job Scheduler...")
    logger.info("=" * 60)

    # ZH: Module 2: 初始化資料庫 | EN: Module 2: Initialize database
    init_db()

    # ==========================================================================
    # ZH: v3.8 **開機清除測試帳號的機制已移除**（擁有者裁定 2026-08-27）。
    #
    # ZH: 原本這裡會在每次服務啟動時,把所有 is_test_account=1 的帳號直接刪掉。
    #     移除的三個理由：
    #       1. 全專案**沒有任何一行把那個旗標設成 1** —— 它從來沒有真的觸發過,
    #          但一直上著膛：有人為了測試在 DB 裡手動設一次,下次重啟帳號就沒了。
    #       2. 它 `db.delete(u)` **直接刪**,沒走正規刪除路徑 ——
    #          不封存 Lab、不解 FK 參照、不清孤兒表。會留下孤兒 volume。
    #       3. 它想解決的問題（臨時帳號）已經有更好的機制：`expires_at` +
    #          `temp_purpose`,而且那條路徑刻意**只停用不刪帳號**。
    #
    # ZH: `is_test_account` 這個欄位**保留** —— auth.py 用它把測試帳號排除在
    #     實體登入紀錄之外,那個用途是好的。只是不再有人會因為它被刪掉。
    # EN: v3.8 startup deletion of test accounts removed; the flag itself is kept
    #     (auth.py still uses it to exclude test accounts from the login log).
    # ==========================================================================


    # ==========================================================================
    # ZH: v3.3 首次啟動自動建立管理員（跳板帳號）
    #     規則：**只在 DB 完全沒有任何 admin 時**才建立。
    #       - 不會覆寫既有帳號、也不會「復活」已被管理者刪除的跳板帳號
    #         （因為那時系統裡已有其他 admin）
    #       - 若所有 admin 都不見了（誤刪／DB 事故），下次啟動會自動再生 → 防永久鎖死
    #     密碼由 .env 的 BOOTSTRAP_ADMIN_PASSWORD 提供（`scripts/setup_env.py` 互動設定）；
    #     留空則不建立，改用 scripts/create-admin.bat 手動建。
    # EN: v3.3 bootstrap admin — created only when NO admin exists at all. Never
    #     overwrites, never resurrects a deliberately deleted one, but recovers from lockout.
    # ==========================================================================
    from .database import SessionLocal as _SL
    from . import models as _m, crud as _c
    try:
        _db = _SL()
        try:
            # ZH: v3.8 看 is_admin 旗標不看 role —— 管理者的身分可能是學生。
            _has_admin = _db.query(_m.User).filter(_m.User.is_admin == 1).first() is not None
            _pw = (settings.BOOTSTRAP_ADMIN_PASSWORD or "").strip()
            if _has_admin:
                pass                      # 已有管理員 → 什麼都不做
            elif not _pw:
                logger.warning(
                    "ZH: 系統尚無管理員，且 BOOTSTRAP_ADMIN_PASSWORD 未設定 → 未自動建立。"
                    "請執行 scripts/create-admin.bat 建立管理員。"
                )
            else:
                _admin = _m.User(
                    username="admin",
                    email=(settings.BOOTSTRAP_ADMIN_EMAIL or "admin@local"),
                    hashed_password=_c.get_password_hash(_pw),
                    role="admin",
                    # ZH: 🔴 v3.8 起管理權限看的是 is_admin 不是 role ——
                    #     漏了這一行,全新部署自動建的第一個管理員會**進不去管理端**,
                    #     而且畫面上只會顯示「這個帳號不是管理員」,看不出是建帳號時漏設。
                    is_admin=1,
                    is_active=1,
                )
                _db.add(_admin)
                _db.commit()
                _db.refresh(_admin)
                _db.add(_m.TokenUsage(
                    user_id=_admin.id, tokens_used=0,
                    tokens_limit=_c.get_setting(_db, "monthly_token_limit"),
                    reset_date=_c._calculate_next_reset_date(_db),
                ))
                _db.commit()
                logger.warning(
                    "ZH: 已自動建立初始管理員 admin（密碼取自 .env BOOTSTRAP_ADMIN_PASSWORD）。"
                    "請盡快登入 :8888 修改密碼，或建立自己的帳號後刪除它。"
                )
        finally:
            _db.close()
    except Exception as e:  # noqa: BLE001 - 建立失敗不應讓服務起不來
        logger.error(f"ZH: 初始管理員建立失敗: {e}")

    # ZH: 啟動時智慧同步全域 Token 額度 | EN: Smart sync global token limit on startup
    # ZH: 只有當 yml 的值被修改過（與上次同步不同），才批量更新所有使用者
    # EN: Only batch-update all users when the yml value actually changed since last sync
    from .database import SessionLocal
    from . import models
    try:
        db = SessionLocal()
        # 讀取上次同步的值
        last_sync = db.query(models.SystemConfig).filter(
            models.SystemConfig.key == "last_synced_token_limit"
        ).first()
        last_val = int(last_sync.value) if last_sync else None
        current_val = settings.DEFAULT_MONTHLY_TOKEN_LIMIT

        if last_val != current_val:
            # yml 的值變了，批量更新所有使用者
            updated = db.query(models.TokenUsage).update(
                {models.TokenUsage.tokens_limit: current_val}
            )
            # 記錄本次同步值
            if last_sync:
                last_sync.value = str(current_val)
            else:
                db.add(models.SystemConfig(
                    key="last_synced_token_limit",
                    value=str(current_val),
                    description="Last synced DEFAULT_MONTHLY_TOKEN_LIMIT from env"
                ))
            db.commit()
            if updated > 0:
                logger.info(f"ZH: yml 額度已從 {last_val} 變更為 {current_val}，已同步 {updated} 位使用者 | "
                            f"EN: yml limit changed {last_val} → {current_val}, synced {updated} users")
        else:
            logger.info("ZH: yml Token 額度未變更，跳過同步 | EN: yml token limit unchanged, skip sync")
        db.close()
    except Exception as e:
        logger.warning(f"ZH: Token 額度同步失敗: {e} | EN: Token limit sync failed: {e}")

    # ZH: Module 8: 啟動排程器 | EN: Module 8: Start scheduler
    await start_scheduler()

    # 確保資料集上傳目錄存在
    import os
    os.makedirs("/data/datasets", exist_ok=True)

    # ==========================================================================
    # ZH: v2.6 客服助手 — 知識庫若為空則匯入。
    #
    # ZH: 🔴 v3.8 改成**背景執行，不擋啟動**。
    #     原本是在這裡 `await`，而這一段在服務開始聽埠**之前** ——
    #     知識庫是空的（全新安裝）而 Ollama 又還沒起來時，
    #     40 個片段各等一次 DNS 逾時（實測 ~2.3 秒）≈ **93 秒**，
    #     而 healthcheck 約 70 秒就判死，於是 nginx 的
    #     `depends_on: service_healthy` 直接放棄：
    #         dependency failed to start: container ai-platform-scheduler is unhealthy
    #     整個平台起不來，而根本原因只是「一個附加功能的資料還沒準備好」。
    #     docs/01-quick-start.md §5 為此寫了一整段「兩層有先後」的警告。
    #
    # ZH: 搬到背景之後：服務照常在幾秒內就緒，知識庫自己慢慢補。
    #     期間 `/assistant/status` 會如實回 `kb_ready: false`
    #     （那個欄位在 v3.8 一併改成不再宣稱「服務可用」），
    #     所以「還沒好」是**看得到的**，不是安靜的。
    #
    # ZH: ⚠ 一定要留住 task 的參照。asyncio 只持有弱參照，
    #     不留的話 task 可能在跑到一半時被 GC 掉 —— 而且不會有任何錯誤訊息。
    # EN: v3.8 KB ingest moved off the startup path (was blocking for ~93s on a
    #     fresh install with Ollama down, which failed nginx's health gate).
    # ==========================================================================
    async def _ingest_kb_in_background():
        """@node job-scheduler/app/main.py::lifespan.<nested>._ingest_kb_in_background"""
        try:
            from .services import rag_service
            db = SessionLocal()
            try:
                result = await rag_service.ingest_knowledge_base(db, force=False)
                logger.info("ZH: 知識庫狀態 | EN: KB status: %s", result)
            finally:
                db.close()
        except Exception as e:  # noqa: BLE001 - 附加功能失敗絕不影響服務本身
            logger.warning(
                "ZH: 知識庫匯入略過（Ollama 未就緒？可稍後由 admin 呼叫 /assistant/reindex）"
                " | EN: KB ingest skipped (Ollama not ready? admin can call /assistant/reindex later): %s", e
            )

    _kb_task = asyncio.create_task(_ingest_kb_in_background())
    app.state.kb_ingest_task = _kb_task        # ZH: 留參照，見上面的 ⚠

    sched_config = SCHEDULER_POLICY.get("scheduling", {})
    logger.info(
        f"ZH: 服務就緒 | EN: Service ready | "
        f"GPU_MOCK={SCHEDULER_POLICY.get('mock_mode', True)} | "
        f"MAX_JOBS={sched_config.get('max_concurrent_jobs', 4)}"
    )

    yield  # ZH: 應用運行中 | EN: Application running

    # ---- ZH: 關閉 | EN: Shutdown ----
    logger.info("ZH: 服務關閉中... | EN: Shutting down...")
    await stop_scheduler()
    logger.info("ZH: 服務已關閉 | EN: Service stopped")


# ==============================================================================
# ZH: 建立 FastAPI 應用實例 | EN: Create FastAPI app instance
# ==============================================================================
app = FastAPI(
    title="AI 訓練平台 Job Scheduler",
    description=(
        "ZH: AI 訓練平台的核心服務，提供使用者認證、Token 額度管理、訓練任務排程。\n"
        "EN: Core service of AI Training Platform, providing auth, token quota, and job scheduling."
    ),
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",       # ZH: Swagger UI 路徑 | EN: Swagger UI path
    redoc_url="/redoc",     # ZH: ReDoc 路徑 | EN: ReDoc path
    # v2.1 修正：關掉 trailing-slash 自動 redirect，避免與 nginx 的 location 形成
    # 307 連鎖。配合 nginx.conf 的 regex location (匹配有/無斜線兩種形態)。
    redirect_slashes=False,
)

# ZH: 掛載速率限制器 | EN: Mount rate limiter
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


# ==============================================================================
# ZH: CORS 中介層 (跨域資源共享)
# EN: CORS middleware (Cross-Origin Resource Sharing)
# ZH: 允許 Open WebUI 及其他前端跨域呼叫 API
# EN: Allows Open WebUI and other frontends to call API cross-origin
# ==============================================================================
# ZH: 開發模式允許所有來源；正式上線時請在 .env 設定 CORS_ORIGINS（逗號分隔）
# EN: Dev mode allows all origins; set CORS_ORIGINS (comma-separated) in .env for production
_raw_origins = os.environ.get("CORS_ORIGINS", "")
allowed_origins = [o.strip() for o in _raw_origins.split(",") if o.strip()] or ["*"]

# ZH: 瀏覽器規範：allow_origins=["*"] 與 allow_credentials=True 不相容（會被瀏覽器阻擋）。
#     僅當有明確來源清單時才啟用 credentials，萬用字元時強制關閉。
# EN: Browser spec: allow_origins=["*"] is incompatible with allow_credentials=True (browsers block it).
#     Enable credentials only when an explicit origin list is provided; wildcard forces it off.
_allow_credentials = "*" not in allowed_origins

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==============================================================================
# ZH: v3.8 — API 回應一律不可快取
# ==============================================================================
@app.middleware("http")
async def _no_store_api(request, call_next):
    """
    ZH: 給所有 `/api/` 的回應加上 `Cache-Control: no-store`。

    ZH: 🔴 為什麼需要：稽核時實測 API 回應**一個快取標頭都沒有**
        （只有 content-type）。而我抓到一次 `/api/v1/reports/mine`
        回傳的是**一頁 HTML**——那是瀏覽器從快取拿的舊東西，
        `fetch(..., {cache:'no-store'})` 再打一次就正常了。
        症狀非常會騙人：畫面顯示「讀不到」而後端好好的、直連 curl 也正常。

    ZH: 這裡的每一個端點回的都是**跟人有關的即時資料**（我的額度、我的任務、
        我的問題回報），沒有一個是可以共用快取的，所以一律 no-store，
        不做例外清單——例外清單遲早會有人忘記維護。

    ZH: 為什麼放在後端而不是 nginx：nginx 有 **13 個** `/api/v1/...` 的
        location 區塊，逐一加 `add_header` 就是 13 個會漏的地方，
        而這個專案已經漏掛過兩次 location（一次 405、一次 502）。
        API 的可快取性應該由 API 自己宣告。

    @node job-scheduler/app/main.py::_no_store_api
    """
    response = await call_next(request)
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


# ==============================================================================
# ZH: 掛載路由 (積木式 - 註解掉即可移除功能)
# EN: Mount routes (building-block - comment out to remove features)
# ==============================================================================

# ZH: Module 4 路由：認證 + Token 管理 | EN: Module 4 routes: Auth + Token
app.include_router(auth.router, prefix="/api/v1/auth")

# ZH: Module 5 路由：訓練任務管理 | EN: Module 5 routes: Training job management
app.include_router(jobs.router, prefix="/api/v1/jobs")

# ZH: 新增聊天助理與管理員路由 | EN: Chat assistant and admin routes
# ZH: Phase E 移除 notebooks router（v1 偽 Notebook 已被 v2.0 Lab 取代）
# EN: Phase E removed notebooks router (v1 pseudo-Notebook replaced by v2.0 Lab)
from .routers import chat, admin, datasets, worker, sso, lab, secrets, announcements
from .routers import models as models_router
from .routers import external_ai
from .routers import assistant
from .routers import reports
from .routers import system
app.include_router(chat.router,      prefix="/api/v1/chat")
app.include_router(admin.router,     prefix="/api/v1/admin")
# ZH: 動態模型清單（各 AI 工具的下拉依 tool_type 抓取）| EN: Dynamic model list per tool
app.include_router(models_router.router, prefix="/api/v1/models")
app.include_router(datasets.router,  prefix="/api/v1/datasets")
app.include_router(worker.router,    prefix="/api/v1/worker")
# ZH: SSO 路由 (C1 修復：先前漏掛載導致 Nginx 代理 /api/v1/sso/ 永遠 404)
# EN: SSO routes (C1 fix: previously unmounted while Nginx still proxied → 404)
app.include_router(sso.router,       prefix="/api/v1/sso")
# ZH: v2.0 Lab 模組 | EN: v2.0 Lab module
app.include_router(lab.router,       prefix="/api/v1/lab")
app.include_router(secrets.router,   prefix="/api/v1/secrets")
# ZH: v2.2 公告（user 看 + admin 編）
app.include_router(announcements.router,        prefix="/api/v1/announcements")
app.include_router(announcements.admin_router,  prefix="/api/v1/admin/announcements")
# ZH: v2.5 外部 AI 分流（使用者導流 + admin 對應表/網址設定）
# EN: v2.5 External AI routing (user redirect + admin mapping/url settings)
app.include_router(external_ai.router,          prefix="/api/v1/external-ai")
# ZH: v2.6 客服／導覽助手（RAG + 本地 Ollama；/ask 公開）
# EN: v2.6 Support/guide assistant (RAG + local Ollama; /ask public)
app.include_router(assistant.router,            prefix="/api/v1/assistant")
# ZH: v3.4 問題回報（使用者送出 + 自己看歷史；admin 看全部 + 回應）
# EN: v3.4 issue reports (user submits & reads own history; admin lists & replies)
app.include_router(reports.router,              prefix="/api/v1/reports")
app.include_router(reports.admin_router,        prefix="/api/v1/admin/reports")
# ZH: v3.8 前台唯讀的營運設定白名單（額度重置日／任務逾時／Lab 封存天數）
# EN: v3.8 whitelisted read-only operational settings for the user-facing site
app.include_router(system.router,               prefix="/api/v1/system")


# ==============================================================================
# ZH: 健康檢查端點 | EN: Health check endpoint
# ZH: 用於 Docker healthcheck 和 Nginx upstream 檢查
# EN: Used by Docker healthcheck and Nginx upstream check
# ==============================================================================
@app.get("/health", tags=["系統 System"])
def health_check():
    """
    ZH: 服務健康檢查
    EN: Service health check

    @node job-scheduler/app/main.py::health_check
    """
    sched_config = SCHEDULER_POLICY.get("scheduling", {})
    return {
        "status": "healthy",
        "service": "job-scheduler",
        "version": "1.0.0",
        "gpu_mock_mode": SCHEDULER_POLICY.get("mock_mode", True),
        "max_concurrent_jobs": sched_config.get("max_concurrent_jobs", 4)
    }


# ==============================================================================
# ZH: 根路徑 | EN: Root path
# ==============================================================================
@app.get("/", tags=["系統 System"])
def root():
    """
    ZH: API 根路徑 - 回傳服務資訊
    EN: API root - returns service info

    @node job-scheduler/app/main.py::root
    """
    return {
        "service": "AI Training Platform - Job Scheduler",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health"
    }
