# -*- coding: utf-8 -*-
"""
ZH: 檢查每一頁 HTML 都載了它的 JS 會用到的那些「共用全域」。

ZH: 為什麼要有這支 —— 實際發生過：`lab.js` 用了 `TW.when(...)`，
    但 `lab.html` 沒有載 `tz.js`。症狀非常會騙人：

      1. 頁面正常載入、console **乾乾淨淨**（例外被 loadSessions 的 catch 吃掉了）
      2. 畫面顯示「暫時讀不到存檔清單」——看起來像**後端或網路**的問題
      3. 而後端其實好好的，資料也真的拿到了

    也就是說，一個少寫的 `<script>` 標籤偽裝成了網路故障。
    這與記憶裡「呼叫端打錯名字」是同一族：靜態沒人擋、測試不會覆蓋、
    上線之後也不會有人回報（使用者只會覺得「這個功能怪怪的」）。

ZH: 判準刻意保守 —— 只認**這個專案自己的共用全域**（下面那張表），
    不去猜瀏覽器內建或第三方。寧可漏抓，也不要製造一堆假警報讓人開始忽略它。

ZH: exit code：有問題回 1。這支**是**可以擋的（與 archgraph 那邊不同）——
    它檢查的是「檔案有沒有被載入」這種零判斷空間的事實。

@node scripts/check_js_globals.py
"""
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent

# ZH: 共用全域 -> 定義它的檔案。加新的共用檔時**要一起加到這裡**，
#     否則這支檢查對它視而不見（而它不會告訴你它視而不見）。
PROVIDERS = {
    "TW":     "tz.js",
    "T":      "i18n.js",
    "I18N":   "i18n.js",
    "Prefs":  "prefs.js",
}

# ZH: 只認「識別字後面接 . 或 (」，並且前面不能是 . 或字元
#     （避免把 `foo.T(` 或 `SOMETHING_T` 算進來）
def _uses(src: str, name: str) -> bool:
    return re.search(r"(?<![\w.$])" + re.escape(name) + r"\s*[.(]", src) is not None


def _scripts(html: str) -> list:
    """ZH: 這一頁載入的**本地** JS 檔名。

    ZH: 外部 CDN（http/https/協定相對）一律跳過 —— 那些不是這支要管的事，
        而且第一版把它們算進來時一口氣噴了 9 個假警報。
        假警報多到一定程度，人就會開始整支忽略，那比沒有這支檢查更糟。
    """
    out = []
    for src in re.findall(r'<script[^>]+src="([^"?]+)', html):
        if src.startswith(("http://", "https://", "//")):
            continue
        out.append(src)
    return out


def main() -> int:
    problems = []
    checked = 0

    # ZH: 🔴 要涵蓋 **admin-ui\* 也要**。第一版只寫了 `web-ui*`，
    #     那正是 check_timezone.py 註解裡警告過的坑：
    #     「寫死的話新增的 UI 目錄自動免疫」——而它免疫時是**安靜的**，
    #     檢查照樣印 [OK]，只是它根本沒去看那個目錄。
    ui_dirs = sorted(
        d for d in ROOT.iterdir()
        if d.is_dir() and (d.name.startswith("web-ui") or d.name.startswith("admin-ui"))
    )
    for ui_dir in ui_dirs:
        for html_path in sorted(ui_dir.glob("*.html")):
            html = html_path.read_text(encoding="utf-8", errors="replace")
            loaded = set(_scripts(html))
            if not loaded:
                continue
            checked += 1

            for js_name in _scripts(html):
                js_path = ui_dir / js_name
                if not js_path.exists():
                    problems.append(
                        f"{html_path.relative_to(ROOT)} 載入了不存在的檔案：{js_name}")
                    continue
                src = js_path.read_text(encoding="utf-8", errors="replace")
                for glob_name, provider in PROVIDERS.items():
                    if provider == js_name:
                        continue          # ZH: 定義它的檔案自己當然可以用
                    if _uses(src, glob_name) and provider not in loaded:
                        problems.append(
                            f"{html_path.relative_to(ROOT)} 沒有載 {provider}，"
                            f"但 {js_name} 用到了 {glob_name}")

    problems = sorted(set(problems))
    if problems:
        print(f"[FAIL] {len(problems)} 個頁面缺少它用到的共用檔：")
        for p in problems:
            print(f"  - {p}")
        print()
        print("  修法：在該 HTML 的 <script> 區塊補上對應檔案，順序要在使用它的那支之前。")
        return 1

    print(f"[OK] {checked} 個頁面的共用全域都有對應的 <script>")
    return 0


if __name__ == "__main__":
    sys.exit(main())
