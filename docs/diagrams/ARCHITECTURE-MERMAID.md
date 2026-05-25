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

    subgraph EXTIDP["外部 Identity Provider (v2.1 OIDC)"]
        MS[("Microsoft Entra ID<br/>login.microsoftonline.com<br/>tenant_id: ...")]
    end

    subgraph L2["第二層：服務層 (Ubuntu Server)"]
        direction TB
        NGX["Nginx :80 / :8888<br/>反向代理 API Gateway"]
        FA["Job Scheduler<br/>FastAPI :8002"]
        DB[("SQLite DB<br/>/data/ai_platform.db")]
        PKG["Portkey LLM Gateway :8000"]
        OL["Ollama :11434<br/>(本地模型)"]
        OWUI["Open WebUI :3000<br/>(備用)"]
        SCH["scheduler.py<br/>(超時清理 + lab 巡檢 +<br/>storage 生命週期)"]
        LM["lab_manager<br/>(Docker SDK)"]
        CS["code-server 容器群<br/>cs-{user_id} (per-user)"]
    end

    subgraph L3["第三層：GPU 高階伺服器 (Windows 11 + WSL2)"]
        direction TB
        WK["gpu-worker/worker.py<br/>(Docker 容器)"]
        NV["nvidia-smi<br/>GPU 偵測"]
        DC["docker run<br/>動態建立訓練容器"]
        STG["per-user volume +<br/>shared_models (read-only)"]
    end

    U -->|"HTTP/SSE<br/>Port 80"| NGX
    U -->|"v2.1 OIDC<br/>302 跳轉"| MS
    MS -->|"302 回 callback<br/>?code=&state="| NGX
    NGX -->|"/train/*"| WebFE["web-ui SPA"]
    NGX -->|"/admin-ui/*"| AdmFE["admin-ui SPA"]
    NGX -->|"/api/v1/*"| FA
    NGX -->|"/code/{user_id}/<br/>+ auth_request"| CS
    FA <-->|"ORM"| DB
    FA -->|"SSE 代理"| PKG
    PKG --> OL
    PKG -->|"API"| EXT["Anthropic / OpenAI / Google"]
    OWUI -.->|"備用入口"| PKG
    SCH --> DB
    FA --> LM
    LM -->|"docker run / stop"| CS

    WK -->|"每 5s POST /worker/take"| FA
    WK -->|"每 30s POST /worker/heartbeat"| FA
    WK -->|"PUT /worker/jobs/{id}/update"| FA
    WK --> NV
    WK --> DC
    DC -->|"--gpus device=N<br/>+ -e secrets + -v volumes"| STG

    classDef l1 fill:#dae8fc,stroke:#6c8ebf
    classDef l2 fill:#d5e8d4,stroke:#82b366
    classDef l3 fill:#ffe6cc,stroke:#d79b00
    classDef ext fill:#fff2cc,stroke:#d6b656
    class U l1
    class NGX,FA,DB,PKG,OL,OWUI,SCH,WebFE,AdmFE,LM,CS l2
    class WK,NV,DC,STG l3
    class MS,EXT ext
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
        N6["cs-{user_id}<br/>(v2.0 動態建立, code-server)"]
    end

    subgraph Vols["Docker Volumes"]
        V1[("./data → /data<br/>SQLite + datasets")]
        V2[("./infrastructure/nginx.conf :ro")]
        V3[("./web-ui /usr/share/nginx/html/train")]
        V4[("./admin-ui /usr/share/nginx/html/admin-ui")]
        V5[("open-webui-data")]
        V6[("ollama-data")]
        V7[("./portkey/config.yaml")]
        V8[("home_{user_id}<br/>(v2.0 per-user, 永久保留)")]
        V9[("shared_models<br/>(v2.0 唯讀共享 HF 快取)")]
        V10[("docker.sock<br/>(v2.0 lab_manager 用)")]
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
    N2 --> V10
    N5 --> V5
    N4 --> V6
    N3 --> V7
    N6 --> V8
    N6 --> V9

    N1 -. "depends_on" .-> N2
    N5 -. "depends_on" .-> N3
    N3 -. "depends_on" .-> N4
    N2 -. "v2.0 lab_manager 建立" .-> N6

    Host(["🖥️ Host: Ubuntu / Windows"]) -->|":80"| N1
    Host -->|":8888 Admin"| N1
    Host -->|":3000 Open WebUI"| N5

    classDef v2 fill:#fff2cc,stroke:#d6b656
    class N6,V8,V9,V10 v2
```

---

## 4. 資料庫 ER 圖（Database ER）

```mermaid
erDiagram
    USERS ||--o| TOKEN_USAGE : has
    USERS ||--o{ TRAINING_JOBS : submits
    USERS ||--o{ CHAT_HISTORY : owns
    USERS ||--o{ MODELS : uploads
    USERS ||--o| LAB_SESSIONS : has
    USERS ||--o{ USER_SECRETS : owns
    USERS ||--o{ QUOTA_GRANTS : receives
    USERS ||--o| USER_STORAGE_STATE : has
    USERS ||--o{ ADMIN_ACTIONS : performs
    USERS ||--o{ USER_SESSION_USAGE : tracks

    USERS {
        string  id PK "UUID"
        string  username UK
        string  email UK
        string  hashed_password "SSO 使用者為隨機值"
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
        int     disk_quota_gb "v2.0 Lab 配額"
        string  auth_source "v2.1: local/sso_mock/sso_cas/sso_oidc"
        string  external_id "v2.1: OIDC oid (Microsoft 永久 ID)"
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
        string  docker_image "v2.0 Lab 用"
        text    inline_code "v2.0 Lab compile 後的 shell script"
        text    entry_args "v2.0 Lab 自訂入口 JSON 陣列"
        string  preferred_node "v2.0 Lab GPU 親和性"
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
        string  pool_type "v2.0 Lab: batch/interactive"
    }

    LAB_SESSIONS {
        string  user_id PK "FK CASCADE"
        string  session_name PK "v2.0: default; v2.1 預留多 session"
        string  container_id
        string  container_name "cs-{user_id}"
        string  status "stopped/starting/running/stopping"
        string  volume_name "home_{user_id}"
        string  base_image
        datetime last_activity
        datetime started_at
        float   cpu_quota
        int     mem_quota_mb
    }

    USER_SECRETS {
        string  id PK
        string  user_id FK "CASCADE"
        string  name "env var name (e.g. HF_TOKEN)"
        blob    value_enc "AES-256-GCM 加密"
        datetime created_at
        datetime updated_at
    }

    QUOTA_GRANTS {
        string  id PK
        string  user_id FK "CASCADE"
        int     extra_quota_gb
        string  granted_by FK "admin user id"
        text    reason "≥5 字審計用"
        datetime granted_at
        datetime expires_at
        datetime revoked_at
    }

    USER_STORAGE_STATE {
        string  user_id PK "FK CASCADE"
        string  state "active/frozen/archived/pending_delete"
        datetime state_since
        float   current_size_gb
        string  archive_path "歸檔後 HDD 路徑"
        text    notes
    }

    ADMIN_ACTIONS {
        string  id PK
        string  admin_id FK
        string  target_user FK "nullable"
        string  action "grant_quota/freeze/archive/.../delete"
        text    payload "JSON"
        datetime timestamp
        string  ip_address
    }

    USER_SESSION_USAGE {
        string  user_id PK "FK CASCADE"
        date    date PK
        int     total_seconds
        int     session_count
    }
```

> **Phase E 移除**：v1 NOTEBOOKS 表已於 2026-05 Phase E 隨 v2.0 Lab 上線同時 DROP（training_jobs 的 4 個 Notebook 欄位保留供 Lab Run on GPU 使用）。

---

## 5. API 端點地圖（API Endpoint Map）

```mermaid
flowchart LR
    API(("/api/v1"))

    API --> AuthGrp["auth/"]
    AuthGrp --> A1["POST /login"]
    AuthGrp --> A2["POST /register"]
    AuthGrp --> A3["GET /me"]
    AuthGrp --> A4["PUT /me<br/>(SSO 改密碼拒絕)"]
    AuthGrp --> A5["GET /usage"]
    AuthGrp --> A6["POST /logout"]
    AuthGrp --> A7["POST /forgot-password"]

    API --> SSOGrp["sso/<br/>(Mock / CAS / OIDC)"]
    SSOGrp --> SS1["GET /login<br/>主 provider 跳轉"]
    SSOGrp --> SS2["GET /callback<br/>CAS / Mock"]
    SSOGrp --> SS3["GET /mock-login (HTML)"]
    SSOGrp --> SS4["POST /mock-submit"]
    SSOGrp --> SS5["GET /oidc/login<br/>v2.1 跳 Microsoft"]
    SSOGrp --> SS6["GET /oidc/callback<br/>v2.1 code→id_token"]
    SSOGrp --> SS7["GET /providers<br/>v2.1 前端用"]
    SSOGrp --> SS8["GET /password-change-info<br/>v2.1 密碼變更分流"]

    API --> JobsGrp["jobs/"]
    JobsGrp --> J1["POST / (含 inline_code)"]
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

    API --> LabGrp["lab/<br/>v2.0 code-server"]
    LabGrp --> L1["POST /start<br/>(限速 5/min)"]
    LabGrp --> L2["POST /stop"]
    LabGrp --> L3["GET /status"]
    LabGrp --> L4["POST /heartbeat<br/>(extension 每 5 分)"]
    LabGrp --> L5["GET /nodes<br/>(依 pool_type 篩選)"]
    LabGrp --> L6["GET /_authz<br/>(nginx auth_request)"]

    API --> SecGrp["secrets/<br/>v2.0 AES-256-GCM"]
    SecGrp --> SC1["GET /<br/>(masked, 永不回 plaintext)"]
    SecGrp --> SC2["PUT /:name"]
    SecGrp --> SC3["DELETE /:name"]

    API --> WkGrp["worker/<br/>Bearer Token"]
    WkGrp --> W1["POST /take<br/>(注入 secrets + volumes)"]
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
    AdmGrp --> AD11["models GET/POST/PUT/DELETE"]
    AdmGrp --> AD12["GET /cluster/stats"]
    AdmGrp --> AD13["GET /analytics"]

    AdmGrp --> AD20["v2.0 Quota:<br/>POST /quota/grant<br/>DELETE /quota/grant/:id<br/>GET /quota/:user_id"]
    AdmGrp --> AD21["v2.0 Storage:<br/>POST /storage/freeze<br/>POST /storage/archive<br/>POST /storage/restore<br/>POST /storage/permanent-delete<br/>GET /storage/states"]
    AdmGrp --> AD22["v2.0 Lab:<br/>GET /lab/sessions<br/>POST /lab/sessions/:id/force-stop"]
    AdmGrp --> AD23["v2.0 Secrets 監控:<br/>GET /secrets/:user_id/names<br/>DELETE /secrets/:user_id/:name"]
    AdmGrp --> AD24["v2.0 Audit:<br/>GET /audit"]

    classDef v2 fill:#fff2cc,stroke:#d6b656
    classDef v21 fill:#ffe6e6,stroke:#cc6666
    class LabGrp,L1,L2,L3,L4,L5,L6,SecGrp,SC1,SC2,SC3,AD20,AD21,AD22,AD23,AD24 v2
    class SS5,SS6,SS7,SS8 v21
```

> **Phase E 移除**：v1 `notebooks/` 端點群（`GET/PUT /mine`、`GET /nodes`）已於 2026-05 隨 v2.0 Lab 上線同時下線。

---

## 6. 前端模組與頁面導覽（Frontend Navigation）

```mermaid
flowchart TB
    Start([使用者開啟瀏覽器]) --> UI{進哪個 UI?}
    UI -->|"port 80<br/>(學生 / 老師)"| Login[#login-view<br/>登入頁]
    UI -->|"port 8888<br/>(管理員)"| AdminLogin["admin-ui<br/>username + password<br/>(緊急救援用)"]

    Login --> Providers{"fetch /sso/providers<br/>看 OIDC 啟用?"}
    Providers -->|"啟用"| OIDCBtn["#sso-section<br/>「使用學校帳號登入」"]
    Providers -->|"PENDING / 未啟用"| Pending["#sso-pending<br/>「系統登入功能尚在設定中」"]

    OIDCBtn -->|"點按鈕"| MS["302 → Microsoft<br/>login.microsoftonline.com"]
    MS -->|"認證成功"| Callback["302 → /api/v1/sso/oidc/callback<br/>?code=...&state=..."]
    Callback -->|"驗 state + 換 token + 建 user"| Redirect["302 → /?sso_token=JWT"]
    Redirect --> Tut{首次登入?}

    AdminLogin --> Tut
    Tut -->|Yes| Tutorial[Welcome 教學面板]
    Tut -->|No| Compute
    Tutorial --> Compute

    Compute[#compute-page<br/>運算任務]
    Compute --> Tab1[High 高算力表單]
    Compute --> Tab2[Mid/Low 中低算力表單]
    Compute --> Tab3["Notebook 子頁籤<br/>(v2.0 Lab launcher)"]
    Tab3 --> Lab1["選擇 base image"]
    Tab3 --> Lab2["「開啟 Notebook」按鈕"]
    Lab2 -->|"POST /lab/start"| Lab3["新分頁開啟 /code/{user_id}/<br/>code-server (VS Code in Browser)"]
    Lab3 --> Lab4["AI Base extension:<br/>Run on GPU / Pick Node / Pick Framework"]

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
    Settings --> ST6["Secrets 管理 (v2.0)"]
    Settings --> ST7["變更密碼<br/>(v2.1 依 auth_source 分流)"]
    ST7 --> ST7a{auth_source?}
    ST7a -->|"local"| ST7b["顯示密碼表單"]
    ST7a -->|"sso_oidc"| ST7c["顯示 Microsoft 連結 +<br/>「為什麼不能在這裡改」"]
    Settings --> ST8[Logout 只清 localStorage]

    Compute -->|"admin role"| AdminUI["/admin-ui/<br/>(獨立 SPA :8888)"]
    AdminUI --> AU1[使用者管理]
    AdminUI --> AU2[模型管理]
    AdminUI --> AU3[全域任務排程]
    AdminUI --> AU4[設定檔編輯]
    AdminUI --> AU5[數據分析]
    AdminUI --> AU6[叢集 GPU 狀態]
    AdminUI --> AU7["v2.0 Lab 管理:<br/>Sessions / Quota / Storage /<br/>Audit / Secrets 監控"]

    classDef v2 fill:#fff2cc,stroke:#d6b656
    classDef v21 fill:#ffe6e6,stroke:#cc6666
    class Tab3,Lab1,Lab2,Lab3,Lab4,ST6,AU7 v2
    class Providers,OIDCBtn,Pending,MS,Callback,Redirect,ST7,ST7a,ST7b,ST7c v21
```

---

## 7. 使用者角色 RBAC（Role-Based Access Control + Auth Source）

```mermaid
flowchart TB
    subgraph Roles["3 種 role（資源權限）"]
        S["👨‍🎓 student<br/>學生"]
        T["👨‍🏫 teacher<br/>教師"]
        A["👑 admin<br/>管理員"]
    end

    subgraph Sources["4 種 auth_source（v2.1 — 認證來源）"]
        AS1["🏫 local<br/>本機 username+password<br/>(admin 緊急救援)"]
        AS2["🔬 sso_mock<br/>dev 測試帳號<br/>(yaml hardcoded)"]
        AS3["🎓 sso_cas<br/>學校 CAS server<br/>(MCU 未用)"]
        AS4["🪟 sso_oidc<br/>Microsoft Entra ID<br/>(MCU 主用)"]
    end

    subgraph Perms["資源權限矩陣"]
        P1["看自己 jobs"]
        P2["看所有人 jobs<br/>(teacher+admin)"]
        P3["取消他人 job<br/>(僅 admin)"]
        P4["管理 user / model / 配額<br/>(僅 admin)"]
        P5["啟動 Lab session"]
        P6["管理 secrets"]
    end

    S --> P1
    S --> P5
    S --> P6
    T --> P1
    T --> P2
    T --> P5
    T --> P6
    A --> P1
    A --> P2
    A --> P3
    A --> P4
    A --> P5
    A --> P6

    AS1 -.->|"可改本機密碼<br/>PUT /me {password}"| P1
    AS2 -.->|"不可改密碼<br/>(隨機 hash, 無人知道)"| P1
    AS3 -.->|"密碼變更去 CAS server"| P1
    AS4 -.->|"密碼變更去 Microsoft<br/>(IdP 統一管理)"| P1

    subgraph Combos["典型組合"]
        C1["MCU 學生 = student + sso_oidc"]
        C2["MCU 教師 = teacher + sso_oidc<br/>(role 由 admin 手動提升)"]
        C3["系統 admin = admin + local<br/>(用 port 8888 緊急救援)"]
        C4["Dev 測試 = student + sso_mock<br/>(yaml T1090001 等)"]
    end

    classDef v21 fill:#ffe6e6,stroke:#cc6666
    class AS1,AS2,AS3,AS4,Sources,Combos v21
```

---

## 8. 使用者認證流程（Auth Sequence）

```mermaid
sequenceDiagram
    autonumber
    participant U as 使用者瀏覽器
    participant W as web-ui (port 80)
    participant AU as admin-ui (port 8888)
    participant N as Nginx
    participant API as FastAPI
    participant DB as SQLite
    participant MS as Microsoft Entra

    Note over U,MS: ─── v2.1 主路徑：OIDC（學生 / 老師） ───
    U->>W: 開啟登入頁
    W->>API: GET /api/v1/sso/providers
    API-->>W: {"providers": ["oidc"]}
    W->>U: 顯示「使用學校帳號登入」按鈕
    U->>W: 點按鈕
    W->>API: GET /api/v1/sso/oidc/login
    API->>API: OIDCSSOClient._sign_state()<br/>(HMAC + timestamp)
    API-->>U: 302 to Microsoft<br/>?client_id=...&state=...
    U->>MS: 學號@mcu.edu.tw + 密碼 + MFA
    MS-->>U: 302 to /api/v1/sso/oidc/callback<br/>?code=...&state=...
    U->>API: GET /oidc/callback
    API->>API: verify_state() 防 CSRF
    API->>MS: POST /token (用 code 換)
    MS-->>API: {id_token: JWT, ...}
    API->>API: jwt.get_unverified_claims()<br/>取出 email/name/oid
    API->>DB: get_user_by_external_id(oid)<br/>→ email → username
    alt 首次登入
        API->>DB: create_sso_user(<br/>auth_source=sso_oidc,<br/>external_id=oid)
    else 既有 local 帳號
        API->>DB: upgrade_to_sso(<br/>auth_source=sso_oidc)
    end
    API->>API: create_access_token({sub, role})
    API-->>U: 302 to /?sso_token=...
    U->>W: setupSSOLogin IIFE 解析<br/>localStorage.setItem(token)
    W->>W: 進 dashboard

    Note over U,MS: ─── v2.1 admin 路徑：port 8888 本機登入（緊急救援） ───
    U->>AU: 開啟 :8888 登入頁
    U->>AU: 輸入 admin username + password
    AU->>API: POST /api/v1/auth/login (form data)
    API->>DB: SELECT user, bcrypt.verify(pwd)
    API->>DB: UPDATE last_login_*
    API-->>AU: {access_token}
    AU->>AU: localStorage.admin_hud_token

    Note over U,MS: ─── 受保護端點存取（兩條路徑都用 JWT） ───
    U->>W: 開啟 /compute-page
    W->>API: GET /api/v1/jobs<br/>Authorization: Bearer JWT
    API->>API: jwt.decode + 驗簽
    API->>DB: SELECT jobs WHERE user_id=?
    DB-->>API: jobs[]
    API-->>W: JSON

    Note over U,MS: ─── 密碼變更（v2.1 依 auth_source 分流） ───
    U->>W: 點「變更密碼」
    W->>API: GET /api/v1/sso/password-change-info
    API-->>W: {providers: {sso_oidc: {change_url, reset_url, message}}}
    alt auth_source = local
        W->>U: 顯示 #password-change-form
        U->>W: 輸入新密碼
        W->>API: PUT /me {password: ...}
        API-->>W: 200 OK
    else auth_source = sso_*
        W->>U: 顯示 IdP 連結 + 「為什麼不能在這裡改」
        Note over U: 點連結到 Microsoft 變更
    end
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

## 10. v2.0 Lab 啟動與 Run on GPU 流程（Lab Execution Sequence）

```mermaid
sequenceDiagram
    autonumber
    participant U as 使用者
    participant FE as web-ui (Lab launcher)
    participant API as Job Scheduler
    participant LM as lab_manager
    participant CS as code-server 容器
    participant EXT as aibase-runner extension
    participant DB as SQLite
    participant WK as GPU Worker
    participant DK as Docker

    Note over U,DK: ─── 1. 開啟 Notebook（啟動 code-server） ───
    U->>FE: 點「開啟 Notebook」+ 選 image
    FE->>API: POST /api/v1/lab/start<br/>{base_image}
    API->>LM: CodeServerLifecycle.start()
    LM->>DK: docker run --name cs-{user_id}<br/>-v home_{user_id}:/home/coder<br/>-v shared_models:/opt/models:ro<br/>-e AIBASE_JWT_TOKEN={JWT}
    DK-->>LM: container_id
    LM->>DB: upsert lab_sessions
    API-->>FE: {status: starting, code_url}
    FE->>U: 新分頁開 /code/{user_id}/

    Note over U,DK: ─── 2. code-server 內編輯 + Extension 啟動 ───
    U->>CS: VS Code 開啟
    CS->>EXT: activate aibase-runner
    EXT->>EXT: 從 env AIBASE_JWT_TOKEN 取 token
    loop 每 5 分鐘
        EXT->>API: POST /api/v1/lab/heartbeat
        API->>DB: 更新 lab_sessions.last_activity
    end

    Note over U,DK: ─── 3. Run on GPU（右鍵或 Notebook cell） ───
    U->>CS: 右鍵 .py / Notebook cell
    CS->>EXT: 觸發「AI Base: Run on GPU」
    EXT->>EXT: compileInlineCode()<br/>(Python heredoc + Shell inline)
    EXT->>API: POST /api/v1/jobs<br/>{docker_image, inline_code, preferred_node}
    API->>DB: INSERT training_jobs (pending)
    API-->>EXT: {job_id}
    EXT->>API: GET /api/v1/jobs/:id/stream (SSE)

    Note over U,DK: ─── 4. GPU Worker 領取並執行 ───
    WK->>API: POST /worker/take
    API->>DB: 原子搶佔 + preferred_node 過濾
    API->>API: 注入該 user 的 secrets (env) +<br/>per-user volume + shared_models
    API-->>WK: {job_id, inline_code, docker_image,<br/>extra_env: {HF_TOKEN, ...},<br/>volume_mounts: [...]}
    WK->>WK: 寫 /tmp/job_{id}/run.sh
    WK->>DK: docker run --gpus device=N<br/>-v home_{user}:/home/coder<br/>-v shared_models:/opt/models:ro<br/>-e HF_TOKEN=*** image bash run.sh
    loop 訓練中
        DK-->>WK: 訓練日誌
        WK->>WK: parse_progress() +<br/>mask secret values in log
        WK->>API: PUT /worker/jobs/:id/update
        API-->>EXT: SSE: log + progress
        EXT->>U: VS Code Output Panel 串流顯示
    end
    DK-->>WK: exit code
    WK->>API: PUT /worker/jobs/:id/update {status}
    API-->>EXT: SSE: completed/failed
    EXT->>U: Status bar 顯示結果

    Note over U,DK: ─── 5. Idle 30 分鐘自動關閉（保留 volume） ───
    loop scheduler 每分鐘
        API->>LM: scan_and_evict()
        alt last_activity > 30 min
            LM->>DK: docker stop cs-{user_id}
            LM->>DB: lab_sessions.status = stopped
            Note over LM: home_{user_id} volume 保留，<br/>下次啟動檔案還在
        end
    end
```

> **Phase E 移除**：v1 `notebooks/mine` 自動儲存流程已隨 Lab launcher 上線同時下線。

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
        +SECRETS_MASTER_KEY (v2.0)
        +PORTKEY_URL
    }

    class OIDCConfig {
        +OIDC_ENABLED (v2.1 flag)
        +SSO_POLICY (yaml)
    }

    class Database {
        +SessionLocal
        +engine
        +Base
        +get_db()
    }

    class CRUD {
        +get_user()
        +create_user()
        +create_sso_user(auth_source, external_id)
        +update_user (v2.1 SSO 拒絕)
        +get_user_by_external_id (v2.1)
        +upgrade_to_sso (v2.1)
        +create_job()
        +get_pending_jobs()
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
        +scan_lab_sessions (v2.0)
        +storage_lifecycle_loop (v2.0)
    }

    class BaseSSOClient {
        <<abstract>>
        +get_login_url()
        +validate_ticket(ticket)
    }
    class MockSSOClient {
        +validate_ticket → auth_source=sso_mock
    }
    class CASSSOClient {
        +validate_ticket → auth_source=sso_cas
    }
    class OIDCSSOClient {
        +tenant_id, client_id, redirect_uri
        +get_login_url() with state
        +validate_ticket(code) → id_token claims
        +_sign_state() HMAC
        +verify_state() 防 CSRF
    }
    BaseSSOClient <|-- MockSSOClient
    BaseSSOClient <|-- CASSSOClient
    BaseSSOClient <|-- OIDCSSOClient

    class LabManager {
        <<v2.0>>
        +start_codeserver()
        +stop_codeserver()
        +scan_and_evict()
    }
    class SecretsService {
        <<v2.0>>
        +encrypt() AES-256-GCM
        +decrypt()
        +inject_to_env(job_id)
    }
    class QuotaService {
        <<v2.0>>
        +grant() with audit
        +revoke()
        +get_effective_quota()
    }
    class StorageLifecycle {
        <<v2.0>>
        +freeze() / archive() / restore()
        +permanent_delete() with admin pwd
    }

    class RouterAuth
    class RouterJobs
    class RouterWorker
    class RouterChat
    class RouterAdmin
    class RouterDatasets
    class RouterSystem
    class RouterSSO {
        +oidc/login (v2.1)
        +oidc/callback (v2.1)
        +providers (v2.1)
        +password-change-info (v2.1)
    }
    class RouterLab {
        <<v2.0>>
        +start/stop/status/heartbeat
        +nodes/_authz
    }
    class RouterSecrets {
        <<v2.0>>
        +GET / PUT / DELETE
    }

    class User {
        +id, username, email
        +role, is_active
        +disk_quota_gb (v2.0)
        +auth_source (v2.1)
        +external_id (v2.1)
    }
    class TrainingJob {
        +id, status, priority
        +docker_image, inline_code
        +entry_args, preferred_node
    }
    class LabSession {
        <<v2.0>>
        +user_id, container_id
        +status, last_activity
    }
    class UserSecret {
        <<v2.0>>
        +user_id, name
        +value_enc (AES)
    }
    class WorkerHeartbeat {
        +node_id, available_gpus
        +pool_type (v2.0)
    }

    FastAPIApp --> Settings : reads
    FastAPIApp --> OIDCConfig : derives flag
    FastAPIApp --> Database : initializes
    FastAPIApp --> RouterAuth : mounts
    FastAPIApp --> RouterJobs : mounts
    FastAPIApp --> RouterWorker : mounts
    FastAPIApp --> RouterChat : mounts
    FastAPIApp --> RouterAdmin : mounts
    FastAPIApp --> RouterDatasets : mounts
    FastAPIApp --> RouterSystem : mounts
    FastAPIApp --> RouterSSO : mounts
    FastAPIApp --> RouterLab : mounts (v2.0)
    FastAPIApp --> RouterSecrets : mounts (v2.0)
    FastAPIApp --> Scheduler : starts

    RouterAuth --> CRUD
    RouterJobs --> CRUD
    RouterWorker --> CRUD
    RouterWorker --> SecretsService : inject env (v2.0)
    RouterChat --> CRUD
    RouterAdmin --> CRUD
    RouterAdmin --> QuotaService
    RouterAdmin --> StorageLifecycle
    RouterAdmin --> LabManager
    RouterSSO --> BaseSSOClient : uses
    RouterSSO --> CRUD : create_sso_user
    RouterLab --> LabManager
    RouterSecrets --> SecretsService

    RouterAuth ..> Auth : uses
    RouterJobs ..> Auth : uses
    RouterAdmin ..> Auth : require_admin
    RouterLab ..> Auth : uses
    RouterSecrets ..> Auth : uses

    CRUD --> Database : Session
    CRUD --> User : ORM
    CRUD --> TrainingJob : ORM
    CRUD --> LabSession : ORM (v2.0)
    CRUD --> UserSecret : ORM (v2.0)
    CRUD --> WorkerHeartbeat : ORM

    Scheduler --> Database : Session
    Scheduler --> TrainingJob : timeout
    Scheduler --> LabManager : scan_and_evict (v2.0)
    Scheduler --> StorageLifecycle : daily 03:00 (v2.0)
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
