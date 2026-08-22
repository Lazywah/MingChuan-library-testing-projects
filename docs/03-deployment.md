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
# 遠端 GPU 節點：建一份本地 env 檔（用「根 .env.example」的 key 名 —— 注意是 WORKER_API_TOKEN，不是 API_TOKEN）
cat > worker.env << 'EOF'
SERVICE_LAYER_URL=http://<服務層真實 IP>:8002    # 例 http://192.168.1.50:8002
WORKER_API_TOKEN=<與服務層「根 .env」的 WORKER_API_TOKEN 完全一致>
NODE_ID=gpu-node-01                                # 多節點請各自命名
POOL_TYPE=batch                                    # 服務層 5090 那台設 interactive
SHARES_SERVICE_STORAGE=false                       # 與服務層不同機 → false（單機部署才是 true）
DATASET_CACHE_MAX_GB=100                           # 依這台機器的磁碟調；GPU 主機這側沒有其他配額
IMAGE_REGISTRY_PREFIX=registry.mcu.edu.tw          # aibase/* 映像在服務層才有，這台要從 registry 拉
REGISTRY_USERNAME=aibase                           # 與服務層一致
REGISTRY_PASSWORD=<與服務層一致>

### 🔴 改過 gpu-worker 的程式碼 → 一定要 `build`

```bash
cd gpu-worker
./start-worker.sh build && ./start-worker.sh up -d

# 確認跑的真的是新版（對任何改動都成立，兩個值要一樣）
docker exec mcu-gpu-worker md5sum /app/worker.py
md5sum worker.py
```

`worker.py` 與 `builtin_scripts/` 是 COPY 進映像的（不是 bind mount，
因為 worker 要能在遠端主機獨立跑）。只跑 `up -d` 會用舊映像起來，
而 compose 只印 `Container mcu-gpu-worker Started`，看起來完全正常。

⚠️ 症狀**不會**長得像「忘了重建」：實際踩過的兩次分別是
「訓練指標永遠是空的」與「registry 設定好像沒生效」，兩次都先去查了別的地方。
確認方式見上面的雜湊比對——**不要**靠「log 有沒有印出某一行」，
那種檢查只對加那一行的當下有效。

> 服務層（job-scheduler）相反 —— `app/` 是 bind mount，
> `docker restart ai-platform-scheduler` 就生效，不必 build。**兩邊規則不同。**

### 私有 registry（多機部署才需要）

`aibase/*` 映像是在**服務層那台**用 `build-all.sh` 建出來的，不在任何公開 registry。
GPU 一搬到獨立主機，**「程式實驗室」與「上傳訓練」會一起停擺**——兩邊都指向這些映像。

服務層這側：

```bash
# 1. 填好根 .env 的 REGISTRY_USERNAME / REGISTRY_PASSWORD
bash infrastructure/registry/make-htpasswd.sh
docker compose --profile registry up -d registry     # 單機部署不需要這步
bash infrastructure/base-images/push-all.sh
```

GPU 主機那側：填 `IMAGE_REGISTRY_PREFIX` 與同一組帳密即可，worker 開機會自己登入。

⚠️ **registry 預設只綁 `127.0.0.1`。** 要讓遠端 GPU 主機連進來時：
- **建議**：走 nginx 的 TLS（與 SSO go-live 的憑證同一套），不要開明文埠
- 過渡做法：`REGISTRY_BIND=0.0.0.0`，並在每台 GPU 主機的 `/etc/docker/daemon.json`
  加 `{"insecure-registries": [...]}`。⚠️ 明文會把帳密送在網路上
- 沒有 registry 的替代方案：`docker save` / `docker load` 用檔案搬（土法，但一學期一次可接受）

⚠️ **沒有帳密的 registry 是一條遠端執行路徑** —— 任何人都能推一個映像進來，
而它之後會在你的 GPU 主機上以 `--gpus` 執行。缺 htpasswd 檔時 registry 容器會直接起不來。

STORAGE_MOUNT_PATH=/mnt/storage                    # Linux 路徑；Windows 用 C:\storage
GPU_IDLE_UTIL_THRESHOLD=90
POLL_INTERVAL=5
HEARTBEAT_INTERVAL=30
EOF

# 用包裝腳本啟動（自動帶 --env-file，避免忘記；Windows 用 start-worker.bat）
WORKER_ENV_FILE=worker.env ./start-worker.sh up -d --build
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
| **OIDC** | **現行正式模式**（MCU 自建 OIDC `auth.mcu.edu.tw`）| IdP | 「使用學校帳號登入」按鈕 |

切換 provider 只需改 `job-scheduler/app/sso_policy.yaml`，**不必動程式碼**：
```yaml
mock_mode: false         # 正式環境改 false
provider: oidc           # mock | cas | oidc
```

改完 `docker compose restart job-scheduler`。

### 2.2 OIDC（MCU 自建 OIDC — 現行正式模式）

> ⚠️ **v3.1 重大更正**：MCU 用的是**自建 OIDC 伺服器 `auth.mcu.edu.tw`**，
> **不是** Microsoft Entra ID。早期文件寫的 tenant_id / Entra 設定已失效
> （實測會得到 `AADSTS700016：application not found in directory`）。

**前置**：向學校 IT 申請，索取 `client_id`、`client_secret`，並請他們在 IdP 註冊 redirect URI。

**端點不需手動設定**：程式啟動時自動從 discovery 取得
（`https://auth.mcu.edu.tw/.well-known/openid-configuration` → authorize / token / userinfo / jwks）。

**憑證只放 `.env`**（`sso_policy.yaml` 進版控，永遠維持 `PENDING` 佔位）：
```
OIDC_CLIENT_ID=<IT 提供>
OIDC_CLIENT_SECRET=<IT 提供>
OIDC_REDIRECT_URI=http://localhost/api/v1/sso/oidc/callback
OIDC_DISCOVERY_URL=            # 留空＝用 sso_policy.yaml 內建的 auth.mcu.edu.tw
```

**身分對應**：MCU 的 userinfo **只回 `{"sub": "<學號>"}`**（無 email、無姓名），
故 `username_claim: "sub"`，email 由 `email_domain: "me.mcu.edu.tw"` 補成 `<學號>@me.mcu.edu.tw`。

> **PENDING fail-safe**：憑證未填時系統自動降級 mock 並記 **error** log，服務不會崩；
> `/api/v1/sso/providers` 會回 `[]`，登入頁顯示「系統登入功能尚在設定中」。

---

### 2.3 ⚠️ 部署範圍：redirect_uri 決定「誰能用」

**`redirect_uri` 是給「瀏覽器」去的地址，不是給伺服器的**——這是它與 `SERVICE_LAYER_URL`
那種機器對機器設定最不一樣、也最容易誤解的地方。

| redirect_uri | 誰能登入 | 說明 |
|---|---|---|
| `http://localhost/...` | **只有坐在伺服器前面的人** | `localhost` 永遠指「開瀏覽器的那台電腦」。學生從自己的筆電登入時，IdP 會把他導回**他自己的** localhost → 失敗 |
| `https://<主機名>/...` | 任何連得到該主機名的人 | ✅ 正式上線用 |

**目前狀態（dev）＝ 學生端實質單機**：`web-ui` 自 v2.1 起**已無本機帳密表單**，
學生沒有 SSO 以外的登入途徑，故其他電腦完全無法使用。

**不受此限制的部分**（不經瀏覽器，機器對機器）：
- **GPU worker**：主動連 `SERVICE_LAYER_URL`，**現在就能跨機部署**（見 §1）
- MYAI 同步等對外 API 呼叫

**admin (:8888) 可跨機登入**（走本機帳密、不經 SSO），但**目前是 http**，
**管理員密碼會明文經過網路** → 補上 HTTPS 前，建議 admin 也只在伺服器本機使用。

### 2.4 開放給其他電腦需要的四件事

1. **真實主機名**（如 `ai.lib.mcu.edu.tw`）+ 內網 DNS 解析 —— 學校 IT
2. 該主機名的 **TLS 憑證**（校內 CA 簽發即可）—— 學校 IT
3. **nginx 加 `:443`** 監聽並掛憑證 —— 我方（目前只有 `:80` / `:8888`）
4. 請 IT 在 IdP **加註冊** `https://<主機名>/api/v1/sso/oidc/callback`（dev 那筆可並存）

> **為什麼一定要 HTTPS（不只是 IdP 政策）**：登入成功後平台是以
> `/V0/?sso_token=<JWT>` 把權杖交給前端——**權杖寫在網址列上**。
> 走 http 的話，同網段的人側錄封包即可取得該 token 並冒充該使用者（效期 2 小時）。
> 這與「密碼有沒有加密」無關，token 本身就是通行證。
>
> **能不能用 IP + http 代替？** OIDC 規範本身不禁止，`auth.mcu.edu.tw` 的 discovery
> 也未宣告限制 —— **收不收要問 IT**。但即使可行也不建議：上述 token 明文問題依舊，
> 且 IP 會變（每變一次就要麻煩 IT 重新註冊）、校內 CA 實務上不簽裸 IP。

### 2.5 CAS（其他學校）

```yaml
provider: cas
cas:
  server_url: "https://cas.your-school.edu.tw/cas"
  service_url: "https://your-domain.edu.tw/api/v1/sso/callback"
  version: "3.0"
```

### 2.6 Mock（開發）

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

### 2.7 密碼變更行為

依使用者 `auth_source` 自動分流：
- `local` → user UI 顯示舊密碼 + 新密碼表單
- `sso_oidc` → user UI 顯示「密碼由學校系統統一管理」+「忘記密碼」導向學校中央入口
  `https://www1.mcu.edu.tw/ForgetPassword.aspx`（學號＋身分證字號 → 新密碼寄校務系統信箱）
- `sso_cas` → 顯示「請至學校 CAS 系統變更」
- `sso_mock` → 顯示「Mock 帳號無密碼可變」

### 2.8 yaml 改動會影響使用者管理嗎？

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
| `WORKER_API_TOKEN` | dev-default | 隨機（gpu-worker 讀同一份根 .env，不再有 gpu-worker/.env）|
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
