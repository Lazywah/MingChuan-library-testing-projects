#!/bin/bash
# ==============================================================================
# ZH: 建構全部 AI Base images
# EN: Build all AI Base images
# ==============================================================================
# Usage:
#   cd CodeSpace
#   bash infrastructure/base-images/build-all.sh [TAG]
#
# 預設 TAG = 2026-spring（學期鎖定政策）
# 必須從 CodeSpace 根目錄執行（因 code-server image 需要 vscode-extension/ context）
# ==============================================================================

set -e

TAG="${1:-2026-spring}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$REPO_ROOT"

echo "================================================================="
echo "Building AI Base Images (TAG: $TAG)"
echo "Repo root: $REPO_ROOT"
echo "================================================================="

# 順序：common-tools 必須先建（其他 image 繼承），然後 pytorch（huggingface 繼承）
declare -a IMAGES=(
    "common-tools|infrastructure/base-images/common/Dockerfile.common-tools|infrastructure/base-images/common"
    "pytorch|infrastructure/base-images/pytorch/Dockerfile|infrastructure/base-images/pytorch"
    "pytorch-legacy|infrastructure/base-images/pytorch-legacy/Dockerfile|infrastructure/base-images/pytorch-legacy"
    "tensorflow|infrastructure/base-images/tensorflow/Dockerfile|infrastructure/base-images/tensorflow"
    "huggingface|infrastructure/base-images/huggingface/Dockerfile|infrastructure/base-images/huggingface"
    "llamacpp|infrastructure/base-images/llamacpp/Dockerfile|infrastructure/base-images/llamacpp"
    "vllm|infrastructure/base-images/vllm/Dockerfile|infrastructure/base-images/vllm"
    "dev-tools|infrastructure/base-images/dev-tools/Dockerfile|infrastructure/base-images/dev-tools"
)

for entry in "${IMAGES[@]}"; do
    IFS='|' read -r name dockerfile context <<< "$entry"
    image_name="aibase/${name}:${TAG}"

    echo ""
    echo "─── Building ${image_name} ───"
    echo "    Dockerfile: ${dockerfile}"

    if docker build -t "${image_name}" -f "${dockerfile}" "${context}"; then
        echo "    ✅ ${image_name} built successfully"
    else
        echo "    ❌ ${image_name} build failed — aborting"
        exit 1
    fi
done

# code-server image 需要 repo root 為 build context（讀 vscode-extension/）
echo ""
echo "─── Building aibase/code-server:${TAG} ───"
if [ ! -d "vscode-extension/aibase-runner" ]; then
    echo "    ⚠️  vscode-extension/aibase-runner not found — skipping code-server build"
    echo "    (run this script again after Phase C is complete)"
else
    if docker build -t "aibase/code-server:${TAG}" \
                    -f infrastructure/base-images/code-server/Dockerfile .; then
        echo "    ✅ aibase/code-server:${TAG} built successfully"
    else
        echo "    ❌ code-server image build failed"
        exit 1
    fi

    # code-server-gpu：GPU 版程式實驗室（疊在 aibase/pytorch 上，見其 Dockerfile 檔頭）。
    # 🔴 2026-08-30 之前這一段不存在 —— Dockerfile 寫好了、lab_manager 的
    #    default_gpu_image 也指著它，但沒有任何東西建它：學生在實驗室勾 GPU
    #    就會拿到 image pull 失敗。同樣需要 repo root context（讀 vscode-extension/）。
    echo ""
    echo "─── Building aibase/code-server-gpu:${TAG} ───"
    if ! docker image inspect "aibase/pytorch:${TAG}" >/dev/null 2>&1; then
        echo "    ❌ aibase/pytorch:${TAG} not found — it is the base of code-server-gpu"
        exit 1
    fi
    if docker build -t "aibase/code-server-gpu:${TAG}" \
                    -f infrastructure/base-images/code-server-gpu/Dockerfile .; then
        echo "    ✅ aibase/code-server-gpu:${TAG} built successfully"
    else
        echo "    ❌ code-server-gpu image build failed"
        exit 1
    fi
fi

echo ""
echo "================================================================="
echo "All images built! Tag list:"
echo "================================================================="
docker images "aibase/*:${TAG}"
