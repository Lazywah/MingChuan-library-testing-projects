"""
==============================================================================
Module 3: ORM 資料模型 (Database ORM Models)
==============================================================================
ZH: 用途：定義所有資料庫表的 Python 物件映射 (Object-Relational Mapping)
EN: Purpose: Define Python object mappings for all database tables (ORM)

ZH: 流程：
    1. 每個 Class 對應一張 SQLite 表
    2. 繼承 database.py 中的 Base
    3. SQLAlchemy 自動處理 SQL ↔ Python 物件轉換
    4. init_db() 呼叫時自動建立所有表
EN: Flow:
    1. Each Class maps to one SQLite table
    2. Inherits Base from database.py
    3. SQLAlchemy auto-handles SQL ↔ Python object conversion
    4. All tables auto-created when init_db() is called

ZH: 模組化設計：
    - 新增表只需在此檔案新增一個 Class
    - 不影響其他模組
    - 修改欄位後重啟即自動 migrate (開發階段)
EN: Modular design:
    - Adding tables only requires a new Class in this file
    - Does not affect other modules
    - Column changes auto-migrate on restart (dev phase)

ZH: 表清單 (依 AI_PROGRAMMING_SPEC.md Section 4.1)：
EN: Table list (per AI_PROGRAMMING_SPEC.md Section 4.1):
    1. User          → users
    2. TokenUsage    → token_usage
    3. TrainingJob   → training_jobs
    4. Model         → models
    5. ChatHistory   → chat_history
    6. SystemConfig  → system_config
==============================================================================
"""

from sqlalchemy import (
    Column, String, Integer, DateTime, Date, Text, Float, ForeignKey,
    LargeBinary, PrimaryKeyConstraint, UniqueConstraint,
)
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
import uuid

from .database import Base


def generate_uuid() -> str:
    """ZH: 產生 UUID 字串 | EN: Generate UUID string"""
    return str(uuid.uuid4())


# ==============================================================================
# ZH: 表 1: User - 使用者認證與管理
# EN: Table 1: User - Authentication and management
# ZH: 角色：student (學生) / teacher (教師) / admin (管理員)
# EN: Roles: student / teacher / admin
# ==============================================================================
class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=generate_uuid)              # ZH: UUID 主鍵 | EN: UUID primary key
    username = Column(String, unique=True, index=True, nullable=False)        # ZH: 使用者名稱 | EN: Username
    email = Column(String, unique=True, index=True, nullable=False)           # ZH: 電子郵件 | EN: Email
    hashed_password = Column(String, nullable=False)                          # ZH: 雜湊密碼 | EN: Hashed password
    role = Column(String, nullable=False, default="student")                  # ZH: 角色 | EN: Role
    is_active = Column(Integer, default=1)                                    # ZH: 啟用狀態 | EN: Active status
    last_login_time = Column(DateTime, nullable=True)                         # ZH: 最後登入時間 | EN: Last login time
    last_login_ip = Column(String, nullable=True)                             # ZH: 最後登入IP | EN: Last login IP
    last_activity = Column(DateTime, nullable=True, index=True)               # ZH: 最後活動時間 (v2.1 修正：取代 online_status) | EN: Last activity time (v2.1: supersedes online_status)
    online_status = Column(Integer, default=0)                                # ZH: 已 deprecated，admin 端動態計算 | EN: Deprecated, computed dynamically
    is_test_account = Column(Integer, default=0)                              # ZH: 測試帳號標記 (0:否, 1:是) | EN: Test account flag
    tutorial_dismissed = Column(Integer, default=0)                           # ZH: 是否不再顯示教學 (0:否, 1:是) | EN: Tutorial dismissed (0:no, 1:yes)
    department = Column(String, nullable=True)                                # ZH: 學系資訊 | EN: Department
    login_count = Column(Integer, default=0)                                  # ZH: 登入次數 | EN: Login count
    lifetime_tokens_used = Column(Integer, default=0)                         # ZH: 歷史累計 Token 數 | EN: Lifetime tokens used
    disk_quota_gb = Column(Integer, default=10)                               # ZH: 個人磁碟配額 GB (v2.0 Lab) | EN: Personal disk quota GB
    # v2.1 SSO OIDC 整合 | v2.1 SSO OIDC integration
    auth_source = Column(String, default="local", nullable=False)             # ZH: local / sso_mock / sso_cas / sso_oidc | EN: auth source identifier
    external_id = Column(String, nullable=True, index=True)                   # ZH: OIDC oid (Microsoft 永久 ID), CAS 為 NULL | EN: OIDC oid (Microsoft permanent ID)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))                    # ZH: 建立時間 | EN: Created at
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))  # ZH: 更新時間 | EN: Updated at


# ==============================================================================
# ZH: 表 2: TokenUsage - Token 用量追蹤
# EN: Table 2: TokenUsage - Token usage tracking
# ZH: 每位使用者一筆記錄，記錄月度 Token 消耗與上限
# EN: One record per user, tracks monthly token consumption and limit
# ==============================================================================
class TokenUsage(Base):
    __tablename__ = "token_usage"

    id = Column(String, primary_key=True, default=generate_uuid)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    tokens_used = Column(Integer, default=0)                                  # ZH: 已使用量 | EN: Tokens consumed
    tokens_limit = Column(Integer, default=5_000_000)                         # ZH: 月度上限 | EN: Monthly limit
    reset_date = Column(DateTime, nullable=False)                             # ZH: 下次重置日 | EN: Next reset date
    last_updated = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


# ==============================================================================
# ZH: 表 3: TrainingJob - 訓練任務佇列
# EN: Table 3: TrainingJob - Training job queue
# ZH: 狀態流轉：pending → queued → running → completed / failed / cancelled
# EN: Status flow: pending → queued → running → completed / failed / cancelled
# ==============================================================================
class TrainingJob(Base):
    __tablename__ = "training_jobs"

    id = Column(String, primary_key=True, default=generate_uuid)
    user_id = Column(String, ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True)
    job_name = Column(String, nullable=False)                                 # ZH: 任務名稱 | EN: Job name
    model_name = Column(String, nullable=False)                               # ZH: 模型名稱 | EN: Model name
    status = Column(String, default="pending", index=True)                    # ZH: 任務狀態 | EN: Job status
    gpu_required = Column(Integer, default=1)                                 # ZH: 需要 GPU 數 | EN: Required GPUs
    priority = Column(Integer, default=0)                                     # ZH: 優先級 | EN: Priority

    # ZH: 訓練配置 (JSON 字串) | EN: Training config (JSON string)
    config = Column(Text)                                                     # {"epochs":10, "batch_size":32}

    # ZH: 執行細節 | EN: Execution details
    gpu_server = Column(String)                                               # ZH: 分配的伺服器 | EN: Assigned server
    gpu_id = Column(Integer)                                                  # ZH: 分配的 GPU | EN: Assigned GPU
    script_path = Column(String)                                              # ZH: 訓練腳本路徑 | EN: Script path
    dataset_path = Column(String)                                             # ZH: 資料集路徑 | EN: Dataset path

    # ZH: Notebook 執行欄位 | EN: Notebook execution fields
    docker_image = Column(String, nullable=True)                              # ZH: 覆寫預設 Docker Image | EN: Override default Docker image
    inline_code  = Column(Text,   nullable=True)                              # ZH: 前端合併的完整 shell script | EN: Compiled shell script from notebook cells
    entry_args   = Column(Text,   nullable=True)                              # ZH: 容器入口指令 JSON 陣列 | EN: Container entry command (JSON array)
    preferred_node = Column(String, nullable=True)                            # ZH: 偏好的 GPU Worker 節點 | EN: Preferred GPU worker node

    # ZH: 進度追蹤 | EN: Progress tracking
    progress = Column(Float, default=0.0)                                     # ZH: 完成百分比 | EN: Completion %
    logs = Column(Text)                                                       # ZH: 執行日誌 | EN: Execution logs
    metrics = Column(Text)                                                    # ZH: 訓練指標 JSON | EN: Training metrics JSON
    error_message = Column(Text)                                              # ZH: 錯誤訊息 | EN: Error message

    # ZH: 輸出結果 | EN: Output result
    output_path = Column(String)                                              # ZH: 模型產出路徑 | EN: Output path

    # ZH: 時間戳記 | EN: Timestamps
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    started_at = Column(DateTime)
    completed_at = Column(DateTime)


# ==============================================================================
# ZH: 表 4: Model - 模型註冊表
# EN: Table 4: Model - Model registry
# ==============================================================================
class Model(Base):
    __tablename__ = "models"

    id = Column(String, primary_key=True, default=generate_uuid)
    name = Column(String, unique=True, nullable=False)                        # ZH: 模型名稱 | EN: Model name
    model_type = Column(String, default="local")                              # ZH: 模型類型 (api/local) | EN: Model type
    description = Column(Text)                                                # ZH: 描述 | EN: Description
    framework = Column(String)                                                # ZH: 框架 | EN: Framework
    storage_path = Column(String, default="")                                 # ZH: 儲存路徑 (本地模型用) | EN: Storage path (local)
    size_bytes = Column(Integer)                                              # ZH: 檔案大小 | EN: File size
    uploaded_by = Column(String, nullable=False)                              # ZH: 上傳者 | EN: Uploader
    is_public = Column(Integer, default=0)                                    # ZH: 公開旗標 | EN: Public flag

    # ZH: API 模型專用欄位 | EN: API model-specific fields
    api_provider = Column(String)                                             # ZH: API 供應商 (anthropic/openai/google) | EN: API provider
    api_endpoint = Column(String)                                             # ZH: API 端點 URL | EN: API endpoint URL
    api_model_id = Column(String)                                             # ZH: 上游模型 ID (e.g. gpt-4o) | EN: Upstream model ID

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


# ==============================================================================
# ZH: 表 5: ChatHistory - 聊天記錄
# EN: Table 5: ChatHistory - Chat conversation history
# ==============================================================================
class ChatHistory(Base):
    __tablename__ = "chat_history"

    id = Column(String, primary_key=True, default=generate_uuid)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    session_id = Column(String, index=True, nullable=False)                   # ZH: 對話工作階段 | EN: Chat session
    role = Column(String, nullable=False)                                     # ZH: 角色 | EN: Role (user/assistant)
    content = Column(Text, nullable=False)                                    # ZH: 訊息內容 | EN: Message content
    tool_type = Column(String, default="chat")                                # ZH: 工具類型 (chat, video_gen, writing) | EN: Tool type
    tokens_used = Column(Integer, default=0)                                  # ZH: Token 消耗 | EN: Tokens used
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


# ==============================================================================
# ZH: 表 6: SystemConfig - 系統設定
# EN: Table 6: SystemConfig - System configuration (Key-Value)
# ==============================================================================
class SystemConfig(Base):
    __tablename__ = "system_config"

    key = Column(String, primary_key=True)                                    # ZH: 設定鍵 | EN: Config key
    value = Column(String, nullable=False)                                    # ZH: 設定值 | EN: Config value
    description = Column(Text)                                                # ZH: 說明 | EN: Description
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


# ==============================================================================
# ZH: 表 7: WorkerHeartbeat - GPU Worker 節點心跳
# EN: Table 7: WorkerHeartbeat - GPU Worker node heartbeat
# ZH: 記錄各 Worker 節點最後一次回報時間與 GPU 狀態，供管理員儀表板顯示
# EN: Tracks last heartbeat and GPU state per Worker node for admin dashboard
# ==============================================================================
class WorkerHeartbeat(Base):
    __tablename__ = "worker_heartbeats"

    node_id = Column(String, primary_key=True)                                # ZH: 節點識別碼 | EN: Node identifier
    available_gpus = Column(Text, default="[]")                               # ZH: 可用 GPU 清單 (JSON) | EN: Available GPUs (JSON array)
    gpu_utilization = Column(Float, default=0.0)                              # ZH: GPU 使用率 % | EN: GPU utilization %
    last_seen = Column(DateTime, default=lambda: datetime.now(timezone.utc))  # ZH: 最後心跳時間 | EN: Last heartbeat time
    is_online = Column(Integer, default=1)                                    # ZH: 是否在線 | EN: Online status
    pool_type = Column(String, default="batch")                               # ZH: 節點池類型 batch/interactive (v2.0 Lab) | EN: Pool type batch/interactive


# ZH: 表 8 (Notebook) 已於 Phase E 移除 — 被 v2.0 Lab (table 9 LabSession) 取代
# EN: Table 8 (Notebook) removed in Phase E — superseded by v2.0 Lab (table 9 LabSession)
# ZH: training_jobs 的 docker_image / inline_code / entry_args / preferred_node 4 欄位保留
#     供 Lab 的「Run on GPU」延續使用，不在此處刪除。
# EN: training_jobs columns docker_image / inline_code / entry_args / preferred_node are
#     intentionally kept — v2.0 Lab's "Run on GPU" still uses them.


# ==============================================================================
# ZH: v2.0 Lab 模組 — 表 9–14
# EN: v2.0 Lab module — Tables 9–14
# ==============================================================================

# ==============================================================================
# ZH: 表 9: LabSession - code-server 工作階段
# EN: Table 9: LabSession - code-server session
# ZH: 複合 PK (user_id, session_name) 預留 v2.1 多 session 並行能力
#     v2.0 強制 session_name = "default"
# EN: Composite PK reserves multi-session support for v2.1; v2.0 enforces "default"
# ==============================================================================
class LabSession(Base):
    __tablename__ = "lab_sessions"

    user_id        = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    session_name   = Column(String, default="default")                        # ZH: v2.0 強制 "default" | EN: v2.0 = "default"
    container_id   = Column(String, nullable=True)                            # ZH: Docker 容器 ID | EN: Docker container ID
    container_name = Column(String, nullable=True)                            # ZH: 容器名稱 cs-{user_id} | EN: Container name
    status         = Column(String, default="stopped")                        # ZH: stopped / starting / running / stopping
    volume_name    = Column(String, nullable=False)                           # ZH: 對應 named volume，如 home_alice
    base_image     = Column(String, nullable=False, default="aibase/pytorch:2026-spring")  # ZH: 目前使用的 image
    last_activity  = Column(DateTime, default=lambda: datetime.now(timezone.utc))          # ZH: 最後活動時間
    started_at     = Column(DateTime, nullable=True)                          # ZH: 啟動時間
    cpu_quota      = Column(Float,   default=0.5)                             # ZH: CPU cores
    mem_quota_mb   = Column(Integer, default=2048)                            # ZH: RAM MB

    __table_args__ = (
        PrimaryKeyConstraint("user_id", "session_name"),
    )


# ==============================================================================
# ZH: 表 10: UserSecret - 使用者 secrets（AES-256-GCM 加密儲存）
# EN: Table 10: UserSecret - User secrets (AES-256-GCM encrypted)
# ==============================================================================
class UserSecret(Base):
    __tablename__ = "user_secrets"

    id          = Column(String, primary_key=True, default=generate_uuid)
    user_id     = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name        = Column(String, nullable=False)                              # ZH: 環境變數名稱，如 HF_TOKEN
    value_enc   = Column(LargeBinary, nullable=False)                         # ZH: AES-256-GCM 加密 (nonce + ciphertext + tag)
    created_at  = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at  = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                         onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_user_secret_name"),
    )


# ==============================================================================
# ZH: 表 11: QuotaGrant - 管理員配額提權紀錄（含審計）
# EN: Table 11: QuotaGrant - Admin quota grant records (with audit trail)
# ==============================================================================
class QuotaGrant(Base):
    __tablename__ = "quota_grants"

    id              = Column(String, primary_key=True, default=generate_uuid)
    user_id         = Column(String, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    extra_quota_gb  = Column(Integer, nullable=False)                         # ZH: 額外配額 GB（base 之上）
    granted_by      = Column(String, ForeignKey("users.id"), nullable=False)  # ZH: 核准的 admin
    reason          = Column(Text,   nullable=False)                          # ZH: 提權理由（必填審計用）
    granted_at      = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    expires_at      = Column(DateTime, nullable=True)                         # ZH: null = 永久
    revoked_at      = Column(DateTime, nullable=True)                         # ZH: null = 仍生效


# ==============================================================================
# ZH: 表 12: UserStorageState - 儲存生命週期狀態機
# EN: Table 12: UserStorageState - Storage lifecycle state machine
# ZH: 狀態：active / frozen / archived / pending_delete
# EN: States: active / frozen / archived / pending_delete
# ==============================================================================
class UserStorageState(Base):
    __tablename__ = "user_storage_state"

    user_id         = Column(String, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    state           = Column(String, default="active")                        # ZH: active/frozen/archived/pending_delete
    state_since     = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    current_size_gb = Column(Float, default=0.0)
    archive_path    = Column(String, nullable=True)                           # ZH: 歸檔後的 HDD 路徑（archived 狀態時非空）
    notes           = Column(Text, nullable=True)                             # ZH: admin 註記


# ==============================================================================
# ZH: 表 13: AdminAction - 管理員操作審計 log
# EN: Table 13: AdminAction - Admin action audit log
# ZH: 記錄所有 admin 對使用者資源的操作（quota / freeze / inject / delete 等）
# EN: Records all admin actions on user resources
# ==============================================================================
class AdminAction(Base):
    __tablename__ = "admin_actions"

    id          = Column(String, primary_key=True, default=generate_uuid)
    admin_id    = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    target_user = Column(String, ForeignKey("users.id"), nullable=True, index=True)
    action      = Column(String, nullable=False, index=True)                  # ZH: grant_quota/revoke_quota/freeze/archive/delete/inject_files/...
    payload     = Column(Text)                                                # ZH: JSON 詳細參數
    timestamp   = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    ip_address  = Column(String, nullable=True)                               # ZH: 執行者當時 IP


# ==============================================================================
# ZH: 表 14: UserSessionUsage - 使用者每日 session 累積時長
# EN: Table 14: UserSessionUsage - Per-user daily session usage
# ZH: 複合 PK (user_id, date)，每日一筆，scheduler 自動累加
# EN: Composite PK (user_id, date); scheduler updates daily
# ==============================================================================
class UserSessionUsage(Base):
    __tablename__ = "user_session_usage"

    user_id        = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    date           = Column(Date, nullable=False)
    total_seconds  = Column(Integer, default=0)                               # ZH: 該日累積秒數
    session_count  = Column(Integer, default=0)                               # ZH: 該日 session 次數

    __table_args__ = (
        PrimaryKeyConstraint("user_id", "date"),
    )
