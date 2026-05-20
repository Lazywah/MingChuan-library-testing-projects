# ==============================================================================
# ZH: aibase/dev-tools:2026-spring — 多語言開發工具鏈
# EN: aibase/dev-tools:2026-spring — Multi-language development toolchain
# ==============================================================================
# 包含: Python + miniconda + CUDA toolkit + C/C++ + Java + Rust + Go
# Used by: 跨語言開發、CUDA kernel 開發、舊版重現環境
# ==============================================================================

# ZH: 使用 CUDA devel base 取得完整 nvcc 工具鏈
# EN: Use CUDA devel base for full nvcc toolchain
FROM nvidia/cuda:12.8.0-devel-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    LANG=C.UTF-8 \
    PATH="/opt/conda/bin:/usr/local/go/bin:/root/.cargo/bin:${PATH}" \
    GOPATH=/home/coder/go

# ============ Stage: 系統工具 + 多語言編譯器 ============
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates curl wget git unzip zip tar bzip2 xz-utils \
        vim nano htop tmux less procps \
        gnupg aria2 \
        # C/C++ 編譯工具
        build-essential gcc-11 g++-11 gcc-10 g++-10 \
        gdb clang-15 clangd-15 \
        cmake make ninja-build pkg-config \
        # Java
        openjdk-17-jdk maven \
        # 通用 dev 工具
        software-properties-common \
        libssl-dev libffi-dev zlib1g-dev \
    && update-alternatives --install /usr/bin/gcc gcc /usr/bin/gcc-11 110 \
    && update-alternatives --install /usr/bin/gcc gcc /usr/bin/gcc-10 100 \
    && update-alternatives --install /usr/bin/g++ g++ /usr/bin/g++-11 110 \
    && update-alternatives --install /usr/bin/g++ g++ /usr/bin/g++-10 100 \
    && curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
       | dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
       > /etc/apt/sources.list.d/github-cli.list \
    && apt-get update && apt-get install -y --no-install-recommends gh \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# ============ Go ============
RUN curl -fsSL https://go.dev/dl/go1.22.0.linux-amd64.tar.gz | tar -xz -C /usr/local

# ============ Miniconda ============
RUN curl -fsSL https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh -o /tmp/miniconda.sh \
    && bash /tmp/miniconda.sh -b -p /opt/conda && rm /tmp/miniconda.sh \
    && /opt/conda/bin/conda config --system --set auto_update_conda false \
    && /opt/conda/bin/conda clean -afy

# ============ Python tools ============
RUN pip install --no-cache-dir \
        numpy pandas matplotlib jupyter ipykernel \
        kaggle "huggingface_hub[cli]"

ENV HF_HOME=/opt/models:/home/coder/.cache/huggingface \
    PIP_NO_CACHE_DIR=1

# ============ User setup ============
RUN useradd -m -s /bin/bash -u 1000 coder \
    && mkdir -p /home/coder/projects /home/coder/outputs /home/coder/go /opt/models \
    && chmod 755 /opt/models \
    && chown -R coder:coder /home/coder

USER coder
WORKDIR /home/coder

# ============ Rust（per-user 安裝，因為 cargo 預設 ~/.cargo）============
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs \
       | sh -s -- -y --default-toolchain stable --profile minimal

RUN echo 'export PATH="/opt/conda/bin:/usr/local/go/bin:$HOME/.cargo/bin:$HOME/.local/bin:$PATH"' >> ~/.bashrc \
    && echo 'export HF_HOME="/opt/models:$HOME/.cache/huggingface"' >> ~/.bashrc \
    && python -m ipykernel install --user --name aibase-dev --display-name "AI Base Dev Tools"

LABEL org.opencontainers.image.title="AI Base Dev Tools" \
      aibase.framework="dev-tools" \
      aibase.languages="python,c,cpp,cuda,java,rust,go"

CMD ["/bin/bash"]
