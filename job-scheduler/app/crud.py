"""
==============================================================================
Module 5: CRUD 資料庫操作 (Database CRUD Operations)
==============================================================================
ZH: 用途：封裝所有資料庫讀寫操作，隔離業務邏輯與 DB 操作
EN: Purpose: Encapsulate all DB read/write ops, isolate business from DB logic

ZH: 流程：
    Router 接收請求 → 呼叫 CRUD 函式 → SQLAlchemy ORM 操作 → SQLite 讀寫
EN: Flow:
    Router receives request → calls CRUD function → SQLAlchemy ORM → SQLite R/W

ZH: 模組化設計：
    - 所有 CRUD 函式接受 db: Session 參數 (依賴注入)
    - 新增操作只需在此檔案加函式
    - Router 不直接操作 ORM，保持程式碼清晰
EN: Modular design:
    - All CRUD functions accept db: Session (dependency injection)
    - Adding operations only requires new functions here
    - Routers don't touch ORM directly, keeping code clean
==============================================================================
"""

from sqlalchemy.orm import Session
from sqlalchemy import desc
from passlib.context import CryptContext
from datetime import datetime, timedelta, timezone
from typing import Optional, List
import json
import logging
import re

from . import models, schemas
from .config import settings

logger = logging.getLogger(__name__)

# ==============================================================================
# ZH: 密碼雜湊工具 | EN: Password hashing utility
# ==============================================================================
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def get_password_hash(password: str) -> str:
    """ZH: 將明文密碼轉為 bcrypt 雜湊 | EN: Hash plaintext password with bcrypt

    @node job-scheduler/app/crud.py::get_password_hash
    """
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """ZH: 驗證密碼是否匹配 | EN: Verify password matches hash

    @node job-scheduler/app/crud.py::verify_password
    """
    return pwd_context.verify(plain_password, hashed_password)


# ==============================================================================
# ZH: 使用者 CRUD | EN: User CRUD
# ==============================================================================

def disable_expired_temp_accounts(db: Session) -> int:
    """ZH: 把已到期的臨時帳號設成停用。回傳這次改了幾個。

    ZH: 到期本身在**登入路徑**就已經擋住了（見 auth.is_expired），
        這裡做的是另一件事：把 `is_active` 也設成 0，
        好讓管理端的清單**看得出來**這個帳號已經不能用了。
        少了這一步，畫面上它還是「啟用」，而實際上登不進來——
        那種不一致會讓人以為是登入壞了。

    ZH: 🔴 只改「還是啟用中」的那些。已經被手動停用的不要動，
        否則每天都會重複寫一次、稽核紀錄被灌滿沒有意義的變更。

    @node job-scheduler/app/crud.py::disable_expired_temp_accounts
    """
    now = datetime.now(timezone.utc)
    rows = (db.query(models.User)
            .filter(models.User.expires_at.isnot(None),
                    models.User.expires_at <= now,
                    models.User.is_active == 1)
            .all())
    for u in rows:
        u.is_active = 0
    if rows:
        db.commit()
    return len(rows)


def get_user_by_username(db: Session, username: str) -> Optional[models.User]:
    """ZH: 依使用者名稱查詢 | EN: Query user by username

    @node job-scheduler/app/crud.py::get_user_by_username
    """
    return db.query(models.User).filter(models.User.username == username).first()


def get_user_by_email(db: Session, email: str) -> Optional[models.User]:
    """ZH: 依電子郵件查詢 | EN: Query user by email

    @node job-scheduler/app/crud.py::get_user_by_email
    """
    return db.query(models.User).filter(models.User.email == email).first()


def get_user_by_id(db: Session, user_id: str) -> Optional[models.User]:
    """ZH: 依 ID 查詢 | EN: Query user by ID

    @node job-scheduler/app/crud.py::get_user_by_id
    """
    return db.query(models.User).filter(models.User.id == user_id).first()


def get_user_by_external_id(db: Session, external_id: str) -> Optional[models.User]:
    """
    ZH: 依 OIDC oid (Microsoft 永久 ID) 查詢使用者
    EN: Query user by OIDC oid (Microsoft permanent ID)

    ZH: v2.1 — OIDC callback 優先使用 oid 識別（學號改名 / 換 email 都不變）
    EN: v2.1 — OIDC callback prefers oid (immune to username / email changes)

    @node job-scheduler/app/crud.py::get_user_by_external_id
    """
    if not external_id:
        return None
    return db.query(models.User).filter(models.User.external_id == external_id).first()


def create_user(db: Session, user: schemas.UserCreate) -> models.User:
    """
    ZH: 建立新使用者 + 自動初始化 Token 額度
    EN: Create new user + auto-initialize token quota

    ZH: 流程：
        1. 雜湊密碼
        2. 建立 User 記錄
        3. 建立對應的 TokenUsage 記錄
    EN: Flow:
        1. Hash password
        2. Create User record
        3. Create corresponding TokenUsage record

    @node job-scheduler/app/crud.py::create_user
    """
    hashed_password = get_password_hash(user.password)
    db_user = models.User(
        username=user.username,
        email=user.email,
        hashed_password=hashed_password,
        role=user.role,
        department=user.department
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)

    # ZH: 自動建立 Token 用量記錄 | EN: Auto-create token usage record
    next_month_reset = _calculate_next_reset_date(db)
    db_usage = models.TokenUsage(
        user_id=db_user.id,
        tokens_used=0,
        tokens_limit=get_setting(db, "monthly_token_limit"),
        reset_date=next_month_reset
    )
    db.add(db_usage)
    db.commit()

    return db_user

def update_user(db: Session, db_user: models.User, update_data: schemas.UserUpdate) -> models.User:
    """
    ZH: 更新使用者資料 (如果不為空)
    EN: Update user data if not None

    ZH: v2.1 — SSO 使用者 (auth_source != "local") 不能透過此處改密碼，
        因為密碼存在 IdP (Microsoft 等)，本地系統從未拿到密碼。
        前端會根據 auth_source 隱藏密碼輸入框並改顯示 IdP 連結。
    EN: v2.1 — SSO users (auth_source != "local") cannot change password here
        because the password lives at the IdP. Frontend hides the password
        field and shows an IdP link instead.

    @node job-scheduler/app/crud.py::update_user
    """
    # v2.1: SSO 使用者改密碼直接拒絕
    if update_data.password is not None and update_data.password.strip():
        if getattr(db_user, "auth_source", "local") != "local":
            raise ValueError(
                f"SSO users (auth_source={db_user.auth_source}) cannot change "
                f"password locally. Use the IdP's password change page."
            )
        db_user.hashed_password = get_password_hash(update_data.password)

    if update_data.email is not None:
        db_user.email = update_data.email
    if getattr(update_data, "tutorial_dismissed", None) is not None:
        db_user.tutorial_dismissed = update_data.tutorial_dismissed
    if getattr(update_data, "department", None) is not None:
        db_user.department = update_data.department
    db.commit()
    db.refresh(db_user)
    return db_user


def create_sso_user(
    db: Session,
    username: str,
    email: str,
    role: str = "student",
    department: Optional[str] = None,
    auth_source: str = "sso_mock",       # v2.1: SSO provider 識別
    external_id: Optional[str] = None,   # v2.1: OIDC oid 等永久 ID
) -> models.User:
    """
    ZH: SSO 登入時自動建立帳號（系統給予隨機 hash 密碼，無人知道實際值）。
    EN: Auto-create account on SSO login (random hashed password, nobody knows it).

    ZH: v2.1 — 增加 auth_source 與 external_id 參數，由 router callback 傳入。
        auth_source 由 SSO client 的 validate_ticket() 回傳並傳遞至此。
    EN: v2.1 — adds auth_source and external_id, populated from SSO client's
        validate_ticket() return dict.

    @node job-scheduler/app/crud.py::create_sso_user
    """
    import secrets as _secrets
    random_password = _secrets.token_urlsafe(16)
    hashed_password = get_password_hash(random_password)

    db_user = models.User(
        username=username,
        email=email,
        hashed_password=hashed_password,
        role=role,
        department=department,
        auth_source=auth_source,
        external_id=external_id,
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)

    # 自動建立 Token 用量記錄
    next_month_reset = _calculate_next_reset_date(db)
    db_usage = models.TokenUsage(
        user_id=db_user.id,
        tokens_used=0,
        tokens_limit=get_setting(db, "monthly_token_limit"),
        reset_date=next_month_reset,
    )
    db.add(db_usage)
    db.commit()

    return db_user


def upgrade_to_sso(
    db: Session,
    db_user: models.User,
    auth_source: str,
    external_id: Optional[str] = None,
) -> models.User:
    """
    ZH: 既有 local 帳號首次走 SSO 登入時，將其升級為 SSO 帳號。
        典型情境：admin 用 provision 建好 T1090001@mcu.edu.tw (local)，
        該學生之後用 OIDC 登入 → 升級為 sso_oidc，並寫入 external_id。
    EN: Upgrade an existing local account to SSO when it first authenticates via SSO.

    ZH: 安全考量 — 此操作會讓使用者「不能再用本機密碼登入」（update_user 拒絕改密碼），
        但既有本機密碼 hash 仍保留在 DB（不主動清除，作為緊急救援保險）。
    EN: Security note — after upgrade, user cannot change password via /me;
        but existing hashed_password is preserved in DB for emergency fallback.

    @node job-scheduler/app/crud.py::upgrade_to_sso
    """
    db_user.auth_source = auth_source
    if external_id:
        db_user.external_id = external_id
    db.commit()
    db.refresh(db_user)
    return db_user

# ==============================================================================
# ZH: Token 用量 CRUD | EN: Token Usage CRUD
# ==============================================================================

def get_token_usage(db: Session, user_id: str) -> Optional[models.TokenUsage]:
    """ZH: 查詢使用者 Token 用量 | EN: Query user token usage

    @node job-scheduler/app/crud.py::get_token_usage
    """
    return db.query(models.TokenUsage).filter(
        models.TokenUsage.user_id == user_id
    ).first()


def create_token_usage(db: Session, user_id: str) -> models.TokenUsage:
    """ZH: 建立 Token 用量記錄 (若不存在) | EN: Create token usage record (if not exists)

    @node job-scheduler/app/crud.py::create_token_usage
    """
    next_month_reset = _calculate_next_reset_date(db)
    db_usage = models.TokenUsage(
        user_id=user_id,
        tokens_used=0,
        tokens_limit=get_setting(db, "monthly_token_limit"),
        reset_date=next_month_reset
    )
    db.add(db_usage)
    db.commit()
    db.refresh(db_usage)
    return db_usage


def increment_token_usage(db: Session, user_id: str, tokens: int) -> models.TokenUsage:
    """
    ZH: 增加 Token 使用量
    EN: Increment token usage

    ZH: 會自動檢查是否需要重置 (過了重置日期)
    EN: Auto-checks if reset is needed (past reset date)

    @node job-scheduler/app/crud.py::increment_token_usage
    """
    usage = get_token_usage(db, user_id)
    if not usage:
        usage = create_token_usage(db, user_id)

    # ZH: 檢查是否需要月度重置 | EN: Check if monthly reset is needed
    reset_date = usage.reset_date
    if reset_date is not None and reset_date.tzinfo is None:
        reset_date = reset_date.replace(tzinfo=timezone.utc)
    if reset_date is None or datetime.now(timezone.utc) >= reset_date:
        usage.tokens_used = 0
        usage.reset_date = _calculate_next_reset_date(db)

    usage.tokens_used += tokens

    # ZH: 同步更新 User 表的歷史總使用量 | EN: Sync update User's lifetime token usage
    user = get_user_by_id(db, user_id)
    if user:
        user.lifetime_tokens_used += tokens

    db.commit()
    db.refresh(usage)
    return usage


def try_deduct_tokens(db: Session, user_id: str, tokens: int) -> bool:
    """
    ZH: 原子性配額檢查 + Token 扣減，消除 TOCTOU 競爭條件。
        以單一 SQL UPDATE 同時完成「餘額足夠才扣減」，rowcount=0 即代表超額。
    EN: Atomic quota-check + token deduction to eliminate TOCTOU race condition.
        A single SQL UPDATE deducts only when quota is sufficient; rowcount=0 means exceeded.

    Returns:
        True  — deduction succeeded
        False — quota exceeded (caller should raise HTTP 429)

    @node job-scheduler/app/crud.py::try_deduct_tokens
    """
    from sqlalchemy import update as _sa_update

    # ZH: 先處理月度重置（在 flush 前完成，月初才發生，碰撞機率極低）
    # EN: Handle monthly reset before the atomic UPDATE (only happens once/month)
    usage = get_token_usage(db, user_id)
    if not usage:
        usage = create_token_usage(db, user_id)

    reset_date = usage.reset_date
    if reset_date is not None and reset_date.tzinfo is None:
        reset_date = reset_date.replace(tzinfo=timezone.utc)
    if reset_date is None or datetime.now(timezone.utc) >= reset_date:
        usage.tokens_used = 0
        usage.reset_date = _calculate_next_reset_date(db)
        db.flush()  # Write reset to DB before the UPDATE reads tokens_used

    # ZH: 原子性 UPDATE：WHERE 子句同時做配額檢查，避免兩步驟競爭
    # EN: Atomic UPDATE: WHERE clause performs quota check, no two-step race
    result = db.execute(
        _sa_update(models.TokenUsage)
        .where(
            models.TokenUsage.user_id == user_id,
            (models.TokenUsage.tokens_used + tokens) <= models.TokenUsage.tokens_limit,
        )
        .values(tokens_used=models.TokenUsage.tokens_used + tokens)
        .execution_options(synchronize_session=False)
    )

    if result.rowcount == 0:
        db.rollback()
        return False  # Quota exceeded

    # ZH: 同步更新終身使用量 | EN: Sync lifetime token usage
    db.execute(
        _sa_update(models.User)
        .where(models.User.id == user_id)
        .values(lifetime_tokens_used=models.User.lifetime_tokens_used + tokens)
        .execution_options(synchronize_session=False)
    )
    db.commit()
    return True


# ==============================================================================
# ZH: 訓練任務 CRUD | EN: Training Job CRUD
# ==============================================================================

# ZH: v3.0 合法節點池白名單。任何未知值一律當 batch —— batch 是「誰都能領」的安全預設，
#     不會把任務推進一個沒有 worker 的池而卡死。
# EN: v3.0 valid node pools. Unknown → batch (the safe "anyone can take it" default).
VALID_POOLS = ("batch", "interactive")


def normalize_pool(value) -> str:
    """ZH: 正規化 pool_type，非白名單一律回 'batch' | EN: normalize pool, unknown → 'batch'.

    @node job-scheduler/app/crud.py::normalize_pool
    """
    v = (value or "batch")
    return v if v in VALID_POOLS else "batch"


def create_job(db: Session, job: schemas.JobCreate, user_id: str) -> models.TrainingJob:
    """
    ZH: 建立新訓練任務 (狀態 = pending)
    EN: Create new training job (status = pending)

    @node job-scheduler/app/crud.py::create_job
    """
    db_job = models.TrainingJob(
        user_id=user_id,
        job_name=job.job_name,
        model_name=job.model_name,
        gpu_required=job.gpu_required,
        priority=job.priority,
        pool_type=normalize_pool(job.pool_type),   # v3.0 目標節點池
        config=json.dumps(job.config) if job.config else None,
        script_path=job.script_path,
        dataset_path=job.dataset_path,
        dataset_id=getattr(job, "dataset_id", None),
        script_source=getattr(job, "script_source", None),
        # ZH: Notebook 欄位 | EN: Notebook fields
        docker_image=job.docker_image,
        inline_code=job.inline_code,
        entry_args=json.dumps(job.entry_args) if job.entry_args else None,
        preferred_node=job.preferred_node if job.preferred_node not in (None, "auto", "") else None,
        status="pending"
    )
    db.add(db_job)
    db.commit()
    db.refresh(db_job)
    return db_job


def get_job(db: Session, job_id: str) -> Optional[models.TrainingJob]:
    """ZH: 依 ID 查詢任務 | EN: Query job by ID

    @node job-scheduler/app/crud.py::get_job
    """
    return db.query(models.TrainingJob).filter(
        models.TrainingJob.id == job_id
    ).first()


def get_jobs_by_user(
    db: Session,
    user_id: str,
    status: Optional[str] = None,
    limit: int = 20,
    offset: int = 0
) -> tuple[List[models.TrainingJob], int]:
    """
    ZH: 查詢使用者的任務列表 (含篩選、分頁)
    EN: Query user's job list (with filter, pagination)

    Returns: (jobs_list, total_count)

    @node job-scheduler/app/crud.py::get_jobs_by_user
    """
    query = db.query(models.TrainingJob).filter(
        models.TrainingJob.user_id == user_id
    )
    if status:
        query = query.filter(models.TrainingJob.status == status)

    total = query.count()
    jobs = query.order_by(desc(models.TrainingJob.created_at)).offset(offset).limit(limit).all()
    return jobs, total


def get_all_jobs(
    db: Session,
    status: Optional[str] = None,
    limit: int = 20,
    offset: int = 0
) -> tuple[List[models.TrainingJob], int]:
    """
    ZH: 查詢所有任務 (管理員用) | EN: Query all jobs (admin only)

    @node job-scheduler/app/crud.py::get_all_jobs
    """
    query = db.query(models.TrainingJob)
    if status:
        query = query.filter(models.TrainingJob.status == status)

    total = query.count()
    jobs = query.order_by(desc(models.TrainingJob.created_at)).offset(offset).limit(limit).all()
    return jobs, total


# ZH: v3.6 內建訓練腳本 —— 使用者只上傳資料就能訓練，不必自己寫程式。
#     key 是「任務種類」，worker 端有一支同名腳本。**這裡是唯一的清單**，
#     送單驗證與派工都讀它，不要在別處另抄一份。
# EN: v3.6 built-in training scripts, keyed by task type. Single source of truth.
BUILTIN_TASKS = {
    "image_classification": {
        "desc":  "ZH: 圖片分類（每個類別一個資料夾）| EN: Image classification (one folder per class)",
        # ZH: **指名映像**，不要落到 worker 的 DEFAULT_IMAGE。內建腳本需要 torchvision，
        #     而「預設映像剛好有沒有」不是可以賭的事——賭輸的症狀是任務起來就 ImportError，
        #     而使用者根本不知道自己選過映像。這裡用平台既有的學期鎖定映像。
        # EN: Pin the image. The built-in script hard-depends on torchvision; relying on
        #     whatever the worker's default happens to be is a silent-failure bet.
        # ZH: 與 PLATFORM_TRAINING_IMAGE 同一個值——但這裡明確寫出來，
        #     因為日後不同任務**可能**需要不同映像（那時這裡就會分岔）。
        "image": "aibase/pytorch:2026-spring",
    },
}
DEFAULT_BUILTIN_TASK = "image_classification"


# ZH: v3.6 平台的標準訓練環境。**自帶程式的單也用它**——
#     自己寫訓練程式的人幾乎一定需要 torchvision / sklearn / pandas 這些，
#     而 worker 的 DEFAULT_IMAGE 是精簡的公版映像（本機還沒有，要拉 4 GB）。
#     實測踩過：第一張自帶程式的單花了好幾分鐘在拉那個映像。
PLATFORM_TRAINING_IMAGE = "aibase/pytorch:2026-spring"


def default_training_image(job) -> Optional[str]:
    """ZH: 這張單該用哪個映像（使用者沒自己選時）。

    ZH: 內建腳本與自帶程式都走平台的標準環境。其餘（實驗室、自訂入口）回 None，
        交給 worker 的預設 —— 那些路徑本來就有自己的映像選擇。

    @node job-scheduler/app/crud.py::default_training_image
    """
    if getattr(job, "docker_image", None):
        return job.docker_image
    if getattr(job, "script_source", None) or builtin_task_for(job):
        return PLATFORM_TRAINING_IMAGE
    return None


def builtin_task_image(task: str) -> Optional[str]:
    """ZH: 這個內建任務要用哪個映像。

    @node job-scheduler/app/crud.py::builtin_task_image
    """
    return (BUILTIN_TASKS.get(task) or {}).get("image")


def builtin_task_for(job) -> Optional[str]:
    """ZH: 這張單要用哪一支內建腳本？沒有就回 None（＝自己帶程式的任務）。

    ZH: 判準：**有資料集**，而且**沒有自己指定執行方式**（inline_code / entry_args）。
        自己帶程式的人一定是想跑自己的東西，不該被換成內建腳本。

    ZH: `config["task"]` 可以指名；沒指名就用預設。**指名了但不認得則回 None**——
        由送單端把它變成明確的錯誤，不要在這裡默默退回預設而跑出使用者沒要的東西。

    @node job-scheduler/app/crud.py::builtin_task_for
    """
    if not getattr(job, "dataset_path", None):
        return None
    # ZH: 自己帶程式的人（inline_code / entry_args / script_source）一定是想跑自己的東西，
    #     不該被換成內建腳本。
    if (getattr(job, "inline_code", None) or getattr(job, "entry_args", None)
            or getattr(job, "script_source", None)):
        return None
    cfg = getattr(job, "config", None)
    if isinstance(cfg, str):
        try:
            cfg = json.loads(cfg)
        except (ValueError, TypeError):
            cfg = None
    task = (cfg or {}).get("task") or DEFAULT_BUILTIN_TASK
    return task if task in BUILTIN_TASKS else None


def job_needs_lab_volume(job) -> bool:
    """ZH: 這個任務是否需要使用者 Lab 的檔案（因而只能在與服務層同機的節點上跑）。

    ZH: 判準是 `inline_code` —— 那是 Lab 的 VS Code 擴充套件（aibase-runner）把
        cell/檔案編譯成 shell script 送過來的，腳本裡的相對路徑都指向 /home/coder。
        該目錄來自 per-user 的 `home_<uid>` Docker volume，**只在服務層那台機器上有內容**。

    @node job-scheduler/app/crud.py::job_needs_lab_volume
    """
    return bool(getattr(job, "inline_code", None))


def has_colocated_worker(db: Session, timeout_seconds: int = 90) -> bool:
    """ZH: 線上是否有「與服務層同機」的節點（看得到 home_<uid> volume）。

    ZH: 用於送單時就攔下不可能執行的任務——否則它會永遠 pending，
        而「永遠排隊」是另一種沉默失敗。

    ZH: 沿用 pool_has_online_worker 的判準：**「在線但被停用／時段外」不算數**，
        否則會誤判有人接而讓任務卡死。

    @node job-scheduler/app/crud.py::has_colocated_worker
    """
    for n in get_online_worker_nodes(db, timeout_seconds=timeout_seconds):
        if not getattr(n, "shares_storage", 0):
            continue
        if node_dispatch_state(get_gpu_node(db, n.node_id))["allowed"]:
            return True
    return False


def get_pending_jobs(db: Session) -> List[models.TrainingJob]:
    """
    ZH: 取得待處理任務 (按優先級排序，排程器使用)
    EN: Get pending jobs (sorted by priority, used by scheduler)

    @node job-scheduler/app/crud.py::get_pending_jobs
    """
    return db.query(models.TrainingJob).filter(
        models.TrainingJob.status == "pending"
    ).order_by(
        desc(models.TrainingJob.priority),
        models.TrainingJob.created_at
    ).all()


def get_running_jobs_count(db: Session) -> int:
    """ZH: 取得正在執行的任務數量 | EN: Get running jobs count

    @node job-scheduler/app/crud.py::get_running_jobs_count
    """
    return db.query(models.TrainingJob).filter(
        models.TrainingJob.status == "running"
    ).count()


def update_job_status(
    db: Session,
    job_id: str,
    status: str,
    gpu_server: Optional[str] = None,
    gpu_id: Optional[int] = None,
    error_message: Optional[str] = None,
    output_path: Optional[str] = None
) -> Optional[models.TrainingJob]:
    """
    ZH: 更新任務狀態 (由排程器呼叫)
    EN: Update job status (called by scheduler)

    @node job-scheduler/app/crud.py::update_job_status
    """
    job = get_job(db, job_id)
    if not job:
        return None

    job.status = status

    if gpu_server:
        job.gpu_server = gpu_server
    if gpu_id is not None:
        job.gpu_id = gpu_id
    if error_message:
        job.error_message = error_message
    if output_path:
        job.output_path = output_path

    # ZH: 自動設定時間戳 | EN: Auto-set timestamps
    if status == "running" and not job.started_at:
        job.started_at = datetime.now(timezone.utc)
    elif status in ("completed", "failed", "cancelled"):
        job.completed_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(job)
    return job


def update_job_progress(db: Session, job_id: str, progress: float) -> Optional[models.TrainingJob]:
    """ZH: 更新任務進度 | EN: Update job progress

    @node job-scheduler/app/crud.py::update_job_progress
    """
    job = get_job(db, job_id)
    if job:
        job.progress = progress
        db.commit()
        db.refresh(job)
    return job


def append_job_log(db: Session, job_id: str, new_log: str) -> Optional[models.TrainingJob]:
    """ZH: 附加日誌 | EN: Append execution log

    @node job-scheduler/app/crud.py::append_job_log
    """
    job = get_job(db, job_id)
    if job:
        current_logs = job.logs or ""
        job.logs = current_logs + new_log + "\n"
        db.commit()
        db.refresh(job)
    return job


def resolve_dataset_for_user(db: Session, user_id: str, root: str,
                             dataset_id=None, dataset_path=None):
    """ZH: 把送單帶來的資料集參照解析成「**確認屬於這個人**」的一份資料集。

    ZH: 回傳 (dataset, path) 或 (None, None)。兩種輸入都走這裡，
        避免兩條路各驗一次而其中一條忘了驗——那正是原本的情況。

    ZH: `dataset_id` 是正解：伺服器自己去查，客戶端拿不到也改不了別人的。
        `dataset_path` 是相容用法：**比對它是不是這個人自己的某一份**，
        不是「看起來像在資料集目錄底下就好」——後者連別人的目錄都算通過。

    @node job-scheduler/app/crud.py::resolve_dataset_for_user
    """
    import os as _os
    if dataset_id:
        ds = get_dataset(db, dataset_id)
        if not ds or ds.user_id != user_id:
            return None, None
        return ds, dataset_file_path(root, ds)

    if dataset_path:
        want = _os.path.normpath(dataset_path)
        for ds in list_datasets(db, user_id):
            if _os.path.normpath(dataset_file_path(root, ds)) == want:
                return ds, dataset_path
        return None, None

    return None, None


def dataset_file_path(root: str, ds) -> str:
    """ZH: 一份資料集在磁碟上的位置。**唯一定義**——上傳、下載、刪除都走這裡。

    @node job-scheduler/app/crud.py::dataset_file_path
    """
    import os as _os
    return _os.path.join(root, ds.user_id, ds.stored_name)


def list_datasets(db: Session, user_id: str) -> List[models.Dataset]:
    """ZH: 某人的資料集，新的在前。

    @node job-scheduler/app/crud.py::list_datasets
    """
    return (db.query(models.Dataset)
            .filter(models.Dataset.user_id == user_id)
            .order_by(desc(models.Dataset.created_at))
            .all())


def get_dataset(db: Session, dataset_id: str) -> Optional[models.Dataset]:
    """@node job-scheduler/app/crud.py::get_dataset"""
    return db.query(models.Dataset).filter(models.Dataset.id == dataset_id).first()


def dataset_active_jobs(db: Session, dataset_id: str) -> int:
    """ZH: 有幾張**還沒跑完**的單在用這份資料集。

    ZH: 刪除前要看這個：資料集刪掉、任務還在排隊的話，
        它會在領工之後才失敗，而使用者根本不會把兩件事聯想在一起。

    @node job-scheduler/app/crud.py::dataset_active_jobs
    """
    return (db.query(models.TrainingJob)
            .filter(models.TrainingJob.dataset_id == dataset_id,
                    models.TrainingJob.status.in_(("pending", "queued", "running")))
            .count())


def delete_dataset(db: Session, ds, remove_file) -> None:
    """ZH: 刪掉一份資料集（實體 + DB）。

    ZH: 已經跑完的任務**保留**它的 dataset_id 參照——DB 那邊是 SET NULL，
        紀錄還在，只是指不到檔案了。刪資料集不該連歷史紀錄一起消失。

    @node job-scheduler/app/crud.py::delete_dataset
    """
    remove_file(ds)
    db.delete(ds)
    db.commit()


def create_dataset(db: Session, user_id: str, original_name: str,
                   stored_name: str, size_bytes: int) -> models.Dataset:
    """@node job-scheduler/app/crud.py::create_dataset"""
    ds = models.Dataset(user_id=user_id, original_name=original_name,
                        stored_name=stored_name, size_bytes=size_bytes)
    db.add(ds)
    db.commit()
    db.refresh(ds)
    return ds


def purge_artifact(db: Session, job, remove_file) -> int:
    """ZH: 清掉一張單的模型檔（實體 + DB 標記），回傳釋放的位元組數。

    ZH: `remove_file` 由呼叫端傳進來，是為了讓測試可以在不碰真實檔案系統的情況下
        驗「DB 與實體檔案是一起處理的」——這兩件事分開做的話，會出現
        「DB 說有、檔案不在」（下載 410）或「檔案還在、DB 說沒有」（永遠不會被清）。

    @node job-scheduler/app/crud.py::purge_artifact
    """
    size = job.artifact_bytes or 0
    remove_file(job.id)
    job.artifact_bytes = None
    db.commit()
    return size


def enforce_artifact_limits(db: Session, user_id: str, keep: int, remove_file) -> int:
    """ZH: 每位使用者最多保留 `keep` 個模型檔，超過的從最舊的開始清。回傳清掉幾個。

    ZH: 為什麼上限用「個數」而不是「總容量」：使用者看得懂「你最近的 10 個模型」，
        看不懂「你用了 437 MB」。而且模型大小差異不大，個數已經夠當界限。

    @node job-scheduler/app/crud.py::enforce_artifact_limits
    """
    rows = (db.query(models.TrainingJob)
            .filter(models.TrainingJob.user_id == user_id,
                    models.TrainingJob.artifact_bytes.isnot(None))
            .order_by(desc(models.TrainingJob.created_at))
            .all())
    removed = 0
    for job in rows[keep:]:
        purge_artifact(db, job, remove_file)
        removed += 1
    return removed


def purge_expired_artifacts(db: Session, ttl_days: int, remove_file) -> dict:
    """ZH: 清掉超過保留天數的模型檔。收拾「不再使用的帳號」留下的長尾。

    ZH: 依 `completed_at` 而不是 `created_at`——一張排隊很久才跑的單，
        保留期該從它產出東西那一刻算起。

    @node job-scheduler/app/crud.py::purge_expired_artifacts
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=ttl_days)
    rows = (db.query(models.TrainingJob)
            .filter(models.TrainingJob.artifact_bytes.isnot(None))
            .all())
    stats = {"removed": 0, "freed_bytes": 0}
    for job in rows:
        when = job.completed_at or job.created_at
        if when is None:
            continue
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        if when < cutoff:
            stats["freed_bytes"] += purge_artifact(db, job, remove_file)
            stats["removed"] += 1
    return stats


def set_job_artifact(db: Session, job_id: str, size_bytes: int) -> Optional[models.TrainingJob]:
    """ZH: 記下這張單的模型檔大小（＝服務層這邊真的有那個檔）。

    @node job-scheduler/app/crud.py::set_job_artifact
    """
    job = get_job(db, job_id)
    if job:
        job.artifact_bytes = size_bytes
        db.commit()
        db.refresh(job)
    return job


def append_job_metric(db: Session, job_id: str, metric: dict) -> Optional[models.TrainingJob]:
    """ZH: 附加指標資料 (存為 JSON array) | EN: Append metric data (stored as JSON array)

    @node job-scheduler/app/crud.py::append_job_metric
    """
    job = get_job(db, job_id)
    if job:
        current_metrics = []
        if job.metrics:
            try:
                current_metrics = json.loads(job.metrics)
            except (json.JSONDecodeError, ValueError) as e:
                logger.warning("append_job_metric: failed to parse metrics JSON for job=%s: %s", job_id, e)
        current_metrics.append(metric)
        job.metrics = json.dumps(current_metrics)
        db.commit()
        db.refresh(job)
    return job


def cancel_job(db: Session, job_id: str) -> Optional[models.TrainingJob]:
    """
    ZH: 取消任務 (僅 pending/queued 可取消)
    EN: Cancel job (only pending/queued can be cancelled)

    @node job-scheduler/app/crud.py::cancel_job
    """
    job = get_job(db, job_id)
    if not job:
        return None
    if job.status not in ("pending", "queued"):
        return None
    job.status = "cancelled"
    job.completed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(job)
    return job


def get_queue_position(db: Session, job_id: str) -> Optional[int]:
    """ZH: 計算任務在佇列中的位置 | EN: Calculate job's queue position

    @node job-scheduler/app/crud.py::get_queue_position
    """
    job = get_job(db, job_id)
    if not job or job.status not in ("pending", "queued"):
        return None

    ahead_count = db.query(models.TrainingJob).filter(
        models.TrainingJob.status.in_(["pending", "queued"]),
        models.TrainingJob.priority >= job.priority,
        models.TrainingJob.created_at < job.created_at
    ).count()

    return ahead_count + 1


# ==============================================================================
# ZH: 工具函式 | EN: Utility functions
# ==============================================================================

def _calculate_next_reset_date(db: Session = None) -> datetime:
    """
    ZH: 計算下一個 Token 重置日期
    EN: Calculate next token reset date

    ZH: 邏輯：找到下一個每月第 token_reset_day 天。有 db 就讀 runtime 設定，否則回 .env 預設。
    EN: Find the next Nth day of the month. Reads runtime setting when db given, else .env default.

    @node job-scheduler/app/crud.py::_calculate_next_reset_date
    """
    now = datetime.now(timezone.utc)
    reset_day = get_setting(db, "token_reset_day") if db is not None else settings.TOKEN_RESET_DAY
    reset_day = min(reset_day, 28)  # ZH: 最多 28 避免日期溢出 | EN: Max 28

    if now.day < reset_day:
        # ZH: 本月還沒到重置日 | EN: This month hasn't reached reset day yet
        return now.replace(day=reset_day, hour=0, minute=0, second=0, microsecond=0)
    else:
        # ZH: 在下個月重置 | EN: Reset next month
        if now.month == 12:
            return now.replace(year=now.year + 1, month=1, day=reset_day,
                             hour=0, minute=0, second=0, microsecond=0)
        else:
            return now.replace(month=now.month + 1, day=reset_day,
                             hour=0, minute=0, second=0, microsecond=0)
# ==============================================================================
# ZH: 聊天紀錄 CRUD | EN: Chat History CRUD
# ==============================================================================

def create_chat_history(db: Session, chat: models.ChatHistory) -> models.ChatHistory:
    """ZH: 建立單筆對話紀錄 | EN: Create a single chat history record

    @node job-scheduler/app/crud.py::create_chat_history
    """
    db.add(chat)
    # ZH: 注意：此處不呼叫 commit()，由呼叫者控制事務 | EN: Caller handles commit
    return chat


# ==============================================================================
# ZH: 動態模型清單 | EN: Dynamic model list
# ==============================================================================

def list_public_models(db: Session, tool_type: str = "chat") -> List[models.Model]:
    """ZH: 列出某工具「公開且適用」的模型（tool_types 以逗號邊界精確比對，避免子字串誤判）。
       EN: List public models applicable to a tool (exact comma-split match).

    @node job-scheduler/app/crud.py::list_public_models
    """
    tt = (tool_type or "chat").strip().lower()
    rows = (
        db.query(models.Model)
        .filter(models.Model.is_public == 1)
        .order_by(models.Model.created_at.asc())
        .all()
    )
    out: List[models.Model] = []
    for m in rows:
        tools = [t.strip().lower() for t in (m.tool_types or "chat").split(",") if t.strip()]
        if tt in tools:
            out.append(m)
    return out


# ==============================================================================
# ZH: Token 估算 | EN: Token Estimation
# ==============================================================================

def estimate_job_tokens(config: Optional[dict]) -> int:
    """
    ZH: 依訓練配置估算 Token 消耗（epochs × 1000，最低 1000）
    EN: Estimate token cost from training config (epochs × 1000, minimum 1000)

    @node job-scheduler/app/crud.py::estimate_job_tokens
    """
    epochs = 10
    if config and "epochs" in config:
        try:
            epochs = int(config["epochs"])
        except (TypeError, ValueError):
            pass
    return max(1000, epochs * 1000)


# ==============================================================================
# ZH: Worker 心跳 CRUD | EN: Worker Heartbeat CRUD
# ==============================================================================

def upsert_worker_heartbeat(
    db: Session, node_id: str, available_gpus: List[str], gpu_utilization: float,
    gpus_detail: Optional[list] = None, pool_type: Optional[str] = None,
    source_ip: Optional[str] = None, shares_storage: bool = False,
) -> models.WorkerHeartbeat:
    """ZH: 更新或新增 Worker 節點心跳；v3.2 順帶自動註冊 gpu_nodes + NODE_ID 撞名偵測
       EN: Upsert worker heartbeat; v3.2 also auto-registers gpu_nodes + duplicate-ID detection

    @node job-scheduler/app/crud.py::upsert_worker_heartbeat
    """
    node = db.query(models.WorkerHeartbeat).filter(
        models.WorkerHeartbeat.node_id == node_id
    ).first()
    now = datetime.now(timezone.utc)
    detail_json = json.dumps(gpus_detail) if gpus_detail is not None else None
    pool = normalize_pool(pool_type)   # v3.0 節點所屬池（未帶＝batch）
    if node:
        # ZH: v3.2 撞名偵測 — 上一筆心跳「還新鮮」卻換了來源 IP ＝ 兩台機器用同一個
        #     NODE_ID 在輪流蓋寫（.env 範本預設 gpu-node-01 抄多台的實務地雷）→ 記警示 10 分鐘
        # EN: v3.2 duplicate-ID detection — fresh heartbeat but source IP flipped means
        #     two machines share one NODE_ID; flag a 10-minute warning.
        if source_ip and node.source_ip and source_ip != node.source_ip:
            last = node.last_seen
            if last is not None and last.tzinfo is None:
                last = last.replace(tzinfo=timezone.utc)
            if last is not None and (now - last) < timedelta(seconds=90):
                node.ip_conflict_until = now + timedelta(minutes=10)
        if source_ip:
            node.source_ip = source_ip
        node.available_gpus = json.dumps(available_gpus)
        node.gpu_utilization = gpu_utilization
        if detail_json is not None:
            node.gpus_detail = detail_json
        node.pool_type = pool
        # ZH: v3.6 —— **每次心跳都覆寫，不保留舊值**。刻意如此：
        #     舊版 worker 不送這個欄位（於是是 False），若改成「沒說就沿用」，
        #     一台原本同機、後來被搬走又降版的節點會繼續自稱同機——那正是要防的情況。
        node.shares_storage = 1 if shares_storage else 0
        node.last_seen = now
        node.is_online = True
    else:
        node = models.WorkerHeartbeat(
            node_id=node_id,
            available_gpus=json.dumps(available_gpus),
            gpu_utilization=gpu_utilization,
            gpus_detail=detail_json if detail_json is not None else "[]",
            pool_type=pool,
            last_seen=now,
            is_online=True,
            source_ip=source_ip,
            # ZH: v3.6 —— 沒宣告＝0（不同機），往安全的方向倒。
            shares_storage=1 if shares_storage else 0,
        )
        db.add(node)
    # ZH: v3.2 自動註冊節點設定列（不存在才建；預設 啟用+全天可排，行為與加表前一致）
    # EN: v3.2 auto-register the gpu_nodes config row (defaults keep legacy behavior)
    if db.query(models.GpuNode).filter(models.GpuNode.node_id == node_id).first() is None:
        db.add(models.GpuNode(node_id=node_id))
    db.commit()
    db.refresh(node)
    return node


# ZH: Notebook CRUD 已於 Phase E 移除 — 被 v2.0 Lab Manager 取代
# EN: Notebook CRUD removed in Phase E — superseded by v2.0 Lab Manager


# ==============================================================================
# ZH: Worker 節點查詢 | EN: Worker Node Query
# ==============================================================================

def get_online_worker_nodes(db: Session, timeout_seconds: int = 90) -> List[models.WorkerHeartbeat]:
    """
    ZH: 取得在線的 Worker 節點列表（最後心跳在 timeout_seconds 秒內）
    EN: Get online worker nodes (last heartbeat within timeout_seconds)

    @node job-scheduler/app/crud.py::get_online_worker_nodes
    """
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=timeout_seconds)
    return db.query(models.WorkerHeartbeat).filter(
        models.WorkerHeartbeat.last_seen >= cutoff
    ).order_by(models.WorkerHeartbeat.node_id).all()


def pool_has_online_worker(db: Session, pool_type: str, timeout_seconds: int = 90) -> bool:
    """ZH: v3.0 該池是否有「可派工」的在線 worker。派工墊底邏輯用：互動池沒人時，batch 才代領互動任務。
       v3.2：改為節點管理感知——(1) 池別以 admin 覆蓋值優先於 worker 自報；
       (2) 「在線但被停用/時段外」的節點不算數，否則互動任務會誤判有人接而卡死 pending。
       EN: v3.2 node-mgmt aware — pool override wins over worker-reported, and
       online-but-not-dispatchable nodes (disabled / out of window) don't count.

    @node job-scheduler/app/crud.py::pool_has_online_worker
    """
    pool = normalize_pool(pool_type)
    for n in get_online_worker_nodes(db, timeout_seconds=timeout_seconds):
        cfg = get_gpu_node(db, n.node_id)
        if effective_pool(cfg, getattr(n, "pool_type", "batch")) != pool:
            continue
        if node_dispatch_state(cfg)["allowed"]:
            return True
    return False


# ==============================================================================
# ZH: v3.2 GPU 節點管理 — 派工閘門 / 池別覆蓋 / 狀態列表 / 設定更新
# EN: v3.2 GPU node management — dispatch gate / pool override / status / update
# ==============================================================================
from . import gpu_schedule  # noqa: E402  (純函式模組，無循環相依)

VALID_NODE_FIELDS = {"display_name", "note", "enabled", "pool_override",
                     "schedule", "dispatch_buffer_min"}


def get_gpu_node(db: Session, node_id: str) -> Optional[models.GpuNode]:
    """ZH: 取節點設定列（可能為 None＝尚未心跳註冊）| EN: node config row (None = never seen)

    @node job-scheduler/app/crud.py::get_gpu_node
    """
    return db.query(models.GpuNode).filter(models.GpuNode.node_id == node_id).first()


def effective_pool(node_cfg: Optional[models.GpuNode], reported_pool) -> str:
    """ZH: 生效池 = admin 覆蓋值優先，否則 worker 自報 | EN: override wins, else worker-reported

    @node job-scheduler/app/crud.py::effective_pool
    """
    if node_cfg is not None and node_cfg.pool_override:
        return normalize_pool(node_cfg.pool_override)
    return normalize_pool(reported_pool)


def node_dispatch_state(node_cfg: Optional[models.GpuNode],
                        at: Optional[datetime] = None) -> dict:
    """
    ZH: 節點此刻可否派工。回 {"allowed": bool, "reason": "ok|disabled|out_of_window|bad_schedule"}。
        未註冊/未設定 = 允許（向後相容）。schedule 解析失敗視為「全天可排」並回報 bad_schedule
        於 reason 尾註（fail-open：設定壞掉不該讓整台機器消失，狀態欄會示警）。
    EN: Whether the node may take jobs now. Missing row = allowed. A corrupt schedule
        fails open (always-on) and is surfaced for the status panel.

    @node job-scheduler/app/crud.py::node_dispatch_state
    """
    if node_cfg is None:
        return {"allowed": True, "reason": "ok"}
    if not node_cfg.enabled:
        return {"allowed": False, "reason": "disabled"}
    try:
        windows = gpu_schedule.parse_schedule(node_cfg.schedule)
    except (ValueError, TypeError, json.JSONDecodeError):
        return {"allowed": True, "reason": "ok_bad_schedule"}
    buffer_min = max(0, int(node_cfg.dispatch_buffer_min or 0))
    if gpu_schedule.is_open(windows, at=at, buffer_min=buffer_min):
        return {"allowed": True, "reason": "ok"}
    return {"allowed": False, "reason": "out_of_window"}


def update_gpu_node(db: Session, node_id: str, fields: dict) -> models.GpuNode:
    """
    ZH: 更新節點設定（僅白名單欄位）。schedule 先過 parse 驗證（存原始 JSON 字串）；
        pool_override 限 batch/interactive/空（空＝清除覆蓋）；buffer 夾 0–1440。
        節點列不存在時建立（允許 admin 在機器上線前先建好設定）。
    EN: Update node config (whitelisted fields only), validating schedule/pool/buffer.
        Creates the row if missing (pre-provisioning before the worker first appears).

    @node job-scheduler/app/crud.py::update_gpu_node
    """
    node = get_gpu_node(db, node_id)
    if node is None:
        node = models.GpuNode(node_id=node_id)
        db.add(node)

    unknown = set(fields.keys()) - VALID_NODE_FIELDS
    if unknown:
        raise ValueError(f"不明欄位：{sorted(unknown)}")

    if "schedule" in fields:
        raw = fields["schedule"]
        if raw in (None, "", {}):
            node.schedule = None                      # 清除＝全天可排
        else:
            gpu_schedule.parse_schedule(raw)          # 格式錯誤在此丟 ValueError
            node.schedule = raw if isinstance(raw, str) else json.dumps(raw)
    if "pool_override" in fields:
        po = (fields["pool_override"] or "").strip()
        if po and po not in VALID_POOLS:
            raise ValueError(f"pool_override 須為 {sorted(VALID_POOLS)} 或留空")
        node.pool_override = po or None
    if "enabled" in fields:
        node.enabled = 1 if fields["enabled"] in (True, 1, "1", "true") else 0
    if "dispatch_buffer_min" in fields:
        try:
            node.dispatch_buffer_min = min(1440, max(0, int(fields["dispatch_buffer_min"] or 0)))
        except (ValueError, TypeError):
            raise ValueError("dispatch_buffer_min 須為整數分鐘")
    if "display_name" in fields:
        node.display_name = (fields["display_name"] or "").strip() or None
    if "note" in fields:
        node.note = (fields["note"] or "").strip() or None

    db.commit()
    db.refresh(node)
    return node


def pool_availability(db: Session, timeout_seconds: int = 90) -> dict:
    """
    ZH: v3.2 Phase 1.5 — 各池「現在有沒有可派工節點；沒有的話最快幾點開放」。
        給學生端送單前的期待管理（任務 pending 不是壞掉、是在等時段）。語意對齊 take_job：
        - available = 存在「在線 + 啟用 + 時段內(含停派緩衝)」且 effective pool 匹配的節點
        - interactive 額外含 batch 墊底：互動池無可派節點時 batch 會代領 → 看 batch 的 available
        - next_open = 未開放時，啟用節點中「時段最早開放」時刻（全天可排但離線的節點給不出
          時間 → 不列入；全部給不出 → None，前端顯示「等機器上線」措辭）
    EN: Per-pool availability + earliest next window opening, matching take_job semantics
        (incl. batch backfill for interactive).

    @node job-scheduler/app/crud.py::pool_availability
    """
    online_ids = {n.node_id for n in get_online_worker_nodes(db, timeout_seconds=timeout_seconds)}
    hb_map = {h.node_id: h for h in db.query(models.WorkerHeartbeat).all()}
    cfg_map = {c.node_id: c for c in db.query(models.GpuNode).all()}

    avail = {"batch": False, "interactive": False}
    next_open: dict = {"batch": None, "interactive": None}

    for node_id in set(hb_map) | set(cfg_map):
        hb, cfg = hb_map.get(node_id), cfg_map.get(node_id)
        pool = effective_pool(cfg, getattr(hb, "pool_type", "batch"))
        if node_id in online_ids and node_dispatch_state(cfg)["allowed"]:
            avail[pool] = True
            continue
        # ZH: 沒開放 → 若是「啟用 + 有時段表 + 目前時段外」，取它下一次開放時刻當候選
        if cfg is None or not cfg.enabled:
            continue
        try:
            windows = gpu_schedule.parse_schedule(cfg.schedule)
        except (ValueError, TypeError, json.JSONDecodeError):
            continue
        if windows is None:
            continue   # 全天可排卻不可用＝離線，給不出「幾點會好」
        open_now, nxt = gpu_schedule.next_transition(windows)
        if not open_now and nxt is not None:
            if next_open[pool] is None or nxt < next_open[pool]:
                next_open[pool] = nxt

    # ZH: interactive 的 batch 墊底（同 take_job：互動池沒人可派時 batch 代領）
    inter_avail = avail["interactive"] or avail["batch"]
    inter_next = next_open["interactive"]
    if not inter_avail:
        for cand in (next_open["interactive"], next_open["batch"]):
            if cand is not None and (inter_next is None or cand < inter_next):
                inter_next = cand

    return {
        "batch": {"available": avail["batch"],
                  "next_open": next_open["batch"].isoformat() if (not avail["batch"] and next_open["batch"]) else None},
        "interactive": {"available": inter_avail,
                        "next_open": inter_next.isoformat() if (not inter_avail and inter_next) else None},
    }


def list_gpu_nodes_with_status(db: Session, timeout_seconds: int = 90) -> list:
    """
    ZH: 給 admin 狀態欄 — 聯集「設定列 ∪ 心跳列」，每節點回：設定 + 心跳即時值 +
        四態狀態(offline/disabled/out_of_window/idle|working) + 下次開/關時間 +
        執行中任務 + 累計完成/失敗數 + NODE_ID 撞名警示。
    EN: Admin status panel — union of config and heartbeat rows with live state,
        next transition, running jobs, per-node totals, duplicate-ID warning.

    @node job-scheduler/app/crud.py::list_gpu_nodes_with_status
    """
    now = datetime.now(timezone.utc)
    hb_map = {h.node_id: h for h in db.query(models.WorkerHeartbeat).all()}
    cfg_map = {c.node_id: c for c in db.query(models.GpuNode).all()}
    out = []
    for node_id in sorted(set(hb_map) | set(cfg_map)):
        hb, cfg = hb_map.get(node_id), cfg_map.get(node_id)

        last_seen = getattr(hb, "last_seen", None)
        if last_seen is not None and last_seen.tzinfo is None:
            last_seen = last_seen.replace(tzinfo=timezone.utc)
        online = bool(last_seen and (now - last_seen) < timedelta(seconds=timeout_seconds))

        dispatch = node_dispatch_state(cfg)
        # ZH: 顯示用時段狀態（不含緩衝）與下次切換 | EN: display open-state (no buffer) + next flip
        schedule_error = False
        try:
            windows = gpu_schedule.parse_schedule(cfg.schedule) if cfg else None
        except (ValueError, TypeError, json.JSONDecodeError):
            windows, schedule_error = None, True
        open_now, next_change = gpu_schedule.next_transition(windows)

        running = db.query(models.TrainingJob).filter(
            models.TrainingJob.gpu_server == node_id,
            models.TrainingJob.status == "running",
        ).all()

        if not online:
            state = "offline"
        elif cfg is not None and not cfg.enabled:
            state = "disabled"
        elif not dispatch["allowed"]:
            state = "out_of_window_draining" if running else "out_of_window"
        else:
            state = "working" if running else "idle"

        conflict_until = getattr(hb, "ip_conflict_until", None)
        if conflict_until is not None and conflict_until.tzinfo is None:
            conflict_until = conflict_until.replace(tzinfo=timezone.utc)

        done = db.query(models.TrainingJob).filter(
            models.TrainingJob.gpu_server == node_id,
            models.TrainingJob.status == "completed").count()
        failed = db.query(models.TrainingJob).filter(
            models.TrainingJob.gpu_server == node_id,
            models.TrainingJob.status == "failed").count()

        out.append({
            "node_id": node_id,
            "display_name": getattr(cfg, "display_name", None),
            "note": getattr(cfg, "note", None),
            "enabled": bool(cfg.enabled) if cfg is not None else True,
            "pool_override": getattr(cfg, "pool_override", None),
            "reported_pool": normalize_pool(getattr(hb, "pool_type", "batch")),
            "effective_pool": effective_pool(cfg, getattr(hb, "pool_type", "batch")),
            "schedule": getattr(cfg, "schedule", None),
            "schedule_error": schedule_error,
            "dispatch_buffer_min": getattr(cfg, "dispatch_buffer_min", 0) or 0,
            "state": state,
            "online": online,
            "last_seen": last_seen.isoformat() if last_seen else None,
            "gpu_utilization": getattr(hb, "gpu_utilization", None),
            "gpus_detail": json.loads(getattr(hb, "gpus_detail", "[]") or "[]"),
            "window_open_now": open_now,
            "next_change": next_change.isoformat() if next_change else None,
            "running_jobs": [
                {"id": j.id, "job_name": j.job_name, "user_id": j.user_id,
                 "started_at": j.started_at.isoformat() if j.started_at else None}
                for j in running
            ],
            "completed_total": done,
            "failed_total": failed,
            "ip_conflict": bool(conflict_until and conflict_until > now),
            "source_ip": getattr(hb, "source_ip", None),
        })
    return out


# ==============================================================================
# ZH: SystemConfig 讀寫 | EN: SystemConfig get/set
# ==============================================================================

def get_system_config(db: Session, key: str, default: str = "") -> str:
    """ZH: 讀設定值，不存在回 default | EN: Read config value, default if missing

    @node job-scheduler/app/crud.py::get_system_config
    """
    row = db.query(models.SystemConfig).filter(models.SystemConfig.key == key).first()
    return row.value if row else default


def set_system_config(db: Session, key: str, value: str, description: Optional[str] = None) -> models.SystemConfig:
    """ZH: 寫設定值 (upsert) | EN: Upsert config value

    @node job-scheduler/app/crud.py::set_system_config
    """
    row = db.query(models.SystemConfig).filter(models.SystemConfig.key == key).first()
    if row:
        row.value = value
        if description is not None:
            row.description = description
    else:
        row = models.SystemConfig(key=key, value=value, description=description)
        db.add(row)
    db.commit()
    db.refresh(row)
    return row


# ==============================================================================
# ZH: v3.1 step 6 — 營運型系統設定（可經 admin「系統設定」頁即時調整）
#     每個 key：型別、預設(讀 .env/Settings)、範圍夾限。SystemConfig 有值就覆寫，否則用預設。
#     設計原則：只放「非機密 + 非開機必需 + scheduler 端讀 + runtime 可讀」的營運旋鈕。
# EN: v3.1 step 6 — runtime-tunable operational settings (admin UI). SystemConfig overrides
#     the .env/Settings default; values are type-checked and clamped to a safe range.
# ==============================================================================
# ZH: 分組。**有順序** —— 畫面就照這個順序分區，前端不另外排。
#
# ZH: 為什麼分組定義放後端而不是前端：新增一個旋鈕時，`group` 是**必填**
#     （下面有自檢會擋），所以加設定的人一定會想「這屬於哪一區」。
#     放前端的話，前端那份對照表遲早漏掉新的 key，而漏掉的表現是
#     那個旋鈕**安靜地從畫面上消失**（它不屬於任何一區）。
# ZH: `view` 是「平台設定」頁面上那個兩格滑條要把這一組放哪一邊。
#     分組（group）是「這是什麼」，檢視（view）是「管理者何時會來看它」——
#     兩者不一對一：小基自己是一組，但它跟平台一起看。
SETTING_GROUPS = [
    {"key": "platform",  "view": "platform", "label": "平台營運"},
    {"key": "myai",      "view": "myai",     "label": "MYAI 廠商整合"},
    {"key": "assistant", "view": "platform", "label": "小基（RAG 助手）"},
    # ZH: v3.8 寄信自成一區。塞進「平台營運」的話那一區會變成 9 個旋鈕,
    #     而 SMTP 是「壞了整批通知就全部不會到」的東西,值得自己一格。
    #     view 仍是 platform —— 分區是「這是什麼」,檢視是「何時會來看它」。
    {"key": "email",     "view": "platform", "label": "寄信（SMTP）"},
]
_VIEW_KEYS = {"platform", "myai"}

# ZH: 星號（starred）的意思（擁有者裁定 2026-08-27）：
#       這個值**使用者看得到**，或者**改之前應該先公告**。
#     不是「比較重要」也不是「比較危險」 —— 同步間隔改錯一樣會出事，
#     但那是內部的事，不需要先跟使用者說。
#
# ZH: 預設不標。新增旋鈕時不會因為忘了標而變成誤報，
#     反過來漏標一個該標的只是少一個提醒 —— 比亂標好。
_GROUP_KEYS = {g["key"] for g in SETTING_GROUPS}


SYSTEM_SETTINGS = {
    "monthly_token_limit":      {"starred": True, "group": "platform", "type": "int",   "default": lambda: settings.DEFAULT_MONTHLY_TOKEN_LIMIT, "min": 0,   "max": None, "label": "每月 Token 額度(新帳號預設；改既有帳號用批量設定)"},
    "token_reset_day":          {"starred": True, "public": True, "group": "platform", "type": "int",   "default": lambda: settings.TOKEN_RESET_DAY,             "min": 1,   "max": 28,   "label": "額度重置日(每月第幾天)"},
    "job_timeout_minutes":      {"starred": True, "public": True, "group": "platform", "type": "int",   "default": lambda: settings.JOB_TIMEOUT_MINUTES,         "min": 1,   "max": None, "label": "任務逾時(分鐘)"},
    "myai_sync_interval_hours": {"group": "myai", "type": "int",   "default": lambda: settings.MYAI_SYNC_INTERVAL_HOURS,    "min": 0,   "max": 168,  "label": "MYAI 同步間隔(小時, 0=關閉)"},
    "rag_top_k":                {"group": "assistant", "type": "int",   "default": lambda: settings.RAG_TOP_K,                   "min": 1,   "max": 20,   "label": "小基 RAG 取回片段數"},
    "rag_min_score":            {"group": "assistant", "type": "float", "default": lambda: settings.RAG_MIN_SCORE,               "min": 0.0, "max": 1.0,  "label": "小基 RAG 相似度門檻"},
    "rag_history_turns":        {"group": "assistant", "type": "int",   "default": lambda: settings.RAG_HISTORY_TURNS,           "min": 0,   "max": 20,   "label": "小基 RAG 帶入對話輪數"},
    # v3.3 MYAI 自動開通
    "myai_autoprovision":       {"starred": True, "group": "myai", "type": "int",   "default": lambda: 0,                                    "min": 0,   "max": 1,    "label": "MYAI 首次登入自動開通(1=開, 0=關)"},
    "myai_init_pwd_days":       {"starred": True, "group": "myai", "type": "int",   "default": lambda: 30,                                   "min": 1,   "max": 180,  "label": "MYAI 初始密碼保存天數(逾期自動清除)"},
    "myai_initial_credit":      {"starred": True, "group": "myai", "type": "int",   "default": lambda: 0,                                    "min": 0,   "max": None, "label": "MYAI 新帳號初始點數(0=不發放)"},
    # v3.3 刪除使用者後 Lab volume 的封存保留天數（逾期背景任務真正刪除）
    "lab_archive_days":         {"starred": True, "public": True, "group": "platform", "type": "int",   "default": lambda: 30,                                   "min": 1,   "max": 365,  "label": "刪除帳號後 Lab 資料封存天數(逾期銷毀)"},
    # v3.4 有使用者在線時的 MYAI 輪詢間隔（無人在線會完全跳過，不受此值影響）
    "myai_active_poll_minutes": {"group": "myai", "type": "int",   "default": lambda: 3,                                    "min": 1,   "max": 60,   "label": "MYAI 輪詢間隔(分, 僅有人在線時; 無人時自動休息)"},
    "myai_usage_window_min":    {"group": "myai", "type": "int",   "default": lambda: 15,                                   "min": 1,   "max": 180,  "label": "判定「正在使用 MYAI」的時間窗(分)"},
    "bounce_scan_minutes":      {"group": "platform", "type": "int",   "default": lambda: 30,                                   "min": 0,   "max": 1440, "label": "退信回收掃描間隔(分, 0=停用)"},
    # ZH: v3.7 小基要用哪個模型回答。值是**模型登錄表裡的 api_model_id**，
    #     選項由「平台設定 → 模型」那張表決定，所以不必在這裡維護一份清單。
    #
    # ZH: ⚠ 選外部模型（Claude / Gemini）代表**把問題送到校外廠商**——
    #     而小基的程式家教模式會讀使用者自己的檔案。介面上要講清楚，
    #     這是政策決定不只是設定。
    # ZH: v3.8 SMTP 連線設定改為管理端可設（擁有者 2026-08-27 裁定）。
    #     🔴 **密碼刻意不在這裡** —— 見 effective_smtp() 的說明。
    "smtp_server":              {"group": "email", "type": "text",  "default": lambda: settings.SMTP_SERVER,      "min": None, "max": None, "maxlen": 253, "text_kind": "host",  "label": "SMTP 主機(留空=不實際寄出,只寫寄信紀錄)"},
    "smtp_port":                {"group": "email", "type": "int",   "default": lambda: settings.SMTP_PORT,        "min": 1,    "max": 65535, "label": "SMTP 埠(STARTTLS 通常是 587)"},
    "smtp_username":            {"group": "email", "type": "text",  "default": lambda: settings.SMTP_USERNAME,    "min": None, "max": None, "maxlen": 254, "text_kind": "any",   "label": "SMTP 帳號(密碼仍只從 .env 讀,不進資料庫)"},
    # ZH: v3.8 帳號刪除後,Lab 資料銷毀前的提醒。天數是「距離銷毀還有幾天」。
    #     ⚠ 保留期預設 30 天(lab_archive_days),所以第一封在**刪除當天**就寄出 ——
    #     那正是使用者最需要知道的時刻(「我的東西還在,但只剩 30 天」)。
    #     值會出現在信件內文,所以標星號。
    "lab_purge_first_days": {"starred": True, "group": "platform", "type": "int", "default": lambda: 30, "min": 0, "max": 365, "label": "Lab 資料銷毀前第一次提醒(剩幾天;0=不寄)"},
    "lab_purge_final_days": {"starred": True, "group": "platform", "type": "int", "default": lambda: 7,  "min": 0, "max": 365, "label": "Lab 資料銷毀前最後提醒(剩幾天;0=不寄)"},
    # ZH: v3.8 管理員告警信。收件人留空 = 完全不寄（預設就是留空）——
    #     一個沒有人填收件人的告警系統應該安靜，而不是往預設信箱亂寄。
    "admin_alert_emails":       {"group": "email", "type": "text",  "default": lambda: "",   "min": None, "max": None, "maxlen": 500, "text_kind": "emails", "label": "管理員告警收件人(逗號分隔;留空=不寄告警)"},
    "admin_alert_min_hours":    {"group": "email", "type": "int",   "default": lambda: 6,    "min": 1,    "max": 168,  "label": "同一類告警最短間隔(小時,避免壞掉時每輪都寄)"},
    "smtp_from_email": {"starred": True, "group": "email", "type": "text", "default": lambda: settings.SMTP_FROM_EMAIL, "min": None, "max": None, "maxlen": 254, "text_kind": "email", "label": "寄件者地址(使用者在信箱裡看到的寄件人)"},
    "rag_chat_model":           {"starred": True, "group": "assistant", "type": "choice", "default": lambda: settings.RAG_CHAT_MODEL,             "min": None, "max": None, "label": "小基回應用的模型"},
}


_RE_SETTING_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _validate_text_setting(key: str, spec: dict, raw) -> str:
    """
    ZH: 驗證文字型旋鈕。**擋下來的都是「存進去不會報錯、但用起來一定壞」的值。**

    ZH: 為什麼要驗：這些值最後會被丟進 smtplib 或信件標頭。
        主機名塞進 `https://smtp.x.com` 這種東西,連線會失敗在**背景任務裡**——
        管理者的畫面上一切正常,只有寄信紀錄裡多一筆 failed,而那一頁沒人天天看。

    ZH: 刻意**不驗**主機是否真的連得上：那是網路狀態不是設定合法性,
        而且驗了會讓「設定頁存檔」這個動作變成一次對外連線。

    @node job-scheduler/app/crud.py::_validate_text_setting
    """
    v = str(raw).strip()
    maxlen = spec.get("maxlen", 200)
    if len(v) > maxlen:
        raise ValueError(f"設定 {key} 太長（上限 {maxlen} 字元，收到 {len(v)}）")
    kind = spec.get("text_kind", "any")
    if kind == "host":
        if any(c.isspace() for c in v):
            raise ValueError(f"設定 {key} 不可有空白：{v}")
        if "://" in v or "/" in v:
            raise ValueError(f"設定 {key} 要填主機名，不是網址：{v}")
    elif kind == "email":
        if not _RE_SETTING_EMAIL.match(v):
            raise ValueError(f"設定 {key} 需為單一電子郵件地址：{v}")
    elif kind == "emails":
        # ZH: 逗號分隔的多個地址。**逐一驗**並回寫正規化後的字串 ——
        #     只驗整串的話，一個打錯的地址會混在裡面存進去，
        #     然後那一封告警安靜地少寄給一個人（其餘照常送達，所以沒人會發現）。
        if v:
            parts = [x.strip() for x in v.split(",")]
            bad = [x for x in parts if not _RE_SETTING_EMAIL.match(x)]
            if bad:
                raise ValueError(f"設定 {key} 這些不是有效的電子郵件地址：{', '.join(bad)}")
            v = ", ".join(parts)
    return v


def _clamp_setting(v, lo, hi):
    """@node job-scheduler/app/crud.py::_clamp_setting"""
    if lo is not None:
        v = max(lo, v)
    if hi is not None:
        v = min(hi, v)
    return v


def get_setting(db: Session, key: str):
    """
    ZH: 讀營運設定的「生效值」：SystemConfig 有值優先，否則回 .env/Settings 預設；一律夾範圍。
    EN: Effective value of an operational setting: SystemConfig override wins, else .env default; clamped.

    @node job-scheduler/app/crud.py::get_setting
    """
    spec = SYSTEM_SETTINGS[key]
    default = spec["default"]()
    raw = get_system_config(db, key, "")
    if raw is None or raw == "":
        return default
    # ZH: 🔴 字串型（choice）不能走數字轉換 —— `float("llama3:latest")` 會丟例外，
    #     然後**靜默退回預設值**：管理者選了 Claude，小基卻還在用 .env 的 Ollama，
    #     而畫面上顯示的是他選的那個。這種不一致沒有任何錯誤訊息。
    if spec["type"] == "choice":
        return raw
    # ZH: text 與 choice 同樣不能走數字轉換,但理由不同 ——
    #     choice 是「值必須在清單裡」,text 是「值本來就是自由文字」。
    #     兩個都掉進下面那個 try 的話,`int("smtp.gmail.com")` 會丟例外,
    #     然後**靜默退回 .env 的舊主機**:管理者改了設定、畫面顯示他改的值,
    #     信卻還是從舊主機寄出去。
    if spec["type"] == "text":
        return raw
    try:
        v = int(raw) if spec["type"] == "int" else float(raw)
    except (ValueError, TypeError):
        return default
    return _clamp_setting(v, spec["min"], spec["max"])


def rag_model_choices(db: Session) -> list:
    """ZH: 小基可以選的模型 —— 直接來自「平台設定 → 模型」那張登錄表。

    ZH: 不在程式碼裡另外維護一份清單：那樣管理者新增一個模型之後，
        小基的下拉還是舊的，而且沒有任何提示。

    ZH: `.env` 的預設值也要放進去（就算它沒被登錄）——
        否則「目前生效的值」在下拉裡找不到，畫面會顯示成別的東西。

    @node job-scheduler/app/crud.py::rag_model_choices
    """
    out, seen = [], set()
    fallback = settings.RAG_CHAT_MODEL
    if fallback:
        out.append({"value": fallback, "label": f"{fallback}（.env 預設，本機 Ollama）",
                    "provider": "ollama"})
        seen.add(fallback)
    for m in db.query(models.Model).order_by(models.Model.name).all():
        mid = (m.api_model_id or "").strip()
        if not mid or mid in seen:
            continue
        seen.add(mid)
        out.append({"value": mid,
                    "label": f"{m.name}（{m.api_provider or '?'}）",
                    "provider": (m.api_provider or "").lower()})
    return out


def rag_model_provider(db: Session, model_id: str) -> str:
    """ZH: 這個模型該走哪個 provider。查不到就當成 ollama（本機）。

    ZH: 🔴 查不到時**不要當成外部** —— 那會把問題送到校外，
        而管理者以為它還在本機跑。往「本機」的方向猜是安全的那一邊：
        最壞情況是 Ollama 沒有這個模型、明確報錯。

    @node job-scheduler/app/crud.py::rag_model_provider
    """
    row = (db.query(models.Model)
           .filter(models.Model.api_model_id == model_id).first())
    return ((row.api_provider or "ollama").lower() if row else "ollama")


# ZH: 自檢。漏標或標錯 group 的旋鈕會在**匯入時**就炸掉，
#     而不是安靜地從管理畫面上消失（後者沒有人會回報）。
_missing = [k for k, v in SYSTEM_SETTINGS.items()
            if v.get("group") not in _GROUP_KEYS]
if _missing:
    raise RuntimeError(
        "SYSTEM_SETTINGS 裡這些旋鈕沒有合法的 group：%s"
        "（可用：%s）" % (_missing, sorted(_GROUP_KEYS)))

# ZH: text 型旋鈕一定要宣告 maxlen 與 text_kind。
#     漏宣告不會當場壞掉 —— 它只是**悄悄不驗**，然後某個亂填的值被存進去，
#     壞在背景寄信任務裡。所以在匯入時就擋。
_VALID_TEXT_KINDS = {"any", "host", "email", "emails"}
_bad_text = [k for k, v in SYSTEM_SETTINGS.items()
             if v.get("type") == "text"
             and (v.get("maxlen") is None or v.get("text_kind") not in _VALID_TEXT_KINDS)]
if _bad_text:
    raise RuntimeError(
        "SYSTEM_SETTINGS 裡這些文字型旋鈕沒有宣告 maxlen 或 text_kind：%s"
        "（text_kind 可用：%s）" % (_bad_text, sorted(_VALID_TEXT_KINDS)))

# ZH: public（前台唯讀端點會送出去的白名單）必須同時是 starred。
#     星號的定義就是「值使用者看得到 **或** 改之前應先公告」——
#     一個旋鈕被前台讀走，它就**必然**滿足前半句。兩邊不一致代表有人只改了一邊，
#     而不一致的表現是：管理者在設定頁看不到星號，卻不知道改下去使用者當場就看得到。
_public_unstarred = [k for k, v in SYSTEM_SETTINGS.items()
                     if v.get("public") and not v.get("starred")]
if _public_unstarred:
    raise RuntimeError(
        "SYSTEM_SETTINGS 裡這些旋鈕標了 public 卻沒有 starred：%s"
        "（前台看得到的值一定要標星號）" % _public_unstarred)

# ZH: 同理，分組也要有合法的 view —— 漏標的話那一組在兩個檢視下都不會出現。
_bad_view = [g["key"] for g in SETTING_GROUPS if g.get("view") not in _VIEW_KEYS]
if _bad_view:
    raise RuntimeError(
        "SETTING_GROUPS 裡這些分組沒有合法的 view：%s"
        "（可用：%s）" % (_bad_view, sorted(_VIEW_KEYS)))


def get_all_settings(db: Session) -> list:
    """ZH: 給 admin GET — 每個 key 的 生效值/預設值/範圍/是否已覆寫。

    @node job-scheduler/app/crud.py::get_all_settings
    """
    out = []
    for key, spec in SYSTEM_SETTINGS.items():
        raw = get_system_config(db, key, "")
        item = {
            "key": key,
            "group": spec["group"],
            "starred": bool(spec.get("starred")),
            "label": spec["label"],
            "type": spec["type"],
            "value": get_setting(db, key),
            "default": spec["default"](),
            "min": spec["min"],
            "max": spec["max"],
            "overridden": raw not in (None, ""),
        }
        # ZH: 下拉型的旋鈕要把選項一起送 —— 前端不該自己去猜有哪些值。
        if spec["type"] == "choice":
            item["choices"] = rag_model_choices(db)
        out.append(item)
    return out


def get_public_settings(db: Session) -> dict:
    """
    ZH: 給**前台**的唯讀白名單 —— 只回 `public` 為真的旋鈕，只回 key 與生效值。

    ZH: 為什麼不共用 get_all_settings 再讓前端過濾：那樣**整張表都已經送到瀏覽器了**，
        過濾只是視覺上的。白名單必須在後端成立，前端過濾不算數。

    ZH: 為什麼不回 label：admin 的 label 是給管理者看的（例如「額度重置日(每月第幾天)」
        括號裡在解釋語意），前台要的是完整句子而且要中英兩版。
        文案留在 i18n.js 由前端組，後端只負責「值是多少」。

    ZH: 🔴 `monthly_token_limit` **刻意不在白名單裡**（擁有者 2026-08-27 裁定）——
        那個值只是**新帳號**的預設，既有使用者的額度各自不同。
        把它寫在前台，對絕大多數人都是**錯的數字**，而且錯得很有說服力。

    @node job-scheduler/app/crud.py::get_public_settings
    """
    return {k: get_setting(db, k)
            for k, spec in SYSTEM_SETTINGS.items() if spec.get("public")}


# ==============================================================================
# ZH: v3.8 組織對照（學系→學院、行政單位、校區）
# EN: v3.8 organisation lookups
# ==============================================================================

def seed_org_tables(db: Session) -> dict:
    """
    ZH: 第一次啟動時把種子資料填進兩張對照表。**表裡已經有東西就完全不動。**

    ZH: 為什麼不是每次啟動都對齊種子：那樣管理者改過的名字會在下次重開時被蓋回去，
        而且沒有任何提示。種子只是初值，真相在表裡（見 org_seed.py 的檔頭）。

    @node job-scheduler/app/crud.py::seed_org_tables
    """
    from . import org_seed
    out = {"departments": 0, "units": 0}
    if db.query(models.OrgDepartment).count() == 0:
        for college, depts in org_seed.COLLEGES.items():
            for name in depts:
                db.add(models.OrgDepartment(name=name, college=college))
                out["departments"] += 1
    if db.query(models.OrgUnit).count() == 0:
        for name, parent in org_seed.UNITS:
            db.add(models.OrgUnit(path=f"{parent}/{name}" if parent else name,
                                  name=name, parent=parent))
            out["units"] += 1
    if out["departments"] or out["units"]:
        db.commit()
        logger.info("組織對照種子資料已寫入: %s", out)
    return out


def college_of(db: Session, department: Optional[str]) -> Optional[str]:
    """
    ZH: 由學系推學院。查不到就回 None —— **不猜**。

    ZH: 查不到是正常情況，不是錯誤：使用者的 department 是自由文字，
        可能是舊系名、可能有錯字、也可能根本沒填。呼叫端要把 None
        顯示成「未分類」而不是硬塞一個學院進去 —— 塞錯的學院沒有人看得出來。

    @node job-scheduler/app/crud.py::college_of
    """
    if not department:
        return None
    row = (db.query(models.OrgDepartment)
           .filter(models.OrgDepartment.name == department.strip()).first())
    return row.college if row else None


def org_options(db: Session) -> dict:
    """ZH: 給下拉選單用的三份清單（學院含底下的系、行政單位、校區）。

    @node job-scheduler/app/crud.py::org_options
    """
    from . import org_seed
    depts = (db.query(models.OrgDepartment)
             .filter(models.OrgDepartment.active == 1)
             .order_by(models.OrgDepartment.college, models.OrgDepartment.name).all())
    units = (db.query(models.OrgUnit)
             .filter(models.OrgUnit.active == 1).all())
    return {
        "campuses": org_seed.CAMPUSES,
        "departments": [{"name": d.name, "college": d.college, "campus": d.campus}
                        for d in depts],
        "units": [{"path": u.path, "name": u.name, "parent": u.parent,
                   "campus": u.campus} for u in units],
    }


def effective_smtp(db: Session) -> dict:
    """
    ZH: SMTP 的**生效**連線設定 —— 全站唯一解析點。

    ZH: 為什麼一定要單一解析點：`smtp_server` 一旦可以被管理端覆寫，
        「寄信」與「退信回收」就會各自看到不同的主機。
        退信回收的 IMAP 主機是**從 SMTP 主機推導**的（smtp.x → imap.x），
        寄信端的比對又用 `from_email` 判斷「哪封退信是我們寄的」。
        兩邊分開讀的話，管理者換一次主機就會：信從新主機寄出、
        退信回收仍然輪詢舊主機、於是**所有退信都收不到而且沒有任何錯誤**。
        （同一形狀已經發生過：MYAI 廠商改版讓交易同步靜默失效 29 天。）

    ZH: 🔴 **密碼刻意不可設定，只從 `.env` 讀。**
        擁有者 2026-08-27 裁定。理由不是「懶得做」：
        SystemConfig 是明文表，admin 的設定頁會把值回填到畫面上，
        寄信紀錄與稽核也都讀得到那張表。把 SMTP 密碼放進去，
        等於多開一個「看得到管理頁就拿得到寄件帳號」的面孔，
        而現行所有密鑰都只從 `.env` 讀、絕不進版控。

    ZH: 回傳的 password 直接取 `.env`；其餘四項 SystemConfig 有覆寫就用覆寫。

    @node job-scheduler/app/crud.py::effective_smtp
    """
    return {
        "server":     get_setting(db, "smtp_server"),
        "port":       get_setting(db, "smtp_port"),
        "username":   get_setting(db, "smtp_username"),
        "from_email": get_setting(db, "smtp_from_email"),
        # ZH: 不經 SystemConfig。這一行是上面那段註解的實作。
        "password":   settings.SMTP_PASSWORD,
    }


def set_settings(db: Session, updates: dict) -> list:
    """
    ZH: 給 admin PUT — 逐鍵驗證型別+夾限後 upsert；值為 None/空字串＝清除覆寫(回退預設)。
        回傳更新後的完整設定表。未知 key 略過。
    EN: Validate/clamp each key then upsert; empty value clears the override (revert to default).

    @node job-scheduler/app/crud.py::set_settings
    """
    for key, val in updates.items():
        if key not in SYSTEM_SETTINGS:
            continue
        if val is None or (isinstance(val, str) and val.strip() == ""):
            row = db.query(models.SystemConfig).filter(models.SystemConfig.key == key).first()
            if row:
                db.delete(row)
                db.commit()
            continue
        spec = SYSTEM_SETTINGS[key]
        if spec["type"] == "choice":
            # ZH: 只接受選單裡真的有的值。不驗的話，一個打錯的模型名會被存進去，
            #     然後小基每次回答都失敗 —— 而設定頁看起來一切正常。
            allowed = {c["value"] for c in rag_model_choices(db)}
            v = str(val).strip()
            if v not in allowed:
                raise ValueError(f"設定 {key} 的值不在可選清單裡：{v}")
            set_system_config(db, key, v, description=spec["label"])
            continue
        if spec["type"] == "text":
            set_system_config(db, key, _validate_text_setting(key, spec, val),
                              description=spec["label"])
            continue
        try:
            v = int(val) if spec["type"] == "int" else float(val)
        except (ValueError, TypeError):
            raise ValueError(f"設定 {key} 需為 {spec['type']} 型別")
        v = _clamp_setting(v, spec["min"], spec["max"])
        set_system_config(db, key, str(v), description=spec["label"])
    return get_all_settings(db)


# ==============================================================================
# ZH: 外部 AI 帳號對應 CRUD (v2.5) | EN: External AI account mapping CRUD (v2.5)
# ==============================================================================

def get_external_account_by_user_id(db: Session, user_id: str) -> Optional[models.ExternalAiAccount]:
    """ZH: 取某使用者的廠商帳號對應 | EN: Get a user's vendor account mapping

    @node job-scheduler/app/crud.py::get_external_account_by_user_id
    """
    return db.query(models.ExternalAiAccount).filter(
        models.ExternalAiAccount.user_id == user_id
    ).first()


def list_external_accounts(db: Session) -> List[dict]:
    """ZH: 列出所有對應 (join users 帶平台帳號名) | EN: List all mappings (join users for username)

    @node job-scheduler/app/crud.py::list_external_accounts
    """
    rows = (
        db.query(models.ExternalAiAccount, models.User.username)
        .join(models.User, models.User.id == models.ExternalAiAccount.user_id)
        .order_by(models.User.username.asc())
        .all()
    )
    out: List[dict] = []
    for acc, username in rows:
        out.append({
            "id": acc.id,
            "user_id": acc.user_id,
            "platform_username": username,
            "vendor_username": acc.vendor_username,
            "status": acc.status,
            "note": acc.note,
            "updated_at": acc.updated_at,
        })
    return out


def create_external_account(
    db: Session, platform_username: str, vendor_username: str,
    status: str = "active", note: Optional[str] = None
) -> models.ExternalAiAccount:
    """ZH: 以平台帳號名建立對應 (查無使用者或已存在對應則拋 ValueError)
       EN: Create mapping by platform username (raises ValueError if user missing or mapping exists)

    @node job-scheduler/app/crud.py::create_external_account
    """
    user = get_user_by_username(db, platform_username)
    if not user:
        raise ValueError(f"platform user not found: {platform_username}")
    if get_external_account_by_user_id(db, user.id):
        raise ValueError(f"mapping already exists for: {platform_username}")
    acc = models.ExternalAiAccount(
        user_id=user.id, vendor_username=vendor_username,
        status=status or "active", note=note,
    )
    db.add(acc)
    db.commit()
    db.refresh(acc)
    return acc


def update_external_account(
    db: Session, account_id: str, vendor_username: Optional[str] = None,
    status: Optional[str] = None, note: Optional[str] = None
) -> Optional[models.ExternalAiAccount]:
    """ZH: 更新對應 | EN: Update mapping

    @node job-scheduler/app/crud.py::update_external_account
    """
    acc = db.query(models.ExternalAiAccount).filter(models.ExternalAiAccount.id == account_id).first()
    if not acc:
        return None
    if vendor_username is not None:
        acc.vendor_username = vendor_username
    if status is not None:
        acc.status = status
    if note is not None:
        acc.note = note
    db.commit()
    db.refresh(acc)
    return acc


def delete_external_account(db: Session, account_id: str) -> bool:
    """ZH: 刪除對應 | EN: Delete mapping

    @node job-scheduler/app/crud.py::delete_external_account
    """
    acc = db.query(models.ExternalAiAccount).filter(models.ExternalAiAccount.id == account_id).first()
    if not acc:
        return False
    db.delete(acc)
    db.commit()
    return True


def upsert_external_account_by_username(
    db: Session, platform_username: str, vendor_username: str
) -> str:
    """ZH: CSV 匯入用：以平台帳號名 upsert，回傳 'created'/'updated'/'skipped'
       EN: For CSV import: upsert by platform username, returns 'created'/'updated'/'skipped'

    @node job-scheduler/app/crud.py::upsert_external_account_by_username
    """
    user = get_user_by_username(db, platform_username)
    if not user:
        raise ValueError(f"platform user not found: {platform_username}")
    acc = get_external_account_by_user_id(db, user.id)
    if acc:
        if acc.vendor_username == vendor_username:
            return "skipped"
        acc.vendor_username = vendor_username
        db.commit()
        return "updated"
    db.add(models.ExternalAiAccount(user_id=user.id, vendor_username=vendor_username))
    db.commit()
    return "created"
