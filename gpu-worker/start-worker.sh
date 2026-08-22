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
# 遠端 GPU 主機（本機沒有根 .env）：用**本目錄的** worker.env.example，不要用根 .env.example：
#   cp worker.env.example worker.env      # 填好裡面標了「← 改我」的幾行
#   WORKER_ENV_FILE=./worker.env ./start-worker.sh
# 為什麼不用根 .env.example：那份 266 行、是整個平台的設定，而且它的預設值是給
# 「與服務層同機」用的 —— 其中 SHARES_SERVICE_STORAGE=true 照抄到遠端節點會造成
# 「不報錯但訓練結果沒有意義」（見 worker.env.example 裡的說明）。
# ==============================================================================
set -euo pipefail
cd "$(dirname "$0")"

ENV_FILE="${WORKER_ENV_FILE:-../.env}"

if [ ! -f "$ENV_FILE" ]; then
  echo "✗ 找不到環境檔 / env file not found: $ENV_FILE" >&2
  echo "  同機部署 / co-located: 先在 CodeSpace/ 執行 python scripts/setup_env.py 產生 ../.env" >&2
  echo "  遠端 GPU 主機 / remote: cp worker.env.example worker.env → 填好 → WORKER_ENV_FILE=./worker.env ./start-worker.sh" >&2
  exit 1
fi

# 無參數 → 預設 up -d / default to up -d when no args given
if [ "$#" -eq 0 ]; then
  set -- up -d
fi

echo "▶ docker compose --env-file $ENV_FILE $*"
docker compose --env-file "$ENV_FILE" "$@"
rc=$?

# ==============================================================================
# ZH: 啟動後檢查 —— 只對「會把 worker 跑起來」的子指令做。
#
# ZH: 為什麼需要這一段：`up -d` 回 0 只代表**容器建立成功**。設定填錯時
#     worker.py 的 run_startup_checks() 會 exit 1，容器隨即進入重啟迴圈，
#     但上面那行 compose 仍然只印一句 `Container mcu-gpu-worker Started`
#     —— 看起來完全正常。裝第 17 台的人不會知道要去 `docker logs`。
#
# ZH: 判準用**日誌裡的固定標記**而不是容器狀態：worker.py 兩條路各印一句，
#     成功印 "Config check passed"、被擋印 "Worker refuses to start"。
#     容器狀態在重啟迴圈裡取樣會忽 running 忽 restarting，不可靠。
#     兩句都等不到就說「判定不了」並把日誌尾巴印出來，不要謊報成功。
# ==============================================================================
case "${1:-}" in
  up|start|run|restart) ;;
  *) exit $rc ;;
esac
[ "$rc" -ne 0 ] && exit "$rc"

verdict=""
for _ in $(seq 1 20); do
  logs=$(docker logs --tail 80 mcu-gpu-worker 2>&1 || true)
  case "$logs" in
    *"Worker refuses to start"*) verdict=bad;  break ;;
    *"Config check passed"*)     verdict=good; break ;;
  esac
  sleep 1
done

if [ "$verdict" = "good" ]; then
  echo "✓ worker 已啟動，設定檢查通過 / worker running, config check passed"
  exit 0
fi

echo "" >&2
if [ "$verdict" = "bad" ]; then
  echo "✗ worker 拒絕啟動：設定有問題（詳見下方）/ worker refused to start" >&2
else
  echo "? 20 秒內看不到設定檢查的結果，先把日誌尾巴印出來 / could not confirm startup" >&2
fi
echo "------------------------------------------------------------------------------" >&2
docker logs --tail 40 mcu-gpu-worker 2>&1 >&2 || true
echo "------------------------------------------------------------------------------" >&2
exit 1
