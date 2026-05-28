# 03 — 部署 | Deployment

涵蓋：GPU 工作節點、SSO 整合（3 種模式）、Windows 測試 → Ubuntu 上線轉換。

> 服務層的基本部署見 [`01-quick-start.md`](01-quick-start.md)。本文只說「擴充節點」與「上線前要改的東西」。

---

## 1. 加 GPU 工作節點

### 1.1 需求
| 項目 | 需求 |
|---|---|
| OS | Windows 11 + WSL2，或 Ubuntu 22.04+ |
| GPU | NVIDIA + 驅動 ≥570（CUDA 12.8 對應）|
| RAM | 256 GB+（單機跑大模型）；中等模型 32-64 GB 即可 |
| Docker | Docker Desktop（Win）/ Docker Engine（Ubuntu）|
| NVIDIA Container Toolkit | 必裝（Win 由 Docker Desktop 自動，Ubuntu 需手動）|

**Windows**：`wsl --install` → 重啟 → 裝 Docker Desktop 勾「Use WSL 2」→ 驗證：
```powershell
docker run --rm --gpus all nvidia/cuda:12.3.0-base-ubuntu22.04 nvidia-smi
```

**Ubuntu**：
```bash
sudo apt-get install -y nvidia-container-toolkit
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
docker run --rm --gpus all nvidia/cuda:12.3.0-base-ubuntu22.04 nvidia-smi
```

### 1.2 設定 worker

複製 `gpu-worker/` 整個資料夾到 GPU 節點，然後：

```bash
cd gpu-worker
# 編輯 .env（從 setup_env.py 產的那份複製過來，或重跑 setup 選 Mode 2 分機）
cat > .env << 'EOF'
SERVICE_LAYER_URL=http://<服務層真實 IP>:8002    # 例 http://192.168.1.50:8002
API_TOKEN=<與服務層 .env 的 WORKER_API_TOKEN 完全一致>
NODE_ID=gpu-node-01                                # 多節點請各自命名
POLL_INTERVAL=5
HEARTBEAT_INTERVAL=30
STORAGE_MOUNT_PATH=C:\storage                      # Win 路徑或 Linux 路徑
EOF

docker compose up -d --build
docker logs -f mcu-gpu-worker
```

正常會看到：
```
[heartbeat] node=gpu-node-01 GPU=... → 200 OK
[poll] no pending jobs
```

> ⚠️ `API_TOKEN` 必須與服務層 `.env` 的 `WORKER_API_TOKEN` **逐字相同**，否則所有請求 401。

### 1.3 單機（all-in-one）特殊設定

服務層與 GPU worker 同一台機器：
- Windows / macOS：`SERVICE_LAYER_URL=http://host.docker.internal:8002`
- Linux：`SERVICE_LAYER_URL=http://172.17.0.1:8002`

或直接讓 worker 加入同個 docker network（編 `gpu-worker/docker-compose.yml` 加 `networks: [ai-platform-net]`），然後用 `SERVICE_LAYER_URL=http://job-scheduler:8000`。

### 1.4 共享儲存

訓練腳本 / dataset 存在服務層的 `data/` 目錄。GPU 節點透過 SMB / NFS 掛載：
- Windows GPU + Ubuntu 服務層 → 服務層裝 Samba，GPU 用 `\\<ip>\storage` 對應到 `C:\storage`
- Ubuntu GPU + Ubuntu 服務層 → 服務層 export NFS，GPU `mount -t nfs ...`

GPU 容器啟動時 `-v C:\storage:/workspace` 把這份共享目錄餵給訓練容器。

---

## 2. SSO 整合（3 種 provider）

### 2.1 三種模式比較

| 模式 | 適用 | 密碼存放 | UI 入口 |
|---|---|---|---|
| **Mock** | 開發 / 測試 | yaml 明文 | 不曝光按鈕；直接打 `/api/v1/sso/login` |
| **CAS** | 學校用 Yale CAS | 學校 LDAP/AD | 「使用學校帳號登入」按鈕 |
| **OIDC** | Microsoft 365 / Google / Keycloak | IdP | 「使用學校帳號登入」按鈕 |

切換 provider 只需改 `job-scheduler/app/sso_policy.yaml`，**不必動程式碼**：
```yaml
mock_mode: false         # 正式環境改 false
provider: oidc           # mock | cas | oidc
```

改完 `docker compose restart job-scheduler`。

### 2.2 OIDC（Microsoft Entra ID）

**前置**：請 IT 在 Microsoft Entra Admin Center 註冊 App Registration，索取：
- `client_id`、`client_secret`
- `redirect_uri` 需登記為：`http(s)://<服務層 domain>:8002/api/v1/sso/oidc/callback`
- 建議一次申請 dev (`localhost`) + prod 兩個 redirect_uri

填入 `sso_policy.yaml`：
```yaml
provider: oidc
oidc:
  tenant_id: "30f2f0eb-3fc8-4a5a-94b5-fffa8944532e"   # MCU 範例（公開資訊）
  client_id: "<IT 給的 client_id>"
  client_secret: "<IT 給的 client_secret>"            # 敏感，建議改放 .env
  redirect_uri: "https://your-domain.edu.tw/api/v1/sso/oidc/callback"
  scopes: ["openid", "email", "profile"]
  password_change_url: "https://account.activedirectory.windowsazure.com/ChangePassword.aspx"
  password_reset_url:  "https://passwordreset.microsoftonline.com/"
```

> **PENDING fail-safe**：`client_id="PENDING"` 時系統自動降級 mock + warning，不會崩。等 IT 給才填真值。

### 2.3 CAS（其他學校）

```yaml
provider: cas
cas:
  server_url: "https://cas.your-school.edu.tw/cas"
  service_url: "https://your-domain.edu.tw/api/v1/sso/callback"
  version: "3.0"
```

### 2.4 Mock（開發）

```yaml
mock_mode: true        # 或 provider: mock
mock:
  users:
    - student_id: "T1090001"
      password: "T1090001"
      name: "林小明"
      email: "T1090001@school.edu.tw"
      role: "student"
```

> Mock SSO **不在 UI 出現按鈕**（避免 admin 用別人身分登入）。dev 直接打 `http://localhost/api/v1/sso/login` 進入。

### 2.5 密碼變更行為

依使用者 `auth_source` 自動分流：
- `local` → user UI 顯示舊密碼 + 新密碼表單
- `sso_oidc` → user UI 顯示「請至 Microsoft 變更密碼」連結
- `sso_cas` → 顯示「請至學校 CAS 系統變更」
- `sso_mock` → 顯示「Mock 帳號無密碼可變」

### 2.6 yaml 改動會影響使用者管理嗎？

- **改 / 新增 mock user**：不影響既有 DB 使用者；影響「未來首次 mock SSO 登入」的人
- **從 yaml 移除 mock user**：使用者管理列表會 filter 掉（DB row 仍保留，避免破壞聊天歷史 FK）

詳見 [`05-api-reference.md`](05-api-reference.md) 的 SSO 章節。

---

## 3. 跨 OS 注意事項

服務層所有元件都跑 Docker → **Windows / Linux / macOS 完全相容**，唯一差異只在「安裝 Docker 的方式」與「shell 指令格式」。

| 元素 | Windows | Linux | macOS |
|---|---|---|---|
| Docker 安裝 | Docker Desktop + WSL2 | `apt install docker.io docker-compose-v2` | Docker Desktop |
| compose 指令 | `docker compose ...`（新版）或 `docker-compose ...`（舊）| `docker compose ...` | `docker compose ...` |
| Bash 腳本 | 需 Git Bash / WSL | 原生 | 原生 |
| 路徑 | `C:\storage` 或 `/c/storage` | `/mnt/storage` | `/Users/.../storage` |
| `host.docker.internal` | ✅ 支援 | ❌ 用 `172.17.0.1` | ✅ 支援 |

---

## 4. Windows 測試 → Ubuntu 正式上線

### 4.1 .env 必改項目

| 變數 | 開發值 | 上線值 |
|---|---|---|
| `JWT_SECRET_KEY` | dev-default | **`secrets.token_urlsafe(48)`** 隨機 |
| `WORKER_API_TOKEN` | dev-default | 隨機 + 同步到 gpu-worker/.env |
| `SECRETS_MASTER_KEY` | dev-default | 隨機（變更會讓既有 secrets 全失效）|
| `WEBUI_SECRET_KEY` | dev-default | 隨機 |
| `CORS_ORIGINS` | 空（允許全部）| 明確列出正式 domain |
| `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `GOOGLE_API_KEY` | placeholder | 真實 API key |
| SMTP_* | 空 | 學校 SMTP 設定 |

> 最快做法：上線前重跑 `python scripts/setup_env.py` 生新的 `.env`（會自動備份舊的）。

### 4.2 scheduler_policy.yaml

```yaml
mock_mode: false
default_image: aibase/code-server:2026-spring   # 不要設成 pytorch (entrypoint 是 /bin/bash 會立刻 exit)
```

### 4.3 防火牆（Ubuntu）

```bash
sudo ufw allow 22/tcp        # SSH
sudo ufw allow 80/tcp        # User UI
sudo ufw allow 8888/tcp      # Admin UI（建議限制來源 IP）
sudo ufw enable
```

服務層的 `/api/v1/worker/*` 路由建議透過 nginx 限制 IP 來源（只允許 GPU 節點 IP）。

### 4.4 上線檢查清單

- [ ] `.env` 所有 secrets 都改成隨機（`python scripts/setup_env.py --check` 驗證）
- [ ] `sso_policy.yaml` `provider: oidc`（或 cas）且 `client_id` 已填
- [ ] `redirect_uri` 已在 IdP 註冊
- [ ] GPU worker 的 `SERVICE_LAYER_URL` + `API_TOKEN` 一致
- [ ] 防火牆設定完成
- [ ] HTTPS 證書（Let's Encrypt + Certbot）
- [ ] SMTP 可寄信
- [ ] admin 密碼夠強且只有 IT 知道
- [ ] DB 備份排程已建（見 [`04-operations.md`](04-operations.md)）
- [ ] Lab base image 已 build 或 deploy 上線時間

---

## 5. （選用）AI Models 推理層

`docker compose -f docker-compose.ai-models.yml up -d` 啟動：
- **open-webui** (port 3000)：LLM 對話 UI
- **portkey** (port 8000)：API gateway 分流到 Anthropic / OpenAI / Google
- **ollama** (port 11434)：本地推理引擎

GPU 加速 ollama（Ubuntu + NVIDIA）：編輯 `docker-compose.ai-models.yml` 取消註解 `runtime: nvidia` + `NVIDIA_VISIBLE_DEVICES=all`。

---

## 下一步

- [`04-operations.md`](04-operations.md) — 部署完之後的日常維運（備份、監控、配額）
- [`08-status-and-roadmap.md`](08-status-and-roadmap.md) — 已知議題（Lab 同網段安全、Jobs polling 等）
