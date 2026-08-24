# -*- coding: utf-8 -*-
"""
ZH: 各 UI 目錄的**共用檔**必須逐位元組相同。

ZH: 為什麼需要這支 —— nginx 的每個 UI 版本是各自的 alias 根目錄，
    跨不過去，所以 `tokens.css` / `i18n.js` / `prefs.js` 這些共用檔
    **只能每個目錄各放一份**。而重複的檔案沒有機械檢查就一定會漂開：
    有人在其中一份修了 bug，另外三份留著原樣，
    症狀是「同一個功能在管理端好好的，在使用者端壞掉」——
    而兩邊的程式碼看起來都對，因為你不會同時打開四個檔案比對。

ZH: `tz.js` 已經有 `check_timezone.py` 在守（它另外還跑行為測試），
    這支負責其餘幾支，判準單純：**與正本的 sha256 相同**。

ZH: 正本一律是 `web-ui-V1/`。改共用檔時改那一份，然後跑 `--fix` 同步出去。

用法：
    python scripts/check_shared_ui_files.py          # 檢查，不同就 exit 1
    python scripts/check_shared_ui_files.py --fix    # 以正本覆蓋其餘副本

@node scripts/check_shared_ui_files.py
"""
import hashlib
import pathlib
import shutil
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
CANON_DIR = ROOT / "web-ui-V1"

# ZH: 要保持一致的共用檔。tz.js 交給 check_timezone.py，這裡不重複管。
# ZH: `styles.css` 也在裡面 —— 管理端**沿用同一份基礎樣式**，
#     管理端專屬的規則放在各自的 `admin.css`，不改這一份。
#     這樣「按鈕長什麼樣」只有一個定義，兩邊不會各自演化。
SHARED = ["tokens.css", "styles.css", "i18n.js", "prefs.js"]


def _sha(p: pathlib.Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()[:12]


def _ui_dirs():
    # ZH: 🔴 只約束 **v2 世代**（目錄名以 `-v2` 結尾）。
    #     第一版寫成「所有 UI 目錄」，結果 v1／v1.5／舊 admin 全部被判不合格 ——
    #     它們各自有一份**內容完全不同**的 `styles.css`，那是它們自己的設計，
    #     不是漂開。判準錯了會製造四個假警報，而假警報會讓人整支忽略這個檢查。
    #
    # ZH: 仍然是自動探索，**不寫死清單** —— 寫死的話新增的 UI 目錄會自動免疫，
    #     而且是安靜地免疫（檢查照樣印 OK）。這個坑 bump_assets.py 踩過。
    # ZH: 🔴 2026-08-22 修：這裡原本寫的是 `-v2`。目錄在 `1cf0b3b` 改名成
    #     V0 / V0.5 / **V1** 之後，這個條件**一個都沒匹配到** ——
    #     於是這支檢查一直在檢查 0 份檔案並印「OK」。
    #     上面那段註解自己就警告過「安靜地免疫（檢查照樣印 OK）」——
    #     實際發生的不是寫死清單，而是**探索規則跟不上改名**。
    #     防御在下方 main()：探到 0 個同儀就直接失敗。
    return sorted(
        d for d in ROOT.iterdir()
        if d.is_dir() and d.name.endswith("-V1") and d != CANON_DIR
    )


def main() -> int:
    fix = "--fix" in sys.argv
    problems, fixed, checked = [], [], 0

    # ZH: 🔴 探不到任何同儀目錄 = 探索規則已經跟不上目錄命名，
    #     **不是「沒有問題」**。這兩件事在畫面上長得一模一樣（都是一行 OK），
    #     而實際上一個是保護、一個是裸奔。實際發生過一次（見上方 _ui_dirs()）。
    peer_dirs = _ui_dirs()
    if not peer_dirs:
        print("[FAIL] 找不到任何同儀 UI 目錄 —— 探索規則失效了，不是「沒有問題」。")
        print("       目錄可能又改名了。請看本檔的 _ui_dirs()。")
        print("       現有目錄：%s"
              % "、".join(sorted(d.name for d in ROOT.iterdir() if d.is_dir())))
        return 1

    for name in SHARED:
        canon = CANON_DIR / name
        if not canon.exists():
            problems.append(f"正本不存在：web-ui-V1/{name}")
            continue
        want = _sha(canon)

        for d in _ui_dirs():
            copy = d / name
            # ZH: 沒有那個檔 = 那個目錄沒用到這支共用檔，不算問題。
            #     （舊版 admin-ui 就沒有 tokens.css / prefs.js。）
            if not copy.exists():
                continue
            checked += 1
            got = _sha(copy)
            if got == want:
                continue
            if fix:
                shutil.copyfile(canon, copy)
                fixed.append(f"{d.name}/{name}")
            else:
                problems.append(
                    f"{d.name}/{name} 與正本不同（{got} ≠ {want}）")

    if fixed:
        print(f"[FIX] 已用正本覆蓋 {len(fixed)} 份：")
        for f in fixed:
            print(f"  - {f}")
        return 0

    if problems:
        print(f"[FAIL] {len(problems)} 份共用檔與正本不一致：")
        for p in problems:
            print(f"  - {p}")
        print()
        print("  修法：共用檔一律改 web-ui-V1/ 那一份（正本），再跑")
        print("        python scripts/check_shared_ui_files.py --fix")
        return 1

    print(f"[OK] {checked} 份共用檔與 web-ui-V1 的正本逐位元組相同")
    return 0


if __name__ == "__main__":
    sys.exit(main())
