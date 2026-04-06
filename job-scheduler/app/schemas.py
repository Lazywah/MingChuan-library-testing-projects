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

from pydantic import BaseModel, EmailStr
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


class UserResponse(BaseModel):
    """ZH: 使用者資訊回應 (不含密碼) | EN: User info response (no password)"""
    id: str
    username: str
    email: str
    role: str
    is_active: int
    created_at: datetime

    class Config:
        from_attributes = True  # ZH: 允許從 ORM 物件轉換 | EN: Allow conversion from ORM objects


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
    """ZH: Token 用量遞增請求 | EN: Token usage increment request"""
    tokens: int                                      # ZH: 要增加的 Token 數 | EN: Tokens to add


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
    script_path: Optional[str] = None                # ZH: 訓練腳本路徑 | EN: Training script path
    dataset_path: Optional[str] = None               # ZH: 資料集路徑 | EN: Dataset path
    priority: Optional[int] = 0                      # ZH: 優先級 (越大越優先) | EN: Priority


class JobResponse(BaseModel):
    """ZH: 任務建立回應 | EN: Job creation response"""
    job_id: str
    status: str
    queue_position: Optional[int] = None             # ZH: 佇列位置 | EN: Queue position
    estimated_start_time: Optional[str] = None       # ZH: 預估開始時間 | EN: Estimated start

    class Config:
        from_attributes = True


class JobStatusResponse(BaseModel):
    """ZH: 任務狀態查詢回應 | EN: Job status query response"""
    job_id: str
    job_name: str
    status: str                                      # ZH: pending/queued/running/completed/failed/cancelled
    progress: float                                  # ZH: 完成百分比 (0-100) | EN: Completion %
    gpu_server: Optional[str] = None
    gpu_id: Optional[int] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    output_path: Optional[str] = None
    logs: Optional[str] = None

    class Config:
        from_attributes = True


class JobListResponse(BaseModel):
    """ZH: 任務列表回應 (含分頁) | EN: Job list response (with pagination)"""
    total: int                                       # ZH: 總筆數 | EN: Total count
    jobs: List[JobStatusResponse]                    # ZH: 任務清單 | EN: Job list


class JobCancelResponse(BaseModel):
    """ZH: 任務取消回應 | EN: Job cancel response"""
    job_id: str
    status: str                                      # ZH: 取消後狀態 | EN: Status after cancel
