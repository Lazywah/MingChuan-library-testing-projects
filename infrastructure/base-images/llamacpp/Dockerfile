# ==============================================================================
# ZH: aibase/llamacpp:2026-spring — llama.cpp 推論 + CUDA 工具鏈
# EN: aibase/llamacpp:2026-spring — llama.cpp inference + CUDA toolchain
# ==============================================================================

ARG BASE_IMAGE=nvidia/cuda:12.8.0-devel-ubuntu22.04
FROM ${BASE_IMAGE}

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    LANG=C.UTF-8 \
    PATH="/opt/conda/bin:${PATH}"

# 系統套件（含完整編譯工具鏈，因為 llama.cpp 從原始碼 build）
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates curl wget git unzip zip tar \
        vim nano htop tmux less \
        build-essential cmake pkg-config \
        libopenblas-dev libcurl4-openssl-dev \
        aria2 gnupg \
    && curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
       | dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
       > /etc/apt/sources.list.d/github-cli.list \
    && apt-get update && apt-get install -y --no-install-recommends gh \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Miniconda
RUN curl -fsSL https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh -o /tmp/miniconda.sh \
    && bash /tmp/miniconda.sh -b -p /opt/conda && rm /tmp/miniconda.sh \
    && /opt/conda/bin/conda clean -afy

# llama.cpp from source with CUDA support
RUN git clone --depth 1 https://github.com/ggerganov/llama.cpp.git /opt/llama.cpp \
    && cd /opt/llama.cpp \
    && mkdir build && cd build \
    && cmake .. -DGGML_CUDA=ON \
    && cmake --build . --config Release -j $(nproc) \
    && ln -s /opt/llama.cpp/build/bin/llama-cli /usr/local/bin/llama-cli \
    && ln -s /opt/llama.cpp/build/bin/llama-server /usr/local/bin/llama-server \
    && ln -s /opt/llama.cpp/build/bin/llama-quantize /usr/local/bin/llama-quantize

# Python 工具（HF 下載 GGUF）
RUN pip install --no-cache-dir \
        kaggle "huggingface_hub[cli]" \
        ipykernel jupyter_client \
        numpy pandas tqdm rich

ENV HF_HOME=/opt/models:/home/coder/.cache/huggingface \
    PIP_NO_CACHE_DIR=1

RUN useradd -m -s /bin/bash -u 1000 coder \
    && mkdir -p /home/coder/projects /home/coder/outputs /opt/models \
    && chmod 755 /opt/models \
    && chown -R coder:coder /home/coder

WORKDIR /home/coder
USER coder

RUN echo 'export PATH="/opt/conda/bin:$HOME/.local/bin:$PATH"' >> ~/.bashrc \
    && echo 'export HF_HOME="/opt/models:$HOME/.cache/huggingface"' >> ~/.bashrc \
    && python -m ipykernel install --user --name aibase-llamacpp \
                                    --display-name "AI Base llama.cpp"

LABEL org.opencontainers.image.title="AI Base llama.cpp" \
      aibase.framework="llamacpp" \
      aibase.cuda="12.8"

CMD ["/bin/bash"]
