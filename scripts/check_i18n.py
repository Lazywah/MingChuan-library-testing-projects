#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
==============================================================================
翻譯完整性檢查 / i18n completeness check
==============================================================================
ZH: `web-ui-v2` 的介面文案走 `i18n.js` 的字典。這支比對三件事：

      1. **程式碼用到的 key，字典兩種語言都要有。**
         少一個 key 的症狀是「那一句永遠是中文」——不會報錯、版面也正常，
         只有懂中文的人看不出來（而看得出來的人正是看不懂中文的那個）。
      2. **字典裡有、但沒有人用的 key**（改文案時忘了刪，會慢慢累積成垃圾）。
      3. **中英兩邊的佔位符必須一致**（`{n}` `{d}` …）。
         呼叫端是 `.replace('{n}', v)`；英文少一個佔位符，畫面上就少一個數字，
         而句子本身仍然通順——**這種錯特別不容易被看出來**。

⚠ ZH: 這支**不檢查翻譯品質**，只檢查「有沒有」與「形狀對不對」。
    措辭好不好要人看。

用法 / Usage:
    python scripts/check_i18n.py         ← 有問題 exit 1
==============================================================================
"""
import re
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(errors="replace")
    sys.stderr.reconfigure(errors="replace")
except (AttributeError, ValueError):
    pass

ROOT = Path(__file__).parent.parent.resolve()

# ZH: 🔴 要檢查的每一個 UI 目錄，以及它的字典由哪幾個檔案組成。
#     管理端 v2 的字典是 `i18n.js`（共用正本，一個字都不改）
#     + `i18n-admin.js`（管理端專屬 key，用 Object.assign 併進去）。
#
# ZH: 為什麼要明寫而不是自動探索：一個目錄的字典由哪些檔案組成**是設計決定**，
#     不是可以從檔名猜的。猜錯的方向會是「少算一個字典檔 → 把有翻譯的 key
#     報成缺翻譯」，那會讓人去補一個已經存在的東西。
TARGETS = [
    ("web-ui-v2", ["i18n.js"]),
    ("admin-ui-v2", ["i18n.js", "i18n-admin.js"]),
]

# ZH: 不是 key 的東西：
#   key   — 函式簽章裡的參數名（`t(key, fallback)`）
#   zh/en — 語言切換鈕的 `[['zh', '中文'], ['en', 'English']]`，剛好符合
#           「字串後面接含中文的字串」這個形狀。**這是形狀判準的已知代價**，
#           寫死排除比把判準改窄好（改窄會重新漏掉以參數傳 key 的呼叫）。
IGNORE_USED = {"key", "zh", "en"}
# ZH: key 是**在執行時組出來的**，掃描器看不到字面值，所以不算「沒人用」。
#   role_ — `T('role_' + user.role, …)`
#   st_   — `T('st_' + node.state, …)`（管理端的節點六態、任務狀態）
#
# ⚠ 代價：這兩個前綴底下**真的沒人用的 key 也不會被抓到**。
#   這是知情的取捨 —— 另一個方向（把它們報成沒人用）會讓人去刪掉
#   實際還在用的翻譯，那個錯誤嚴重得多。
DYNAMIC_PREFIXES = ("role_", "st_")


def used_keys(ui: Path, dict_files: list) -> dict:
    """ZH: 掃 HTML 的 data-i18n* 與 JS 的 T('…') / Prefs.t('…') / L('…')。"""
    found = {}
    for f in sorted(ui.glob("*.html")):
        s = f.read_text(encoding="utf-8")
        for m in re.finditer(r'data-i18n(?:-placeholder|-aria)?="([^"]+)"', s):
            found.setdefault(m.group(1), set()).add(f.name)
    for f in sorted(ui.glob("*.js")):
        # ZH: 字典檔本身不算「使用」—— 它裡面全是 key 的定義。
        if f.name in dict_files:
            continue
        s = f.read_text(encoding="utf-8")
        # ZH: 判準是**形狀**不是函式名：「key 後面接一個含中文的 fallback」。
        #     這樣 T('k','中')、item(el,'k','中')、stepBtn(-10,'k','中','A−') 全部涵蓋。
        #     一開始只抓 `T('…'`，漏掉五個「以參數傳 key」的呼叫，
        #     卻把它們報成「字典有但沒人用」——**誤判方向剛好是最會誤導人的那個**
        #     （照著修就會把真的有用的翻譯刪掉）。
        for m in re.finditer(r"'([a-z0-9_]+)'\s*,\s*'[^']*[一-鿿]", s):
            found.setdefault(m.group(1), set()).add(f.name)
        for m in re.finditer(r"setAttribute\(\s*'data-i18n[a-z-]*'\s*,\s*'([a-z0-9_]+)'", s):
            found.setdefault(m.group(1), set()).add(f.name)
        # ZH: JS 直接組 HTML 字串時寫的 `data-i18n="key"`。
        #     管理端的 admin-chrome.js 就是這樣產生頂部列的，
        #     漏掉這個形狀會把**實際有在用**的 key 報成「沒有人用」——
        #     而照著那個報告修，會把還在用的翻譯刪掉。
        for m in re.finditer(r'data-i18n(?:-placeholder|-aria)?="([a-z0-9_]+)"', s):
            found.setdefault(m.group(1), set()).add(f.name)
    return {k: v for k, v in found.items() if k not in IGNORE_USED}


def dict_keys(ui: Path, dict_files: list) -> dict:
    """ZH: 從這個目錄的字典檔取出 zh / en 兩份的 key → 值。

    ZH: 一個目錄的字典可能由**多個檔案**組成：管理端是
        `i18n.js`（共用正本，一個字都不改）+ `i18n-admin.js`（自己的 key）。
        後者靠 `Object.assign` 併進同一本字典，所以這裡也要把兩份合起來算。
    """
    out = {"zh": {}, "en": {}}
    for name in dict_files:
        s = (ui / name).read_text(encoding="utf-8")
        for lang in ("zh", "en"):
            out[lang].update(_one_lang(s, lang))
    return out


def _one_lang(s: str, lang: str) -> dict:
    """ZH: 從一份原始碼裡切出某個語言的 key → 值。

    ZH: 用括號配對切區塊，不用「找下一個 `},`」——
        字典值裡本來就有 `}`（佔位符），那種切法會在第一個佔位符就切斷。

    ZH: 兩種寫法都要認：
          `zh: {`                            → i18n.js 的本體
          `I18N.zh, {`                       → i18n-admin.js 的 Object.assign 擴充
    """
    m = (re.search(r"\n\s+%s:\s*\{" % lang, s)
         or re.search(r"I18N\.%s\s*,\s*\{" % lang, s))
    if not m:
        return {}
    i = s.index("{", m.start())
    depth, j = 0, i
    while j < len(s):
        if s[j] == "{":
            depth += 1
        elif s[j] == "}":
            depth -= 1
            if depth == 0:
                break
        j += 1
    body = s[i:j]
    return dict(re.findall(r"\n\s+([a-z0-9_]+):\s*'((?:[^'\\]|\\.)*)'", body))


def html_fallbacks(ui: Path) -> list:
    """ZH: 取出各 HTML 裡 `data-i18n="k">文字<` 的 (檔名, key, 文字)。

    ZH: 只看**單純的文字節點**——內容含標籤的（例：`<strong>`）跳過，
        那種是刻意分段標記的，與字典的整句本來就不會逐字相同。

    @node scripts/check_i18n.py::html_fallbacks
    """
    out = []
    pat = re.compile(r'data-i18n="([a-z0-9_]+)"[^>]*>([^<>]+)<')
    for f in sorted(ui.glob("*.html")):
        html = f.read_text(encoding="utf-8")
        for key, text in pat.findall(html):
            out.append((f.name, key, text.strip()))
    return out


PLACEHOLDER = re.compile(r"\{[a-z]\}")


def check_one(dirname: str, dict_files: list) -> list:
    """ZH: 檢查一個 UI 目錄，回傳問題清單（空的代表過）。"""
    ui = ROOT / dirname
    problems = []

    missing = [f for f in dict_files if not (ui / f).is_file()]
    if missing:
        return [f"{dirname} 找不到字典檔：{', '.join(missing)}"]

    used = used_keys(ui, dict_files)
    d = dict_keys(ui, dict_files)
    zh, en = d.get("zh", {}), d.get("en", {})

    for k, where in sorted(used.items()):
        if k.startswith(DYNAMIC_PREFIXES):
            continue
        for lang, table in (("zh", zh), ("en", en)):
            if k not in table:
                problems.append(f"{lang} 缺 key `{k}`（用在 {', '.join(sorted(where))}）")

    # ZH: 🔴 兩種語言要**對稱** —— 一邊有、另一邊沒有就是漏翻。
    #     這一條與「有沒有人用」無關，所以動態前綴也逃不掉。
    #
    # ZH: 為什麼要獨立寫一條：上面那個迴圈對 DYNAMIC_PREFIXES 是 `continue`，
    #     於是 `st_working` 只有中文、沒有英文時**完全不會被抓到**，
    #     英文模式下就會靜默退回中文。這是陽性對照抓到的（我原本以為有守住）。
    for k in sorted(set(zh) ^ set(en)):
        miss = "en" if k in zh else "zh"
        problems.append(f"{miss} 缺 key `{k}`（另一種語言有，這是漏翻）")

    dynamic_ok = {k for k in list(zh) + list(en) if k.startswith(DYNAMIC_PREFIXES)}
    unused = (set(zh) | set(en)) - set(used) - dynamic_ok
    # ZH: 🔴 共用的 i18n.js 在管理端**一定會有一堆沒人用的 key**
    #     （使用者端的文案），那不是錯誤。只把「這個目錄自己的字典檔」
    #     定義的 key 拿來算多餘。
    own = set()
    for name in dict_files:
        if name == "i18n.js" and dirname != "web-ui-v2":
            continue        # 共用正本，歸使用者端管
        own |= set(dict_keys(ui, [name]).get("zh", {}))
        own |= set(dict_keys(ui, [name]).get("en", {}))
    for k in sorted(unused & own):
        problems.append(f"字典有 `{k}` 但沒有人用（改文案時忘了刪？）")

    for k in sorted(set(zh) & set(en)):
        a = sorted(PLACEHOLDER.findall(zh[k]))
        b = sorted(PLACEHOLDER.findall(en[k]))
        if a != b:
            problems.append(f"`{k}` 的佔位符不一致：zh {a or '無'} vs en {b or '無'}")

    # ZH: HTML 的 fallback 文字 vs zh 字典。同一句兩份，只改一份是靜默的。
    #     執行時字典會蓋掉 HTML，所以「改了 HTML 沒改字典」＝改了等於沒改。
    for fname, key, text in html_fallbacks(ui):
        want = zh.get(key)
        if want is None:
            continue
        # ZH: 字典是 JS 原始碼，值裡的 \n / \' 是**逸出序列**；HTML 裡是真正的字元。
        #     不解逸出就比，多行文案一定報假陽性（第一版就是這樣，被 tr_tree 抓到）。
        want_decoded = (want.replace("\\n", "\n").replace("\\t", "\t")
                            .replace("\\'", "'").replace('\\"', '"'))
        if want_decoded.strip() != text.strip():
            problems.append(
                f"{fname} 的 `{key}` fallback 與 zh 字典不一致"
                f"（HTML:「{text[:24]}」/ 字典:「{want[:24]}」）"
                f"—— 執行時字典會蓋掉 HTML，只改 HTML 等於沒改"
            )

    print(f"  {dirname}：程式碼用到 {len(used)} 個 key　字典 zh {len(zh)} / en {len(en)}")
    return [f"{dirname}: {x}" for x in problems]


def main() -> int:
    print("翻譯完整性檢查")
    problems = []
    for dirname, dict_files in TARGETS:
        if not (ROOT / dirname).is_dir():
            continue          # ZH: 目錄還沒建 → 不是錯誤（例如尚未開始的版本）
        problems += check_one(dirname, dict_files)

    if problems:
        for p in problems:
            print(f"  [FAIL] {p}")
        print(f"\n[FAIL] {len(problems)} 項")
        return 1
    print("\n[OK] 兩種語言的 key 齊全、無多餘 key、佔位符一致")
    return 0


if __name__ == "__main__":
    sys.exit(main())
