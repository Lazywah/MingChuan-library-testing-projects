"""
ZH: API 回應一律 `Cache-Control: no-store`（v3.8）。

ZH: 🔴 為什麼要守：稽核（2026-08-27）實測 API 回應**一個快取標頭都沒有**，
    而且抓到一次 `/api/v1/reports/mine` 回傳**一頁 HTML** —— 那是瀏覽器
    從快取拿的舊東西，加 `cache: 'no-store'` 再打一次就正常。
    症狀會騙人：畫面顯示「讀不到」，而後端好好的、直連 curl 也正常。

ZH: 這個檔案裡的每一條都刻意用**真實的 app**（TestClient），不 mock middleware ——
    middleware 有沒有掛上去正是要測的事。
"""
import pytest


def test_api_responses_are_not_cacheable(client):
    """ZH: 這些端點回的都是跟人有關的即時資料，一個都不該被快取。"""
    for path in ("/api/v1/system/public-settings",
                 "/api/v1/auth/me",
                 "/api/v1/sso/providers"):
        r = client.get(path)
        assert r.headers.get("cache-control") == "no-store", \
            f"{path} 缺少 no-store（實際: {r.headers.get('cache-control')!r}）"


def test_even_error_responses_get_no_store(client):
    """
    ZH: **未驗證的回應也要加**。不加的話，401/403 這種「你還沒登入」的
        回應會被快取起來 —— 使用者登入之後照樣看到「無法驗證憑證」，
        而且重新整理沒有用。
    """
    r = client.get("/api/v1/auth/me")          # 沒有帶憑證 → 401
    assert r.status_code == 401
    assert r.headers.get("cache-control") == "no-store"


def test_non_api_paths_are_untouched(client):
    """
    ZH: **陽性對照。** 上面兩條若是因為「所有回應都被加了 no-store」而過，
        它們就證明不了條件有在判斷。`/health` 不是 /api/ 開頭，不該被加。
    """
    r = client.get("/health")
    assert r.status_code == 200
    assert r.headers.get("cache-control") is None, \
        "非 /api/ 的路徑被加上了 no-store —— 判斷條件寫錯了"
