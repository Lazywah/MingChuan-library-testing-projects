# ==============================================================================
# ZH: aibase/pytorch:2026-spring — PyTorch 2.7 + CUDA 12.8（標準訓練 image）
# EN: aibase/pytorch:2026-spring — PyTorch 2.7 + CUDA 12.8 (standard training image)
# ==============================================================================
# Build:
#   docker build -t aibase/pytorch:2026-spring -f pytorch/Dockerfile .
# (請先 build aibase/common-tools:2026-spring)
# ==============================================================================

FROM aibase/common-tools:2026-spring

USER root

# ZH: PyTorch 2.7 + CUDA 12.8 wheel
# EN: PyTorch 2.7 + CUDA 12.8 wheel
RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cu128 \
        torch==2.7.0 torchvision==0.22.0 torchaudio==2.7.0 \
    && pip install --no-cache-dir \
        numpy pandas matplotlib seaborn scikit-learn \
        tqdm rich tabulate \
        jupyter ipython ipykernel \
        accelerate datasets \
        wandb tensorboard \
        Pillow opencv-python-headless

USER coder

# ZH: 設定 ipykernel 註冊（v2.1 真 Kernel 模式會用到）
# EN: Register ipykernel for v2.1 real-kernel mode
RUN python -m ipykernel install --user --name aibase-pytorch --display-name "AI Base PyTorch 2.7"

LABEL org.opencontainers.image.title="AI Base PyTorch" \
      org.opencontainers.image.description="PyTorch 2.7 + CUDA 12.8 + 資料科學套件" \
      org.opencontainers.image.version="2026-spring" \
      aibase.framework="pytorch" \
      aibase.framework_version="2.7" \
      aibase.cuda="12.8"

CMD ["/bin/bash"]
