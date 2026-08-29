"""
ZH: 確認送出**真的送得出去**（走真實的 httpx 請求建構路徑）。

ZH: 🔴 為什麼需要這一支：其餘 MYAI 測試都把 `_session_request` 整個換掉，
    於是「httpx 收不收得下我組出來的 body」這件事從來沒有被測到。
    2026-08-29 首次真實 SSO 自動開通就死在這裡：

        RuntimeError: Attempted to send an sync request with an AsyncClient instance.

    當時 51 支測試全綠。錯誤訊息也不提「data 參數的型別」，看起來像 client 用錯了。

ZH: 根因：確認送出需要**重複的 key**（一列一組 `emails[]`），dict 裝不下；
    而 httpx 0.25 拿到 list of tuples 的 `data=` 會走同步串流的路徑。

ZH: 這裡用 `httpx.MockTransport` —— **不連網路，但走完整的請求建構**，
    那正是出事的那一段。
"""
import sys
import os
import asyncio

import httpx
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "job-scheduler"))

from app.services import myai_sync as M  # noqa: E402


TWO_ROWS = [{"emails": "a@example.com", "transferPoints": "1", "remarks": "r"},
            {"emails": "b@example.com", "transferPoints": "2", "remarks": "r"}]
FIELDS = ("emails", "transferPoints", "remarks")


def test_urlencoded_keeps_repeated_keys():
    """ZH: 一列一組 `emails[]` —— 重複的 key 不能被壓成一個。"""
    body = M._urlencoded(TWO_ROWS, FIELDS)
    assert body.count("emails%5B%5D=") == 2
    assert "a%40example.com" in body and "b%40example.com" in body


def test_urlencoded_body_is_sendable_by_an_async_client():
    """
    ZH: 🔴 這一條就是那個 bug 的迴歸測試。

    ZH: 用真的 AsyncClient + MockTransport 送一次 —— 不連網路，
        但請求建構走的是與正式環境完全相同的路徑。
    """
    seen = {}

    def handler(request):
        seen["body"] = request.content.decode()
        seen["ctype"] = request.headers.get("content-type")
        return httpx.Response(200, text="ok")

    async def go():
        async with httpx.AsyncClient(
                transport=httpx.MockTransport(handler),
                base_url="http://vendor.invalid") as c:
            return await c.post(
                "/confirm", content=M._urlencoded(TWO_ROWS, FIELDS),
                headers={"Content-Type": "application/x-www-form-urlencoded"})

    r = asyncio.run(go())
    assert r.status_code == 200
    assert seen["body"].count("emails%5B%5D=") == 2
    assert seen["ctype"] == "application/x-www-form-urlencoded"


def test_the_old_way_really_does_blow_up():
    """
    ZH: 陽性對照 —— 證明上面那條測的是**真的失敗模式**，不是我編的。

    ZH: 如果哪天 httpx 修好了這個行為，這一條會紅。那時候可以把
        `_urlencoded` 的註解更新，但**不要**因此改回 `data=list`：
        自己 urlencode 沒有版本相依，換回去只是把地雷埋回土裡。
    """
    pairs = [("emails[]", "a@example.com"), ("emails[]", "b@example.com")]

    async def go():
        async with httpx.AsyncClient(
                transport=httpx.MockTransport(lambda r: httpx.Response(200)),
                base_url="http://vendor.invalid") as c:
            return await c.post("/confirm", data=pairs)

    with pytest.raises(RuntimeError, match="sync request"):
        asyncio.run(go())


def test_no_caller_passes_a_list_to_httpx_data():
    """
    ZH: 靜態守門 —— 整個 myai_sync 裡不該再出現 `data=form` 這種寫法。

    ZH: 只看有沒有 `data=` 接一個變數名（不是 dict 常值）。
        這是保守的檢查：抓不到全部，但抓得到我當初寫的那一種。
    """
    import re
    src_path = os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "job-scheduler", "app", "services",
        "myai_sync.py")
    src = open(src_path, encoding="utf-8").read()
    src = re.sub(r'"""[\s\S]*?"""', "", src)          # ZH: 去掉 docstring
    src = "\n".join(l for l in src.split("\n") if not l.strip().startswith("#"))
    bad = re.findall(r"\bdata=(?!\{)(\w+)", src)
    # ZH: 登入那支用的是 dict 常值，會被上面的 (?!\{) 排除。
    assert bad == [], f"這些地方把變數丟給 httpx 的 data=：{bad}"
