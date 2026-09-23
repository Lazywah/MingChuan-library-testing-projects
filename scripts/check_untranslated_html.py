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

# ZH: 主控台／管線若為 cp950（中文 Windows 預設），遇到不可編碼字元改為替代字而非崩潰。
#     deploy_check 用 subprocess 跑這支，stdout 是管線 → Windows 上取地區編碼不是 UTF-8。
#     沒有這段的話，印一個 ⚠ 就會 UnicodeEncodeError、exit 1，被回報成「檢查失敗」。
try:
    sys.stdout.reconfigure(errors="replace")
    sys.stderr.reconfigure(errors="replace")
except (AttributeError, ValueError):
    pass

ROOT = pathlib.Path(__file__).resolve().parent.parent
CJK = re.compile(r"[一-鿿]")

# ZH: 只管現行世代（`-V1`）。V0 / V0.5 是既有版本，它們沒有這套 i18n 機制，
#     掃它們只會產生一堆改不動的警告。
#
# ZH: 🔴 這裡原本寫的是 `-v2`，而目錄在改名成 `-V1` 之後**沒有人回來改這一行** ——
#     於是這支掃 0 個目錄、印 `[OK] 0 段中文都掛了 data-i18n`、回傳 0，
#     `deploy_check` 也跟著顯示綠勾。**守衛看起來在站崗，實際上沒有。**
#     2026-09-23 首頁改版前查到（改版正是最需要它的時候）。
#     同一個坑 check_shared_ui_files.py 踩過一次，它的解法抄在下面的 main()。
def _dirs():
    return sorted(d for d in ROOT.iterdir() if d.is_dir() and d.name.endswith("-V1"))


def main() -> int:
    problems, checked = [], 0

    # ZH: 🔴 探不到任何目錄 = 探索規則已經跟不上目錄命名，**不是「沒有問題」**。
    #     這兩件事在畫面上長得一模一樣（都是一行 OK），而實際上一個是保護、
    #     一個是裸奔。這支就這樣裸奔過一段時間（見上方 _dirs()）。
    dirs = _dirs()
    if not dirs:
        print("[FAIL] 找不到任何要檢查的 UI 目錄 —— 探索規則失效了，不是「沒有問題」。")
        print("       目錄可能又改名了。請看本檔的 _dirs()。")
        print("       現有目錄：%s"
              % "、".join(sorted(d.name for d in ROOT.iterdir() if d.is_dir())))
        return 1

    for d in dirs:
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
