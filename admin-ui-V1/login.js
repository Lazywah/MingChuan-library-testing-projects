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

    // ═════════════════════════════════════════════════════════════════
    // ZH: 「回使用者端」的網址在這裡組，不寫死在 HTML 裡。
    //
    // ZH: 原本寫的是 `http://localhost/v2/`，三處都不對：主機寫死成 localhost
    //     （正式機是 ai.lib.mcu.edu.tw，接管者從別台電腦點下去會連到他自己那台）、
    //     明文 http（:80 只剩 301 轉 https）、`/v2/` 是舊路徑（nginx 還留著
    //     302 到 /V1/，但沒有理由多繞一次）。
    //
    // ZH: 🔴 管理端與使用者端是**不同 origin**（:8888 vs :443），
    //     相對路徑會留在管理端這一側 —— 所以要組絕對網址：
    //     同協定、同主機、**拿掉 port**（使用者端在該協定的預設埠）。
    //
    // ZH: 🔴 :8890 是例外 —— 本機明文測試門把兩端掛在同一個 origin
    //     （管理端 /admin/、使用者端 /V1/）。在那裡拿掉 port 會跑去 :80，
    //     而 :80 只會 301 到 https://localhost，憑證簽給網域不簽 localhost
    //     → 必跳憑證警告。同一個門，用相對路徑才對。
    // ═════════════════════════════════════════════════════════════════
    function wireBackToUserSite() {
        var a = $('adm-to-user');
        if (!a) return;
        a.href = (location.port === '8890')
            ? '/V1/'
            : location.protocol + '//' + location.hostname + '/V1/';
    }

    wireBackToUserSite();

    function showError(msg) {
        var box = $('adm-error');
        box.textContent = msg;
        box.hidden = false;
    }

    // ══════════════════════════════════════════════════════════════════
    // ZH: v4.10 換票自動登入（擁有者裁定 2026-09-11）。
    //
    // ZH: 從使用者端點「管理介面」過來時，網址帶 `#ticket=…`。
    //     拿票跟後端換一個 token，換到就直接進去，不必再登入一次。
    //     這對 SSO 管理者是**唯一**可行的路 —— 他們的密碼是建號時隨機
    //     產生後丟掉的，根本沒有東西可以輸入（見 crud.create_sso_user）。
    //
    // ZH: 🔴 票不會給任何新權限：後端 redeem 會重新查資料庫確認這個人
    //     現在仍是管理員，回的是他**原本就有的**身分所簽的 token。
    //
    // ZH: 🔴 **不論成功失敗都要把 fragment 清掉**。留著的話：
    //       · 使用者按重新整理會拿一張已經用掉的票去換 → 看到錯誤訊息，
    //         而他其實已經登入成功了，那個錯誤完全沒道理
    //       · 票會留在網址列與瀏覽器歷史裡
    //     用 replaceState 清（不是改 location.hash）—— 後者會留下一筆歷史，
    //     按上一頁又回到帶票的網址。
    // ══════════════════════════════════════════════════════════════════
    function takeTicket() {
        var m = /[#&]ticket=([^&]+)/.exec(location.hash || '');
        if (!m) return null;
        var t = decodeURIComponent(m[1]);
        history.replaceState(null, '', location.pathname + location.search);
        return t;
    }

    async function tryHandoff() {
        var ticket = takeTicket();
        if (!ticket) return false;
        try {
            var r = await fetch(API + '/auth/admin-handoff/redeem', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ ticket: ticket }),
            });
            if (!r.ok) {
                // ZH: 講出來就好，不要卡住 —— 下面還有正常的登入表單可以用。
                showError(T('adm_handoff_fail',
                    '自動登入沒有成功（票可能過期了），請用帳號密碼登入，或回上一頁再按一次。'));
                return false;
            }
            sessionStorage.setItem(TOKEN_KEY, (await r.json()).access_token);
            location.href = 'index.html';
            return true;
        } catch (e) {
            showError(T('adm_login_offline', '連不上伺服器，請確認服務是否啟動。'));
            return false;
        }
    }

    tryHandoff();

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
