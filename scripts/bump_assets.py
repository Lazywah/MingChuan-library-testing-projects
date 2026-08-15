#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
==============================================================================
前端靜態資產版號自動化 / Front-end asset cache-buster
==============================================================================
ZH: 把 index.html 內 `?v=` 的值改成「該資產檔的內容 hash」，取代手動 bump 日期編號。
    - 內容沒變 -> hash 不變 -> HTML 不動（冪等，不產生多餘 diff）
    - 內容一變 -> hash 自動改變 -> 瀏覽器抓到新版，不會拿到舊快取
    這樣改 app.js / styles.css / admin.js 後就「不必記得手動改 ?v=」。

用法 / Usage:
  python scripts/bump_assets.py            ← 依內容 hash 重寫所有 ?v=（會改 HTML）
  python scripts/bump_assets.py --check    ← 只檢查有無過期，不寫入；有過期則 exit 1（給 deploy-check / CI 用）

需求 / Requirements: Python 3.6+，無額外套件。
==============================================================================
"""
import hashlib
import re
import sys
from pathlib import Path

# ZH: 主控台若為 cp950/Big5，遇到不可編碼字元改為替代字而非崩潰（純保險，輸出本身只用 ASCII 標記）
try:
    sys.stdout.reconfigure(errors="replace")
    sys.stderr.reconfigure(errors="replace")
except (AttributeError, ValueError):
    pass

ROOT_DIR = Path(__file__).parent.parent.resolve()   # CodeSpace/
# 要掃描的前端目錄（各自獨立，web 與 admin 互不影響）
ASSET_DIRS = [ROOT_DIR / "web-ui", ROOT_DIR / "admin-ui"]

HASH_LEN = 8   # 取 sha256 前 8 碼十六進位

# 比對 <script src="app.js?v=..."> / <link href="styles.css?v=..."> 這類本地資產引用。
# group: 1=attr(src|href) 2=資產路徑(不含?) 3=舊v值 4=其餘 query 尾巴(&...)
_REF = re.compile(
    r'((?:src|href)=")([^"?]+)\?v=([^"&]*)((?:&[^"]*)?)"'
)


def content_hash(path: Path) -> str:
    """@node scripts/bump_assets.py::content_hash"""
    return hashlib.sha256(path.read_bytes()).hexdigest()[:HASH_LEN]


def process_html(html_path: Path, write: bool):
    """
    回傳 (changed_list, missing_list)：
      changed_list = [(asset, old_v, new_v), ...] 需要更新的項目
      missing_list = [asset, ...] 引用了但檔案不存在的項目

    @node scripts/bump_assets.py::process_html
    """
    text = html_path.read_bytes().decode("utf-8")
    changed, missing = [], []

    def repl(m):
        """@node scripts/bump_assets.py::process_html.<nested@57>.repl"""
        attr, asset, old_v, tail = m.group(1), m.group(2), m.group(3), m.group(4)
        # 外部資源（http/https/協定相對）不處理
        if asset.startswith(("http://", "https://", "//")):
            return m.group(0)
        asset_file = (html_path.parent / asset).resolve()
        if not asset_file.is_file():
            missing.append(asset)
            return m.group(0)
        new_v = content_hash(asset_file)
        if new_v != old_v:
            changed.append((asset, old_v, new_v))
        return f'{attr}{asset}?v={new_v}{tail}"'

    new_text = _REF.sub(repl, text)

    if write and changed:
        # 用 bytes 寫回，保留原換行 (CRLF/LF)，只更動 ?v= 片段
        html_path.write_bytes(new_text.encode("utf-8"))

    return changed, missing


def main():
    """@node scripts/bump_assets.py::main"""
    check_only = "--check" in sys.argv

    html_files = []
    for d in ASSET_DIRS:
        if d.is_dir():
            html_files.extend(sorted(d.glob("*.html")))

    if not html_files:
        print("找不到任何 HTML（web-ui/ admin-ui/）/ no HTML found")
        return 0

    total_changed = 0
    total_missing = 0
    for html in html_files:
        rel = html.relative_to(ROOT_DIR)
        changed, missing = process_html(html, write=not check_only)
        for asset in missing:
            total_missing += 1
            print(f"  [!] {rel}: 引用的資產不存在 / missing asset: {asset}")
        if changed:
            total_changed += len(changed)
            verb = "過期(需更新)" if check_only else "已更新"
            print(f"  [*] {rel} - {verb} {len(changed)} 項:")
            for asset, old_v, new_v in changed:
                print(f"        {asset}: {old_v}  ->  {new_v}")
        else:
            print(f"  [OK] {rel} - 版號皆為最新 / up to date")

    print()
    if check_only:
        if total_changed:
            print(f"[X] 有 {total_changed} 個 ?v= 過期，請跑 `python scripts/bump_assets.py` 更新後再部署")
            return 1
        print("[OK] 所有 ?v= 都是最新內容 hash / all up to date")
        return 0

    if total_changed:
        print(f"[DONE] 已依內容 hash 更新 {total_changed} 個 ?v=（改了前端資產後記得重跑本腳本）")
    else:
        print("[DONE] 無需更新，所有 ?v= 已是最新")
    if total_missing:
        print(f"[!] 有 {total_missing} 個引用指向不存在的檔案，請檢查路徑")
    return 0


if __name__ == "__main__":
    sys.exit(main())
