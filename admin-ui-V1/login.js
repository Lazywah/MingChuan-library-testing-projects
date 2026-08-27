/* ==========================================================================
 * login.js — 管理端登入
 *
 * ZH: 流程與舊版相同：`POST /auth/login` → `GET /auth/me` → 檢查 role。
 *
 * ⚠ **role 檢查只是體驗，不是安全機制。** 真正的權限在後端每一個
 *   `/api/v1/admin/*` 端點上（`Depends(require_admin)`）。這裡擋一下，
 *   是為了讓非管理員在**登入當下**就知道「你進不去」，
 *   而不是進到一個每一格都 403 的畫面再自己推理發生什麼事。
 *
 * ZH: token 存成 `ai_hud_token` —— 與使用者端**同名但不同 origin**。
 *   localStorage 是按 origin 隔離的（`:8888` 與 `:80` 各一份），
 *   所以不會互相覆蓋。同名的好處是共用的 `prefs.js` 一個字都不用改。
 * ========================================================================== */
(function () {
    'use strict';

    var API = '/api/v1';
    var TOKEN_KEY = 'ai_hud_token';

    function $(id) { return document.getElementById(id); }

    // ZH: `T()` 是 prefs.js 提供的全域，不要在這裡再寫一份 ——
    //     兩份定義遲早會漂開（同一個 key 在兩頁翻出不同結果，而且沒有人會發現）。

    function showError(msg) {
        var box = $('adm-error');
        box.textContent = msg;
        box.hidden = false;
    }

    $('adm-form').addEventListener('submit', async function (ev) {
        ev.preventDefault();
        var btn = $('adm-submit');
        $('adm-error').hidden = true;
        btn.disabled = true;

        try {
            var body = new URLSearchParams({
                username: $('adm-user').value.trim(),
                password: $('adm-pass').value,
            });
            var r = await fetch(API + '/auth/login', {
                method: 'POST',
                headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                body: body,
            });
            if (!r.ok) {
                // ZH: 帳號錯與密碼錯**講同一句話** —— 分開講等於告訴外面
                //     「這個帳號存在」，那是可以拿來列舉帳號的。
                showError(T('adm_login_fail', '登入失敗，請檢查帳號密碼。'));
                btn.disabled = false;
                return;
            }
            var tok = (await r.json()).access_token;

            var me = await fetch(API + '/auth/me', {
                headers: { Authorization: 'Bearer ' + tok },
            });
            var user = me.ok ? await me.json() : null;
            // ZH: v3.8 看 is_admin 旗標不看 role（身分與權限拆開）。
            if (!user || !user.is_admin) {
                // ZH: 這一句**可以**講得具體：他已經證明自己是這個帳號的主人了，
                //     告訴他「你不是管理員」不會洩漏任何他不知道的事。
                showError(T('adm_login_not_admin', '這個帳號不是管理員。'));
                btn.disabled = false;
                return;
            }

            sessionStorage.setItem(TOKEN_KEY, tok);
            location.href = 'index.html';
        } catch (e) {
            // ZH: 連不上與帳密錯**要分開講**：前者他再怎麼打都不會過，
            //     叫他去檢查帳密是把人送去錯的方向。
            showError(T('adm_login_offline', '連不上伺服器，請確認服務是否啟動。'));
            btn.disabled = false;
        }
    });
})();
