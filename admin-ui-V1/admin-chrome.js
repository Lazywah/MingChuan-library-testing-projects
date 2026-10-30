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
/* ──────────────────────────────────────────────────────────────────────────
 * ZH: v3.8 — API 請求一律繞過瀏覽器快取。
 *
 * ZH: 🔴 這不是「效能微調」，是修一個**看起來像後端壞掉**的故障。
 *     2026-08-27 稽核實測：問題回報頁顯示「暫時讀不到歷史回報」，
 *     而後端完全正常（直連 curl、經 nginx 都回 200 JSON）。
 *     原因是瀏覽器快取裡存著一份 **HTML**：
 *       nginx 若少掛某條 `/api/v1/...` 的 location，GET 會落到 catch-all
 *       (Open WebUI)，拿到它的 SPA 首頁 —— **200 而且可快取**。
 *       之後 nginx 補好了，瀏覽器仍然繼續給那份舊 HTML，
 *       前端 JSON.parse 失敗 → 顯示「讀不到」。
 *
 * ZH: 後端已經加了 `Cache-Control: no-store`（main.py 的 middleware），
 *     但那**只防未來** —— 已經存在使用者瀏覽器裡的那一筆不會自己消失。
 *     這一層讓已中招的人下次開頁面就恢復正常。
 *
 * ZH: 為什麼包 window.fetch 而不是逐一改：管理端每一頁各自有自己的 `api()` helper（people/platform/reports 三份）,
 *     加上散落的 fetch，逐一改就是 34 個會漏的地方，而且新寫的程式還會再漏。
 *     只對「同源 + /api/ 開頭」動手，其他請求原封不動。
 * ────────────────────────────────────────────────────────────────────────── */
(function () {
    'use strict';
    var _fetch = window.fetch;
    if (!_fetch || _fetch.__noStorePatched) return;
    function patched(input, init) {
        try {
            var url = (typeof input === 'string') ? input : (input && input.url) || '';
            // ZH: 只認同源的 /api/ —— 相對路徑，或絕對路徑但 origin 相同。
            var isApi = url.indexOf('/api/') === 0
                || url.indexOf(location.origin + '/api/') === 0;
            // ZH: 呼叫端已經指定 cache 的話不覆蓋（例如刻意要用快取的地方）。
            if (isApi && !(init && init.cache)) {
                init = Object.assign({}, init, { cache: 'no-store' });
            }
        } catch (e) { /* ZH: 這一層絕不能讓請求本身失敗 —— 出事就照原樣送出 */ }
        return _fetch.call(this, input, init);
    }
    patched.__noStorePatched = true;
    window.fetch = patched;
})();

(function () {
    'use strict';

    var API = '/api/v1';
    var TOKEN_KEY = 'ai_hud_token';

    // ZH: 六頁。`file` 對應實際檔名，`key` 是翻譯 key。
    //     順序＝設計文件第 1 節推導的使用時機：先「看有沒有出事」，最後才是「查數字」。
    var NAV = [
        { file: 'index.html',     key: 'adm_nav_overview',  zh: '總覽' },
        { file: 'people.html',    key: 'adm_nav_people',    zh: '帳號' },
        { file: 'platform.html',  key: 'adm_nav_platform',  zh: '平台設定' },
        { file: 'reports.html',   key: 'adm_nav_msg',       zh: '訊息' },
        { file: 'analytics.html', key: 'adm_nav_analytics', zh: '數據' },
        // ZH: v4.37 管理端 AI（唯讀查詢、本機模型）。放最後：它是查問題的輔助，不是日常巡視的一站。
        { file: 'ai.html',        key: 'adm_nav_ai',        zh: 'AI 查詢' },
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
        // ZH: 目前語言。給下面的中/英滑條算 aria-pressed 用（理由見那裡）。
        var adminLang = (window.Prefs && window.Prefs.get().ui_lang === 'en') ? 'en' : 'zh';

        // ZH: 版面：只有品牌在左，導覽與帳號選單一起靠右。
        //     跟使用者端一致 —— 那邊也是「LOGO 在左，其餘全部靠右」。
        bar.innerHTML =
            // ZH: 🔴 用 T() **建的時候就翻好**，不要寫中文等 applyLang 來翻。
            //     理由見下面導覽那一段的長註解 —— 那一趟不一定會來。
            '<span class="topbar__brand" data-i18n="adm_brand">'
            + esc(T('adm_brand', 'MCU AI Base 管理端')) + '</span>'
            + '<span class="topbar__spacer"></span>'
            // ZH: 手機版把右側整塊收進 ☰（v4.13，與使用者端同一套做法）——
            //     375px 實測原本擠成三排（品牌／導覽／語言＋帳號）約 280px 高。
            // ZH: ☰ 沒有文字，唸出來的就是 aria-label，所以要翻譯；
            //     符號本身包在 aria-hidden 裡，不然閱讀器會唸字元名。
            + '<button type="button" class="topbar__burger" id="adm-burger"'
            + '        aria-controls="adm-tools" aria-expanded="false"'
            + '        data-i18n-aria="nav_menu" aria-label="'
            +      esc(T('nav_menu', '選單')) + '"><span aria-hidden="true">☰</span></button>'
            // ZH: 桌面上這一層是普通的 flex 列（版面與包之前相同），
            //     手機上同一層變成 ☰ 底下展開的面板。一個容器 + 一條 media query，
            //     不做「依寬度搬節點」那種有狀態的做法。
            + '<div class="topbar__tools" id="adm-tools">'
            + '<nav class="adm-nav" aria-label="' + esc(T('adm_nav_aria', '管理端導覽'))
            +      '" data-i18n-aria="adm_nav_aria">'
            // ZH: 🔴 用 `T(n.key, n.zh)` 建，**不要**寫成 `esc(n.zh)` 等 applyLang 來翻。
            //
            // ZH: applyLang 這一趟不一定會來，而且**畫面上完全看不出來**：
            //       1. prefs.js 載入時就 apply() 過一次 —— 那時導覽還不存在
            //       2. build() 建出導覽（若寫中文，這時就是中文）
            //       3. loadWho() → syncFrom(me)：伺服器存的語言若**與本地快取相同**，
            //          它會 early return，**不再 apply**
            //     於是「帳號記得是英文、滑條也顯示 EN，只有導覽是中文」。
            //     實際回報過（2026-08-30）。
            // ZH: ⚠ data-i18n 仍然要留 —— 之後**切換**語言時靠它重畫。
            //     兩者是不同時機：T() 管「建出來的當下」，data-i18n 管「之後改語言」。
            + NAV.map(function (n) {
                var cur = n.file === here;
                return '<a class="adm-nav__item' + (cur ? ' is-current' : '') + '"'
                    + ' href="' + n.file + '"' + (cur ? ' aria-current="page"' : '')
                    + ' data-i18n="' + n.key + '">' + esc(T(n.key, n.zh)) + '</a>';
            }).join('')
            + '</nav>'

            // ZH: 中／英切換，放在帳號鈕左邊（與使用者端同一個位置與同一份樣式）。
            //     點擊不用接 —— prefs.js 有 document 層的委派。
            // ZH: 🔴 但 aria-pressed 的**初始值要自己算**（與使用者端同一個坑）：
            //     prefs.js 只在 applyLang() 裡重畫所有 [data-set-lang]，
            //     而這兩顆是在那之後才生出來的。寫死 true 的話，
            //     切成英文後換一頁，內容是英文而滑條回到「中」——
            //     語言其實好好的，是按鈕在說謊。
            + '<div class="lang-switch">'
            + '  <button type="button" data-set-lang="zh" aria-pressed="'
            +      (adminLang === 'zh' ? 'true' : 'false') + '"'
            + '          data-i18n-aria="prefs_lang_zh" aria-label="切換成中文">中</button>'
            + '  <button type="button" data-set-lang="en" aria-pressed="'
            +      (adminLang === 'en' ? 'true' : 'false') + '"'
            + '          data-i18n-aria="prefs_lang_en" aria-label="切換成英文">EN</button>'
            + '</div>'

            // ZH: 帳號選單。class 沿用共用 styles.css 的 .account* ——
            //     那一套是使用者端在用的，兩邊共用同一份樣式就不會漂開。
            + '<div class="account">'
            + '  <button class="account__toggle" type="button" id="adm-acct"'
            + '          aria-haspopup="menu" aria-expanded="false"></button>'
            + '  <div class="account__menu" role="menu" hidden id="adm-menu"></div>'
            + '</div>'
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

    // ZH: ☰ 的開關（v4.13）。與帳號下拉是不同性質的東西：帳號選單是面板**裡面**
    //     的一個項目，所以兩者不能共用同一套互斥邏輯 —— 收面板時要順手把帳號
    //     選單也收掉，反過來則不行（開帳號選單不該把面板關掉）。
    function wireBurger(btn, panel) {
        if (!btn || !panel) return;
        function close() {
            panel.classList.remove('is-open');
            btn.setAttribute('aria-expanded', 'false');
            if (_menu) {
                _menu.hidden = true;
                if (_toggle) _toggle.setAttribute('aria-expanded', 'false');
            }
        }
        btn.addEventListener('click', function (ev) {
            ev.stopPropagation();
            var open = !panel.classList.contains('is-open');
            if (!open) { close(); return; }
            panel.classList.add('is-open');
            btn.setAttribute('aria-expanded', 'true');
        });
        // ZH: 點面板外面就關。判斷要在**捕獲階段**先記 —— 理由與 wireToggle
        //     那段相同：面板裡的字級／顏色按鈕會讓 prefs.js 重畫整塊，
        //     冒泡到這裡時 ev.target 已經不在 DOM 上。
        var inside = false;
        document.addEventListener('click', function (ev) {
            inside = panel.contains(ev.target) || btn.contains(ev.target);
        }, true);
        document.addEventListener('click', function () {
            if (panel.classList.contains('is-open') && !inside) close();
        });
        // ZH: 點面板裡的連結要關 —— 導覽多半會換頁不必處理，但**目前這一頁**
        //     那一個不會換頁（停在總覽時點「總覽」），面板就會一直開著。
        panel.addEventListener('click', function (ev) {
            if (ev.target.closest && ev.target.closest('a')) close();
        });
        document.addEventListener('keydown', function (ev) {
            if (ev.key === 'Escape') close();
        });
    }

    // ZH: 頂部列放不下一排時改成 ☰（.topbar.is-compact，樣式在 admin.css「手機版把頂部列…」那段）。
    //     原本只看 ≤640px 這一條斷點，可是 640 以上也放不下：英文到約 1085px、中文到約 860px，
    //     頂部列折成兩三排（113／161px）。它是 sticky —— 錨點跳過來時標題被蓋住；1024 英文時
    //     還會隨著直捲軸出現／消失在一排與兩排之間跳，切篩選時整頁上下跳 57px（2026-10-30 版面掃描）。
    //     斷點寫死不了（語言、帳號名稱長度、字級都會改變需要的寬度），所以**實際量**：
    //     先拿掉 is-compact 排一次，任何一項的中線跟品牌不在同一排，就收成 ☰。
    //     兩種狀態頂部列都是一排 56px，切換本身不改頁面高度，不會來回跳。
    function wireFit(bar) {
        if (!bar) return;
        var queued = false;
        function fit() {
            queued = false;
            bar.classList.remove('is-compact');
            var narrow = window.innerWidth <= 640;
            if (!narrow) {
                var items = bar.querySelectorAll('.topbar__brand, .adm-nav__item, .topbar__tools > :not(nav)');
                var lo = Infinity, hi = -Infinity;
                [].forEach.call(items, function (e) {
                    var r = e.getBoundingClientRect();
                    if (!r.height) return;
                    var c = r.top + r.height / 2;
                    if (c < lo) lo = c;
                    if (c > hi) hi = c;
                });
                narrow = hi - lo > 12;
            }
            bar.classList.toggle('is-compact', narrow);
        }
        // ZH: 用 setTimeout 不用 requestAnimationFrame：分頁在背景時 rAF 整個停掉，
        //     在背景換了語言（或寬度）回來時頂部列會停在折行的樣子，直到下一次改視窗大小。
        function later() {
            if (queued) return;
            queued = true;
            setTimeout(fit, 0);
        }
        fit();
        window.addEventListener('resize', later);
        // ZH: 換語言／字級（prefs:applied）、帳號名稱載入（loadWho 改了按鈕寬度）都會改變需要的寬度。
        document.addEventListener('prefs:applied', later);
        if (window.ResizeObserver) new ResizeObserver(later).observe(bar);
        if (document.fonts && document.fonts.ready) document.fonts.ready.then(later);
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
        wireBurger(document.getElementById('adm-burger'),
                   document.getElementById('adm-tools'));
        wireFit(document.querySelector('.topbar'));
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

    // ZH: v4.10b 把目前登入者開放給各頁讀。
    //
    // ZH: 為什麼是這裡而不是各頁自己打一次 /auth/me：這一支**本來就會打**
    //     （為了畫帳號選單）。各頁再打一次等於同一個資訊有兩個來源，
    //     而且兩次回來的時間不同 —— 頁面會依賴哪一次先到，那種 bug 很難查。
    //
    // ZH: 回 null 是正常情況（還沒載到、或那一次讀失敗），呼叫端要自己處理。
    /* ZH: 帶 token 的檔案下載（v4.24，唯一真相）。
     *
     * ZH: 🔴 為什麼不能用 `<a href="/api/…">`：管理端的認證是 **Authorization 標頭**
     *     （token 在 localStorage），不是 cookie。瀏覽器自己發的下載請求不帶那個標頭，
     *     點下去只會拿到 401 —— 而畫面上看起來像「這個檔案壞了」。
     *
     * ZH: 🔴 這支的來歷：同一條規則原本在管理端有**四份**抄寫
     *     （使用者匯出、範例檔、數據匯出、組織對照表），而它們已經漂開了：
     *       · 四份都只認 `filename="…"`，沒有一份認 `filename*=UTF-8''…`
     *         → **中文檔名全部退回預設名**
     *       · 四份都**立刻** revokeObjectURL；慢一點的瀏覽器還沒開始讀就沒了，
     *         下載會是空檔（使用者端那份早就改成延遲 60 秒，但沒有人回頭改這邊）
     *     補邊界時只會補到其中一份，而另外三份**看起來仍然正常** —— 所以收斂。
     *
     * ZH: ⚠ 按鈕狀態（「匯出中…」）留在呼叫端：那是各頁自己的事，
     *     這支只負責把檔案交給瀏覽器。
     */
    async function download(path, fallbackName) {
        var r = await fetch(API + path, { headers: { Authorization: 'Bearer ' + token() } });
        if (!r.ok) throw new Error('HTTP ' + r.status);

        var cd = r.headers.get('content-disposition') || '';
        var name = fallbackName || 'download';
        var star = cd.match(/filename\*=UTF-8''([^;]+)/i);
        var plain = cd.match(/filename="?([^";]+)"?/i);
        if (star) { try { name = decodeURIComponent(star[1]); } catch (e) { /* 用下面那個 */ } }
        else if (plain) { name = plain[1]; }

        var url = URL.createObjectURL(await r.blob());
        var a = document.createElement('a');
        a.href = url;
        a.download = name;
        document.body.appendChild(a);
        a.click();
        a.remove();
        // ZH: 延遲 revoke —— 立刻撤銷的話慢一點的瀏覽器會拿到空檔。
        setTimeout(function () { URL.revokeObjectURL(url); }, 60000);
    }

    window.AdminDownload = download;

    // ZH: v4.44 下拉按鈕（擁有者 2026-10-30）。帳號頁工具列、匯入對話框、數據頁共用 ——
    //     所以放在這裡（每一頁都載），以 window.AdminDropdown 給各頁用。
    // ZH: 樣式沿用帳號選單的 .account__menu。樣式沿用帳號選單的 .account__menu。
    //     點選單項之後就收起來（項目自己的事件先跑，這裡在冒泡時才收）；
    //     點外面、按 Esc、Tab 離開也收。上下鍵在項目間移動。
    // ZH: 「點在裡面嗎」在捕獲階段先記 —— 與 admin-chrome.js 的 wireToggle 同一個理由。
    function wireDropdown(toggle, menu) {
        if (!toggle || !menu) return;
        function items() { return [].slice.call(menu.querySelectorAll('[role="menuitem"]')); }
        function setOpen(open) {
            menu.hidden = !open;
            toggle.setAttribute('aria-expanded', String(open));
            // ZH: 上一次打開時夾邊寫的 left/right 先清掉，讓 CSS 的對齊（往右／.adm-dd--left 往左）
            //     重新生效 —— 不然視窗放大之後選單還停在上次手機寬時被推過去的位置。
            menu.style.left = '';
            menu.style.right = '';
            if (!open) return;
            // ZH: 在 <dialog> 裡改用 fixed 定位，讓選單**可以超出對話框**（擁有者 2026-10-30）。
            //     對話框是 overflow-y:auto，絕對定位的選單會被它切掉、要捲才看得到；
            //     fixed 的定位基準是視窗，不受對話框的 overflow 影響。
            //     座標每次打開時現量；對話框捲動時就收起來（不然選單會停在原地跟按鈕分開）。
            // ZH: 對齊要跟 CSS 一樣：預設**右緣對齊按鈕右緣**（往左長），只有 .adm-dd--left 才從左緣往右長。
            //     原本一律寫 left = 按鈕左緣，個人對話框外部 AI 的「更多▾」在對話框右緣，
            //     選單往右長出對話框 100px、1024 寬時被螢幕切掉（2026-10-30 版面掃描）。
            var dlg = toggle.closest('dialog');
            var vw = document.documentElement.clientWidth;
            if (dlg) {
                var rc = toggle.getBoundingClientRect();
                menu.style.position = 'fixed';
                menu.style.top = Math.round(rc.bottom + 8) + 'px';
                if (toggle.closest('.adm-dd--left')) {
                    menu.style.left = Math.round(rc.left) + 'px';
                    menu.style.right = 'auto';
                } else {
                    menu.style.left = 'auto';
                    menu.style.right = Math.round(vw - rc.right) + 'px';
                }
                if (!dlg._ddScroll) {
                    dlg._ddScroll = true;
                    dlg.addEventListener('scroll', function () {
                        [].forEach.call(dlg.querySelectorAll('.adm-dd .account__menu'), function (m) {
                            m.hidden = true;
                        });
                        [].forEach.call(dlg.querySelectorAll('.adm-dd [aria-expanded="true"]'), function (b) {
                            b.setAttribute('aria-expanded', 'false');
                        });
                    });
                }
            }
            // ZH: 最後夾進視窗（左右各留 8px）。手機寬時按鈕會換行到左邊，往左長的選單
            //     就伸出螢幕左緣（組織對照表的「匯出▾」在 375 寬時 -51px）。量一次、差多少推多少；
            //     left 用算出來的值（absolute 與 fixed 都適用：getComputedStyle 給的是實際的 px）。
            var M = 8, mr = menu.getBoundingClientRect(), shift = 0;
            if (mr.right > vw - M) shift = (vw - M) - mr.right;
            if (mr.left + shift < M) shift = M - mr.left;
            if (shift) {
                menu.style.left = Math.round(parseFloat(getComputedStyle(menu).left) + shift) + 'px';
                menu.style.right = 'auto';
            }
        }
        toggle.addEventListener('click', function () { setOpen(menu.hidden); });
        toggle.addEventListener('keydown', function (ev) {
            if (ev.key === 'ArrowDown') {
                ev.preventDefault();
                setOpen(true);
                items()[0].focus();
            }
        });
        menu.addEventListener('click', function (ev) {
            if (ev.target.closest('[role="menuitem"]')) setOpen(false);
        });
        menu.addEventListener('keydown', function (ev) {
            var list = items(), i = list.indexOf(document.activeElement);
            if (ev.key === 'ArrowDown' || ev.key === 'ArrowUp') {
                ev.preventDefault();
                var n = ev.key === 'ArrowDown' ? i + 1 : i - 1;
                list[(n + list.length) % list.length].focus();
            } else if (ev.key === 'Escape') {
                // ZH: 在 <dialog> 裡時 Esc 預設會把整個對話框關掉 —— 這一下只該關選單。
                ev.preventDefault();
                ev.stopPropagation();
                setOpen(false);
                toggle.focus();
            } else if (ev.key === 'Tab') {
                setOpen(false);
            }
        });
        // ZH: 匯入對話框每開一次就重畫一次，舊的選單會離開 DOM ——
        //     掛在 document 上的監聽發現自己的選單不在了就自己拆掉，不然會越積越多。
        var inside = false;
        function onCapture(ev) {
            if (!menu.isConnected) { detach(); return; }
            inside = menu.contains(ev.target) || toggle.contains(ev.target);
        }
        function onBubble() {
            if (!menu.isConnected) { detach(); return; }
            if (!menu.hidden && !inside) setOpen(false);
        }
        function detach() {
            document.removeEventListener('click', onCapture, true);
            document.removeEventListener('click', onBubble);
        }
        document.addEventListener('click', onCapture, true);
        document.addEventListener('click', onBubble);
        toggle.addEventListener('keydown', function (ev) {
            if (ev.key === 'Escape' && !menu.hidden) {
                ev.preventDefault();      // ZH: 同上 —— 選單開著時 Esc 只關選單
                ev.stopPropagation();
                setOpen(false);
            }
        });
    }

    window.AdminDropdown = wireDropdown;

    /* ==========================================================================
     * v4.45 共用版面元件（版面整理，計畫第 3 節）
     *
     * ZH: 放在這支的理由與 AdminDownload / AdminDropdown 相同：每一頁都載它，
     *     而這幾樣東西原本是**各頁各抄一份**（分頁器有四份），抄寫會漂開。
     *     樣式在 admin.css 的「v4.45 版面整理」那一段。
     * ========================================================================== */

    /* ── 分頁器 ────────────────────────────────────────────────────────────────
     * @node AdminPager
     * ZH: 取代 people.js（帳號清單、補齊預覽、回收預覽）與 reports.js（寄信／管理動作紀錄）
     *     裡四份一模一樣的 `.adm-inline.tu-pager` 標記。四份都只差在 id 前綴。
     *
     * ZH: 用法（頁碼一律**從 1 算**，那是畫面上顯示的數字）：
     *       box.innerHTML = '<table>…</table>' + AdminPager.html({ id: 'mail', page: 2, pages: 5, total: 47 });
     *       AdminPager.wire({ id: 'mail', onGo: function (p, which) { …重畫第 p 頁… } });
     *     或一步到位（容器裡只放分頁器時）：
     *       AdminPager.render(el, { id, page, pages | perPage, total, onGo, focus });
     *
     * ZH: 產生的按鈕 id 是 `<id>-prev` / `<id>-next` —— 與四份舊碼的 id 相同
     *     （pp-、tu-、rc-、mail-、audit-），呼叫端換過來時不必改其他地方。
     *
     * ZH: 🔴 換頁通常是整段 innerHTML 重畫，原本按的那顆鈕就不在了，焦點掉回 <body>
     *     —— 用鍵盤的人得從頁首重新 Tab 過來（reports.js 原本就為此補過一次）。
     *     所以 onGo 的第二個參數告訴你是哪一顆（'prev' / 'next'），重畫後把它傳回
     *     wire / render 的 `focus`，焦點就回到同一顆；那顆到頭變成 disabled 時改放另一顆。
     *
     * ZH: 只有一頁時：有給 total 就只顯示「共 N 筆」（計畫：分頁器一直顯示總筆數），
     *     沒給 total 就回空字串（與舊碼「一頁就不畫」相同）。
     * ──────────────────────────────────────────────────────────────────────── */
    function pagerPages(o) {
        if (o.pages != null) return Math.max(1, o.pages | 0);
        if (o.perPage) return Math.max(1, Math.ceil((o.total || 0) / o.perPage));
        return 1;
    }

    function pagerHtml(o) {
        var pages = pagerPages(o);
        var at = Math.min(pages, Math.max(1, o.page | 0 || 1));
        var hasTotal = o.total != null;
        var id = esc(o.id);
        if (pages <= 1) {
            if (!hasTotal) return '';
            return '<div class="adm-pager" id="' + id + '-pager"><span class="adm-pager__at">'
                + esc(T('adm_pg_total', '共 {n} 筆').replace('{n}', o.total)) + '</span></div>';
        }
        // ZH: 「第 a / b 頁（共 N 筆）」—— 沿用既有的 pf_pg_of + rp_pg_total，
        //     與舊的四份分頁器同一句話，換過來畫面上的字不變。
        var label = T('pf_pg_of', '第 {a} / {b} 頁').replace('{a}', at).replace('{b}', pages)
            + (hasTotal ? T('rp_pg_total', '（共 {n} 筆）').replace('{n}', o.total) : '');
        return '<nav class="adm-pager" id="' + id + '-pager" aria-label="'
            + esc(T('adm_pg_nav', '分頁')) + '">'
            + '<button class="btn--quiet" type="button" id="' + id + '-prev"'
            + (at <= 1 ? ' disabled' : '') + '><span aria-hidden="true">‹</span> '
            + '<span data-i18n="pf_pg_prev">' + esc(T('pf_pg_prev', '上一頁')) + '</span></button>'
            + '<span class="adm-pager__at">' + esc(label) + '</span>'
            + '<button class="btn--quiet" type="button" id="' + id + '-next"'
            + (at >= pages ? ' disabled' : '') + '>'
            + '<span data-i18n="pf_pg_next">' + esc(T('pf_pg_next', '下一頁')) + '</span>'
            + ' <span aria-hidden="true">›</span></button>'
            + '</nav>';
    }

    function pagerWire(o) {
        var prev = document.getElementById(o.id + '-prev');
        var next = document.getElementById(o.id + '-next');
        // ZH: 目前頁碼從畫出來的標記讀不到，所以由呼叫端給（與 html() 同一個 o 即可）。
        var at = Math.max(1, o.page | 0 || 1);
        if (prev && o.onGo) prev.addEventListener('click', function () { o.onGo(at - 1, 'prev'); });
        if (next && o.onGo) next.addEventListener('click', function () { o.onGo(at + 1, 'next'); });
        if (o.focus) {
            var el = o.focus === 'prev' ? prev : next;
            if (el && el.disabled) el = (el === prev) ? next : prev;
            if (el && !el.disabled) el.focus();
        }
    }

    window.AdminPager = {
        html: pagerHtml,
        wire: pagerWire,
        render: function (el, o) {
            if (typeof el === 'string') el = document.getElementById(el);
            if (!el) return;
            el.innerHTML = pagerHtml(o);
            pagerWire(o);
        },
    };

    /* ── 收合區塊 ──────────────────────────────────────────────────────────────
     * @node AdminFold
     * ZH: 原生 <details class="adm-fold">。收起來時標題列上看得到數量（setCount），
     *     第一次點開才載入（onFirstOpen）—— 訊息頁的寄信紀錄／管理動作紀錄就是這樣用。
     *
     * ZH: 標記（HTML 裡直接寫，或用 AdminFold.html() 產生）：
     *       <details class="adm-fold adm-sec" data-fold="msg-mail">
     *         <summary class="adm-fold__head">
     *           <h2 class="adm-head__title" id="h-mail">寄信紀錄</h2>
     *           <span class="adm-head__count" data-fold-count></span>
     *         </summary>
     *         <div class="adm-fold__body" id="mail">…</div>
     *       </details>
     *     ⚠ <summary> 裡只放標題與數量，**不放按鈕** —— 按鈕要在收起來時也按得到，
     *       而收起來的 <details> 只剩 summary；把動作放在 summary 裡又會跟「點一下展開」搶。
     *
     * ZH: 開合狀態記在記憶體（以 data-fold 為鍵）。總覽每 10 秒整段重畫，
     *     沒有這一層的話使用者剛點開的名單 10 秒後就被收回去（計畫第 5 節第 4 步點名的事）。
     *     重畫時用 AdminFold.html({ id, … }) 產生，它會照記住的狀態帶上 open。
     *     加 `data-fold-persist` 的才另外存 localStorage（跨次造訪也記得）；
     *     存不了（私密視窗、被擋）就只記這一次 —— 不影響功能。
     *
     * ZH: 'toggle' 事件不冒泡，但**捕獲階段**照樣經過 document，所以一個監聽就涵蓋
     *     之後才長出來的每一個收合區（不必每次重畫都重新接）。
     * ──────────────────────────────────────────────────────────────────────── */
    var FOLD_LS = 'adm_fold:';
    var _foldOpen = {};

    function foldRemembered(id) {
        if (!id) return null;
        if (Object.prototype.hasOwnProperty.call(_foldOpen, id)) return _foldOpen[id];
        try {
            var v = localStorage.getItem(FOLD_LS + id);
            if (v === '1' || v === '0') return v === '1';
        } catch (e) { /* ZH: 存取被擋就當作沒記過 */ }
        return null;
    }

    document.addEventListener('toggle', function (ev) {
        var d = ev.target;
        if (!d || !d.classList || !d.classList.contains('adm-fold')) return;
        var id = d.getAttribute('data-fold');
        if (!id) return;
        _foldOpen[id] = d.open;
        if (d.hasAttribute('data-fold-persist')) {
            try { localStorage.setItem(FOLD_LS + id, d.open ? '1' : '0'); } catch (e) { /* 同上 */ }
        }
    }, true);

    // ZH: o = { id, key, zh, tag:'h2'|'h3', titleId, count, body, open, persist, cls }
    //     標題用 key + zh（與導覽表同一個寫法，翻譯檢查掃得到），切換語言時靠 data-i18n 重畫。
    //     body 是**已經組好的 HTML**（呼叫端負責跳脫），其餘欄位這裡跳脫。
    function foldHtml(o) {
        var mem = foldRemembered(o.id);
        var open = mem == null ? !!o.open : mem;
        var tag = o.tag === 'h3' ? 'h3' : 'h2';
        return '<details class="adm-fold' + (o.cls ? ' ' + esc(o.cls) : '') + '"'
            + (o.id ? ' data-fold="' + esc(o.id) + '"' : '')
            + (o.persist ? ' data-fold-persist' : '')
            + (open ? ' open' : '') + '>'
            + '<summary class="adm-fold__head">'
            + '<' + tag + ' class="adm-head__title"' + (o.titleId ? ' id="' + esc(o.titleId) + '"' : '')
            + (o.key ? ' data-i18n="' + esc(o.key) + '"' : '') + '>'
            + esc(o.key ? T(o.key, o.zh) : (o.zh || '')) + '</' + tag + '>'
            + '<span class="adm-head__count" data-fold-count>' + (o.count == null ? '' : esc(o.count)) + '</span>'
            + '</summary>'
            + '<div class="adm-fold__body">' + (o.body || '') + '</div>'
            + '</details>';
    }

    // ZH: 接上一個收合區。o = { onFirstOpen(body, el), onToggle(open, el) }
    //     onFirstOpen 只跑一次；它回傳的 Promise 若失敗，下次點開會**再試一次** ——
    //     載入失敗後永遠停在錯誤訊息、而且重新點開也沒用，那看起來像壞掉。
    //     回傳一個控制物件：{ el, body, open(), close(), isOpen(), setCount(text) }。
    function foldWire(el, o) {
        if (typeof el === 'string') el = document.getElementById(el);
        if (!el) return null;
        o = o || {};
        var body = el.querySelector('.adm-fold__body') || el;
        var loaded = false;

        function first() {
            if (loaded || !o.onFirstOpen) return;
            loaded = true;
            var r;
            try { r = o.onFirstOpen(body, el); } catch (e) { loaded = false; throw e; }
            if (r && typeof r.then === 'function') {
                r.then(null, function () { loaded = false; });
            }
        }
        el.addEventListener('toggle', function () {
            if (el.open) first();
            if (o.onToggle) o.onToggle(el.open, el);
        });

        // ZH: 記住的狀態優先於 HTML 寫死的 open（換頁回來、或重畫之後要維持使用者剛才的選擇）。
        var mem = foldRemembered(el.getAttribute('data-fold'));
        if (mem != null && mem !== el.open) el.open = mem;   // ZH: 會觸發 toggle → first()
        else if (el.open) first();

        return {
            el: el,
            body: body,
            open: function () { el.open = true; },
            close: function () { el.open = false; },
            isOpen: function () { return el.open; },
            // ZH: 收起來時標題列上顯示的數字／摘要。空字串＝不顯示（.adm-head__count:empty）。
            setCount: function (text) {
                var c = el.querySelector('[data-fold-count]');
                if (c) c.textContent = text == null ? '' : String(text);
            },
        };
    }

    window.AdminFold = {
        html: foldHtml,
        wire: foldWire,
        // ZH: 不另外提供「用 id 查記住的狀態」—— AdminFold.html() 畫的時候已經還原了，
        //     沒有任何頁需要自己查；單個收合區開著沒有，問 wire() 回傳的 isOpen()。
    };

    /* ── 「更多▾」選單 ─────────────────────────────────────────────────────────
     * @node AdminMenu
     * ZH: 區塊標題列右半「最多兩顆按鈕＋更多▾」的那個 ▾。外觀與行為就是 AdminDropdown，
     *     這裡只負責產生標記，並強制一條規則：**危險項一律排到最底下**（紅字、上面一條線，
     *     樣式見 admin.css 的 .adm-menu__danger）。靠每個呼叫端自己記得排，總有一處會漏。
     *
     * ZH: 用法：
     *       head.innerHTML += AdminMenu.html({ id: 'org-more', items: [
     *           { id: 'org-alma',   key: <翻譯 key>, zh: '用 Alma 重建' },
     *           { id: 'org-import', key: <翻譯 key>, zh: '匯入' },
     *           { id: 'org-wipe',   key: <翻譯 key>, zh: '清空', danger: true },
     *       ] });
     *     ⚠ 範例刻意不寫真的 key 字面值 —— check_i18n.py 連註解一起掃，
     *       寫了不存在的 key 會被報成「有人用但字典沒有」。
     *       AdminMenu.wire('org-more');            // ← 等同 AdminDropdown(toggle, menu)
     *       $('org-alma').addEventListener('click', …);   // 項目的事件照舊各自接
     *     項目也可以是 { sep: true }（分組線）或 { label: true, key, zh }（組名）。
     *     label 不給時按鈕寫「更多」；要具名的下拉（匯出▾）就給 { key, zh }。
     *     left: true → 選單往左對齊（按鈕在容器左緣時，見 .adm-dd--left）。
     * ──────────────────────────────────────────────────────────────────────── */
    function menuHtml(o) {
        var items = (o.items || []).slice();
        // ZH: 穩定排序：危險項移到最後，其餘保持原順序。
        var safe = items.filter(function (it) { return !it.danger; });
        var bad = items.filter(function (it) { return it.danger; });
        var lab = o.label || { key: 'adm_more', zh: '更多' };
        var id = esc(o.id);
        return '<div class="account adm-dd' + (o.left ? ' adm-dd--left' : '') + '">'
            + '<button class="btn btn--minor" type="button" id="' + id + '"'
            + ' aria-haspopup="menu" aria-expanded="false" aria-controls="' + id + '-menu">'
            + '<span data-i18n="' + esc(lab.key) + '">' + esc(T(lab.key, lab.zh)) + '</span>'
            + ' <span class="account__caret" aria-hidden="true">▾</span></button>'
            + '<div class="account__menu" role="menu" hidden id="' + id + '-menu">'
            + safe.concat(bad).map(function (it) {
                if (it.sep) return '<div class="adm-menu__sep" role="separator"></div>';
                if (it.label) {
                    return '<div class="adm-menu__label" role="presentation" data-i18n="' + esc(it.key) + '">'
                        + esc(T(it.key, it.zh)) + '</div>';
                }
                return '<button type="button" role="menuitem"'
                    + (it.id ? ' id="' + esc(it.id) + '"' : '')
                    + (it.danger ? ' class="adm-menu__danger"' : '')
                    + (it.hidden ? ' hidden' : '')
                    + ' data-i18n="' + esc(it.key) + '">' + esc(T(it.key, it.zh)) + '</button>';
            }).join('')
            + '</div></div>';
    }

    window.AdminMenu = {
        html: menuHtml,
        wire: function (id) {
            wireDropdown(document.getElementById(id), document.getElementById(id + '-menu'));
        },
    };

    /* ── 編輯中標示 ────────────────────────────────────────────────────────────
     * @node AdminEditMark
     * ZH: 平台設定原本有 6 句「目前是唯讀」—— 唯讀是平常的狀態，每段都講一次等於沒講。
     *     改成**只標例外**：進入編輯時區塊左側一條色條（.adm-sec.is-editing），
     *     標題旁一顆「編輯中」藥丸；離開編輯就拿掉。
     * ZH: 用法：AdminEditMark(sectionEl 或 id, true / false)。
     *     藥丸放在標題後面（.adm-head__title／h2／h3），找不到標題就放在標題列最後。
     * ──────────────────────────────────────────────────────────────────────── */
    function editMark(sec, on) {
        if (typeof sec === 'string') sec = document.getElementById(sec);
        if (!sec) return;
        sec.classList.toggle('is-editing', !!on);
        var head = sec.querySelector('.adm-head__what') || sec.querySelector('.adm-head')
            || sec.querySelector('.adm-sec__head') || sec;
        var pill = head.querySelector('.adm-pill--editing');
        if (!on) { if (pill) pill.remove(); return; }
        if (pill) return;
        pill = document.createElement('span');
        pill.className = 'adm-pill adm-pill--editing';
        pill.setAttribute('data-i18n', 'adm_editing');
        pill.textContent = T('adm_editing', '編輯中');
        var title = head.querySelector('.adm-head__title, h2, h3');
        if (title && title.parentNode === head) title.insertAdjacentElement('afterend', pill);
        else head.appendChild(pill);
    }

    window.AdminEditMark = editMark;

    window.AdminMe = function () { return _me; };

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
