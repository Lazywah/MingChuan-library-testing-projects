#!/usr/bin/env bash
# ==============================================================================
# GPU Worker 啟動包裝 / GPU Worker launcher
# ------------------------------------------------------------------------------
# 為什麼要這支：gpu-worker 的 compose 變數（WORKER_API_TOKEN / SERVICE_LAYER_URL…）
# 一律從「根目錄 .env」插值。若直接在本目錄 `docker compose up`，compose 會改讀
# 本地 gpu-worker/.env（易與根 .env 漂移 → 靜默 401）。本腳本強制帶 --env-file ../.env，
# 讓設定只有「單一來源＝根 .env」。
#
# 用法 / Usage：
#   ./start-worker.sh                 # 等同 up -d
#   ./start-worker.sh down            # 停止
#   ./start-worker.sh logs -f         # 看日誌
#   ./start-worker.sh <任何 compose 子指令>
#
# 遠端 GPU 主機（本機沒有根 .env）：把根 .env.example 複製成一份填好的 env 檔，再：
#   WORKER_ENV_FILE=/path/to/your.env ./start-worker.sh
# 該檔的 key 名稱請沿用根 .env.example（用 WORKER_API_TOKEN，不是 API_TOKEN）。
# ==============================================================================
set -euo pipefail
cd "$(dirname "$0")"

ENV_FILE="${WORKER_ENV_FILE:-../.env}"

if [ ! -f "$ENV_FILE" ]; then
  echo "✗ 找不到環境檔 / env file not found: $ENV_FILE" >&2
  echo "  同機部署 / co-located: 先在 CodeSpace/ 執行 python scripts/setup_env.py 產生 ../.env" >&2
  echo "  遠端 GPU 主機 / remote: 複製根 .env.example 填好後 → WORKER_ENV_FILE=<該檔> ./start-worker.sh" >&2
  exit 1
fi

# 無參數 → 預設 up -d / default to up -d when no args given
if [ "$#" -eq 0 ]; then
  set -- up -d
fi

echo "▶ docker compose --env-file $ENV_FILE $*"
exec docker compose --env-file "$ENV_FILE" "$@"
