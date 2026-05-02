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
from datetime import datetime, timedelta
from typing import Optional, List
import json

from . import models, schemas
from .config import settings

# ==============================================================================
# ZH: 密碼雜湊工具 | EN: Password hashing utility
# ==============================================================================
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def get_password_hash(password: str) -> str:
    """ZH: 將明文密碼轉為 bcrypt 雜湊 | EN: Hash plaintext password with bcrypt"""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """ZH: 驗證密碼是否匹配 | EN: Verify password matches hash"""
    return pwd_context.verify(plain_password, hashed_password)


# ==============================================================================
# ZH: 使用者 CRUD | EN: User CRUD
# ==============================================================================

def get_user_by_username(db: Session, username: str) -> Optional[models.User]:
    """ZH: 依使用者名稱查詢 | EN: Query user by username"""
    return db.query(models.User).filter(models.User.username == username).first()


def get_user_by_email(db: Session, email: str) -> Optional[models.User]:
    """ZH: 依電子郵件查詢 | EN: Query user by email"""
    return db.query(models.User).filter(models.User.email == email).first()


def get_user_by_id(db: Session, user_id: str) -> Optional[models.User]:
    """ZH: 依 ID 查詢 | EN: Query user by ID"""
    return db.query(models.User).filter(models.User.id == user_id).first()


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
    """
    hashed_password = get_password_hash(user.password)
    db_user = models.User(
        username=user.username,
        email=user.email,
        hashed_password=hashed_password,
        role=user.role
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)

    # ZH: 自動建立 Token 用量記錄 | EN: Auto-create token usage record
    next_month_reset = _calculate_next_reset_date()
    db_usage = models.TokenUsage(
        user_id=db_user.id,
        tokens_used=0,
        tokens_limit=settings.DEFAULT_MONTHLY_TOKEN_LIMIT,
        reset_date=next_month_reset
    )
    db.add(db_usage)
    db.commit()

    return db_user

def update_user(db: Session, db_user: models.User, update_data: schemas.UserUpdate) -> models.User:
    """ZH: 更新使用者資料 (如果不為空) | EN: Update user data if not None"""
    if update_data.email is not None:
        db_user.email = update_data.email
    if update_data.password is not None and update_data.password.strip():
        db_user.hashed_password = get_password_hash(update_data.password)
    if update_data.tutorial_dismissed is not None:
        db_user.tutorial_dismissed = update_data.tutorial_dismissed
    db.commit()
    db.refresh(db_user)
    return db_user

def create_sso_user(db: Session, username: str, email: str, role: str = "student") -> models.User:
    """SSO 登入時自動建立帳號 (無需讓使用者輸入密碼，系統給予隨機 hash 密碼)"""
    import secrets
    random_password = secrets.token_urlsafe(16)
    hashed_password = get_password_hash(random_password)
    
    db_user = models.User(
        username=username,
        email=email,
        hashed_password=hashed_password,
        role=role
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)

    # 自動建立 Token 用量記錄
    next_month_reset = _calculate_next_reset_date()
    db_usage = models.TokenUsage(
        user_id=db_user.id,
        tokens_used=0,
        tokens_limit=settings.DEFAULT_MONTHLY_TOKEN_LIMIT,
        reset_date=next_month_reset
    )
    db.add(db_usage)
    db.commit()

    return db_user

# ==============================================================================
# ZH: Token 用量 CRUD | EN: Token Usage CRUD
# ==============================================================================

def get_token_usage(db: Session, user_id: str) -> Optional[models.TokenUsage]:
    """ZH: 查詢使用者 Token 用量 | EN: Query user token usage"""
    return db.query(models.TokenUsage).filter(
        models.TokenUsage.user_id == user_id
    ).first()


def create_token_usage(db: Session, user_id: str) -> models.TokenUsage:
    """ZH: 建立 Token 用量記錄 (若不存在) | EN: Create token usage record (if not exists)"""
    next_month_reset = _calculate_next_reset_date()
    db_usage = models.TokenUsage(
        user_id=user_id,
        tokens_used=0,
        tokens_limit=settings.DEFAULT_MONTHLY_TOKEN_LIMIT,
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
    """
    usage = get_token_usage(db, user_id)
    if not usage:
        usage = create_token_usage(db, user_id)

    # ZH: 檢查是否需要月度重置 | EN: Check if monthly reset is needed
    if datetime.utcnow() >= usage.reset_date:
        usage.tokens_used = 0
        usage.reset_date = _calculate_next_reset_date()

    usage.tokens_used += tokens
    db.commit()
    db.refresh(usage)
    return usage


# ==============================================================================
# ZH: 訓練任務 CRUD | EN: Training Job CRUD
# ==============================================================================

def create_job(db: Session, job: schemas.JobCreate, user_id: str) -> models.TrainingJob:
    """
    ZH: 建立新訓練任務 (狀態 = pending)
    EN: Create new training job (status = pending)
    """
    db_job = models.TrainingJob(
        user_id=user_id,
        job_name=job.job_name,
        model_name=job.model_name,
        gpu_required=job.gpu_required,
        priority=job.priority,
        config=json.dumps(job.config) if job.config else None,
        script_path=job.script_path,
        dataset_path=job.dataset_path,
        status="pending"
    )
    db.add(db_job)
    db.commit()
    db.refresh(db_job)
    return db_job


def get_job(db: Session, job_id: str) -> Optional[models.TrainingJob]:
    """ZH: 依 ID 查詢任務 | EN: Query job by ID"""
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
    """
    query = db.query(models.TrainingJob)
    if status:
        query = query.filter(models.TrainingJob.status == status)

    total = query.count()
    jobs = query.order_by(desc(models.TrainingJob.created_at)).offset(offset).limit(limit).all()
    return jobs, total


def get_pending_jobs(db: Session) -> List[models.TrainingJob]:
    """
    ZH: 取得待處理任務 (按優先級排序，排程器使用)
    EN: Get pending jobs (sorted by priority, used by scheduler)
    """
    return db.query(models.TrainingJob).filter(
        models.TrainingJob.status == "pending"
    ).order_by(
        desc(models.TrainingJob.priority),
        models.TrainingJob.created_at
    ).all()


def get_running_jobs_count(db: Session) -> int:
    """ZH: 取得正在執行的任務數量 | EN: Get running jobs count"""
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
        job.started_at = datetime.utcnow()
    elif status in ("completed", "failed", "cancelled"):
        job.completed_at = datetime.utcnow()

    db.commit()
    db.refresh(job)
    return job


def update_job_progress(db: Session, job_id: str, progress: float) -> Optional[models.TrainingJob]:
    """ZH: 更新任務進度 | EN: Update job progress"""
    job = get_job(db, job_id)
    if job:
        job.progress = progress
        db.commit()
        db.refresh(job)
    return job


def append_job_log(db: Session, job_id: str, new_log: str) -> Optional[models.TrainingJob]:
    """ZH: 附加日誌 | EN: Append execution log"""
    job = get_job(db, job_id)
    if job:
        current_logs = job.logs or ""
        job.logs = current_logs + new_log + "\n"
        db.commit()
        db.refresh(job)
    return job


def append_job_metric(db: Session, job_id: str, metric: dict) -> Optional[models.TrainingJob]:
    """ZH: 附加指標資料 (存為 JSON array) | EN: Append metric data (stored as JSON array)"""
    job = get_job(db, job_id)
    if job:
        current_metrics = []
        if job.metrics:
            try:
                current_metrics = json.loads(job.metrics)
            except:
                pass
        current_metrics.append(metric)
        job.metrics = json.dumps(current_metrics)
        db.commit()
        db.refresh(job)
    return job


def cancel_job(db: Session, job_id: str) -> Optional[models.TrainingJob]:
    """
    ZH: 取消任務 (僅 pending/queued 可取消)
    EN: Cancel job (only pending/queued can be cancelled)
    """
    job = get_job(db, job_id)
    if not job:
        return None
    if job.status not in ("pending", "queued"):
        return None
    job.status = "cancelled"
    job.completed_at = datetime.utcnow()
    db.commit()
    db.refresh(job)
    return job


def get_queue_position(db: Session, job_id: str) -> Optional[int]:
    """ZH: 計算任務在佇列中的位置 | EN: Calculate job's queue position"""
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

def _calculate_next_reset_date() -> datetime:
    """
    ZH: 計算下一個 Token 重置日期
    EN: Calculate next token reset date

    ZH: 邏輯：找到下一個每月第 TOKEN_RESET_DAY 天
    EN: Logic: find the next Nth day of the month
    """
    now = datetime.utcnow()
    reset_day = min(settings.TOKEN_RESET_DAY, 28)  # ZH: 最多 28 避免日期溢出 | EN: Max 28

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
    """ZH: 建立單筆對話紀錄 | EN: Create a single chat history record"""
    db.add(chat)
    # ZH: 注意：此處不呼叫 commit()，由呼叫者控制事務 | EN: Caller handles commit
    return chat
