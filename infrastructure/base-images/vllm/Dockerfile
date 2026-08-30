# ==============================================================================
# ZH: aibase/vllm:2026-spring — vLLM 高效能推論服務
# EN: aibase/vllm:2026-spring — vLLM high-performance inference
# ==============================================================================

FROM aibase/common-tools:2026-spring

USER root

# ==============================================================================
# ZH: 🔴 必裝與選配**分兩條 RUN**（2026-08-30 修）。
#     原本一條：`pip install vllm "ray[default]" flash-attn … || echo "flash-attn build failed"`
#     那個 `|| echo` 想容忍的是 flash-attn 編不過，但它掛在**整條 pip** 上，
#     而 pip 是整批安裝的 —— flash-attn 在 metadata 階段就因為
#     `No module named 'torch'`（common-tools 沒有 torch）失敗，
#     於是 vllm 與 ray **一個都沒裝**，`|| echo` 再把 exit 1 吞掉。
#     結果是一顆 9.18 GB、與 common-tools 位元組數相同的「空 vllm」映像，
#     **兩個月來 build 全綠、沒有人發現**（docs/00 還把 9G 抄成正常大小）。
# EN: Split required vs optional installs. The old single-RUN `|| echo` swallowed
#     the WHOLE pip failure: flash-attn's metadata build needs torch (absent in
#     common-tools), pip aborted the entire batch, and the image shipped without
#     vllm for two months while every build stayed green.
# ==============================================================================

# ZH: 必裝 —— 失敗就讓 build 紅，不准吞
# EN: Required — a failure here must fail the build
RUN pip install --no-cache-dir vllm "ray[default]"

# ZH: 選配加速 —— 只有這一個允許失敗（此時 torch 已隨 vllm 裝好，成功率也高了）
# EN: Optional accelerator — the only line allowed to fail (torch now present)
RUN pip install --no-cache-dir flash-attn --no-build-isolation \
    || echo "flash-attn build failed (optional accelerator; vllm itself works)"

USER coder

RUN python -m ipykernel install --user --name aibase-vllm --display-name "AI Base vLLM"

LABEL org.opencontainers.image.title="AI Base vLLM" \
      aibase.framework="vllm" \
      aibase.cuda="12.8"

# vLLM 通常以 server 形式跑：vllm serve <model>
CMD ["/bin/bash"]
