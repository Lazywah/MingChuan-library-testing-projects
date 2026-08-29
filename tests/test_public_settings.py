"""
ZH: 前台唯讀營運設定（v3.8）—— 白名單本身就是這個功能的全部風險所在。
EN: v3.8 whitelisted read-only operational settings for the user-facing site.

ZH: 這支測試守的不是「端點會不會回 200」，而是**白名單有沒有被悄悄放寬**。
    多一個 key 進去，就是多一個值被送到每個登入使用者的瀏覽器，
    而那件事在畫面上看不出來。
"""
import pytest
from conftest import make_user, auth_headers

from app import crud


PUBLIC_KEYS = {"job_timeout_minutes", "lab_archive_days"}


class TestPublicSettingWhitelist:
    def test_returns_exactly_the_whitelisted_keys(self, db):
        assert set(crud.get_public_settings(db)) == PUBLIC_KEYS

    def test_monthly_token_limit_is_not_exposed(self, db):
        """
        ZH: 擁有者 2026-08-27 裁定不揭露 —— 那個值只是**新帳號**的預設，
            既有使用者的額度各自不同，寫在前台對多數人是錯的數字。
            這條獨立寫一個測試，是因為它是「刻意不做」而不是「還沒做」：
            將來有人順手把它加進白名單時，要有東西擋下來並說明原因。
        """
        assert "monthly_token_limit" not in crud.get_public_settings(db)
        # ZH: 但它必須仍然是一個存在的旋鈕 —— 否則這個測試會因為
        #     「key 被改名了」而恆真，變成守不住任何東西的假綠。
        assert "monthly_token_limit" in crud.SYSTEM_SETTINGS

    def test_every_public_setting_is_also_starred(self, db):
        """ZH: 星號＝使用者看得到 或 改前應公告。被前台讀走就必然滿足前半句。"""
        unstarred = [k for k, v in crud.SYSTEM_SETTINGS.items()
                     if v.get("public") and not v.get("starred")]
        assert unstarred == []

    def test_returns_effective_value_not_env_default(self, db):
        """ZH: 管理者改過的值要**當場**反映到前台，否則畫面會停在舊數字。"""
        before = crud.get_public_settings(db)["lab_archive_days"]
        crud.set_settings(db, {"lab_archive_days": before + 1})
        after = crud.get_public_settings(db)["lab_archive_days"]
        assert after == before + 1, "改了營運設定,前台讀到的仍是舊值"

    def test_out_of_range_value_is_clamped_not_rejected(self, db):
        """
        ZH: 封存天數範圍 1–365。

        ZH: ⚠ 超出範圍時 `set_settings` **不拋錯，是靜默夾限** ——
            我原本寫成 `pytest.raises(ValueError)`，測試當場紅了才發現。
            記在這裡是因為這個行為從呼叫端看不出來：
            管理者輸入 999、畫面不報錯，實際存進去的是 365。
            會拋錯的只有「型別不對」與「choice 不在清單裡」兩種。

        ZH: 對前台的意義：白名單送出去的值**保證落在宣告範圍內**，
            所以畫面上不會出現「封存 0 天」這種自相矛盾的說法。
        """
        crud.set_settings(db, {"lab_archive_days": 999})
        assert crud.get_public_settings(db)["lab_archive_days"] == 365

        crud.set_settings(db, {"lab_archive_days": 0})
        assert crud.get_public_settings(db)["lab_archive_days"] == 1

        # ZH: 型別不對才是真的會拋 —— 兩種行為要分清楚,否則上面那段註解只是我的猜測。
        with pytest.raises(ValueError):
            crud.set_settings(db, {"lab_archive_days": "不是數字"})

    def test_token_reset_day_is_no_longer_exposed(self, db):
        """
        ZH: 2026-08-29 退出白名單。**這是刻意的，不是漏掉。**

        ZH: 它當初被揭露，只為了在使用量頁面寫一句「額度每月 N 號重置。」
            —— 而那句話印在 **MYAI 點數**的卡片裡，講的卻是平台自己的
            Token 重置日。MYAI 的點數不會每月重置（廠商後台根本沒有這個功能），
            所以那是一句會被當真的錯話。句子拿掉了，這個值就沒有前台讀者。

        ZH: 沒有讀者還留在白名單裡的話，下一個人看到瀏覽器拿得到這個值，
            很可能又拿它寫回同一句話。所以把入口關掉，並在這裡留下原因。
        """
        assert "token_reset_day" not in crud.get_public_settings(db)
        # ZH: 但它必須仍然是一個存在的旋鈕（平台自己的重置照常運作，
        #     只是不對使用者講）—— 否則這個測試會因為 key 被改名而恆真。
        assert "token_reset_day" in crud.SYSTEM_SETTINGS


class TestPublicSettingEndpoint:
    def test_requires_login(self, client):
        resp = client.get("/api/v1/system/public-settings")
        assert resp.status_code == 401

    def test_logged_in_user_gets_the_whitelist(self, client, db):
        make_user(db)
        resp = client.get("/api/v1/system/public-settings",
                          headers=auth_headers(client))
        assert resp.status_code == 200
        assert set(resp.json()["settings"]) == PUBLIC_KEYS
