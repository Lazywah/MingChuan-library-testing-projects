# ==============================================================================
# ZH: aibase/vllm:2026-spring — vLLM 高效能推論服務
# EN: aibase/vllm:2026-spring — vLLM high-performance inference
# ==============================================================================

FROM aibase/common-tools:2026-spring

USER root

# vLLM (含 CUDA 12.8 binary)
RUN pip install --no-cache-dir \
        vllm \
        "ray[default]" \
        flash-attn --no-build-isolation || echo "flash-attn build failed"

USER coder

RUN python -m ipykernel install --user --name aibase-vllm --display-name "AI Base vLLM"

LABEL org.opencontainers.image.title="AI Base vLLM" \
      aibase.framework="vllm" \
      aibase.cuda="12.8"

# vLLM 通常以 server 形式跑：vllm serve <model>
CMD ["/bin/bash"]
