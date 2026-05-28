# Plan: Colab 風格 Notebook 模組升級 — code-server + Dual-Track + Hybrid Persistence

> **版本**：v2（2026-05-18 重寫，取代 v1 偽 Notebook 設計）
> **目標體驗**：VS Code in Browser，Colab 級體驗，1000 人規模
> **交付方式**：單一獨立模組，完成後可整批接入

---

## Context

### v1（現況）的問題

2026-05 已完成的「偽 Notebook」模組（`web-ui/app.js` 的 `NB` IIFE + `routers/notebooks.py` + `gpu-worker/worker.py` 的 `inline_code` 分支）有三個結構性痛點：

1. **UI 不便於程式開發**：只有單一 Notebook 編輯介面，無多檔編輯、無檔案總管、無 Git，編輯器是 Monaco 但缺 LSP / 自動補全延展性。
2. **必須開終端機才能做的事**：沒有任何 terminal，所有 `ls`/`pip list`/`tail -f`/`nvidia-smi` 互動式操作都得寫進 shell cell 重跑一次，無法即時 debug。
3. **環境問題**：容器 `--rm` 後消失，pip install 不保留、HuggingFace 模型每次重下載（5–15 GB）、框架切換失去先前裝的套件、無 secrets 注入。

### 使用者決策（已確認）

| 議題 | 選擇 |
|------|------|
| 目標體驗 | **VS Code in Browser**（code-server） |
| 持久化方案 | **D = 三者混合**（base image + per-user volume + requirements.txt） |
| 容器架構 | **雙軌**（CPU 編輯容器常駐 + GPU 容器任務驅動） |
| code-server idle | **30 分鐘自動關**（volume 保留） |
| Run 觸發 | **VS Code Notebook Cell Run**（自製 extension）|
| Terminal 範圍 | **code-server 內全域 terminal**，shell cell 仍保留作為「批次指令」 |
| 規模 | **小→中規模成長**（目前 ≤20，預期擴至 100；1000 人為遠期目標）|
| 交付 | **一次到位，作為單一獨立模組** |
| Secrets 管理 | **v2.0 納入**（HF_TOKEN / WANDB_API_KEY / 自訂） |
| 多 GPU 任務 | **v2.0 不支援**，明確標註留 v2.1 |
| v2.1 預留 | **架構抽象（Protocol 介面 + 文件），不寫半實作 schema/API**（避免攻擊面） |
| Session Hard Limit | **學生 1.5 小時 / 每日 6 小時**；教師 / admin 無限 |
| 訓練 Job 不受 Session 限制 | **雙軌天然支援** — Job 在 GPU server 獨立執行，code-server 關閉不影響 |

### 1000 人規模磁碟預估（已試算）

- 熱儲存 NVMe SSD：8 TB（含使用者 home volumes + 共享模型快取）
- 冷儲存 HDD：6 TB（90 天閒置歸檔）
- Base images：~500 GB（固定一次性）
- 預設配額：學生 10 GB / 研究生 40 GB / 教師 50 GB

### 服務層硬體建議（依使用者規模）

**特別說明**：code-server 容器跑在**服務層 CPU**（Ubuntu Server 主機），訓練容器跑在 GPU 高階伺服器。服務層需依預期同時在線人數規劃硬體。

| 同時在線 | CPU cores | RAM | 服務層 NVMe |
|---------|----------|-----|------------|
| 20 人 | 16 cores | 64 GB | 4 TB |
| 100 人 | 64 cores | 256 GB | 16 TB |
| 1000 人 | 需橫向擴展（K8s / Docker Swarm，多台服務層節點） | — | — |

每個 code-server 容器配額：0.5 CPU、2 GB RAM。idle 30 分鐘自動關，volume 保留。

### GPU 節點池分層（重新定義「中低算力 vs 高算力」）

**背景**：服務層也預計配 RTX 5090。但**保留分層**，因為兩種使用模式對啟動延遲、容器壽命的需求完全不同。

| 池名稱 | 機器 | 用途 | 容器壽命 | v2.0 啟用 |
|--------|------|------|---------|----------|
| **批次訓練池**（Batch Pool） | 高階 GPU 伺服器 | 訓練、微調、推論服務、Run on GPU 一次性任務 | 短期（`--rm`，跑完即關） | ✅ 啟用 |
| **互動式 GPU 池**（Interactive Pool） | 服務層 RTX 5090 | v2.1 Jupyter Kernel、debug session、小推論 | 長期（idle timeout） | ⏸ v2.0 預留節點但不開放 |

**為什麼不合併**：
- 批次任務跑 24 小時、吃滿 VRAM → 與「即時 API 服務」共處會讓 nginx / scheduler latency 飆升
- 互動式要 < 1 秒啟動 → 批次容器需 5-10 秒 docker pull + 啟動，無法滿足
- 隔離原則保護服務層的「即時服務」品質

**Plan 對應變更**：
- `WorkerHeartbeat` 模型新增 `pool_type: str`（"batch" / "interactive"，v2.0 預設都填 "batch"）
- `scheduler_policy.yaml` 新增 `pools:` 區塊宣告
- 管理介面新增「節點池」分頁，顯示兩池狀態
- v2.1 開放互動池供 Jupyter Kernel 使用

---

## 架構總覽

```
┌──────────────────────────────────────────────────────────────────────┐
│  服務層 (Ubuntu Server)                                                │
│                                                                       │
│  ┌─────────────┐    ┌────────────────────────────────────────────┐  │
│  │  Nginx :80  │───▶│  Job Scheduler (FastAPI :8002)             │  │
│  │  Gateway    │    │  ├── /api/v1/auth/*  (現有)                 │  │
│  │             │    │  ├── /api/v1/jobs/*  (現有，沿用 SSE)       │  │
│  │  /code/{u}/ │    │  ├── /api/v1/worker/* (現有)                │  │
│  │  → cs-{u}   │    │  └── /api/v1/lab/* (新增 — 編輯容器管理)    │  │
│  └─────────────┘    └──────────────────┬─────────────────────────┘  │
│         │                              │                              │
│         │                              ▼                              │
│         │           ┌────────────────────────────────┐               │
│         │           │  Lab Session Manager (新增)    │               │
│         │           │  ├── start_codeserver(user)    │               │
│         │           │  ├── stop_idle(>30min)         │               │
│         │           │  └── docker SDK calls          │               │
│         │           └────────────────────────────────┘               │
│         │                                                             │
│         ▼                                                             │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │  code-server containers (一人一個，CPU only)                    │ │
│  │  cs-alice  │  cs-bob  │  cs-charlie  ...                       │ │
│  │  ├ Mount: home_{user}:/home/coder    (per-user volume, 持久) │ │
│  │  ├ Mount: shared_models:/opt/models  (read-only, 共享快取)    │ │
│  │  ├ Resource: 0.5 CPU, 2 GB RAM                                │ │
│  │  ├ Extensions: Python, Jupyter, AI Base Run-on-GPU (自製)     │ │
│  │  └ Idle 30min → stop（volume 保留）                            │ │
│  └────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────┘
                                │
                          Pull 任務 (現有機制)
                                ▼
┌──────────────────────────────────────────────────────────────────────┐
│  GPU 高階伺服器 (Windows 11 + WSL2)                                    │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │  GPU Worker（現有）                                              │ │
│  │  領取任務 → docker run --gpus --rm ...                          │ │
│  │  ├ Mount: home_{user}:/home/coder     (同一塊 volume！)         │ │
│  │  ├ Mount: shared_models:/opt/models   (同上)                   │ │
│  │  ├ Image: 5 個預裝 base images                                  │ │
│  │  └ entrypoint: bash /job_code/run.sh  (與 v1 相同)              │ │
│  └────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────┘
```

**關鍵設計：CPU 與 GPU 容器掛載「**同一塊** per-user volume」**。
這代表：
- 使用者在 code-server 寫的程式碼 → GPU 容器立即看得到
- GPU 容器訓練輸出 → code-server 檔案總管立即顯示
- pip install --user 裝的套件、HF cache 都共用
- 完美對應 Colab「`/content/drive` 隨處可見」的體驗

---

## 元件詳細設計

### 1. Lab Session Manager（新後端模組）

**檔案**：`job-scheduler/app/services/lab_manager.py`（新）

職責：
- 接收 `POST /api/v1/lab/start`（user 點「開啟 Notebook」）
- 用 docker SDK 啟動 `cs-{user_id}` 容器（若尚未啟動）
- 配置：mount 對應 volume、注入環境變數、設定資源限制
- 回傳 code-server URL（含 one-time token）
- 背景排程器每 1 分鐘掃 idle 容器，超過 30 分鐘 stop

**Endpoints**（新 router `routers/lab.py`）：
| 方法 | 路徑 | 說明 |
|------|------|------|
| POST | `/api/v1/lab/start` | 啟動 / 取得使用者的 code-server URL |
| GET | `/api/v1/lab/status` | 查詢容器狀態（running / stopped / starting） |
| POST | `/api/v1/lab/stop` | 主動關閉自己的容器（不刪 volume） |
| POST | `/api/v1/lab/heartbeat` | code-server 內 extension 每 5 分鐘呼叫，更新 last_activity |

### 2. 自製 VS Code Extension — `aibase-runner`

**位置**：`vscode-extension/aibase-runner/`（新目錄）

職責：
1. **「Run on GPU」command**：右鍵 `.py` 檔或 Notebook cell → 「Run on GPU」 → 將檔案內容（或 cell 內容）打包為 `inline_code`，POST 至 `/api/v1/jobs`
2. **SSE 輸出回顯**：開啟 VS Code Output Panel "AI Base GPU"，串流任務日誌
3. **Job 狀態列**：底部顯示 "Running on gpu-node-01 | 45% | step 100/200"
4. **Notebook Cell Run 接管**：override 預設 Jupyter Run Cell，改提交 Job
5. **Heartbeat**：每 5 分鐘 POST `/api/v1/lab/heartbeat`，讓 server 知道使用者仍活躍

打包後安裝進 code-server image，使用者開 VS Code 就有。

### 3. Base Image 重新設計

**位置**：`infrastructure/base-images/`（新目錄）

6 個預製 image（含 dev-tools 支援多語言），由 CI 預先 build push 到 registry：

| Image | 內容 | 主要用途 |
|-------|------|---------|
| `aibase/pytorch:2.7-cu128` | PyTorch + accelerate + datasets + numpy + pandas + matplotlib + sklearn + wandb | 標準 PyTorch 訓練 |
| `aibase/tensorflow:2.15-gpu` | TF + keras + tensorboard + 資料科學套件 | TF 訓練 |
| `aibase/huggingface:latest` | pytorch + transformers + diffusers + sentencepiece + peft + bitsandbytes + trl | **LoRA 微調**（最常用）|
| `aibase/llamacpp:cuda` | llama.cpp + ggml + CUDA toolchain (nvcc) | 推論 / CUDA 開發 |
| `aibase/vllm:latest` | vLLM + flash-attn | 高效能推論服務 |
| **`aibase/dev-tools:latest`**（新增） | g++/gdb/cmake、openjdk-17、go、rust + python + cuda toolkit | **C++/CUDA/Java/Rust/Go 多語言開發** |

**code-server image**：`aibase/code-server:latest`
- Based on `codercom/code-server:latest`
- **Multi-stage build**（Stage 1: Node.js 編譯 aibase-runner extension；Stage 2: 只複製 .vsix 進 final image）
- 預裝 extensions：Python、Jupyter、clangd (C++)、Java Pack、rust-analyzer、Go、aibase-runner
- 預裝工具：python3.11、pip、git、curl、wget、tar、zip
- 最終 image 大小：< 1 GB（vs 不用 multi-stage 約 2.5 GB）

### 3.2 多版本工具鏈策略

**設計目標**：穩定性優先（base image 鎖版本），同時讓使用者能切換到舊版（透過 conda）。

**分層解法**：

| 層次 | 機制 | 切換速度 | 穩定性 |
|------|------|---------|--------|
| **L1 主版本** | 切 base image（PyTorch 2.7 ↔ PyTorch 2.0 等） | 5-10 秒 | ⭐⭐⭐⭐⭐ |
| **L2 Python 版本** | 各 image 預裝 **miniconda3**；使用者 `conda create -n env python=3.X` 建私人環境 | 第一次 10-30 分鐘 | ⭐⭐⭐ |
| **L3 編譯器版本** | `dev-tools` image 用 `update-alternatives` 切 gcc/g++/nvcc | 即時 | ⭐⭐⭐⭐ |
| **L4 套件版本** | 每個 conda env 內 `pip install <pkg>==<version>` | 看套件大小 | ⭐⭐⭐ |

**所有 base image 預裝**：
- miniconda3（~150 MB 額外）
- `conda config` 預設 channel 包含 conda-forge / nvidia
- conda env 預設存放路徑：`/home/coder/.conda/envs/`（在 persistent volume 內，跨次保留）

**Legacy 版本支援**：
- v2.0 提供主流版本 base image：PyTorch 2.7（CUDA 12.8）+ PyTorch 2.0（CUDA 11.8）兩個版本
- 學生若要 PyTorch 1.8（很舊）：用 conda 自建 env 或申請 admin 加客製 image
- v2.1 開放 admin 在管理介面註冊客製 image（標籤、適用對象、來源 URL）

**使用者體驗範本**：
```bash
# 場景：研究生要跑 PyTorch 1.13 + CUDA 11.7 的舊 paper code
# Step 1: 切框架到 aibase/pytorch:2.0-cu118（最接近的 base）
# Step 2: 在 terminal 自建 conda env
conda create -n paper-repro python=3.9
conda activate paper-repro
conda install pytorch==1.13 cudatoolkit=11.7 -c pytorch
# Step 3: 環境永久保留在 /home/coder/.conda/envs/paper-repro
# Step 4: 下次登入 → conda activate paper-repro → 立即可用

# 「凍結環境」匯出供未來重建
conda env export > paper-repro-env.yml  # 存到 ~/projects/
```

**配套功能**：
- code-server 內附 conda extension（自動偵測並切換）
- 使用者設定頁面顯示「我的 conda envs」清單與磁碟使用量
- 「環境出問題了」一鍵重置：刪除 `~/.conda/` 與 `~/.local/`，保留 `~/projects/`

### 3.1 共享模型快取機制（重要設計）

**`shared_models` Docker named volume**：read-only 掛載到所有容器的 `/opt/models/`

**HF_HOME 環境變數**：
```bash
# 在每個 base image 的 Dockerfile 設定：
ENV HF_HOME=/opt/models:/home/coder/.cache/huggingface
# ↑ 多路徑：先查共享快取，找不到再查使用者私人快取
```

**結果**：
- 使用者程式 `from_pretrained("meta-llama/Llama-2-7b-hf")` 自動命中 `/opt/models/`
- LoRA 微調 base model **零複製**（read from /opt/models/，write LoRA adapter to ~/outputs/）
- 100 個學生共用 Llama-2-7B = 14 GB（不是 1.4 TB），節省 99% 磁碟

**全量微調例外**：使用者需手動 `cp -r /opt/models/llama-2-7b ~/projects/` 才能改權重 → 此時才複製，且使用者自費配額。

**預下載模型清單**（管理員維護，admin-ui 介面新增/刪除）：
- Llama-2-7B / Llama-2-13B（gated，需 HF_TOKEN）
- Mistral-7B / Mixtral-8x7B
- BERT-base / BERT-large（中英文）
- T5-base / T5-large
- Stable Diffusion 1.5 / SDXL
- Whisper-large（語音）
- 系所自有模型

預估熱門模型總量：~200-400 GB（一次性）

### 4. Per-user Volume 結構

```
/home/coder/                              ← per-user docker volume
├── .bashrc                                ← 預先注入 PYTHONPATH、HF_HOME 等
├── .cache/
│   ├── pip/                               ← pip 下載快取
│   └── huggingface/                       ← HF 模型快取（指向 shared, fallback to local）
├── .local/
│   ├── bin/
│   └── lib/python3.11/site-packages/      ← pip install --user 裝這
├── projects/                              ← 使用者 notebooks 與程式碼
│   └── my-first-project/
│       ├── train.ipynb
│       ├── requirements.txt
│       └── data/
├── outputs/                               ← 訓練輸出（模型、checkpoint）
└── logs/                                  ← 任務日誌備份
```

`shared_models` volume（**read-only** mount 到所有容器的 `/opt/models`）：
- 預下載熱門模型：Llama-2-7B、Mistral-7B、BERT、T5、SD-1.5 等
- 系所自有模型
- 透過 `HF_HOME=/opt/models:~/.cache/huggingface` 讓 HuggingFace 優先讀共享

### 5. Nginx 路由擴充

**檔案**：`infrastructure/nginx.conf`

新增：
```nginx
# code-server 路由（per-user）
# /code/{user_id}/ → cs-{user_id}:8080
location ~* ^/code/([a-f0-9-]+)/ {
    auth_request /api/v1/lab/_authz;        # 先驗證 JWT 屬於這個 user_id
    proxy_pass http://cs-$1:8080/;          # 注意：cs-* 是 Docker 內部 DNS

    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade"; # code-server 用 WebSocket
    proxy_buffering off;
    proxy_read_timeout 24h;
}

# 內部認證端點（給 auth_request）
location = /api/v1/lab/_authz {
    internal;
    proxy_pass http://job_scheduler/api/v1/lab/authz?path=$request_uri;
    proxy_set_header Authorization $http_authorization;
}
```

### 5.5 Session 時間管理（學生 1.5 小時 Hard Limit + 每日 6 小時總額）

**雙計時器設計**：

| 計時器 | 用途 | 學生預設 | 教師預設 | admin 預設 |
|--------|------|---------|---------|----------|
| **Idle Timeout** | 無互動自動關 | 30 分鐘 | 120 分鐘 | 無限 |
| **Hard Session Limit** | 從啟動算起累積 | 90 分鐘（1.5 小時） | 無限 | 無限 |
| **Daily Quota** | 每日總使用時長 | 360 分鐘（6 小時） | 無限 | 無限 |

**核心觀念**：以上計時器**僅針對 code-server 編輯容器**。**已提交的 GPU 訓練 Job 完全不受影響**（這是雙軌設計的最大好處）。

#### Settings（在 `scheduler_policy.yaml` 統一管理）
```yaml
session_limits:
  student:
    idle_timeout_min: 30
    hard_limit_min: 90
    daily_limit_min: 360
  teacher:
    idle_timeout_min: 120
    hard_limit_min: null      # null = 不限制
    daily_limit_min: null
  admin:
    idle_timeout_min: null
    hard_limit_min: null
    daily_limit_min: null
```

admin-ui 提供「Session 限制」分頁編輯這份 yaml，儲存後即時生效。

#### 對各種活動的影響評估

| 活動 | 影響 | 解法 |
|------|------|------|
| 寫程式 / 編輯 | 🟢 無 | VS Code auto save 預設開啟 |
| 拖拉上傳 < 500 MB | 🟢 無 | 秒級完成 |
| 終端機下載 < 5 GB | 🟢 無 | < 2 分鐘 |
| 終端機下載 50 GB+ | 🟡 偶爾跨 session | `aria2c -c` 自動續傳，下次接續 |
| Terminal 未存指令輸出 | 🟡 容器關閉時消失 | bash history 自動保留 |
| **長時間訓練（6-24 小時）** | 🟢 **完全無** | **雙軌：Job 在 GPU server 跑，code-server 關了不影響** |
| 互動式 debug (v2.1 真 Kernel) | 🔴 高 | 教師角色或申請延長 |

#### 新增 DB schema
```python
class UserSessionUsage(Base):
    __tablename__ = "user_session_usage"
    user_id        = Column(String, ForeignKey("users.id"), primary_key=True)
    date           = Column(Date, primary_key=True)
    total_seconds  = Column(Integer, default=0)     # 該日累積使用秒數
    session_count  = Column(Integer, default=0)     # 該日啟動 session 次數
```

#### Lab Manager 啟動 / 關閉時的判斷邏輯

```python
def start_session(user_id) -> str:
    limits = get_limits_for_role(user.role)
    today_usage = get_today_usage(user_id)

    # 檢查每日上限
    if limits.daily_limit_min and today_usage.total_seconds >= limits.daily_limit_min * 60:
        raise HTTPException(429, "本日已達使用時長上限，請明日再試")

    # 啟動容器，記錄起始時間
    ...
    return container_url

# 背景任務每 1 分鐘掃一次
def scan_sessions():
    for session in active_sessions():
        elapsed_seconds = now - session.started_at
        if elapsed_seconds > limits.hard_limit_min * 60:
            stop_session(session, reason="hard_limit_reached")
            increment_usage(session.user_id, elapsed_seconds)
        elif (now - session.last_activity) > limits.idle_timeout_min * 60:
            stop_session(session, reason="idle_timeout")
            increment_usage(session.user_id, elapsed_seconds)
```

#### 使用者體驗強化（aibase-runner extension）

1. **VS Code Status Bar 倒數計時顯示**：
   - 🟢 綠：> 15 分鐘剩餘
   - 🟡 黃：5–15 分鐘剩餘
   - 🔴 紅：< 5 分鐘 + 彈窗警告「將於 X 分鐘後關閉，請存檔」
2. **自動 save**：剩 1 分鐘時 extension 觸發 VS Code「Save All」
3. **每日額度提示**：開啟 session 時提示「今日已用 X 小時，剩餘 Y 小時」

### 6. 資料模型擴充

**檔案**：`job-scheduler/app/models.py`

新增表：
```python
class LabSession(Base):
    __tablename__ = "lab_sessions"
    user_id        = Column(String, ForeignKey("users.id", ondelete="CASCADE"),
                            nullable=False)
    session_name   = Column(String, default="default")  # v2.0 強制 "default"，v2.1 開放多 session
    container_id   = Column(String, nullable=True)
    container_name = Column(String, nullable=True)
    status         = Column(String, default="stopped")
                          # stopped / starting / running / stopping
    volume_name    = Column(String, nullable=False)
                          # e.g. "home_alice"
    base_image     = Column(String, nullable=False)
                          # 當前 session 用的 image，例如 "aibase/huggingface:latest"
    last_activity  = Column(DateTime)
    started_at     = Column(DateTime)
    cpu_quota      = Column(Float, default=0.5)
    mem_quota_mb   = Column(Integer, default=2048)
    disk_quota_gb  = Column(Integer, default=10)
    __table_args__ = (
        # ZH: 複合 PK 預留 v2.1 多 session 並行能力（v2.0 仍只允許 default）
        # EN: Composite PK to support v2.1 multi-session; v2.0 enforces "default"
        PrimaryKeyConstraint("user_id", "session_name"),
    )


class UserSecret(Base):
    """ZH: 使用者 secrets（HF_TOKEN, WANDB_API_KEY 等），AES 加密儲存"""
    __tablename__ = "user_secrets"
    id          = Column(String, primary_key=True, default=generate_uuid)
    user_id     = Column(String, ForeignKey("users.id", ondelete="CASCADE"),
                         nullable=False, index=True)
    name        = Column(String, nullable=False)         # 環境變數名稱，如 "HF_TOKEN"
    value_enc   = Column(LargeBinary, nullable=False)    # AES-256 加密的 value
    created_at  = Column(DateTime)
    updated_at  = Column(DateTime)
    __table_args__ = (UniqueConstraint("user_id", "name"),)
```

**修改現有表**：`models.User` 新增：
```python
disk_quota_gb = Column(Integer, default=10)  # 個別配額（admin 可調）
```

### 6.5 Secrets 管理層（v2.0 新增）

**設計理念**：研究生需要 HF_TOKEN（讀 gated 模型）、WANDB_API_KEY（實驗追蹤）、自訂 API key。

**檔案**：
- `job-scheduler/app/services/secrets_service.py`（新）
  - `set_secret(user_id, name, value)` → AES-256-GCM 加密 → DB
  - `get_secrets(user_id) → Dict[name, plaintext]` → 解密
  - `delete_secret(user_id, name)`
  - 主金鑰（KEK）從 `.env` 的 `SECRETS_MASTER_KEY` 讀取，啟動時驗證強度（≥32 chars，沿用 C3 fail-fast）

**Endpoints**（加入 `routers/lab.py` 或新 `routers/secrets.py`）：
| 方法 | 路徑 | 說明 |
|------|------|------|
| GET | `/api/v1/secrets/` | 列出自己的 secrets（只回傳 name + masked value，不回 plaintext） |
| PUT | `/api/v1/secrets/{name}` | 新增 / 更新 |
| DELETE | `/api/v1/secrets/{name}` | 刪除 |

**注入流程**：
- 提交 GPU Job 時，後端從 `user_secrets` 查出該使用者全部 secrets
- 透過 `docker run -e HF_TOKEN=xxx -e WANDB_API_KEY=yyy ...` 注入容器環境變數
- code-server 啟動時同樣注入到 `/home/coder/.bashrc` 內 `export HF_TOKEN=xxx`

**安全要點**：
- secrets **絕不** 寫進 Job 的 logs / inline_code / DB job 紀錄
- API 回傳值永遠 masked（顯示 `hf_********xy`）
- admin 介面**不能查看**他人 secrets（即使 admin role 也不行；可刪除 / 重置）
- 加密金鑰輪換機制留 v2.1（v2.0 用單一 KEK）

### 6.5b 工作階段運行中環境查看

**設計目標**：使用者可隨時查看「我的 code-server 目前處於什麼狀態」「注入了哪些 secrets」，但不洩漏 plaintext。

**Endpoint 擴充**：`GET /api/v1/lab/status` 回傳：
```json
{
  "session_name": "default",
  "status": "running",
  "started_at": "2026-05-21T10:23:15Z",
  "last_activity": "2026-05-21T10:28:33Z",
  "idle_seconds": 12,
  "base_image": "aibase/huggingface:latest",
  "injected_secrets": [
    {"name": "HF_TOKEN", "value_masked": "hf_********xy", "set_at": "2026-04-12"},
    {"name": "WANDB_API_KEY", "value_masked": "wb_********ab", "set_at": "2026-05-01"}
  ],
  "resource_usage": {
    "cpu_percent": 12.3, "cpu_limit": 0.5,
    "mem_mb": 1234, "mem_limit_mb": 2048,
    "disk_used_gb": 14.3, "disk_quota_gb": 40
  }
}
```

**code-server 內查看 plaintext**：使用者在自己的 terminal 跑 `echo $HF_TOKEN` 可看（容器內安全），UI 不提供。

**admin UI Secrets 監控分頁顯示**（所有使用者）：
- 名稱清單、最後更新時間、是否已注入到當前 session
- **永遠不顯示 plaintext value**
- 可強制刪除使用者的特定 secret

### 6.6 v2.1 預留架構（抽象介面，不寫死 schema/API）

**目的**：未來加 Jupyter Kernel 模式時，不動 v2.0 已上線的 schema 與 endpoint，避免攻擊面與相容性問題。

**做法**：

1. **`lab_manager.py` 用 Protocol 抽象 container 生命週期**
   ```python
   from typing import Protocol

   class ContainerLifecycle(Protocol):
       """所有容器類型的共通介面"""
       def start(self, user_id: str, config: dict) -> str: ...
       def stop(self, user_id: str) -> None: ...
       def is_idle(self, user_id: str) -> bool: ...
       def status(self, user_id: str) -> str: ...

   class CodeServerLifecycle:
       """v2.0 唯一實作"""
       def start(self, user_id, config):
           # docker run codercom/code-server ...
   ```

2. **v2.1 加 Kernel 時新增 `KernelLifecycle(ContainerLifecycle)`**，不動 `CodeServerLifecycle`、不動 `lab_sessions` schema。

3. **文件**：新增 `docs/dev/v2.1-roadmap.md` 明確標註：
   > Jupyter Kernel 模式預期擴充點：
   > - 新增 `services/kernel_manager.py`（不要改 `lab_manager.py`）
   > - 新增 `routers/kernels.py`（不要動 `routers/lab.py`）
   > - 新增 `kernel_sessions` 表（**不要在 `lab_sessions` 加欄位**）
   > - GPU 分配政策：新增 `gpu_reservations` 表追蹤 interactive 容器佔用

**v2.0 不做的事**（避免半實作攻擊面）：
- ❌ 不在 `lab_sessions` 加 `is_interactive` 欄位
- ❌ 不在 `training_jobs` 加 `mode: batch | interactive` 欄位
- ❌ Job API 不接受 `reserved` 之類未使用參數
- ❌ WorkerHeartbeat 不加 reserved GPU 計數

### 7. 前端（web-ui）變更

**簡化策略**：
- 移除 v1 偽 Notebook 模組（`compute-notebook` sub-tab + NB IIFE）
- 改為單一「**開啟 Notebook**」按鈕 → 呼叫 `/api/v1/lab/start` → 跳轉至 `/code/{user_id}/`
- 容器啟動中顯示 spinner（約 5-10 秒）

**保留**：原本的 High / Mid-Low 簡易表單頁籤作為**快速提交模式**（給只想跑單一腳本、不需要 IDE 的人）。

### 8. 管理介面（admin-ui）擴充

新增「**Lab Sessions**」分頁，顯示：
- 目前線上的 code-server 容器（user / 啟動時間 / 最後活動 / RAM 使用 / CPU 使用）
- 強制關閉某個使用者的容器
- 設定個別使用者配額（CPU / RAM / 磁碟）
- 共享模型快取管理（列出 / 加入 / 刪除）

新增「**Secrets 監控**」分頁（管理員可監控，不可查看內容）：
- 列出所有使用者的 secrets 數量、名稱清單、最後更新時間
- **不顯示 plaintext value**（即使 admin 也不行）
- 強制刪除某個使用者的特定 secret（例如離校學生）

### 9. 使用者設定頁面擴充（web-ui）

設定頁面新增「**Secrets 管理**」區塊：
- 列出自己的 secrets（顯示 name + masked value，如 `hf_********xy`）
- 新增 / 更新 / 刪除 secret
- 提供範本快捷鍵：`HF_TOKEN` / `WANDB_API_KEY` / `OPENAI_API_KEY` / 自訂

### 9.5 配額提權與儲存生命週期管理

#### 配額提權機制

**背景**：研究生做全量微調時可能需要超過預設 40 GB 配額。管理員需要能「臨時提權」讓使用者使用更多校方硬碟。

**新增表 `quota_grants`**（獨立表而非欄位，方便審計與歷史紀錄）：
```python
class QuotaGrant(Base):
    __tablename__ = "quota_grants"
    id              = Column(String, primary_key=True, default=generate_uuid)
    user_id         = Column(String, ForeignKey("users.id"), index=True)
    extra_quota_gb  = Column(Integer)
    granted_by      = Column(String, ForeignKey("users.id"))   # 哪個 admin
    reason          = Column(Text)                              # 必填，審計用
    granted_at      = Column(DateTime)
    expires_at      = Column(DateTime, nullable=True)           # null = 永久
    revoked_at      = Column(DateTime, nullable=True)
```

**有效配額計算**（在 `crud.py`）：
```python
def get_effective_quota_gb(db, user_id) -> int:
    base = user.disk_quota_gb
    extra = sum(g.extra_quota_gb for g in db.query(QuotaGrant).filter(
        QuotaGrant.user_id == user_id,
        QuotaGrant.revoked_at.is_(None),
        or_(QuotaGrant.expires_at.is_(None),
            QuotaGrant.expires_at > now)
    ).all())
    return base + extra
```

**Admin UI 變更**：使用者列表加「配額提權」按鈕，表單欄位：額外配額（GB）/ 有效期限 / 提權理由（必填）。列表顯示目前生效與歷史 grants，可單筆撤銷。

#### 儲存生命週期管理（永不自動硬刪）

**核心原則**：節制磁碟壓力，但**所有資料永久刪除都需 admin 二次確認**。

**四階段狀態機**：

```
[active] ──超配額/90天未登入──▶ [frozen] ──30天無動作──▶ [archived] ──1年無動作──▶ [pending_delete]
   ↑                              ↑(只讀)                 ↑(壓縮移至 HDD)         ↑(等 admin 確認)
   └──────── admin 解凍 ──────────┘                       └─── 7 天內可復原 ────┘
```

| 狀態 | 觸發 | 使用者體驗 | 系統行為 |
|------|------|----------|---------|
| `active` | 配額內 + 30 天內登入 | 完全正常 | NVMe |
| `frozen` | 超過配額 OR 90 天未登入 | code-server 可開但**唯讀** + 提示清理 / 申請提權 | NVMe，移除寫入權限 |
| `archived` | frozen 後 30 天無動作 OR 180 天未登入 | code-server 不可開；申請「解凍下載」可生效 | 壓縮為 tar.gz 移到 HDD，metadata 保留 |
| `pending_delete` | archived 後 1 年無動作 OR 帳號刪除 | 通知 email 7 天前最後通知 | 列入 admin 待刪清單 |

**安全機制**：
1. **永不自動硬刪**：每筆刪除都需 admin 在 UI 點「確認永久刪除」並輸入管理員密碼（沿用 `/api/v1/admin/verify`）
2. **刪除前 audit log**：執行刪除前 dump volume metadata（owner / size / last_access / 執行者）到 `admin_actions` 表
3. **學期保護**：學期中（9月–次年6月）禁止觸發 `frozen → archived` 與 `archived → pending_delete` 轉換（避免期末考週資料消失）
4. **教師例外**：role=teacher 預設不歸檔（除非離校手動觸發）
5. **緊急復原**：archived 階段可申請「7 天內復原」（從 HDD 拉回 NVMe）

**新增表 `user_storage_state`**：
```python
class UserStorageState(Base):
    __tablename__ = "user_storage_state"
    user_id        = Column(String, ForeignKey("users.id"), primary_key=True)
    state          = Column(String, default="active")
    state_since    = Column(DateTime)
    current_size_gb = Column(Float)
    archive_path   = Column(String, nullable=True)
    notes          = Column(Text)
```

**新增表 `admin_actions`**（審計）：
```python
class AdminAction(Base):
    __tablename__ = "admin_actions"
    id          = Column(String, primary_key=True, default=generate_uuid)
    admin_id    = Column(String, ForeignKey("users.id"))
    target_user = Column(String, ForeignKey("users.id"), nullable=True)
    action      = Column(String)        # grant_quota / revoke_quota / freeze / archive / delete / inject_files / ...
    payload     = Column(Text)           # JSON 詳細參數
    timestamp   = Column(DateTime)
```

**Admin UI 新增「儲存管理」分頁**：
- 各狀態使用者數量總覽
- 各階段使用者清單（state, last_login, size, days_in_state）
- 手動觸發「凍結 / 解凍 / 歸檔 / 復原 / 永久刪除」操作
- 配額提權快捷入口
- audit log 查詢

**背景排程任務**（`scheduler.py`）：
- 每天 03:00 執行一次「狀態轉換掃描」
- 學期中（9月–6月）只執行 `active → frozen`，跳過後續轉換
- 暑假（7-8月）執行完整轉換流程

**工時影響**：+1.5 天（3 個新表 + state machine + admin UI 分頁 + 背景任務）

### 10. 檔案傳輸功能

#### 學生 / 一般使用者上傳（三個管道）

| 管道 | 適用大小 | 做法 | 開發成本 |
|------|---------|------|---------|
| **L1 — 拖拉上傳**（小檔案首選） | < 500 MB | code-server Explorer 拖拉檔案到目錄 → 自動上傳（**code-server 原生**） | 0 |
| **L2 — 終端機下載**（大檔案 / 線上資料集首選） | 任意大小 | `wget` / `curl` / `aria2` / `kaggle` / `huggingface-cli` / `gh repo clone` 等指令 | 0（工具預裝） |
| **L3 — 自製分塊上傳** | 500 MB – 10 GB | Web UI「資料集上傳」按鈕、tus.io 協定、續傳、進度條 | **v2.1**（v2.0 不做，L2 已能覆蓋）|

#### 教師批量注入

| 管道 | 做法 | 開發成本 |
|------|------|---------|
| **admin 批量資料注入** | admin-ui 新分頁，上傳 zip → 後端解壓到指定使用者的 `~/projects/` | 1 天 |

新增 endpoint：
```
POST /api/v1/admin/lab/inject
  Form: target_user_id, project_name, file (multipart, zip/tar.gz, max 5 GB)
  → 解壓到 home_{target_user_id} volume 內 /projects/{project_name}/
```

#### 下載 / 打包

| 管道 | 做法 | 開發成本 |
|------|------|---------|
| **L1 — VS Code Explorer**（單檔） | 右鍵 → Download | 0 |
| **L2 — 整個專案打包** | 終端機 `tar -czf my.tar.gz ~/projects/` 再 Download；或 endpoint `GET /api/v1/lab/export?project=xxx` 串流 tar.gz | 0.5 天 |

### 10.5 終端機指令下載資料集（與 Secrets 模組整合）

**設計目標**：學生想下載 Kaggle / HuggingFace / GitHub 上的資料集時，只需一行指令，身份驗證透明處理。

#### 預裝 CLI 工具（所有 base image）

| 工具 | 用途 | 大小 |
|------|------|------|
| `kaggle` | Kaggle 競賽資料集 | ~30 MB |
| `huggingface-cli` | HF Datasets / Models | ~50 MB |
| `gh` (GitHub CLI) | GitHub repo / release / gist | ~20 MB |
| `aria2c` | 多執行緒下載加速器 | ~5 MB |
| `wget` / `curl` / `git` | 通用工具（已預裝） | 內建 |

#### 身份驗證整合（透過 Secrets 自動注入）

| 資料來源 | 需要的 secrets | 注入方式 |
|---------|--------------|---------|
| Kaggle | `KAGGLE_USERNAME` + `KAGGLE_KEY` | container entrypoint 自動寫 `~/.kaggle/kaggle.json` (mode 600) |
| HuggingFace gated | `HF_TOKEN` | 環境變數，`huggingface_hub` 自動讀 |
| GitHub private | `GITHUB_TOKEN` 或 `GH_TOKEN` | 環境變數，entrypoint 自動 `gh auth login --with-token` |
| 一般 HTTPS | 不需要 | wget/curl/aria2 直接拉 |

#### `code-server` 容器 entrypoint script

新增 `infrastructure/base-images/code-server/aibase-entrypoint.sh`：
```bash
#!/bin/bash
# 自動轉換 secrets 為 CLI config

# Kaggle
if [ -n "$KAGGLE_USERNAME" ] && [ -n "$KAGGLE_KEY" ]; then
    mkdir -p ~/.kaggle
    cat > ~/.kaggle/kaggle.json <<EOF
{"username":"$KAGGLE_USERNAME","key":"$KAGGLE_KEY"}
EOF
    chmod 600 ~/.kaggle/kaggle.json
fi

# GitHub CLI
if [ -n "$GH_TOKEN" ]; then
    echo "$GH_TOKEN" | gh auth login --with-token 2>/dev/null || true
fi

# 啟動 code-server
exec /usr/bin/code-server --bind-addr 0.0.0.0:8080 "$@"
```

#### aibase-runner extension 內建「Dataset Helper」（+0.5 天）

VS Code Command Palette 新增「AI Base: Download Dataset」command：
- 彈出輸入框
- 支援格式：
  - `kaggle:zynicide/wine-reviews` → `kaggle datasets download -d zynicide/wine-reviews`
  - `hf:squad` → `huggingface-cli download --repo-type dataset squad`
  - `gh:owner/repo` → `gh repo clone owner/repo`
  - `url:https://...` → `aria2c -x 16 https://...`
- 自動偵測來源 → 開啟 terminal → 執行指令 → 顯示進度
- 完成後自動 `ls` 該目錄

#### 使用者實際流程範例

```bash
# 場景：學生 Alice 要下載 5GB Kaggle 資料集 + 用 HF gated dataset
# Step 1: 在 web-ui 設定頁加 secrets (KAGGLE_USERNAME / KAGGLE_KEY / HF_TOKEN)
# Step 2: 點「Open Notebook」→ code-server 啟動，entrypoint 自動處理 config

# Step 3: 在 terminal:
cd ~/projects/my-research/data/

# Kaggle (5 GB, ~1 分鐘從伺服器下載)
kaggle datasets download -d zynicide/wine-reviews && unzip wine-reviews.zip

# HF gated dataset
huggingface-cli download --repo-type dataset --local-dir ./alpaca tatsu-lab/alpaca

# GitHub repo
gh repo clone myteam/preprocessing-utils

# 完成！全部存在 home volume，下次登入仍在
```

#### 文件補強

`docs/03-使用者指南/10-使用者操作手冊.md` 新增「資料集下載快速指南」章節，含 Kaggle / HF / GitHub / 一般 URL 的常見範例。

---

## 實作順序（單一模組內部階段）

**目標**：完成後可一次性接入。但內部分四階段以利驗證。

### 階段 A：基礎設施（Base Images + Volume + Nginx）
1. `infrastructure/base-images/`：5 個 Dockerfile + build script
2. `infrastructure/base-images/code-server/`：含 aibase-runner extension 的 Dockerfile
3. 預下載熱門模型至 `shared_models` volume
4. `infrastructure/nginx.conf` 新增 `/code/{user_id}/` 路由
5. `docker-compose.yml` 宣告 `shared_models` named volume

### 階段 B：後端 Lab Manager + Secrets + 配額生命週期
6. `job-scheduler/app/models.py` 新增 `LabSession` + `UserSecret` + `QuotaGrant` + `UserStorageState` + `AdminAction` + `UserSessionUsage` 表 + `User.disk_quota_gb` + `WorkerHeartbeat.pool_type`
7. `job-scheduler/app/database.py:init_db()` 加入對應 ALTER TABLE
8. `job-scheduler/app/services/lab_manager.py`（新）：docker SDK 包裝、**用 Protocol 抽象 ContainerLifecycle**
9. `job-scheduler/app/services/secrets_service.py`（新）：AES-256-GCM 加密 / 解密
10. `job-scheduler/app/services/quota_service.py`（新）：有效配額計算
11. `job-scheduler/app/services/storage_lifecycle.py`（新）：凍結 / 歸檔 / 復原 / 待刪 狀態機
12. `job-scheduler/app/routers/lab.py`（新）：4 個 endpoint + auth_request 驗證
13. `job-scheduler/app/routers/secrets.py`（新）：3 個 endpoint
14. `job-scheduler/app/routers/admin.py`（修改）：新增配額提權、儲存管理、強制刪除 endpoints
15. `job-scheduler/app/config.py` 新增 `SECRETS_MASTER_KEY` 並加 fail-fast 驗證（沿用 C3 模式）
16. `job-scheduler/app/scheduler.py`：加入「idle 30 分鐘關閉」+「儲存狀態每日 03:00 掃描」+「學期保護日曆」背景任務
17. `job-scheduler/app/main.py`：掛載 lab / secrets router、啟動所有背景任務
18. **修改 Job 提交流程**（`crud.create_job` 或 worker `/take`）：自動注入該 user 的 secrets 為 docker env

### 階段 C：VS Code Extension
16. `vscode-extension/aibase-runner/`：TypeScript + package.json + extension.ts
17. 實作 「Run on GPU」、SSE 輸出、heartbeat、Notebook Cell Run override
18. 打包成 `.vsix`，放入 `code-server` image 的 build 階段

### 階段 D：前端 + 管理介面 + 文件
19. `web-ui/index.html` + `app.js`：移除 NB 模組、新增「開啟 Notebook」按鈕、新增「Secrets 管理」設定區塊
20. `admin-ui`：新增 Lab Sessions 與 Secrets 監控分頁
21. `docs/`：更新使用者手冊、部署指南
22. **`docs/dev/v2.1-roadmap.md`（新）**：標註 Jupyter Kernel 與多 GPU 擴充指引

### 階段 E：清理舊 Notebook 模組（同一次發布）
23. 刪除 `job-scheduler/app/routers/notebooks.py`（舊偽 Notebook router）
24. 刪除 `models.Notebook` 表 + cascade（保留 training_jobs 的 docker_image / inline_code / entry_args / preferred_node — 這 4 欄位 Lab 仍會用）
25. `database.py:init_db()` 加入 `DROP TABLE notebooks` 遷移
26. **修補先前驗證部署時發現的 ALTER 漏洞**：`training_jobs` 的 4 個 Notebook 欄位確實 ALTER

---

## 需修改 / 新增的檔案清單

### 新增
- `infrastructure/base-images/pytorch/Dockerfile`
- `infrastructure/base-images/tensorflow/Dockerfile`
- `infrastructure/base-images/huggingface/Dockerfile`
- `infrastructure/base-images/llamacpp/Dockerfile`
- `infrastructure/base-images/vllm/Dockerfile`
- `infrastructure/base-images/code-server/Dockerfile`
- `infrastructure/base-images/build-all.sh`
- `infrastructure/base-images/preload-models.sh`
- `job-scheduler/app/services/lab_manager.py`
- `job-scheduler/app/routers/lab.py`
- `vscode-extension/aibase-runner/package.json`
- `vscode-extension/aibase-runner/src/extension.ts`
- `vscode-extension/aibase-runner/src/jobRunner.ts`
- `vscode-extension/aibase-runner/src/sseStream.ts`
- `vscode-extension/aibase-runner/tsconfig.json`
- `vscode-extension/aibase-runner/README.md`
- `docs/01-部署與運營/06-Lab模組部署指南.md`

### 修改
- `job-scheduler/app/models.py`（+ LabSession, + User.disk_quota_gb）
- `job-scheduler/app/database.py`（init_db ALTER + 修補 v1 遺漏的 training_jobs ALTER）
- `job-scheduler/app/main.py`（掛 lab router、移除 notebooks router、啟 idle scanner）
- `job-scheduler/app/scheduler.py`（加 idle scanner task）
- `job-scheduler/app/schemas.py`（+ LabStartResponse, + LabStatusResponse）
- `job-scheduler/app/crud.py`（+ upsert_lab_session, + get_idle_sessions）
- `infrastructure/nginx.conf`（+ /code/{user_id}/ 路由 + internal authz）
- `docker-compose.yml`（+ shared_models volume + docker socket mount 給 lab_manager）
- `web-ui/index.html`（移除 NB 區塊，加開啟按鈕）
- `web-ui/app.js`（移除 NB IIFE，加 lab 啟動函式）
- `web-ui/styles.css`（清除 .nb-* 樣式）
- `admin-ui/admin.js`（+ Lab Sessions 分頁）
- `docs/03-使用者指南/10-使用者操作手冊.md`（改寫 Notebook 章節）
- `docs/02-API與開發/07-API使用手冊.md`（+ Lab API 章節）

### 刪除
- `job-scheduler/app/routers/notebooks.py`
- `models.Notebook` 類別（同時 DROP TABLE，分階段執行）

---

## 重用既有元件

| 既有功能 | 重用方式 |
|---------|---------|
| `job-scheduler/app/routers/jobs.py` 的 SSE 串流 | aibase-runner extension 直接 subscribe |
| `gpu-worker/worker.py` 的 inline_code 分支 | code-server 提交 cell 內容仍走這條路 |
| `training_jobs.docker_image / inline_code / entry_args / preferred_node` | 保留並使用，這是 v1 唯一仍有價值的 schema 改動 |
| `WorkerHeartbeat` 表 + `/notebooks/nodes` 端點 | 改名為 `/lab/nodes`，給 VS Code extension 選 GPU 節點 |
| JWT 認證（`get_current_user`、`require_role`） | nginx auth_request 重用同一邏輯 |
| `slowapi` rate limiter | 給 `/api/v1/lab/start` 加 5 req/min 限速 |

---

## 驗證方式（End-to-End）

### A. 基礎設施
1. `cd infrastructure/base-images && ./build-all.sh` → 5 個 base + code-server image 全 build 成功
2. `./preload-models.sh` → `shared_models` volume 內可 `ls /opt/models/llama-2-7b` 看到模型
3. `docker compose up -d`：所有服務 healthy

### B. Lab Manager
4. 學生帳號登入 web-ui → 點「開啟 Notebook」→ 5-10 秒內跳到 `/code/{user_id}/`
5. 看到 VS Code 介面，左側 Explorer 顯示 `/home/coder/projects/`
6. 開 Terminal → `pip install --user requests` → 重新 stop & start → `python -c "import requests"` 仍可用 ✅ **驗證持久化**
7. 在 admin-ui Lab Sessions 看到該使用者容器在跑、最後活動時間更新

### C. 「Run on GPU」流程
8. code-server 內新增 `train.py`（內含 `import torch; print(torch.cuda.is_available())`）
9. 右鍵「Run on GPU」→ Output panel 串流出 `True`
10. 切框架到 `aibase/huggingface:latest` → `from transformers import AutoModel` 可成功 import

### D. Notebook Cell 體驗
11. 新增 `demo.ipynb`，第一格 `import torch`、第二格 `torch.zeros(10).cuda()`
12. 點每格的 "Run on GPU" → 各自獨立提交 Job、output 顯示在 cell 底下
13. 點 "Run All" → 一次提交合併 script（與 v1 邏輯相同）

### E. 配額與冷卻
14. 故意 30 分鐘不操作 → 容器自動 stop（admin-ui 顯示 stopped）
15. 重新點「開啟 Notebook」→ 同樣 volume 重新掛回、檔案還在
16. 模擬填滿 10 GB 配額 → `/api/v1/lab/start` 回 429 並提示

### F. 安全性
17. 用 alice 的 token 嘗試訪問 `/code/bob-uuid/` → nginx auth_request 回 403
18. JWT 過期後訪問 `/code/{user_id}/` → 重導向至登入頁

### G. 系統管理
19. admin 強制關閉某使用者容器 → 該使用者頁面立即收到 "Session ended"
20. admin 改某使用者配額為 100 GB → DB 與 lab_manager 立即生效

---

## 風險與緩解

| 風險 | 緩解 |
|------|------|
| **Docker socket 掛入 lab_manager 的安全風險** | lab_manager 跑在獨立容器，sandboxing；或改用 Docker API over TCP + TLS |
| **1000 人同時開 → CPU/RAM 爆炸** | 嚴格 idle 30min；admin 介面顯示資源使用率；極限可加 user quota（每人最多 1 個 session） |
| **shared_models 損壞影響所有人** | read-only 掛載；定期 snapshot；NFS-style 雙副本 |
| **VS Code Extension 開發成本高** | 用 TypeScript template，aibase-runner extension 不超過 500 行；先做 MVP 版本 |
| **code-server image 太大（含所有 extensions）** | 用 multi-stage build；參考 `linuxserver/code-server` 結構 |
| **base image build 失敗（CUDA 版本不相容）** | 各 image build script 加 CI gate；發佈前手動測試 GPU 可用 |
| **使用者 pip 衝突弄壞自己環境** | 提供 admin-ui「Reset Home Volume」按鈕（清空 ~/.local 與 ~/.cache，保留 projects/）|

---

## 明確留給 v2.1 的功能（在 docs/dev/v2.1-roadmap.md 詳細記錄）

| 項目 | 動機 | v2.1 估計工時 |
|------|------|--------------|
| **Jupyter 真 Kernel 模式** | 大模型互動式 debug、變數共享、邊訓練邊調整 | 3-5 天 |
| **多 GPU 任務支援**（`gpu_required > 1`） | 全量微調 7B+ 模型、研究生需求 | 1.5 天 |
| **多工作階段並行**（一人 N 個 code-server，各跑不同 image） | 同時開多專案的研究生 | 2 天（schema 已預留）|
| **互動式 GPU 池啟用** | 服務層 5090 給 Jupyter Kernel 用 | 1 天 |
| **自訂 image 註冊** | admin 註冊客製 image 給 legacy 專案 | 1.5 天 |
| **Devcontainer 支援** | `.devcontainer/devcontainer.json` 自動切換 image | 2 天 |
| **Secrets 金鑰輪換** | 安全週期 90 天輪換 KEK | 1 天 |
| **使用者間檔案分享 / 協作** | code-server Live Share | 待調研 |
| **Git 帳號綁定** | base image 預裝 git，未來可整合 GitHub OAuth | 待調研 |

## 已決定的設計細節（從原本的開放問題定案）

### 1. GPU 節點選擇 UI — Status Bar + Command Palette 並存

**決策**：兩者並存，Status Bar 為主、Command Palette 為輔。

| 入口 | 場景 |
|------|------|
| **Status Bar**（底部狀態列） | 永遠顯示「⚡ GPU: gpu-node-01 (45%) \| ⏱ Session 28 min」，點擊彈出選單。**預設主入口** |
| **Command Palette**（Ctrl+Shift+P）| 進階使用者鍵盤導向；輸入「AI Base: Select GPU Node」 |
| **Notebook Cell 旁 button** | 單格執行時臨時換節點 |

三者打開同一個 QuickPick 選單，列表項目為：
- ⚡ 各 GPU 節點（顯示 GPU 型號 × 數量、目前 utilization、可用 VRAM）
- 🔄 auto（讓 scheduler 自動決定）

### 2. Base Image 版本鎖定政策 — 學期鎖定 + 維護視窗（與 conda 雙層互補）

**決策**：採學期鎖定（`aibase/pytorch:2026-spring`），每學期升一次。**Base image 鎖定** 與 **使用者 conda env** 是**互補的雙層機制**，不是二選一。

#### 兩層分工

| 層次 | 對象 | 內容 | 升級頻率 | 啟動速度 |
|------|------|------|---------|---------|
| **Layer 1 — Base Image**（學期鎖定） | admin 管理 | 標準框架 + CUDA + 常用套件 | 學期一次 | < 10 秒（已預裝） |
| **Layer 2 — Conda Env**（使用者自管） | 使用者自由 | 各種特殊版本 / 舊 paper repro | 任意 | 第一次 10-30 分鐘，之後秒切 |

#### 為什麼不全部用 conda 取代 base image

- 🔴 conda 建 PyTorch env 要 10-30 分鐘 → 學生 1.5 小時 session 耗掉 1/3
- 🔴 cudatoolkit via conda 約 3 GB / 人 → 100 人 = 300 GB 重複（vs base image 共享 layer 僅 3 GB）
- 🔴 conda 解依賴常失敗（PyTorch + transformers + bitsandbytes 互相衝突）；base image 在 CI 已驗證
- 🟡 base image 系統級 PyTorch 經 build-time 優化，效能優於 conda 安裝

#### 為什麼不全部用 base image

- ❌ 學生想用 PyTorch 1.13 跑舊 paper repro → 沒這個 image 也不該硬塞
- ❌ 要 admin 為每個小眾需求加 image → image 數量爆炸（5 × 3 × 3 = 45 個）

#### 互補策略

```
99% 使用者 → 直接用 base image
   │
   ↓ 啟動快、穩定、共享資源
   
1% 特殊需求 → 從 base image 啟動，再用 conda 建專屬 env
   │
   ↓ 環境存在 ~/.conda/envs/，學期升級不受影響
```

#### 升級時的隔離保證

| 機制 | 學期升級影響 |
|------|------------|
| Base image 升級（spring → fall） | 預設容器換新；想用舊版的學生可在管理介面選 `pytorch:2026-spring`（舊 tag 保留一學期） |
| 使用者 conda env | **完全不受影響**（位於 home volume，與 base image 解耦） |
| 使用者 home volume / 檔案 | **完全不受影響** |

| 時機 | 動作 |
|------|------|
| 學期前 2 週（如 8/15、1/15） | admin pull 新版上游 image、跑測試、push 新 tag、提前公告 |
| 學期內 | 所有容器固定用該學期 tag，不變 |
| 學期末 | 評估升級內容、整理 changelog |

**安全更新例外**：
- 🔴 高危 CVE：學期中也升級，發信通知全體使用者
- 🟡 中度 patch：累積到下學期
- 🟢 minor：跳過

**重大版本變更**（如 PyTorch 2 → 3）：舊 tag 保留一學期，使用者可選舊版避免相容性問題。

學生 conda env 裝在 home volume，與 base image 解耦，升級時不受影響。

### 3. dev-tools Image 精簡程度 — v2.0 合併，v2.1 評估拆分

**決策**：v2.0 採單一大 image `aibase/dev-tools:latest`（約 3.5 GB after multi-stage 精簡）。

**內容**：
```
Python 3.11 + miniconda
CUDA toolkit 12.8 (nvcc, cublas, cudnn)
C/C++: gcc-11, g++-11, gdb, cmake, make, clang-15
Java: OpenJDK 17 + maven + gradle
Rust: rustc, cargo
Go: go 1.22
Node.js 18 + npm
通用: git, curl, wget, vim, htop, tmux, aria2, kaggle, huggingface-cli, gh
```

**理由**：
- ML 跨語言開發常態（CUDA + Python binding、Rust ML crates）
- 學生不用想「我該選哪個 image」
- image layer 在 GPU server 上共享，磁碟壓力不大
- 與 HuggingFace、NVIDIA NGC 業界趨勢一致

**精簡技巧**（multi-stage build）：
- Stage 1 裝 OS 套件 + 編譯工具
- Stage 2 只保留 binary、移除 apt cache、pip cache
- 預估 5 GB → 3.5 GB

**v2.1 評估標準**：若數據顯示 90% 學生只用 Python / 不用其他語言，再拆分為 `dev-cpp` / `dev-jvm` / `dev-rust` 等專用 image。

### 4. 教師批量資料注入 — 完整審計 + 學生知情權

**決策**：必須留完整 audit log，且學生有權查看與選擇拒收。

**審計記錄**（`admin_actions` 表已涵蓋，補強 payload）：
```python
AdminAction(
    admin_id="teacher-123",
    target_user="student-456",
    action="inject_files",
    payload=json.dumps({
        "project_name": "homework-3",
        "file_name": "dataset-v2.zip",
        "file_size_mb": 850,
        "file_sha256": "abc...",        # 防篡改校驗
        "extracted_files": [...],        # 解壓清單
        "extracted_total_size_mb": 1245
    }),
    timestamp="...",
    ip_address="192.168.1.5"            # 教師當時 IP
)
```

**三種視圖**：

| 視角 | 看得到 |
|------|--------|
| 教師自己 | admin-ui「我的注入紀錄」分頁：自己注入過的所有檔案、對象、時間 |
| 學生（被注入方） | 設定頁「收到的資料注入」清單：誰、何時、什麼檔案 |
| admin 全域 | audit log 完整查詢介面 |

**學生隱私保護**：
- 注入動作自動發 email 通知學生（學生可關閉）
- 學生設定頁可開「拒收注入」開關 → 教師再注入會被拒並通知雙方
- 注入紀錄保留 3 年（依資料保護法律）

**工時影響**：+0.5 天（教師注入邏輯 + 學生通知 email + 學生設定開關）

---

## 預估工作量

| 階段 | 工時 |
|------|------|
| A. 基礎設施（6 image + volume + nginx + 池分層） | 2.5 天（+0.5 因 dev-tools image + 池） |
| B. 後端 Lab Manager + Secrets + 配額/生命週期 | 5 天（+1.5 因配額提權 + 儲存狀態機 + audit）|
| C. VS Code Extension（含 Dataset Helper） | 3.5 天（+0.5 因 Dataset Helper） |
| D. 前端 + admin-ui + v2.1 roadmap 文件 | 3 天（+0.5 教師注入 + 學生通知/拒收開關）|
| E. 清理舊 Notebook + 文件 | 1 天 |
| **合計** | **約 15 工作天**（單人全職） |

可平行：A 與 C 可同時進行；B 必須等 A 的 image 大致就緒；D 可在 B 完成後立即跟上。
