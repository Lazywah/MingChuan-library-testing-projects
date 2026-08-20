/* ==========================================================================
 * chrome.js — 頂部列右側的唯一真相來源（導覽 + 帳號選單 + 登出）
 *
 * ZH: 版面（擁有者裁定 2026-08-20）：
 *
 *     [MCU AI Base]                        MYAI · Lab ·（色系）·［學號 ▾］
 *      ← 只有 LOGO 在左，其餘全部靠右
 *
 *     LOGO 本身就是回首頁的連結，所以原本各頁左上角的「‹ 首頁」拿掉——
 *     兩個做同一件事的東西擺在同一條列上只會讓人猶豫該按哪個。
 *
 * ZH: 為什麼整塊由 JS 建，而不是在 8 個 HTML 各寫一份：
 *     topbar 本來就有三種變體（首頁沒有返回鍵、login 沒有導覽、其餘有兩者），
 *     再手工複製 8 份帳號選單必定漂掉。一份 JS ＝ 一個真相來源，
 *     login.html 就是不載入這支。
 *
 * ⚠ **登出的順序不能反過來**：
 *     `ai_hud_token` 是 **HttpOnly** cookie（後端 auth.py 明寫），JS 讀不到也刪不掉，
 *     而**那個 cookie 才是 nginx auth_request 放行 /code/<uid>/ 的憑證**。
 *     只清 sessionStorage 的話，使用者以為登出了，Lab 卻還進得去。
 *     所以一定要先打 POST /auth/logout（後端 delete_cookie），
 *     但**不管它成功與否都要清本地並導回登入頁**——網路一斷就把人鎖在登入狀態更糟。
 *
 * ⚠ **選單只放真的存在的去處。** v1.5 的下拉有 User Profile 與 Change Password，
 *     v2 沒有那兩個頁面，所以不放——設計文件 §5 的 V3 就是在講
 *     「入口通往不存在的地方」這件事。
 * ========================================================================== */
(function () {
    'use strict';

    var API = '/api/v1';

    function token() {
        return sessionStorage.getItem('ai_hud_token') || localStorage.getItem('ai_hud_token');
    }
    function authHeaders() {
        var t = token();
        return t ? { Authorization: 'Bearer ' + t } : {};
    }

    // ── 登出 ──────────────────────────────────────────────────────────
    async function logout() {
        try {
            await fetch(API + '/auth/logout', { method: 'POST', headers: authHeaders(),
                                                credentials: 'include' });
        } catch (e) {
            // ZH: 後端連不上也要繼續往下清。**不能因為 API 失敗就把人留在登入狀態。**
        }
        sessionStorage.removeItem('ai_hud_token');
        localStorage.removeItem('ai_hud_token');
        localStorage.removeItem('admin_hud_token');   // ZH: 管理端用的那份也要清
        location.href = 'login.html';
    }

    // ── 建頂部列右側 ──────────────────────────────────────────────────
    function build() {
        var bar = document.querySelector('.topbar');
        if (!bar) return;

        // LOGO 變成回首頁的連結，並移除各頁重複的「‹ 首頁」
        var brand = bar.querySelector('.topbar__brand');
        if (brand && brand.tagName !== 'A') {
            var a = document.createElement('a');
            a.className = 'topbar__brand';
            a.href = 'index.html';
            a.textContent = brand.textContent;
            brand.replaceWith(a);
        }
        var back = bar.querySelector('.topbar__back');
        if (back) back.remove();

        // ZH: spacer 決定「LOGO 在左、其餘在右」。缺了就補一個。
        if (!bar.querySelector('.topbar__spacer')) {
            var sp = document.createElement('span');
            sp.className = 'topbar__spacer';
            (bar.querySelector('.topbar__brand') || bar.firstChild).after(sp);
        }

        var page = (location.pathname.split('/').pop() || 'index.html');

        // ── 導覽：MYAI（動作）· Lab（頁面）
        var nav = bar.querySelector('.topnav');
        if (!nav) {
            nav = document.createElement('nav');
            nav.className = 'topnav';
            nav.setAttribute('aria-label', '主要');
            // ZH: 插在色系切換**之前**。色系切換是開發期的東西（Decision Log #16，
            //     上線擇一後整塊移除），順序要讓「移除它之後仍然正確」：
            //       現在   MYAI Lab [黃][藍] [學號▾]
            //       上線後 MYAI Lab        [學號▾]
            //     若接在它後面，開發期會變成 [黃][藍] MYAI Lab，導覽被夾在中間。
            var theme = bar.querySelector('.theme-switch');
            if (theme) bar.insertBefore(nav, theme); else bar.appendChild(nav);
        }
        nav.textContent = '';

        // ZH: MYAI **不做跳轉，回首頁就好**（擁有者裁定 2026-08-20）。
        //     首頁本來就是「MYAI 那一頁」：額度在上面，層級 1 的動作就是前往 MYAI。
        //     從頂部直接開廠商分頁會讓「按了沒反應（被擋）」的處理散到八個頁面，
        //     回首頁則是把那件事收在唯一有 #handoff 的地方。
        var myai = document.createElement('a');
        myai.href = 'index.html';
        myai.textContent = 'MYAI';
        if (page === 'index.html' || page === '') myai.setAttribute('aria-current', 'page');
        nav.appendChild(myai);

        var lab = document.createElement('a');
        lab.href = 'lab.html';
        lab.textContent = 'Lab';
        // ZH: 底色只給「目前所在頁」（擁有者裁定）。
        if (page === 'lab.html') lab.setAttribute('aria-current', 'page');
        nav.appendChild(lab);

        // ── 帳號選單（永遠在最右邊；色系切換是開發期的，上線會整塊移除）
        var acc = document.createElement('div');
        acc.className = 'account';
        acc.innerHTML = '';
        var toggle = document.createElement('button');
        toggle.type = 'button';
        toggle.className = 'account__toggle';
        toggle.id = 'account-toggle';
        toggle.setAttribute('aria-haspopup', 'menu');
        toggle.setAttribute('aria-expanded', 'false');
        toggle.textContent = '載入中…';
        var menu = document.createElement('div');
        menu.className = 'account__menu';
        menu.setAttribute('role', 'menu');
        menu.hidden = true;
        acc.appendChild(toggle);
        acc.appendChild(menu);
        bar.appendChild(acc);

        wireToggle(toggle, menu);
        fillAccount(toggle, menu);
    }

    function wireToggle(toggle, menu) {
        function close() {
            menu.hidden = true;
            toggle.setAttribute('aria-expanded', 'false');
        }
        toggle.addEventListener('click', function (ev) {
            ev.stopPropagation();
            var open = menu.hidden;
            menu.hidden = !open;
            toggle.setAttribute('aria-expanded', String(open));
        });
        document.addEventListener('click', function (ev) {
            if (!menu.hidden && !menu.contains(ev.target)) close();
        });
        // ZH: Esc 關閉——只能用滑鼠關的選單對鍵盤使用者是陷阱。
        document.addEventListener('keydown', function (ev) {
            if (ev.key === 'Escape') close();
        });
    }

    var ROLE = { student: '學生', teacher: '教師', admin: '管理員' };

    function item(el, text) {
        el.setAttribute('role', 'menuitem');
        el.textContent = text;
        return el;
    }

    async function fillAccount(toggle, menu) {
        var me = null;
        try {
            var r = await fetch(API + '/auth/me',
                                { headers: Object.assign({ Accept: 'application/json' }, authHeaders()) });
            if (r.ok) me = await r.json();
        } catch (e) { /* 下面會處理 */ }

        if (!me) {
            // ZH: 取不到身分就不要假裝有人登入。給的是「去登入」而不是空選單。
            toggle.textContent = '未登入';
            menu.textContent = '';
            var go = document.createElement('a');
            go.href = 'login.html';
            menu.appendChild(item(go, '前往登入'));
            return;
        }

        toggle.textContent = '';
        var name = document.createElement('span');
        name.className = 'account__name';
        name.textContent = me.username || '（不明）';
        toggle.appendChild(name);
        var caret = document.createElement('span');
        caret.className = 'account__caret';
        caret.setAttribute('aria-hidden', 'true');
        caret.textContent = '▾';
        toggle.appendChild(caret);
        toggle.setAttribute('aria-label', '帳號選單：' + (me.username || ''));

        menu.textContent = '';

        // 身分（唯讀）
        var head = document.createElement('div');
        head.className = 'account__id';
        var who = document.createElement('div');
        who.className = 'account__id-name';
        who.textContent = me.username || '（不明）';
        head.appendChild(who);
        var sub = document.createElement('div');
        sub.className = 'account__id-sub';
        // ⚠ ZH: SSO 使用者沒有 email 時後端會給 `<學號>@unknown`（routers/sso.py），
        //     顯示出來像壞掉的資料。那種就只顯示身分。
        var mail = (me.email || '');
        sub.textContent = /@unknown$/.test(mail) || !mail
            ? (ROLE[me.role] || me.role || '')
            : (ROLE[me.role] || me.role || '') + ' · ' + mail;
        head.appendChild(sub);
        menu.appendChild(head);

        var usage = document.createElement('a');
        usage.href = 'usage.html';
        menu.appendChild(item(usage, '使用量明細'));

        var report = document.createElement('a');
        report.href = 'report.html';
        menu.appendChild(item(report, '問題回報'));

        if (me.role === 'admin') {
            // ZH: 管理端在同主機 port 8888，且要先把 token 交棒過去（沿用 v1.5 的做法）。
            var admin = document.createElement('a');
            admin.href = '#';
            admin.addEventListener('click', function (ev) {
                ev.preventDefault();
                var t = token();
                if (t) localStorage.setItem('admin_hud_token', t);
                location.href = location.protocol + '//' + location.hostname + ':8888/';
            });
            menu.appendChild(item(admin, '管理介面'));
        }

        var out = document.createElement('button');
        out.type = 'button';
        out.className = 'account__logout';
        out.addEventListener('click', logout);
        menu.appendChild(item(out, '登出'));
    }

    // ZH: 對外只暴露 logout —— 其他頁面若要做「登出」都該走同一份實作。
    //     （goMyai 已搬回 app.js：MYAI 改成回首頁之後，只剩首頁那顆按鈕在用它。）
    window.Chrome = { logout: logout };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', build);
    } else {
        build();
    }
})();
