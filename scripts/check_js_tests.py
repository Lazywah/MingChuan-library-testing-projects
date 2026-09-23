#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
==============================================================================
前端行為測試 / Front-end behaviour tests
==============================================================================
ZH: 跑 `tests/*.test.js`（純 node、零相依的手寫測試）。

ZH: 為什麼有這一支：這個 repo **沒有 JS 測試框架**，而前端不是沒有邏輯 ——
    引導導覽的跨頁狀態機、時區換算這些東西，錯了畫面上不會報錯，
    只會顯示錯的東西。`tests/tz.test.js` 開了這條路（純 node、手寫斷言），
    這支只是讓「再寫一支」不必再接一次線。

ZH: ⚠ `tz.test.js` **不在這裡跑** —— 它由 `check_timezone.py` 帶（那支還要
    另外比對五份 tz.js 是否一致，兩件事在同一支裡才看得出關聯）。
    重複跑一次不會壞，但會讓「哪一支在守什麼」變模糊。

ZH: 🔴 沒有 node 時**明講沒跑**，不要印 OK。
    「沒有問題」與「沒有在檢查」在畫面上長得一模一樣 ——
    這個 repo 已經因為那個差別出過兩次事（見 check_shared_ui_files.py
    與 check_untranslated_html.py 的 _dirs 註解）。

用法 / Usage:
    python scripts/check_js_tests.py          ← 有測試失敗則 exit 1
==============================================================================
"""
import shutil
import subprocess
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(errors="replace")
    sys.stderr.reconfigure(errors="replace")
except (AttributeError, ValueError):
    pass

ROOT = Path(__file__).parent.parent.resolve()
TESTS_DIR = ROOT / "tests"

# ZH: 由別支腳本負責的，這裡不重複跑（理由見檔頭）。
OWNED_ELSEWHERE = {"tz.test.js": "check_timezone.py"}


def main() -> int:
    """@node scripts/check_js_tests.py::main"""
    files = sorted(TESTS_DIR.glob("*.test.js"))
    mine = [f for f in files if f.name not in OWNED_ELSEWHERE]
    others = [f for f in files if f.name in OWNED_ELSEWHERE]

    if not files:
        # ZH: 一個都沒有時不失敗 —— 這支是「有就跑」，不是「一定要有」。
        print("[OK] 沒有 tests/*.test.js，略過")
        return 0

    node = shutil.which("node")
    if not node:
        print("[WARN] 找不到 node —— 前端行為測試**沒有跑**（不是通過）")
        print("       要跑的有：%s" % "、".join(f.name for f in mine))
        return 0

    failed = []
    for f in mine:
        r = subprocess.run([node, str(f)], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", cwd=str(ROOT))
        tag = "OK" if r.returncode == 0 else "FAIL"
        print(f"  [{tag}] {f.name}")
        if r.returncode != 0:
            failed.append(f.name)
            for line in (r.stdout or "").splitlines():
                if "FAIL" in line or "預期" in line or "得到" in line:
                    print(f"        {line.strip()}")
            if r.stderr.strip():
                print(f"        {r.stderr.strip().splitlines()[-1]}")

    for f in others:
        print(f"  [--] {f.name}（由 {OWNED_ELSEWHERE[f.name]} 負責）")

    if failed:
        print(f"\n[FAIL] {len(failed)} 支前端測試沒過：{'、'.join(failed)}")
        return 1
    print(f"\n[OK] {len(mine)} 支前端行為測試通過")
    return 0


if __name__ == "__main__":
    sys.exit(main())
