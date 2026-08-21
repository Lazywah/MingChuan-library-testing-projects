# -*- coding: utf-8 -*-
"""
ZH: 會送到畫面上的錯誤訊息必須有中文。

ZH: 這個平台的使用者是中文為主的師生。一個寫著 `Permission denied` 的錯誤
    對他們而言等於沒有訊息 —— 他不知道發生什麼事，也不知道能做什麼，
    只會來問管理員，而管理員也要先去翻程式碼。

ZH: 慣例是 `detail="ZH: 中文 | EN: english"`，前端的 `zhOnly()` 依語言取一半。
    只有英文的話，兩種語言的使用者都會看到英文。

ZH: 🔴 **`worker.py` 刻意排除。** 那些訊息是給 GPU worker（程式）看的，
    不會出現在任何人的畫面上；翻譯它們只會增加雜訊，
    而雜訊會讓人開始忽略這支檢查。

ZH: 判準：`HTTPException(... detail=...)` 的字串裡有沒有中文字元。
    不檢查翻譯品質 —— 那要人看。

用法：
    python scripts/check_error_messages.py

@node scripts/check_error_messages.py
"""
import io
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
APP = ROOT / "job-scheduler" / "app"

# ZH: 機器對機器的路由 —— 它的錯誤只會進 worker 的日誌。
SKIP_FILES = {"worker.py"}

# ZH: 訊息本身就是變數（例如已經雙語的 ValueError）時，`detail=str(e)`
#     這種形狀沒有字面字串可以檢查，跳過。
_DETAIL = re.compile(r'HTTPException\([^)]*?detail\s*=\s*(f?)(["\'])(.+?)\2', re.S)


def _has_chinese(text: str) -> bool:
    return any("一" <= c <= "鿿" for c in text)


def main() -> int:
    problems, checked = [], 0
    for f in sorted(APP.rglob("*.py")):
        if f.name in SKIP_FILES:
            continue
        src = io.open(f, encoding="utf-8").read()
        for m in _DETAIL.finditer(src):
            checked += 1
            txt = m.group(3)
            if _has_chinese(txt):
                continue
            line = src[: m.start()].count("\n") + 1
            problems.append(f"{f.relative_to(ROOT)}:{line}　{txt[:60]}")

    if problems:
        print(f"[FAIL] {len(problems)} 則錯誤訊息沒有中文：")
        for p in problems:
            print(f"  - {p}")
        print()
        print('  寫法：detail="ZH: 中文 | EN: english"')
        print("  （只給程式看的訊息請放在 worker.py，或加進這支的 SKIP_FILES）")
        return 1

    print(f"[OK] {checked} 則錯誤訊息都有中文（worker.py 除外，那是給程式看的）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
