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

from sqlalchemy import Column, String, Integer, DateTime, Text, Float
from datetime import datetime
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
    online_status = Column(Integer, default=0)                                # ZH: 在線狀態 (0:離線, 1:線上) | EN: Online status
    is_test_account = Column(Integer, default=0)                              # ZH: 測試帳號標記 (0:否, 1:是) | EN: Test account flag
    tutorial_dismissed = Column(Integer, default=0)                           # ZH: 是否不再顯示教學 (0:否, 1:是) | EN: Tutorial dismissed (0:no, 1:yes)
    created_at = Column(DateTime, default=datetime.utcnow)                    # ZH: 建立時間 | EN: Created at
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)  # ZH: 更新時間 | EN: Updated at


# ==============================================================================
# ZH: 表 2: TokenUsage - Token 用量追蹤
# EN: Table 2: TokenUsage - Token usage tracking
# ZH: 每位使用者一筆記錄，記錄月度 Token 消耗與上限
# EN: One record per user, tracks monthly token consumption and limit
# ==============================================================================
class TokenUsage(Base):
    __tablename__ = "token_usage"

    id = Column(String, primary_key=True, default=generate_uuid)
    user_id = Column(String, index=True, nullable=False)                      # ZH: 關聯使用者 | EN: Associated user
    tokens_used = Column(Integer, default=0)                                  # ZH: 已使用量 | EN: Tokens consumed
    tokens_limit = Column(Integer, default=5_000_000)                         # ZH: 月度上限 | EN: Monthly limit
    reset_date = Column(DateTime, nullable=False)                             # ZH: 下次重置日 | EN: Next reset date
    last_updated = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ==============================================================================
# ZH: 表 3: TrainingJob - 訓練任務佇列
# EN: Table 3: TrainingJob - Training job queue
# ZH: 狀態流轉：pending → queued → running → completed / failed / cancelled
# EN: Status flow: pending → queued → running → completed / failed / cancelled
# ==============================================================================
class TrainingJob(Base):
    __tablename__ = "training_jobs"

    id = Column(String, primary_key=True, default=generate_uuid)
    user_id = Column(String, index=True, nullable=False)                      # ZH: 提交者 | EN: Submitter
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

    # ZH: 進度追蹤 | EN: Progress tracking
    progress = Column(Float, default=0.0)                                     # ZH: 完成百分比 | EN: Completion %
    logs = Column(Text)                                                       # ZH: 執行日誌 | EN: Execution logs
    metrics = Column(Text)                                                    # ZH: 訓練指標 JSON | EN: Training metrics JSON
    error_message = Column(Text)                                              # ZH: 錯誤訊息 | EN: Error message

    # ZH: 輸出結果 | EN: Output result
    output_path = Column(String)                                              # ZH: 模型產出路徑 | EN: Output path

    # ZH: 時間戳記 | EN: Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
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
    description = Column(Text)                                                # ZH: 描述 | EN: Description
    framework = Column(String)                                                # ZH: 框架 | EN: Framework
    storage_path = Column(String, nullable=False)                             # ZH: 儲存路徑 | EN: Storage path
    size_bytes = Column(Integer)                                              # ZH: 檔案大小 | EN: File size
    uploaded_by = Column(String, nullable=False)                              # ZH: 上傳者 | EN: Uploader
    is_public = Column(Integer, default=0)                                    # ZH: 公開旗標 | EN: Public flag
    created_at = Column(DateTime, default=datetime.utcnow)


# ==============================================================================
# ZH: 表 5: ChatHistory - 聊天記錄
# EN: Table 5: ChatHistory - Chat conversation history
# ==============================================================================
class ChatHistory(Base):
    __tablename__ = "chat_history"

    id = Column(String, primary_key=True, default=generate_uuid)
    user_id = Column(String, index=True, nullable=False)
    session_id = Column(String, index=True, nullable=False)                   # ZH: 對話工作階段 | EN: Chat session
    role = Column(String, nullable=False)                                     # ZH: 角色 | EN: Role (user/assistant)
    content = Column(Text, nullable=False)                                    # ZH: 訊息內容 | EN: Message content
    tokens_used = Column(Integer, default=0)                                  # ZH: Token 消耗 | EN: Tokens used
    created_at = Column(DateTime, default=datetime.utcnow)


# ==============================================================================
# ZH: 表 6: SystemConfig - 系統設定
# EN: Table 6: SystemConfig - System configuration (Key-Value)
# ==============================================================================
class SystemConfig(Base):
    __tablename__ = "system_config"

    key = Column(String, primary_key=True)                                    # ZH: 設定鍵 | EN: Config key
    value = Column(String, nullable=False)                                    # ZH: 設定值 | EN: Config value
    description = Column(Text)                                                # ZH: 說明 | EN: Description
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
