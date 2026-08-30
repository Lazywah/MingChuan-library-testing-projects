# -*- coding: utf-8 -*-
"""
ZH: 檢查後端掛的 API 前綴，nginx 有沒有跟著開路。

ZH: 為什麼要有這支 —— **同一類缺陷已經發生兩次**：

      2026-07  `/api/v1/models`  → 502
      2026-08  `/api/v1/reports` → 405（問題回報送不出去）

    兩次都是 `main.py` 加了新的 `include_router`，但沒有回 `nginx.conf`
    補一條對應的 `location`。請求於是落到檔案最底下的 catch-all，
    被送去 **Open WebUI**（完全不同的產品）。

ZH: 🔴 這個缺陷最惡毒的地方是**症狀不像路由問題**：

      - 回的不是 404，而是 405 或 502 —— 看起來像「後端壞了」
      - `Server:` 標頭仍然是 nginx，看起來像平台自己回的
      - 後端測試全綠，因為後端根本沒被呼叫到

    分辨方法是直連 `:8002` 再打一次：直連回 401（`server: uvicorn`）
    而經 nginx 回 405，就是路由漏掛。

ZH: 判準只有一條，刻意保守：**main.py 掛的每個前綴，port 80 都要有 location**，
    白名單除外。寧可漏抓也不要誤報 —— 會亂叫的檢查最後會被整支忽略。

ZH: exit code：有問題回 1。這檢查的是「有沒有這條 location」這種零判斷空間的事實。

@node scripts/check_nginx_routes.py
"""
import io
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
MAIN = ROOT / "job-scheduler" / "app" / "main.py"
CONF = ROOT / "infrastructure" / "nginx.conf"

# ZH: 刻意**不**開在使用者埠（:80）的前綴。每一條都要寫清楚理由 ——
#     沒有理由的白名單，下次就會被人拿來塞掉一個真的漏洞。
ALLOW_NOT_ON_80 = {
    "admin":  "管理 API 不對使用者埠開放；只掛在 :8888",
    "worker": "GPU worker 直連 :8002（純拉取式），不經 nginx",
}


def backend_prefixes(src: str) -> set:
    """ZH: 從 main.py 取出所有 include_router 的前綴（只留 /api/v1/ 之後的第一段）。

    @node scripts/check_nginx_routes.py::backend_prefixes
    """
    found = re.findall(r'include_router\([^)]*prefix\s*=\s*"(/api/v1/[^"]+)"', src)
    return {p.split("/")[3] for p in found if len(p.split("/")) > 3}


def nginx_blocks(conf: str) -> dict:
    """ZH: 把 nginx.conf 依 server 區塊切開，回 {埠號: 該區塊原始碼}。

    ZH: 結構若被改動而切不出來，呼叫端會**大聲失敗**而不是安靜通過 ——
        解析不到就當作檢查失效，不能當作沒問題。

    ZH: 🔴 v2（2026-08-30）改成「剝註解 → 大括號配對找 server 區塊 →
        區塊掛在它**所有** listen 埠下」。第一版用 `listen \\d+` 的字面位置切，
        兩個地方會壞：
          1. **註解裡的 listen 也被當邊界** —— 443/TLS 預埋註解一寫進去，
             `# listen 443 ssl;` 就把 :80 區塊切到只剩幾行，守門直接失明。
          2. **同一個 server 掛兩個 listen**（:80 + :443 共用路由，刻意設計，
             理由見 nginx.conf）—— 天真切法會把全部 location 算給後面那個埠。
        與 check_dockerfile_pins 剝註解免得報到自己，是同一個教訓。

    @node scripts/check_nginx_routes.py::nginx_blocks
    """
    # ZH: 剝註解（nginx 註解 = `#` 到行尾）。結構判定一律用剝過的文字。
    stripped = "\n".join(line.split("#", 1)[0] for line in conf.splitlines())

    out = {}
    for m in re.finditer(r"\bserver\s*\{", stripped):
        # ZH: 從 `{` 開始配對大括號，找到這個 server 區塊的結尾。
        depth = 0
        start = stripped.index("{", m.start())
        end = None
        for i in range(start, len(stripped)):
            if stripped[i] == "{":
                depth += 1
            elif stripped[i] == "}":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        if end is None:
            continue        # ZH: 括號不平衡 —— 留給 caller 的「找不到 :80」大聲失敗
        block = stripped[m.start():end]
        for port in re.findall(r"\blisten\s+(\d+)", block):
            out[port] = block
    return out


def nginx_prefixes(block: str) -> set:
    """ZH: 取出一個 server 區塊裡所有 `location ... ^/api/v1/<第一段>`。

    @node scripts/check_nginx_routes.py::nginx_prefixes
    """
    return set(re.findall(r"location[^\n]*\^/api/v1/([\w-]+)", block))


def main() -> int:
    """@node scripts/check_nginx_routes.py::main"""
    for p in (MAIN, CONF):
        if not p.exists():
            print("[FAIL] 找不到 %s" % p)
            return 1

    prefixes = backend_prefixes(io.open(MAIN, encoding="utf-8").read())
    conf = io.open(CONF, encoding="utf-8").read()
    blocks = nginx_blocks(conf)

    # ── 解析失效時要大聲失敗，不能安靜通過 ────────────────────────────────
    # ZH: 一支「安靜通過」的檢查比沒有這支更糟：它讓人以為看過了。
    #     check_select_bool 就踩過——正則的字元集漏了一個 `-`，
    #     於是它對一個**確實含有該缺陷的檔案**回報通過。
    if not prefixes:
        print("[FAIL] 從 main.py 解析不到任何 include_router 前綴 —— "
              "檢查本身失效了（不是「沒有問題」）。請看 backend_prefixes 的正則。")
        return 1
    if "80" not in blocks:
        print("[FAIL] 從 nginx.conf 解析不到 `listen 80` 的 server 區塊 —— "
              "檢查本身失效了。請看 nginx_blocks。")
        return 1

    on80 = nginx_prefixes(blocks["80"])
    if not on80:
        print("[FAIL] :80 區塊裡找不到任何 /api/v1 location —— 檢查本身失效了。")
        return 1

    missing = sorted(p for p in prefixes if p not in on80 and p not in ALLOW_NOT_ON_80)

    # ZH: 白名單長了灰塵也要講：某個前綴已經從 main.py 拿掉，白名單卻還留著。
    stale = sorted(k for k in ALLOW_NOT_ON_80 if k not in prefixes)

    if missing:
        print("[FAIL] %d 個後端前綴在 nginx :80 沒有對應的 location：" % len(missing))
        for p in missing:
            print("  - /api/v1/%s" % p)
        print()
        print("  ZH: 請求會落到 nginx.conf 最底下的 catch-all → Open WebUI，")
        print("      症狀是 405 或 502（不是 404），而且 Server 標頭仍是 nginx，")
        print("      看起來像後端壞了。同一類已經發生過兩次。")
        print()
        print("  修法：在 infrastructure/nginx.conf 的 :80 區塊，照既有寫法補一條")
        print("        location ~ ^/api/v1/<前綴>(/.*)?$ { proxy_pass http://job_scheduler$request_uri; … }")
        print("        改完要 `docker exec ai-platform-nginx nginx -s reload`")
        print("        —— bind mount 的設定，光 `up -d` 不會重載。")
        print()
        print("  真的不該對使用者埠開放的話，加進本檔的 ALLOW_NOT_ON_80 並寫明理由。")
        return 1

    if stale:
        print("[OK] %d 個後端前綴都有 nginx :80 的 location（白名單 %d 個）"
              % (len(prefixes) - len(ALLOW_NOT_ON_80), len(ALLOW_NOT_ON_80)))
        print("     ⚠️ 白名單有 %d 筆已經不在 main.py 裡，可以清掉：%s"
              % (len(stale), "、".join(stale)))
        return 0

    print("[OK] %d 個後端前綴都有 nginx :80 的 location；%d 個在白名單內（%s）"
          % (len(prefixes) - len(ALLOW_NOT_ON_80), len(ALLOW_NOT_ON_80),
             "、".join("%s：%s" % (k, v) for k, v in sorted(ALLOW_NOT_ON_80.items()))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
