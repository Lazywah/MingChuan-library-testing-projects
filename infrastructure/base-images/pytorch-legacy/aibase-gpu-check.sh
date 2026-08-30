#!/bin/bash
# ==============================================================================
# ZH: pytorch-legacy 的開機防呆 —— 把「安靜的不相容」變成「吵的失敗」。
#
# ZH: 為什麼需要：這個映像的 torch 是 cu118 wheel，kernel 只編到 sm_90。
#     在更新的卡（如 RTX 5090 = sm_120）上，`torch.cuda.is_available()`
#     照樣回 **True**，直到第一次真的算東西才丟出
#     `no kernel image is available for execution on the device` ——
#     學生看不懂，而且多半已經排了隊、等了很久。（2026-08-30 於 5090 實測。）
#
# ZH: 做法：容器啟動時用 nvidia-smi 讀 compute capability，超過本映像
#     支援上限就**拒絕啟動**並用人話說明該換哪個映像。
#       - 沒掛 GPU（nvidia-smi 不存在）→ 不擋，CPU 用途照常。
#       - 讀不到 capability → 不擋（探測失敗不該誤傷正常使用）。
#       - AIBASE_SKIP_GPU_CHECK=1 → 跳過（刻意要 CPU-only 跑在新卡機器上時用）。
#
# ZH: 上限由 Dockerfile 的 ENV AIBASE_MAX_SM 提供（cu118 → 90）。
#     升級 CUDA base 時要一起改那個 ENV，不是改這支腳本。
#
# EN: Startup guard: cu118 wheels ship kernels only up to sm_90, yet
#     cuda.is_available() still returns True on newer GPUs — the failure is
#     silent until the first real kernel launch. Refuse to start with a clear
#     message instead. Skippable via AIBASE_SKIP_GPU_CHECK=1; never blocks
#     CPU-only runs (no nvidia-smi → no check).
# ==============================================================================
set -u

if [ "${AIBASE_SKIP_GPU_CHECK:-0}" != "1" ] && command -v nvidia-smi >/dev/null 2>&1; then
    max_sm="${AIBASE_MAX_SM:-90}"
    # ZH: 可能多卡，逐一檢查；輸出形如 "12.0" → 120
    caps="$(nvidia-smi --query-gpu=compute_cap --format=csv,noheader 2>/dev/null || true)"
    while IFS= read -r cap; do
        [ -z "$cap" ] && continue
        sm="$(echo "$cap" | tr -d ' .' )"
        case "$sm" in (*[!0-9]*|'') continue;; esac
        if [ "$sm" -gt "$max_sm" ]; then
            name="$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | head -1)"
            echo "==============================================================" >&2
            echo "❌ 這個環境（PyTorch CUDA 11.8 Legacy）不支援你的 GPU" >&2
            echo "   GPU: ${name:-unknown} (sm_${sm})，本映像的 kernel 最高只到 sm_${max_sm}" >&2
            echo "   torch.cuda.is_available() 會回 True，但一算就會失敗：" >&2
            echo "   'no kernel image is available for execution on the device'" >&2
            echo "" >&2
            echo "   ➜ 請改用主要環境 aibase/pytorch（CUDA 12.8，支援到 sm_120）" >&2
            echo "   ➜ 這個 Legacy 環境是給**驅動太舊、跑不了 CUDA 12.8** 的機器用的" >&2
            echo "" >&2
            echo "EN: This legacy cu118 image does not support this GPU" >&2
            echo "    (sm_${sm} > sm_${max_sm}). Use aibase/pytorch instead." >&2
            echo "    Set AIBASE_SKIP_GPU_CHECK=1 only for deliberate CPU-only runs." >&2
            echo "==============================================================" >&2
            exit 1
        fi
    done <<< "$caps"
fi

exec "$@"
