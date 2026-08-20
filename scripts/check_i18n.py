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
UI = ROOT / "web-ui-v2"
DICT = UI / "i18n.js"

# ZH: 不是 key 的東西：
#   key   — 函式簽章裡的參數名（`t(key, fallback)`）
#   zh/en — 語言切換鈕的 `[['zh', '中文'], ['en', 'English']]`，剛好符合
#           「字串後面接含中文的字串」這個形狀。**這是形狀判準的已知代價**，
#           寫死排除比把判準改窄好（改窄會重新漏掉以參數傳 key 的呼叫）。
IGNORE_USED = {"key", "zh", "en"}
DYNAMIC_PREFIXES = ("role_",)


def used_keys() -> dict:
    """ZH: 掃 HTML 的 data-i18n* 與 JS 的 T('…') / Prefs.t('…') / L('…')。"""
    found = {}
    for f in sorted(UI.glob("*.html")):
        s = f.read_text(encoding="utf-8")
        for m in re.finditer(r'data-i18n(?:-placeholder|-aria)?="([^"]+)"', s):
            found.setdefault(m.group(1), set()).add(f.name)
    for f in sorted(UI.glob("*.js")):
        if f.name == "i18n.js":
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
    return {k: v for k, v in found.items() if k not in IGNORE_USED}


def dict_keys() -> dict:
    """ZH: 從 i18n.js 取出 zh / en 兩份的 key → 值。

    ZH: 用括號配對切出兩個語言區塊，不用「找下一個 `},`」——
        字典值裡本來就有 `}`（佔位符），那種切法會在第一個佔位符就切斷。
    """
    s = DICT.read_text(encoding="utf-8")
    out = {}
    for lang in ("zh", "en"):
        m = re.search(r"\n\s+%s:\s*\{" % lang, s)
        if not m:
            out[lang] = {}
            continue
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
        out[lang] = dict(re.findall(r"\n\s+([a-z0-9_]+):\s*'((?:[^'\\]|\\.)*)'", body))
    return out


PLACEHOLDER = re.compile(r"\{[a-z]\}")


def main() -> int:
    if not DICT.is_file():
        print(f"[FAIL] 找不到 {DICT.relative_to(ROOT)}")
        return 1

    used = used_keys()
    d = dict_keys()
    zh, en = d.get("zh", {}), d.get("en", {})
    problems = []

    for k, where in sorted(used.items()):
        if k.startswith(DYNAMIC_PREFIXES):
            continue
        for lang, table in (("zh", zh), ("en", en)):
            if k not in table:
                problems.append(f"{lang} 缺 key `{k}`（用在 {', '.join(sorted(where))}）")

    dynamic_ok = {k for k in list(zh) + list(en) if k.startswith(DYNAMIC_PREFIXES)}
    unused = (set(zh) | set(en)) - set(used) - dynamic_ok
    for k in sorted(unused):
        problems.append(f"字典有 `{k}` 但沒有人用（改文案時忘了刪？）")

    for k in sorted(set(zh) & set(en)):
        a = sorted(PLACEHOLDER.findall(zh[k]))
        b = sorted(PLACEHOLDER.findall(en[k]))
        if a != b:
            problems.append(f"`{k}` 的佔位符不一致：zh {a or '無'} vs en {b or '無'}")

    print("翻譯完整性檢查（web-ui-v2）")
    print(f"  程式碼用到 {len(used)} 個 key　字典 zh {len(zh)} / en {len(en)}")
    if problems:
        for p in problems:
            print(f"  [FAIL] {p}")
        print(f"\n[FAIL] {len(problems)} 項")
        return 1
    print("\n[OK] 兩種語言的 key 齊全、無多餘 key、佔位符一致")
    return 0


if __name__ == "__main__":
    sys.exit(main())
