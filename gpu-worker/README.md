# GPU Worker

GPU 訓練節點。設定**單一來源＝根目錄 `../.env`**（由 `scripts/setup_env.py` 產生），
本目錄**不再放自己的 `.env`**（舊做法會與根 .env 漂移 → token 對不上 → 靜默 401）。

## 啟動（同機部署，最常見）

一律用包裝腳本，它會自動帶 `--env-file ../.env`：

```bash
./start-worker.sh            # 啟動（= up -d）
./start-worker.sh logs -f    # 看日誌
./start-worker.sh down       # 停止
```

### 🔴 改過 worker 的程式碼？**一定要先 build**

```bash
./start-worker.sh build      # 先重建映像
./start-worker.sh up -d      # 再起來
```

`worker.py` 與 `builtin_scripts/` 是 **COPY 進映像**的（不是 bind mount，
因為 worker 要能在遠端主機獨立跑）。所以只跑 `up -d` 會用**舊映像**起來——
而 compose 只會印一行 `Container mcu-gpu-worker Started`，看起來完全正常。

⚠️ **症狀不會長得像「忘了重建」。** 實際踩過兩次：

| 實際看到的症狀 | 容易誤判成 | 真正的原因 |
|---|---|---|
| 訓練指標永遠是空的 | 回報那段程式碼寫錯了 | 容器裡是舊的 `worker.py`，沒有 `parse_metric` |
| registry 設定好像沒生效 | env 沒傳進容器 | 同上，舊映像裡沒有那段程式碼 |

兩次都是先往別的方向查了一陣子才發現。

**永遠有效的確認方法**——比對容器裡的檔案與磁碟上的檔案：

```bash
docker exec mcu-gpu-worker md5sum /app/worker.py
md5sum worker.py                     # 兩個值要一樣
```

（不要靠「log 有沒有印出某一行」來判斷。那種檢查只對加那一行的當下有效，
下一次改動就分辨不出來了。雜湊比對對任何改動都成立。）

> ZH: 服務層（job-scheduler）**不一樣** —— 它的 `app/` 是 bind mount，
> 改完 `docker restart ai-platform-scheduler` 就會生效，不必 build。
> 兩邊規則不同，是這個坑好踩的原因之一。

Windows 用 `start-worker.bat`（用法相同）。Linux 首次可能要先給執行權限：`chmod +x start-worker.sh`（或改用 `bash start-worker.sh`）。

> ⚠️ 不要在本目錄直接 `docker compose up`。少了 `--env-file ../.env`，
> compose 會改用不安全的預設 token；為此 compose 已設 fail-fast，會**直接報錯**提醒你改用腳本。

## 遠端 GPU 主機（worker 與服務層不同機）

本機沒有根 `../.env`。用**本目錄的** `worker.env.example`：

```bash
cp worker.env.example worker.env     # Windows：copy worker.env.example worker.env
# 把裡面標了「← 改我」的幾行填好
WORKER_ENV_FILE=./worker.env ./start-worker.sh
```

> 🔴 **不要複製根 `.env.example`。** 那份 266 行、是整個平台的設定，
> 而且它的預設值是給「與服務層同機」用的。三個鍵的正確值是**相反**的：
>
> | 鍵 | 根 `.env.example` | 遠端節點正確值 | 照抄的後果 |
> |---|---|---|---|
> | `SERVICE_LAYER_URL` | `http://ai-platform-scheduler:8000` | 真實 IP:8002 | 容器內部名，遠端解析不到 |
> | `SHARES_SERVICE_STORAGE` | `true` | `false` | 🔴 **不報錯**，訓練結果沒有意義 |
> | `NODE_ID` | `gpu-node-01` | 每台各自命名 | 多台互相蓋寫心跳 |
>
> 這三項填錯的話，worker 開機時會**拒絕啟動**並說明原因
> （`worker.py::validate_config`），不會帶著錯的設定跑起來。

還是想知道每一個鍵的意思的話：

- `SERVICE_LAYER_URL`＝服務層主機的真實位址（例 `http://192.168.1.50:8002`）
- `WORKER_API_TOKEN`＝**與服務層根 .env 完全一致**（key 名就叫 `WORKER_API_TOKEN`，不是 `API_TOKEN`）
- `NODE_ID`＝此節點名稱；`POOL_TYPE`＝`batch` 或 `interactive`
- `IMAGE_REGISTRY_PREFIX` ← **這一節（不同機）幾乎一定要填**（例 `registry.mcu.edu.tw`）。
  `aibase/*` 映像是在**服務層那台**建出來的，不在任何公開 registry，這台拉不到。
  症狀是每張任務都失敗在 `docker run`，訊息是 `manifest unknown` 或 `pull access denied`。
  留空＝用本機映像（那是單機部署的情形）。
- `REGISTRY_USERNAME` / `REGISTRY_PASSWORD` ← 與服務層一致。worker 開機會自己 `docker login`。
- ⚠ **明文 HTTP 的 registry**：這台的 docker daemon 要加
  `{"insecure-registries": ["registry.mcu.edu.tw:5000"]}`。兩個平台位置不同：
  - **Linux**：改 `/etc/docker/daemon.json` 再 `systemctl restart docker`
  - **Windows（Docker Desktop）**：Settings → Docker Engine 的 JSON 編輯器，
    改完按 Apply & restart。**沒有 `/etc/docker/daemon.json` 這個檔**，
    在 WSL 裡建一個也不會生效。
  正式環境**建議改走 nginx 的 TLS**，不要用明文——帳密會送在網路上。
- `DATASET_CACHE_MAX_GB` ← **依這台機器的磁碟大小調**（預設 100 GB）。
  這台機器上**沒有任何配額擋著**（服務層那側有每人 2 GB，這裡沒有）：
  資料集快取與訓練產出不清會一路長到磁碟滿，而症狀是「訓練突然全部失敗」。
  worker 每 6 小時自己清一次，判準見 `worker.py::reap_host_storage`。
- `SHARES_SERVICE_STORAGE=false` ← **這一節（不同機）必填 false**。
  設 true 會讓服務層把「程式實驗室」的任務派過來，而那些任務要讀使用者的
  `home_<uid>` Docker volume；那個 volume 在服務層那台。docker 會在**這台**
  自動建立一個**空的**同名 volume：不報錯、資料不在、訓練出沒有意義的結果。
- `STORAGE_MOUNT_PATH`＝此宿主機的共享儲存路徑（Linux 不可留 `C:\...`）

然後：

```bash
WORKER_ENV_FILE=/path/to/your.env ./start-worker.sh
```

## 檢查設定漂移 / token 是否一致

在 `CodeSpace/` 執行：

```bash
python scripts/setup_env.py --check
```
