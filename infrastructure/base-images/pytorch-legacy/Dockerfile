# ==============================================================================
# ZH: aibase/pytorch-legacy:2026-spring — PyTorch 2.6 + CUDA 11.8（舊版相容）
# EN: aibase/pytorch-legacy:2026-spring — PyTorch 2.6 + CUDA 11.8 (legacy compat)
# ==============================================================================
# 用途：給仍依賴 CUDA 11.8（無法升級驅動）的舊環境使用
# Purpose: For environments stuck on CUDA 11.8 driver
#
# 版本歷史：
#   2.0.1 → 2.5.1 → 2.6.0 (2026-05)
#     2.0.1: PyTorch 已從 cu118 wheel 索引下架
#     2.5.1: torchvision 0.20.x 無 cp313+cu118 wheel（Python 3.13 + CUDA 11.8）
#     2.6.0: 第一個有完整 cp313+cu118 trio (torch/vision/audio) 的版本
#   "Legacy" 區隔不再來自 PyTorch 版本，而是 CUDA driver (11.8 vs 主 image 12.8)
# ==============================================================================

# ZH: 使用 CUDA 11.8 base，與其他 image 不同
# EN: Use CUDA 11.8 base, different from others
FROM nvidia/cuda:11.8.0-cudnn8-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    PATH="/opt/conda/bin:${PATH}"

# 同 common-tools 的基本工具（這裡 inline 因為 CUDA base 不同）
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates curl wget git unzip zip tar bzip2 \
        vim nano htop tmux less \
        build-essential pkg-config aria2 gnupg \
    && curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
       | dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg \
    && chmod go+r /usr/share/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
       > /etc/apt/sources.list.d/github-cli.list \
    && apt-get update && apt-get install -y --no-install-recommends gh \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Miniconda
RUN curl -fsSL https://repo.anaconda.com/miniconda/Miniconda3-py313_26.5.3-2-Linux-x86_64.sh -o /tmp/miniconda.sh \
    && bash /tmp/miniconda.sh -b -p /opt/conda && rm /tmp/miniconda.sh \
    && /opt/conda/bin/conda config --system --set auto_update_conda false \
    && /opt/conda/bin/conda clean -afy

# PyTorch 2.6 + CUDA 11.8（cp313 wheel 對 cu118 最舊只到 torchvision 0.21）
# Python 3.13 (miniconda 內建) 對 cu118 wheel 的 torchvision 最舊 0.21.x，
# 因此 trio 一起升到 2.6.0 / 0.21.0 / 2.6.0
RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cu118 \
        torch==2.6.0 torchvision==0.21.0 torchaudio==2.6.0 \
    && pip install --no-cache-dir \
        numpy pandas matplotlib seaborn scikit-learn \
        tqdm rich \
        jupyter ipython ipykernel \
        accelerate datasets \
        Pillow \
        kaggle "huggingface_hub[cli]"

ENV HF_HOME=/opt/models:/home/coder/.cache/huggingface \
    PIP_NO_CACHE_DIR=1

RUN useradd -m -s /bin/bash -u 1000 coder \
    && mkdir -p /home/coder/projects /home/coder/outputs /home/coder/logs \
    && mkdir -p /opt/models && chmod 755 /opt/models \
    && chown -R coder:coder /home/coder

WORKDIR /home/coder
USER coder

RUN echo 'export PATH="/opt/conda/bin:$HOME/.local/bin:$PATH"' >> ~/.bashrc \
    && echo 'export HF_HOME="/opt/models:$HOME/.cache/huggingface"' >> ~/.bashrc \
    && python -m ipykernel install --user --name aibase-pytorch-legacy \
                                    --display-name "AI Base PyTorch 2.6 (Legacy CU118)"

LABEL org.opencontainers.image.title="AI Base PyTorch Legacy" \
      aibase.framework="pytorch" \
      aibase.framework_version="2.6" \
      aibase.cuda="11.8"

# ==============================================================================
# ZH: 開機防呆（2026-08-30，5090 實測後加）—— cu118 kernel 只到 sm_90，
#     但在更新的卡上 `torch.cuda.is_available()` 照樣回 True、一算才炸。
#     entrypoint 先驗 GPU 世代再 `exec "$@"`：worker 的 `docker run image bash -euc …`
#     與互動 `docker run -it image` 兩條路徑都原樣保留（`$@` 沒給時吃 CMD）。
#     sed 去 CR + chmod：與 code-server/Dockerfile 的 v2.1 前例相同，
#     防 Windows checkout 把腳本翻成 CRLF。
# EN: Boot guard — refuse to start on GPUs newer than the cu118 kernels
#     (sm_90). See aibase-gpu-check.sh. AIBASE_MAX_SM must track the CUDA base.
# ==============================================================================
USER root
COPY aibase-gpu-check.sh /usr/local/bin/aibase-gpu-check.sh
RUN sed -i 's/\r$//' /usr/local/bin/aibase-gpu-check.sh \
    && chmod +x /usr/local/bin/aibase-gpu-check.sh
USER coder

ENV AIBASE_MAX_SM=90
ENTRYPOINT ["/usr/local/bin/aibase-gpu-check.sh"]
CMD ["/bin/bash"]
