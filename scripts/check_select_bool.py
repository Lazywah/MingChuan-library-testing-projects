# -*- coding: utf-8 -*-
"""
ZH: 檢查「下拉選單的值被當成布林用」。

ZH: 為什麼要有這支 —— `<select>` 的 `.value` **永遠是字串**，而 JavaScript 裡
    字串 `'0'` 是 **truthy**。所以一個用 `'1'`/`'0'` 表示是非的下拉，
    只要有人拿 `!!` 或裸真值去讀它，「否」就會被當成「是」。

ZH: 這不是理論。實測過一次（管理端「模型」的「公開」欄）：

      is_public: !!m.is_public          // m.is_public 是下拉回來的 '0'

    結果是 **光按下編輯再按儲存，所有非公開的模型都被改成公開**，
    而畫面還顯示「存好了：改了 2 列」。公開模型是所有使用者都看得到的。

ZH: 為什麼測試抓不到 —— 後端的 365 支測試全綠，因為錯在前端的型別轉換；
    後端收到的是一個合法的 `true`，它沒有辦法知道那個 true 是怎麼來的。
    這與記憶裡「呼叫端打錯名字」同族：靜態沒人擋、測試不覆蓋、
    使用者也不會回報（他不知道那個模型本來不該公開）。

ZH: 判準刻意保守，只抓三種**幾乎不可能有正當理由**的寫法。寧可漏抓，
    也不要製造假警報 —— 一支會亂叫的檢查，最後會被整支忽略。

ZH: exit code：有問題回 1。它檢查的是零判斷空間的事實。

@node scripts/check_select_bool.py
"""
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
UI_DIRS = ["admin-ui-v2", "web-ui-v2"]

# ZH: 行內若有 `check_select_bool: ok` 就跳過該行。留給**真的**有理由的例外，
#     而且逼寫的人把理由寫在旁邊。
ALLOW = "check_select_bool: ok"


def _strip_comments(src: str) -> str:
    """ZH: 去掉註解，免得註解裡示範的壞寫法被當成真的違規。

    ZH: ⚠ **行數不能變**。整塊拿掉的話行號會往前縮，回報的位置就對不上原始檔 ——
        有人照著行號去看會找到不相干的東西。所以區塊註解要換成等量的換行。
        （這也是靠陽性對照才發現的：它回報 779，實際那行在 796。）

    @node scripts/check_select_bool.py::_strip_comments
    """
    src = re.sub(r"/\*.*?\*/",
                 lambda m: "\n" * m.group(0).count("\n"), src, flags=re.S)
    return re.sub(r"(?<!:)//[^\n]*", "", src)


def _select_fields(src: str) -> set:
    """ZH: 找出「由下拉寫入」的欄位名。

    ZH: 兩種來源，對應這個專案實際的兩種寫法：
          cellSelect('is_public', ...)          → 表格儲存格的下拉
          '<select ... data-f="is_public"'      → 直接寫出來的下拉
        兩者最後都會被 readRow 寫成 `物件[名字] = el.value`（字串）。

    @node scripts/check_select_bool.py::_select_fields
    """
    names = set(re.findall(r"cellSelect\(\s*'([A-Za-z_][\w]*)'", src))
    # ZH: `<select` 之後、下一個 `>` 之前出現的 data-f。
    #
    # ZH: ⚠ **只認寫死的名字**。`data-f="' + esc(f) + '"` 這種動態拼接不能抓 ——
    #     抓到的會是變數名 `f`，於是 readRow 裡那句
    #     `target[el.dataset.f] = ... el.checked : el.value` 會被誤報。
    #     （這支檢查第一次跑就是被自己這個錯誤絆倒的。）
    #     動態的那種由呼叫端的 `cellSelect('真名', ...)` 涵蓋，不會漏。
    for seg in re.findall(r"<select\b[^>]*", src):
        names |= set(re.findall(r"data-f=\"([\w]+)\"", seg))
    return names


def _select_ids(src: str) -> set:
    """ZH: 找出以 id 建立的下拉（`<select ... id="n-on"`）。

    @node scripts/check_select_bool.py::_select_ids
    """
    ids = set()
    for seg in re.findall(r"<select\b[^>]*", src):
        ids |= set(re.findall(r"id=\"([\w-]+)\"", seg))
    return ids


def _lines(src: str):
    """@node scripts/check_select_bool.py::_lines"""
    return src.split("\n")


def main() -> int:
    """@node scripts/check_select_bool.py::main"""
    problems = []
    checked = 0

    for d in UI_DIRS:
        for js in sorted((ROOT / d).glob("*.js")):
            raw = js.read_text(encoding="utf-8", errors="replace")
            src = _strip_comments(raw)
            fields = _select_fields(src)
            ids = _select_ids(src)
            checked += 1
            rel = f"{d}/{js.name}"

            for n, line in enumerate(_lines(src), 1):
                if ALLOW in raw.split("\n")[n - 1]:
                    continue

                # ── 規則 1：!! 不得作用在 .value 上 ──────────────────────
                # ZH: `.value` 永遠是字串。`!!` 之後只有空字串會是 false，
                #     `'0'`、`'false'`、`'no'` 全都變成 true。
                # ZH: ⚠ 字元集裡的 `-` 不能少 —— id 常帶連字號（`n-on`、`nw-pin`）。
                #     少了它，`!!$('n-on').value` 就匹配不到，而檢查會**安靜地通過**。
                #     這條規則第一次寫就漏了它，是靠陽性對照才發現的。
                if re.search(r"!!\s*[\w$().\[\]'\"-]*\.value\b", line):
                    problems.append(
                        (rel, n, "!! 作用在 .value 上",
                         "`.value` 永遠是字串，`'0'` 是 truthy。"
                         "改成明確比對（=== '1'）或先正規化。"))

                # ── 規則 2：!! 不得作用在下拉寫入的欄位名上 ──────────────
                for f in fields:
                    if re.search(r"!!\s*[\w$.\[\]]*\b" + re.escape(f) + r"\b", line):
                        problems.append(
                            (rel, n, f"!! 作用在下拉欄位 `{f}` 上",
                             f"`{f}` 由 <select> 寫入，值是字串。"
                             "改成明確比對或先正規化（見 platform.js 的 isPub）。"))

                # ── 規則 3：<select> 不得用 .checked 讀 ─────────────────
                # ZH: 勾選框改成下拉之後最容易留下的殘骸。`.checked` 在
                #     <select> 上是 undefined —— 永遠 falsy，而且不報錯。
                for i in ids:
                    if re.search(r"\$\(\s*'" + re.escape(i) + r"'\s*\)\s*\.checked\b", line):
                        problems.append(
                            (rel, n, f"用 .checked 讀下拉 `#{i}`",
                             "`<select>` 沒有 .checked，會拿到 undefined（永遠 falsy）。"
                             "改讀 .value 並比對。"))
                for f in fields:
                    if re.search(r"\bdataset\." + re.escape(f) + r"\b.*\.checked", line):
                        problems.append(
                            (rel, n, f"用 .checked 讀下拉欄位 `{f}`",
                             "`<select>` 沒有 .checked。改讀 .value 並比對。"))

    problems = sorted(set(problems))
    if problems:
        print(f"[FAIL] {len(problems)} 處把下拉的值當成布林用：")
        for rel, n, what, how in problems:
            print(f"  - {rel}:{n}  {what}")
            print(f"      {how}")
        print()
        print("  ZH: <select> 的 .value 永遠是字串，而 '0' 在 JS 裡是 truthy。")
        print("      真的有理由的話，在該行加註 `" + ALLOW + "` 並寫明原因。")
        return 1

    print(f"[OK] {checked} 支 UI JS 沒有把下拉的值當成布林用")
    return 0


if __name__ == "__main__":
    sys.exit(main())
