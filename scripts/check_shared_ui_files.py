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

ZH: 正本一律是 `web-ui-v2/`。改共用檔時改那一份，然後跑 `--fix` 同步出去。

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
CANON_DIR = ROOT / "web-ui-v2"

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
    return sorted(
        d for d in ROOT.iterdir()
        if d.is_dir() and d.name.endswith("-v2") and d != CANON_DIR
    )


def main() -> int:
    fix = "--fix" in sys.argv
    problems, fixed, checked = [], [], 0

    for name in SHARED:
        canon = CANON_DIR / name
        if not canon.exists():
            problems.append(f"正本不存在：web-ui-v2/{name}")
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
        print("  修法：共用檔一律改 web-ui-v2/ 那一份（正本），再跑")
        print("        python scripts/check_shared_ui_files.py --fix")
        return 1

    print(f"[OK] {checked} 份共用檔與 web-ui-v2 的正本逐位元組相同")
    return 0


if __name__ == "__main__":
    sys.exit(main())
