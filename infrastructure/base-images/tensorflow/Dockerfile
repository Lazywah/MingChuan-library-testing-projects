# ==============================================================================
# ZH: aibase/tensorflow:2026-spring — TensorFlow 2.21 + GPU
# EN: aibase/tensorflow:2026-spring — TensorFlow 2.21 + GPU support
# ==============================================================================
# 為什麼是 2.21 而非 2.15 / 2.19？
#   - common-tools 用 Miniconda3-latest → 2026 年實測為 Python 3.13
#   - TF 各版本 wheel 對應 Python：
#       2.15 (2023-10) → cp39/cp310/cp311      (差兩版)
#       2.19 (2025-03) → cp39 ~ cp312          (差一版)
#       2.20 (2025-08) → cp39 ~ cp313          (可)
#       2.21 (2025 末) → cp39 ~ cp313 + bundled CUDA 12.9 (推薦)
#   - tensorflow[and-cuda] 會 pip 安裝自己一套 CUDA libs 到 site-packages/nvidia/
#     版本: cuBLAS 12.9 / cuDNN 9.22 / cuSPARSE 12.5 (TF 2.21 bundled)
#     與 base image 的 CUDA 12.8 system libs 並存，TF 透過 LD_LIBRARY_PATH 找自己的
#   - Keras 從 TF 2.16 起預設是 Keras 3；若舊 code 需要 Keras 2 行為，
#     設環境變數 TF_USE_LEGACY_KERAS=1 即可（詳見 docs/01-quick-start.md §9.1）
# ==============================================================================

FROM aibase/common-tools:2026-spring

USER root

# TF 2.21 with bundled CUDA (Python 3.13 compatible)
# tf-keras 是 Keras 2 legacy 套件 — 設 TF_USE_LEGACY_KERAS=1 才會被 TF 載入
# 不裝的話 env var 無效，仍然吃 Keras 3
RUN pip install --no-cache-dir \
        tensorflow[and-cuda]==2.21.0 \
        tf-keras \
        tensorboard \
    && pip install --no-cache-dir \
        numpy pandas matplotlib seaborn scikit-learn \
        tqdm rich \
        jupyter ipython ipykernel \
        Pillow opencv-python-headless

USER coder

RUN python -m ipykernel install --user --name aibase-tf --display-name "AI Base TensorFlow 2.21"

LABEL org.opencontainers.image.title="AI Base TensorFlow" \
      org.opencontainers.image.description="TensorFlow 2.21 + CUDA 12.9 (bundled) + 資料科學套件" \
      org.opencontainers.image.version="2026-spring" \
      aibase.framework="tensorflow" \
      aibase.framework_version="2.21" \
      aibase.cuda="12.9-bundled"

CMD ["/bin/bash"]
