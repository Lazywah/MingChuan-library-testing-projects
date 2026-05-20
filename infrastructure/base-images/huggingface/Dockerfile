# ==============================================================================
# ZH: aibase/huggingface:2026-spring — HF 全套件（LoRA 微調最常用）
# EN: aibase/huggingface:2026-spring — HF stack (most common for LoRA fine-tuning)
# ==============================================================================

FROM aibase/pytorch:2026-spring

USER root

# ZH: HuggingFace 全家桶 + LoRA / 量化 / SFT 套件
# EN: HF ecosystem + LoRA / quantization / SFT stack
RUN pip install --no-cache-dir \
        transformers==4.40.0 \
        diffusers==0.27.0 \
        peft==0.10.0 \
        accelerate==0.29.0 \
        bitsandbytes==0.43.0 \
        sentencepiece \
        tokenizers \
        safetensors \
        trl==0.8.0 \
        evaluate \
        einops \
        flash-attn --no-build-isolation || echo "flash-attn build failed, skipping (will be installed by user if needed)"

USER coder

RUN python -m ipykernel install --user --name aibase-hf --display-name "AI Base HuggingFace"

LABEL org.opencontainers.image.title="AI Base HuggingFace" \
      aibase.framework="huggingface" \
      aibase.framework_version="transformers-4.40"

CMD ["/bin/bash"]
