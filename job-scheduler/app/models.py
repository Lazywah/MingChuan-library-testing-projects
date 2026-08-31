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
    """ZH: 產生 UUID 字串 | EN: Generate UUID string

    @node job-scheduler/app/models.py::generate_uuid
    """
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
    # ZH: v3.8 這個 role 是怎麼來的 —— `sso_email`(依信箱網域自動判) / `admin`(管理者設)
    #     / NULL(v3.8 之前建的,不知道)。
    # ZH: 為什麼要記：自動判定的依據是**我們自己組出來的信箱**（MCU 的 userinfo
    #     只回 sub,email 是依 sub 的長相推的）。所以實際規則是「sub 開頭是英文字母
    #     就給 teacher」—— 學號不是 8 碼純數字的學生會安靜地拿到 teacher。
    #     沒有這一欄的話,「誰是自動升的」與「誰是管理者確認過的」完全分不出來。
    role_source = Column(String, nullable=True)                               # ZH: sso_email / admin / NULL
    # ZH: v3.8 **身分與權限拆開**（擁有者裁定 2026-08-27）。
    #     role 是「你是誰」（學生／教師／職員／訪客）,is_admin 是「你能做什麼」。
    #     合成一個欄位時,一個學生兼系統管理員只能二選一 ——
    #     選 admin 的話他在「依身分」統計裡會被算成管理員,汙染自己的報表。
    # ZH: 🔴 **使用者端絕對碰不到這個欄位**：它只出現在 AdminUserUpdate,
    #     使用者端的 UserUpdate 連表達它的能力都沒有,而 crud.update_user
    #     是逐欄位明寫、不是 setattr 掃過去。要加使用者可改的欄位時,
    #     務必維持這個形狀 —— 改成通用的 setattr 迴圈就等於開了提權後門。
    is_admin = Column(Integer, default=0, nullable=False)                     # ZH: 管理權限（與 role 無關）
    is_active = Column(Integer, default=1)                                    # ZH: 啟用狀態 | EN: Active status
    last_login_time = Column(DateTime, nullable=True)                         # ZH: 最後登入時間 | EN: Last login time
    last_login_ip = Column(String, nullable=True)                             # ZH: 最後登入IP | EN: Last login IP
    last_activity = Column(DateTime, nullable=True, index=True)               # ZH: 最後活動時間 (v2.1 修正：取代 online_status) | EN: Last activity time (v2.1: supersedes online_status)
    # ZH: 🔴 **這個欄位不要讀。** v2.1 起已 deprecated,而且沒有任何地方寫它 ——
    #     所以它**永遠是 0**。讀了會得到「所有人都離線」這個錯誤但看起來很合理的答案。
    #     線上狀態一律用 admin.py 的 _compute_online()（依 last_activity 當場算）。
    #     API 回應裡仍有一個叫 online_status 的欄位,那是算出來的值,不是這一欄。
    # ZH: 2026-08-27 擁有者裁定保留欄位（移除的好處不足以換取改結構的風險）。
    online_status = Column(Integer, default=0)                                # ZH: 見上,不要讀 | EN: Deprecated, always 0 — never read
    is_test_account = Column(Integer, default=0)                              # ZH: 測試帳號標記 (0:否, 1:是) | EN: Test account flag

    # ZH: v3.7 臨時帳號（校外人士、長官視察、例外用途）
    #
    # ⚠ **不要用 is_test_account 做這件事**：帶那個旗標的帳號會在**每次服務重啟時
    #   被刪掉**（見 main.py 的開機清理）。長官視察當天重啟一次，帳號就沒了。
    #
    # ZH: `expires_at` 到期後由每日排程把 is_active 設成 0（**不刪帳號**，
    #   擁有者裁定）——留著才查得到「誰、什麼時候、為了什麼而開過帳號」。
    #   登入路徑也會即時擋（不能只靠排程，那中間有最多一天的空窗）。
    expires_at   = Column(DateTime, nullable=True, index=True)                # ZH: 臨時帳號的到期時間（None=永久）
    temp_purpose = Column(String, nullable=True)                              # ZH: 為什麼開這個帳號（臨時帳號必填）
    # ZH: v3.8 初次登入設定（校區 / 學系 or 行政單位）完成的時間。NULL = 還沒設定過。
    # ZH: 🔴 **刻意不沿用 tutorial_dismissed** —— 那是「不再顯示教學」,語意不同。
    #     混用之後：關掉教學的人會被當成已完成設定,而完成設定的人再也看不到教學。
    onboarded_at = Column(DateTime, nullable=True)
    tutorial_dismissed = Column(Integer, default=0)                           # ZH: 是否不再顯示教學 (0:否, 1:是) | EN: Tutorial dismissed (0:no, 1:yes)
    department = Column(String, nullable=True)                                # ZH: 學系資訊 | EN: Department
    # ZH: v3.8 組織欄位。學院**不在這裡** —— 由 department 經 org_departments 推導。
    #     unit 只有職員（role='staff'）有意義；campus 所有人都可以有。
    unit       = Column(String, nullable=True)                                # ZH: 行政單位（org_units.path）
    # ZH: 校區在 user_campuses（多對多）—— 教職員可以同時屬於多個校區
    #     （擁有者裁定 2026-08-27）。學生限一個,規則在 crud.set_user_campuses。
    # ZH: v3.5 介面偏好——**跟帳號走，不是跟裝置走**（擁有者裁定）：換一台機器登入設定要在。
    #     只有兩個設定，沿用本表既有的個人偏好欄位慣例（tutorial_dismissed / department），
    #     不另開 user_preferences 表。前端另存一份 localStorage 當**快取**（避免載入時閃一下），
    #     但**真相是這裡**。
    ui_font_scale = Column(Integer, default=100)                              # ZH: 介面字級 %（80–150）| EN: UI font scale %
    ui_lang       = Column(String, default="zh")                              # ZH: 介面語言 zh / en | EN: UI language
    ui_theme      = Column(String, default="yellow")                          # ZH: 色系 yellow / blue | EN: colour scheme
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
    # ZH: v3.6 —— 使用者自己帶的訓練程式（單一 .py 的原始碼）。
    #     ⚠ 與 `inline_code` **刻意分開**：那個欄位是「程式實驗室模式」的判準，
    #       會觸發同機閘門（要讀 home_<uid>）。自帶 .py 不需要實驗室的檔案，
    #       混用會讓它被錯誤地擋在遠端節點外。
    script_source = Column(Text, nullable=True)                               # ZH: 使用者自帶的 .py 原始碼 | EN: User-supplied training script
    entry_args   = Column(Text,   nullable=True)                              # ZH: 容器入口指令 JSON 陣列 | EN: Container entry command (JSON array)
    preferred_node = Column(String, nullable=True)                            # ZH: 偏好的 GPU Worker 節點 | EN: Preferred GPU worker node

    # ZH: 進度追蹤 | EN: Progress tracking
    progress = Column(Float, default=0.0)                                     # ZH: 完成百分比 | EN: Completion %
    logs = Column(Text)                                                       # ZH: 執行日誌 | EN: Execution logs
    metrics = Column(Text)                                                    # ZH: 訓練指標 JSON | EN: Training metrics JSON
    error_message = Column(Text)                                              # ZH: 錯誤訊息 | EN: Error message

    # ZH: 輸出結果 | EN: Output result
    # ZH: ⚠ 這是**運算主機上**的路徑（/workspace/outputs/…），服務層讀不到它。
    #     留著只是給管理者上機器找檔案用。使用者要下載的檔案看 artifact_bytes。
    output_path = Column(String)                                              # ZH: 模型產出路徑（運算主機）| EN: Output path (on the compute host)
    # ZH: v3.6 —— 這張單用的是哪一份資料集。**這才是正解**：
    #     dataset_path 是客戶端傳來的字串，伺服器無從判斷所有權；
    #     dataset_id 讓伺服器自己去查（見 crud.resolve_dataset_for_user）。
    dataset_id = Column(String, ForeignKey("datasets.id", ondelete="SET NULL"))
    # ZH: v3.6 —— worker 回傳的模型檔大小。**有值＝服務層這邊真的有那個檔**。
    #     刻意不存路徑：路徑由 job_id 推導（/data/artifacts/<job_id>/model.pt），
    #     少一個會跟實體檔案漂開的字串。
    artifact_bytes = Column(Integer)                                          # ZH: 模型檔大小，None=沒有 | EN: Artifact size, None = not present

    # ZH: 時間戳記 | EN: Timestamps
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    started_at = Column(DateTime)
    completed_at = Column(DateTime)


# ==============================================================================
# ZH: 表 3b: Dataset - 使用者上傳的資料集 (v3.6)
# EN: Table 3b: Dataset - user-uploaded datasets (v3.6)
# ==============================================================================
# ZH: 為什麼需要這張表（原本只有磁碟上的檔案，沒有任何紀錄）：
#       1. **沒有紀錄就沒有刪除**。每人 2 GB 配額，傳滿之後使用者永遠卡住。
#       2. **原始檔名會遺失**。存檔名為了防命令注入已經清成 ASCII，
#          「我的圖片.zip」在磁碟上是 `0fad32ff_dataset.zip`——列表裡沒得顯示。
#       3. **所有權沒有地方查**。原本送單時的 dataset_path 是客戶端給的，
#          伺服器無從判斷那是不是他自己的（實測證實：別人的照收）。
class Dataset(Base):
    __tablename__ = "datasets"

    id = Column(String, primary_key=True, default=generate_uuid)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    # ZH: 使用者當初上傳的檔名（可能是中文）。只用於顯示，**不拿來組路徑**。
    original_name = Column(String, nullable=False)
    # ZH: 磁碟上的實際檔名（已清成安全字元）。與 user_id 一起就能推出完整路徑。
    stored_name = Column(String, nullable=False)
    size_bytes = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


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


class UserCampus(Base):
    """
    ZH: v3.8 使用者 ↔ 校區。**一開始做成 users.campus 單一欄位,同一天改掉了** ——
        教職員可以同時在台北與桃園有課,單一欄位表達不了。

    ZH: 學生限一個、教職員不限,這條規則放在 crud.set_user_campuses（寫入端），
        不做成資料庫約束:SQLite 的 CHECK 看不到另一張表的 role,
        而把規則拆成兩半會讓「規則到底是什麼」要看兩個地方。

    EN: v3.8 user↔campus. Staff may belong to several campuses; students to one.
    """
    __tablename__ = "user_campuses"

    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"),
                     primary_key=True)
    campus  = Column(String, primary_key=True)


class ProfileUnlock(Base):
    """
    ZH: v3.8 個人組織資料的**一次性解鎖**（擁有者裁定 2026-08-27）。

    ZH: 校區／學系／行政單位在初次設定之後就上鎖 —— 那三項是分組統計的基礎,
        讓人隨時自己改的話,報表會隨著人改資料而變動,而且看不出是誰改的。
        要改就跟管理員說（用既有的「問題回報」送單即可,那邊本來就有
        送出→管理端可見→回覆的完整流程）,管理員核可後開一次。

    ZH: 🔴 **「用掉」的定義是「使用者成功存檔一次」,不是「過了多久」。**
        給時間窗的話沒有人會記得回來收,那個帳號就長期開著 ——
        而「長期開著的一次性權限」比不上鎖還糟,因為大家以為它是鎖著的。

    ZH: 🔴 **可解鎖的欄位清單裡永遠沒有 role 與 is_admin。**
        那條線是型別層擋的（使用者端的 schema 連表達的能力都沒有）,
        這張表不能變成繞過它的後門。清單在 crud.UNLOCKABLE_FIELDS,有自檢擋著。

    EN: v3.8 one-shot unlock for a user's own org fields. Consumed by a successful
        save, never by elapsed time. Never covers role/is_admin.
    """
    __tablename__ = "profile_unlocks"

    id         = Column(String, primary_key=True, default=generate_uuid)
    user_id    = Column(String, ForeignKey("users.id", ondelete="CASCADE"),
                        index=True, nullable=False)
    fields     = Column(String, nullable=False)          # ZH: 逗號分隔:campus / department / unit
    reason     = Column(Text, nullable=True)             # ZH: 管理者為什麼開（留給稽核看）
    granted_by = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    granted_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    used_at    = Column(DateTime, nullable=True, index=True)   # ZH: NULL = 還沒用掉


class OrgDepartment(Base):
    """
    ZH: v3.8 學系 → 學院對照。**主鍵就是學系全名** —— `users.department` 存的就是它，
        用名稱當鍵，join 才不必再維護一組 id 對應。
    ZH: 學院不存進 users：改對照表就全站生效，不必回填幾千筆使用者。
    EN: v3.8 department→college lookup; college is derived, never stored on users.
    """
    __tablename__ = "org_departments"

    name    = Column(String, primary_key=True)                 # ZH: 學系全名
    college = Column(String, nullable=False, index=True)       # ZH: 所屬學院
    # ZH: v3.9 英文名。空的就退回中文顯示 —— **不自動翻譯**：
    #     系所有官方英文名，機器翻的比中文更難跟註冊資料對照。
    # ZH: `college_en` 存在每一列上（學院本身沒有自己的表）。同一個學院的多列
    #     若填得不一致，分組標籤取**第一個非空的**（見 crud.org_options）。
    name_en    = Column(String, nullable=True)
    college_en = Column(String, nullable=True)
    # ZH: 校區由管理者選 —— 官網的教學單位頁沒有標校區，硬推會是假資料。
    campus  = Column(String, nullable=True)
    active  = Column(Integer, default=1)                       # ZH: 停招的留著但不進下拉


class OrgUnit(Base):
    """
    ZH: v3.8 行政單位（`users.unit` 用，只有職員有）。

    ZH: 🔴 **主鍵是路徑不是名稱**：官網底下有兩個「事務組」（總務處／金門分部）
        與兩個「處長室」（桃園／基河行政處）。名稱當鍵會撞，
        而改名字讓它不撞的話，職員在下拉裡就找不到自己單位的正式名稱了。
        路徑長成 `總務處/事務組`，看得懂又唯一。
    EN: v3.8 administrative units; PK is the path because the official org chart
        genuinely contains duplicate unit names under different parents.
    """
    __tablename__ = "org_units"

    path   = Column(String, primary_key=True)                  # ZH: 上層/名稱，或頂層就是名稱
    name   = Column(String, nullable=False, index=True)        # ZH: 顯示用的原名（逐字照官網）
    name_en = Column(String, nullable=True)                    # ZH: v3.9 英文名（空的退回中文）
    parent = Column(String, nullable=True, index=True)         # ZH: 上層處室名；頂層為 NULL
    campus = Column(String, nullable=True)
    active = Column(Integer, default=1)


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
    # ZH: v3.8 銷毀前的提醒。分兩格而不是一個「已提醒」布林 ——
    #     兩封信的內容與急迫度不同,只記一格的話補寄或稽核時分不出寄過哪一封。
    reminded_first_at = Column(DateTime, nullable=True)   # ZH: 第一次提醒寄出時間
    reminded_final_at = Column(DateTime, nullable=True)   # ZH: 最後提醒寄出時間
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
    # ZH: v3.6 —— 這個節點是否與服務層**同機**（因而看得到 per-user 的 home_<uid> volume）。
    #     程式實驗室（Notebook）模式的任務靠那個 volume 取得使用者的檔案；跨機時它會是一個
    #     **自動建立的空 volume**，不報錯但資料不在。預設 0（不同機）＝安全的一邊。
    shares_storage = Column(Integer, default=0)                               # ZH: 是否與服務層同機 | EN: Co-located with the service layer
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
    # ZH: v3.6 —— 多份存檔的鍵。`default` 是原本那一份（沿用舊的容器／volume／網址名）。
    #     ⚠ 這個值會進**容器名與網址**，所以只允許 [a-z0-9-]；使用者看得懂的名字
    #       存在 display_name，兩者刻意分開（中文不能進 DNS 名稱）。
    session_name   = Column(String, default="default")                        # ZH: v3.6 多份存檔的鍵
    display_name   = Column(String, nullable=True)                            # ZH: 使用者取的名字（可中文）
    container_id   = Column(String, nullable=True)                            # ZH: Docker 容器 ID | EN: Docker container ID
    container_name = Column(String, nullable=True)                            # ZH: 容器名稱 cs-{user_id} | EN: Container name
    status         = Column(String, default="stopped")                        # ZH: stopped / starting / running / stopping
    volume_name    = Column(String, nullable=False)                           # ZH: 對應 named volume，如 home_alice
    base_image     = Column(String, nullable=False, default="aibase/pytorch:2026-spring")  # ZH: 目前使用的 image
    # ZH: 🔴 **不要**給 default=now。只有 start_session / touch_activity 寫這個欄位，
    #     兩處都明確給值；而有 default 的話「剛建好、還沒開過」的存檔會被填上「現在」，
    #     畫面就會寫「最後使用：今天 09:22」——陳述一件沒發生過的事。
    #     （SQLAlchemy 把 `last_activity=None` 當成「沒給值」，所以在建立端寫 None 沒有用。）
    last_activity  = Column(DateTime, nullable=True)                                      # ZH: 最後活動時間（沒開過 = None）
    started_at     = Column(DateTime, nullable=True)                          # ZH: 啟動時間
    # ZH: v3.9 這個 session 佔用的 GPU 編號；NULL = 沒有 GPU（預設，CPU 實驗室）。
    #
    # ZH: 🔴 **為什麼要記在這裡**：批次訓練由 `gpu-worker` 派，它用的是自己行程內的
    #     `_busy_gpus`，看不到 Lab 容器。一張卡被兩個互不知情的分配者共用時，
    #     學生會拿到莫名其妙的 CUDA OOM，而且完全看不出是被別人佔走。
    #     把佔用寫進資料庫，`/worker/take` 才有辦法在派工前把這張卡排除掉。
    #
    # ZH: ⚠ 只在**與服務層同機**的 worker 上有意義（台北的節點有自己的卡）。
    #     判斷依據是 take 請求裡的 `shares_service_storage`。
    gpu_index      = Column(Integer, nullable=True)
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
    # ZH: v3.9 凍結原因。`freeze()` 的 reason 原本只寫進 notes 的自由文字裡，
    #     那個字串是**給人看的**，不能拿來做判斷。
    # ZH: 🔴 為什麼需要它：自動解凍必須分得出來是誰凍的 ——
    #     「超配額」在用量降下去之後該自動解開，
    #     **「管理員手動凍結」絕對不可以被自動解開**。
    #     沒有這個欄位的話，自動解凍會把管理員的處置也一起撤銷。
    frozen_reason   = Column(String, nullable=True)
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
    # ZH: v3.9 英文版（擁有者裁定 2026-08-30）。**空的退回中文** ——
    #     與 name_en 同一條規則。強制要填英文的話，結果是公告乾脆不發。
    # ZH: ⚠ 中文欄位仍然是必填。英文版是「額外的」，不是「另一則公告」——
    #     兩邊都可空的話，會出現一則兩種語言都看不到內容的公告。
    title_en    = Column(String, nullable=True)
    body_en     = Column(Text, nullable=True)
    posted_by   = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    posted_at   = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    updated_at  = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                                   onupdate=lambda: datetime.now(timezone.utc))
    is_pinned   = Column(Integer, default=0)                                # ZH: 1 = 置頂 (排在最前)
    is_visible  = Column(Integer, default=1)                                # ZH: 0 = 隱藏 (草稿/已下架)


class AnnouncementFile(Base):
    """ZH: 公告附件 | EN: Announcement attachment

    ZH: 為什麼是一張表而不是公告上的一個欄位：一則公告可能夾好幾個檔案。

    ZH: ⚠ `filename` 與 `stored_name` **刻意分開**：
        前者是管理員上傳時的原始檔名（畫面上要顯示的），
        後者是磁碟上真正的檔名（只留安全字元）。
        合成一個的話，要嘛畫面上出現一串沒人看得懂的字，
        要嘛檔名裡的路徑符號會變成安全問題。資料集那邊是同一套做法。

    ZH: 🔴 `ondelete="CASCADE"` 只清資料庫的列，**磁碟上的檔案不會跟著消失**。
        刪公告的路徑必須自己刪檔（見 routers/announcements.py），
        否則就是製造下一個孤兒類別。
    """
    __tablename__ = "announcement_files"

    id             = Column(Integer, primary_key=True, autoincrement=True)
    announcement_id = Column(Integer, ForeignKey("announcements.id", ondelete="CASCADE"),
                             nullable=False, index=True)
    filename       = Column(String, nullable=False)      # ZH: 原始檔名（顯示用）
    stored_name    = Column(String, nullable=False)      # ZH: 磁碟上的檔名（安全字元）
    size_bytes     = Column(Integer, nullable=False, default=0)
    content_type   = Column(String, nullable=True)
    uploaded_at    = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class MyaiVisit(Base):
    """ZH: 使用者從平台跳去 MYAI 的紀錄（v3.9）| EN: Platform → MYAI redirect log

    ZH: 為什麼要有這張表：`goMyai()` 只是開一個新分頁，**不留下任何痕跡**。
        於是「有多少人從平台走進 MYAI」在這之前是查不到的。

    ZH: ⚠ 這與 `myai_transactions` 測的**不是同一件事**：
          這張表 = 有多少人走進去（入口流量）
          交易日誌 = 進去之後真的用了幾次（實際使用）
        一個人跳進去發呆五分鐘就關掉，這裡 +1、交易 +0。

    ZH: 🔴 **不存 IP**。統計要回答的是「哪個系在用」，而那由 user_id 就推得出來
        （users.department → org_departments）。存 IP 對這個問題沒有任何貢獻，
        只是多留一份可以反推位置的資料。與問題回報同一條原則。

    ZH: ⚠ 按下按鈕就記，**不管新分頁有沒有被瀏覽器擋掉** ——
        那是「他想去」的事實，而彈窗被擋是我們這邊的問題，
        不該讓他從統計裡消失。
    """
    __tablename__ = "myai_visits"

    id          = Column(Integer, primary_key=True, autoincrement=True)
    user_id     = Column(String, ForeignKey("users.id", ondelete="CASCADE"),
                         nullable=False, index=True)
    occurred_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)


class LabUsageLog(Base):
    """ZH: Lab 每一次啟動的紀錄（v3.9）| EN: One row per lab session start

    ZH: 🔴 為什麼不能用 `lab_sessions` 算：**那張表是狀態不是歷史**。
        每次啟動都覆寫同一列的 `started_at` 與 `gpu_index`，停止時把
        `gpu_index` 清成 None。所以它回答的是「**現在**有幾張卡被借走」，
        不是「這段期間被借了幾次」。拿它做日期分群會得到一個看起來合理
        但其實錯的數字。

    ZH: ⚠ `user_session_usage` 有每日的 session_count，但**不分 CPU/GPU** ——
        開實驗室寫程式與借卡跑訓練被算在一起。這張表就是為了分開它們。

    ZH: `ended_at` 為 NULL = 還在跑（或平台在它結束前重啟過）。
        算時長時要把 NULL 排除掉，不要當成 0 —— 那會把還在跑的長工作
        算成「用了 0 秒」。
    """
    __tablename__ = "lab_usage_log"

    id         = Column(Integer, primary_key=True, autoincrement=True)
    user_id    = Column(String, ForeignKey("users.id", ondelete="CASCADE"),
                        nullable=False, index=True)
    started_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    ended_at   = Column(DateTime, nullable=True)
    used_gpu   = Column(Integer, default=0, index=True)   # ZH: 1 = 這次借了 GPU
    gpu_index  = Column(Integer, nullable=True)


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
    status          = Column(String, default="active", nullable=False)        # ZH: active / disabled / vendor_deleted(v4.0 對帳偵測到廠商端已刪；provision 會重建並復活) | EN: active / disabled / vendor_deleted
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

    # ==========================================================================
    # ZH: v3.9 初始點數發放紀錄 —— **這三欄同時是稽核紀錄與冪等鍵**。
    #     發點數是不可逆的（廠商端收不回來），所以「發過沒有」不能靠流程保證，
    #     要靠資料庫裡的事實：`credit_granted_at` 有值就**永不再發**。
    #     為什麼不寫進 admin_actions：那張表的 admin_id 是 NOT NULL 且外鍵指向
    #     users，而自動開通沒有「執行的管理員」—— 硬塞一個人進去等於記錄假的
    #     執行者。現有的系統發起路徑是直接跳過稽核（storage_lifecycle 的
    #     `if admin_id:`），對不可逆的發點數而言那更糟。
    # EN: v3.9 initial-credit grant record; doubles as the idempotency key.
    #     A non-null credit_granted_at means "already granted, never again".
    # ==========================================================================
    credit_granted_at    = Column(DateTime, nullable=True)                    # ZH: 發放時間（有值＝發過了）| EN: granted at (non-null = already granted)
    credit_granted_pts   = Column(Integer, nullable=True)                     # ZH: 實際發放點數 | EN: points granted
    credit_grant_note    = Column(Text, nullable=True)                        # ZH: 結果／失敗原因 | EN: outcome or failure reason


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


# ==============================================================================
# ZH: 表 22: IssueReport - 使用者問題回報 (v3.4 新增)
# EN: Table 22: IssueReport - user-submitted issue reports (v3.4)
#
# ZH: 使用者在 web-ui 的「問題回報」頁送出，管理端可見、可回應。
#     v3.4 範圍：**單則回應**（管理者寫一段回覆，使用者看得到，不能再回）。
#     來回對話串需要另一張表 + 未讀狀態 + 通知，範圍差很多，刻意不做。
#
# ⚠ ZH: **這張表不存任何使用者沒看到的欄位——包括 IP。**
#     report.html 把診斷資訊整段攤開給使用者看，並寫著「要別人交出診斷資訊，
#     就不能讓他不知道交了什麼」。後端若在送出時偷偷補上 IP 或 session 資訊，
#     那句話就變成假的。diagnostics 原封不動存前端送來的那份。
#     （與 myai_transactions 不存 IP 是同一條原則。）
# EN: Stores ONLY what the user was shown before submitting — no IP, no
#     server-side fingerprinting. The report page displays the exact diagnostics
#     payload; silently enriching it server-side would make that display a lie.
#
# ZH: user_id 是 SET NULL 而非 CASCADE：帳號刪了，問題可能還在，
#     那仍是管理者的待辦。username_at_report 留下快照，刪帳號後仍知道是誰報的。
# ==============================================================================
class IssueReport(Base):
    __tablename__ = "issue_reports"

    id          = Column(Integer, primary_key=True, autoincrement=True)
    user_id     = Column(String, ForeignKey("users.id", ondelete="SET NULL"),
                         nullable=True, index=True)
    username_at_report = Column(String, nullable=True)                        # ZH: 送出當下的帳號名快照
    # ZH: v3.9 主旨與類別。
    #   subject  —— 管理端清單一列只放得下一句話，用內文的前 60 字當摘要
    #               常常切在句子中間。主旨是使用者自己寫的那一句。
    #   category —— 值是**固定的英數代碼**（quota/account/train/lab/other），
    #               不是顯示文字：顯示文字要翻譯，而翻譯過的字串當篩選鍵，
    #               介面一切成英文就篩不到任何東西。
    # ZH: 兩者都 nullable —— v3.9 之前的回報沒有這兩欄，補上預設值等於
    #     替使用者宣稱他選了某個類別。空的就是空的。
    subject     = Column(String, nullable=True)
    category    = Column(String, nullable=True, index=True)
    body        = Column(Text, nullable=False)                                # ZH: 使用者描述
    diagnostics = Column(Text, nullable=True)                                 # ZH: JSON，前端攤開給使用者看的那份
    status      = Column(String, default="open", index=True)                  # ZH: open / in_progress / resolved
    created_at  = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    updated_at  = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                         onupdate=lambda: datetime.now(timezone.utc))

    admin_reply = Column(Text, nullable=True)                                 # ZH: 管理者回應（單則）
    replied_by  = Column(String, ForeignKey("users.id", ondelete="SET NULL"),
                         nullable=True, index=True)
    replied_at  = Column(DateTime, nullable=True)
