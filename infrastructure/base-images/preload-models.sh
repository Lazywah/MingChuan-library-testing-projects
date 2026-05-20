#!/bin/bash
# ==============================================================================
# ZH: 預下載熱門模型到 shared_models volume（read-only 給所有使用者共享）
# EN: Preload popular models to shared_models volume (read-only, shared by all)
# ==============================================================================
# 必須先：
#   1. docker volume create shared_models
#   2. 提供 HF_TOKEN（讀 gated 模型如 Llama-2 用）
# ==============================================================================

set -e

# ZH: HF_TOKEN 可從 .env 讀或 export
# EN: HF_TOKEN can be from .env or exported
if [ -z "${HF_TOKEN:-}" ] && [ -f .env ]; then
    HF_TOKEN=$(grep -E "^HF_TOKEN=" .env | cut -d= -f2-)
fi

if [ -z "$HF_TOKEN" ]; then
    echo "⚠️  HF_TOKEN not set. Gated models (Llama-2, etc.) will be skipped."
    echo "   To download gated models, set HF_TOKEN in .env or export HF_TOKEN=hf_xxx"
fi

# ZH: 確保 shared_models volume 存在
# EN: Ensure shared_models volume exists
if ! docker volume inspect shared_models >/dev/null 2>&1; then
    echo "Creating shared_models volume..."
    docker volume create shared_models
fi

# ZH: 啟動暫時 container 在 volume 內下載
# EN: Spin up a temporary container to download into the volume
TEMP_NAME="aibase-model-preloader"

echo "Starting preloader container..."
docker rm -f "$TEMP_NAME" 2>/dev/null || true

docker run --rm --name "$TEMP_NAME" \
    -v shared_models:/opt/models \
    -e HF_TOKEN="$HF_TOKEN" \
    aibase/common-tools:2026-spring \
    bash -c '
        set -e
        cd /opt/models

        # 預下載熱門公開模型（無需 token）
        echo "─── Downloading public models ───"
        for model in \
            "bert-base-uncased" \
            "google-t5/t5-base" \
            "sentence-transformers/all-MiniLM-L6-v2" \
            "openai/whisper-base"; do
            echo "  Downloading $model ..."
            huggingface-cli download "$model" --local-dir-use-symlinks=False \
                --local-dir "./$(basename $model)" || echo "  ⚠️  Failed: $model"
        done

        # Gated 模型（需 HF_TOKEN）
        if [ -n "$HF_TOKEN" ]; then
            echo "─── Downloading gated models (using HF_TOKEN) ───"
            for model in \
                "meta-llama/Llama-2-7b-hf" \
                "mistralai/Mistral-7B-v0.1"; do
                echo "  Downloading $model ..."
                huggingface-cli download "$model" --token "$HF_TOKEN" \
                    --local-dir-use-symlinks=False \
                    --local-dir "./$(basename $model)" || echo "  ⚠️  Failed: $model (check HF_TOKEN access)"
            done
        else
            echo "─── Skipping gated models (no HF_TOKEN) ───"
        fi

        echo ""
        echo "─── shared_models contents ───"
        ls -lh /opt/models
        du -sh /opt/models/*
    '

echo ""
echo "✅ Preload complete."
echo "   shared_models volume now contains:"
docker run --rm -v shared_models:/opt/models alpine ls /opt/models
