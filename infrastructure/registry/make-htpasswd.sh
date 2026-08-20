#!/usr/bin/env bash
# ==============================================================================
# ZH: 產生私有 registry 的帳密檔 / Generate the private registry's htpasswd file
# ==============================================================================
# ZH: 為什麼一定要有：沒有帳密的 registry 等於讓網路上任何人把映像推進來，
#     而那些映像之後會在你的 GPU 主機上以 `--gpus` 執行。那是一條遠端執行路徑。
#
# ZH: registry 容器**沒有這個檔就起不來**（REGISTRY_AUTH=htpasswd 指向它），
#     所以「忘了跑這支」的結果是大聲失敗，不是安靜地開放。
#
# 用法 / Usage：
#   bash infrastructure/registry/make-htpasswd.sh              # 從 ../../.env 讀帳密
#   REGISTRY_USERNAME=x REGISTRY_PASSWORD=y bash ...           # 或用環境變數
# ==============================================================================
set -euo pipefail
cd "$(dirname "$0")"

ENV_FILE="../../.env"

# ZH: 沒帶環境變數就從根 .env 讀（設定單一來源＝根 .env，與 start-worker.sh 同一個原則）
if [ -z "${REGISTRY_USERNAME:-}" ] && [ -f "$ENV_FILE" ]; then
  REGISTRY_USERNAME="$(grep -E '^REGISTRY_USERNAME=' "$ENV_FILE" | head -1 | cut -d= -f2- || true)"
fi
if [ -z "${REGISTRY_PASSWORD:-}" ] && [ -f "$ENV_FILE" ]; then
  REGISTRY_PASSWORD="$(grep -E '^REGISTRY_PASSWORD=' "$ENV_FILE" | head -1 | cut -d= -f2- || true)"
fi

if [ -z "${REGISTRY_USERNAME:-}" ] || [ -z "${REGISTRY_PASSWORD:-}" ]; then
  echo "✗ 找不到 REGISTRY_USERNAME / REGISTRY_PASSWORD" >&2
  echo "  請先填進根 .env，或用環境變數帶進來：" >&2
  echo "  REGISTRY_USERNAME=aibase REGISTRY_PASSWORD='<夠長的密碼>' bash $0" >&2
  exit 1
fi

# ZH: 密碼太短的話這整套保護等於沒有 —— 在這裡擋，不要等到被推了才知道。
if [ "${#REGISTRY_PASSWORD}" -lt 12 ]; then
  echo "✗ REGISTRY_PASSWORD 太短（${#REGISTRY_PASSWORD} 字元，至少 12）" >&2
  echo "  這組密碼保護的是一條「別人可以把映像塞進你 GPU 主機」的路徑。" >&2
  exit 1
fi

mkdir -p auth

# ZH: 用 registry:2 自帶的 htpasswd（-B ＝ bcrypt，registry 只認這個）。
#     不需要主機上裝 apache2-utils。
docker run --rm --entrypoint htpasswd httpd:2 \
  -Bbn "$REGISTRY_USERNAME" "$REGISTRY_PASSWORD" > auth/htpasswd

echo "✓ 已產生 auth/htpasswd（使用者：$REGISTRY_USERNAME）"
echo
echo "  下一步："
echo "    docker compose --profile registry up -d registry"
echo "    bash infrastructure/base-images/push-all.sh"
echo
echo "  ⚠ auth/ 已在 .gitignore 裡，不要進版控。"
