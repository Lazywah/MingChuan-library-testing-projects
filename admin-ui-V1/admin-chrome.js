/* ==========================================================================
 * admin-chrome.js — 管理端的頂部列（唯一真相來源）
 *
 * ZH: 導覽、顯示設定、帳號、登出**只在這裡產生一次**，各頁不要自己寫。
 *     使用者端 v2 就是因為「九頁各寫一份色系切換」而只有一頁會存設定 ——
 *     那個 bug 花了實地測試才發現。這裡從一開始就集中。
 *
 * ZH: 顯示設定（字級／語言／顏色）收進帳號選單，與使用者端同一個樣子。
 *
 * ZH: ⚠ 這裡原本是相反的做法（常駐在頂部列），理由寫的是「沿用舊版側邊欄的
 *     位置習慣」。改掉是因為兩端長得不一樣本身就是成本：同一個人在兩邊
 *     切換，每次都要重新找一次那三個東西在哪。常駐省下的那一次點擊，
 *     換不到「兩套介面各記一套」。
 *
 * ZH: ⚠ 登入頁**不載這支**，所以它的色系切換留在該頁的 HTML 裡 ——
 *     那一頁沒有這個選單，拿掉就沒有地方可以改了。
 *
 * ⚠ 登出**不論成敗都導回登入頁**：後端掛掉時若停在原地，
 *   使用者會以為自己還登著，而畫面上的資料其實已經是舊的。
 * ========================================================================== */
(function () {
    'use strict';

    var API = '/api/v1';
    var TOKEN_KEY = 'ai_hud_token';

    // ZH: 五頁。`file` 對應實際檔名，`key` 是翻譯 key。
    //     順序＝設計文件第 1 節推導的使用時機：先「看有沒有出事」，最後才是「查數字」。
    var NAV = [
        { file: 'index.html',     key: 'adm_nav_overview',  zh: '總覽' },
        { file: 'people.html',    key: 'adm_nav_people',    zh: '帳號' },
        { file: 'platform.html',  key: 'adm_nav_platform',  zh: '平台設定' },
        { file: 'reports.html',   key: 'adm_nav_msg',       zh: '訊息' },
        { file: 'analytics.html', key: 'adm_nav_analytics', zh: '數據' },
    ];

    function token() {
        return sessionStorage.getItem(TOKEN_KEY) || localStorage.getItem(TOKEN_KEY);
    }

    function requireLogin() {
        if (!token()) {
            location.replace('login.html');
            return false;
        }
        return true;
    }

    function esc(s) {
        return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
            return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
        });
    }

    function build() {
        var here = (location.pathname.split('/').pop() || 'index.html');
        var bar = document.createElement('header');
        bar.className = 'topbar';

        // ZH: 版面：只有品牌在左，導覽與帳號選單一起靠右。
        //     跟使用者端一致 —— 那邊也是「LOGO 在左，其餘全部靠右」。
        bar.innerHTML =
            '<span class="topbar__brand" data-i18n="adm_brand">MCU AI Base 管理端</span>'
            + '<span class="topbar__spacer"></span>'
            + '<nav class="adm-nav" aria-label="管理端導覽" data-i18n-aria="adm_nav_aria">'
            + NAV.map(function (n) {
                var cur = n.file === here;
                return '<a class="adm-nav__item' + (cur ? ' is-current' : '') + '"'
                    + ' href="' + n.file + '"' + (cur ? ' aria-current="page"' : '')
                    + ' data-i18n="' + n.key + '">' + esc(n.zh) + '</a>';
            }).join('')
            + '</nav>'

            // ZH: 中／英切換，放在帳號鈕左邊（與使用者端同一個位置與同一份樣式）。
            //     不接事件 —— prefs.js 的委派負責點擊與 aria-pressed。
            + '<div class="lang-switch">'
            + '  <button type="button" data-set-lang="zh" aria-pressed="true"'
            + '          data-i18n-aria="prefs_lang_zh" aria-label="切換成中文">中</button>'
            + '  <button type="button" data-set-lang="en" aria-pressed="false"'
            + '          data-i18n-aria="prefs_lang_en" aria-label="切換成英文">EN</button>'
            + '</div>'

            // ZH: 帳號選單。class 沿用共用 styles.css 的 .account* ——
            //     那一套是使用者端在用的，兩邊共用同一份樣式就不會漂開。
            + '<div class="account">'
            + '  <button class="account__toggle" type="button" id="adm-acct"'
            + '          aria-haspopup="menu" aria-expanded="false"></button>'
            + '  <div class="account__menu" role="menu" hidden id="adm-menu"></div>'
            + '</div>';

        document.body.insertBefore(bar, document.body.firstChild);
        wire();
    }

    // ZH: 取文案。字典裡沒有就用 fallback，**不清空**。
    function T(key, fallback) {
        return (window.Prefs && window.Prefs.t) ? window.Prefs.t(key, fallback) : fallback;
    }

    function item(el, key, fallback) {
        el.setAttribute('role', 'menuitem');
        el.setAttribute('data-i18n', key);
        el.textContent = T(key, fallback);
        return el;
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
        // ZH: 🔴 「這一下點在選單裡嗎」必須在**捕獲階段**先記下來。
        //     顏色那幾顆按鈕靠 prefs.js 的 document 委派，所以不能 stopPropagation；
        //     等它冒泡到這裡時，prefs:applied 已經把整個選單重畫過了，
        //     ev.target 早就脫離 DOM —— contains() 回 false，選單就被誤關。
        //     （實測：點字級不會關、點顏色會關，差別就在這裡。）
        var inside = false;
        document.addEventListener('click', function (ev) {
            inside = menu.contains(ev.target) || toggle.contains(ev.target);
        }, true);
        document.addEventListener('click', function () {
            if (!menu.hidden && !inside) close();
        });
        // ZH: Esc 關閉 —— 只能用滑鼠關的選單對鍵盤使用者是陷阱。
        document.addEventListener('keydown', function (ev) {
            if (ev.key === 'Escape') close();
        });
    }

    // ── 顯示設定（字級／語言／顏色）────────────────────────────────────────
    // ZH: 與使用者端 chrome.js 的 prefsSection() 是同一個版面與同一組 class。
    //     兩邊刻意長一樣：同一個人會在兩端之間切換。
    function prefsSection() {
        var box = document.createElement('div');
        box.className = 'account__prefs';

        var title = document.createElement('div');
        title.className = 'account__prefs-title';
        title.setAttribute('data-i18n', 'prefs_title');
        title.textContent = T('prefs_title', '顯示設定');
        box.appendChild(title);

        // 字級
        var fontRow = document.createElement('div');
        fontRow.className = 'account__prefs-row';
        var fontLabel = document.createElement('span');
        fontLabel.setAttribute('data-i18n', 'prefs_font');
        fontLabel.textContent = T('prefs_font', '字級');
        fontRow.appendChild(fontLabel);

        var group = document.createElement('div');
        group.className = 'account__seg';
        var out = document.createElement('span');
        out.className = 'account__seg-value';
        out.textContent = window.Prefs.get().ui_font_scale + '%';

        function stepBtn(delta, key, fb, label) {
            var b = document.createElement('button');
            b.type = 'button';
            b.textContent = label;
            b.setAttribute('data-i18n-aria', key);
            b.setAttribute('aria-label', T(key, fb));
            // ZH: 到頂／到底就停用 —— 不然一直按而畫面毫無反應，
            //     那看起來像壞了而不是「已經到底了」。
            var cur = window.Prefs.get().ui_font_scale;
            b.disabled = delta < 0 ? (cur <= window.Prefs.MIN) : (cur >= window.Prefs.MAX);
            b.addEventListener('click', function (ev) {
                ev.stopPropagation();          // ZH: 別讓它把選單關掉
                var now = window.Prefs.get().ui_font_scale + delta;
                now = Math.min(window.Prefs.MAX, Math.max(window.Prefs.MIN, now));
                window.Prefs.set({ ui_font_scale: now });
            });
            return b;
        }
        group.appendChild(stepBtn(-10, 'prefs_font_smaller', '縮小字級', 'A−'));
        // ZH: 中間顯示目前值，並兼任「還原 100%」—— 數字本身可點，省一顆按鈕。
        var reset = document.createElement('button');
        reset.type = 'button';
        reset.className = 'account__seg-reset';
        reset.setAttribute('data-i18n-aria', 'prefs_font_reset');
        reset.setAttribute('aria-label', T('prefs_font_reset', '還原為 100%'));
        reset.appendChild(out);
        reset.addEventListener('click', function (ev) {
            ev.stopPropagation();
            window.Prefs.set({ ui_font_scale: 100 });
        });
        group.appendChild(reset);
        group.appendChild(stepBtn(10, 'prefs_font_bigger', '放大字級', 'A+'));
        fontRow.appendChild(group);
        box.appendChild(fontRow);


        // 顏色
        //
        // ZH: 按鈕不用自己接事件：prefs.js 有一個 document 層的委派監聽
        //     （closest('[data-set-theme]')），aria-pressed 也由它統一重畫。
        var themeRow = document.createElement('div');
        themeRow.className = 'account__prefs-row';
        var themeLabel = document.createElement('span');
        themeLabel.setAttribute('data-i18n', 'prefs_theme');
        themeLabel.textContent = T('prefs_theme', '顏色');
        themeRow.appendChild(themeLabel);
        var themeGroup = document.createElement('div');
        themeGroup.className = 'account__seg';
        themeGroup.setAttribute('role', 'group');
        themeGroup.setAttribute('data-i18n-aria', 'theme_aria');
        themeGroup.setAttribute('aria-label', T('theme_aria', '色系'));
        [['yellow', 'theme_yellow', '黃'], ['blue', 'theme_blue', '藍']].forEach(function (t) {
            var b = document.createElement('button');
            b.type = 'button';
            b.dataset.setTheme = t[0];
            b.setAttribute('data-i18n', t[1]);
            b.textContent = T(t[1], t[2]);
            // ZH: ⚠ 初始值要自己設。prefs.js 只在 prefs:applied 時重畫所有
            //     [data-set-theme]，而這幾顆是**在那之後**才產生的 ——
            //     不設的話 aria-pressed 是 null，讀螢幕的人聽不出哪一個是選中的。
            b.setAttribute('aria-pressed', String(t[0] === window.Prefs.get().ui_theme));
            themeGroup.appendChild(b);
        });
        themeRow.appendChild(themeGroup);
        box.appendChild(themeRow);

        return box;
    }

    var _toggle = null, _menu = null, _me = null;

    function wire() {
        _toggle = document.getElementById('adm-acct');
        _menu = document.getElementById('adm-menu');
        wireToggle(_toggle, _menu);
        renderMenu();
        loadWho();
    }

    // ZH: 改字級／語言／顏色都會觸發 prefs:applied。整個選單重畫 ——
    //     像「管理員 · a@b.c」這種**組合字串**不是 data-i18n 元素，
    //     prefs.js 的字典掃描換不掉它，只會留下半中半英的選單。
    document.addEventListener('prefs:applied', function () {
        if (_menu) renderMenu();
    });

    function renderMenu() {
        var name = (_me && _me.username) || '';
        _toggle.textContent = '';
        var who = document.createElement('span');
        who.className = 'account__name';
        who.textContent = name || T('acct_loading', '載入中…');
        _toggle.appendChild(who);
        var caret = document.createElement('span');
        caret.className = 'account__caret';
        caret.setAttribute('aria-hidden', 'true');
        caret.textContent = '▾';
        _toggle.appendChild(caret);
        _toggle.setAttribute('aria-label', T('acct_menu', '帳號選單') + '：' + name);

        _menu.textContent = '';

        if (_me) {
            var head = document.createElement('div');
            head.className = 'account__id';
            var n1 = document.createElement('div');
            n1.className = 'account__id-name';
            n1.textContent = name;
            head.appendChild(n1);
            var sub = document.createElement('div');
            sub.className = 'account__id-sub';
            // ⚠ ZH: SSO 使用者沒有 email 時後端會給 `<學號>@unknown`，
            //     顯示出來像壞掉的資料。那種就只顯示身分。
            var mail = _me.email || '';
            sub.textContent = /@unknown$/.test(mail) || !mail
                ? T('role_admin', '管理員')
                : T('role_admin', '管理員') + ' · ' + mail;
            head.appendChild(sub);
            _menu.appendChild(head);
        }

        // ZH: 回使用者介面。管理端在 :8888、使用者端在 :80，是**不同的 origin**，
        //     所以不做 token 交棒（那份 token 在對面的 storage 裡本來就有）。
        //
        // ZH: 🔴 路徑一定要帶 `/V1/`。根路徑雖然已經導向 V1，但那是 302 ——
        //     多一次往返，而且 catch-all 底下仍是 Open WebUI（完全不同的產品）。
        //     nginx 上三個版本各自有路徑：/V0/、/V0.5/、/V1/（現行）。
        var back = document.createElement('a');
        back.href = location.protocol + '//' + location.hostname + '/V1/';
        _menu.appendChild(item(back, 'adm_back_user', '回到使用者介面'));

        _menu.appendChild(prefsSection());

        var out = document.createElement('button');
        out.type = 'button';
        out.className = 'account__logout';
        out.addEventListener('click', logout);
        _menu.appendChild(item(out, 'adm_logout', '登出'));
    }

    async function logout() {
        try {
            await fetch(API + '/auth/logout', {
                method: 'POST',
                headers: { Authorization: 'Bearer ' + token() },
            });
        } catch (e) { /* ZH: 後端掛了也要讓他登出，見檔頭 */ }
        sessionStorage.removeItem(TOKEN_KEY);
        localStorage.removeItem(TOKEN_KEY);
        location.replace('login.html');
    }

    async function loadWho() {
        try {
            var r = await fetch(API + '/auth/me', { headers: { Authorization: 'Bearer ' + token() } });
            if (r.status === 401) { location.replace('login.html'); return; }
            if (!r.ok) throw new Error('HTTP ' + r.status);
            _me = await r.json();

            // ZH: 顯示設定跟帳號走 —— 拿到 /auth/me 之後與本地快取對帳。
            //     ⚠ syncFrom 會觸發 prefs:applied → renderMenu()，所以要先存 _me。
            if (window.Prefs.syncFrom) window.Prefs.syncFrom(_me);
            renderMenu();
        } catch (e) {
            // ZH: 讀不到就留白，**不要寫「未登入」** —— 那是錯的：
            //     token 還在、頁面也還能用，只是這一次沒讀到名字。
            _me = null;
            renderMenu();
        }
    }

    if (requireLogin()) {
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', build);
        } else {
            build();
        }
    }
})();
