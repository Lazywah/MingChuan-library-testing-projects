# ==============================================================================
# ZH: aibase/code-server:2026-spring — VS Code in Browser (CPU edit container)
# EN: aibase/code-server:2026-spring — VS Code in Browser (CPU edit container)
# ==============================================================================
# Multi-stage build:
#   Stage 1: Node.js builder → 編譯 aibase-runner extension
#   Stage 2: code-server runtime → 安裝 extension、預裝 Python 工具
# ==============================================================================

# ============ Stage 1: Build aibase-runner extension ============
# v2.1 修正：Node 18 + 新版 @vscode/vsce (undici) 會出 ReferenceError: File is not defined
# (File 是 Fetch API 全域，Node 20+ 才有)；升到 Node 20 LTS
FROM node:20-bullseye AS builder

WORKDIR /build

# 複製 extension 原始碼（build context 必須包含 vscode-extension/）
COPY vscode-extension/aibase-runner/ ./aibase-runner/

WORKDIR /build/aibase-runner

# 安裝依賴與 vsce 打包工具
RUN npm install \
    && npm install -g @vscode/vsce \
    && npm run compile \
    && vsce package --no-yarn -o /build/aibase-runner.vsix

# ============ Stage 2: Code-server runtime ============
FROM codercom/code-server:4.96.4

USER root

ENV DEBIAN_FRONTEND=noninteractive \
    LANG=C.UTF-8 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/conda/bin:/home/coder/.local/bin:${PATH}"

# 系統工具 + 資料集下載 CLI（與 base image 一致）
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates curl wget git unzip zip tar \
        vim nano htop tmux less \
        build-essential pkg-config aria2 gnupg \
        python3 python3-pip python3-venv \
    && curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
       | dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
       > /etc/apt/sources.list.d/github-cli.list \
    && apt-get update && apt-get install -y --no-install-recommends gh \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Miniconda (與 base image 一致，使用者可以在 code-server terminal 跑 conda)
RUN curl -fsSL https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh -o /tmp/miniconda.sh \
    && bash /tmp/miniconda.sh -b -p /opt/conda \
    && rm /tmp/miniconda.sh \
    && /opt/conda/bin/conda config --system --set auto_update_conda false \
    && /opt/conda/bin/conda clean -afy

# 資料集 CLI Python 工具
RUN pip3 install --no-cache-dir --break-system-packages \
        kaggle "huggingface_hub[cli]" || \
    pip3 install --no-cache-dir kaggle "huggingface_hub[cli]"

# ZH: 從 Stage 1 複製打包好的 extension .vsix
# EN: Copy built extension .vsix from Stage 1
COPY --from=builder /build/aibase-runner.vsix /tmp/aibase-runner.vsix

# ZH: 安裝 extensions（語法高亮 + aibase-runner）
# EN: Install extensions (syntax + aibase-runner)
# v2.1 修正：rm 改用 root 執行 (coder UID 1000 無法刪除 root 拷貝進來的 .vsix)
USER coder
RUN code-server --install-extension ms-python.python \
    && code-server --install-extension ms-toolsai.jupyter \
    && code-server --install-extension llvm-vs-code-extensions.vscode-clangd \
    && code-server --install-extension redhat.java \
    && code-server --install-extension golang.go \
    && code-server --install-extension rust-lang.rust-analyzer \
    && code-server --install-extension /tmp/aibase-runner.vsix

USER root
RUN rm -f /tmp/aibase-runner.vsix

# ZH: Entrypoint 處理 secrets → CLI config 自動寫入
# EN: Entrypoint converts secrets to CLI configs at startup
# v2.1 修正：Windows host build 時 .sh 可能變 CRLF，導致容器啟動報
# "exec /usr/local/bin/aibase-entrypoint.sh: no such file or directory"
# (kernel 把 /bin/bash\r 當解譯器)。COPY 後用 sed 強制改 LF
COPY infrastructure/base-images/code-server/aibase-entrypoint.sh /usr/local/bin/aibase-entrypoint.sh
RUN sed -i 's/\r$//' /usr/local/bin/aibase-entrypoint.sh \
    && chmod +x /usr/local/bin/aibase-entrypoint.sh

# ZH: 預設使用者目錄結構
# EN: Default user directory structure
RUN mkdir -p /home/coder/projects /home/coder/outputs /home/coder/logs /opt/models \
    && chmod 755 /opt/models \
    && chown -R coder:coder /home/coder

# bashrc
USER coder
RUN echo 'export PATH="/opt/conda/bin:$HOME/.local/bin:$PATH"' >> ~/.bashrc \
    && echo 'export HF_HOME="/opt/models:$HOME/.cache/huggingface"' >> ~/.bashrc \
    && echo 'alias ll="ls -alh"' >> ~/.bashrc

WORKDIR /home/coder

EXPOSE 8080

ENTRYPOINT ["/usr/local/bin/aibase-entrypoint.sh"]
# v2.1 修正：auth 從 password 改為 none
# nginx 已用 auth_request /api/v1/lab/_authz 驗證 JWT 與 user_id 對應，
# code-server 不需再次密碼驗證。原 password 模式會在通過 nginx 後再彈 login 頁，
# 但 window.open 不帶密碼 → 死鎖 401。
#
# ⚠️ 已知風險（v2.2 處理）：所有 lab 容器在同一 ai-platform-net，
# 若使用者從自己 lab 容器內執行 `curl http://cs-<other_uid>:8080/` 可繞過 nginx
# 直接讀其他人的工作目錄。學校教學平台威脅模型可接受，但 v2.2 會用
# per-user docker network 隔離。詳見：docs/dev/v2.2-roadmap.md
CMD ["--bind-addr", "0.0.0.0:8080", "--auth", "none", "/home/coder/projects"]
