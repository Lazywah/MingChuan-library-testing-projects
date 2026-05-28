# 01 — 快速啟動 | Quick Start

從零（沒裝過這專案的電腦）跑到「能用 admin 帳號登入」。預計 **30-60 分鐘**。

---

## 1. 硬體與軟體需求

| 角色 | CPU | RAM | 磁碟 | GPU |
|---|---|---|---|---|
| **服務層**（你要部署的這台） | 4 核+ | 8 GB+ | 50 GB+ SSD | 不需要 |
| **GPU 工作節點**（可在另一台） | — | — | 100 GB+ | NVIDIA + ≥12 GB VRAM |

軟體：Docker 24+、Docker Compose v2+、Python 3.9+（只用來跑 setup 腳本）、Git。

> 想單機跑全套（服務層 + GPU）也可，但 GPU 必須是 NVIDIA + 安裝 NVIDIA Container Toolkit。

---

## 2. 安裝 Docker

### Windows 11
1. 下載 [Docker Desktop](https://www.docker.com/products/docker-desktop/)
2. 安裝時勾「Use WSL 2 instead of Hyper-V」
3. 重開機 → 啟動 Docker Desktop → 等右下角圖示變綠
4. 驗證：`docker version` / `docker compose version`

### Ubuntu 22.04 / 24.04
```bash
sudo apt update
sudo apt install -y docker.io docker-compose-v2
sudo usermod -aG docker $USER && newgrp docker
docker version
```

### macOS
下載 Docker Desktop for Mac → 拖到 Applications → 啟動。

---

## 3. 取得程式碼

```bash
git clone <repo-url> CodeSpace
cd CodeSpace
```

確認看到：`admin-ui/  gpu-worker/  job-scheduler/  web-ui/  infrastructure/  docs/  scripts/  docker-compose.yml`

---

## 4. 產生 `.env`

```bash
python scripts/setup_env.py
```

腳本會問你：

| 提示 | 建議答案 |
|---|---|
| 服務層 IP | 開發機用 `127.0.0.1`；區網部署填區網 IP（例 `192.168.1.50`）|
| Token 月度配額 | 預設 `5000000` (5M / user / 月) |
| Job 超時（分） | 預設 `120` |
| LOG_LEVEL | `INFO` |
| SMTP | 學生環境可跳過（直接 Enter）|
| GPU Worker .env | 單機部署選「[1] 單機 all-in-one」自動帶 `host.docker.internal` |

腳本會：
- 用 `secrets.token_urlsafe()` 生 `JWT_SECRET_KEY` / `WORKER_API_TOKEN` / `WEBUI_SECRET_KEY` / `SECRETS_MASTER_KEY`（v2.0 Lab 用）
- 寫入 `./.env` 與 `./gpu-worker/.env`（兩邊 token 自動對齊）
- 備份既有 `.env` 為 `.env.bak_YYYYMMDD_HHMMSS`

> **已有 .env、只想補新欄位**：`python scripts/setup_env.py --check`（只追加缺漏 key，不覆寫既有值）

---

## 5. 啟動服務

```bash
docker compose up -d --build      # 第一次 build 約 3-8 分鐘
docker compose ps
```

預期看到 2 個 `Up (healthy)` 容器：
- `ai-platform-nginx` → ports `80`, `8888`
- `ai-platform-scheduler` → port `8002`

驗證：
```bash
curl http://localhost/health      # → "OK"
```

---

## 6. 開啟介面（此時還沒帳號）

| URL | 用途 |
|---|---|
| http://localhost/train/ | 使用者介面 |
| http://localhost:8888/ | 管理員介面 |
| http://localhost:8002/docs | API Swagger |

此時看得到登入頁但無法登入 — 下一步建第一個 admin。

---

## 7. 建立第一個 admin（Bootstrap）

> 系統**沒有預設的 admin/admin**（v2.1 安全強化）。第一個 admin 必須從 DB 寫入。

```bash
docker compose exec job-scheduler python -c "
from app.database import SessionLocal
from app.crud import get_password_hash
from app import models
from datetime import datetime, timezone, timedelta

db = SessionLocal()

# === 改這 3 行 ===
ADMIN_USERNAME = 'admin'
ADMIN_EMAIL    = 'admin@school.edu.tw'
ADMIN_PASSWORD = 'CHANGE_THIS_STRONG_PASSWORD'   # 至少 12 字元
# =================

if db.query(models.User).filter(models.User.username == ADMIN_USERNAME).first():
    print(f'User {ADMIN_USERNAME} already exists, skipping.')
else:
    user = models.User(
        username=ADMIN_USERNAME, email=ADMIN_EMAIL,
        hashed_password=get_password_hash(ADMIN_PASSWORD),
        role='admin', is_active=1,
    )
    db.add(user); db.flush()
    quota = models.TokenUsage(
        user_id=user.id, tokens_used=0, tokens_limit=99_000_000,
        reset_date=datetime.now(timezone.utc) + timedelta(days=30),
    )
    db.add(quota); db.commit()
    print(f'Admin created: {user.id} / {ADMIN_USERNAME}')
db.close()
"
```

然後用 admin 帳號登入 http://localhost:8888/ → 設定 → 變更密碼。

---

## 8. 建立一般使用者（4 種方式）

### A. 管理員 UI（推薦）
admin UI → 使用者管理 → Provision User → 填 username/email/role → 系統寄臨時密碼信（需 SMTP）

### B. 學生自助註冊
http://localhost/train/ → 註冊 → 強制 `role=student`（schema 層擋下，無法手動改 admin）

### C. 批次匯入（Python）
範例見 `docs/archive/PLAN-v2.1-sso-oidc.md` 或直接：
```bash
docker compose exec job-scheduler python << 'EOF'
from app.database import SessionLocal
from app.crud import get_password_hash
from app import models
from datetime import datetime, timezone, timedelta

USERS = [
    ('T1090001', 'T1090001@school.edu.tw', 'temp_pw_xxx'),
    # ...
]
db = SessionLocal()
for u, e, p in USERS:
    if db.query(models.User).filter(models.User.username == u).first(): continue
    user = models.User(username=u, email=e, hashed_password=get_password_hash(p),
                       role='student', is_active=1)
    db.add(user); db.flush()
    db.add(models.TokenUsage(user_id=user.id, tokens_used=0, tokens_limit=5_000_000,
                             reset_date=datetime.now(timezone.utc)+timedelta(days=30)))
db.commit(); db.close()
EOF
```

### D. Mock SSO（dev 環境最快）
`job-scheduler/app/sso_policy.yaml` 預設 2 個學生：T1090001 / T1090002。直接打 http://localhost/api/v1/sso/login → 下拉選 → 自動建帳號。

---

## 9. （選用）建立 Lab base images

> 想用 **v2.0 Lab**（VS Code in Browser）才需要。**只建 code-server 就能用**（10 分鐘）；全套 7 個 image 需 30-60 分鐘。

```bash
# 最小可用：只 build code-server
docker build -t aibase/code-server:2026-spring \
    -f infrastructure/base-images/code-server/Dockerfile .

# 全套：含 PyTorch / TensorFlow / HuggingFace / llama.cpp / vLLM / dev-tools
bash infrastructure/base-images/build-all.sh
```

驗證：登入 → 運算任務 → Notebook → 選 image → 點「開啟 Notebook」→ 跳到 `/code/<uid>/` 看到 VS Code 即成功。

---

## 10. 常見問題

| 症狀 | 修法 |
|---|---|
| `JWT_SECRET_KEY uses an insecure default value` | 重跑 `python scripts/setup_env.py` |
| `SECRETS_MASTER_KEY must be set` | `python scripts/setup_env.py --check` 補欄位 |
| `error while interpolating ...` | 同上，缺 env 變數 |
| scheduler 不 healthy | `docker compose logs job-scheduler --tail 30` |
| 忘記 admin 密碼 | 重跑 §7 但加 `admin.hashed_password = get_password_hash('NEW_PW')` |
| 要重新開始（清空所有資料）| `docker compose down -v && rm -rf data/ai_platform.db && docker compose up -d --build` ⚠️ 不可逆 |
| Notebook 點開 502 | base image 沒 build，看 §9 |

---

## 下一步

- [`02-architecture.md`](02-architecture.md) — 了解三層架構與各模組關係
- [`03-deployment.md`](03-deployment.md) — GPU 工作節點 / SSO 整合 / 正式上線
- [`04-operations.md`](04-operations.md) — 備份、監控、配額管理
- [`06-user-guide.md`](06-user-guide.md) — 給使用者的操作手冊
