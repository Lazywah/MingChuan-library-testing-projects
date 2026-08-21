/* ==========================================================================
 * admin-chrome.js — 管理端的頂部列（唯一真相來源）
 *
 * ZH: 導覽、顯示設定、帳號、登出**只在這裡產生一次**，各頁不要自己寫。
 *     使用者端 v2 就是因為「九頁各寫一份色系切換」而只有一頁會存設定 ——
 *     那個 bug 花了實地測試才發現。這裡從一開始就集中。
 *
 * ZH: 顯示設定（字級／語言／色系）**直接放在頂部列上**，不收進選單。
 *     理由：舊版管理端把 A− / A+ 與主題、語言放在側邊欄常駐，
 *     那是你已經習慣的位置；收進選單等於平白拿掉一個你每天在用的東西。
 *     （使用者端收進帳號選單是因為那邊版面窄、且一般使用者很少調。）
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
        { file: 'people.html',    key: 'adm_nav_people',    zh: '人' },
        { file: 'platform.html',  key: 'adm_nav_platform',  zh: '平台設定' },
        { file: 'reports.html',   key: 'adm_nav_reports',   zh: '回報' },
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
        bar.innerHTML =
            '<span class="topbar__brand" data-i18n="adm_brand">MCU AI Base 管理端</span>'
            + '<nav class="adm-nav" aria-label="管理端導覽">'
            + NAV.map(function (n) {
                var cur = n.file === here;
                return '<a class="adm-nav__item' + (cur ? ' is-current' : '') + '"'
                    + ' href="' + n.file + '"' + (cur ? ' aria-current="page"' : '')
                    + ' data-i18n="' + n.key + '">' + esc(n.zh) + '</a>';
            }).join('')
            + '</nav>'
            + '<span class="topbar__spacer"></span>'

            // ── 顯示設定（常駐，沿用舊版側邊欄的位置習慣）
            + '<div class="adm-prefs">'
            + '  <div class="adm-font" role="group" aria-label="字級" data-i18n-aria="prefs_font">'
            + '    <button type="button" id="adm-font-down" aria-label="縮小字級">A−</button>'
            + '    <span id="adm-font-val">100%</span>'
            + '    <button type="button" id="adm-font-up" aria-label="放大字級">A+</button>'
            + '  </div>'
            + '  <button class="adm-lang" type="button" id="adm-lang" aria-label="Language">中 / EN</button>'
            + '  <div class="theme-switch" role="group" aria-label="色系" data-i18n-aria="theme_aria">'
            + '    <button type="button" data-set-theme="yellow" data-i18n="theme_yellow">黃</button>'
            + '    <button type="button" data-set-theme="blue" data-i18n="theme_blue">藍</button>'
            + '  </div>'
            + '</div>'

            + '<span class="adm-who" id="adm-who" title=""></span>'
            + '<button class="adm-logout" type="button" id="adm-logout" data-i18n="adm_logout">登出</button>';

        document.body.insertBefore(bar, document.body.firstChild);
        wire();
    }

    function wire() {
        var st = window.Prefs.get();

        function setFont(delta) {
            var next = window.Prefs.get().ui_font_scale + delta;
            next = Math.min(window.Prefs.MAX, Math.max(window.Prefs.MIN, next));
            window.Prefs.set({ ui_font_scale: next });
            paintFont(next);
        }
        function paintFont(p) {
            document.getElementById('adm-font-val').textContent = p + '%';
            // ZH: 到頂／到底時停用按鈕 —— 不然使用者會一直按而畫面毫無反應，
            //     那看起來像壞了而不是「已經到底了」。
            document.getElementById('adm-font-down').disabled = (p <= window.Prefs.MIN);
            document.getElementById('adm-font-up').disabled = (p >= window.Prefs.MAX);
        }
        document.getElementById('adm-font-down').addEventListener('click', function () { setFont(-10); });
        document.getElementById('adm-font-up').addEventListener('click', function () { setFont(10); });
        paintFont(st.ui_font_scale);

        document.getElementById('adm-lang').addEventListener('click', function () {
            var cur = window.Prefs.get().ui_lang;
            window.Prefs.set({ ui_lang: cur === 'zh' ? 'en' : 'zh' });
        });

        document.getElementById('adm-logout').addEventListener('click', async function () {
            try {
                await fetch(API + '/auth/logout', {
                    method: 'POST',
                    headers: { Authorization: 'Bearer ' + token() },
                });
            } catch (e) { /* ZH: 後端掛了也要讓他登出，見檔頭 */ }
            sessionStorage.removeItem(TOKEN_KEY);
            localStorage.removeItem(TOKEN_KEY);
            location.replace('login.html');
        });

        loadWho();
    }

    async function loadWho() {
        var el = document.getElementById('adm-who');
        try {
            var r = await fetch(API + '/auth/me', { headers: { Authorization: 'Bearer ' + token() } });
            if (r.status === 401) { location.replace('login.html'); return; }
            if (!r.ok) throw new Error('HTTP ' + r.status);
            var me = await r.json();

            // ZH: 顯示設定跟帳號走 —— 拿到 /auth/me 之後與本地快取對帳。
            if (window.Prefs.syncFrom) window.Prefs.syncFrom(me);
            document.getElementById('adm-font-val').textContent =
                window.Prefs.get().ui_font_scale + '%';

            el.textContent = me.username || '';
            el.title = (me.email || '');
        } catch (e) {
            // ZH: 讀不到就留白，**不要寫「未登入」** —— 那是錯的：
            //     token 還在、頁面也還能用，只是這一次沒讀到名字。
            el.textContent = '';
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
