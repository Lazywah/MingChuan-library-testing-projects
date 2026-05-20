# ==============================================================================
# ZH: aibase/pytorch-legacy:2026-spring — PyTorch 2.0 + CUDA 11.8（舊版相容）
# EN: aibase/pytorch-legacy:2026-spring — PyTorch 2.0 + CUDA 11.8 (legacy compat)
# ==============================================================================
# 用途：給仍依賴 PyTorch 2.0 / CUDA 11.8 的舊專案使用
# Purpose: For projects still on PyTorch 2.0 / CUDA 11.8
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
RUN curl -fsSL https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh -o /tmp/miniconda.sh \
    && bash /tmp/miniconda.sh -b -p /opt/conda && rm /tmp/miniconda.sh \
    && /opt/conda/bin/conda config --system --set auto_update_conda false \
    && /opt/conda/bin/conda clean -afy

# PyTorch 2.0 + CUDA 11.8
RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cu118 \
        torch==2.0.1 torchvision==0.15.2 torchaudio==2.0.2 \
    && pip install --no-cache-dir \
        numpy pandas matplotlib seaborn scikit-learn \
        tqdm rich \
        jupyter ipython ipykernel \
        accelerate==0.21.0 datasets==2.14.0 \
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
                                    --display-name "AI Base PyTorch 2.0 (Legacy)"

LABEL org.opencontainers.image.title="AI Base PyTorch Legacy" \
      aibase.framework="pytorch" \
      aibase.framework_version="2.0" \
      aibase.cuda="11.8"

CMD ["/bin/bash"]
