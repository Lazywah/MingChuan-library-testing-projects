# -*- coding: utf-8 -*-
"""
ZH: 前端的每一支 .js 都必須是**能解析的 JavaScript**。

ZH: 🔴 為什麼需要這支 —— 實際發生過，而且**已經 commit 進去了**：

      pf_external_warn: '... reads the user's own files. ...'
                                          ^ 單引號字串被這個撇號截斷

    後果是 `i18n-admin.js` 整個無法解析、`Object.assign` 從來沒執行，
    於是**英文模式下管理端的翻譯全部失效**。

ZH: 而它為什麼沒被任何人發現：
      1. 中文模式看起來完全正常 —— `T('key', '中文原文')` 的 fallback 接住了
      2. `check_i18n.py` 用正規表示式讀字典，**不驗這個檔是不是合法的 JS**
      3. 頁面不會整個壞掉 —— 每個 <script> 各自獨立，其他支照跑
    三件事加起來，就是一個「看起來一切正常」的靜默失效。

ZH: 這支只做一件事：把每支 .js 丟給 node 解析。不檢查風格、不檢查邏輯。
    判準是零判斷空間的事實 —— 能不能解析。

ZH: 沒有 node 時回 WARN 不是 FAIL —— 部署機不一定裝 node，
    而「因為量不到就說它壞了」比不量還糟。

用法：
    python scripts/check_js_syntax.py

@node scripts/check_js_syntax.py
"""
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _ui_dirs():
    return sorted(
        d for d in ROOT.iterdir()
        if d.is_dir() and (d.name.startswith("web-ui") or d.name.startswith("admin-ui"))
    )


def main() -> int:
    node = shutil.which("node")
    if not node:
        print("[WARN] 找不到 node，略過 JS 語法檢查")
        return 0

    problems, checked = [], 0
    for d in _ui_dirs():
        for f in sorted(d.glob("*.js")):
            checked += 1
            # ZH: `--check` 只解析不執行 —— 這些檔案會碰 document/window，
            #     真的跑起來一定會炸，那不是我們要測的東西。
            r = subprocess.run([node, "--check", str(f)],
                               capture_output=True, text=True,
                               encoding="utf-8", errors="replace")
            if r.returncode != 0:
                first = next((l.strip() for l in (r.stderr or "").splitlines()
                              if "Error" in l or "error" in l), "")
                problems.append(f"{f.relative_to(ROOT)}：{first or '解析失敗'}")

    if problems:
        print(f"[FAIL] {len(problems)} 支 JS 無法解析：")
        for p in problems:
            print(f"  - {p}")
        print()
        print("  最常見的原因：單引號字串裡有沒跳脫的撇號（例如 user's）。")
        return 1

    print(f"[OK] {checked} 支 JS 都能解析")
    return 0


if __name__ == "__main__":
    sys.exit(main())
