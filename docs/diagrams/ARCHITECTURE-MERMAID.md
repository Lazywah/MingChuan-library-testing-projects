# 系統架構圖表（Mermaid）| Architecture Diagrams (Mermaid)

> 本文件以 Mermaid 語法繪製專案完整架構，可直接在 GitHub / VS Code / Obsidian 等支援 Mermaid 的工具中渲染。

## 📑 目錄 | Table of Contents
1. [檔案結構樹（Project File Tree）](#1-檔案結構樹-project-file-tree)
2. [三層系統架構（Three-Layer Architecture）](#2-三層系統架構-three-layer-architecture)
3. [Docker 容器網路（Container Network）](#3-docker-容器網路-container-network)
4. [資料庫 ER 圖（Database ER）](#4-資料庫-er-圖-database-er)
5. [API 端點地圖（API Endpoint Map）](#5-api-端點地圖-api-endpoint-map)
6. [前端模組與頁面導覽（Frontend Navigation）](#6-前端模組與頁面導覽-frontend-navigation)
7. [使用者角色 RBAC（Role-Based Access Control）](#7-使用者角色-rbac-role-based-access-control)
8. [使用者認證流程（Auth Sequence）](#8-使用者認證流程-auth-sequence)
9. [GPU Worker Pull 模式（Worker Pull Sequence）](#9-gpu-worker-pull-模式-worker-pull-sequence)
10. [Notebook 提交與執行流程（Notebook Execution Sequence）](#10-notebook-提交與執行流程-notebook-execution-sequence)
11. [訓練任務狀態機（Job State Machine）](#11-訓練任務狀態機-job-state-machine)
12. [類別關聯圖（Class Diagram – Backend Modules）](#12-類別關聯圖-class-diagram--backend-modules)

---

## 1. 檔案結構樹（Project File Tree）

```mermaid
flowchart LR
    Root["CodeSpace/"] --> Env[".env / .env.example"]
    Root --> DC1["docker-compose.yml<br/>(核心:nginx+scheduler)"]
    Root --> DC2["docker-compose.ai-models.yml<br/>(open-webui+portkey+ollama)"]
    Root --> Readme["README.md"]

    Root --> WebUI["web-ui/<br/>使用者前端"]
    WebUI --> WI["index.html"]
    WebUI --> WA["app.js<br/>(SPA 業務邏輯)"]
    WebUI --> WS["styles.css"]

    Root --> AdminUI["admin-ui/<br/>管理員前端"]
    AdminUI --> AI["index.html"]
    AdminUI --> AA["admin.js"]
    AdminUI --> AS["styles.css"]

    Root --> JS["job-scheduler/<br/>FastAPI 後端"]
    JS --> JSDF["Dockerfile / requirements.txt"]
    JS --> JSApp["app/"]
    JSApp --> M1["main.py<br/>應用入口"]
    JSApp --> M2["config.py / database.py"]
    JSApp --> M3["models.py<br/>(8 張表)"]
    JSApp --> M4["schemas.py / crud.py"]
    JSApp --> M5["auth.py / sso_client.py"]
    JSApp --> M6["scheduler.py<br/>(每 5 分超時清理)"]
    JSApp --> M7["rate_limit.py"]
    JSApp --> Pol["*.yaml<br/>(scheduler/sso policy)"]
    JSApp --> R["routers/"]
    R --> R1["auth.py / sso.py"]
    R --> R2["jobs.py / worker.py"]
    R --> R3["admin.py / system.py"]
    R --> R4["chat.py / datasets.py"]
    R --> R5["notebooks.py<br/>(2026-05 新增)"]
    JSApp --> Svc["services/email_service.py"]

    Root --> GW["gpu-worker/<br/>GPU 節點代理"]
    GW --> GWD["Dockerfile / docker-compose.yml"]
    GW --> GWW["worker.py<br/>(輪詢 + 容器派發)"]

    Root --> INF["infrastructure/"]
    INF --> NG["nginx.conf<br/>(反向代理)"]
    INF --> SQL["schema.sql"]

    Root --> PK["portkey/config.yaml<br/>(LLM 閘道路由)"]
    Root --> SCR["scripts/<br/>(deploy.sh / setup_env.py)"]
    Root --> T["tests/<br/>(72 個測試)"]
    Root --> Data["data/<br/>(SQLite + 上傳檔)"]
    Root --> DocDir["docs/<br/>(11 份手冊)"]
```

---

## 2. 三層系統架構（Three-Layer Architecture）

```mermaid
flowchart TB
    subgraph L1["第一層：使用者端 (Browser)"]
        U[("👤 使用者<br/>瀏覽器")]
    end

    subgraph L2["第二層：服務層 (Ubuntu Server)"]
        direction TB
        NGX["Nginx :80 / :8888<br/>反向代理 API Gateway"]
        FA["Job Scheduler<br/>FastAPI :8002"]
        DB[("SQLite DB<br/>/data/ai_platform.db")]
        PKG["Portkey LLM Gateway :8000"]
        OL["Ollama :11434<br/>(本地模型)"]
        OWUI["Open WebUI :3000<br/>(備用)"]
        SCH["scheduler.py<br/>(每 5 分超時清理)"]
    end

    subgraph L3["第三層：GPU 高階伺服器 (Windows 11 + WSL2)"]
        direction TB
        WK["gpu-worker/worker.py<br/>(Docker 容器)"]
        NV["nvidia-smi<br/>GPU 偵測"]
        DC["docker run<br/>動態建立訓練容器"]
        STG["Samba 共享<br/>/workspace"]
    end

    U -->|"HTTP/SSE<br/>Port 80"| NGX
    NGX -->|"/train/*"| WebFE["web-ui SPA"]
    NGX -->|"/admin-ui/*"| AdmFE["admin-ui SPA"]
    NGX -->|"/api/v1/*"| FA
    FA <-->|"ORM"| DB
    FA -->|"SSE 代理"| PKG
    PKG --> OL
    PKG -->|"API"| EXT["Anthropic / OpenAI / Google"]
    OWUI -.->|"備用入口"| PKG
    SCH --> DB

    WK -->|"每 5s POST /worker/take"| FA
    WK -->|"每 30s POST /worker/heartbeat"| FA
    WK -->|"PUT /worker/jobs/{id}/update"| FA
    WK --> NV
    WK --> DC
    DC -->|"--gpus device=N"| STG

    classDef l1 fill:#dae8fc,stroke:#6c8ebf
    classDef l2 fill:#d5e8d4,stroke:#82b366
    classDef l3 fill:#ffe6cc,stroke:#d79b00
    class U l1
    class NGX,FA,DB,PKG,OL,OWUI,SCH,WebFE,AdmFE l2
    class WK,NV,DC,STG l3
```

---

## 3. Docker 容器網路（Container Network）

```mermaid
flowchart LR
    subgraph Net["ai-platform-net (bridge network)"]
        direction TB
        N1["ai-platform-nginx<br/>:80 / :8888"]
        N2["ai-platform-scheduler<br/>:8002"]
        N3["ai-platform-portkey<br/>:8000"]
        N4["ai-platform-ollama<br/>:11434"]
        N5["ai-platform-webui<br/>(open-webui :3000)"]
    end

    subgraph Vols["Docker Volumes"]
        V1[("./data → /data<br/>SQLite + datasets")]
        V2[("./infrastructure/nginx.conf")]
        V3[("./web-ui /usr/share/nginx/html/train")]
        V4[("./admin-ui /usr/share/nginx/html/admin-ui")]
        V5[("open-webui-data")]
        V6[("ollama-data")]
        V7[("./portkey/config.yaml")]
    end

    subgraph Compose["Compose 檔案"]
        C1["docker-compose.yml<br/>(核心)"]
        C2["docker-compose.ai-models.yml<br/>(AI Models)"]
    end

    C1 --> N1
    C1 --> N2
    C2 --> N3
    C2 --> N4
    C2 --> N5

    N1 --> V2
    N1 --> V3
    N1 --> V4
    N2 --> V1
    N5 --> V5
    N4 --> V6
    N3 --> V7

    N1 -. "depends_on" .-> N2
    N5 -. "depends_on" .-> N3
    N3 -. "depends_on" .-> N4

    Host(["🖥️ Host: Ubuntu / Windows"]) -->|":80"| N1
    Host -->|":8888 Admin"| N1
    Host -->|":3000 Open WebUI"| N5
```

---

## 4. 資料庫 ER 圖（Database ER）

```mermaid
erDiagram
    USERS ||--o| TOKEN_USAGE : has
    USERS ||--o{ TRAINING_JOBS : submits
    USERS ||--o{ CHAT_HISTORY : owns
    USERS ||--o| NOTEBOOKS : draft
    USERS ||--o{ MODELS : uploads

    USERS {
        string  id PK "UUID"
        string  username UK
        string  email UK
        string  hashed_password
        string  role "student/teacher/admin"
        int     is_active
        int     is_test_account
        int     tutorial_dismissed
        string  department
        int     online_status
        datetime last_login_time
        string  last_login_ip
        int     login_count
        int     lifetime_tokens_used
        datetime created_at
        datetime updated_at
    }

    TOKEN_USAGE {
        string  id PK
        string  user_id FK "CASCADE"
        int     tokens_used
        int     tokens_limit
        datetime reset_date
        datetime last_updated
    }

    TRAINING_JOBS {
        string  id PK
        string  user_id FK "SET NULL"
        string  job_name
        string  model_name
        string  status "pending|queued|running|completed|failed|cancelled"
        int     gpu_required
        int     priority "0-5"
        text    config "JSON"
        string  gpu_server
        int     gpu_id
        string  script_path
        string  dataset_path
        string  docker_image "2026-05 新增"
        text    inline_code "2026-05 新增"
        text    entry_args "2026-05 新增 JSON"
        string  preferred_node "2026-05 新增"
        float   progress
        text    logs
        text    metrics "JSON"
        text    error_message
        string  output_path
        datetime created_at
        datetime started_at
        datetime completed_at
    }

    MODELS {
        string  id PK
        string  name UK
        string  model_type "api|local"
        text    description
        string  framework
        string  storage_path
        int     size_bytes
        string  uploaded_by FK
        int     is_public
        string  api_provider
        string  api_endpoint
        string  api_model_id
        datetime created_at
    }

    CHAT_HISTORY {
        string  id PK
        string  user_id FK "CASCADE"
        string  session_id
        string  role "user|assistant"
        text    content
        string  tool_type
        int     tokens_used
        datetime created_at
    }

    SYSTEM_CONFIG {
        string  key PK
        string  value
        text    description
        datetime updated_at
    }

    WORKER_HEARTBEATS {
        string  node_id PK
        text    available_gpus "JSON array"
        float   gpu_utilization
        datetime last_seen
        int     is_online
    }

    NOTEBOOKS {
        string  id PK
        string  user_id FK "CASCADE UNIQUE"
        text    cells "JSON array"
        text    environment "JSON object"
        datetime updated_at
    }
```

---

## 5. API 端點地圖（API Endpoint Map）

```mermaid
flowchart LR
    API(("/api/v1"))

    API --> AuthGrp["auth/"]
    AuthGrp --> A1["POST /login"]
    AuthGrp --> A2["POST /register"]
    AuthGrp --> A3["GET /me"]
    AuthGrp --> A4["PUT /me"]
    AuthGrp --> A5["GET /usage"]
    AuthGrp --> A6["POST /logout"]
    AuthGrp --> A7["POST /forgot-password"]
    AuthGrp --> A8["POST /sso/login"]

    API --> JobsGrp["jobs/"]
    JobsGrp --> J1["POST /"]
    JobsGrp --> J2["GET /"]
    JobsGrp --> J3["GET /:id"]
    JobsGrp --> J4["DELETE /:id"]
    JobsGrp --> J5["GET /:id/stream<br/>(SSE)"]

    API --> ChatGrp["chat/"]
    ChatGrp --> CH1["POST /completions<br/>(SSE)"]
    ChatGrp --> CH2["GET /history"]

    API --> DSGrp["datasets/"]
    DSGrp --> D1["POST /upload"]
    DSGrp --> D2["GET /list"]

    API --> NBGrp["notebooks/<br/>(2026-05)"]
    NBGrp --> NB1["GET /mine"]
    NBGrp --> NB2["PUT /mine"]
    NBGrp --> NB3["GET /nodes"]

    API --> WkGrp["worker/<br/>Bearer Token"]
    WkGrp --> W1["POST /take"]
    WkGrp --> W2["POST /jobs/:id/update"]
    WkGrp --> W3["POST /heartbeat"]

    API --> SysGrp["system/<br/>admin only"]
    SysGrp --> S1["GET /files"]
    SysGrp --> S2["GET /files/:name"]
    SysGrp --> S3["PUT /files/:name"]

    API --> AdmGrp["admin/<br/>admin only"]
    AdmGrp --> AD1["GET /users"]
    AdmGrp --> AD2["PUT /users/:id"]
    AdmGrp --> AD3["POST /users/:id/delete"]
    AdmGrp --> AD4["POST /users/:id/reset"]
    AdmGrp --> AD5["POST /users/provision"]
    AdmGrp --> AD6["PUT /users/batch/tokens"]
    AdmGrp --> AD7["POST /verify"]
    AdmGrp --> AD8["GET /jobs"]
    AdmGrp --> AD9["POST /jobs/:id/cancel"]
    AdmGrp --> AD10["PUT /jobs/:id/priority"]
    AdmGrp --> AD11["GET /models / POST / PUT / DELETE"]
    AdmGrp --> AD12["GET /cluster/stats"]
    AdmGrp --> AD13["GET /analytics"]

    classDef new fill:#fff2cc,stroke:#d6b656
    class NBGrp,NB1,NB2,NB3 new
```

---

## 6. 前端模組與頁面導覽（Frontend Navigation）

```mermaid
flowchart TB
    Start([使用者開啟瀏覽器]) --> Login[#login-page<br/>登入頁]
    Login -->|"本機 / SSO"| Tut{首次登入?}
    Tut -->|Yes| Tutorial[Welcome 教學面板]
    Tut -->|No| Compute
    Tutorial --> Compute

    Compute[#compute-page<br/>運算任務]
    Compute --> Tab1[High 高算力表單]
    Compute --> Tab2[Mid/Low 中低算力表單]
    Compute --> Tab3["Notebook 子頁籤<br/>(2026-05)"]
    Tab3 --> NB1[工具列: 框架/模式/GPU]
    Tab3 --> NB2[資料集列]
    Tab3 --> NB3[Cells 容器<br/>code/shell/markdown]
    Tab3 --> NB4[輸出面板<br/>SSE + 進度條]

    Compute --> Assistant[#assistant-page<br/>AI 大廳]
    Assistant --> Hub[AI Hub 12 張卡片]
    Hub -->|"✅ 已實作"| Chat[文字聊天]
    Hub -->|"🚫 Coming Soon"| Soon[11 項佔位]

    Compute --> Settings[#settings-page<br/>系統設定]
    Settings --> ST1[Token Resources 環形]
    Settings --> ST2[Profile Update]
    Settings --> ST3[Appearance 主題]
    Settings --> ST4[Localization 中/英]
    Settings --> ST5[Tutorial 開啟教學]
    Settings --> ST6[Logout]

    Compute -->|"admin role"| AdminUI["/admin-ui/<br/>(獨立 SPA :8888)"]
    AdminUI --> AU1[使用者管理]
    AdminUI --> AU2[模型管理]
    AdminUI --> AU3[全域任務排程]
    AdminUI --> AU4[設定檔編輯]
    AdminUI --> AU5[數據分析]
    AdminUI --> AU6[叢集 GPU 狀態]

    classDef new fill:#fff2cc,stroke:#d6b656
    class Tab3,NB1,NB2,NB3,NB4 new
```

---

## 7. 使用者角色 RBAC（Role-Based Access Control）

```mermaid
flowchart TB
    subgraph Roles["3 種角色 (role 欄位)"]
        S["👨‍🎓 student<br/>學生"]
        T["👨‍🏫 teacher<br/>教師"]
        A["🛡️ admin<br/>管理員"]
    end

    subgraph Features["功能權限"]
        F1["提交訓練任務"]
        F2["查看自己任務"]
        F3["查看所有任務"]
        F4["取消他人任務"]
        F5["AI 助手對話"]
        F6["Token 配額管理"]
        F7["使用者 CRUD"]
        F8["模型 CRUD"]
        F9["設定檔編輯"]
        F10["強制操作任務"]
        F11["叢集 GPU 監控"]
    end

    S --> F1
    S --> F2
    S --> F5
    T --> F1
    T --> F2
    T --> F3
    T --> F5
    A --> F1
    A --> F2
    A --> F3
    A --> F4
    A --> F5
    A --> F6
    A --> F7
    A --> F8
    A --> F9
    A --> F10
    A --> F11

    classDef student fill:#dae8fc,stroke:#6c8ebf
    classDef teacher fill:#d5e8d4,stroke:#82b366
    classDef admin fill:#f8cecc,stroke:#b85450
    class S student
    class T teacher
    class A admin
```

---

## 8. 使用者認證流程（Auth Sequence）

```mermaid
sequenceDiagram
    autonumber
    participant U as 使用者
    participant W as web-ui
    participant N as Nginx
    participant API as FastAPI
    participant DB as SQLite
    participant SSO as SSO Mock

    Note over U,SSO: ─── 本機帳號登入 ───
    U->>W: 輸入帳號 + 密碼
    W->>N: POST /api/v1/auth/login
    N->>API: 轉發
    API->>DB: SELECT user WHERE username = ?
    DB-->>API: User record
    API->>API: bcrypt.verify(pwd, hash)
    API->>API: 簽發 JWT (HS256, 24h)
    API->>DB: UPDATE last_login_time / ip / count
    API-->>W: {access_token, token_type}
    W->>W: localStorage.setItem('token')

    Note over U,SSO: ─── SSO Mock 登入 ───
    U->>W: 點擊 SSO 按鈕 + 學號
    W->>API: POST /api/v1/auth/sso/login
    API->>SSO: 比對 sso_policy.yaml
    SSO-->>API: 認證成功
    API->>DB: upsert user (auto-create if new)
    API-->>W: {access_token}

    Note over U,SSO: ─── 受保護端點存取 ───
    U->>W: 開啟 /compute-page
    W->>API: GET /api/v1/jobs<br/>Authorization: Bearer ...
    API->>API: jwt.decode + 驗證簽章
    API->>DB: SELECT jobs WHERE user_id = ?<br/>(student) 或全部 (teacher/admin)
    DB-->>API: jobs[]
    API-->>W: JSON 回應
```

---

## 9. GPU Worker Pull 模式（Worker Pull Sequence）

```mermaid
sequenceDiagram
    autonumber
    participant W as gpu-worker
    participant API as Job Scheduler
    participant DB as SQLite
    participant DK as Docker (sibling)

    loop 每 5 秒
        W->>W: nvidia-smi 查詢空閒 GPU<br/>(util < 10%)

        alt 每 30 秒一次
            W->>API: POST /worker/heartbeat<br/>{node_id, gpus, util}
            API->>DB: upsert worker_heartbeats
            API-->>W: 200 OK
        end

        alt 有空閒 GPU
            W->>API: POST /worker/take<br/>{node_id, available_gpus}
            API->>DB: SELECT pending jobs<br/>ORDER BY priority DESC
            DB-->>API: pending[]
            API->>API: 過濾 preferred_node
            API->>DB: UPDATE status='running'<br/>WHERE id=? AND status='pending'<br/>(原子搶佔)
            alt 搶佔成功
                API-->>W: {job: {...inline_code, docker_image...}}
                W->>W: 寫入 /tmp/job_{id}/run.sh
                W->>DK: docker run --rm --gpus device=N<br/>-v /workspace -v /job_code<br/>image bash -eu run.sh
                loop 串流 stdout
                    DK-->>W: 訓練日誌
                    W->>W: parse_progress()<br/>(Epoch / step / [N/M] / %)
                    W->>API: POST /worker/jobs/:id/update<br/>{log, progress}
                end
                DK-->>W: exit code
                alt exit == 0
                    W->>API: POST /worker/jobs/:id/update<br/>{status: completed, output_path}
                else
                    W->>API: POST /worker/jobs/:id/update<br/>{status: failed, error}
                end
                W->>W: rmtree /tmp/job_{id}
            else 已被別人領走
                API-->>W: {job: null}
            end
        end
    end
```

---

## 10. Notebook 提交與執行流程（Notebook Execution Sequence）

```mermaid
sequenceDiagram
    autonumber
    participant U as 使用者
    participant FE as web-ui (NB module)
    participant ME as Monaco Editor
    participant API as Job Scheduler
    participant DB as SQLite
    participant WK as GPU Worker

    Note over U,WK: ─── 開啟 Notebook 頁籤 ───
    U->>FE: 點擊 Notebook 子頁籤
    FE->>API: GET /api/v1/notebooks/mine
    API->>DB: SELECT notebooks WHERE user_id=?
    DB-->>API: cells + environment
    API-->>FE: {cells, environment, updated_at}
    FE->>ME: 為每格初始化 Monaco
    FE->>API: GET /api/v1/notebooks/nodes
    API->>DB: SELECT worker_heartbeats<br/>WHERE last_seen > now-90s
    DB-->>API: 在線節點清單
    API-->>FE: nodes[]
    FE->>FE: 填充 GPU 下拉選單

    Note over U,WK: ─── 編輯與自動儲存 ───
    U->>ME: 輸入程式碼
    ME->>FE: onChange event
    FE->>FE: debounce 2s
    FE->>API: PUT /api/v1/notebooks/mine<br/>{cells, environment}
    API->>DB: upsert notebooks
    API-->>FE: {status: ok}
    FE->>U: "已儲存 ✓"

    Note over U,WK: ─── Run All 執行 ───
    U->>FE: 點擊 "▶ Run All"
    FE->>FE: _compile()<br/>code→python heredoc<br/>shell→inline bash
    FE->>API: POST /api/v1/jobs<br/>{docker_image, inline_code,<br/>preferred_node, ...}
    API->>DB: INSERT training_jobs (status=pending)
    API-->>FE: {job_id}
    FE->>API: GET /api/v1/jobs/:id/stream<br/>(SSE)

    Note over U,WK: ─── GPU Worker 領取 ───
    WK->>API: POST /worker/take
    API->>DB: 原子搶佔 + preferred_node 過濾
    API-->>WK: {job_id, inline_code, docker_image}
    WK->>WK: 寫入 run.sh
    WK->>WK: docker run image bash run.sh
    loop 訓練中
        WK-->>API: PUT /worker/jobs/:id/update {log, progress}
        API-->>FE: SSE event: log / progress
        FE->>U: 更新輸出面板 + 進度條
    end
    WK-->>API: PUT /worker/jobs/:id/update {status: completed}
    API-->>FE: SSE: completed → 關閉串流
```

---

## 11. 訓練任務狀態機（Job State Machine）

```mermaid
stateDiagram-v2
    [*] --> pending: 使用者提交<br/>POST /api/v1/jobs
    pending --> queued: scheduler 排序<br/>(priority + created_at)
    queued --> running: Worker 原子搶佔<br/>POST /worker/take
    running --> completed: 容器 exit 0<br/>output_path 已存
    running --> failed: 容器 exit ≠ 0<br/>或例外
    running --> cancelled: admin 強制取消<br/>POST /admin/jobs/:id/cancel
    pending --> cancelled: 使用者取消<br/>DELETE /api/v1/jobs/:id
    queued --> cancelled: 使用者取消
    running --> failed: scheduler 超時清理<br/>(每 5 分檢查 > 120 分鐘)
    completed --> [*]
    failed --> [*]
    cancelled --> [*]
```

---

## 12. 類別關聯圖（Class Diagram – Backend Modules）

```mermaid
classDiagram
    class FastAPIApp {
        +include_router()
        +on_startup()
        +on_shutdown()
    }

    class Settings {
        +DATABASE_PATH
        +JWT_SECRET_KEY
        +WORKER_API_TOKEN
        +PORTKEY_URL
    }

    class Database {
        +SessionLocal
        +engine
        +Base
        +get_db()
    }

    class CRUD {
        +get_user()
        +create_job()
        +get_pending_jobs()
        +get_notebook()
        +save_notebook()
        +upsert_worker_heartbeat()
        +get_online_worker_nodes()
    }

    class Auth {
        +create_access_token()
        +get_current_user()
        +require_admin()
        +verify_password()
    }

    class Scheduler {
        +cleanup_timeout_jobs()
        +run_every_5_min()
    }

    class RouterAuth
    class RouterJobs
    class RouterWorker
    class RouterChat
    class RouterAdmin
    class RouterNotebooks
    class RouterDatasets
    class RouterSystem
    class RouterSSO

    class User {
        +id, username, email
        +role, is_active
    }
    class TrainingJob {
        +id, status, priority
        +docker_image, inline_code
        +entry_args, preferred_node
    }
    class Notebook {
        +id, user_id
        +cells, environment
    }
    class WorkerHeartbeat {
        +node_id, available_gpus
        +last_seen
    }

    FastAPIApp --> Settings : reads
    FastAPIApp --> Database : initializes
    FastAPIApp --> RouterAuth : mounts
    FastAPIApp --> RouterJobs : mounts
    FastAPIApp --> RouterWorker : mounts
    FastAPIApp --> RouterChat : mounts
    FastAPIApp --> RouterAdmin : mounts
    FastAPIApp --> RouterNotebooks : mounts
    FastAPIApp --> RouterDatasets : mounts
    FastAPIApp --> RouterSystem : mounts
    FastAPIApp --> RouterSSO : mounts
    FastAPIApp --> Scheduler : starts

    RouterAuth --> CRUD
    RouterJobs --> CRUD
    RouterWorker --> CRUD
    RouterChat --> CRUD
    RouterAdmin --> CRUD
    RouterNotebooks --> CRUD

    RouterAuth ..> Auth : uses
    RouterJobs ..> Auth : uses
    RouterAdmin ..> Auth : require_admin
    RouterNotebooks ..> Auth : uses

    CRUD --> Database : Session
    CRUD --> User : ORM
    CRUD --> TrainingJob : ORM
    CRUD --> Notebook : ORM
    CRUD --> WorkerHeartbeat : ORM

    Scheduler --> Database : Session
    Scheduler --> TrainingJob : timeout
```

---

## 渲染建議 | Rendering Tips

- **GitHub**：直接開啟 `.md` 即可自動渲染 Mermaid。
- **VS Code**：安裝 `Markdown Preview Mermaid Support` 擴充套件。
- **Obsidian**：原生支援。
- **匯出 PNG/SVG**：
  ```bash
  npx -p @mermaid-js/mermaid-cli mmdc -i ARCHITECTURE-MERMAID.md -o out.png
  ```
- **線上編輯**：複製單一程式碼區塊至 [Mermaid Live Editor](https://mermaid.live/)。
