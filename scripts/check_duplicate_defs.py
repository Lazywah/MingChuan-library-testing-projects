# -*- coding: utf-8 -*-
"""
ZH: 檢查 Python 模組層的**重複定義**（同一個檔案裡同名的 def / class 出現兩次以上）。

ZH: 為什麼需要機械檢查：重複定義**不會報錯**。Python 直接用最後一份，
    測試全綠、程式行為正確、code review 也很容易滑過去——因為兩份長得一樣。
    直到有人只改了其中一份，才會出現「我明明改了卻沒有作用」。

ZH: 這支是被真實事故逼出來的（2026-08-20）：批次修補腳本在多檔模式下
    「前面的檔案已寫入、後面的錨點才失敗」，我修完重跑，於是 crud.py 裡
    `job_needs_lab_volume` 與 `has_colocated_worker` 各有兩份。
    全套 203 支測試沒有任何一支變紅。

ZH: 與 check_timezone / check_i18n 同一類：把「靜默且正確」的錯誤變成看得見的。

@node scripts/check_duplicate_defs.py
"""
import ast
import collections
import io
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent

# ZH: 掃描範圍。第三方與產生物不掃。
SCAN_DIRS = ["job-scheduler/app", "gpu-worker", "scripts", "rag-service"]
SKIP_PARTS = {"__pycache__", "node_modules", ".venv", "venv", "migrations"}

# ZH: 刻意允許重複的名稱（型別分支、平台分支等）。目前為空——有需要時列在這裡並寫原因。
ALLOWED = {}


def scan(path: pathlib.Path):
    """ZH: 回傳 {名稱: 出現次數} 中大於 1 的部分。

    ZH: 只看**模組層**（tree.body）。函式內的區域重新指派是正常的 Python，
        類別內的方法重複則另外看（見下）。

    @node scripts/check_duplicate_defs.py::scan
    """
    try:
        tree = ast.parse(io.open(path, encoding="utf-8").read())
    except SyntaxError as e:
        return {}, f"{e.lineno}: {e.msg}"

    found = collections.defaultdict(list)
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            found[node.name].append(node.lineno)
        # ZH: 模組層常數重複指派也算——「改了上面那份卻沒作用」同一個症狀。
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id.isupper():
                    found[t.id].append(node.lineno)

    # ZH: 類別內的方法重複（同一個 class 裡兩個同名 def）——後者無聲蓋掉前者。
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            inner = collections.defaultdict(list)
            for m in node.body:
                if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    inner[m.name].append(m.lineno)
            for name, lines in inner.items():
                if len(lines) > 1:
                    found[f"{node.name}.{name}"] = lines

    return {k: v for k, v in found.items() if len(v) > 1}, None


def main() -> int:
    """@node scripts/check_duplicate_defs.py::main"""
    files = []
    for d in SCAN_DIRS:
        base = ROOT / d
        if not base.exists():
            continue
        for p in base.rglob("*.py"):
            if SKIP_PARTS & set(p.parts):
                continue
            files.append(p)

    bad = 0
    for p in sorted(files):
        rel = p.relative_to(ROOT).as_posix()
        dups, err = scan(p)
        if err:
            print(f"  [!] {rel} 語法錯誤 / syntax error — {err}")
            bad += 1
            continue
        for name, lines in sorted(dups.items()):
            if ALLOWED.get(rel) == name:
                continue
            print(f"  [X] {rel}: `{name}` 定義了 {len(lines)} 次（行 {', '.join(map(str, lines))}）"
                  f" — 只有最後一份有效 / only the last one takes effect")
            bad += 1

    print(f"\n  掃描 {len(files)} 個 .py 檔 / scanned {len(files)} files")
    if bad:
        print(f"\n[FAIL] {bad} 處重複定義。刪掉多餘的那份，或在 ALLOWED 列出並寫明原因。")
        return 1
    print("\n[OK] 無重複定義 / no duplicate definitions")
    return 0


if __name__ == "__main__":
    sys.exit(main())
