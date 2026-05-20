#!/bin/bash
# ==============================================================================
# ZH: code-server 容器啟動腳本 — 將注入的 secrets 自動轉為 CLI config
# EN: code-server entrypoint — convert injected secrets to CLI configs
# ==============================================================================
# 此腳本在容器啟動時跑一次，把環境變數轉為對應工具的設定檔
# This script runs once at container start, translating env vars to tool configs
# ==============================================================================

set -e

# ============ Kaggle ============
if [ -n "$KAGGLE_USERNAME" ] && [ -n "$KAGGLE_KEY" ]; then
    mkdir -p "$HOME/.kaggle"
    cat > "$HOME/.kaggle/kaggle.json" <<EOF
{"username":"$KAGGLE_USERNAME","key":"$KAGGLE_KEY"}
EOF
    chmod 600 "$HOME/.kaggle/kaggle.json"
    echo "[aibase-entrypoint] Kaggle credentials configured for user $KAGGLE_USERNAME"
fi

# ============ GitHub CLI ============
if [ -n "$GH_TOKEN" ]; then
    # gh CLI 從 GH_TOKEN 環境變數讀（無需 auth login），但顯式登入更明確
    echo "$GH_TOKEN" | gh auth login --with-token 2>/dev/null \
        && echo "[aibase-entrypoint] GitHub CLI authenticated" \
        || echo "[aibase-entrypoint] GitHub CLI auth skipped (token format issue, gh will read GH_TOKEN env)"
fi

# ============ HuggingFace ============
# HF_TOKEN 環境變數已存在，huggingface_hub 會自動讀取，無須額外設定
if [ -n "$HF_TOKEN" ]; then
    echo "[aibase-entrypoint] HF_TOKEN detected (will be auto-read by huggingface_hub)"
fi

# ============ 確保使用者目錄結構存在 ============
mkdir -p "$HOME/projects" "$HOME/outputs" "$HOME/logs" "$HOME/.cache/huggingface" "$HOME/.local/bin"

# ============ 設定 conda env 預設路徑（在 home volume 內）============
if [ -d /opt/conda ] && [ ! -f "$HOME/.condarc" ]; then
    cat > "$HOME/.condarc" <<EOF
envs_dirs:
  - $HOME/.conda/envs
pkgs_dirs:
  - $HOME/.conda/pkgs
auto_activate_base: false
EOF
    echo "[aibase-entrypoint] Conda configured to use ~/.conda for envs/pkgs"
fi

# ============ Welcome banner（只在第一次啟動時建立）============
WELCOME_FILE="$HOME/projects/.welcome-shown"
if [ ! -f "$WELCOME_FILE" ]; then
    cat > "$HOME/projects/README.md" <<'EOF'
# 歡迎使用 AI Base Lab！

## 快速開始

### 寫程式 + 提交 GPU 任務
1. 在 Explorer 內新增 `.py` 或 `.ipynb` 檔
2. 寫完程式後右鍵 → **「Run on GPU」**（或 Cmd+Shift+P → AI Base: Run on GPU）
3. Output panel 會即時顯示訓練輸出

### 下載資料集
在 Terminal 內：
```bash
# Kaggle
kaggle datasets download -d zynicide/wine-reviews && unzip wine-reviews.zip

# HuggingFace
huggingface-cli download --repo-type dataset squad

# GitHub
gh repo clone myteam/dataset-repo

# 一般 URL
aria2c -x 16 https://example.com/big-dataset.tar.gz
```

### 安裝套件（永久保留）
```bash
pip install --user transformers wandb     # 裝在 ~/.local/，下次仍在
# 或建立 conda env
conda create -n my-env python=3.10 pytorch -c pytorch
conda activate my-env
```

### Session 限制（學生）
- Idle 30 分鐘無互動 → 自動關閉
- Hard limit 90 分鐘 → 強制關閉
- 每日累積 6 小時上限
- **訓練 Job 不受 session 限制**（在 GPU server 獨立運行）

更多說明請見「使用者操作手冊」。
EOF
    touch "$WELCOME_FILE"
fi

# ============ 啟動 code-server ============
echo "[aibase-entrypoint] Starting code-server..."
exec /usr/bin/code-server "$@"
