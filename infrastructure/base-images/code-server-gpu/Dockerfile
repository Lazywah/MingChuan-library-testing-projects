# ==============================================================================
# ZH: aibase/code-server-gpu:2026-spring — 帶 GPU 的程式實驗室（互動式訓練）
# EN: aibase/code-server-gpu:2026-spring — Code Lab with GPU (interactive training)
# ==============================================================================
# Build（build context 是 **repo root** —— 要讀 vscode-extension/，與 CPU 版一致）:
#   docker build -t aibase/code-server-gpu:2026-spring -f infrastructure/base-images/code-server-gpu/Dockerfile .
#
# 前置：aibase/pytorch:2026-spring 要先 build 好。
# ==============================================================================
#
# ZH: 🔴 **為什麼疊在 aibase/pytorch 上，而不是在 code-server 上裝 torch。**
#     學生在實驗室裡跑得動的程式，送去「交給平台訓練」也必須跑得動。
#     兩邊各自裝 torch 的話版本遲早漂開，而症狀是**在實驗室好好的、送出去就掛**，
#     那種問題最難查（環境不同，錯誤訊息卻只出現在使用者看不到的批次日誌裡）。
#     疊在同一個 base 上，torch / CUDA / numpy 全部逐位元組相同。
#
# ZH: 磁碟成本比看起來小很多：pytorch 那 21.4 GB 的層是**共用的**，
#     這個映像只多出 code-server 與擴充套件（約 1 GB）。
#
# ZH: ⚠ 與 CPU 版 `aibase/code-server` 的差異只有「基底」與「不必再裝 conda/python」。
#     擴充套件、entrypoint、目錄結構刻意保持一致 —— 兩個映像的行為要一樣，
#     使用者不該因為換了一個而發現操作方式不同。
# ==============================================================================

# ============ Stage 1: 編譯 aibase-runner extension ============
# ZH: 與 code-server/Dockerfile 同一段。Node 20：Node 18 + 新版 vsce 會出
#     `ReferenceError: File is not defined`（File 是 Fetch API 全域，Node 20+ 才有）。
FROM node:20-bullseye AS builder

WORKDIR /build
COPY vscode-extension/aibase-runner/ ./aibase-runner/
WORKDIR /build/aibase-runner

# ZH: 編譯後 prune 掉 devDeps，讓 vsce 把 production node_modules 一併打包 ——
#     不這樣做的話 extension 執行期會 `Cannot find module 'node-fetch'`。
RUN npm install \
    && npm install -g @vscode/vsce \
    && npm run compile \
    && npm prune --production \
    && vsce package --no-yarn -o /build/aibase-runner.vsix

# ============ Stage 2: 在 PyTorch 映像上裝 code-server ============
FROM aibase/pytorch:2026-spring

USER root

ENV DEBIAN_FRONTEND=noninteractive \
    LANG=C.UTF-8 \
    PYTHONUNBUFFERED=1

# ZH: code-server 本體。用官方安裝腳本裝到 /usr/lib + /usr/bin
#     （CPU 版是直接 FROM codercom/code-server，這裡的基底不是它，所以要自己裝）。
# ZH: ⚠ 版本釘死 —— 不釘的話兩個映像的 code-server 版本會漂開，
#     而「同一份設定在另一個實驗室behave 不同」是很難查的問題。
RUN curl -fsSL https://code-server.dev/install.sh \
      | sh -s -- --version 4.96.4 \
    && rm -rf /root/.cache

# ZH: 從 Stage 1 複製打包好的 extension
COPY --from=builder /build/aibase-runner.vsix /tmp/aibase-runner.vsix

# ZH: 擴充套件清單與 CPU 版**逐項相同**（見上方說明）。
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

# ZH: entrypoint 與 CPU 版共用同一支（secrets → CLI config）。
# ZH: ⚠ Windows 上 build 時 .sh 可能被翻成 CRLF，容器會報
#     "exec …: no such file or directory"（kernel 把 `/bin/bash\r` 當解譯器）。
#     COPY 後強制轉回 LF —— CPU 版踩過這個坑。
COPY infrastructure/base-images/code-server/aibase-entrypoint.sh /usr/local/bin/aibase-entrypoint.sh
RUN sed -i 's/\r$//' /usr/local/bin/aibase-entrypoint.sh \
    && chmod +x /usr/local/bin/aibase-entrypoint.sh

# ZH: 目錄結構與 CPU 版一致（使用者的檔案掛在 /home/coder 上，兩邊要能互換）。
RUN mkdir -p /home/coder/projects /home/coder/outputs /home/coder/logs /opt/models \
    && chmod 755 /opt/models \
    && chown -R coder:coder /home/coder

USER coder
RUN echo 'export PATH="/opt/conda/bin:$HOME/.local/bin:$PATH"' >> ~/.bashrc \
    && echo 'export HF_HOME="/opt/models:$HOME/.cache/huggingface"' >> ~/.bashrc \
    && echo 'alias ll="ls -alh"' >> ~/.bashrc

WORKDIR /home/coder
EXPOSE 8080

ENTRYPOINT ["/usr/local/bin/aibase-entrypoint.sh"]
# ZH: `--auth none` 與 CPU 版相同 —— nginx 的 auth_request 已經驗過 JWT 與 user_id，
#     code-server 再要一次密碼會在 window.open 時死鎖（CPU 版 v2.1 修過）。
CMD ["--bind-addr", "0.0.0.0:8080", "--auth", "none", "/home/coder/projects"]
