#!/usr/bin/env bash
# ==============================================================================
# ZH: 把 aibase/* 映像推到私有 registry / Push aibase images to the private registry
# ==============================================================================
# ZH: 為什麼需要：這些映像是在服務層這台機器上建出來的（build-all.sh），
#     不在任何公開 registry。GPU 搬到獨立主機之後那台拉不到，
#     而「程式實驗室」與「上傳訓練」**兩邊都指向這些映像**，會一起停擺。
#
# 用法 / Usage：
#   bash infrastructure/base-images/push-all.sh [TAG]
#
#   TAG 預設 2026-spring（學期鎖定政策，與 build-all.sh 一致）
#   registry 位址從根 .env 的 IMAGE_REGISTRY_PREFIX 讀
#
# ZH: ⚠ 這支只推**本機已經建好**的映像。沒建過的先跑 build-all.sh。
# ==============================================================================
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$REPO_ROOT"

TAG="${1:-2026-spring}"
ENV_FILE=".env"

read_env() {
  [ -f "$ENV_FILE" ] || return 0
  grep -E "^$1=" "$ENV_FILE" | head -1 | cut -d= -f2- || true
}

PREFIX="${IMAGE_REGISTRY_PREFIX:-$(read_env IMAGE_REGISTRY_PREFIX)}"
PREFIX="${PREFIX%/}"

if [ -z "$PREFIX" ]; then
  echo "✗ IMAGE_REGISTRY_PREFIX 是空的" >&2
  echo "  這台機器是**服務層**，要推到哪個 registry 必須講明。" >&2
  echo "  在根 .env 填上，例如：IMAGE_REGISTRY_PREFIX=registry.mcu.edu.tw" >&2
  echo "  （空值的意思是「用本機映像」，那是單機部署，不需要推）" >&2
  exit 1
fi

# ZH: 清單**從 build-all.sh 推導**，不另外手維護一份。
#     兩份手寫清單一定會漂開，而少推一個的症狀是
#     「大部分任務正常，某一種框架的任務永遠拉不到映像」——沒有人會聯想到這裡。
BUILD_ALL="$SCRIPT_DIR/build-all.sh"
if [ ! -f "$BUILD_ALL" ]; then
  echo "✗ 找不到 $BUILD_ALL —— 這支腳本靠它決定要推哪些映像" >&2
  exit 1
fi

mapfile -t BUILT < <(sed -n '/^declare -a IMAGES=(/,/^)/p' "$BUILD_ALL"                      | grep -oE '"[a-z-]+\|' | tr -d '"|')

# ZH: 🔴 build-all.sh 裡有**不在那個陣列**、直接寫死 `docker build -t` 的特例
#     （code-server 與 code-server-gpu，它們要 repo root 當 build context）。
#     所以再撈一次 `-t "aibase/<名字>:`，兩份聯集才是完整清單。
# ZH: 為什麼不手寫特例：2026-09-23 發現這裡只補了 code-server，漏掉
#     code-server-gpu —— 而 lab_manager 的 default_gpu_image 正是它。
#     GPU 節點獨立之後，學生在實驗室勾 GPU 就會拉不到映像，
#     症狀是「CPU 實驗室好好的，GPU 實驗室永遠起不來」。
#     手寫清單一定會漂開，所以這裡改成從同一份來源推導。
mapfile -t SPECIAL < <(grep -oE -- '-t "aibase/[a-z-]+:' "$BUILD_ALL"                        | sed -E 's|.*aibase/([a-z-]+):|\1|')

if [ ${#BUILT[@]} -lt 2 ] || [ ${#SPECIAL[@]} -lt 1 ]; then
  echo "✗ 從 build-all.sh 解出 ${#BUILT[@]} 個陣列映像、${#SPECIAL[@]} 個特例映像，看起來是解析失敗了" >&2
  echo "  （build-all.sh 的 IMAGES 陣列或 docker build -t 的寫法改了嗎？）" >&2
  exit 1
fi

IMAGES=()
for name in "${BUILT[@]}" "${SPECIAL[@]}"; do
  # ZH: common-tools 只是其他映像的建構基底，不會被直接 run —— 它的層已經烤進
  #     衍生映像裡了，推它只是浪費空間。
  [ "$name" = "common-tools" ] && continue
  # ZH: 兩份來源會重疊（陣列裡的也可能出現在 -t），去重。
  skip=""
  for seen in ${IMAGES[@]+"${IMAGES[@]}"}; do
    [ "$seen" = "$name" ] && skip=1 && break
  done
  [ -n "$skip" ] && continue
  IMAGES+=("$name")
done
echo "要推的映像（由 build-all.sh 推導）：${IMAGES[*]}"

echo "================================================================="
echo "Pushing aibase images  TAG=$TAG  →  $PREFIX"
echo "================================================================="

missing=()
for name in "${IMAGES[@]}"; do
  if ! docker image inspect "aibase/${name}:${TAG}" >/dev/null 2>&1; then
    missing+=("aibase/${name}:${TAG}")
  fi
done
if [ ${#missing[@]} -gt 0 ]; then
  echo "✗ 這些映像本機沒有，請先跑 build-all.sh：" >&2
  printf '    %s\n' "${missing[@]}" >&2
  exit 1
fi

failed=()
for name in "${IMAGES[@]}"; do
  src="aibase/${name}:${TAG}"
  dst="${PREFIX}/aibase/${name}:${TAG}"
  echo
  echo "── $src → $dst"
  docker tag "$src" "$dst"
  if ! docker push "$dst"; then
    failed+=("$dst")
  fi
done

echo
if [ ${#failed[@]} -gt 0 ]; then
  echo "✗ 這些推失敗了：" >&2
  printf '    %s\n' "${failed[@]}" >&2
  echo >&2
  echo "  常見原因：" >&2
  echo "    • 沒登入      → docker login $PREFIX" >&2
  echo "    • 明文 HTTP   → 那台 docker daemon 要設 insecure-registries，或改走 TLS" >&2
  echo "    • registry 沒起 → docker compose --profile registry up -d registry" >&2
  exit 1
fi

echo "✓ 全部推完（${#IMAGES[@]} 個）"
echo
echo "  GPU 主機那邊在它的 env 檔設："
echo "    IMAGE_REGISTRY_PREFIX=$PREFIX"
echo "    REGISTRY_USERNAME / REGISTRY_PASSWORD  （與服務層一致）"
