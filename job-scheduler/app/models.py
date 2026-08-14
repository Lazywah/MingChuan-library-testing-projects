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
    # ZH: v3.0 目標節點池 batch(高階 GPU 伺服器) / interactive(本地·服務層 GPU)。
    #     派工採「首選對應池 + batch 墊底」——見 routers/worker.take_job。舊資料 NULL 視為 batch。
    # EN: v3.0 target pool: batch(high-end GPU server) / interactive(local service-layer GPU).
    pool_type = Column(String, default="batch")                              # ZH: 目標節點池 | EN: Target node pool

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
    tool_types = Column(String, default="chat")                               # ZH: 適用工具 (CSV, e.g. "chat,presentation") | EN: Applicable tools (CSV)

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
class EmailLog(Base):
    """
    ZH: v3.4 寄信紀錄 —— 「我們試著寄給誰、結果如何」。
        ⚠️ 重要限制：SMTP 的 `sendmail()` 成功只代表**中繼伺服器收下了**，不代表送達。
        「網域存在但信箱不存在」會被中繼接受、稍後才**非同步退信到寄件人信箱**，
        程式端看不到 → 本表對該情況會記為 `sent`。本表的價值是提供對照名冊：
        收到退信時，可立刻查出那是誰、哪個功能、何時寄的。
        能明確記錄的失敗：連線/認證錯誤(`failed`)、收件人當下被拒(`refused`)。
    EN: v3.4 outbound email log. `sent` means accepted by the relay, NOT delivered —
        async bounces land in the sender's mailbox. Serves as a correlation roster.
    """
    __tablename__ = "email_log"

    id         = Column(String, primary_key=True, default=generate_uuid)
    to_email   = Column(String, nullable=False, index=True)
    user_id    = Column(String, nullable=True, index=True)   # ZH: 已知才填（不設 FK，帳號刪了仍留紀錄）
    username   = Column(String, nullable=True)
    kind       = Column(String, nullable=True)               # ZH: temp_password / login_alert / password_change_alert
    subject    = Column(String, nullable=True)
    status     = Column(String, nullable=False)              # ZH: sent / refused / failed / mock
                                                             #     v3.5 退信回填：bounced（永久，5.x.x）/ deferred（暫時，4.x.x）
    detail     = Column(Text, nullable=True)                 # ZH: 錯誤或被拒原因 / 退信診斷碼
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    # ZH: v3.5 退信回收 —— Message-ID 是把「非同步退信」對回「當初那一封」的唯一可靠鍵。
    #     只靠 to_email 比對，同一人寄過多封時會對錯封。
    message_id = Column(String, nullable=True, index=True)
    bounced_at = Column(DateTime, nullable=True)             # ZH: 收到退信的時間（status 轉 bounced/deferred）


class ArchivedLabVolume(Base):
    """
    ZH: v3.3 刪除使用者時，其 Lab volume 不立即銷毀，改「原地封存」並記錄於此。
        - 原地保留＝零複製成本（volume 300MB~1GB，搬移很慢），資料完全不動
        - 本表讓「刻意封存」與「來路不明的孤兒 volume」可以區分
        - 逾期由背景任務真正 remove；期限由 SystemConfig `lab_archive_days` 控制
        - 還原時把內容複製進目標使用者的新 volume（SSO 使用者回來是新 uuid）
    EN: v3.3 On user deletion the Lab volume is archived in place (zero-copy) and
        tracked here; purged after the retention window, restorable meanwhile.
    """
    __tablename__ = "archived_lab_volumes"

    id           = Column(String, primary_key=True, default=generate_uuid)
    volume_name  = Column(String, nullable=False, unique=True, index=True)   # ZH: Docker volume 名稱
    user_id      = Column(String, nullable=True)     # ZH: 原使用者 id（已刪除，故不設 FK）
    username     = Column(String, nullable=True)     # ZH: 快照原帳號名，供辨識
    email        = Column(String, nullable=True)
    size_bytes   = Column(Integer, nullable=True)    # ZH: 封存當下大小
    reason       = Column(String, nullable=True)     # ZH: 封存原因（admin_delete / adopted_orphan…）
    archived_at  = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    expires_at   = Column(DateTime, nullable=True)   # ZH: 逾此時間背景任務會真正刪除
    restored_at  = Column(DateTime, nullable=True)   # ZH: 已還原給誰/何時（保留紀錄）
    restored_to  = Column(String, nullable=True)


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
    gpus_detail = Column(Text, default="[]")                                  # ZH: 每張 GPU 詳細 (JSON: name/util/temp/mem) | EN: Per-GPU detail (JSON)
    last_seen = Column(DateTime, default=lambda: datetime.now(timezone.utc))  # ZH: 最後心跳時間 | EN: Last heartbeat time
    is_online = Column(Integer, default=1)                                    # ZH: 是否在線 | EN: Online status
    pool_type = Column(String, default="batch")                               # ZH: 節點池類型 batch/interactive (v2.0 Lab) | EN: Pool type batch/interactive
    # ZH: v3.2 節點管理 — 心跳來源 IP 與「同 ID 多來源」撞名偵測（NODE_ID 抄預設值的實務地雷）
    # EN: v3.2 node mgmt — heartbeat source IP + duplicate-NODE_ID detection
    source_ip = Column(String)                                                # ZH: 最近心跳來源 IP | EN: Latest heartbeat source IP
    ip_conflict_until = Column(DateTime)                                      # ZH: 撞名警示有效期 | EN: Conflict warning valid until


# ==============================================================================
# ZH: 表 7b: GpuNode - GPU 節點管理設定 (v3.2)
# EN: Table 7b: GpuNode - GPU node management config (v3.2)
# ZH: 節點第一次心跳自動註冊；admin 可設 開關/週時段/池別覆蓋/停派緩衝。
#     派工閘門在 /worker/take 讀本表；未註冊或未設定 = 啟用+全天可排（向後相容）。
# EN: Auto-registered on first heartbeat; admin sets enable/schedule/pool override/
#     dispatch buffer. Dispatch gate in /worker/take; missing row = always allowed.
# ==============================================================================
class GpuNode(Base):
    __tablename__ = "gpu_nodes"

    node_id = Column(String, primary_key=True)          # ZH: 對應 worker NODE_ID | EN: worker NODE_ID
    display_name = Column(String)                       # ZH: 人讀名稱（如「圖書館 3F-05") | EN: Human-readable name
    note = Column(Text)                                 # ZH: 位置/用途備註 | EN: Location/purpose note
    enabled = Column(Integer, default=1)                # ZH: 總開關（0=完全不派工）| EN: Master switch
    pool_override = Column(String)                      # ZH: 池別覆蓋 batch/interactive；NULL=依 worker 自報 | EN: Pool override; NULL=worker-reported
    schedule = Column(Text)                             # ZH: 週時段 JSON（見 gpu_schedule.py）；NULL=全天可排 | EN: Weekly schedule JSON; NULL=always
    dispatch_buffer_min = Column(Integer, default=0)    # ZH: 時段結束前 N 分鐘停派新工（drain 緩衝）| EN: Stop dispatching N min before window end
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


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
# ZH: 表 14-: Announcement - 首頁公告 (v2.2 新增)
# EN: Table 14-: Announcement - Homepage announcements (v2.2)
# ZH: admin 可在 admin UI 動態管理公告 (新增/編輯/置頂/刪除)
#     使用者首頁拉最新 N 則可見公告
# ==============================================================================
class Announcement(Base):
    __tablename__ = "announcements"

    id          = Column(Integer, primary_key=True, autoincrement=True)
    title       = Column(String, nullable=False)
    body        = Column(Text, nullable=False)
    posted_by   = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    posted_at   = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    updated_at  = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                                   onupdate=lambda: datetime.now(timezone.utc))
    is_pinned   = Column(Integer, default=0)                                # ZH: 1 = 置頂 (排在最前)
    is_visible  = Column(Integer, default=1)                                # ZH: 0 = 隱藏 (草稿/已下架)


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


# ==============================================================================
# ZH: 表 15: ExternalAiAccount - 外部 AI 廠商帳號對應 (v2.5 外部 AI 分流)
# EN: Table 15: ExternalAiAccount - external AI vendor account mapping
# ZH: 平台帳號 ↔ 廠商帳號 (myai168) 對應表。廠商無 API/SSO，僅能導流 + 帳號後台造冊，
#     故由 admin 批次匯入對應。安全原則：只存廠商帳號名，絕不存廠商密碼。
# EN: Bridges platform user ↔ vendor (myai168) account. Vendor offers no API/SSO,
#     only redirect + back-office provisioning; admin bulk-imports mappings.
#     Security: store vendor username only, NEVER the vendor password.
# ==============================================================================
class ExternalAiAccount(Base):
    __tablename__ = "external_ai_accounts"

    id              = Column(String, primary_key=True, default=generate_uuid)
    user_id         = Column(String, ForeignKey("users.id", ondelete="CASCADE"),
                             unique=True, index=True, nullable=False)          # ZH: 一位平台使用者一筆 | EN: one row per platform user
    vendor_username = Column(String, nullable=False)                          # ZH: 廠商端帳號 = myai email (非密碼) | EN: vendor account = myai email (not password)
    myai_vendor_sn  = Column(String, nullable=True, index=True)                # ZH: v2.8 對應 myai_accounts.vendor_sn 的穩定鍵 (email 改了也追得到) | EN: stable FK to myai_accounts.vendor_sn
    status          = Column(String, default="active", nullable=False)        # ZH: active / disabled | EN: active / disabled
    note            = Column(Text, nullable=True)                             # ZH: 備註 | EN: note
    created_at      = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at      = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                             onupdate=lambda: datetime.now(timezone.utc))

    # ==========================================================================
    # ZH: v3.3 自動開通 — 系統產生的 MYAI「初始密碼」暫存（憑證遞送，非密碼保管）
    #     ⚠️ 界線：這不是學生自選的密碼，而是我們替他建號時產生的一次性初始值。
    #     「絕不存學生密碼」原則不變 —— 學生一改密碼，這裡的值即失去意義。
    #     AES-256-GCM 加密（同 user_secrets 的 KEK）；逾期或學生按「已修改」即清除。
    # EN: v3.3 auto-provision — system-generated MYAI *initial* password, held briefly
    #     for delivery only (encrypted, auto-purged). Not a user-chosen password.
    # ==========================================================================
    init_pwd_enc    = Column(LargeBinary, nullable=True)                      # ZH: 加密後的初始密碼 | EN: encrypted initial password
    init_pwd_at     = Column(DateTime, nullable=True)                         # ZH: 發放時間（保存期起算）| EN: issued at (retention clock)
    init_pwd_ack    = Column(Integer, default=0)                              # ZH: 1=學生已按「我已修改」→ 立即清除 | EN: acknowledged


# ==============================================================================
# ZH: 表 16: KnowledgeChunk - RAG 知識庫片段 (v2.6 客服/導覽助手)
# EN: Table 16: KnowledgeChunk - RAG knowledge chunks (v2.6 support/guide assistant)
# ZH: 由 knowledge/*.md 切塊匯入，embedding 以 JSON 陣列字串存放（SQLite 無原生向量型別）。
#     知識庫規模小，查詢時全載入記憶體做 cosine（見 rag_service 規模備註）。
# EN: Ingested from knowledge/*.md; embedding stored as a JSON array string
#     (SQLite has no native vector type). Small KB → load all rows and cosine
#     in memory at query time (see rag_service scale note).
# ==============================================================================
class KnowledgeChunk(Base):
    __tablename__ = "knowledge_chunks"

    id          = Column(String, primary_key=True, default=generate_uuid)
    source      = Column(String, nullable=False, index=True)                  # ZH: 來源檔名 (相對 KNOWLEDGE_DIR) | EN: source file (relative to KNOWLEDGE_DIR)
    heading     = Column(String, default="")                                  # ZH: 最近標題 (引用/定位用) | EN: nearest heading (for citation)
    content     = Column(Text, nullable=False)                                # ZH: 片段內容 | EN: chunk text
    embedding   = Column(Text, nullable=False)                                # ZH: 向量 (JSON array string) | EN: vector (JSON array string)
    created_at  = Column(DateTime, default=lambda: datetime.now(timezone.utc))


# ==============================================================================
# ZH: 表 17: MyaiAccount - MYAI 廠商平台帳號/點數同步快取 (v2.8 唯讀同步)
# EN: Table 17: MyaiAccount - cached MYAI vendor account/credit sync (v2.8, read-only)
# ZH: headless 登入廠商管理後台 → 匯出使用者清單 → 存進此表供平台顯示。
#     以 email 對應到本平台使用者；只同步顯示，不回寫廠商。
# EN: Headless-login to vendor admin → export users → cache here for display.
#     Keyed by email; display-only, never written back to vendor.
# ==============================================================================
class MyaiAccount(Base):
    __tablename__ = "myai_accounts"

    id         = Column(String, primary_key=True, default=generate_uuid)
    vendor_sn  = Column(String, unique=True, index=True, nullable=False)       # ZH: 廠商編號 | EN: vendor user id (編號)
    email      = Column(String, index=True, nullable=True)                     # ZH: 對應本平台使用者的鍵 | EN: join key to our users
    name       = Column(String, nullable=True)                                 # ZH: 名稱 | EN: name
    user_type  = Column(String, nullable=True)                                 # ZH: 類型 (超級管理員/使用者) | EN: type
    points     = Column(Integer, default=0)                                    # ZH: 點數 = Token 餘額 | EN: credits (token balance)
    expiry     = Column(String, nullable=True)                                 # ZH: 有效期間 (原字串) | EN: expiry (raw string)
    status     = Column(String, nullable=True)                                 # ZH: 狀態 | EN: status
    newsletter = Column(String, nullable=True)                                 # ZH: 電子報 | EN: newsletter
    note       = Column(Text, nullable=True)                                   # ZH: 備註 | EN: note
    synced_at  = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))           # ZH: 最後同步時間 | EN: last sync time


# ==============================================================================
# ZH: 表 18: MyaiTransaction - 廠商交易日誌逐筆 (v2.8 消耗/工具別分析)
# EN: Table 18: MyaiTransaction - per-event vendor transaction log
# ZH: 來源：admin 專屬 /mcu/ai/admin/transaction（全體、逐筆）。每筆含事件(備註)、
#     點數變化、餘額、模型名。**不存 IP**（隱私）。以 dedup_key 去重（可重複同步）。
#     event_type：login / ai_usage(扣點) / transfer(配點) / other。
# EN: Sourced from the admin transaction log (all users, per event). Stores the
#     event/model, point delta, balance. **No IP stored**. Dedup via dedup_key.
# ==============================================================================
class MyaiTransaction(Base):
    __tablename__ = "myai_transactions"

    id           = Column(String, primary_key=True, default=generate_uuid)
    occurred_at  = Column(DateTime, index=True, nullable=True)                 # ZH: 事件時間(備註「時間」)| EN: event time
    vendor_sn    = Column(String, index=True, nullable=True)                   # ZH: 序號 | EN: vendor user id
    email        = Column(String, index=True, nullable=True)                  # ZH: 帳號 | EN: account email
    name         = Column(String, nullable=True)                              # ZH: 顯示名稱 | EN: display name
    points_delta = Column(Integer, default=0)                                 # ZH: 點數變化(負=消耗) | EN: point delta
    balance      = Column(Integer, default=0)                                 # ZH: 事件後餘額 | EN: balance after
    note         = Column(Text, nullable=True)                                # ZH: 備註原文(事件/模型名) | EN: raw note
    event_type   = Column(String, index=True, nullable=True)                  # ZH: login/ai_usage/transfer/other
    model        = Column(String, index=True, nullable=True)                  # ZH: 使用的模型(ai_usage 才有) | EN: model used
    dedup_key    = Column(String, unique=True, index=True, nullable=False)    # ZH: 去重鍵 | EN: 時間|序號|Δ|備註
    synced_at    = Column(DateTime, default=lambda: datetime.now(timezone.utc))


# ==============================================================================
# ZH: 表 19: MyaiModelMap - 廠商模型代碼 ↔ 顯示名稱/供應商/類別 對應表 (v2.9)
# EN: Table 19: MyaiModelMap - vendor model code ↔ display name / provider / category
# ZH: 廠商在備註欄給的是原始代碼(如 gpt_5_6_sol、nano_banana_pro)，難讀且對話模型
#     與工具混在一起。本表由 admin 手動維護，**僅在數據分析「顯示時」套用**，
#     不改寫 myai_transactions 原始資料 → 對錯了隨時改回，不會污染來源。
#     對不到的代碼在管理端會標成「未對應」，方便發現廠商新增/改名的模型。
# EN: Admin-maintained lookup applied at DISPLAY time only; raw tx rows are never
#     rewritten, so a wrong mapping is always reversible. Unmapped codes are
#     surfaced in the admin UI to catch new/renamed vendor models.
# ==============================================================================
class MyaiModelMap(Base):
    __tablename__ = "myai_model_map"

    id           = Column(String, primary_key=True, default=generate_uuid)
    code         = Column(String, unique=True, index=True, nullable=False)     # ZH: 廠商原始代碼 | EN: raw vendor code
    display_name = Column(String, nullable=True)                               # ZH: 顯示名稱 | EN: friendly name
    provider     = Column(String, index=True, nullable=True)                   # ZH: 供應商 (Anthropic/OpenAI/…) | EN: provider
    category     = Column(String, index=True, nullable=True)                   # ZH: 類別 (對話/簡報/文件/…) | EN: category
    note         = Column(Text, nullable=True)                                 # ZH: 備註(自用) | EN: admin note
    updated_at   = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                          onupdate=lambda: datetime.now(timezone.utc))
