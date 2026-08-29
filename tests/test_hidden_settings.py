"""
ZH: 從管理畫面隱藏的營運旋鈕（v3.9）。

ZH: 為什麼要有這支測試：`hidden` 是**刻意的**，不是漏掉。
    沒有東西釘住的話，下一個人看到「registry 裡有、畫面上沒有」會當成 bug 修掉，
    然後那兩個會誤導人的旋鈕就回到畫面上了。

ZH: 隱藏的理由（擁有者 2026-08-29 裁定）：
    `monthly_token_limit` / `token_reset_day` 是**平台自己的** Token 額度與重置日，
    跟學生實際在用的 MYAI 點數無關。兩者並排時，接手的人會以為調這裡就能改
    學生的額度 —— 調了不會有效果，也不會有任何錯誤訊息告訴他調錯地方。
"""
from conftest import make_user, auth_headers

from app import crud


HIDDEN_KEYS = {"monthly_token_limit", "token_reset_day"}


def test_hidden_keys_are_absent_from_the_admin_list(db):
    """ZH: 管理畫面拿到的清單不含它們。"""
    keys = {s["key"] for s in crud.get_all_settings(db)}
    assert keys.isdisjoint(HIDDEN_KEYS), "隱藏的旋鈕出現在管理清單裡"


def test_hidden_keys_still_exist_and_still_work(db):
    """
    ZH: 🔴 陽性對照 —— **隱藏 ≠ 停用**。

    ZH: 沒有這一條的話，上面那個測試在「key 被整個刪掉」時也會過，
        變成守不住任何東西的假綠。平台的月額度與重置日照常運作。
    """
    for k in HIDDEN_KEYS:
        assert k in crud.SYSTEM_SETTINGS, f"{k} 被刪掉了，不只是隱藏"
        assert crud.get_setting(db, k) is not None, f"{k} 讀不到生效值"


def test_hidden_and_public_are_mutually_exclusive(db):
    """ZH: 兩個都標＝管理者看不到、使用者卻看得到，必然是標錯的。"""
    both = [k for k, v in crud.SYSTEM_SETTINGS.items()
            if v.get("hidden") and v.get("public")]
    assert both == []


def test_the_admin_endpoint_does_not_leak_them(client, db):
    """
    ZH: 端點層也要驗 —— 過濾是寫在 crud 還是 router 是實作細節，
        使用者走的是這條路。
    """
    make_user(db, username="adm", email="adm@example.com", role="admin")
    h = auth_headers(client, "adm", "password123")
    body = client.get("/api/v1/admin/system-settings", headers=h).json()
    keys = {s["key"] for s in body["settings"]}
    assert keys.isdisjoint(HIDDEN_KEYS)
    # ZH: 陽性對照：這個端點確實有回東西（否則上面那行是空集合恆真）
    assert "job_timeout_minutes" in keys
