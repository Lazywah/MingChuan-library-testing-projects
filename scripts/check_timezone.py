#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
==============================================================================
時區一致性檢查 / Timezone consistency check
==============================================================================
ZH: 全站顯示的時間一律為**台灣時間**（Asia/Taipei），規則實作在 `tz.js`。
    這支檢查三件事：

      1. **五個 UI 目錄的 tz.js 逐位元組相同。**
         沒有共用機制（各 UI 由 nginx 以不同 alias 提供，沒有共享路徑），
         所以檔案是複製的。「記得同步五份」不是約束，可機械檢查才是。
      2. **載入 tz.js 的頁面，順序在使用它的 JS 之前。**
         順序錯的症狀是 `TW is not defined`，只在該頁真的渲染時間時才炸。
      3. **tz.js 的行為測試通過**（需要 node；沒有 node 時明講「沒跑」，
         不假裝通過——§ skip 不是 pass）。

⚠ ZH: 一個**刻意的例外**，不要「順手修好」：
    `myai_transactions.occurred_at` 存的是**廠商當地時間**（已是台灣時間的
    naive 值），不是 UTC。admin.js 的 MYAI「近期事件」表刻意用原字串顯示，
    套 tz.js 會再推 8 小時。該處有註解說明。

用法 / Usage:
    python scripts/check_timezone.py           ← 檢查，有問題 exit 1
==============================================================================
"""
import hashlib
import re
import subprocess
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(errors="replace")
    sys.stderr.reconfigure(errors="replace")
except (AttributeError, ValueError):
    pass

ROOT = Path(__file__).parent.parent.resolve()
CANONICAL = ROOT / "web-ui-V1" / "tz.js"          # 正本
# ZH: 測試檔放 tests/ 而非 web-ui-V1/ —— 後者是 nginx 對外提供的靜態目錄，
#     測試檔不該被公開提供。
TEST_FILE = ROOT / "tests" / "tz.test.js"

# ZH: 用 glob 自動探索，不寫死清單 —— 寫死的話新增的 UI 目錄自動免疫
#     （bump_assets.py 就踩過這個坑）。
UI_DIRS = sorted(
    d for d in ROOT.iterdir()
    if d.is_dir() and (d.name.startswith("web-ui") or d.name.startswith("admin-ui"))
)


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()[:12]


def check_copies() -> list[str]:
    """ZH: 每個「有頁面引用 tz.js」的 UI 目錄都必須有一份，且與正本相同。"""
    problems = []
    if not CANONICAL.is_file():
        return [f"找不到正本 {CANONICAL.relative_to(ROOT)}"]
    want = _sha(CANONICAL)

    for d in UI_DIRS:
        refs = [h for h in d.glob("*.html") if 'src="tz.js' in h.read_text(encoding="utf-8")]
        f = d / "tz.js"
        if not refs:
            # ZH: 沒有任何頁面引用就不強制要有——但若檔案在那裡，內容仍須一致，
            #     否則會出現一份沒人用卻已經漂掉的副本，日後被複製出去。
            if f.is_file() and _sha(f) != want:
                problems.append(f"{d.name}/tz.js 與正本不同（且該目錄沒有頁面引用它）")
            continue
        if not f.is_file():
            problems.append(f"{d.name} 有頁面引用 tz.js，但該目錄沒有這個檔")
        elif _sha(f) != want:
            problems.append(f"{d.name}/tz.js 與正本不同（{_sha(f)} vs {want}）")
    return problems


def check_order() -> list[str]:
    """ZH: tz.js 必須排在使用它的 JS 之前，否則是 TW is not defined。"""
    problems = []
    tag = re.compile(r'<script[^>]+src="([^"?]+)[^"]*"')
    for d in UI_DIRS:
        for h in sorted(d.glob("*.html")):
            text = h.read_text(encoding="utf-8")
            if 'src="tz.js' not in text:
                continue
            srcs = tag.findall(text)
            if "tz.js" not in srcs:
                continue
            i = srcs.index("tz.js")
            # ZH: 只看同目錄的自家 JS（CDN 那些不相干），且只挑真的用到 TW 的。
            users = [x for x in srcs[:i]
                     if (d / x).is_file() and "TW." in (d / x).read_text(encoding="utf-8")]
            if users:
                problems.append(
                    f"{d.name}/{h.name}：{', '.join(users)} 排在 tz.js 之前，會 TW is not defined")
    return problems


def check_behaviour() -> tuple[list[str], list[str]]:
    """ZH: 跑 tz.test.js。沒有 node 時回 warning，不假裝通過。"""
    if not TEST_FILE.is_file():
        return [f"找不到 {TEST_FILE.relative_to(ROOT)}"], []
    try:
        r = subprocess.run(["node", str(TEST_FILE)], capture_output=True,
                           text=True, encoding="utf-8", errors="replace", timeout=60)
    except (FileNotFoundError, OSError):
        return [], ["找不到 node，**tz.js 的行為測試沒有執行**（不是通過）。"
                    "有 node 的機器請跑：node tests/tz.test.js"]
    if r.returncode != 0:
        tail = [l for l in (r.stdout or "").splitlines() if l.startswith("FAIL")]
        return ["tz.js 行為測試失敗：" + ("；".join(tail) or "見 node tests/tz.test.js")], []
    return [], []


def main() -> int:
    errs = check_copies() + check_order()
    berrs, warns = check_behaviour()
    errs += berrs

    print("時區一致性檢查（全站顯示一律 Asia/Taipei）")
    print(f"  正本 web-ui-V1/tz.js  sha {_sha(CANONICAL) if CANONICAL.is_file() else '?'}")
    print(f"  掃描 {len(UI_DIRS)} 個 UI 目錄：{', '.join(d.name for d in UI_DIRS)}")
    for w in warns:
        print(f"  [WARN] {w}")
    if errs:
        for e in errs:
            print(f"  [FAIL] {e}")
        print(f"\n[FAIL] {len(errs)} 項不一致")
        return 1
    print("\n[OK] tz.js 五份一致、載入順序正確、行為測試通過"
          if not warns else "\n[OK] 檔案一致性通過（行為測試未執行，見上方 WARN）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
