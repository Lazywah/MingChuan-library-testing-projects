# -*- coding: utf-8 -*-
"""
ZH: MYAI 同步的傳輸層重試與錯誤訊息（2026-09-26 那封「登入請求失敗：」空信之後）。

ZH: 兩個缺口，各守一條：
      1. **冷連線第一下會斷**（實測 EndOfStream、~10 秒），第二下就好 ——
         沒有重試的話一小時一次的同步碰到就整輪失敗、寄信。只重試一次：
         真的斷網時多試只是把告警延後，救不回來。
      2. httpx 傳輸層例外的 str() 常常是**空字串** —— 告警信裡就是一句沒內容的話。
         訊息一律帶型別、盡量帶 cause 與網址。

ZH: 廠商 HTTP 一律用假的 client 頂掉（與 test_myai_grant 同一個精神：測試絕不打廠商）。

@node tests/test_myai_session_retry.py
"""
import httpx
import pytest

from app.services import myai_sync as M


class FakeResponse:
    def __init__(self, text="ok", status=200):
        self.text = text
        self.status_code = status
        self.headers = {}


class FakeClient:
    """ZH: 依 `script` 逐次回應：元素是例外就 raise，不然當成回應。記下每一次呼叫。"""
    script = []
    calls = []

    def __init__(self, **kw):
        self.cookies = httpx.Cookies()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def _next(self, what):
        FakeClient.calls.append(what)
        item = FakeClient.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    async def get(self, path, **kw):
        return await self._next("GET " + path)

    async def post(self, path, **kw):
        return await self._next("POST " + path)


@pytest.fixture
def vendor(monkeypatch):
    monkeypatch.setattr(M.settings, "MYAI_ADMIN_EMAIL", "admin@example.com")
    monkeypatch.setattr(M.settings, "MYAI_ADMIN_PASSWORD", "secret")
    monkeypatch.setattr(M, "_RETRY_PAUSE_SECONDS", 0)      # ZH: 測試不真的等
    monkeypatch.setattr(M, "_save_cookies", lambda c: None)
    monkeypatch.setattr(M.httpx, "AsyncClient", FakeClient)
    FakeClient.calls = []

    def _run(script, cookies=None):
        FakeClient.script = list(script)
        monkeypatch.setattr(M, "_MYAI_COOKIES", cookies)
        return M._session_request(lambda c: c.get("/export"), lambda r: r.status_code == 200)
    return _run


def _conn_err():
    return httpx.ConnectError("")           # ZH: 就是實測看到的那個：str() 是空的


# ── 1. 重試 ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_first_connection_blip_is_retried_once(vendor):
    """ZH: 🔴 登入的第一下斷掉 → 等一下再試 → 成功。整輪同步不該因此失敗。"""
    resp = await vendor([_conn_err(),                       # 第一次登入：GET 登入頁就斷
                         FakeResponse(), FakeResponse(),    # 重試：GET 登入頁、POST 登入
                         FakeResponse("data")])             # 抓資料
    assert resp.text == "data"
    assert FakeClient.calls.count("GET /mcu/ai/user/login") == 2, FakeClient.calls


@pytest.mark.asyncio
async def test_cached_session_blip_falls_through_to_login(vendor):
    """ZH: 有快取 cookie 時第一下也可能斷：重試一次還是斷就改走登入，不是直接整輪失敗。"""
    resp = await vendor([_conn_err(), _conn_err(),          # 快取抓取：兩次都斷
                         FakeResponse(), FakeResponse(),    # 登入
                         FakeResponse("data")],
                        cookies=httpx.Cookies({"s": "1"}))
    assert resp.text == "data"


@pytest.mark.asyncio
async def test_persistent_failure_still_raises(vendor):
    """ZH: 只重試一次 —— 一直斷就要報錯，不能永遠等下去。"""
    with pytest.raises(M.MyaiSyncError):
        await vendor([_conn_err(), _conn_err()])
    assert len(FakeClient.calls) == 2, "登入只該試兩次（原本一次＋重試一次）"


@pytest.mark.asyncio
async def test_http_status_errors_are_not_retried(vendor):
    """ZH: 4xx/5xx 是廠商真的這樣回，重送同一個請求不會變 —— 不重試。"""
    req = httpx.Request("POST", "https://vendor.example/login_info")
    err = httpx.HTTPStatusError("boom", request=req, response=httpx.Response(500, request=req))
    with pytest.raises(M.MyaiSyncError):
        await vendor([err])
    assert len(FakeClient.calls) == 1


# ── 2. 訊息不留白 ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_error_message_is_never_blank(vendor):
    """ZH: 🔴 2026-09-26 的信：「登入請求失敗：」後面空的。訊息至少要有例外型別。"""
    with pytest.raises(M.MyaiSyncError) as ei:
        await vendor([_conn_err(), _conn_err()])
    msg = str(ei.value)
    assert not msg.rstrip().endswith("："), msg
    assert "ConnectError" in msg, msg


def test_describe_adds_type_cause_and_url():
    e = httpx.ConnectError("", request=httpx.Request("POST", "https://vendor.example/login_info"))
    d = M._describe(e)
    assert d.startswith("ConnectError"), d
    assert "vendor.example/login_info" in d, d
    # ZH: 連 request 都沒有時也不能是空的
    assert M._describe(httpx.ReadError("")) == "ReadError（無詳細訊息）"
    # ZH: 有內容的照原樣帶著
    assert "timed out" in M._describe(httpx.ReadTimeout("timed out"))
