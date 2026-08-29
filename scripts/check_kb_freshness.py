"""
ZH: 知識庫有沒有過時 —— 比對它提到的介面字串是否還存在於程式碼裡。

ZH: 🔴 為什麼需要這一支：知識庫過時的失敗模式是**小基自信地講錯**。
    2026-08-28 查到的實例：它叫使用者「前往 Compute Tasks 分頁」，
    而那個名稱在現在的介面上**一個字都不存在** —— 知識庫停在兩個月前的 V0 介面，
    中間沒有任何人發現，因為小基答得很流暢、格式很正確、只是內容是錯的。

ZH: 這支只做**一件機械上做得到的事**：知識庫用「」括起來的介面字串，
    到「使用者真的看得到的字」裡找得到嗎。找不到＝那個名稱可能被改掉了。

ZH: ⚠ **它抓不到的（不要以為綠燈就等於知識庫是對的）：**
      · 沒有用「」括起來的敘述（「閒置 30 分鐘會自動關閉」這種）。
      · 數字對不對（配額 10 GB、逾時 120 分鐘…）—— 那些散落在
        yaml / config / 前端寫死值裡，各自的比對規則都不一樣，
        硬做會變成一堆假警報。
      · 功能還在、但行為變了。

ZH: 🔴 **假警報比漏抓更糟**：一支會誤報的檢查會被整支忽略，
    連它真的抓到東西的那一天也一起。所以排除規則寧可保守 ——
    第一版不排除時有 17 個未命中而**全部都是誤報**（省略號、
    刻意提到的舊稱、把幾個標籤串起來的複合詞…）。

用法：
    python scripts/check_kb_freshness.py
"""
import glob
import io
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KB = os.path.join(ROOT, "job-scheduler", "knowledge")


# ══════════════════════════════════════════════════════════════════════════
# ZH: 搜尋範圍 —— **只收「使用者真的看得到的字」**
# ══════════════════════════════════════════════════════════════════════════
# ZH: 🔴 這一條是**陽性對照逼出來的**，不是我一開始就想到的。
#     第一版直接把整個檔案當大海撈。用當初真正發生過的問題重現一次
#     （知識庫寫「運算任務」，而介面上早就沒有這個名稱）—— **它沒抓到**，
#     因為 rag_service.py 的提示詞散文裡有「…提交運算任務…」這幾個字。
#     一個已經消失的介面名，靠註解裡的隻字片語就能「證明它還在」。
#
# ZH: 也就是說：那時候的綠燈完全不代表這支檢查有用。**驗尺比驗結果重要。**
#
# ZH: 所以現在只收四種來源，而且**一律去掉註解與 docstring**：
#       i18n 字典的值 / HTML 可見文字 / JS 字串常值 / 後端字串常值

def _i18n_values():
    """ZH: i18n 字典的**值**（不含 key）。

    @node scripts/check_kb_freshness.py::_i18n_values
    """
    out = []
    for p in ("web-ui-V1/i18n.js", "admin-ui-V1/i18n-admin.js"):
        f = os.path.join(ROOT, p)
        if os.path.exists(f):
            src = io.open(f, encoding="utf-8").read()
            out += re.findall(r":\s*'([^']*)'", src)
    return out


def _html_text():
    """ZH: HTML 去掉標籤、script 與註解之後的可見文字。

    @node scripts/check_kb_freshness.py::_html_text
    """
    out = []
    for g in ("web-ui-V1/*.html", "admin-ui-V1/*.html"):
        for f in glob.glob(os.path.join(ROOT, g)):
            h = io.open(f, encoding="utf-8").read()
            h = re.sub(r"<script.*?</script>", "", h, flags=re.S)
            h = re.sub(r"<!--.*?-->", "", h, flags=re.S)
            plain = re.sub(r"<[^>]+>", "\n", h)
            out += [l.strip() for l in plain.split("\n") if l.strip()]
    return out


def _js_literals():
    """ZH: JS 的字串常值（T() 的 fallback、組出來的 HTML 文字）。**去掉註解。**

    @node scripts/check_kb_freshness.py::_js_literals
    """
    out = []
    for g in ("web-ui-V1/*.js", "admin-ui-V1/*.js"):
        for f in glob.glob(os.path.join(ROOT, g)):
            s = io.open(f, encoding="utf-8").read()
            s = re.sub(r"^\s*//.*$", "", s, flags=re.M)
            s = re.sub(r"/\*.*?\*/", "", s, flags=re.S)
            for pat in (r"'([^']*)'", r'"([^"]*)"', r"`([^`]*)`"):
                out += re.findall(pat, s)
    return out


def _backend_strings():
    """ZH: 後端的字串常值。**去掉 docstring 與註解** —— 那正是第一版漏抓的原因。

    @node scripts/check_kb_freshness.py::_backend_strings
    """
    out = []
    pattern = os.path.join(ROOT, "job-scheduler", "app", "**", "*.py")
    for f in glob.glob(pattern, recursive=True):
        src = io.open(f, encoding="utf-8").read()
        src = re.sub(r'"""[\s\S]*?"""', "", src)
        body = "\n".join(l for l in src.split("\n") if not l.strip().startswith("#"))
        for pat in (r'"([^"]*)"', r"'([^']*)'"):
            out += re.findall(pat, body)
    return out


# ══════════════════════════════════════════════════════════════════════════
# ZH: 排除規則 —— 每一條都對應第一版量到的一種誤報
# ══════════════════════════════════════════════════════════════════════════
SKIP_PATTERNS = [
    (re.compile(r"[…]"), "省略號（不是完整字串）"),
    (re.compile(r"[/／|]"), "複合詞（把幾個標籤串在一起）"),
    (re.compile(r"[()（）]"), "帶括號的說明"),
    (re.compile(r"^[A-Za-z][A-Za-z .]*$"), "純英文（多半是刻意提到的舊稱）"),
    (re.compile(r"\bN\b|\{"), "帶佔位符"),
]

KB_TITLES = None    # ZH: 由 main() 依實際檔名填


def _skip_reason(q):
    """ZH: 該跳過就回原因，否則 None。

    @node scripts/check_kb_freshness.py::_skip_reason
    """
    for pat, why in SKIP_PATTERNS:
        if pat.search(q):
            return why
    # ZH: ⚠ 比對要**去掉空白**：檔名是 20-MYAI與AI額度.md，
    #     內文寫的是「MYAI 與 AI 額度」（有空格）。不去空白就對不上。
    flat = q.replace(" ", "")
    if KB_TITLES and any(flat in t.replace(" ", "") for t in KB_TITLES):
        return "指涉另一份知識庫文件"
    return None


def main():
    """@node scripts/check_kb_freshness.py::main"""
    global KB_TITLES
    kb_files = sorted(glob.glob(os.path.join(KB, "*.md")))
    if not kb_files:
        print("  [WARN] 找不到知識庫檔案，跳過")
        return 0
    KB_TITLES = [os.path.splitext(os.path.basename(f))[0] for f in kb_files]

    haystack = "\n".join(_i18n_values() + _html_text()
                         + _js_literals() + _backend_strings())
    if len(haystack) < 50000:
        # ZH: 🔴 大海撈針的「海」空了的話，**每一根針都會找不到** ——
        #     那會變成一整頁假警報。寧可明講讀不到也不要報一堆錯。
        print(f"  [FAIL] 搜尋範圍只讀到 {len(haystack)} 字，路徑可能不對")
        return 1

    checked = skipped = 0
    problems = []
    for f in kb_files:
        name = os.path.basename(f)
        for i, line in enumerate(io.open(f, encoding="utf-8").read().split("\n"), 1):
            for m in re.finditer(r"「([^」]{2,20})」", line):
                q = m.group(1)
                if _skip_reason(q):
                    skipped += 1
                    continue
                checked += 1
                if q not in haystack:
                    problems.append((name, i, q, line.strip()[:70]))

    print("知識庫新鮮度檢查")
    print(f"  比對了 {checked} 個介面字串（跳過 {skipped} 個不適用的）")
    if not problems:
        print("  [OK] 知識庫提到的介面字串都還在程式碼裡")
        print("  * 這只證明名稱沒過期，不證明內容是對的"
              "（數字與行為描述抓不到，見檔頭）")
        return 0

    print(f"\n  [FAIL] {len(problems)} 個字串在使用者看得到的地方找不到 —— "
          "介面可能改名了，知識庫沒跟上：")
    for name, ln, q, ctx in problems:
        print(f"    {name}:{ln}  {q}")
        print(f"      {ctx}")
    print("\n  改完知識庫記得跑 reindex（POST /api/v1/assistant/reindex）")
    return 1


if __name__ == "__main__":
    sys.exit(main())
