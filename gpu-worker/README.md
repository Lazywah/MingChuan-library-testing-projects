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

Windows 用 `start-worker.bat`（用法相同）。Linux 首次可能要先給執行權限：`chmod +x start-worker.sh`（或改用 `bash start-worker.sh`）。

> ⚠️ 不要在本目錄直接 `docker compose up`。少了 `--env-file ../.env`，
> compose 會改用不安全的預設 token；為此 compose 已設 fail-fast，會**直接報錯**提醒你改用腳本。

## 遠端 GPU 主機（worker 與服務層不同機）

本機沒有根 `../.env`。做法：複製**根** `.env.example` 成一份本地 env 檔，至少填：

- `SERVICE_LAYER_URL`＝服務層主機的真實位址（例 `http://192.168.1.50:8002`）
- `WORKER_API_TOKEN`＝**與服務層根 .env 完全一致**（key 名就叫 `WORKER_API_TOKEN`，不是 `API_TOKEN`）
- `NODE_ID`＝此節點名稱；`POOL_TYPE`＝`batch` 或 `interactive`
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
