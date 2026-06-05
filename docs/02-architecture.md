# 02 — 系統架構 | Architecture

三層分離設計：**工作站 → 服務層 → GPU 高階伺服器**。本文件全面以 **Mermaid** 繪製（GitHub / VS Code「Markdown Preview Mermaid Support」/ Obsidian 皆可直接渲染）。

> **v2.4 更新**：對齊實際部署 — Portkey OSS 監聽 **:8787**（header 路由、Ollama 經 `x-portkey-custom-host`）、新增**動態模型清單**模組（`/api/v1/models` + `Model.tool_types`）、**文書簡報 agent**（`agent_dispatcher` + `document_generator`）、**Lab 就緒偵測**、**GPU per-card telemetry**。新增 §1.5「服務層模組分布與交互」總覽各模組與互動。本機完整部署步驟見 [`00-本機完整部署指南.md`](00-本機完整部署指南.md)。

---

## 1. 整體架構（三層）

> 三層以 L1/L2/L3 subgraph 區隔；拆除前端 SPA / LLM 推理的巢狀內框（巢狀框邊界正是連線橫越主因），群組資訊改寫進節點名稱，並精簡連線標籤避免浮動標籤壓住節點。

```mermaid
flowchart TB
    subgraph L1["第一層：使用者端 Browser"]
        U[("👤 使用者瀏覽器")]
    end

    subgraph L2["第二層：服務層 Ubuntu Server"]
        direction TB
        NGX["Nginx :80 / :8888<br/>反向代理 / API Gateway"]
        WebFE["web-ui SPA · /train/*"]
        AdmFE["admin-ui SPA · /admin-ui/*"]
        FA["Job Scheduler<br/>FastAPI :8002"]
        SCH["scheduler.py<br/>背景排程"]
        DB[("SQLite DB<br/>ai_platform.db")]
        PKG["Portkey Gateway :8787<br/>LLM 閘道 (header 路由)"]
        OL["Ollama :11434 (GPU)<br/>本地模型"]
        OWUI["Open WebUI :3000<br/>備用入口"]
        CS["code-server cs-&lt;uid&gt;<br/>per-user Lab 容器 (動態)"]
    end

    subgraph L3["第三層：GPU 高階伺服器 Win11 + WSL2 / Ubuntu"]
        direction TB
        WK["gpu-worker<br/>worker.py"]
        NV["nvidia-smi GPU 偵測"]
        DC["docker run --rm<br/>per-job 隔離容器"]
        STG["共享 volume /workspace"]
    end

    subgraph EXTG["外部 API（選用）"]
        EXT["Anthropic / OpenAI / Google"]
    end

    U -->|HTTP/SSE| NGX
    NGX --> WebFE
    NGX --> AdmFE
    NGX -->|/api/v1/*| FA
    FA --- DB
    SCH --> DB
    FA -->|SSE 代理| PKG
    FA -.->|Docker SDK 啟動/就緒偵測| CS
    NGX -->|/code/&lt;uid&gt;/ auth_request 代理| CS
    PKG -->|custom-host| OL
    PKG -.->|選用| EXT
    OWUI -.->|備用| PKG

    WK -->|輪詢 + 心跳 + GPU telemetry| FA
    WK --> NV
    WK --> DC
    DC -->|--gpus device=N| STG

    classDef l1 fill:#dae8fc,stroke:#6c8ebf
    classDef l2 fill:#d5e8d4,stroke:#82b366
    classDef l3 fill:#ffe6cc,stroke:#d79b00
    classDef ext fill:#f8cecc,stroke:#b85450
    class U l1
    class NGX,WebFE,AdmFE,FA,SCH,DB,PKG,OL,OWUI,CS l2
    class EXT ext
    class WK,NV,DC,STG l3
```

**關鍵設計**：
- GPU 節點 **Pull**（主動領取）→ 無需開放對外 port、藏在 NAT 後仍可用
- 服務層**沒有**GPU 節點的 SSH 私鑰 → 服務層被駭頂多塞惡意任務、不能登入 GPU 機
- 訓練容器都是 `--rm` → 結束即清空、惡意腳本最多污染 container 不污染 host

---

## 1.5 服務層模組分布與交互（Component Map）

> 服務層（Job Scheduler）內部分層「routers（HTTP 端點）→ services（商業邏輯）→ crud（ORM）→ SQLite」，
> 以及與 AI 推理、GPU 節點、per-user Lab 容器的互動。是「各模組分布與交互」的總覽。

```mermaid
flowchart TB
    subgraph CLI["前端 SPA（Nginx 靜態）"]
        WUI["web-ui<br/>chat · 文書簡報 · Notebook · 設定"]
        AUI["admin-ui<br/>使用者 · 模型 · Lab · 分析"]
    end

    subgraph SCHED["Job Scheduler — FastAPI :8002"]
        direction TB
        subgraph R["routers/ — HTTP 端點"]
            rAuth["auth · sso"]
            rChat["chat (SSE)"]
            rModels["models（動態清單）"]
            rJobs["jobs"]
            rLab["lab"]
            rSec["secrets"]
            rAdmin["admin"]
            rWk["worker (API Token)"]
            rEtc["announcements · datasets · system"]
        end
        subgraph SV["services/ — 商業邏輯"]
            sDisp["agent_dispatcher<br/>簡報 system prompt + 生成契約"]
            sDoc["document_generator<br/>spec → .pptx → put_archive"]
            sLab["lab_manager<br/>code-server 生命週期 + 就緒偵測"]
            sSec["secrets_service<br/>AES-256-GCM"]
            sQuota["quota_service"]
            sStore["storage_lifecycle"]
            sSched["scheduler<br/>背景：超時 / Lab idle / 儲存"]
            sMail["email_service"]
        end
        CRUD["crud — ORM 封裝"]
    end

    DB[("SQLite ai_platform.db<br/>users · models · training_jobs<br/>lab_sessions · chat_history<br/>secrets · worker_heartbeats · …")]

    subgraph AIM["AI 推理 — docker-compose.ai-models"]
        PK["Portkey :8787<br/>(header 路由)"]
        OLL["Ollama :11434 (GPU)"]
        EXTA["外部 API（選用）<br/>Anthropic / OpenAI / Google"]
    end

    subgraph GPUN["GPU 節點 — gpu-worker"]
        WORK["worker.py<br/>pull + nvidia-smi telemetry"]
        TRAIN["訓練容器 --gpus<br/>(aibase/* sibling)"]
    end

    CSV["code-server cs-&lt;uid&gt;<br/>per-user Lab 容器"]

    WUI --> R
    AUI --> R
    R --> CRUD
    CRUD --> DB

    rChat --> sDisp
    sDisp --> sDoc
    rChat -->|x-portkey-custom-host| PK
    sDoc -->|put_archive .pptx| CSV
    rModels --> CRUD
    rLab --> sLab
    sLab -->|Docker SDK run| CSV
    sLab -.->|就緒探測 :8080| CSV
    rSec --> sSec
    rAdmin --> sLab
    rAdmin --> sStore
    rAdmin --> sQuota
    sSched --> CRUD

    PK -->|custom-host| OLL
    PK -.-> EXTA
    WORK -->|/worker/take · /heartbeat| rWk
    WORK -->|docker run --gpus| TRAIN

    classDef fe fill:#dae8fc,stroke:#6c8ebf
    classDef rt fill:#d5e8d4,stroke:#82b366
    classDef sv fill:#fff2cc,stroke:#d6b656
    classDef ext fill:#f8cecc,stroke:#b85450
    class WUI,AUI fe
    class rAuth,rChat,rModels,rJobs,rLab,rSec,rAdmin,rWk,rEtc rt
    class sDisp,sDoc,sLab,sSec,sQuota,sStore,sSched,sMail sv
    class PK,OLL,EXTA,WORK,TRAIN ext
```

**模組職責對照**：

| 層 | 模組 | 職責 |
|---|---|---|
| routers | `chat` | LLM 對話 SSE 代理；偵測 `tool_type` → 走簡報 dispatch |
| routers | `models` | `GET /api/v1/models?tool_type=` 動態回傳「公開且適用該工具」的模型 |
| routers | `lab` | 啟動/停止 code-server、`_authz`（給 nginx auth_request）|
| routers | `worker` | GPU 節點 pull 任務、回報進度、心跳 + per-GPU telemetry |
| services | `agent_dispatcher` | 依 tool_type 注入專項 system prompt + 生成契約標記（PPTX_SPEC）|
| services | `document_generator` | AI spec → python-pptx 渲染 → `put_archive` 進 Lab 容器 `/home/coder/outputs/` |
| services | `lab_manager` | code-server 容器生命週期、就緒偵測 `_wait_until_ready`（避免開頁 503）|
| services | `storage_lifecycle` | 使用者儲存 freeze/archive/restore、`list_states` |
| services | `scheduler` | 背景任務：訓練超時清理、Lab idle 驅逐、儲存生命週期掃描 |

---

## 2. 認證流程

平台**三 provider 並存**：`local`（本機帳號）/ `sso_mock` / `sso_cas` / `sso_oidc`（Microsoft Entra ID）。下圖以「本機帳號 + SSO Mock + 受保護端點」為代表；OIDC 另在 IdP 端多一段 302 redirect（見下方說明）。

```mermaid
sequenceDiagram
    autonumber
    participant U as 使用者
    participant W as web-ui
    participant N as Nginx
    participant API as FastAPI
    participant DB as SQLite
    participant SSO as SSO (Mock/CAS/OIDC)

    rect rgb(218, 232, 252)
        Note left of U: ① 本機帳號登入
        U->>W: 輸入帳號 + 密碼
        W->>N: POST /auth/login
        N->>API: 轉發請求
        API->>DB: SELECT user
        DB-->>API: User record
        API->>API: 驗證密碼 + 簽發 JWT
        API->>DB: UPDATE 登入紀錄
        API-->>W: access_token + cookie
    end

    rect rgb(213, 232, 212)
        Note left of U: ② SSO 登入 (Mock/CAS/OIDC)
        U->>W: 點「使用學校帳號登入」
        W->>API: /sso/<provider>/login
        API->>SSO: 導向 IdP
        SSO-->>API: 回呼 code+state
        API->>API: _finalize_sso_login()
        API->>DB: upsert user (新帳號自動建立)
        API-->>W: 簽 JWT + 302 /train/
    end

    rect rgb(255, 230, 204)
        Note left of U: ③ 受保護端點存取
        U->>W: 開啟 /compute-page
        W->>API: GET /jobs (Bearer)
        API->>API: 驗證 JWT 簽章
        API->>DB: SELECT jobs (依角色範圍)
        DB-->>API: jobs[]
        API-->>W: JSON 回應
    end
```

**重點**：
- `auth_source` 欄位區分 4 種：`local` / `sso_mock` / `sso_cas` / `sso_oidc`
- 密碼變更 UI 依 `auth_source` 分流（SSO 帳號改密碼導向 IdP）
- admin 走獨立 port 8888，學生不會發現
- Mock SSO **不曝光於 UI 按鈕**（避免 admin 用別人身分）

### Cookie 用途（v2.1 HttpOnly）

| Token 來源 | 用途 | XSS 風險 |
|---|---|---|
| `localStorage['ai_hud_token']` | SPA `fetch()` 帶 `Authorization: Bearer` | 有，但 fetch 必經 IP/CORS 防護 |
| Cookie `ai_hud_token` (HttpOnly) | 瀏覽器 `window.open('/code/<uid>/')` 由 nginx auth_request 讀 | 無（JS 讀不到） |

---

## 3. v2.0 Lab 啟動流程

```mermaid
sequenceDiagram
    autonumber
    participant U as 使用者
    participant FE as web-ui
    participant API as FastAPI (lab router)
    participant LM as lab_manager
    participant DK as Docker SDK
    participant CS as cs-&lt;uid&gt; (code-server)
    participant NGX as Nginx

    rect rgb(218, 232, 252)
        Note left of U: ① 啟動 Lab
        U->>FE: Notebook 分頁 → 點「開啟 Notebook」
        FE->>API: POST /lab/start {base_image}
        API->>LM: start_session(user_id)
        LM->>LM: 檢查每日配額 (360 min/day)
        LM->>LM: 找/建 LabSession + volume
        LM->>DK: containers.run(name=cs-&lt;uid&gt;)
        DK-->>LM: 容器啟動
        LM-->>API: url + password
        API-->>FE: 200 {url: /code/&lt;uid&gt;/, pwd}
        FE->>U: window.open(url, '_blank')
    end

    rect rgb(213, 232, 212)
        Note left of U: ② 存取 code-server (每次請求)
        U->>NGX: GET /code/&lt;uid&gt;/...
        NGX->>API: auth_request → /lab/_authz
        API-->>NGX: 200 OK 或 401
        NGX->>CS: proxy_pass cs-&lt;uid&gt;:8080
        CS-->>U: VS Code Web UI
    end
```

**Idle 30 分鐘 + 每日 360 分鐘**：scheduler 背景每 60s 掃描 → 自動關 idle session、累計 daily 用量。

---

## 4. 資料庫 ER 圖（核心表）

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
        string  tool_types "v2.4 CSV chat,presentation"
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
        text    gpus_detail "v2.4 per-GPU name/util/temp/mem JSON"
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

## 5. 檔案結構樹

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
    JSApp --> M3["models.py / schemas.py / crud.py"]
    JSApp --> M5["auth.py / sso_client.py"]
    JSApp --> M6["scheduler.py<br/>(背景排程)"]
    JSApp --> Pol["*.yaml<br/>(scheduler/sso policy)"]
    JSApp --> R["routers/"]
    R --> R1["auth.py / sso.py"]
    R --> R2["jobs.py / worker.py"]
    R --> R3["admin.py / system.py"]
    R --> R4["chat.py / datasets.py"]
    R --> R5["lab.py / secrets.py / notebooks.py"]
    JSApp --> Svc["services/<br/>(lab_manager / secrets / quota / email / agent_dispatcher / document_generator)"]

    Root --> GW["gpu-worker/<br/>GPU 節點代理"]
    GW --> GWW["worker.py<br/>(輪詢 + 容器派發)"]

    Root --> INF["infrastructure/<br/>nginx.conf + base-images/"]
    Root --> Data["data/<br/>(SQLite + 上傳檔)"]
    Root --> DocDir["docs/<br/>(8 主檔 + archive)"]
```

---

## 6. Docker 容器網路

```mermaid
flowchart LR
    subgraph Net["ai-platform-net (bridge network)"]
        direction TB
        N1["ai-platform-nginx<br/>:80 / :8888"]
        N2["ai-platform-scheduler<br/>:8002"]
        N3["ai-platform-portkey<br/>:8787"]
        N4["ai-platform-ollama<br/>:11434 (GPU)"]
        N5["ai-platform-webui<br/>(open-webui :3000)"]
        N6["cs-&lt;uid&gt;<br/>per-user Lab (動態, scheduler 經 docker.sock 建)"]
    end

    subgraph Vols["Docker Volumes"]
        V1[("./data → /data<br/>SQLite + datasets")]
        V2[("./infrastructure/nginx.conf")]
        V3[("./web-ui → /train")]
        V4[("./admin-ui → /admin-ui")]
        V5[("open-webui-data")]
        V6[("ollama-data")]
        V7[("./portkey/config.yaml")]
    end

    subgraph Compose["Compose 檔案"]
        C1["docker-compose.yml<br/>(核心)"]
        C2["docker-compose.ai-models.yml<br/>(AI Models)"]
        C3["docker-compose.ai-models.gpu.yml<br/>(Ollama GPU override, 選用)"]
        C4["gpu-worker/docker-compose.yml<br/>(GPU 節點, 獨立)"]
    end

    WK2["mcu-gpu-worker<br/>(host.docker.internal:8002)"]

    C1 --> N1
    C1 --> N2
    C2 --> N3
    C2 --> N4
    C2 --> N5
    C3 -. "GPU 疊加" .-> N4
    C4 --> WK2

    N1 --> V2
    N1 --> V3
    N1 --> V4
    N2 --> V1
    N5 --> V5
    N4 --> V6
    N3 --> V7
    N2 -. "docker.sock 建/管" .-> N6

    N1 -. "depends_on" .-> N2
    N5 -. "depends_on" .-> N3
    N3 -. "depends_on" .-> N4
    WK2 -. "pull/heartbeat" .-> N2

    Host(["🖥️ Host: Ubuntu / Windows + NVIDIA"]) -->|":80"| N1
    Host -->|":8888 Admin"| N1
    Host -->|":3000 Open WebUI"| N5
```

> 注意：`gpu-worker` 為**獨立 compose / 獨立網路**，透過 host 的 `:8002`（同機用 `host.docker.internal`）連服務層；
> 它不在 `ai-platform-net` 內。`cs-<uid>` 由 scheduler 經 `docker.sock` 動態建立並掛 `ai-platform-net`。

---

## 7. API 端點地圖

```mermaid
flowchart LR
    API(("/api/v1"))

    API --> AuthGrp["auth/"]
    AuthGrp --> A1["login / register / me"]
    AuthGrp --> A2["usage / logout / forgot-password"]

    API --> SsoGrp["sso/"]
    SsoGrp --> SS1["oidc login / callback"]
    SsoGrp --> SS2["mock login / providers"]

    API --> JobsGrp["jobs/"]
    JobsGrp --> J1["POST / · GET / · GET /:id"]
    JobsGrp --> J2["DELETE /:id · GET /:id/stream (SSE)"]

    API --> ChatGrp["chat/"]
    ChatGrp --> CH1["POST /completions (SSE)"]
    ChatGrp --> CH2["GET /history"]

    API --> ModelsGrp["models/ (v2.4)"]
    ModelsGrp --> MD1["GET /?tool_type=（動態模型清單）"]

    API --> LabGrp["lab/"]
    LabGrp --> LB1["start / stop / status / heartbeat / _authz"]

    API --> SecGrp["secrets/"]
    SecGrp --> SC1["CRUD (AES-256-GCM)"]

    API --> AnnGrp["announcements/"]
    AnnGrp --> AN1["GET（user）· admin CRUD"]

    API --> WkGrp["worker/<br/>API Token"]
    WkGrp --> W1["take / jobs/:id/update / heartbeat"]

    API --> AdmGrp["admin/<br/>admin only"]
    AdmGrp --> AD1["users CRUD · provision · tokens"]
    AdmGrp --> AD2["jobs · models · cluster/stats · analytics"]
```

完整 endpoint 與範例見 [`05-api-reference.md`](05-api-reference.md)。

| Prefix | 模組 | 認證 |
|---|---|---|
| `/api/v1/auth/*` | 註冊、登入、登出、forgot-password、me、usage | JWT |
| `/api/v1/sso/*` | OIDC login/callback、mock login、providers | 無（callback 後簽 JWT） |
| `/api/v1/jobs/*` | 提交/查/取消 GPU 任務、SSE 進度 | JWT |
| `/api/v1/chat/*` | LLM 對話、聊天歷史、SSE 串流（含 `tool_type` 簡報 dispatch）| JWT |
| `/api/v1/models/*` | **(v2.4)** 依 `tool_type` 動態回傳公開模型清單 | JWT |
| `/api/v1/datasets/*` | 資料集上傳、自動分析 | JWT |
| `/api/v1/lab/*` | 啟動/停止 lab session、status、heartbeat、`_authz`（含就緒偵測）| JWT / cookie |
| `/api/v1/secrets/*` | 使用者 AES-256-GCM secrets CRUD | JWT |
| `/api/v1/announcements/*` | 首頁公告（user 讀）+ admin CRUD | JWT |
| `/api/v1/admin/*` | 使用者管理、配額、模型(tool_types)、storage、lab/sessions、cluster/stats、audit | JWT (admin) |
| `/api/v1/worker/*` | Pull 任務、更新進度、heartbeat | API_TOKEN（與 .env 對齊） |
| `/api/v1/system/*` | 系統設定、健康檢查 | JWT (admin) |

---

## 8. 前端模組與頁面導覽

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
    Compute --> Tab3["Notebook 子頁籤"]
    Tab3 --> NB1[工具列: 框架/模式/GPU]
    Tab3 --> NB3[Cells 容器<br/>code/shell/markdown]
    Tab3 --> NB4[輸出面板<br/>SSE + 進度條]

    Compute --> Assistant[#assistant-page<br/>AI 大廳]
    Assistant --> Hub[AI Hub 卡片]
    Hub -->|"✅ 已實作"| Chat[文字聊天 / 文書簡報]
    Hub -->|"🚫 提案中"| Soon[其餘佔位卡]

    Compute --> Settings[#settings-page<br/>系統設定]
    Settings --> ST1[Token 資源環形]
    Settings --> ST2[Profile / Appearance]
    Settings --> ST4[Localization 中/英 · Tutorial · Logout]

    Compute -->|"admin role"| AdminUI["/admin-ui/<br/>(獨立 SPA :8888)"]
    AdminUI --> AU1[使用者管理]
    AdminUI --> AU2[模型管理 / 全域排程]
    AdminUI --> AU5[數據分析 / 叢集 GPU 狀態]
```

---

## 9. 使用者角色 RBAC

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

## 10. GPU Worker Pull 模式

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
                W->>DK: docker run --rm --gpus device=N<br/>image bash -eu run.sh
                loop 串流 stdout
                    DK-->>W: 訓練日誌
                    W->>W: parse_progress()<br/>(Epoch / step / [N/M] / %)
                    W->>API: POST /worker/jobs/:id/update<br/>{log, progress}
                end
                DK-->>W: exit code
                alt exit == 0
                    W->>API: update {status: completed, output_path}
                else
                    W->>API: update {status: failed, error}
                end
                W->>W: rmtree /tmp/job_{id}
            else 已被別人領走
                API-->>W: {job: null}
            end
        end
    end
```

---

## 11. Notebook 提交與執行流程

```mermaid
sequenceDiagram
    autonumber
    participant U as 使用者
    participant FE as web-ui
    participant ME as Monaco
    participant API as Job Scheduler
    participant DB as SQLite
    participant WK as GPU Worker

    rect rgb(218, 232, 252)
        Note left of U: ① 開啟 Notebook 頁籤
        U->>FE: 點擊 Notebook 子頁籤
        FE->>API: GET /notebooks/mine
        API->>DB: SELECT notebooks
        DB-->>API: cells + environment
        API-->>FE: cells / env / updated_at
        FE->>ME: 初始化 Monaco
        FE->>API: GET /notebooks/nodes
        API->>DB: SELECT 在線節點
        DB-->>API: 節點清單
        API-->>FE: nodes[]
        FE->>FE: 填充 GPU 下拉
    end

    rect rgb(213, 232, 212)
        Note left of U: ② 編輯與自動儲存
        U->>ME: 輸入程式碼
        ME->>FE: onChange
        FE->>FE: debounce 2s
        FE->>API: PUT /notebooks/mine
        API->>DB: upsert notebooks
        API-->>FE: ok
        FE->>U: 顯示「已儲存 ✓」
    end

    rect rgb(255, 242, 204)
        Note left of U: ③ Run All 執行
        U->>FE: 點擊「▶ Run All」
        FE->>FE: _compile() 編譯儲存格
        FE->>API: POST /jobs (image, code)
        API->>DB: INSERT training_jobs
        API-->>FE: job_id
        FE->>API: GET /jobs/:id/stream (SSE)
    end

    rect rgb(255, 230, 204)
        Note left of U: ④ GPU Worker 領取與回報
        WK->>API: POST /worker/take
        API->>DB: 原子搶佔 + 節點過濾
        API-->>WK: job_id / code / image
        WK->>WK: docker run --gpus + bash -c inline_code
        loop 訓練中
            WK-->>API: PUT update (log, progress)
            API-->>FE: SSE: log / progress
            FE->>U: 更新輸出 + 進度條
        end
        WK-->>API: PUT update (completed)
        API-->>FE: SSE: completed
    end
```

---

## 12. 訓練任務狀態機

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

## 13. 後端類別關聯圖

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
        +get_db()
    }
    class CRUD {
        +get_user()
        +create_job()
        +get_pending_jobs()
        +get_notebook()
        +save_notebook()
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
    class RouterModels
    class RouterAdmin
    class RouterLab
    class RouterSecrets

    class AgentDispatcher {
        +is_dispatch_tool()
        +get_agent_config()
    }
    class DocumentGenerator {
        +generate_presentation()
    }
    class LabManager {
        +start_session()
        +_wait_until_ready()
        +list_all_sessions()
        +stop_session()
    }

    class User {
        +id, username, email
        +role, is_active
    }
    class TrainingJob {
        +id, status, priority
        +docker_image, inline_code
        +entry_args, preferred_node
    }
    class Model {
        +id, name, tool_types
        +is_public, api_model_id
    }
    class LabSession {
        +user_id, container_name
        +status, base_image
    }
    class WorkerHeartbeat {
        +node_id, available_gpus
        +gpus_detail, last_seen
    }

    FastAPIApp --> Settings : reads
    FastAPIApp --> Database : initializes
    FastAPIApp --> RouterAuth : mounts
    FastAPIApp --> RouterJobs : mounts
    FastAPIApp --> RouterWorker : mounts
    FastAPIApp --> RouterChat : mounts
    FastAPIApp --> RouterAdmin : mounts
    FastAPIApp --> RouterModels : mounts
    FastAPIApp --> RouterLab : mounts
    FastAPIApp --> RouterSecrets : mounts
    FastAPIApp --> Scheduler : starts

    RouterChat ..> AgentDispatcher : presentation dispatch
    AgentDispatcher ..> DocumentGenerator : spec → pptx
    RouterLab ..> LabManager : 容器生命週期 + 就緒偵測

    RouterAuth --> CRUD
    RouterJobs --> CRUD
    RouterWorker --> CRUD
    RouterModels --> CRUD

    RouterAuth ..> Auth : uses
    RouterJobs ..> Auth : uses
    RouterAdmin ..> Auth : require_admin

    CRUD --> Database : Session
    CRUD --> User : ORM
    CRUD --> TrainingJob : ORM
    CRUD --> Model : ORM
    CRUD --> WorkerHeartbeat : ORM
    LabManager --> LabSession : ORM

    Scheduler --> Database : Session
    Scheduler --> TrainingJob : timeout
```

---

## 14. 安全模型摘要

| 威脅 | 防護 |
|---|---|
| 學生互看別人任務 | JWT 認證 + admin-only 端點 |
| 學生互看別人 Lab 工作目錄 | nginx auth_request 驗 user_id 對應 — ⚠️ v2.1 同網段可繞過，**v2.2 加 per-user network**（見 [`08-status-and-roadmap.md`](08-status-and-roadmap.md)） |
| XSS 偷 token | Cookie `HttpOnly` (v2.1)；不過 localStorage 仍可被 XSS 讀取 |
| Secrets 洩漏 | AES-256-GCM 加密儲存、admin 亦不可讀 plaintext、僅在容器啟動時解密注入 |
| GPU 節點被 SSH 入侵 | 採 Pull 架構、無需開對外 port |
| 服務層被駭 → 橫向移動 | 服務層無 GPU 節點私鑰、最多塞惡意任務（被 `--rm` 容器隔離）|
| 暴力破解 admin | rate limit + emergency-only port 8888 |

---

## 渲染建議 | Rendering Tips

- **GitHub**：直接開啟即可自動渲染 Mermaid。
- **VS Code**：安裝 `Markdown Preview Mermaid Support` 擴充套件。
- **Obsidian**：原生支援。
- **匯出 PNG/SVG**：`npx -p @mermaid-js/mermaid-cli mmdc -i 02-architecture.md -o out.png`
- **線上編輯**：複製單一 ```mermaid 區塊至 [Mermaid Live Editor](https://mermaid.live/)。

---

## 下一步

- [`03-deployment.md`](03-deployment.md) — 加 GPU 工作節點 / SSO / 正式上線
- [`05-api-reference.md`](05-api-reference.md) — API 完整參考
- [`07-development.md`](07-development.md) — 模組擴展、新增 router、i18n
