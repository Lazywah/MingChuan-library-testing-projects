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

from pydantic import (BaseModel, EmailStr, Field, ConfigDict, field_validator,
                      field_serializer, PlainSerializer)
from typing_extensions import Annotated
from datetime import datetime, timezone, date, time, timedelta
# ZH: 台灣時區只定義一次。gpu_schedule 只依賴標準庫，沒有循環匯入風險。
from .gpu_schedule import TZ_TAIPEI
import json
from typing import ClassVar, Optional, Dict, Any, List


# ==============================================================================
# ZH: 時間欄位的型別 | EN: The datetime field type
# ==============================================================================
# ZH: ⚠ 時間欄位存的是 **UTC**（models 用 datetime.now(timezone.utc)），
#     但 SQLite 取回來是 naive datetime，序列化出去長這樣：
#         "2026-08-20T01:42:38.152605"          ← 沒有 Z、沒有 +08:00
#     瀏覽器的 `new Date(...)` 會把沒有時區的字串當成**本地時間**，
#     於是 +08:00 的使用者看到的時間**早了 8 小時**。
#     不會報錯、不會壞版面，只是每個時間都是錯的 —— 實測抓到（送出 09:42 顯示 01:42）。
#
# ZH: 為什麼做成**型別**而不是每個 schema 各加一個 field_serializer：
#     那樣就是第十份、第十一份同樣的程式碼，而總有一份會漏——
#     機械稽核當初正是抓出九個漏掉的。型別自己帶行為，新增欄位不會忘。
#     `scripts/check_naive_datetime.py` 另外守著「有人又用了裸的 datetime」。
#
# ZH: 不在這裡轉成台北時間：**顯示時區是前端的事**（tz.js 釘死 Asia/Taipei）。
#     後端只負責把「這是 UTC」講清楚，兩邊各做各的，不要互相猜。
# EN: Naive UTC datetimes serialize without an offset; browsers then read them as
#     local time (8h early for +08:00). The type carries the fix so new fields
#     cannot forget it. Converting to Taipei is the frontend's job (tz.js).
def _utc_iso(v: Optional[datetime]) -> Optional[str]:
    """@node job-scheduler/app/schemas.py::_utc_iso"""
    if v is None:
        return None
    return (v.replace(tzinfo=timezone.utc) if v.tzinfo is None else v).isoformat()


UtcDatetime = Annotated[datetime, PlainSerializer(_utc_iso, return_type=Optional[str])]


# ==============================================================================
# ZH: 認證相關 Schema | EN: Authentication Schemas
# ==============================================================================

class UserCreate(BaseModel):
    """ZH: 使用者註冊請求 | EN: User registration request

    @node job-scheduler/app/schemas.py::UserCreate
    """
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
        """@node job-scheduler/app/schemas.py::UserCreate.role_must_be_student"""
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
    # ZH: 🔴 v3.8 `department` 從這裡**移除**。它原本讓使用者透過 PUT /auth/me
    #     隨意改成任何自由文字 —— 那既繞過了組織對照表的驗證（打錯字的系名
    #     會長成一個新的統計類別）,也讓「單次解鎖」形同虛設。
    #     改組織欄位一律走 POST /system/onboarding,那裡會驗值也會檢查解鎖。


class AdminUserUpdate(BaseModel):
    """ZH: 管理員更新使用者請求 | EN: Admin user update request"""
    email: Optional[EmailStr] = None
    password: Optional[str] = None                   # ZH: 留空則不變更 | EN: Empty = no change
    role: Optional[str] = None                       # ZH: student/teacher/staff/guest（身分）
    # ZH: v3.8 管理權限。🔴 **刻意只在這份 schema 出現** ——
    #     使用者端的 UserUpdate 沒有這個欄位,所以 PUT /auth/me 根本表達不出它。
    #     要加使用者可改的欄位時務必維持這個形狀:兩份 schema、逐欄位明寫,
    #     不要改成通用的 setattr 迴圈（那等於開提權後門）。
    is_admin: Optional[int] = None                   # ZH: 0/1，與 role 無關
    is_active: Optional[int] = None                  # ZH: 0=停用 1=啟用 | EN: 0=disabled 1=enabled
    tokens_limit: Optional[int] = None               # ZH: Token 月度上限 | EN: Monthly token limit
    department: Optional[str] = None                 # ZH: 學系資訊 | EN: Department


# ==============================================================================
# ZH: 臨時帳號的到期日
# ------------------------------------------------------------------------------
# ZH: 契約是**台灣時間的一個日曆日**（`expires_on`），不是天數。
#     擁有者裁定 2026-08-24：管理者是在日曆上挑一天；要延期就挑一個更後面的日子，
#     所以「建立」與「延長」用同一種輸入。
#
# ZH: 這推翻了本檔原本「再延 N 天」的設計。舊理由是「管理者腦中的動作是
#     『再給他一個禮拜』」與「直接設日期時 None 會同時代表『不改』與『改成永久』」。
#     後者在新契約下不成立 —— `expires_on` 是**必填**，None 根本不會出現。
#
# ZH: 🔴 「到 9/3」的意思是**那一天結束**（台灣時間 23:59:59），不是那天零點。
#     選了 9/3 卻在 9/3 當天就登不進來，會被當成 bug 回報。
#
# ZH: 存進 DB 的仍然是 UTC。轉換**只有這一個地方做** —— 兩支端點共用同一個函式，
#     不要各自算（各自算的兩份遲早會差一天，而那種差異沒有人看得出來）。
# ==============================================================================
TEMP_ACCOUNT_MAX_DAYS = 90


def tw_today() -> date:
    """ZH: 今天（台灣時間）。伺服器在哪個時區都得到同一個答案。

    @node job-scheduler/app/schemas.py::tw_today
    """
    return datetime.now(TZ_TAIPEI).date()


def expires_on_to_utc(d: date) -> datetime:
    """ZH: 台灣時間那一天的 23:59:59 → UTC 的 aware datetime。

    @node job-scheduler/app/schemas.py::expires_on_to_utc
    """
    return datetime.combine(d, time(23, 59, 59), tzinfo=TZ_TAIPEI).astimezone(timezone.utc)


def _check_expires_on(v: date) -> date:
    """ZH: 到期日必須在「今天」到「今天 +90 天」之間。

    ZH: 上限沿用原本 days 的 90 天 —— 再長就不叫臨時了，該走正式開帳號的流程。
    ZH: 下限是**今天**而不是明天：選今天＝「今天結束就失效」，那是合理的用法
        （臨時帳號常常就是當天用完）。

    @node job-scheduler/app/schemas.py::_check_expires_on
    """
    today = tw_today()
    if v < today:
        raise ValueError(
            "ZH: 到期日不能早於今天 | EN: expiry date cannot be in the past")
    if v > today + timedelta(days=TEMP_ACCOUNT_MAX_DAYS):
        raise ValueError(
            "ZH: 到期日最多只能設到 %d 天後 | "
            "EN: expiry date can be at most %d days out" % (TEMP_ACCOUNT_MAX_DAYS, TEMP_ACCOUNT_MAX_DAYS))
    return v


class AdminTempUserCreate(BaseModel):
    """ZH: 建立臨時帳號（校外人士、長官視察、例外用途）。

    ZH: 為什麼不沿用 `AdminProvisionUser`：那條路**強制要 email 而且會寄信**，
        而臨時帳號的典型對象沒有學校信箱。填一個假的進去會**真的寄出去然後退信**
        （這個專案已經因為類似的事寄出過約 35 封必退信件）。

    @node job-scheduler/app/schemas.py::AdminTempUserCreate
    """
    username: str
    purpose: str                                     # ZH: 為什麼開這個帳號 —— **必填**
    expires_on: date                                 # ZH: 台灣時間的到期「日」（當天結束才失效）
    role: Optional[str] = "student"
    department: Optional[str] = None
    email: Optional[EmailStr] = None                 # ZH: 有就填，沒有就留空（不寄信）

    @field_validator("purpose")
    @classmethod
    def purpose_required(cls, v: str) -> str:
        """ZH: 空白字串不算填了。

        ZH: 半年後在清單裡看到一個叫 guest3 的帳號，沒有用途就沒有人敢刪它，
            於是它會一直留著——那正是臨時帳號最後變成永久帳號的方式。

        @node job-scheduler/app/schemas.py::AdminTempUserCreate.purpose_required
        """
        if not (v or "").strip():
            raise ValueError("ZH: 請說明這個臨時帳號的用途 | EN: Purpose is required")
        return v.strip()

    @field_validator("expires_on")
    @classmethod
    def expires_on_in_range(cls, v: date) -> date:
        """@node job-scheduler/app/schemas.py::AdminTempUserCreate.expires_on_in_range"""
        return _check_expires_on(v)

    @property
    def expires_at_utc(self) -> datetime:
        """ZH: 給端點直接寫進 DB 的值。

        @node job-scheduler/app/schemas.py::AdminTempUserCreate.expires_at_utc
        """
        return expires_on_to_utc(self.expires_on)


class AdminExtendTempAccount(BaseModel):
    """ZH: 重新設定臨時帳號的到期日（**絕對日期**，不是再加幾天）。

    ZH: 它曾經是「再延 N 天」，理由是「管理者腦中的動作是再給他一個禮拜」。
        擁有者 2026-08-24 改成日曆：建立與延期用**同一種輸入**，
        延期就是在日曆上改成一個更後面的日子。

    ZH: 舊註解擔心的「`None` 同時代表不改與永久」在新契約下不成立：
        `expires_on` 是必填的，None 根本不會出現。

    @node job-scheduler/app/schemas.py::AdminExtendTempAccount
    """
    expires_on: date

    @field_validator("expires_on")
    @classmethod
    def expires_on_in_range(cls, v: date) -> date:
        """@node job-scheduler/app/schemas.py::AdminExtendTempAccount.expires_on_in_range"""
        return _check_expires_on(v)

    @property
    def expires_at_utc(self) -> datetime:
        """@node job-scheduler/app/schemas.py::AdminExtendTempAccount.expires_at_utc"""
        return expires_on_to_utc(self.expires_on)


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
    tool_types: Optional[str] = "chat"               # ZH: 適用工具 CSV (chat,presentation) | EN: Applicable tools CSV
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
    tool_types: Optional[str] = None
    api_provider: Optional[str] = None
    api_endpoint: Optional[str] = None
    api_model_id: Optional[str] = None

class PublicModel(BaseModel):
    """ZH: 使用者端可見的模型 (依工具動態載入) | EN: User-facing model (loaded per tool)"""
    value: str                                       # ZH: 送給 chat 的 model_id | EN: model_id sent to chat
    label: str                                       # ZH: 顯示名稱 | EN: Display name
    model_type: Optional[str] = None
    api_provider: Optional[str] = None

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
    # ZH: v3.8 組織欄位。`campuses` 來自 user_campuses 關聯表,不是 users 的欄位 ——
    #     所以 /auth/me 會**明確填它**（ORM 模式帶不出關聯表的值,不填會永遠是空陣列）。
    unit: Optional[str] = None
    campuses: List[str] = []
    # ZH: v3.8 管理權限。這是**回應** schema —— 使用者看得到自己有沒有,但改不了。
    is_admin: int = 0
    onboarded_at: Optional[UtcDatetime] = None
    # ZH: v4.2 角色是怎麼來的（sso_email=依信箱自動判 / self_onboard=本人初次設定時選）。
    #     🔴 唯讀狀態回報 —— 前端靠它判斷「要不要在初次設定問身分」：
    #     職員與老師同網域（@mail.mcu.edu.tw），系統分不出來，
    #     擁有者裁定 2026-09-02：讓本人在首次登入時自己選。
    role_source: Optional[str] = None
    # ZH: v3.8 管理者開放的一次性修改。`None` = 鎖著。
    #     🔴 這是**唯讀的狀態回報** —— 使用者改不了它,寫入只有管理端那支端點。
    #     沒有這個欄位的話,前端無從得知「現在可以改了」,
    #     管理者開了也沒有任何地方能用（v3.8 開發中實際發生過）。
    profile_unlock: Optional[List[str]] = None
    login_count: int = 0
    lifetime_tokens_used: int = 0
    last_login_ip: Optional[str] = None
    last_login_time: Optional[UtcDatetime] = None
    # v2.1 SSO 整合 — 給前端判斷密碼變更 UI 該顯示本機表單還是 IdP 連結
    # v2.1 SSO integration — for frontend to decide password-change UI mode
    auth_source: str = "local"        # local / sso_mock / sso_cas / sso_oidc
    external_id: Optional[str] = None # OIDC oid; None for local users
    # ZH: v3.5 介面偏好。放在 /auth/me 一起回，前端本來就會呼叫它——**不必多一次往返**。
    ui_font_scale: int = 100
    ui_lang: str = "zh"
    ui_theme: str = "yellow"
    created_at: UtcDatetime


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
    reset_date: UtcDatetime                             # ZH: 下次重置日 | EN: Next reset date


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
    # ZH: v3.6 —— **這才是之後該用的欄位**。伺服器自己查所有權，
    #     路徑完全不經過客戶端。
    dataset_id: Optional[str] = None
    # ZH: 相容用法（v1 / v1.5 送的是這個）。⚠ 這是客戶端給的字串，
    #     伺服器必須自己驗它屬於送單的人——實測證實原本沒驗。
    dataset_path: Optional[str] = Field(
        default=None, 
        pattern=r"^[a-zA-Z0-9_\-\.\/\\]+$",
        description="Only alphanumeric, dash, underscore, dot and slashes allowed"
    )
    
    priority: Optional[int] = 0                      # ZH: 優先級 (越大越優先) | EN: Priority
    # ZH: v3.0 目標節點池：batch(高階 GPU) / interactive(本地 GPU)。只收白名單，其他一律當 batch。
    # EN: v3.0 target pool: batch(high-end) / interactive(local). Whitelisted; anything else → batch.
    pool_type: Optional[str] = "batch"

    # ZH: Notebook 執行欄位 | EN: Notebook execution fields
    docker_image:   Optional[str]       = None        # ZH: 覆寫預設 Docker Image，空則使用 DEFAULT_IMAGE | EN: Override default image
    inline_code:    Optional[str]       = None        # ZH: 前端 compileNotebook() 產出的 shell script | EN: Compiled shell script from notebook
    # ZH: v3.6 使用者自帶的訓練程式（單一 .py 的原始碼，不是檔名）。
    #     上限 256 KB —— 單一訓練腳本遠低於此；再大就不該用這條路。
    script_source:  Optional[str]       = Field(default=None, max_length=262144)
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
    started_at: Optional[UtcDatetime] = None
    completed_at: Optional[UtcDatetime] = None
    error_message: Optional[str] = None
    output_path: Optional[str] = None
    logs: Optional[str] = None
    # ZH: v3.6 訓練指標。DB 存的是 JSON **字串**，這裡出去必須是陣列——
    #     不轉的話前端拿到一坨字串，而 `JSON.parse` 該由誰做會變成兩邊各猜一次。
    metrics: Optional[List[Dict[str, Any]]] = None
    # ZH: v3.6 —— 這張單有沒有可下載的模型檔，以及多大。
    #     前端靠這個決定要不要顯示下載鈕；不要讓它自己去猜。
    has_model: bool = False
    model_bytes: Optional[int] = None

    @field_validator("metrics", mode="before")
    @classmethod
    def _parse_metrics(cls, v):
        """ZH: 字串 → 陣列。壞掉的 JSON 回 None（不是丟例外）——
           指標壞掉不該讓整個任務查詢 500，狀態與日誌還是要看得到。

        @node job-scheduler/app/schemas.py::JobStatusResponse._parse_metrics
        """
        if v is None or isinstance(v, list):
            return v
        if isinstance(v, str):
            try:
                parsed = json.loads(v)
            except (ValueError, TypeError):
                return None
            return parsed if isinstance(parsed, list) else None
        return None


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
    started_at: Optional[UtcDatetime] = None
    completed_at: Optional[UtcDatetime] = None
    created_at: Optional[UtcDatetime] = None
    error_message: Optional[str] = None
    output_path: Optional[str] = None
    # ZH: v3.6 有沒有可下載的模型（列表直接給下載鈕用）
    has_model: bool = False
    model_bytes: Optional[int] = None
    # ZH: v3.9 排隊位置（只有 pending 的任務會有值）。
    #   position/total —— 同池內的第幾個 / 共幾個
    #   wait_reason    —— 只給排第一個的：lab（別人的實驗室佔著卡）/
    #                     job（正在跑別的訓練）/ closed（時段外）/ no_node（沒機器在線）
    # ZH: ⚠ 位置是**估計值**，見 crud.queue_info 的說明。
    queue_position: Optional[int] = None
    queue_total: Optional[int] = None
    wait_reason: Optional[str] = None


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
    # ZH: v3.8 這個 role 怎麼來的 —— sso_email(自動判) / admin(管理者設) / None(不知道)
    role_source: Optional[str] = None
    is_admin: int = 0
    is_active: int
    online_status: Optional[int] = 0
    last_login_time: Optional[UtcDatetime] = None
    last_login_ip: Optional[str] = None
    department: Optional[str] = None
    # ZH: v3.9 學系的英文名（org_departments.name_en）。沒有對照或沒填就是 None，
    #     前端退回中文。
    # ZH: ⚠ **行政單位刻意沒有 unit_en**：英文名只有 53/97，做了會讓同一欄
    #     一半英文一半中文，比全中文更難讀。等補齊再開（擁有者裁定 2026-08-30）。
    department_en: Optional[str] = None
    created_at: Optional[UtcDatetime] = None
    tokens_used: int = 0
    tokens_limit: int = 0
    # v2.1: 給 admin UI 的 3-tab 分頁 (local / sso_oidc / sso_mock) 用
    auth_source: str = "local"

    # ZH: v3.7 臨時帳號 —— 管理端要看得出**這個帳號什麼時候會失效、為什麼存在**。
    #     沒有這兩個欄位的話，臨時帳號在清單裡與一般帳號長得一模一樣，
    #     那它就會被當成一般帳號留下來（臨時帳號變成永久帳號的標準路徑）。
    expires_at: Optional[UtcDatetime] = None
    temp_purpose: Optional[str] = None


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
    created_at: Optional[UtcDatetime] = None
    started_at: Optional[UtcDatetime] = None
    completed_at: Optional[UtcDatetime] = None
    error_message: Optional[str] = None


# ==============================================================================
# ZH: Worker 心跳 Schema | EN: Worker Heartbeat Schemas
# ==============================================================================

class WorkerHeartbeatPayload(BaseModel):
    """ZH: Worker 心跳上報請求 | EN: Worker heartbeat report request"""
    node_id: str
    available_gpus: List[str]
    gpu_utilization: Optional[float] = 0.0  # ZH: GPU 使用率 % | EN: GPU utilization %
    gpus_detail: Optional[List[Dict[str, Any]]] = None  # ZH: 每張 GPU 詳細 | EN: Per-GPU detail
    pool_type: Optional[str] = "batch"      # ZH: v3.0 此節點所屬池 batch/interactive | EN: node's pool
    # ZH: v3.6 —— 此節點是否與服務層同機（看得到 per-user 的 home_<uid> volume）。
    #     預設 False：舊版 worker 不送這欄位，於是被當成「不同機」——寧可不派工。
    shares_service_storage: bool = False


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
    last_seen:      Optional[UtcDatetime] = None
    is_online:      int = 1


class WorkerNodeListResponse(BaseModel):
    """ZH: 線上 Worker 節點列表回應 | EN: Online worker node list response"""
    nodes: List[WorkerNodeInfo]


# ==============================================================================
class LabSessionCreate(BaseModel):
    """ZH: 新增一份實驗室存檔 | EN: Create a Code Lab workspace

    ZH: 只收使用者看得懂的名字（可中文）。進容器名與網址的那個鍵由伺服器
        自己 slugify —— 讓客戶端決定那個鍵等於讓它決定容器叫什麼。
    """
    display_name: str = Field(min_length=1, max_length=60)


# ZH: 公告 Schema (v2.2 新增) | EN: Announcement Schemas (v2.2)
# ==============================================================================

class AnnouncementCreate(BaseModel):
    """ZH: admin 建立 / 編輯公告的請求 | EN: Admin create/edit announcement"""
    title: str
    body: str
    # ZH: 英文版可空 —— 空的時候使用者端退回中文（見 news.js 的 pick）。
    title_en: Optional[str] = None
    body_en: Optional[str] = None
    is_pinned: int = 0          # 0 / 1
    is_visible: int = 1         # 0 / 1


class AnnouncementFileOut(BaseModel):
    """ZH: 公告附件 | EN: Announcement attachment

    ZH: ⚠ **不回 stored_name。** 那是磁碟上的路徑片段，前端用不到，
        送出去只是多給一個猜檔案位置的線索。下載一律用 id。
    """
    model_config = ConfigDict(from_attributes=True)

    id: int
    filename: str
    size_bytes: int = 0
    content_type: Optional[str] = None


class AnnouncementResponse(BaseModel):
    """ZH: 公告回應 | EN: Announcement response"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    body: str
    title_en: Optional[str] = None
    body_en: Optional[str] = None
    posted_by: Optional[str] = None
    posted_at: UtcDatetime
    updated_at: Optional[UtcDatetime] = None
    is_pinned: int = 0
    is_visible: int = 1
    files: list[AnnouncementFileOut] = []


# ==============================================================================
# ZH: 外部 AI 分流 Schema (v2.5) | EN: External AI routing schemas (v2.5)
# ==============================================================================

class ExternalAiAccountCreate(BaseModel):
    """ZH: admin 建立對應 (以平台帳號名指定) | EN: Admin create mapping (by platform username)"""
    platform_username: str
    vendor_username: str
    status: Optional[str] = "active"        # active / disabled
    note: Optional[str] = None


class ExternalAiAccountUpdate(BaseModel):
    """ZH: admin 編輯對應 | EN: Admin update mapping"""
    vendor_username: Optional[str] = None
    status: Optional[str] = None
    note: Optional[str] = None


class ExternalAiAccountResponse(BaseModel):
    """ZH: 對應表列項 (含平台帳號名，由 join 帶出) | EN: Mapping row (platform_username via join)"""
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    platform_username: Optional[str] = None
    vendor_username: str
    status: str = "active"
    note: Optional[str] = None
    updated_at: Optional[UtcDatetime] = None


class ExternalAiMe(BaseModel):
    """ZH: 使用者端取得自己的外部 AI 導流資訊 | EN: User-facing external-AI redirect info"""
    url: str                                # ZH: 外部平台網址 (空=未啟用) | EN: vendor URL (empty=disabled)
    vendor_username: Optional[str] = None   # ZH: 指派帳號 (未開通為 None) | EN: assigned account (None if not provisioned)
    status: str                             # active / not_provisioned / disabled
    # v2.8 廠商 Token 餘額（以 email 對應 myai_accounts；無資料為 None）
    myai_points: Optional[int] = None       # ZH: AI 點數餘額 | EN: vendor token balance
    myai_expiry: Optional[str] = None       # ZH: 有效期間 | EN: expiry
    myai_status: Optional[str] = None       # ZH: 廠商端狀態 | EN: vendor account status
    # v2.8 共用機台換手：廠商登出網址（前端「結束使用」會開它殺掉 myai session）
    logout_url: Optional[str] = None        # ZH: 廠商登出 URL | EN: vendor logout URL


class ExternalAiUrl(BaseModel):
    """ZH: 外部 AI 平台網址設定 | EN: External AI platform URL setting"""
    url: str
    logout_url: Optional[str] = None        # ZH: v2.8 廠商登出網址 | EN: vendor logout URL


class ExternalAiImportResult(BaseModel):
    """ZH: CSV 匯入結果 | EN: CSV import result"""
    created: int = 0
    updated: int = 0
    skipped: int = 0
    errors: List[str] = Field(default_factory=list)


# ==============================================================================
# ZH: v3.4 問題回報 (Issue Reports)
# EN: v3.4 user issue reports
# ==============================================================================
ISSUE_STATUSES = ("open", "in_progress", "resolved")


class IssueReportCreate(BaseModel):
    """ZH: 使用者送出問題回報 | EN: User submits an issue report

    ⚠ ZH: diagnostics 是**前端攤開給使用者看的那一份**，原封不動送上來。
        後端不補任何使用者沒看到的欄位（IP、session…）——見 models.IssueReport 註解。
    """
    subject: Optional[str] = Field(None, max_length=120,
                                   description="ZH: 主旨（一句話）| EN: subject line")
    category: Optional[str] = Field(None, max_length=20,
                                    description="ZH: 類別代碼 | EN: category code")
    body: str = Field(..., min_length=1, max_length=4000,
                      description="ZH: 使用者描述 | EN: what happened")
    diagnostics: Dict[str, Any] = Field(default_factory=dict,
                                        description="ZH: 頁面上顯示過的診斷欄位")

    # ZH: 類別是**固定的代碼**，不是自由文字。收白名單以外的值一律當成沒選 ——
    #     不擋的話資料庫裡會長出一堆只出現過一次的類別，管理端的篩選就沒有意義了。
    # ZH: 🔴 這份清單與前端 report.js 的 CATEGORIES 必須一致。
    #     不一致的表現是：使用者選得到、送出後被清空，而且沒有任何錯誤訊息。
    # ZH: 標 ClassVar —— 不標的話 pydantic 會把它當成一個**欄位**，
    #     整個模組匯入就失敗（PydanticUserError）。
    CATEGORIES: ClassVar[set] = {"quota", "account", "train", "lab", "other"}

    @field_validator("category")
    @classmethod
    def _known_category(cls, v):
        v = (v or "").strip()
        return v if v in cls.CATEGORIES else None

    @field_validator("subject")
    @classmethod
    def _clean_subject(cls, v):
        # ZH: 整串空白等於沒填。存 "" 與存 None 要是同一種狀態。
        v = (v or "").strip()
        return v or None

    @field_validator("body")
    @classmethod
    def _body_not_blank(cls, v: str) -> str:
        # ZH: min_length 擋不掉整串空白——那會產生一筆管理者看不懂的空回報。
        s = v.strip()
        if not s:
            raise ValueError("描述不可為空白")
        return s


class IssueReportResponse(BaseModel):
    """ZH: 回報內容（使用者與 admin 共用；欄位相同，差別在誰看得到哪些筆）"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: Optional[str] = None
    username_at_report: Optional[str] = None
    subject: Optional[str] = None
    category: Optional[str] = None          # ZH: 代碼；顯示文字由前端依語言查表
    body: str
    diagnostics: Optional[str] = None       # ZH: 存的是 JSON 字串，前端自己 parse
    status: str = "open"
    created_at: datetime
    updated_at: Optional[datetime] = None
    admin_reply: Optional[str] = None
    replied_at: Optional[datetime] = None

    # ZH: ⚠ 時間欄位存的是 **UTC**（models 用 datetime.now(timezone.utc)），
    #     但 SQLite 存回來是 naive datetime，序列化出去長這樣：
    #         "2026-08-20T01:42:38.152605"          ← 沒有時區
    #     瀏覽器的 new Date(...) 會把沒有時區的字串當成**本地時間**，
    #     於是 +08:00 的使用者看到的時間**早了 8 小時**。
    #     不會報錯、不會壞版面，只是每個時間都是錯的 —— 實測抓到（送出 09:42 顯示 01:42）。
    #     這裡明講它是 UTC，前端就不必各自補救。
    # EN: Naive UTC datetimes serialize without an offset; browsers then read them as
    #     local time (8h early for +08:00). Emit an explicit UTC marker instead.
    @field_serializer("created_at", "updated_at", "replied_at")
    def _as_utc(self, v: Optional[datetime]) -> Optional[str]:
        if v is None:
            return None
        return (v.replace(tzinfo=timezone.utc) if v.tzinfo is None else v).isoformat()


class AdminIssueReportUpdate(BaseModel):
    """ZH: admin 更新狀態 / 寫回應 | EN: Admin updates status / writes a reply

    ZH: 兩個欄位都可選：只改狀態、只寫回應、兩個一起改，都是合法的。
    """
    status: Optional[str] = None
    admin_reply: Optional[str] = Field(None, max_length=4000)

    @field_validator("status")
    @classmethod
    def _known_status(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in ISSUE_STATUSES:
            raise ValueError(f"status 必須是 {ISSUE_STATUSES} 其中之一")
        return v


# ==============================================================================
# ZH: v3.5 介面偏好（字級 / 語言），跟帳號走
# ==============================================================================
UI_LANGS = ("zh", "en")
UI_THEMES = ("yellow", "blue")                # ZH: 開發期雙色系；上線擇一後這裡收斂
FONT_SCALE_MIN, FONT_SCALE_MAX = 80, 150      # ZH: 沿用 v1.5 的範圍


class UserPreferencesUpdate(BaseModel):
    """ZH: 兩個欄位都可選——只改字級、只改語言、兩個一起改，都是合法的。"""
    ui_font_scale: Optional[int] = Field(None, ge=FONT_SCALE_MIN, le=FONT_SCALE_MAX)
    ui_lang: Optional[str] = None
    ui_theme: Optional[str] = None

    @field_validator("ui_lang")
    @classmethod
    def _known_lang(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in UI_LANGS:
            raise ValueError(f"ui_lang 必須是 {UI_LANGS} 其中之一")
        return v

    @field_validator("ui_theme")
    @classmethod
    def _known_theme(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in UI_THEMES:
            raise ValueError(f"ui_theme 必須是 {UI_THEMES} 其中之一")
        return v
