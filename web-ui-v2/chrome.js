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
            // ZH: 這個 aria-label 原本寫死中文——**每一頁都是**，而只有用螢幕閱讀器
            //     的英文使用者會遇到，所以沒有人會回報。
            nav.setAttribute('aria-label', T('nav_aria', '主要'));
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
        myai.setAttribute('data-i18n', 'nav_myai');
        myai.textContent = T('nav_myai', 'MYAI');
        if (page === 'index.html' || page === '') myai.setAttribute('aria-current', 'page');
        nav.appendChild(myai);

        var lab = document.createElement('a');
        lab.href = 'lab.html';
        lab.setAttribute('data-i18n', 'nav_lab');
        lab.textContent = T('nav_lab', '程式實驗室');
        // ZH: 底色只給「目前所在頁」（擁有者裁定）。
        if (page === 'lab.html') lab.setAttribute('aria-current', 'page');
        nav.appendChild(lab);

        // ZH: v3.6 「我的訓練」。**這是三頁裡最該在導覽上的一個** —— 使用者送出之後
        //     關掉分頁，就只剩導覽找得回那張單（在這之前是完全找不回來）。
        var jl = document.createElement('a');
        jl.href = 'jobs.html';
        jl.setAttribute('data-i18n', 'nav_jobs');
        jl.textContent = T('nav_jobs', '我的訓練');
        // ZH: 訓練頁歸在「我的訓練」這一組（送出與查看是同一件事的兩端）
        if (page === 'jobs.html' || page === 'train.html') jl.setAttribute('aria-current', 'page');
        nav.appendChild(jl);

        // ZH: v3.6 「我的資料集」。放進主導覽而不是埋在某一頁的連結裡，
        //     因為使用者會需要它的時機是「傳不上去了」——那時他不會記得
        //     從哪一頁進得去。訓練頁與這一頁是互相到得了的一組。
        var ds = document.createElement('a');
        ds.href = 'datasets.html';
        ds.setAttribute('data-i18n', 'nav_datasets');
        ds.textContent = T('nav_datasets', '我的資料集');
        if (page === 'datasets.html') ds.setAttribute('aria-current', 'page');
        nav.appendChild(ds);

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
        toggle.setAttribute('data-i18n', 'acct_loading');
        toggle.textContent = T('acct_loading', '載入中…');
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
        // ZH: Esc 關閉——只能用滑鼠關的選單對鍵盤使用者是陷阱。
        document.addEventListener('keydown', function (ev) {
            if (ev.key === 'Escape') close();
        });
    }

    // ZH: 取文案。字典裡沒有就用 fallback（＝原本的中文），**不清空**。
    function T(key, fallback) {
        return (window.Prefs && window.Prefs.t(key, fallback)) || fallback;
    }
    function roleLabel(role) {
        return T('role_' + role, { student: '學生', teacher: '教師', admin: '管理員' }[role] || role || '');
    }

    function item(el, key, fallback) {
        el.setAttribute('role', 'menuitem');
        el.setAttribute('data-i18n', key);
        el.textContent = T(key, fallback);
        return el;
    }

    // ── 顯示設定（字級 / 語言）─────────────────────────────────────────
    // ZH: 放在帳號選單裡而不是另開設定頁：只有兩個設定，開一頁的成本遠大於收益，
    //     而且這裡正是「跟你這個帳號有關的東西」該在的位置。
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

        function stepBtn(delta, key, fb, label) {
            var b = document.createElement('button');
            b.type = 'button';
            b.textContent = label;
            b.setAttribute('data-i18n-aria', key);
            b.setAttribute('aria-label', T(key, fb));
            b.addEventListener('click', function (ev) {
                ev.stopPropagation();               // ZH: 別讓它把選單關掉
                var cur = window.Prefs.get().ui_font_scale;
                savePrefs({ ui_font_scale: cur + delta });
            });
            return b;
        }
        group.appendChild(stepBtn(-10, 'prefs_font_smaller', '縮小字級', 'A−'));
        // ZH: 中間顯示目前值，並兼任「還原 100%」——數字本身可點，省一顆按鈕。
        var reset = document.createElement('button');
        reset.type = 'button';
        reset.className = 'account__seg-reset';
        reset.setAttribute('data-i18n-aria', 'prefs_font_reset');
        reset.setAttribute('aria-label', T('prefs_font_reset', '還原為 100%'));
        reset.appendChild(out);
        reset.addEventListener('click', function (ev) {
            ev.stopPropagation();
            savePrefs({ ui_font_scale: 100 });
        });
        group.appendChild(reset);
        group.appendChild(stepBtn(10, 'prefs_font_bigger', '放大字級', 'A+'));
        fontRow.appendChild(group);
        box.appendChild(fontRow);

        // 語言
        var langRow = document.createElement('div');
        langRow.className = 'account__prefs-row';
        var langLabel = document.createElement('span');
        langLabel.setAttribute('data-i18n', 'prefs_lang');
        langLabel.textContent = T('prefs_lang', '語言');
        langRow.appendChild(langLabel);
        var langGroup = document.createElement('div');
        langGroup.className = 'account__seg';
        [['zh', '中文'], ['en', 'English']].forEach(function (pair) {
            var b = document.createElement('button');
            b.type = 'button';
            b.textContent = pair[1];
            b.dataset.lang = pair[0];
            b.addEventListener('click', function (ev) {
                ev.stopPropagation();
                savePrefs({ ui_lang: pair[0] });
            });
            langGroup.appendChild(b);
        });
        langRow.appendChild(langGroup);
        box.appendChild(langRow);

        // 顏色
        //
        // ZH: 原本常駐在每一頁的頂部列上。搬進來的理由跟字級／語言一樣：
        //     它是「跟這個帳號有關的顯示設定」，三個放在一起才找得到。
        //
        // ZH: ⚠ 登入頁**不載 chrome.js**，所以它那顆色系切換要留在原地 ——
        //     那一頁沒有這個選單，拿掉就沒有地方可以改了。
        //
        // ZH: 按鈕不用自己接事件：prefs.js 有一個 document 層的委派監聽
        //     （closest('[data-set-theme]')），搬到哪裡都會生效；
        //     aria-pressed 也由它在 prefs:applied 時統一重畫。
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
        [['yellow', 'theme_yellow', '\u9ec3'],
         ['blue', 'theme_blue', '\u85cd']].forEach(function (t) {
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

        var warn = document.createElement('div');
        warn.className = 'account__prefs-warn';
        // ZH: 警告是**模組狀態**不是元素狀態。改設定會觸發 prefs:applied → 整個選單重畫，
        //     若把訊息寫進當時捕捉到的節點，那個節點已經脫離 DOM，訊息就永遠看不到。
        //     （實測踩到：畫面正確地沒回滾，但提示不見了。）
        warn.textContent = _prefsWarn;
        warn.hidden = !_prefsWarn;
        box.appendChild(warn);

        syncPrefsUI(box);
        return box;
    }

    // ZH: 「上次存回帳號失敗」的訊息。空字串＝沒有問題。
    var _prefsWarn = '';

    function syncPrefsUI(box) {
        var st = window.Prefs.get();
        var v = box.querySelector('.account__seg-value');
        if (v) v.textContent = st.ui_font_scale + '%';
        box.querySelectorAll('[data-lang]').forEach(function (b) {
            b.setAttribute('aria-pressed', String(b.dataset.lang === st.ui_lang));
        });
    }

    async function savePrefs(patch) {
        var ok = await window.Prefs.set(patch);   // ← 這裡就會觸發重畫
        // ZH: 存不回帳號時**不回滾畫面**——他看到的就是他選的。
        //     但要講清楚「這台機器有效、沒存回帳號」，否則換機器發現設定不見會很困惑。
        _prefsWarn = ok ? '' : T('prefs_saved_local_only',
            '已在這台機器上套用，但沒有存回帳號（稍後再試）。');
        // ZH: 重畫已經發生過了，所以往**現在活著的**節點寫，不要用捕捉到的舊參照。
        var live = _menu && _menu.querySelector('.account__prefs-warn');
        if (live) {
            live.textContent = _prefsWarn;
            live.hidden = !_prefsWarn;
        }
    }

    // ZH: 快取 /auth/me 的結果。切換語言時要重畫選單——
    //     像「學生 · a@b.c」這種**組合字串**不是 data-i18n 元素，
    //     prefs.js 的字典掃描換不掉它，只會留下半中半英的選單。
    //     重畫而不是重打 API：語言切換不該產生網路請求。
    var _me = null;
    var _toggle = null, _menu = null;

    document.addEventListener('prefs:applied', function () {
        if (_toggle && _menu) render(_toggle, _menu, _me);
    });

    // ZH: 取自己的身分。**「請求失敗」與「沒登入」必須分開**——
    //     原本兩者都落到 me=null，於是網路抖一下就宣稱使用者「未登入」，
    //     而且偏好（字級／語言／色系）也不會同步，畫面停在預設值。
    //     實測抓到：同樣的頁面重覆載入，偶爾出現「未登入」而 /auth/me 直打是 200。
    //     401/403 才是真的沒登入；其餘一律視為暫時失敗，重試一次。
    async function fetchMe(tries) {
        try {
            var r = await fetch(API + '/auth/me', { credentials: 'include',
                headers: Object.assign({ Accept: 'application/json' }, authHeaders()) });
            if (r.ok) return { me: await r.json() };
            if (r.status === 401 || r.status === 403) return { me: null, anon: true };
            throw new Error('HTTP ' + r.status);
        } catch (e) {
            if ((tries || 0) < 1) {
                await new Promise(function (rs) { setTimeout(rs, 600); });
                return fetchMe((tries || 0) + 1);
            }
            // ZH: 重試後仍失敗 —— **不要說「未登入」**，那是另一回事。
            return { me: null, anon: false, error: String(e && e.message || e) };
        }
    }

    async function fillAccount(toggle, menu) {
        _toggle = toggle; _menu = menu;
        var res = await fetchMe(0);
        var me = res.me;
        _anon = res.anon !== false;      // 只有明確 401/403 才當成未登入

        // ZH: 偏好跟帳號走。這裡順便對帳——**不要再打一次 /auth/me**。
        //     ⚠ syncFrom 會觸發 prefs:applied → render()，所以要先存 _me。
        _me = me;
        if (me && window.Prefs) window.Prefs.syncFrom(me);
        render(toggle, menu, me);
    }

    // ZH: true = 後端明確說沒登入；false = 只是這次拿不到（網路／5xx）。
    var _anon = true;

    function render(toggle, menu, me) {
        if (!me && !_anon) {
            // ZH: 拿不到身分**不等於**沒登入。說「未登入」會讓已登入的人以為被登出了，
            //     還會誘導他去點「前往登入」——那是錯的去處。
            toggle.removeAttribute('data-i18n');
            toggle.textContent = T('acct_unavailable', '暫時讀不到');
            menu.textContent = '';
            var again = document.createElement('button');
            again.type = 'button';
            again.addEventListener('click', function (ev) {
                ev.stopPropagation();
                fillAccount(toggle, menu);
            });
            menu.appendChild(item(again, 'btn_retry', '重試'));
            menu.appendChild(prefsSection());
            return;
        }
        if (!me) {
            // ZH: 取不到身分就不要假裝有人登入。給的是「去登入」而不是空選單。
            toggle.setAttribute('data-i18n', 'acct_anon');
            toggle.textContent = T('acct_anon', '未登入');
            menu.textContent = '';
            var go = document.createElement('a');
            go.href = 'login.html';
            menu.appendChild(item(go, 'acct_go_login', '前往登入'));
            menu.appendChild(prefsSection());       // ZH: 沒登入也要能調字級／語言
            return;
        }

        toggle.textContent = '';
        var name = document.createElement('span');
        name.className = 'account__name';
        name.textContent = me.username || T('acct_unknown', '（不明）');
        toggle.appendChild(name);
        var caret = document.createElement('span');
        caret.className = 'account__caret';
        caret.setAttribute('aria-hidden', 'true');
        caret.textContent = '▾';
        toggle.appendChild(caret);
        toggle.removeAttribute('data-i18n');    // ZH: 這裡放的是帳號名，不是可翻譯文案
        toggle.setAttribute('aria-label', T('acct_menu', '帳號選單') + '：' + (me.username || ''));

        menu.textContent = '';

        // 身分（唯讀）
        var head = document.createElement('div');
        head.className = 'account__id';
        var who = document.createElement('div');
        who.className = 'account__id-name';
        who.textContent = me.username || T('acct_unknown', '（不明）');
        head.appendChild(who);
        var sub = document.createElement('div');
        sub.className = 'account__id-sub';
        // ⚠ ZH: SSO 使用者沒有 email 時後端會給 `<學號>@unknown`（routers/sso.py），
        //     顯示出來像壞掉的資料。那種就只顯示身分。
        var mail = (me.email || '');
        sub.textContent = /@unknown$/.test(mail) || !mail
            ? roleLabel(me.role)
            : roleLabel(me.role) + ' · ' + mail;
        head.appendChild(sub);
        menu.appendChild(head);

        var usage = document.createElement('a');
        usage.href = 'usage.html';
        menu.appendChild(item(usage, 'acct_usage', '使用量明細'));

        var report = document.createElement('a');
        report.href = 'report.html';
        menu.appendChild(item(report, 'acct_report', '問題回報'));

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
            menu.appendChild(item(admin, 'acct_admin', '管理介面'));
        }

        menu.appendChild(prefsSection());

        var out = document.createElement('button');
        out.type = 'button';
        out.className = 'account__logout';
        out.addEventListener('click', logout);
        menu.appendChild(item(out, 'acct_logout', '登出'));
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
