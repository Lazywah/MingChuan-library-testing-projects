# -*- coding: utf-8 -*-
"""
ZH: HTML 裡看得見的中文，都必須掛 `data-i18n`。

ZH: 🔴 為什麼需要這支 —— `check_i18n.py` 檢查的是「**已經掛上** data-i18n 的
    那些 key 有沒有翻譯」。一段**完全沒掛**的中文它看不到，
    於是那段文字在英文模式下永遠是中文，而且不會有任何提示。

ZH: 實際找到五處（都在使用者端）：四個「讀取中…」的載入佔位字，
    以及 train.html 裡**常駐**的路徑約定 —— 後者是使用者寫程式時要照的規格，
    英文使用者會一直看到中文。

ZH: 刻意排除的：
      - HTML 註解（`<!-- -->`）
      - `<script>` / `<style>` 的內容
      - 產品名與識別碼（MCU AI Base、MYAI…）—— 那些本來就不翻

ZH: 這支只看**文字節點**。屬性裡的中文（placeholder / title / aria-label）
    要用 `data-i18n-placeholder` 等，那由 check_i18n 那邊管。

用法：
    python scripts/check_untranslated_html.py

@node scripts/check_untranslated_html.py
"""
import io
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
CJK = re.compile(r"[一-鿿]")

# ZH: 只管 v2 世代。v1 / v1.5 是既有版本，它們沒有這套 i18n 機制，
#     掃它們只會產生一堆改不動的警告。
def _dirs():
    return sorted(d for d in ROOT.iterdir() if d.is_dir() and d.name.endswith("-v2"))


def main() -> int:
    problems, checked = [], 0

    for d in _dirs():
        for f in sorted(d.glob("*.html")):
            html = io.open(f, encoding="utf-8").read()
            # ZH: 註解裡的中文是寫給維護者看的，不會出現在畫面上。
            body = re.sub(r"<!--.*?-->", "", html, flags=re.S)
            # ZH: script / style 的內容不是給人讀的文字。
            body = re.sub(r"<(script|style)\b.*?</\1>", "", body, flags=re.S | re.I)

            for m in re.finditer(r"<([a-z0-9]+)([^>]*)>([^<>]+)<", body, re.I):
                tag, attrs, text = m.group(1), m.group(2), m.group(3)
                if not CJK.search(text):
                    continue
                checked += 1
                if "data-i18n" in attrs:
                    continue
                line = body[: m.start()].count("\n") + 1
                flat = " ".join(text.split())[:50]
                problems.append(f"{f.relative_to(ROOT)}:{line}　<{tag}>　{flat}")

    if problems:
        print(f"[FAIL] {len(problems)} 段中文沒有掛 data-i18n：")
        for p in problems:
            print(f"  - {p}")
        print()
        print("  修法：給那個元素加 data-i18n=\"key\"，並在 i18n.js 補上中英兩份。")
        print("  （產品名或不需要翻的東西，請放在註解裡說明為什麼）")
        return 1

    print(f"[OK] {checked} 段中文都掛了 data-i18n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
