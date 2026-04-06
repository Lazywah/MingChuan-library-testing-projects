-- ==============================================================================
-- ZH: AI 訓練平台 - SQLite 資料庫結構定義
-- EN: AI Training Platform - SQLite Database Schema Definition
-- ZH: 此檔案定義所有資料表、索引及預設值
-- EN: This file defines all tables, indexes, and default values
-- ==============================================================================

-- ZH: 啟用 WAL 模式 (提升並發讀寫效能) | EN: Enable WAL mode (better concurrency)
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

-- ==============================================================================
-- ZH: 表 1: users - 使用者認證與管理
-- EN: Table 1: users - User authentication and management
-- ZH: 用途：儲存所有使用者帳號資訊，支援學生/教師/管理員角色
-- EN: Purpose: Store all user account info, supports student/teacher/admin roles
-- ==============================================================================
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,                    -- ZH: UUID 主鍵 | EN: UUID primary key
    username TEXT UNIQUE NOT NULL,          -- ZH: 使用者名稱 (唯一) | EN: Username (unique)
    email TEXT UNIQUE NOT NULL,             -- ZH: 電子郵件 (唯一) | EN: Email (unique)
    hashed_password TEXT NOT NULL,          -- ZH: 雜湊密碼 | EN: Hashed password
    role TEXT NOT NULL DEFAULT 'student',   -- ZH: 角色 (student/teacher/admin) | EN: Role
    is_active INTEGER DEFAULT 1,           -- ZH: 是否啟用 (1=是, 0=否) | EN: Active status
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);

-- ==============================================================================
-- ZH: 表 2: token_usage - Token 用量追蹤
-- EN: Table 2: token_usage - Token usage tracking
-- ZH: 用途：追蹤每位使用者的 LLM Token 消耗量與月度配額
-- EN: Purpose: Track per-user LLM token consumption and monthly quota
-- ==============================================================================
CREATE TABLE IF NOT EXISTS token_usage (
    id TEXT PRIMARY KEY,                    -- ZH: UUID 主鍵 | EN: UUID primary key
    user_id TEXT NOT NULL,                  -- ZH: 關聯使用者 ID | EN: Associated user ID
    tokens_used INTEGER DEFAULT 0,          -- ZH: 已使用 Token 數 | EN: Tokens consumed
    tokens_limit INTEGER DEFAULT 5000000,   -- ZH: 月度上限 (預設 5M) | EN: Monthly limit
    reset_date DATETIME NOT NULL,           -- ZH: 下次重置日期 | EN: Next reset date
    last_updated DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_token_usage_user_id ON token_usage(user_id);

-- ==============================================================================
-- ZH: 表 3: training_jobs - 訓練任務佇列與狀態追蹤
-- EN: Table 3: training_jobs - Training job queue and status tracking
-- ZH: 用途：記錄所有訓練任務的完整生命週期
-- EN: Purpose: Record complete lifecycle of all training jobs
-- ZH: 狀態流轉：pending → queued → running → completed/failed/cancelled
-- EN: Status flow: pending → queued → running → completed/failed/cancelled
-- ==============================================================================
CREATE TABLE IF NOT EXISTS training_jobs (
    id TEXT PRIMARY KEY,                    -- ZH: UUID 主鍵 | EN: UUID primary key
    user_id TEXT NOT NULL,                  -- ZH: 提交者 ID | EN: Submitter user ID
    job_name TEXT NOT NULL,                 -- ZH: 任務名稱 | EN: Job display name
    model_name TEXT NOT NULL,               -- ZH: 模型名稱 | EN: Model name to train
    status TEXT DEFAULT 'pending',          -- ZH: 任務狀態 | EN: Job status
    gpu_required INTEGER DEFAULT 1,         -- ZH: 需要的 GPU 數量 | EN: Required GPU count
    priority INTEGER DEFAULT 0,             -- ZH: 優先級 (越大越優先) | EN: Priority (higher = urgent)

    -- ZH: 訓練配置 (JSON 字串) | EN: Training config (JSON string)
    config TEXT,                            -- {"epochs": 10, "batch_size": 32, ...}

    -- ZH: 執行細節 | EN: Execution details
    gpu_server TEXT,                        -- ZH: 分配的伺服器 | EN: Assigned server
    gpu_id INTEGER,                         -- ZH: 分配的 GPU ID | EN: Assigned GPU ID
    script_path TEXT,                       -- ZH: 訓練腳本路徑 | EN: Training script path
    dataset_path TEXT,                      -- ZH: 資料集路徑 | EN: Dataset path

    -- ZH: 進度追蹤 | EN: Progress tracking
    progress REAL DEFAULT 0.0,              -- ZH: 完成百分比 (0-100) | EN: Completion %
    logs TEXT,                              -- ZH: 執行日誌 | EN: Execution logs
    error_message TEXT,                     -- ZH: 錯誤訊息 | EN: Error message

    -- ZH: 輸出結果 | EN: Output result
    output_path TEXT,                       -- ZH: 訓練產出路徑 | EN: Trained model path

    -- ZH: 時間戳記 | EN: Timestamps
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    started_at DATETIME,
    completed_at DATETIME,

    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_jobs_user_id ON training_jobs(user_id);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON training_jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_created_at ON training_jobs(created_at);
-- ZH: 排程用複合索引 (按狀態+優先級+時間排序) | EN: Composite index for queue scheduling
CREATE INDEX IF NOT EXISTS idx_jobs_queue ON training_jobs(status, priority DESC, created_at);

-- ==============================================================================
-- ZH: 表 4: models - 模型註冊表
-- EN: Table 4: models - Model registry
-- ZH: 用途：記錄已上傳或訓練產出的模型資訊
-- EN: Purpose: Record uploaded or training-output model metadata
-- ==============================================================================
CREATE TABLE IF NOT EXISTS models (
    id TEXT PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,              -- ZH: 模型名稱 | EN: Model name
    description TEXT,                       -- ZH: 模型描述 | EN: Model description
    framework TEXT,                         -- ZH: 框架 (pytorch/tensorflow/onnx) | EN: Framework
    storage_path TEXT NOT NULL,             -- ZH: 儲存路徑 | EN: Storage path
    size_bytes INTEGER,                     -- ZH: 檔案大小 (bytes) | EN: File size
    uploaded_by TEXT NOT NULL,              -- ZH: 上傳者 ID | EN: Uploader user ID
    is_public INTEGER DEFAULT 0,           -- ZH: 是否公開 (0=私有) | EN: Public flag
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (uploaded_by) REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS idx_models_name ON models(name);
CREATE INDEX IF NOT EXISTS idx_models_uploaded_by ON models(uploaded_by);

-- ==============================================================================
-- ZH: 表 5: chat_history - 聊天記錄
-- EN: Table 5: chat_history - Chat conversation history
-- ZH: 用途：儲存使用者與 LLM 的對話紀錄 (供 Open WebUI 整合)
-- EN: Purpose: Store user-LLM conversations (for Open WebUI integration)
-- ==============================================================================
CREATE TABLE IF NOT EXISTS chat_history (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    session_id TEXT NOT NULL,               -- ZH: 對話工作階段 ID | EN: Chat session ID
    role TEXT NOT NULL,                     -- ZH: 角色 (user/assistant) | EN: Role
    content TEXT NOT NULL,                  -- ZH: 訊息內容 | EN: Message content
    tokens_used INTEGER DEFAULT 0,          -- ZH: 此訊息消耗的 Token 數 | EN: Tokens for this msg
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_chat_history_user_id ON chat_history(user_id);
CREATE INDEX IF NOT EXISTS idx_chat_history_session_id ON chat_history(session_id);

-- ==============================================================================
-- ZH: 表 6: system_config - 系統設定 (Key-Value)
-- EN: Table 6: system_config - System configuration (Key-Value store)
-- ZH: 用途：儲存全域系統設定，所有服務共用
-- EN: Purpose: Store global system settings, shared by all services
-- ==============================================================================
CREATE TABLE IF NOT EXISTS system_config (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    description TEXT,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- ZH: 插入預設系統設定 | EN: Insert default system configurations
INSERT OR IGNORE INTO system_config (key, value, description) VALUES
('max_concurrent_jobs', '4', 'ZH: 最大同時訓練任務數 (=GPU 總數) | EN: Max concurrent training jobs'),
('default_token_limit', '5000000', 'ZH: 每月預設 Token 上限 | EN: Default monthly token limit'),
('token_reset_day', '1', 'ZH: 每月重置日 | EN: Day of month to reset token counts'),
('gpu_server_1_host', '192.168.1.100', 'ZH: GPU 伺服器 1 IP | EN: GPU Server 1 IP address'),
('gpu_server_2_host', '192.168.1.101', 'ZH: GPU 伺服器 2 IP | EN: GPU Server 2 IP address');
