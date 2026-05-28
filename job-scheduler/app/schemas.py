"""
==============================================================================
Module 4: Pydantic 資料驗證 (Request/Response Schemas)
==============================================================================
ZH: 用途：定義所有 API 請求與回應的資料結構與驗證規則
EN: Purpose: Define data structures and validation rules for all API req/res

ZH: 流程：
    Client JSON → Pydantic Schema 驗證 → 型別安全的 Python 物件
    Python 物件 → Pydantic Schema 序列化 → JSON 回應
EN: Flow:
    Client JSON → Pydantic Schema validation → type-safe Python object
    Python object → Pydantic Schema serialization → JSON response

ZH: 模組化設計：
    - 新增 API 時，只需在此檔案新增對應的 Schema Class
    - Schema 與 ORM Model 分離，API 回應不會洩漏內部欄位 (如密碼)
    - 可獨立修改驗證規則，不影響資料庫結構
EN: Modular design:
    - Adding APIs only requires new Schema Classes in this file
    - Schemas are separated from ORM Models, API responses won't leak internals
    - Validation rules can be modified independently of DB schema
==============================================================================
"""

from pydantic import BaseModel, EmailStr, Field, ConfigDict, field_validator
from datetime import datetime
from typing import Optional, Dict, Any, List


# ==============================================================================
# ZH: 認證相關 Schema | EN: Authentication Schemas
# ==============================================================================

class UserCreate(BaseModel):
    """ZH: 使用者註冊請求 | EN: User registration request"""
    username: str                                    # ZH: 使用者名稱 | EN: Username
    email: EmailStr                                  # ZH: 電子郵件 (自動驗證格式) | EN: Email (auto-validated)
    password: str                                    # ZH: 密碼 (明文，後端會雜湊) | EN: Password (plaintext, hashed by backend)
    role: Optional[str] = "student"                  # ZH: 角色 (預設 student) | EN: Role (default: student)
    department: Optional[str] = None                 # ZH: 學系資訊 | EN: Department

    # C-4: ZH: 防止公開註冊自行提升為 admin/teacher，只允許 student
    # EN: Block self-elevation to admin/teacher via public registration — student only
    @field_validator("role")
    @classmethod
    def role_must_be_student(cls, v: Optional[str]) -> str:
        if v not in (None, "student"):
            raise ValueError(
                "ZH: 公開註冊只允許 student 角色，teacher/admin 由管理員配發 | "
                "EN: Public registration only allows role=student; teacher/admin are provisioned by admins"
            )
        return v or "student"


class UserUpdate(BaseModel):
    """ZH: 使用者更新個人資料請求 | EN: User profile update request"""
    email: Optional[EmailStr] = None
    password: Optional[str] = None
    tutorial_dismissed: Optional[int] = None
    department: Optional[str] = None


class AdminUserUpdate(BaseModel):
    """ZH: 管理員更新使用者請求 | EN: Admin user update request"""
    email: Optional[EmailStr] = None
    password: Optional[str] = None                   # ZH: 留空則不變更 | EN: Empty = no change
    role: Optional[str] = None                       # ZH: student/teacher/admin
    is_active: Optional[int] = None                  # ZH: 0=停用 1=啟用 | EN: 0=disabled 1=enabled
    tokens_limit: Optional[int] = None               # ZH: Token 月度上限 | EN: Monthly token limit
    department: Optional[str] = None                 # ZH: 學系資訊 | EN: Department


class AdminProvisionUser(BaseModel):
    """ZH: 管理員初始化帳號請求 | EN: Admin provision user request"""
    username: str                                    # ZH: 使用者名稱 | EN: Username
    email: EmailStr                                  # ZH: 電子郵件 | EN: Email
    role: Optional[str] = "student"                  # ZH: 角色 | EN: Role
    password: Optional[str] = None                   # ZH: 自訂密碼，若無則自動產生 | EN: Custom password, if empty auto-generate
    department: Optional[str] = None                 # ZH: 學系資訊 | EN: Department

class AdminDeleteUser(BaseModel):
    """ZH: 管理員刪除使用者請求 | EN: Admin delete user request"""
    admin_password: str                              # ZH: 管理員密碼驗證 | EN: Admin password validation

class AdminVerify(BaseModel):
    """ZH: 管理員權限驗證請求 | EN: Admin privilege verification request"""
    admin_password: str                              # ZH: 管理員密碼驗證 | EN: Admin password validation

class AdminJobPriority(BaseModel):
    """ZH: 管理員修改任務優先級請求 | EN: Admin update job priority request"""
    priority: int = Field(..., ge=0, le=5)           # ZH: 新優先級 (0-5) | EN: New priority (0-5)

class AdminModelCreate(BaseModel):
    """ZH: 管理員新增模型請求 | EN: Admin create model request"""
    name: str                                        # ZH: 模型名稱 | EN: Model name
    model_type: str = "local"                         # ZH: 模型類型 (api/local) | EN: Model type
    description: Optional[str] = None                # ZH: 描述 | EN: Description
    framework: Optional[str] = None                  # ZH: 框架 | EN: Framework (PyTorch/TF/etc.)
    storage_path: Optional[str] = ""                  # ZH: 儲存路徑 | EN: Storage path
    is_public: Optional[int] = 0                     # ZH: 公開旗標 | EN: Public flag
    # ZH: API 模型專用 | EN: API model fields
    api_provider: Optional[str] = None               # ZH: 供應商 (anthropic/openai/google/ollama) | EN: Provider
    api_endpoint: Optional[str] = None               # ZH: API 端點 | EN: Endpoint URL
    api_model_id: Optional[str] = None               # ZH: 上游模型 ID | EN: Upstream model ID

class AdminModelUpdate(BaseModel):
    """ZH: 管理員更新模型請求 | EN: Admin update model request"""
    name: Optional[str] = None
    model_type: Optional[str] = None
    description: Optional[str] = None
    framework: Optional[str] = None
    storage_path: Optional[str] = None
    is_public: Optional[int] = None
    api_provider: Optional[str] = None
    api_endpoint: Optional[str] = None
    api_model_id: Optional[str] = None

class AuthForgotPassword(BaseModel):
    """ZH: 忘記密碼請求 | EN: Forgot password request"""
    username: str
    email: EmailStr

class UserResponse(BaseModel):
    """ZH: 使用者資訊回應 (不含密碼) | EN: User info response (no password)"""
    model_config = ConfigDict(from_attributes=True)

    id: str
    username: str
    email: str
    role: str
    is_active: int
    online_status: Optional[int] = 0
    tutorial_dismissed: int = 0
    department: Optional[str] = None
    login_count: int = 0
    lifetime_tokens_used: int = 0
    last_login_ip: Optional[str] = None
    last_login_time: Optional[datetime] = None
    # v2.1 SSO 整合 — 給前端判斷密碼變更 UI 該顯示本機表單還是 IdP 連結
    # v2.1 SSO integration — for frontend to decide password-change UI mode
    auth_source: str = "local"        # local / sso_mock / sso_cas / sso_oidc
    external_id: Optional[str] = None # OIDC oid; None for local users
    created_at: datetime


class Token(BaseModel):
    """ZH: JWT Token 回應 | EN: JWT Token response"""
    access_token: str                                # ZH: JWT Token 字串 | EN: JWT Token string
    token_type: str                                  # ZH: Token 類型 (固定 "bearer") | EN: Token type


class TokenData(BaseModel):
    """ZH: JWT 解碼後的資料 | EN: Decoded JWT data"""
    username: Optional[str] = None
    role: Optional[str] = None


# ==============================================================================
# ZH: Token 用量 Schema | EN: Token Usage Schemas
# ==============================================================================

class TokenUsageResponse(BaseModel):
    """ZH: Token 用量查詢回應 | EN: Token usage query response"""
    user_id: str
    tokens_used: int                                 # ZH: 已使用量 | EN: Tokens consumed
    tokens_limit: int                                # ZH: 月度上限 | EN: Monthly limit
    usage_percentage: float                          # ZH: 使用百分比 | EN: Usage percentage
    reset_date: datetime                             # ZH: 下次重置日 | EN: Next reset date


class TokenIncrementRequest(BaseModel):
    """
    ZH: Token 用量遞增請求 | EN: Token usage increment request

    ZH: C2 修復：必須指定 user_id，否則先前會錯扣 admin 自己（呼叫者）
    EN: C2 fix: must specify user_id; previously deducted from the caller (admin) by mistake
    """
    user_id: str                                     # ZH: 目標使用者 UUID | EN: Target user UUID
    tokens: int                                      # ZH: 要增加的 Token 數 | EN: Tokens to add


class BatchTokenUpdate(BaseModel):
    """
    ZH: 管理員批量更新 Token 請求 | EN: Admin batch token update request

    ZH: action 支援以下操作：
        - reset_usage：將指定使用者的 tokens_used 歸零（value 忽略）
        - set_limit：將指定使用者的 tokens_limit 設為 value
    EN: Supported actions:
        - reset_usage: Reset tokens_used to 0 for target users (value ignored)
        - set_limit: Set tokens_limit to value for target users
    """
    user_ids: List[str]                              # ZH: 目標使用者 UUID 清單 | EN: Target user UUID list
    action: str                                      # ZH: 操作類型 (reset_usage / set_limit) | EN: Action type
    value: Optional[int] = 0                         # ZH: set_limit 時使用的新額度 | EN: New limit for set_limit action


# ==============================================================================
# ZH: 訓練任務 Schema | EN: Training Job Schemas
# ==============================================================================

class JobCreate(BaseModel):
    """
    ZH: 提交訓練任務請求
    EN: Submit training job request
    """
    job_name: str                                    # ZH: 任務名稱 | EN: Job display name
    model_name: str                                  # ZH: 模型名稱 | EN: Model to train
    gpu_required: Optional[int] = 1                  # ZH: 需要的 GPU 數 (1 或 2) | EN: GPUs needed
    config: Optional[Dict[str, Any]] = None          # ZH: 訓練配置 | EN: Training config
    
    # ZH: 嚴格校驗路徑參數，防禦 Command Injection | EN: Strict path validation to prevent ACE
    script_path: Optional[str] = Field(
        default=None, 
        pattern=r"^[a-zA-Z0-9_\-\.\/\\]+$",
        description="Only alphanumeric, dash, underscore, dot and slashes allowed"
    )
    dataset_path: Optional[str] = Field(
        default=None, 
        pattern=r"^[a-zA-Z0-9_\-\.\/\\]+$",
        description="Only alphanumeric, dash, underscore, dot and slashes allowed"
    )
    
    priority: Optional[int] = 0                      # ZH: 優先級 (越大越優先) | EN: Priority

    # ZH: Notebook 執行欄位 | EN: Notebook execution fields
    docker_image:   Optional[str]       = None        # ZH: 覆寫預設 Docker Image，空則使用 DEFAULT_IMAGE | EN: Override default image
    inline_code:    Optional[str]       = None        # ZH: 前端 compileNotebook() 產出的 shell script | EN: Compiled shell script from notebook
    entry_args:     Optional[List[str]] = None        # ZH: 容器入口指令陣列（非 Python 工具用）| EN: Container entry command array
    preferred_node: Optional[str]       = None        # ZH: 偏好的 GPU Worker 節點 ID，"auto" 或空值代表自動 | EN: Preferred worker node, "auto"/null = auto


class JobResponse(BaseModel):
    """ZH: 任務建立回應 | EN: Job creation response"""
    model_config = ConfigDict(from_attributes=True)

    job_id: str
    status: str
    queue_position: Optional[int] = None
    estimated_start_time: Optional[str] = None


class JobStatusResponse(BaseModel):
    """ZH: 任務狀態查詢回應 | EN: Job status query response"""
    model_config = ConfigDict(from_attributes=True)

    job_id: str
    job_name: str
    status: str
    progress: float
    gpu_server: Optional[str] = None
    gpu_id: Optional[int] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    output_path: Optional[str] = None
    logs: Optional[str] = None


class JobListItem(BaseModel):
    """ZH: 任務列表項目 (不含大型 logs 欄位) | EN: Job list item (excludes large logs field)"""
    model_config = ConfigDict(from_attributes=True)

    job_id: str
    job_name: str
    status: str
    progress: float
    priority: Optional[int] = 0
    model_name: Optional[str] = None
    user_id: Optional[str] = None
    gpu_server: Optional[str] = None
    gpu_id: Optional[int] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    error_message: Optional[str] = None
    output_path: Optional[str] = None


class JobListResponse(BaseModel):
    """ZH: 任務列表回應 (含分頁) | EN: Job list response (with pagination)"""
    total: int                                       # ZH: 總筆數 | EN: Total count
    jobs: List[JobListItem]                          # ZH: 任務清單 (不含 logs) | EN: Job list (no logs)


class JobCancelResponse(BaseModel):
    """ZH: 任務取消回應 | EN: Job cancel response"""
    job_id: str
    status: str                                      # ZH: 取消後狀態 | EN: Status after cancel


# ==============================================================================
# ZH: 聊天相關 Schema | EN: Chat Schemas
# ==============================================================================

class ChatMessage(BaseModel):
    """ZH: 單筆對話訊息 | EN: Single chat message"""
    role: str                                        # ZH: user / assistant
    content: str                                     # ZH: 訊息內容 | EN: Message content


class ChatRequest(BaseModel):
    """ZH: 聊天請求 | EN: Chat request"""
    model_id: str                                    # ZH: 模型識別碼 (gemini-1.5, llama3)
    messages: List[ChatMessage]                      # ZH: 對話歷史 | EN: Message history
    stream: Optional[bool] = True                    # ZH: 是否串流 | EN: Request streaming
    tool_type: Optional[str] = "chat"                # ZH: 工具類型 | EN: Tool type
    session_id: Optional[str] = None                 # ZH: 對話 session ID | EN: Chat session ID


class ChatHistoryResponse(BaseModel):
    """ZH: 歷史對話紀錄回應 | EN: Chat history response"""
    model_config = ConfigDict(from_attributes=True)

    session_id: str
    messages: List[ChatMessage]


# ==============================================================================
# ZH: 管理員回應 Schema | EN: Admin Response Schemas
# ==============================================================================

class AdminUserListItem(BaseModel):
    """ZH: 管理員使用者列表項目（含 Token 狀態）| EN: Admin user list item with token status"""
    model_config = ConfigDict(from_attributes=True)

    id: str
    username: str
    email: str
    role: str
    is_active: int
    online_status: Optional[int] = 0
    last_login_time: Optional[datetime] = None
    last_login_ip: Optional[str] = None
    department: Optional[str] = None
    created_at: Optional[datetime] = None
    tokens_used: int = 0
    tokens_limit: int = 0
    # v2.1: 給 admin UI 的 3-tab 分頁 (local / sso_oidc / sso_mock) 用
    auth_source: str = "local"


class AdminJobListItem(BaseModel):
    """ZH: 管理員任務列表項目 | EN: Admin job list item"""
    model_config = ConfigDict(from_attributes=True)

    job_id: str
    job_name: str
    model_name: Optional[str] = None
    user_id: Optional[str] = None
    status: str
    priority: Optional[int] = 0
    progress: float = 0.0
    gpu_server: Optional[str] = None
    created_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None


# ==============================================================================
# ZH: Worker 心跳 Schema | EN: Worker Heartbeat Schemas
# ==============================================================================

class WorkerHeartbeatPayload(BaseModel):
    """ZH: Worker 心跳上報請求 | EN: Worker heartbeat report request"""
    node_id: str
    available_gpus: List[str]
    gpu_utilization: Optional[float] = 0.0  # ZH: GPU 使用率 % | EN: GPU utilization %


# ZH: Notebook Schema 已於 Phase E 移除 — 被 v2.0 Lab schemas 取代
# EN: Notebook schemas removed in Phase E — superseded by v2.0 Lab schemas


# ==============================================================================
# ZH: Worker 節點列表 Schema | EN: Worker Node List Schema
# ==============================================================================

class WorkerNodeInfo(BaseModel):
    """ZH: 單一 Worker 節點資訊 | EN: Single worker node info"""
    model_config = ConfigDict(from_attributes=True)

    node_id:        str
    available_gpus: List[str]
    gpu_utilization: float = 0.0
    last_seen:      Optional[datetime] = None
    is_online:      int = 1


class WorkerNodeListResponse(BaseModel):
    """ZH: 線上 Worker 節點列表回應 | EN: Online worker node list response"""
    nodes: List[WorkerNodeInfo]


# ==============================================================================
# ZH: 公告 Schema (v2.2 新增) | EN: Announcement Schemas (v2.2)
# ==============================================================================

class AnnouncementCreate(BaseModel):
    """ZH: admin 建立 / 編輯公告的請求 | EN: Admin create/edit announcement"""
    title: str
    body: str
    is_pinned: int = 0          # 0 / 1
    is_visible: int = 1         # 0 / 1


class AnnouncementResponse(BaseModel):
    """ZH: 公告回應 | EN: Announcement response"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    body: str
    posted_by: Optional[str] = None
    posted_at: datetime
    updated_at: Optional[datetime] = None
    is_pinned: int = 0
    is_visible: int = 1
