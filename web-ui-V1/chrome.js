/* ==========================================================================
 * ZH: SSO 回來時把 token 收下（v3.9）
 *
 * ZH: 學校 SSO 驗證完之後，後端 302 回 `/V1/?sso_token=...`。
 *     那個 token **必須進 sessionStorage** —— 後端同時設的 `ai_hud_token`
 *     cookie 是 HttpOnly（給 /code/ 的 nginx auth_request 用），JS 讀不到，
 *     所有 fetch 的 Authorization 都是從 sessionStorage 拿的。
 *
 * ZH: 🔴 這一段在 V1 一直不存在 —— SSO 原本 302 到 `/train/`，而 nginx 把
 *     `/train/` 導到 V0，V0 的 setupSSOLogin() 接住了它。於是用 SSO 登入的人
 *     會落在**舊介面**，而且沒有任何錯誤訊息。2026-08-29 改成導回 V1，
 *     這一段就是 V1 這邊接住它的地方。
 *
 * ZH: ⚠️ 位置很重要：要在**任何 fetch 之前**跑完。所以放在檔案最上面、
 *     在其他 IIFE 之前 —— chrome.js 是同步 script，這裡執行完才輪到
 *     DOMContentLoaded 上的那些請求。
 *
 * ZH: ⚠️ 收下之後要把參數從網址上拿掉：token 留在網址列會進瀏覽歷史，
 *     也會跟著 Referer 送給外部連結。只拿掉 sso_token，其他查詢參數留著
 *     （`?state=` 這種除錯參數還有人在用）。
 * ========================================================================== */
(function () {
    'use strict';
    try {
        var url = new URL(window.location.href);
        var t = url.searchParams.get('sso_token');
        if (!t) return;
        sessionStorage.setItem('ai_hud_token', t);
        url.searchParams.delete('sso_token');
        window.history.replaceState({}, document.title,
            url.pathname + (url.searchParams.toString() ? '?' + url.searchParams : '') + url.hash);
    } catch (e) {
        // ZH: 這裡壞掉不能讓整頁跟著壞 —— 最壞的情況是使用者被當成未登入，
        //     而登入頁本來就在那裡。靜默失敗好過白畫面。
    }
})();

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
 * ZH: 為什麼包 window.fetch 而不是逐一改：使用者端有 **34 個** fetch 呼叫
 *     散在 15 個檔案，逐一改就是 34 個會漏的地方，而且新寫的程式還會再漏。
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

        // ── 導覽：首頁 + 三個分類下拉（v3.9，擁有者裁定 2026-08-30）
        //
        // ZH: 原本是四個並排的連結：MYAI · 程式實驗室 · 我的訓練 · 我的資料集。
        //     改成下拉的理由 —— 首頁已經用「想做點什麼／看我的東西／不知道怎麼做」
        //     分好三組，導覽列卻是**另一套分法**。同一個平台兩種心智模型，
        //     使用者得自己在腦子裡對應，而那個對應沒有人教他。
        //
        // ZH: 「首頁」是新增的第一項（擁有者裁定）。原本第一項是 MYAI，
        //     而它其實連到首頁 —— **名字與去處不一致**，點下去會意外。
        var nav = bar.querySelector('.topnav');
        if (!nav) {
            nav = document.createElement('nav');
            nav.className = 'topnav';
            // ZH: 這個 aria-label 原本寫死中文——**每一頁都是**，而只有用螢幕閱讀器
            //     的英文使用者會遇到，所以沒有人會回報。
            nav.setAttribute('aria-label', T('nav_aria', '主要'));
            // ZH: 插在色系切換**之前**。色系切換是開發期的東西（Decision Log #16，
            //     上線擇一後整塊移除），順序要讓「移除它之後仍然正確」。
            var theme = bar.querySelector('.theme-switch');
            if (theme) bar.insertBefore(nav, theme); else bar.appendChild(nav);
        }
        nav.textContent = '';
        // ZH: 重建導覽時把上一輪的關閉函式丟掉 —— 不清的話每重建一次就多累積
        //     一組指向已移除節點的閉包（不會壞，但會無限長）。
        MENUS.length = 0;

        // ZH: ⚠ 這張表是**首頁分組卡片的鏡像**。改了首頁的分類就要改這裡；
        //     兩邊分歧比一開始就不分組更糟。
        var GROUPS = [
            {
                key: 'grp_do_t', zh: '想做點什麼',
                // ZH: 停在這些頁時，這一組的鈕要標成「你在這裡」。
                // ZH: train.html 沒有自己的選單項（它是從 gpu.html 進去的第二條路），
                //     但停在那裡時仍然算在這一組 —— 不然那一頁的導覽列會完全沒有落點。
                // ZH: v3.6 曾把 train.html 跟 jobs.html 歸在一起（「送出與查看是
                //     同一件事的兩端」）。那是導覽只有平鋪連結時的權宜；
                //     現在的判準是**使用者帶著什麼念頭來**，送出訓練是「想做點什麼」。
                pages: ['myai.html', 'gpu.html', 'train.html', 'lab.html'],
                items: [
                    // ZH: v3.9 有自己的頁了（擁有者裁定 2026-08-30）。
                    //     在那之前它連到首頁 —— 而「首頁」就在它左邊，
                    //     兩個選單項同一個去處，點下去會意外。
                    // ZH: 「按了被擋」的處理跟著搬過去了：myai.html 是現在唯一有
                    //     #handoff 的地方，那段邏輯仍然只有一份。
                    { href: 'myai.html', key: 'grp_ai_t', zh: '體驗大模型' },
                    { href: 'gpu.html', key: 'grp_go_t', zh: '體驗現有模型訓練' },
                    { href: 'lab.html', key: 'nav_lab', zh: '程式實驗室' }
                ]
            },
            {
                key: 'grp_mine_t', zh: '看我的東西',
                pages: ['jobs.html', 'datasets.html', 'usage.html'],
                items: [
                    { href: 'jobs.html', key: 'grp_jobs_t', zh: '我的訓練進度' },
                    { href: 'datasets.html', key: 'grp_ds_t', zh: '我的歷史資料訓練' },
                    { href: 'usage.html', key: 'acct_usage', zh: '使用量明細' }
                ]
            },
            {
                key: 'grp_help_t', zh: '不知道怎麼做',
                pages: ['docs.html', 'report.html'],
                items: [
                    // ZH: 文件庫入口在沒有內容前不出現。規則只寫在 docs-entry.js，
                    //     這裡只放一個槽位（hidden + data-docs-entry）交給它決定。
                    { href: 'docs.html', key: 'entry_docs_title', zh: '看別人做過什麼', docs: true },
                    { href: 'report.html', key: 'acct_report', zh: '問題回報' }
                ]
            }
        ];

        var home = document.createElement('a');
        home.href = 'index.html';
        home.setAttribute('data-i18n', 'nav_home');
        home.textContent = T('nav_home', '首頁');
        if (page === 'index.html' || page === '') home.setAttribute('aria-current', 'page');
        nav.appendChild(home);

        GROUPS.forEach(function (g, gi) {
            var box = document.createElement('div');
            box.className = 'navmenu';
            // ZH: 🔴 最後一組的選單要往**左**長。導覽列靠右，最右邊那顆鈕
            //     底下的選單若照預設往右長，會超出視窗右緣並撐出橫向捲軸
            //     （實測 710px 寬時就會發生）。
            // ZH: ⚠ 用「是不是最後一組」判斷，不要寫成 CSS 的 :last-child ——
            //     日後在導覽尾端加任何東西，那個選擇器會安靜地不再命中。
            if (gi === GROUPS.length - 1) box.className += ' navmenu--right';
            // ZH: 目前頁在這一組裡就把鈕標起來。
            // ZH: ⚠ 用 class 不用 aria-current —— 這顆鈕**不是**目前那一頁，
            //     它只是包著那一頁的選單。真正的 aria-current 掛在下面的連結上。
            if (g.pages.indexOf(page) >= 0) box.className += ' is-current';

            var btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'navmenu__toggle';
            btn.setAttribute('aria-haspopup', 'menu');
            btn.setAttribute('aria-expanded', 'false');
            btn.setAttribute('data-i18n', g.key);
            btn.textContent = T(g.key, g.zh);

            var menu = document.createElement('div');
            menu.className = 'navmenu__menu';
            menu.setAttribute('role', 'menu');
            menu.hidden = true;
            g.items.forEach(function (it) {
                var a = document.createElement('a');
                a.href = it.href;
                a.setAttribute('role', 'menuitem');
                a.setAttribute('data-i18n', it.key);
                a.textContent = T(it.key, it.zh);
                if (it.href === page) a.setAttribute('aria-current', 'page');
                if (it.docs) { a.setAttribute('data-docs-entry', ''); a.hidden = true; }
                menu.appendChild(a);
            });

            box.appendChild(btn);
            box.appendChild(menu);
            nav.appendChild(box);
            wireToggle(btn, menu);
        });

        // ZH: 文件庫那一項是這裡動態建的，**比 docs-entry.js 的第一次掃描還晚**。
        //     這一行把它已經知道的決定再套一次；規則本身仍然只有那一份實作。
        DocsEntry.apply(nav);

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

        // ZH: 中／英切換。**放在帳號鈕的左邊**（擁有者裁定）——
        //     切語言是當下就想做的事，不該先開一層選單。
        //     字級與顏色留在選單裡：那兩個設定一次就好。
        // ZH: 不接任何事件 —— prefs.js 有 document 層的委派（data-set-lang），
        //     aria-pressed 也由它在 applyLang 統一重畫。
        var langBox = document.createElement('div');
        langBox.innerHTML = '<div class="lang-switch"><button type="button" data-set-lang="zh" aria-pressed="true" data-i18n-aria="prefs_lang_zh" aria-label="切換成中文">中</button><button type="button" data-set-lang="en" aria-pressed="false" data-i18n-aria="prefs_lang_en" aria-label="切換成英文">EN</button></div>';
        bar.appendChild(langBox.firstChild);

        bar.appendChild(acc);

        wireToggle(toggle, menu);
        fillAccount(toggle, menu);
    }

    // ZH: 所有下拉（三個分類 + 帳號）的關閉函式。開一個就把其他的關掉。
    var MENUS = [];

    function wireToggle(toggle, menu) {
        function close() {
            menu.hidden = true;
            toggle.setAttribute('aria-expanded', 'false');
        }
        toggle.addEventListener('click', function (ev) {
            ev.stopPropagation();
            var open = menu.hidden;
            // ZH: v3.9 導覽變成三個下拉之後才需要這一行 —— 沒有它的話，
            //     依序點過三個分類，畫面上會同時掛著三張互相疊住的選單。
            MENUS.forEach(function (fn) { if (fn !== close) fn(); });
            menu.hidden = !open;
            toggle.setAttribute('aria-expanded', String(open));
        });
        MENUS.push(close);
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

    // ZH: 這支原本不需要跳脫（選單文字都是字典裡的固定字串），
    //     v3.8 的初次設定彈窗開始把**資料庫來的名稱**（系所、單位）拼進 innerHTML，
    //     那些是管理者可編輯的自由文字 —— 沒有跳脫就是一個 XSS 入口。
    function esc(v) {
        return String(v == null ? '' : v)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
    }

    // ZH: 把「管理端設定的連結」變成可以安全放進 href 的字串。
    // ZH: 🔴 只跳脫引號是不夠的 —— `javascript:alert(1)` 完全沒有引號,
    //     跳脫完照樣是一個按下去就執行的連結。所以先擋通訊協定,再處理引號。
    //     這些 URL 來自管理端的自由文字欄位,不是常數。
    // ZH: 不合格回空字串,呼叫端據此**整個不畫這個連結** ——
    //     畫一個壞掉的連結比不畫更糟:使用者會以為是自己按錯。
    function safeUrl(raw) {
        const v = String(raw == null ? '' : raw).trim();
        if (!/^https?:\/\//i.test(v)) return '';
        return v.replace(/&/g, '&amp;').replace(/"/g, '&quot;')
                .replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }

    // ZH: 取文案。字典裡沒有就用 fallback（＝原本的中文），**不清空**。
    function T(key, fallback) {
        return (window.Prefs && window.Prefs.t(key, fallback)) || fallback;
    }
    function roleLabel(role) {
        return T('role_' + role, { student: '學生', teacher: '教師', staff: '職員',
                                   guest: '訪客', admin: '管理員' }[role] || role || '');
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

        // ZH: v3.8 初次登入設定。接在這裡是因為 `me` 已經在手上 ——
        //     另外打一次 /auth/me 只為了看一個欄位不划算。
        //     不 await：彈窗要不要跳跟頂部列畫不畫完沒有關係,
        //     等它會讓 topbar 在慢網路下多空白一段時間。
        if (me) maybeShowOnboarding(me);
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

        // ZH: v3.8 看 is_admin 旗標不看 role —— 管理者的身分可能是學生。
        if (me.is_admin) {
            // ZH: 管理端在同主機 port 8888。
            //
            // ZH: 🔴 路徑要帶 `/V1/`。`:8888/` 只是導向，而舊版在 /V0/ ——
            //     nginx 上三個版本各自有路徑：/V0/、/V0.5/、/V1/（現行）。
            //
            // ZH: token 仍然交棒 —— `admin_hud_token` 是舊版管理端在讀的；
            //     v2 用自己的 `ai_hud_token`（不同 origin，storage 本來就分開），
            //     所以到了對面還是會走一次登入。留著交棒是為了舊版還在的期間。
            var admin = document.createElement('a');
            admin.href = '#';
            admin.addEventListener('click', function (ev) {
                ev.preventDefault();
                var t = token();
                if (t) localStorage.setItem('admin_hud_token', t);
                location.href = location.protocol + '//' + location.hostname + ':8888/V1/';
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

    // ── 前台可見的營運設定（v3.8）────────────────────────────────────
    // ZH: 使用量／訓練／實驗室三頁都要講出「額度什麼時候重置」「任務跑多久會被砍」
    //     「檔案封存幾天」。在此之前前台**完全沒有管道讀到這些值**，
    //     所以那三句話要嘛不存在，要嘛是寫死在 HTML 裡的數字——
    //     而寫死的數字在管理者調過旋鈕之後就是**錯的，且不會有人發現**。
    //
    // ZH: 放這裡而不是三頁各寫一份：理由同這個檔案開頭那段——
    //     三份複製一定會漂掉。三頁共用取值，但**句子各自寫**
    //     （文案在 i18n.js，中英兩版）。
    //
    // ⚠ 回傳的是**快取起來的 Promise**，同一頁重複呼叫不會重打 API。
    //   失敗時回空物件而不是拋錯：這三句話都是補充說明，
    //   讀不到就不顯示，不該讓整頁的主要功能跟著壞掉。
    var _settingsPromise = null;
    function publicSettings() {
        if (!_settingsPromise) {
            _settingsPromise = fetch(API + '/system/public-settings', { headers: authHeaders() })
                .then(function (r) { return r.ok ? r.json() : { settings: {} }; })
                .then(function (j) { return (j && j.settings) || {}; })
                .catch(function () { return {}; });
        }
        return _settingsPromise;
    }

    // ── 初次登入設定（v3.8）────────────────────────────────────────────
    // ZH: 帳號從來沒設定過校區/學系時跳一次。**沒有關閉鈕、點背景也不關** ——
    //     那兩項是分組統計的基礎資料,能跳過的話永遠會有一堆「未分類」。
    //
    // ZH: 放在 chrome.js 而不是某一頁：使用者 SSO 進來會落在 /train/,
    //     但他也可能直接開書籤到別頁。寫在單一頁面的話,從別的入口進來就不會跳。
    //
    // ZH: 只在**登入後**的頁面出現 —— login.html 不載入這支。
    var CAMPUS_ONLY_ROLES = { guest: 1 };     // ZH: 訪客不屬於任何系所/單位,只問校區

    function onbFieldFor(role) {
        if (CAMPUS_ONLY_ROLES[role]) return null;
        return (role === 'staff' || role === 'admin') ? 'unit' : 'department';
    }

    // ZH: 這個彈窗有**兩種模式**：
    //       初次設定 —— onboarded_at 是 null,兩項都要填,不能跳過
    //       解鎖修改 —— 已經設定過,但管理者開放了一次修改（profile_unlock 有值）
    //
    // ZH: 🔴 沒有第二種模式的話,整條路是**斷的**：管理者按了「開放一次修改」,
    //     使用者端卻沒有任何地方能用它。（v3.8 開發中實際發生過,
    //     後端做完了、管理端介面做完了,使用者那邊卻打不開表單。）
    async function maybeShowOnboarding(me) {
        if (!me) return;
        var unlock = me.onboarded_at ? (me.profile_unlock || null) : null;
        if (me.onboarded_at && !unlock) return;      // ZH: 設定過且沒開放 → 不問
        try {
            var r = await fetch(API + '/system/org-options', { headers: authHeaders() });
            if (!r.ok) return;                       // ZH: 讀不到選項就不要擋住人
            _onbOpts = await r.json();
        } catch (e) { return; }
        buildOnboarding(me, _onbOpts, null, unlock);
    }

    // ZH: 選項清單存起來 —— 從確認頁「返回修改」時要重畫第一頁,
    //     再打一次 API 只是讓他多等一次而已。
    var _onbOpts = null;

    // ZH: `prefill` 是從確認頁返回時帶回來的選擇。沒有它的話,
    //     使用者按返回等於從頭再選一次 —— 那比沒有返回鍵更氣人。
    // ZH: `unlock` 是管理者核可的欄位清單（null = 初次設定,全部都要填）。
    var _onbUnlock = null;

    function buildOnboarding(me, opts, prefill, unlock) {
        var curLang = (window.Prefs && window.Prefs.get)
            ? window.Prefs.get().ui_lang : 'zh';

        // ZH: v3.9 學系／單位／校區的顯示名。
        //
        // ZH: 🔴 **只有顯示會換，送出去的 value 永遠是中文。**
        //     `users.department` 存的就是中文全名（它同時是 org_departments 的主鍵），
        //     送英文回去會查無此系而被後端擋下 —— 而錯誤訊息會是「沒有這個學系」，
        //     完全看不出是語言的問題。
        //
        // ZH: 英文名沒填就退回中文（不是留空）—— 148 筆要人工填，
        //     填到一半的期間畫面必須照樣可用。
        function disp(zh, en) {
            return (curLang === 'en' && en) ? en : zh;
        }
        _onbUnlock = unlock || null;
        var field = onbFieldFor(me.role);
        // ZH: 解鎖模式下只顯示核可範圍內的欄位 —— 顯示了卻不能存,
        //     使用者會以為自己改成功了,而後端會退回「這次核可的範圍不包含…」。
        var askCampus = !unlock || unlock.indexOf('campus') >= 0;
        var askOrg = !!field && (!unlock || unlock.indexOf(field) >= 0);
        var box = document.createElement('div');
        box.className = 'onb';
        box.setAttribute('role', 'dialog');
        box.setAttribute('aria-modal', 'true');
        box.setAttribute('aria-labelledby', 'onb-title');

        // ZH: 學生只能選一個校區（後端 set_user_campuses 也擋,這裡只是別讓他白選）。
        var multi = me.role !== 'student';
        // ZH: 校區的英文名是**平行陣列**（campuses_en），不是每一項的欄位 ——
        //     校區清單寫死在後端 org_seed，沒有進資料庫，所以沒有物件可以掛。
        //     長度對不上就整個退回中文，不要用索引硬對（會配錯校區）。
        var campusEn = (opts.campuses_en && opts.campuses_en.length === opts.campuses.length)
            ? opts.campuses_en : null;
        var campusOpts = opts.campuses.map(function (c, i) {
            return '<option value="' + esc(c) + '">'
                + esc(disp(c, campusEn ? campusEn[i] : '')) + '</option>';
        }).join('');

        var orgHtml = '';
        if (askOrg && field === 'department') {
            // ZH: 依學院分組,51 個系直接平鋪很難找。
            var byCollege = {};
            var collegeLabel = {};
            opts.departments.forEach(function (d) {
                (byCollege[d.college] = byCollege[d.college] || []).push(d);
                collegeLabel[d.college] = disp(d.college, d.college_en);
            });
            // ZH: （這裡原本先組了一個寫死「請選擇」的空 optgroup，下一行就整個覆蓋掉 ——
            //      死碼，而且是這個對話框裡唯一沒有走 T() 的字串。）
            orgHtml = Object.keys(byCollege).map(function (c) {
                return '<optgroup label="' + esc(collegeLabel[c] || c) + '">'
                    + byCollege[c].map(function (d) {
                        // ZH: value 一律中文（主鍵），只有顯示的字會換語言。
                        return '<option value="' + esc(d.name) + '">'
                            + esc(disp(d.name, d.name_en)) + '</option>';
                    }).join('') + '</optgroup>';
            }).join('');
        } else if (askOrg && field === 'unit') {
            // ZH: 97 個單位,依上層處室分組。頂層單位自成一組。
            var tops = opts.units.filter(function (u) { return !u.parent; });
            orgHtml = tops.map(function (t) {
                var kids = opts.units.filter(function (u) { return u.parent === t.name; });
                var self = '<option value="' + esc(t.path) + '">'
                    + esc(disp(t.name, t.name_en)) + '</option>';
                if (!kids.length) return self;
                return '<optgroup label="' + esc(disp(t.name, t.name_en)) + '">' + self
                    + kids.map(function (k) {
                        return '<option value="' + esc(k.path) + '">'
                            + esc(disp(k.name, k.name_en)) + '</option>';
                    }).join('') + '</optgroup>';
            }).join('');
        }

        box.innerHTML =
            '<div class="onb__box">'
            // ZH: 🔴 語言切換**必須放在對話框裡面**。
            //     這個遮罩是 `position:fixed; inset:0; z-index:1000`，蓋住整頁 ——
            //     包含頂部列上的那組「中／EN」。而它刻意沒有關閉鈕、點背景也關不掉
            //     （校區與學系是分組統計的基礎，能跳過就會有一堆「未分類」）。
            //     兩件事加起來：**只看英文的人第一次登入就被鎖在一個中文對話框裡，
            //     而切語言的鈕正好被自己擋住了。**
            //     不改 z-index 讓頂部列浮上來，是因為那會讓遮罩看起來破一個洞；
            //     把切換帶進來比較誠實 —— 它本來就是這一刻唯一需要的控制項。
            + '<div class="onb__lang">'
            +   '<div class="lang-switch">'
            +     '<button type="button" data-set-lang="zh" aria-pressed="'
            +       (curLang === 'zh' ? 'true' : 'false')
            +       '" data-i18n-aria="prefs_lang_zh" aria-label="'
            +       esc(T('prefs_lang_zh', '切換成中文')) + '">中</button>'
            +     '<button type="button" data-set-lang="en" aria-pressed="'
            +       (curLang === 'en' ? 'true' : 'false')
            +       '" data-i18n-aria="prefs_lang_en" aria-label="'
            +       esc(T('prefs_lang_en', '切換成英文')) + '">EN</button>'
            +   '</div>'
            + '</div>'
            + '<h2 class="onb__title" id="onb-title">'
            + esc(unlock ? T('onb_edit_title', '修改你的資料')
                         : T('onb_title', '先完成基本設定')) + '</h2>'
            + '<p class="onb__sub">'
            + esc(unlock
                ? T('onb_edit_sub', '管理員開放了一次修改。存檔之後會再次鎖定。')
                : T('onb_sub', '這些資料用來做統計分組，只需要設定一次。')) + '</p>'
            + '<p class="onb__err" id="onb-err" hidden></p>'
            + (askCampus ? '<div class="onb__field">'
            +   '<label class="onb__label" for="onb-campus">' + esc(T('onb_campus', '校區')) + '</label>'
            +   '<select class="onb__select" id="onb-campus"' + (multi ? ' multiple size="5"' : '') + '>'
            +     (multi ? '' : '<option value="">' + esc(T('onb_pick', '請選擇')) + '</option>')
            +     campusOpts + '</select>'
            +   (multi ? '<span class="onb__hint">' + esc(T('onb_campus_multi', '可以選多個（按住 Ctrl／⌘）。')) + '</span>' : '')
            + '</div>' : '')
            + (askOrg
                ? '<div class="onb__field">'
                  + '<label class="onb__label" for="onb-org">'
                  + esc(field === 'unit' ? T('onb_unit', '行政單位') : T('onb_dept', '學系'))
                  + '</label>'
                  + '<select class="onb__select" id="onb-org">'
                  + '<option value="">' + esc(T('onb_pick', '請選擇')) + '</option>'
                  + orgHtml + '</select></div>'
                : '')
            + '<button class="btn btn--primary btn--block" type="button" id="onb-go">'
            + esc(T('onb_next', '下一步')) + '</button>'
            + '</div>';

        document.body.appendChild(box);

        // ZH: 解鎖模式帶入現有值 —— 只開放改校區時,不該讓他連學系一起重選;
        //     而且看得到目前是什麼,才知道自己要改成什麼。
        if (!prefill && unlock) {
            prefill = { campuses: me.campuses || [],
                        org: (field === 'unit' ? me.unit : me.department) || '' };
        }
        if (prefill) {
            var cs = box.querySelector('#onb-campus');
            if (multi) {
                Array.prototype.forEach.call(cs.options, function (o) {
                    o.selected = prefill.campuses.indexOf(o.value) >= 0;
                });
            } else {
                cs.value = prefill.campuses[0] || '';
            }
            var oe = box.querySelector('#onb-org');
            if (oe && prefill.org) oe.value = prefill.org;
        }

        box.querySelector('#onb-go').addEventListener('click', function () {
            reviewOnboarding(box, multi, field);
        });

        // ZH: 切語言要把對話框整個重畫。
        //
        // ZH: 🔴 光是把切換鈕放進來還不夠 —— 標題、說明、按鈕文字都是 build 當下
        //     用 T() 組進 innerHTML 的，字典掃描只換得掉有 `data-i18n` 的元素。
        //     不重畫的話：他按了 EN，背後的頁面變成英文，**而他正看著的對話框
        //     還是中文** —— 那比沒有切換鈕更令人困惑（看起來像按了沒反應）。
        //
        // ZH: ⚠️ 重畫要**把已經選好的帶回去**，用的是 #onb-back 同一套 prefill；
        //     不帶的話切一次語言就得從 51 個系裡重選一次。
        //     `_onbUnlock` 也要帶（理由同 #onb-back 那裡）。
        function onLang() {
            var sel = box.querySelector('#onb-campus');
            var picked = !sel ? []
                : multi
                    ? Array.prototype.slice.call(sel.selectedOptions)
                        .map(function (o) { return o.value; })
                    : (sel.value ? [sel.value] : []);
            var orgEl = box.querySelector('#onb-org');
            document.removeEventListener('prefs:langchanged', onLang);
            box.remove();
            buildOnboarding(_me, _onbOpts,
                { campuses: picked, org: orgEl ? orgEl.value : null }, _onbUnlock);
        }
        document.addEventListener('prefs:langchanged', onLang);
    }

    // ── 二次確認（v3.8）──────────────────────────────────────────────
    // ZH: 送出之後這幾項就**鎖住**了 —— 要再改得發問題回報、等管理員核可解鎖。
    //     所以手殘按到的代價不是「重按一次」而是「等好幾天」。
    //     確認頁把選到的值原樣列出來,並明講之後不能自己改。
    //
    // ZH: 🔴 **確認頁不重新讀取欄位** —— 它顯示的就是待會要送出的那份資料。
    //     重讀的話,顯示與送出會是兩次不同的讀取,中間任何變動都看不出來。
    function reviewOnboarding(box, multi, field) {
        // ZH: 解鎖模式下只會出現核可範圍內的欄位,所以兩個都可能不存在。
        var sel = box.querySelector('#onb-campus');
        var campuses = !sel ? []
            : multi
                ? Array.prototype.slice.call(sel.selectedOptions).map(function (o) { return o.value; })
                : (sel.value ? [sel.value] : []);
        var orgEl = box.querySelector('#onb-org');
        var orgValue = orgEl ? orgEl.value : null;
        var err = box.querySelector('#onb-err');

        // ZH: 明顯的漏填在這裡先擋 —— 讓他確認一份空的再被後端退回很不友善。
        if (sel && !campuses.length) {
            err.textContent = T('onb_need_campus', '請先選擇校區。');
            err.hidden = false;
            return;
        }
        if (orgEl && !orgValue) {
            err.textContent = field === 'unit'
                ? T('onb_need_unit', '請先選擇行政單位。')
                : T('onb_need_dept', '請先選擇學系。');
            err.hidden = false;
            return;
        }
        err.hidden = true;

        var orgLabel = orgEl && orgEl.selectedOptions[0]
            ? orgEl.selectedOptions[0].textContent : '';
        var rows = (sel ? '<div class="onb__row"><span class="onb__k">'
            + esc(T('onb_campus', '校區')) + '</span><span class="onb__v">'
            + esc(campuses.join('、')) + '</span></div>' : '')
            + (orgEl
                ? '<div class="onb__row"><span class="onb__k">'
                  + esc(field === 'unit' ? T('onb_unit', '行政單位') : T('onb_dept', '學系'))
                  + '</span><span class="onb__v">' + esc(orgLabel) + '</span></div>'
                : '');

        box.querySelector('.onb__box').innerHTML =
            '<h2 class="onb__title" id="onb-title">'
            + esc(T('onb_confirm_title', '確認一下')) + '</h2>'
            + '<p class="onb__sub">' + esc(T('onb_confirm_sub',
                '送出之後這些資料就不能自己修改了。要更改需要向管理員申請。')) + '</p>'
            + '<p class="onb__err" id="onb-err" hidden></p>'
            + '<div class="onb__review">' + rows + '</div>'
            + '<button class="btn btn--primary btn--block" type="button" id="onb-yes">'
            + esc(T('onb_confirm_yes', '確認送出')) + '</button>'
            + '<button class="btn btn--ghost btn--block" type="button" id="onb-back">'
            + esc(T('onb_confirm_back', '返回修改')) + '</button>';

        box.querySelector('#onb-yes').addEventListener('click', function () {
            submitOnboarding(box, campuses, orgValue);
        });
        // ZH: 返回就重畫第一頁 —— 但**要把剛才選的帶回去**,
        //     不然他返回之後得從頭再選一次,那比沒有返回鍵更氣人。
        box.querySelector('#onb-back').addEventListener('click', function () {
            box.remove();
            // ZH: 🔴 `_onbUnlock` 要一起帶回去 —— 不帶的話返回之後會變成
            //     初次設定模式,欄位全開,而使用者存下去會被後端擋「超出核可範圍」。
            buildOnboarding(_me, _onbOpts, { campuses: campuses, org: orgValue }, _onbUnlock);
        });
    }

    // ZH: 收的是**確認頁顯示過的那份值**,不是重新讀欄位 ——
    //     重讀的話「他看到的」與「送出去的」會是兩次不同的讀取。
    async function submitOnboarding(box, campuses, orgValue) {
        var btn = box.querySelector('#onb-yes');
        var err = box.querySelector('#onb-err');

        btn.disabled = true;
        try {
            var r = await fetch(API + '/system/onboarding', {
                method: 'POST',
                headers: Object.assign({ 'Content-Type': 'application/json' }, authHeaders()),
                body: JSON.stringify({ campuses: campuses, org_value: orgValue }),
            });
            if (!r.ok) {
                // ZH: 後端的訊息是給人看的（「請選擇校區」「沒有這個學系」）,直接顯示。
                var body = await r.json().catch(function () { return {}; });
                err.textContent = body.detail || ('HTTP ' + r.status);
                err.hidden = false;
                btn.disabled = false;
                return;
            }
            box.remove();
        } catch (e) {
            err.textContent = T('onb_net', '存不起來，請檢查連線後再試一次。');
            err.hidden = false;
            btn.disabled = false;
        }
    }

    // ZH: 對外只暴露 logout —— 其他頁面若要做「登出」都該走同一份實作。
    //     （goMyai 已搬回 app.js：MYAI 改成回首頁之後，只剩首頁那顆按鈕在用它。）
    // ZH: safeUrl 對外開放是因為 app.js / usage.js 都要畫「申請額度」那個連結。
    //     兩邊各寫一份的話,只有一邊會被記得補上 javascript: 的防線。
    window.Chrome = { logout: logout, publicSettings: publicSettings, safeUrl: safeUrl };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', build);
    } else {
        build();
    }
})();
