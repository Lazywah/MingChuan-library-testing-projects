/* ==========================================================================
 * platform.js — 平台設定（調完就走）
 *
 * ZH: 三塊都是「設定完就離開」的東西，與總覽（每天看）和人（接到求助才開）
 *     的使用時機不同：
 *       營運設定  GET/PUT /admin/system-settings
 *       模型      GET/POST /admin/models、PUT/DELETE /admin/models/{id}
 *       GPU 節點  GET /admin/gpu-nodes、PUT /admin/gpu-nodes/{id}
 *
 * ZH: 外部 AI（MYAI）只收下**設定**的部分（8 / 23 個端點）：
 *       連線設定  GET/PUT /external-ai/admin/url、/admin/alert-config
 *       代碼對應  GET/POST /external-ai/admin/model-map、DELETE .../{id}、POST .../seed
 *     其餘 15 個是營運動作或報表：帳號對應與同步在「人」、
 *     即時使用狀態在「總覽」、消耗分析在「數據」。
 *
 * ZH: 營運設定是**資料驅動**的：後端每個旋鈕都回 label/type/value/default/
 *     min/max/overridden，所以這裡不寫死欄位清單。加旋鈕時前端不用改。
 * ========================================================================== */
(function () {
    'use strict';

    var API = '/api/v1';
    var DAYS = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'];

    function $(id) { return document.getElementById(id); }

    function token() {
        return sessionStorage.getItem('ai_hud_token') || localStorage.getItem('ai_hud_token');
    }

    function esc(s) {
        return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
            return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
        });
    }

    function detailText(body) {
        var d = body && body.detail;
        if (!d) return '';
        if (typeof d === 'string') return zhOnly(d);
        if (Array.isArray(d)) {
            return d.map(function (x) {
                return (x.loc ? x.loc[x.loc.length - 1] + '：' : '')
                    + zhOnly(String(x.msg || '').replace(/^Value error,\s*/, ''));
            }).join('；');
        }
        return String(d);
    }

    function zhOnly(text) {
        var parts = String(text).split(' | ');
        var lang = (window.Prefs && Prefs.get().ui_lang) || 'zh';
        var want = parts.filter(function (p) {
            return p.indexOf(lang === 'en' ? 'EN:' : 'ZH:') === 0;
        })[0];
        return (want || parts[0] || '').replace(/^(ZH|EN):\s*/, '');
    }

    async function api(path, opts) {
        var o = opts || {};
        o.headers = Object.assign({ Authorization: 'Bearer ' + token() }, o.headers || {});
        var r = await fetch(API + path, o);
        if (r.status === 401) { location.replace('login.html'); throw new Error('401'); }
        if (!r.ok) {
            var body = await r.json().catch(function () { return {}; });
            throw new Error(detailText(body) || ('HTTP ' + r.status));
        }
        return r.status === 204 ? null : r.json();
    }

    // ZH: 大數字要有千分位 —— 1234 與 12340 在沒有分隔時一眼分不出來。
    function num(n) { return Number(n || 0).toLocaleString('en-US'); }

    function say(id, text) {
        var el = $(id);
        if (!el) return;
        el.textContent = text;
        el.hidden = !text;
    }

    // ZH: 只給**成功**訊息用的短暫提示（幾秒後自己消失）。
    //
    // ZH: 🔴 錯誤訊息**不要**用這個 —— 它還沒被解決，讀者需要時間看清楚，
    //     而且訊息消失之後畫面看起來就像什麼都沒發生過。
    //     成功則相反：確認完就沒有用了，留著只會變成雜訊
    //     （下次再按時你分不出那是新的還是上次留下的）。
    var _flashTimers = {};
    function flash(id, text, ms) {
        say(id, text);
        // ZH: 舊的計時器一定要取消。不取消的話，上一次的計時器會在幾秒後
        //     把**新的**訊息清掉——包含錯誤訊息。
        clearTimeout(_flashTimers[id]);
        _flashTimers[id] = setTimeout(function () {
            var el = $(id);
            // ZH: 只清掉自己那一則。中間若換成別的訊息（例如錯誤），就不要動它。
            if (el && el.textContent === text) say(id, '');
        }, ms || 3000);
    }


    // ── 可編輯表格（各區共用）─────────────────────────────────────────────
    //
    // ZH: 這一頁的每一區都是同一個節奏：**唯讀 → 按編輯 → 欄位變可填 →
    //     一次儲存**。所以表格的 markup 統一在這裡產生，四個區塊長同一個樣子。
    //
    // ZH: 但**儲存契約各自不同**（營運設定是一次 PUT 一個字典、連線設定是兩個
    //     PUT、模型與代碼對應是逐列 POST/PUT/DELETE），那部分留在各自的函式裡。
    //     硬要一起抽象只會做出一個誰都看不懂的參數包。
    function tableHtml(cols, body) {
        return '<div class="adm-tablewrap"><table class="adm-table"><thead><tr>'
            + cols.map(function (c) {
                return '<th' + (c[2] ? ' class="' + esc(c[2]) + '"' : '') + '>'
                    + esc(c[0] ? T(c[0], c[1]) : '') + '</th>';
            }).join('')
            + '</tr></thead><tbody>' + body + '</tbody></table></div>';
    }

    // ZH: 🔴 `o.label` 是**必要的**，不是裝飾。表格裡的欄位沒有 <label>，
    //     欄位名在 <th> 裡，而 <th> 不會自動關聯到 <td> 裡的控制項 ——
    //     沒有 aria-label 的話，讀螢幕的人聽到的是一連串沒有名字的「編輯方塊」。
    //     （實測過：表格化之後這一頁編輯模式有 136 個控制項沒有可及的名稱。）
    function cellInput(f, value, o) {
        o = o || {};
        return '<td><input class="field__input" data-f="' + esc(f) + '"'
            + (o.label ? ' aria-label="' + esc(o.label) + '"' : '')
            + ' type="' + esc(o.type || 'text') + '"'
            + (o.min != null ? ' min="' + esc(o.min) + '"' : '')
            + (o.max != null ? ' max="' + esc(o.max) + '"' : '')
            + (o.step ? ' step="' + esc(o.step) + '"' : '')
            + (o.placeholder != null ? ' placeholder="' + esc(o.placeholder) + '"' : '')
            + (o.disabled ? ' disabled' : '')
            + ' value="' + esc(value == null ? '' : value) + '"></td>';
    }

    // ZH: 這兩個旋鈕由「告警信」那一格負責，**不畫進營運設定表**。
    //     同一個值有兩個編輯處的話，兩邊會顯示不同的內容（一邊改完另一邊沒重讀），
    //     而使用者不知道該信哪一個。
    // ZH: ⚠ 從表格移除的東西必須**確定有別的地方畫它**。這裡兩者在同一頁、
    //     同一個檢視（platform）、同一次 loadSettings 之後渲染，所以不會發生
    //     「從表格拿掉了、新區塊又沒出現」那種安靜消失。
    var ALERT_MAIL_KEYS = ['admin_alert_emails', 'admin_alert_cc_emails'];

    // ZH: 逗號分隔字串 → 陣列。空白與空項目一律丟掉。
    //     `null` / 空字串會得到空陣列（不是 [""]）—— 那會讓畫面出現一個空白列。
    function splitAddrs(v) {
        return String(v == null ? '' : v).split(',')
            .map(function (x) { return x.trim(); })
            .filter(function (x) { return x.length > 0; });
    }

    // ZH: list 可以是字串陣列，也可以是 {value,label}。
    function cellSelect(f, list, value, o) {
        o = o || {};
        return '<td><select class="field__input" data-f="' + esc(f) + '"'
            + (o.label ? ' aria-label="' + esc(o.label) + '"' : '')
            + (o.disabled ? ' disabled' : '') + '>'
            + (o.blank === false ? ''
                : '<option value="">' + esc(o.blankText
                    || T('pf_mm_blank', '（不指定）')) + '</option>')
            + (list || []).map(function (x) {
                var v = (x && x.value != null) ? x.value : x;
                var l = (x && x.label != null) ? x.label : x;
                return '<option value="' + esc(v) + '"'
                    + (String(value == null ? '' : value) === String(v) ? ' selected' : '')
                    + '>' + esc(l) + '</option>';
            }).join('')
            + '</select></td>';
    }

    // ZH: 把畫面上的值收回物件。checkbox 要讀 checked 不是 value ——
    //     讀 value 的話永遠拿到字串 "on"，勾不勾都一樣。
    //
    // ZH: 這一頁**目前沒有任何 checkbox**（布林值都改成下拉了），所以那一支
    //     現在走不到。留著是因為 readRow 是通用的：日後誰加一個 checkbox，
    //     沒有這一行就會靜默讀成 "on"，而且不會有任何錯誤。
    function readRow(tr, target) {
        tr.querySelectorAll('[data-f]').forEach(function (el) {
            target[el.dataset.f] = (el.type === 'checkbox') ? el.checked : el.value;
        });
    }

    // ZH: 標記為「要刪」的那一列（還沒真的刪，按儲存才送出）。
    function delCell(id, marked) {
        return '<td class="num"><button class="btn btn--minor" type="button" data-del="' + esc(id) + '">'
            + esc(marked ? T('pf_mm_undel', '不刪了') : T('pf_m_del', '刪除')) + '</button></td>';
    }

    // ── 營運設定 ──────────────────────────────────────────────────────────
    // ZH: 預設**唯讀**，按「編輯設定」才變成可填的欄位。
    //
    // ZH: 兩個理由：15 個輸入框常駐會把這一區撐得很長，而真正要改的時候
    //     一年也沒幾次；而且常駐的輸入框會招來誤觸 ——
    //     捲頁時滑鼠滾輪停在數字欄位上，值就被改掉了，
    //     而且**完全沒有痕跡**（除非他剛好按了儲存）。
    var SETTINGS = [];
    var EDITING = false;

    var GROUPS = [];

    // ==================================================================
    // ZH: 「平台 / MYAI」檢視。
    //
    // ZH: 狀態放在**網址 hash**，不放 storage：
    //       - 重新整理不會跳回去（管理者常常改完就 F5）
    //       - 可以把 `platform.html#myai` 直接貼給別人
    //       - 不留任何跨工作階段的殘留（這是檢視偏好，不是帳號設定）
    //     用 replaceState 而不是設 location.hash —— 後者每切一次就多一筆
    //     瀏覽紀錄，按上一頁會在兩個檢視之間來回彈。
    //
    // ZH: 🔴 「營運設定」那一區**兩個檢視都會出現**（data-view="both"），
    //     只是裡面顯示的分組不同。所以切換時**一定要重畫它** ——
    //     只做 section 的顯示/隱藏的話，它會一直停在上一個檢視的分組。
    // ==================================================================
    var VIEWS = ['platform', 'myai'];

    // ZH: hash → 要顯示哪個檢視。
    //
    // ZH: 🔴 `#node-<id>` 是 GPU 節點的深層連結（見 scrollToHash）。那一區在
    //     「平台」這一邊 —— 不特別處理的話，人在 MYAI 檢視時點到節點連結，
    //     **會被帶到一個看不見那個區塊的畫面**，而且沒有任何錯誤訊息。
    function viewFromHash() {
        var h = (location.hash || '').replace('#', '');
        if (h.indexOf('node-') === 0) return 'platform';
        return VIEWS.indexOf(h) >= 0 ? h : 'platform';
    }

    var VIEW = viewFromHash();

    function applyView(next) {
        if (next) VIEW = next;
        document.querySelectorAll('[data-view]').forEach(function (el) {
            var v = el.dataset.view;
            el.hidden = !(v === 'both' || v === VIEW);
        });
        // ZH: 見上面 🔴 —— 分組是依 VIEW 篩的，換檢視就得重畫。
        if (SETTINGS.length) renderSettings();
        // ZH: 🔴 **只動我們自己的 hash**。這一頁還有 `#node-<id>` 的深層連結
        //     （GPU 節點，見 scrollToHash）—— 無條件 replaceState 會在載入時
        //     把它洗掉，於是從別處連過來就不會捲到那個節點了，
        //     而且畫面上完全看不出哪裡不對。
        var cur = (location.hash || '').replace('#', '');
        if (cur === '' || VIEWS.indexOf(cur) >= 0) {
            try {
                history.replaceState(null, '',
                    location.pathname + (VIEW === 'platform' ? '' : '#' + VIEW));
            } catch (e) { /* 某些情境下不給改網址，不影響功能 */ }
        }
    }

    function wireViewSeg() {
        var seg = $('view-seg');
        if (!seg) return;
        var thumb = seg.querySelector('.adm-seg__thumb');
        var opts = [].slice.call(seg.querySelectorAll('[data-view-opt]'));

        function pick(i, focus) {
            if (i < 0 || i >= opts.length) return;
            var v = opts[i].dataset.viewOpt;
            thumb.style.transform = 'translateX(' + (i * 100) + '%)';
            opts.forEach(function (o, k) {
                var on = k === i;
                o.classList.toggle('is-current', on);
                o.setAttribute('aria-checked', on ? 'true' : 'false');
                o.setAttribute('tabindex', on ? '0' : '-1');
            });
            if (focus) opts[i].focus();
            applyView(v);
        }

        opts.forEach(function (o, i) {
            o.addEventListener('click', function () { pick(i, false); });
        });
        // ZH: radiogroup 的慣例是左右鍵換選項（群組本身只佔一個 Tab 位）。
        seg.addEventListener('keydown', function (e) {
            var d = e.key === 'ArrowRight' ? 1 : e.key === 'ArrowLeft' ? -1 : 0;
            if (!d) return;
            e.preventDefault();
            var cur = VIEWS.indexOf(VIEW);
            pick((cur + d + opts.length) % opts.length, true);
        });

        // ZH: 網址帶 #myai 進來時，滑塊與選取狀態要跟著對 ——
        //     只設 VIEW 而不動 DOM 的話，內容是 MYAI 但滑塊停在「平台」。
        pick(VIEWS.indexOf(VIEW), false);

        // ZH: 🔴 **只改 hash 不會重新載入頁面**，模組頂層那行 `var VIEW = ...`
        //     只跑一次。沒有這個監聽的話，從 `#myai` 連到 `#node-xxx`
        //     會停在 MYAI 檢視，而使用者要看的 GPU 節點是隱藏的。
        //     （實測過：view 停在 MYAI、gpuSectionVisible=false。）
        window.addEventListener('hashchange', function () {
            var want = viewFromHash();
            if (want !== VIEW) pick(VIEWS.indexOf(want), false);
        });
    }

    async function loadSettings() {
        try {
            var r = await api('/admin/system-settings');
            SETTINGS = r.settings || [];
            // ZH: 分組與順序都由後端決定 —— 前端不維護對照表，
            //     不然後端新增旋鈕時這裡會漏，而漏掉的旋鈕會安靜地不出現。
            GROUPS = r.groups || [];
        } catch (e) {
            $('settings').innerHTML = '<p class="footnote">'
                + esc(T('ov_fail_part', '這一段暫時讀不到（{w}）').replace('{w}', e.message)) + '</p>';
            return;
        }
        renderSettings();
        renderAlertMail();
    }

    // ══════════════════════════════════════════════════════════════════════
    // ZH: 「告警信」—— 收件人設定畫成一封信的樣子（寄件人／收件人／副本／主旨）。
    //
    // ZH: 為什麼不留在營運設定那張表：那張表是四欄的統一格式，
    //     而這幾個值要回答的是「這封信會從哪寄、寄給誰、長什麼樣」——
    //     那是一封信，不是一個值。放進表格就只是兩列看不出關係的字串。
    //
    // ZH: 這一格同時是**預覽**。告警是安靜的（沒填收件人就完全不寄），
    //     所以「它到底會寄給誰、從哪個地址寄」必須一眼看得到，
    //     不能要人自己把三個設定欄位在腦裡兜起來。
    // ══════════════════════════════════════════════════════════════════════
    var AM_EDITING = false;

    function settingByKey(k) {
        return SETTINGS.filter(function (x) { return x.key === k; })[0] || null;
    }

    // ZH: 取生效值。找不到就回空字串 —— 後端還沒有這個旋鈕時（前後端版本不同步）
    //     這一格要照樣畫得出來，而不是整段炸掉。
    function amValue(k) {
        var s = settingByKey(k);
        return s ? String(s.value == null ? '' : s.value) : '';
    }

    function amRowHtml(labelKey, labelZh, hint, body) {
        return '<div class="am-row">'
            + '<div class="am-row__label">' + esc(T(labelKey, labelZh))
            + (hint ? ' <span class="am-row__hint">' + esc(hint) + '</span>' : '')
            + '</div>'
            + '<div class="am-row__body">' + body + '</div></div>';
    }

    // ZH: chip = 一個地址。刪除鈕有 aria-label，而且 chip 本身可以聚焦後按
    //     Backspace/Delete 刪掉 —— 只能用滑鼠點 × 的介面對鍵盤使用者是死路。
    //
    // ZH: 🔴 唯讀時**不畫 ×，也不給 tabindex**。
    //     第一版兩種模式共用同一段 HTML，於是唯讀的 chip 上也有一顆 ×，
    //     但那顆鈕沒有接任何行為 —— 看起來能點、點下去沒反應，
    //     而且鍵盤會停在一個什麼都不能做的 chip 上。
    //     （在真實頁面上截圖才看到的；DOM 測試只驗了編輯模式。）
    function amChipHtml(addr, editable) {
        return '<span class="am-chip"' + (editable ? ' tabindex="0" data-chip="1"' : '')
            + ' role="listitem">'
            + '<span class="am-chip__t">' + esc(addr) + '</span>'
            + (editable
                ? '<button class="am-chip__x" type="button" data-delchip="1" tabindex="-1"'
                    + ' aria-label="' + esc(T('pf_am_remove', '移除 {a}').replace('{a}', addr))
                    + '">×</button>'
                : '')
            + '</span>';
    }

    function amFieldHtml(key, labelKey, labelZh) {
        var addrs = splitAddrs(amValue(key));
        if (!AM_EDITING) {
            return amRowHtml(labelKey, labelZh, '', addrs.length
                // ZH: ⚠ 不能寫成 `addrs.map(amChipHtml)` —— map 會把**索引**
                //     當成第二個參數傳進去，於是第 0 個是唯讀樣子、其餘都可編輯。
                ? '<span class="am-chips" role="list">'
                    + addrs.map(function (a) { return amChipHtml(a, false); }).join('') + '</span>'
                : '<span class="footnote">' + esc(T('pf_am_none', '（沒有人）')) + '</span>');
        }
        return amRowHtml(labelKey, labelZh, '', ''
            + '<div class="am-chips am-chips--edit" data-am="' + esc(key) + '" role="list">'
            + addrs.map(function (a) { return amChipHtml(a, true); }).join('')
            + '<input class="am-chips__in" type="email" data-aminput="1"'
            + ' aria-label="' + esc(T(labelKey, labelZh)) + '"'
            + ' placeholder="' + esc(T('pf_am_add', '輸入信箱後按 Enter')) + '">'
            + '</div>');
    }

    function renderAlertMail() {
        var box = $('alertmail');
        if (!box) return;                       // ZH: 舊版 HTML 還在快取時不要整頁炸掉

        var from = amValue('smtp_from_email');
        var hours = amValue('admin_alert_min_hours');

        // ZH: 主旨用真的格式（scheduler._alert 組的那個），後面接一個實際會出現的標題。
        //     寫死一句假的「範例主旨」沒有意義 —— 那不會讓人看出信長什麼樣。
        var subject = '[AI Base 告警 | Alert] '
            + T('pf_am_subj_eg', 'MYAI 自動同步失敗 | MYAI sync failed');

        box.innerHTML = '<div class="am-draft">'
            // ZH: 提示放在**值後面**，不放在標籤裡。放標籤裡會把那一欄撐成兩行
            //     （量過：50px vs 其他三列的 27px），四個標籤高度不一樣就不像信件抬頭了。
            + amRowHtml('pf_am_from', '寄件人', '',
                (from
                    ? '<span class="am-from">' + esc(from) + '</span>'
                    : '<span class="footnote">'
                        + esc(T('pf_am_no_from', '（尚未設定寄件地址）')) + '</span>')
                + ' <span class="am-row__hint">'
                + esc(T('pf_am_from_hint', '（跟著 SMTP 設定走）')) + '</span>')
            + amFieldHtml('admin_alert_emails', 'pf_am_to', '收件人')
            + amFieldHtml('admin_alert_cc_emails', 'pf_am_cc', '副本')
            + amRowHtml('pf_am_subject', '主旨', '',
                '<span class="am-subject">' + esc(subject) + '</span>')
            + '</div>'
            + '<p class="footnote">'
            + esc(T('pf_am_throttle', '同一類告警最少隔 {h} 小時才會再寄一次。')
                .replace('{h}', hours))
            + '</p>';

        $('am-edit').hidden = AM_EDITING;
        $('am-cancel').hidden = !AM_EDITING;
        $('am-save').hidden = !AM_EDITING;
        if (AM_EDITING) wireAlertMail();
    }

    function wireAlertMail() {
        $('alertmail').querySelectorAll('[data-am]').forEach(function (box) {
            var input = box.querySelector('[data-aminput]');

            function commit() {
                // ZH: 一次可以貼進多個（從別的地方複製一串逗號分隔的地址是常見動作）。
                var added = splitAddrs(input.value);
                if (!added.length) { input.value = ''; return; }
                var have = {};
                box.querySelectorAll('[data-chip] .am-chip__t').forEach(function (t) {
                    have[t.textContent.trim().toLowerCase()] = true;
                });
                added.forEach(function (a) {
                    if (have[a.toLowerCase()]) return;   // ZH: 已經有了就不重複加
                    have[a.toLowerCase()] = true;
                    input.insertAdjacentHTML('beforebegin', amChipHtml(a, true));
                });
                input.value = '';
            }

            input.addEventListener('keydown', function (ev) {
                if (ev.key === 'Enter' || ev.key === ',') { ev.preventDefault(); commit(); return; }
                // ZH: 空輸入框按 Backspace → 刪掉前一個 chip（信件收件人欄的通用行為）。
                if (ev.key === 'Backspace' && !input.value) {
                    var chips = box.querySelectorAll('[data-chip]');
                    if (chips.length) chips[chips.length - 1].remove();
                }
            });
            // ZH: 🔴 打完沒按 Enter 就直接按「儲存設定」是**最常見的操作**。
            //     沒有這一行的話，那個地址會安靜地不見 —— 使用者以為存好了。
            input.addEventListener('blur', commit);

            box.addEventListener('click', function (ev) {
                var x = ev.target.closest('[data-delchip]');
                if (x) { x.closest('[data-chip]').remove(); input.focus(); return; }
                // ZH: 點空白處就聚焦輸入框 —— 整格看起來像一個欄位，點哪裡都該能打字。
                if (ev.target === box) input.focus();
            });

            // ZH: chip 聚焦後按 Backspace/Delete 刪掉自己。只有滑鼠能刪的話，
            //     用鍵盤的人根本移不掉任何一個地址。
            box.addEventListener('keydown', function (ev) {
                var chip = ev.target.closest('[data-chip]');
                if (!chip) return;
                if (ev.key === 'Backspace' || ev.key === 'Delete') {
                    ev.preventDefault();
                    chip.remove();
                    input.focus();
                }
            });
        });
    }

    function readAlertMail() {
        var payload = {};
        $('alertmail').querySelectorAll('[data-am]').forEach(function (box) {
            // ZH: 先把還停在輸入框裡的那一個收進來（blur 沒觸發的情況，例如直接按 Enter 送出表單）
            var input = box.querySelector('[data-aminput]');
            var pending = input ? splitAddrs(input.value) : [];
            var addrs = [];
            box.querySelectorAll('[data-chip] .am-chip__t').forEach(function (t) {
                addrs.push(t.textContent.trim());
            });
            pending.forEach(function (a) {
                if (addrs.map(function (x) { return x.toLowerCase(); })
                        .indexOf(a.toLowerCase()) < 0) addrs.push(a);
            });
            payload[box.dataset.am] = addrs.join(', ');
        });
        return payload;
    }

    async function saveAlertMail() {
        try {
            await api('/admin/system-settings', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(readAlertMail()),
            });
            flash('am-msg', T('pf_saved', '已儲存'));
            AM_EDITING = false;
            await loadSettings();      // ZH: 重讀 —— 後端會正規化，畫面要顯示真正存進去的
        } catch (e) {
            say('am-msg', T('pf_save_fail', '存不起來（{w}）').replace('{w}', e.message));
        }
    }

    function settingValueLabel(s) {
        // ZH: 唯讀時下拉要顯示**看得懂的名字**，不是模型 id。
        if (s.type === 'choice') {
            var pick = (s.choices || []).filter(function (c) {
                return String(c.value) === String(s.value);
            })[0];
            return pick ? pick.label : String(s.value);
        }
        return String(s.value);
    }

    function renderSettings() {
        paintSettingsButtons();

        var cols = [['pf_s_name', '設定'], ['pf_s_value', '值'],
                    ['pf_default_h', '預設'], ['pf_range_h', '範圍']];
        if (EDITING) cols = cols.concat([['', '']]);

        // ZH: 一列的 HTML。抽出來是為了讓下面能按分組各自組表，
        //     而不是把整個 map 複製三份。
        function rowHtml(s2) {
            var range = (s2.min != null && s2.max != null)
                ? T('pf_range', '{min}–{max}').replace('{min}', s2.min).replace('{max}', s2.max)
                : '—';
            // ZH: `overridden` 是後端給的 —— 標出來，管理者才分得出
            //     「這是我改過的」與「這是 .env 的預設」。
            // ZH: 星號在標籤前面。用 title 而不是只給一個符號 ——
            //     一個沒有解釋的星號，下一個接手的人根本不知道它在講什麼。
            //     區塊上方另外有一行圖例（見 analytics 以外的 pf_star_legend）。
            var star = s2.starred
                ? '<span class="pf-star" title="' + esc(T('pf_star_why',
                    '這個值使用者看得到，或者改之前應該先公告。'))
                    + '" aria-label="' + esc(T('pf_star_why',
                    '這個值使用者看得到，或者改之前應該先公告。')) + '">\u2605</span> '
                : '';
            var name = '<td>' + star + esc(s2.label)
                + (s2.overridden ? ' <span class="adm-pill adm-pill--temp">'
                    + esc(T('pf_overridden', '已覆寫')) + '</span>' : '') + '</td>';

            if (!EDITING) {
                return '<tr>' + name
                    + '<td>' + esc(settingValueLabel(s2)) + '</td>'
                    + '<td class="footnote">' + esc(s2.default) + '</td>'
                    + '<td class="footnote">' + esc(range) + '</td></tr>';
            }

            // ZH: 🔴 **只有「已覆寫」的才填值**，其餘留空、用 placeholder 顯示預設。
            //
            // ZH: 原本一律填入生效值，結果按一次「儲存設定」就把**全部 15 個旋鈕
            //     都變成明確覆寫**（實測 11 → 15），連沒碰過的也是 ——
            //     之後改 .env 對它們就再也沒有作用，而且沒有任何提示。
            //
            // ZH: 空白＝跟著預設走，正好是後端的契約（值留空＝清除覆寫）。
            //     所以「回到預設」只要把欄位清空就好，不需要另外記狀態。
            var field = s2.type === 'choice'
                // ZH: 下拉沒辦法「留空」，所以給一個明確的「用預設」選項。
                //     選項由後端給 —— 前端不維護一份模型清單，
                //     不然管理者新增模型之後這裡還是舊的。
                ? cellSelect('v', s2.choices || [], s2.overridden ? s2.value : '',
                             { blankText: T('pf_use_default', '（用預設）'), label: s2.label })
                : cellInput('v', s2.overridden ? s2.value : '', {
                    type: (s2.type === 'int' || s2.type === 'float') ? 'number' : 'text',
                    step: s2.type === 'float' ? '0.01' : null,
                    min: s2.min, max: s2.max, placeholder: s2.default,
                    label: s2.label,
                });
            return '<tr data-key="' + esc(s2.key) + '">' + name + field
                + '<td class="footnote">' + esc(s2.default) + '</td>'
                + '<td class="footnote">' + esc(range) + '</td>'
                + '<td class="num"><button class="btn btn--minor" type="button"'
                + ' data-reset="' + esc(s2.key) + '"' + (s2.overridden ? '' : ' disabled') + '>'
                + esc(T('pf_reset', '回到預設')) + '</button></td></tr>';
        }

        // ZH: 依後端給的順序分區。
        //
        // ZH: 🔴 **不屬於任何已知分組的旋鈕要有地方去**。
        //     後端雖然有自檢擋著（漏標 group 會在匯入時就炸），
        //     但假如前後端版本對不上（例如瀏覽器快取了舊的 JS），
        //     漏接的旋鈕就會**安靜地消失** —— 而那是沒有人會回報的故障。
        //     所以這裡兵分兩路：有分組就按分組，剩下的一律掃進最後一區。
        var known = {};
        GROUPS.forEach(function (g) { known[g.key] = true; });

        // ZH: 只畫屬於目前檢視的分組。view 由後端給（見 crud.SETTING_GROUPS）。
        var shown = GROUPS.filter(function (g) { return g.view === VIEW; });

        // ZH: 不屬於任何**已知分組**的旋鈕才進「其他」；已知但不屬於這個檢視的
        //     不算漏接（它在另一邊）。這兩件事分清楚，否則切到平台時
        //     MYAI 的六個旋鈕會全部跑進「其他」。
        var leftover = SETTINGS.filter(function (x) { return !known[x.group]; });

        var blocks = shown.map(function (g) {
            var rows = SETTINGS.filter(function (x) {
                return x.group === g.key && ALERT_MAIL_KEYS.indexOf(x.key) < 0;
            });
            if (!rows.length) return '';        // 空的分組不畫標題
            return '<h3 class="adm-subhead">' + esc(g.label) + '</h3>'
                 + tableHtml(cols, rows.map(rowHtml).join(''));
        });

        if (leftover.length) {
            blocks.push('<h3 class="adm-subhead">'
                + esc(T('pf_group_other', '其他')) + '</h3>'
                + tableHtml(cols, leftover.map(rowHtml).join('')));
        }

        // ZH: 一個都沒有的話講清楚，不要留一塊空白讓人以為還在載入。
        $('settings').innerHTML = blocks.join('')
            || '<p class="footnote">' + esc(T('pf_no_settings', '目前沒有可調的設定。')) + '</p>';

        wireExternalWarning();

        $('settings').querySelectorAll('[data-reset]').forEach(function (b) {
            b.addEventListener('click', function () {
                // ZH: 🔴 **只清空欄位，不存檔。**
                //     原本是按下去就立刻送出並跳回唯讀 —— 你正在改好幾個欄位，
                //     其中一個按了「回到預設」就把全部一起存掉並踢出編輯模式。
                var tr = b.closest('tr');
                var el = tr && tr.querySelector('[data-f="v"]');
                if (el) { el.value = ''; el.focus(); }
                b.disabled = true;          // 已經是預設了，再按沒有意義
            });
        });
    }

    // ZH: 選了校外供應商就把代價講出來 —— 這是政策決定，不只是換個下拉值。
    //
    // ZH: ⚠ **唯讀時也要顯示**。這條提示講的是「平台現在把使用者的問題送到哪裡」——
    //     那件事在你沒有在編輯的時候同樣成立，而且正是你最需要看到它的時候。
    //     （只在編輯時顯示的話，它就變成一句沒有人會再看到的話。）
    function wireExternalWarning() {
        var row = SETTINGS.filter(function (x) { return x.key === 'rag_chat_model'; })[0];
        if (!row) { $('ext-warn').hidden = true; return; }

        var paint = function (value) {
            var pick = (row.choices || []).filter(function (c) {
                return String(c.value) === String(value);
            })[0];
            $('ext-warn').hidden = !(pick && pick.provider && pick.provider !== 'ollama');
        };

        // ZH: 表格化之後欄位沒有 id 了，靠列上的 data-key 找。
        //     ⚠ 這行漏改的話警語會**靜默失效** —— sel 拿到 null，
        //       就一路走到「唯讀模式」那條分支，編輯中換下拉不再有反應。
        var row2 = $('settings').querySelector('[data-key="rag_chat_model"]');
        var sel = row2 && row2.querySelector('[data-f="v"]');
        if (sel) {
            sel.addEventListener('change', function () { paint(sel.value); });
            paint(sel.value);
        } else {
            paint(row.value);          // 唯讀模式：看目前生效的值
        }
    }

    function paintSettingsButtons() {
        $('s-edit').hidden = EDITING;
        $('s-save').hidden = !EDITING;
        $('s-cancel').hidden = !EDITING;
        $('s-ro-hint').hidden = EDITING;
        // ZH: 「空白＝跟著預設」這條規則要講出來 ——
        //     不講的話，看到一排空欄位的人第一個反應是「資料沒載到」。
        $('s-edit-hint').hidden = !EDITING;
    }

    async function saveSettings(single) {
        var payload = {};
        if (single) {
            payload[single.key] = single.value;
        } else {
            // ZH: 從表格的每一列讀 —— 欄位不再有 `s-<key>` 這種 id，
            //     列上的 data-key 才是它對應哪一個旋鈕。
            $('settings').querySelectorAll('[data-key]').forEach(function (tr) {
                var el = tr.querySelector('[data-f="v"]');
                if (el) payload[tr.dataset.key] = el.value;
            });
        }
        try {
            await api('/admin/system-settings', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });
            flash('s-msg', T('pf_saved', '已儲存'));
            EDITING = false;               // ZH: 存完就收起來，回到唯讀
            await loadSettings();          // ZH: 重讀 —— 後端會夾限，畫面要顯示真正存進去的值
        } catch (e) {
            say('s-msg', T('pf_save_fail', '存不起來（{w}）').replace('{w}', e.message));
        }
    }

    // ── 模型 ──────────────────────────────────────────────────────────────
    //
    // ZH: 跟其他區同一套：唯讀 → 編輯 → 表格內直接改 → 一次儲存。
    //     原本是每一列常駐「編輯／刪除」兩顆鈕，按編輯還另開一個表單面板 ——
    //     同一頁上四個區塊三種改法，使用者每換一區就要重新學一次。
    //
    // ZH: 🔴 儲存只送真的改過的列（與代碼對應同一個理由）。
    var MODELS = null;
    var MODELS_EDIT = false;
    var MODELS_DEL = {};
    var MODELS_NEW = [];
    var MODELS_SEQ = 0;

    // ZH: 🔴 「公開」在畫面上可能是 boolean（剛從後端讀回來）也可能是字串
    //     （使用者剛在下拉裡選過）。**`!!'0'` 是 true**，所以不能直接用 !!
    //     ——比對「有沒有改過」與組 payload 都要先經過這裡。
    function isPub(v) { return v === true || v === 1 || v === '1'; }

    // ZH: 可編的欄位。`model_type` 不在裡面 —— 後端在建立時決定，
    //     改它等於換一種模型，不是編輯。
    var MODEL_FIELDS = ['name', 'api_provider', 'api_model_id', 'api_endpoint', 'description'];

    function paintModelButtons() {
        $('m-edit').hidden = MODELS_EDIT;
        $('m-save').hidden = !MODELS_EDIT;
        $('m-cancel').hidden = !MODELS_EDIT;
        $('m-add').hidden = !MODELS_EDIT;
        $('m-ro-hint').hidden = MODELS_EDIT;
        $('m-edit-hint').hidden = !MODELS_EDIT;
    }

    function modelsExitEdit() {
        MODELS_EDIT = false;
        MODELS_DEL = {};
        MODELS_NEW = [];
    }

    function renderModels() {
        if (!MODELS) return;
        paintModelButtons();

        var rows = (MODELS.items || []).concat(MODELS_NEW);
        if (!rows.length) {
            $('models').innerHTML = '<p class="footnote">'
                + esc(T('pf_m_none', '還沒有任何模型。')) + '</p>';
            wireModelRows();
            return;
        }

        var cols = [['pf_m_name', '名稱'], ['pf_m_type', '類型'], ['pf_m_provider', '供應者'],
                    ['pf_m_id', '模型 ID'], ['pf_m_endpoint', 'API 位址'],
                    ['pf_m_public', '公開'], ['pf_m_desc', '說明']];
        if (MODELS_EDIT) cols = cols.concat([['', '']]);

        $('models').innerHTML = tableHtml(cols,
            rows.map(MODELS_EDIT ? modelRowEdit : modelRowRo).join(''));
        wireModelRows();
    }

    function modelRowRo(m) {
        return '<tr>'
            + '<td>' + esc(m.name) + '</td>'
            + '<td>' + esc(m.model_type || '—') + '</td>'
            + '<td>' + esc(m.api_provider || '—') + '</td>'
            + '<td class="mono">' + esc(m.api_model_id || '—') + '</td>'
            + '<td class="mono">' + esc(m.api_endpoint || '—') + '</td>'
            + '<td>' + esc(isPub(m.is_public) ? T('pf_yes', '是') : T('pf_no', '否')) + '</td>'
            + '<td>' + esc(m.description || '—') + '</td>'
            + '</tr>';
    }

    function modelRowEdit(m) {
        var gone = !!MODELS_DEL[m.id];
        // ZH: aria-label 用「欄位名：這一列是誰」。新增的空白列還沒有名字，
        //     就用「新的一列」——總比三個一樣的「供應者」好分辨。
        var who = m.name || T('pf_m_new_row', '新的一列');
        var lab = function (key, zh) { return { disabled: gone, label: T(key, zh) + '：' + who }; };
        return '<tr class="' + (gone ? 'is-gone' : '') + '" data-row="' + esc(m.id) + '">'
            + cellInput('name', m.name, { disabled: gone, label: T('pf_m_name', '名稱') })
            // ZH: 類型由後端在建立時決定，這裡只顯示不給改。
            + '<td>' + esc(m.model_type || '—') + '</td>'
            + cellInput('api_provider', m.api_provider, lab('pf_m_provider', '供應者'))
            + cellInput('api_model_id', m.api_model_id, lab('pf_m_id', '模型 ID'))
            + cellInput('api_endpoint', m.api_endpoint, lab('pf_m_endpoint', 'API 位址'))
            // ZH: 用下拉不用勾選框，跟 GPU 節點的「狀態」同一個理由：整排都是
            //     輸入框時，一個小方塊看起來像漏做的；而且下拉會把兩個狀態
            //     直接寫出來。選項用的字與唯讀那格**完全一樣**（是／否）——
            //     不一樣的話，同一個值在看與改之間會長成兩種樣子。
            + cellSelect('is_public', [{ value: '1', label: T('pf_yes', '是') },
                                       { value: '0', label: T('pf_no', '否') }],
                         isPub(m.is_public) ? '1' : '0',
                         { blank: false, disabled: gone,
                           label: T('pf_m_public', '公開') + '：' + who })
            + cellInput('description', m.description, lab('pf_m_desc', '說明'))
            + delCell(m.id, gone)
            + '</tr>';
    }

    function wireModelRows() {
        $('models').querySelectorAll('[data-del]').forEach(function (b) {
            b.addEventListener('click', function () {
                var id = b.dataset.del;
                // ZH: 新增的空白列直接拿掉，不必標記 —— 它還不存在於後端。
                if (String(id).indexOf('new-') === 0) {
                    MODELS_NEW = MODELS_NEW.filter(function (x) { return x.id !== id; });
                } else if (MODELS_DEL[id]) {
                    delete MODELS_DEL[id];
                } else {
                    MODELS_DEL[id] = true;
                }
                modelsKeep();       // ZH: 重畫前先收起畫面上的改動，不然會被洗掉
                renderModels();
            });
        });
    }

    function modelsKeep() {
        if (!MODELS_EDIT) return;
        $('models').querySelectorAll('[data-row]').forEach(function (tr) {
            var id = tr.dataset.row;
            var target = (MODELS.items || []).filter(function (x) { return String(x.id) === id; })[0]
                || MODELS_NEW.filter(function (x) { return x.id === id; })[0];
            if (target) readRow(tr, target);
        });
    }

    async function saveModels() {
        modelsKeep();
        var base = MODELS.__base || {};
        var fails = [], writes = 0, dels = 0;

        // ZH: 先刪再寫 —— 若有人刪掉一列又新增同名的，順序反了會把新的刪掉。
        for (var id in MODELS_DEL) {
            try {
                await api('/admin/models/' + encodeURIComponent(id), { method: 'DELETE' });
                dels++;
            } catch (e) {
                fails.push((base[id] ? base[id].name : id) + '：' + e.message);
            }
        }

        var rows = (MODELS.items || []).filter(function (m) { return !MODELS_DEL[m.id]; })
            .concat(MODELS_NEW);
        for (var i = 0; i < rows.length; i++) {
            var m = rows[i];
            var name = (m.name || '').trim();
            // ZH: 新增的空白列沒填名字就當作沒新增，不要攔住整批儲存。
            if (!name) continue;
            var was = base[m.id];
            if (was && MODEL_FIELDS.every(function (f) {
                    return (was[f] || '') === (m[f] || '');
                }) && isPub(was.is_public) === isPub(m.is_public)) continue;   // 沒改就不送
            var body = { name: name, is_public: isPub(m.is_public) };
            MODEL_FIELDS.forEach(function (f) {
                if (f !== 'name') body[f] = (m[f] || '').trim() || null;
            });
            try {
                await api(m.__new ? '/admin/models'
                                  : '/admin/models/' + encodeURIComponent(m.id), {
                    method: m.__new ? 'POST' : 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(body),
                });
                writes++;
            } catch (e) {
                fails.push(name + '：' + e.message);
            }
        }

        if (fails.length) {
            say('m-msg', T('pf_save_fail', '存不起來（{w}）').replace('{w}', fails.join('；')));
        } else {
            flash('m-msg', T('pf_mm_saved', '存好了：改了 {a} 列、刪了 {b} 列。')
                .replace('{a}', writes).replace('{b}', dels));
            modelsExitEdit();
        }
        await loadModels();
    }

    async function loadModels() {
        var list;
        try {
            list = await api('/admin/models');
        } catch (e) {
            $('models').innerHTML = '<p class="footnote">'
                + esc(T('ov_fail_part', '這一段暫時讀不到（{w}）').replace('{w}', e.message)) + '</p>';
            return;
        }
        MODELS = { items: list, __base: {} };
        // ZH: 留一份原樣，儲存時用來比對「哪幾列真的被改過」，
        //     取消時也靠它回復（items 會被編輯中的輸入值就地覆寫）。
        list.forEach(function (m) {
            var b = { is_public: isPub(m.is_public) };
            MODEL_FIELDS.forEach(function (f) { b[f] = m[f] || ''; });
            MODELS.__base[m.id] = b;
        });
        renderModels();
    }

    function schedMode(raw) {
        if (raw == null || raw === '') return 'all';
        var obj = typeof raw === 'string' ? JSON.parse(raw) : raw;
        var any = DAYS.some(function (d) { return (obj[d] || []).length; });
        return any ? 'win' : 'never';
    }

    function schedToText(raw, day) {
        if (raw == null || raw === '') return '';
        var obj = typeof raw === 'string' ? JSON.parse(raw) : raw;
        return (obj[day] || []).map(function (seg) { return seg[0] + '-' + seg[1]; }).join(', ');
    }

    // ZH: 把「18:00-23:00, 08:00-12:00」轉回契約要的 [["18:00","23:00"], …]。
    //     格式不對就丟錯 —— **不要默默忽略**，那會讓管理者以為存好了。
    function textToSegs(text) {
        var out = [];
        String(text || '').split(',').forEach(function (part) {
            var t = part.trim();
            if (!t) return;
            var m = t.match(/^(\d{1,2}:\d{2})\s*-\s*(\d{1,2}:\d{2})$/);
            if (!m) throw new Error(t);
            out.push([m[1], m[2]]);
        });
        return out;
    }

    // ZH: 🔴 **下拉選一台、只畫那一台。**
    //
    // ZH: 原本是每台機器一張卡（後來改成可收合）。兩種都不對，理由是同一個：
    //     總覽已經是「一眼看完所有節點狀態」的地方，這裡再列一次是重複的 ——
    //     而重複的資訊會讓人不確定該信哪一邊，也讓這一頁隨機器數變長。
    //
    // ZH: 這一頁的工作是「調某一台」，所以入口就該是「選一台」。
    //     不管有幾台機器，這一區永遠只有一張卡。
    var NODES = [];

    async function loadNodes(keepId) {
        try {
            NODES = (await api('/admin/gpu-nodes')).nodes || [];
        } catch (e) {
            $('nodes').innerHTML = '<p class="footnote">'
                + esc(T('ov_fail_part', '這一段暫時讀不到（{w}）').replace('{w}', e.message)) + '</p>';
            $('node-card').hidden = true;
            $('n-count').textContent = '';
            return;
        }
        if (!NODES.length) {
            $('nodes').innerHTML = '<p class="footnote">'
                + esc(T('pf_n_none', '沒有任何節點回報過心跳。')) + '</p>';
            $('node-card').hidden = true;
            $('n-count').textContent = '';
            return;
        }
        $('nodes').innerHTML = '';        // ZH: 清掉骨架／錯誤訊息
        $('node-card').hidden = false;
        $('n-count').textContent = T('pf_n_count', '{n} 台機器').replace('{n}', NODES.length);

        // ZH: 存檔後要停在同一台，不要跳回第一台 ——
        //     連續調同一台的兩個設定是很常見的動作。
        var fromHash = hashNodeId();
        var want = keepId || fromHash || NODES[0].node_id;
        renderNodePicker(want);
        renderNodeForm(want);

    }

    function hashNodeId() {
        // ZH: 從總覽的 GPU 卡片連過來：platform.html#node-<id>
        var h = decodeURIComponent((location.hash || '').replace(/^#node-/, '').replace(/^#/, ''));
        return h && NODES.some(function (n) { return n.node_id === h; }) ? h : '';
    }

    function renderNodePicker(current) {
        $('node-pick').innerHTML = NODES.map(function (n) {
            // ZH: 只放名字。狀態／池別／張數**刻意不放** ——
            //     那些總覽已經有了，在這裡重複只會讓人不確定該信哪一邊。
            return '<option value="' + esc(n.node_id) + '"'
                + (n.node_id === current ? ' selected' : '') + '>'
                + esc(n.display_name ? n.display_name + '（' + n.node_id + '）' : n.node_id)
                + '</option>';
        }).join('');
    }

    // ZH: 只重畫 #node-body —— 卡片外殼與下拉留在原地，換節點時焦點不會掉。
    // ZH: 跟這一頁其他區一樣：預設唯讀。這一區尤其需要 —— 七天的時段輸入框
    //     常駐的話，捲頁時滑鼠停在上面就可能改到，而改錯的後果是那台機器
    //     整天不派任務，而且不會有人來通報。
    var NODE_EDIT = false;

    function paintNodeButtons() {
        $('n-edit').hidden = NODE_EDIT;
        $('n-cancel').hidden = !NODE_EDIT;
        $('n-ro-hint').hidden = NODE_EDIT;
    }

    // ZH: 唯讀時把設定用「名稱 / 值」列出來，跟營運設定那區同一個長相。
    function nodeRo(n, mode) {
        var kv = function (k, v) {
            return '<div class="adm-setting adm-setting--ro">'
                + '<span class="adm-setting__label">' + esc(k) + '</span>'
                + '<span class="adm-setting__ro">' + esc(v) + '</span></div>';
        };
        var modeText = { all: T('pf_n_mode_all', '全天可用'),
                         win: T('pf_n_mode_win', '依時段'),
                         never: T('pf_n_mode_never', '永不可用') }[mode] || mode;
        var out = kv(T('pf_n_name', '顯示名稱'), n.display_name || '—')
            + kv(T('pf_n_note', '備註'), n.note || '—')
            + kv(T('pf_n_state', '狀態'),
                 n.enabled ? T('pf_n_enabled', '啟用') : T('pf_n_disabled', '停用'))
            + kv(T('pf_n_pool', '池別覆寫'),
                 n.pool_override || T('pf_n_pool_auto', '（跟著節點回報）'))
            + kv(T('pf_n_buffer', '收工緩衝（分）'),
                 n.dispatch_buffer_min == null ? '0' : n.dispatch_buffer_min)
            + kv(T('pf_n_mode', '開放方式'), modeText);

        // ZH: 只有「依時段」才列七天 —— 其他兩種模式下那七行是誤導。
        if (mode === 'win') {
            out += DAYS.map(function (d) {
                return kv(T('d_' + d, d), schedToText(n.schedule, d)
                    || T('pf_n_day_off', '不開放'));
            }).join('');
        }
        return out;
    }

    function renderNodeForm(nodeId) {
        var n = NODES.filter(function (x) { return x.node_id === nodeId; })[0];
        if (!n) { $('node-body').innerHTML = ''; return; }
        var mode = schedMode(n.schedule);
        paintNodeButtons();

        // ZH: 撞名在兩種模式下都要顯示 —— 它是「現在有問題」，
        //     不是只有在編輯時才成立的事。
        var conflict = n.ip_conflict
            ? '<div class="adm-alert adm-alert--error"><span>'
                + esc(T('pf_n_conflict', '🔴 這個 NODE_ID 有兩台機器在用。')) + '</span></div>'
            : '';

        if (!NODE_EDIT) {
            $('node-body').innerHTML = conflict + nodeRo(n, mode)
                + '<div class="inline-error" id="n-msg" hidden></div>';
            return;
        }

        $('node-body').innerHTML = ''

            // ZH: 撞名是設定問題，而且要在這一頁修（改其中一台的 NODE_ID），
            //     所以留在這一區；上面的 conflict 變數兩種模式共用。
            + conflict

            + '<div class="adm-cols">'
            + '<div>'
            + fieldRow('n-name', T('pf_n_name', '顯示名稱'), n.display_name || '')
            + fieldRow('n-note', T('pf_n_note', '備註'), n.note || '')
            // ZH: 用下拉不用勾選框。這張卡其他欄位都是整行寬的輸入框與下拉，
            //     只有它是一個小方塊，看起來像漏做的；而且勾選框的「勾／沒勾」
            //     要靠讀標籤才知道是哪一邊，下拉直接把兩個狀態寫出來。
            + '<label class="field"><span class="field__label" for="n-on">'
            + esc(T('pf_n_state', '狀態')) + '</span>'
            + '<select class="field__input" id="n-on">'
            + [['1', T('pf_n_enabled', '啟用')], ['0', T('pf_n_disabled', '停用')]]
                .map(function (o) {
                    return '<option value="' + o[0] + '"'
                        + ((n.enabled ? '1' : '0') === o[0] ? ' selected' : '') + '>'
                        + esc(o[1]) + '</option>';
                }).join('')
            + '</select></label>'
            + '<label class="field"><span class="field__label" for="n-pool">'
            + esc(T('pf_n_pool', '池別覆寫')) + '</span>'
            + '<select class="field__input" id="n-pool">'
            + ['', 'batch', 'interactive'].map(function (p) {
                return '<option value="' + p + '"' + (n.pool_override === p ? ' selected' : '') + '>'
                    + esc(p || T('pf_n_pool_auto', '（跟著節點回報）')) + '</option>';
            }).join('')
            + '</select></label>'
            + fieldRow('n-buf', T('pf_n_buffer', '收工緩衝（分）'),
                       n.dispatch_buffer_min == null ? '' : n.dispatch_buffer_min, 'number')
            + '<p class="footnote">' + esc(T('pf_n_buffer_hint',
                '時段結束前這麼多分鐘就不再派新任務，讓正在跑的有時間收尾。')) + '</p>'
            + '</div>'

            + '<div>'
            + '<label class="field"><span class="field__label" for="n-mode">'
            + esc(T('pf_n_mode', '開放方式')) + '</span>'
            + '<select class="field__input" id="n-mode">'
            + [['all', T('pf_n_mode_all', '全天可用')],
               ['win', T('pf_n_mode_win', '依時段')],
               ['never', T('pf_n_mode_never', '永不可用')]].map(function (o) {
                return '<option value="' + o[0] + '"' + (mode === o[0] ? ' selected' : '') + '>'
                    + esc(o[1]) + '</option>';
            }).join('')
            + '</select></label>'
            + '<div class="adm-days" id="n-days"' + (mode === 'win' ? '' : ' hidden') + '>'
            + DAYS.map(function (d) {
                return '<label class="adm-day">'
                    + '<span>' + esc(T('d_' + d, d)) + '</span>'
                    + '<input class="field__input" id="n-' + d
                    + '" type="text" value="' + esc(schedToText(n.schedule, d)) + '">'
                    + '</label>';
            }).join('')
            + '<p class="footnote">' + esc(T('pf_n_sched_hint',
                '每一天可以填多段，用逗號分開，例如「18:00-23:00, 08:00-12:00」。空白＝那天不開放。')) + '</p>'
            + '<p class="footnote">' + esc(T('pf_n_overnight',
                '結束時間比開始早＝跨夜，例如 22:00-02:00。')) + '</p>'
            + '</div>'
            + '</div>'
            + '</div>'

            + '<div class="ds__actions">'
            + '<button class="btn btn--primary" type="button" id="n-save">'
            + esc(T('pf_n_save', '儲存這個節點')) + '</button>'
            + '</div>'
            + '<div class="inline-error" id="n-msg" hidden></div>';

        // ZH: 切「依時段」才顯示七天的輸入 —— 選「全天」時那七格是誤導。
        $('n-mode').addEventListener('change', function (ev) {
            $('n-days').hidden = (ev.target.value !== 'win');
        });
        $('n-save').addEventListener('click', function () { saveNode(n); });
    }

    function fieldRow(id, label, value, type) {
        return '<label class="field">'
            + '<span class="field__label" for="' + id + '">' + esc(label) + '</span>'
            + '<input class="field__input" id="' + id + '" type="' + (type || 'text') + '"'
            + ' value="' + esc(value) + '"></label>';
    }

    async function saveNode(n) {
        var mode = $('n-mode').value;
        var schedule;

        if (mode === 'all') {
            schedule = null;                    // ZH: null = 全天可排
        } else if (mode === 'never') {
            schedule = {};                      // ZH: 空 dict = 永不（與 null 相反，見上方註解）
        } else {
            schedule = {};
            try {
                DAYS.forEach(function (d) {
                    var segs = textToSegs($('n-' + d).value);
                    if (segs.length) schedule[d] = segs;
                });
            } catch (bad) {
                say('n-msg', T('pf_n_sched_bad', '時段格式看不懂：{w}').replace('{w}', bad.message));
                return;
            }
            // ZH: 選了「依時段」卻一段都沒填 —— 那在契約上等於「永不」。
            //     這很可能不是他的本意，所以擋下來問清楚，不要默默關掉一台機器。
            if (!Object.keys(schedule).length) {
                say('n-msg', T('pf_n_mode_never', '永不可用') + '？');
                return;
            }
        }

        var buf = $('n-buf').value.trim();
        var payload = {
            display_name: $('n-name').value.trim(),
            note: $('n-note').value.trim(),
            // ZH: 下拉的值是字串，不是 boolean —— 直接送 '0' 過去會被當成真。
            enabled: $('n-on').value === '1',
            pool_override: $('n-pool').value || null,
            schedule: schedule,
        };
        if (buf !== '') payload.dispatch_buffer_min = parseInt(buf, 10);

        try {
            await api('/admin/gpu-nodes/' + encodeURIComponent(n.node_id), {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });
            // ZH: 重讀 —— 後端會回算 state 與 next_change。
            //     ⚠ 帶著 node_id 重讀，**停在同一台**：跳回第一台的話，
            //       連續調同一台的兩個設定會變成每次都要重選。
            // ⚠ ZH: 順序不能反。loadNodes 會重畫表單，所以旗標要先放掉 ——
            //     放在後面的話，重畫時 NODE_EDIT 還是 true，畫面停在編輯模式，
            //     那一行等於沒有作用。
            NODE_EDIT = false;
            await loadNodes(n.node_id);
            // ZH: #n-msg 在 node-body 裡、剛被重畫過，所以要在重讀之後才 flash。
            flash('n-msg', T('pf_saved', '已儲存'));
        } catch (e) {
            say('n-msg', e.message);
        }
    }

    // ── 啟動 ──────────────────────────────────────────────────────────────
    $('s-edit').addEventListener('click', function () {
        EDITING = true;
        say('s-msg', '');
        renderSettings();
    });
    $('s-cancel').addEventListener('click', function () {
        // ZH: 取消要**丟掉改動**。從 SETTINGS 重畫即可 ——
        //     那份資料是上次從後端讀回來的，沒有被編輯過。
        EDITING = false;
        say('s-msg', '');
        renderSettings();
    });
    $('s-save').addEventListener('click', function () { saveSettings(null); });

    // ZH: 告警信那一格。與其他區同一套：唯讀 → 編輯 → 就地改 → 一次儲存。
    //     取消是從 SETTINGS 重畫（那份資料沒有被編輯過），所以改動自然被丟掉。
    $('am-edit').addEventListener('click', function () {
        AM_EDITING = true;
        say('am-msg', '');
        renderAlertMail();
    });
    $('am-cancel').addEventListener('click', function () {
        AM_EDITING = false;
        say('am-msg', '');
        renderAlertMail();
    });
    $('am-save').addEventListener('click', function () { saveAlertMail(); });
    $('m-edit').addEventListener('click', function () {
        MODELS_EDIT = true;
        say('m-msg', '');
        renderModels();
    });
    $('m-cancel').addEventListener('click', function () {
        // ZH: 取消要丟掉改動。MODELS.items 在編輯中被就地覆寫過，
        //     所以不能只重畫 —— 要重讀後端那一份原樣。
        modelsExitEdit();
        say('m-msg', '');
        loadModels();
    });
    $('m-save').addEventListener('click', saveModels);
    $('m-add').addEventListener('click', function () {
        modelsKeep();
        MODELS_NEW.push({ id: 'new-' + (++MODELS_SEQ), __new: true, is_public: false,
                          name: '', api_provider: '', api_model_id: '',
                          api_endpoint: '', description: '' });
        renderModels();
        var last = $('models').querySelector('tr:last-child [data-f="name"]');
        if (last) last.focus();
    });

    $('x-edit').addEventListener('click', function () {
        EXT_EDIT = true;
        say('x-msg', '');
        renderExt();
    });
    $('x-cancel').addEventListener('click', function () {
        // ZH: 取消要丟掉改動。EXT 是上次從後端讀回來的，重畫即可。
        EXT_EDIT = false;
        say('x-msg', '');
        renderExt();
    });
    $('x-save').addEventListener('click', saveExt);
    $('mm-edit').addEventListener('click', function () {
        MAP_EDIT = true;
        say('mm-msg', '');
        renderMap();
    });
    $('mm-cancel').addEventListener('click', function () {
        // ZH: 取消要丟掉改動。MAP.items 在編輯中被就地覆寫過，
        //     所以不能只重畫 —— 要重讀後端那一份原樣。
        mapExitEdit();
        say('mm-msg', '');
        loadMap();
    });
    $('mm-save').addEventListener('click', saveMap);
    $('mm-add').addEventListener('click', function () {
        mapKeep();
        MAP_NEW.push({ id: 'new-' + (++MAP_SEQ), __new: true,
                       code: '', display_name: '', provider: '', category: '' });
        renderMap();
        // ZH: 新的一列出現在最後面，焦點直接進去 —— 不然使用者要自己捲下去找。
        var last = $('mm-list').querySelector('tr:last-child [data-f="code"]');
        if (last) last.focus();
    });

    // ZH: 換一台就重畫那張卡。不重讀後端 —— NODES 是剛拿的，
    //     再打一次 API 只會讓切換變慢。
    $('node-pick').addEventListener('change', function (ev) {
        // ZH: 換一台就退出編輯。不退的話，畫面會用**新節點的值**重畫成編輯中，
        //     剛才在前一台改到一半的東西無聲消失；更糟的是你會以為自己還在
        //     編輯原來那一台。
        NODE_EDIT = false;
        renderNodeForm(ev.target.value);
    });

    $('n-edit').addEventListener('click', function () {
        NODE_EDIT = true;
        renderNodeForm($('node-pick').value);
    });
    $('n-cancel').addEventListener('click', function () {
        // ZH: 取消要丟掉改動。NODES 是上次從後端讀回來的，重畫即可。
        NODE_EDIT = false;
        renderNodeForm($('node-pick').value);
    });

    // ZH: 🔴 從總覽的 GPU 卡片連過來時要**捲到 GPU 節點那一區**。
    //     只把下拉選好而不捲的話，你會停在頁面最上方的「營運設定」，
    //     完全看不出剛才那個連結做了什麼 —— 連結等於只做了一半。
    //
    // ZH: ⚠ 時序：三段是平行載入的。在 loadNodes 裡捲的話，
    //     營運設定的 15 列可能**之後**才畫在它上方，把版面撐開 ——
    //     捲是捲了，但停在錯的位置。所以要等三段都就位。
    //
    // ZH: ⚠ 只在**第一次**捲。語言切換也會重跑 loadAll，
    //     每次都把人拉到 GPU 節點會很煩。
    var scrolled = false;


    // ── 外部 AI：連線設定 ─────────────────────────────────────────────────
    //
    // ZH: 跟營運設定一樣預設唯讀 —— 這四個值一年也改不了幾次，
    //     常駐輸入框只會招來誤觸。
    //
    // ZH: ⚠ 這四個值走的是**兩個端點**（url 與 alert-config），
    //     所以儲存要送兩次。任一失敗就把哪一段失敗講出來，
    //     不要只說「存不起來」——另一半可能已經存進去了。
    var EXT = null;
    var EXT_EDIT = false;

    var EXT_FIELDS = [
        ['url', 'pf_ext_url', '平台網址', 'text', 'pf_ext_url_why',
         '留空＝平台上不顯示外部 AI 的入口。'],
        ['logout_url', 'pf_ext_logout', '廠商登出網址', 'text', 'pf_ext_logout_why',
         '共用機台換手時用它殺掉廠商那邊的登入狀態。'],
        ['low_balance_threshold', 'pf_ext_thr', '低點數提醒門檻', 'number', 'pf_ext_thr_why',
         '學生點數低於這個數字就在平台內提醒，每次登入只提醒一次。'],
        ['apply_guide_url', 'pf_ext_guide', '申請教學連結', 'text', 'pf_ext_guide_why',
         '顯示在低點數提醒裡。可以留空。'],
    ];

    function paintExtButtons() {
        $('x-edit').hidden = EXT_EDIT;
        $('x-save').hidden = !EXT_EDIT;
        $('x-cancel').hidden = !EXT_EDIT;
        $('x-ro-hint').hidden = EXT_EDIT;
    }

    function renderExt() {
        paintExtButtons();
        if (!EXT) return;

        var cols = [['pf_s_name', '設定'], ['pf_s_value', '值'], ['pf_s_note', '說明']];
        $('ext-conn').innerHTML = tableHtml(cols, EXT_FIELDS.map(function (f) {
            var v = EXT[f[0]];
            var name = '<td>' + esc(T(f[1], f[2])) + '</td>';
            var note = '<td class="footnote">' + esc(T(f[4], f[5])) + '</td>';
            return '<tr data-key="' + esc(f[0]) + '">' + name
                + (EDIT_OFF(f, v))
                + note + '</tr>';
        }).join(''));
    }

    // ZH: 唯讀時空值要明講「沒有設定」—— 一片空白看起來像沒載到。
    function EDIT_OFF(f, v) {
        if (!EXT_EDIT) {
            return '<td>' + esc(v === '' || v == null
                ? T('pf_ext_unset', '（沒有設定）') : v) + '</td>';
        }
        return cellInput('v', v, { type: f[3], min: f[3] === 'number' ? 0 : null,
                                   label: T(f[1], f[2]) });
    }

    async function loadExt() {
        try {
            var two = await Promise.all([
                api('/external-ai/admin/url'),
                api('/external-ai/admin/alert-config'),
            ]);
            EXT = Object.assign({}, two[0], two[1]);
            renderExt();
        } catch (e) {
            say('x-msg', T('pf_ext_fail', '讀不到外部 AI 的設定（{w}）').replace('{w}', e.message));
        }
    }

    async function saveExt() {
        // ZH: 表格化之後欄位沒有 id 了，靠列上的 data-key 找。
        var get = function (k) {
            var tr = $('ext-conn').querySelector('[data-key="' + k + '"]');
            var el = tr && tr.querySelector('[data-f="v"]');
            return el ? el.value.trim() : '';
        };
        var failed = [];
        try {
            await api('/external-ai/admin/url', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ url: get('url'), logout_url: get('logout_url') }),
            });
        } catch (e) { failed.push(T('pf_ext_conn', '連線設定') + '：' + e.message); }
        try {
            var thr = get('low_balance_threshold');
            await api('/external-ai/admin/alert-config', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    // ZH: 空字串送過去會變成 0（等於關掉提醒）。留空就不動這個值。
                    low_balance_threshold: thr === '' ? null : Number(thr),
                    apply_guide_url: get('apply_guide_url'),
                }),
            });
        } catch (e) { failed.push(T('pf_ext_thr', '低點數提醒門檻') + '：' + e.message); }

        if (failed.length) {
            say('x-msg', T('pf_save_fail', '存不起來（{w}）').replace('{w}', failed.join('；')));
        } else {
            flash('x-msg', T('pf_saved', '已儲存'));
            EXT_EDIT = false;
        }
        await loadExt();       // ZH: 不論成敗都重讀 —— 畫面要顯示真正存進去的值
    }

    // ── 外部 AI：廠商模型代碼對應 ─────────────────────────────────────────
    //
    // ZH: 跟營運設定同一套：**預設唯讀，按「編輯設定」才變成可填的欄位，
    //     改完一次儲存。** 這裡的理由比營運設定更強 —— 三十幾列各有三個欄位，
    //     常駐就是上百個輸入框，而且捲頁時滑鼠停在下拉上滾輪就會把值改掉。
    //
    // ZH: 🔴 儲存時**只送真的改過的列**。全部重送的話，一次按下去就是三十幾個
    //     寫入請求，而且每一列的 updated 時間都會被動到 —— 之後想查「誰動過
    //     哪一列」就再也看不出來。
    var MAP = null;
    var MAP_EDIT = false;
    var MAP_DEL = {};        // ZH: 標記要刪的列（id → true），按儲存才真的刪
    var MAP_NEW = [];        // ZH: 編輯中新增的空白列（尚未寫入後端）
    var MAP_SEQ = 0;

    function paintMapButtons() {
        $('mm-edit').hidden = MAP_EDIT;
        $('mm-save').hidden = !MAP_EDIT;
        $('mm-cancel').hidden = !MAP_EDIT;
        $('mm-add').hidden = !MAP_EDIT;
        $('mm-ro-hint').hidden = MAP_EDIT;
        $('mm-edit-hint').hidden = !MAP_EDIT;
    }

    // ZH: ⚠ 這裡**不清訊息**。存檔成功時是先 flash 再呼叫它 ——
    //     在這裡清掉的話，剛設好的「存好了」會被自己抹掉，
    //     使用者按了儲存卻什麼都沒看到。要清的地方自己清。
    function mapExitEdit() {
        MAP_EDIT = false;
        MAP_DEL = {};
        MAP_NEW = [];
    }

    function renderMap() {
        if (!MAP) return;
        paintMapButtons();

        // ZH: 沒對應到的先講 —— 數據那一頁會用原始代碼顯示，
        //     那看起來像壞掉，其實是這裡少一列。
        //
        // ZH: 「全部帶入建議值」在編輯中**不顯示**：它會立刻寫入並重讀，
        //     手上還沒存的改動會被沖掉。
        var un = MAP.unmapped || [];
        $('mm-unmapped').innerHTML = !un.length
            ? '<p class="footnote">' + esc(T('pf_mm_none', '交易裡出現過的代碼都對應好了。')) + '</p>'
            : '<div class="adm-alert adm-alert--warn">'
                + '<span>' + esc(T('pf_mm_unmapped', '有 {n} 個代碼還沒對應，「數據」那一頁會直接顯示原始代碼。')
                    .replace('{n}', un.length)) + '</span>'
                + (MAP_EDIT ? '' : '<button class="btn btn--minor" type="button" id="mm-seed">'
                    + esc(T('pf_mm_seed', '全部帶入建議值')) + '</button>')
                + '</div>'
                + '<ul class="adm-pie__legend">' + un.map(function (u) {
                    return '<li class="adm-pie__row">'
                        + '<span class="adm-pie__name"><code>' + esc(u.code) + '</code></span>'
                        + '<span class="adm-pie__val">' + esc(u.display_name || '') + '</span>'
                        + '<span class="adm-pie__pct">'
                        + esc(T('pf_mm_tx_n', '{n} 筆').replace('{n}', num(u.tx_count))) + '</span>'
                        + '</li>';
                }).join('') + '</ul>';

        var rows = (MAP.items || []).concat(MAP_NEW);
        if (!rows.length) {
            $('mm-list').innerHTML = '<p class="footnote">'
                + esc(T('pf_mm_empty', '還沒有任何對應。')) + '</p>';
            wireMapRows();
            return;
        }

        var cols = [['pf_mm_code', '廠商原始代碼'], ['pf_mm_name', '顯示名稱'],
                    ['pf_m_provider', '供應者'], ['pf_mm_cat', '類別'],
                    ['pf_mm_tx', '交易筆數']];
        $('mm-list').innerHTML =
            '<div class="adm-tablewrap"><table class="adm-table"><thead><tr>'
            + cols.map(function (h) { return '<th>' + esc(T(h[0], h[1])) + '</th>'; }).join('')
            + (MAP_EDIT ? '<th></th>' : '')
            + '</tr></thead><tbody>'
            + rows.map(MAP_EDIT ? mapRowEdit : mapRowRo).join('')
            + '</tbody></table></div>';

        wireMapRows();
    }

    function mapRowRo(r) {
        return '<tr>'
            + '<td><code>' + esc(r.code) + '</code></td>'
            + '<td>' + esc(r.display_name || '—') + '</td>'
            + '<td>' + esc(r.provider || '—') + '</td>'
            + '<td>' + esc(r.category || '—') + '</td>'
            // ZH: 沒出現過的列標出來 —— 多半是打錯字或廠商改了代碼。留著不會有害，
            //     但知道它沒在用比較好判斷要不要刪。
            + '<td class="num">' + (r.seen ? esc(num(r.tx_count))
                : '<span class="footnote">' + esc(T('pf_mm_unseen', '沒出現過')) + '</span>') + '</td>'
            + '</tr>';
    }

    function mapRowEdit(r) {
        var id = r.id;
        var gone = !!MAP_DEL[id];
        var opt = function (list, val) {
            return '<option value="">' + esc(T('pf_mm_blank', '（不指定）')) + '</option>'
                + (list || []).map(function (o) {
                    return '<option value="' + esc(o) + '"'
                        + (String(val || '') === String(o) ? ' selected' : '') + '>'
                        + esc(o) + '</option>';
                }).join('');
        };
        return '<tr class="' + (gone ? 'is-gone' : '') + '" data-row="' + esc(id) + '">'
            // ZH: 代碼是這張表的鍵，改了等於換一列。已存在的就不給改，
            //     只有編輯中新增的空白列可以填。
            // ZH: aria-label 用「欄位名：這一列是誰」。只寫欄位名的話，
            //     三十幾列會有三十幾個一模一樣的「顯示名稱」，分不出是哪一列。
            + '<td>' + (r.__new
                ? '<input class="field__input" data-f="code" value="' + esc(r.code || '') + '"'
                    + ' aria-label="' + esc(T('pf_mm_code', '廠商原始代碼')) + '"'
                    + ' placeholder="' + esc(T('pf_mm_code', '廠商原始代碼')) + '">'
                : '<code>' + esc(r.code) + '</code>') + '</td>'
            + '<td><input class="field__input" data-f="display_name" value="'
            + esc(r.display_name || '') + '"'
            + ' aria-label="' + esc(T('pf_mm_name', '顯示名稱') + '：' + (r.code || '')) + '"'
            + (gone ? ' disabled' : '') + '></td>'
            + '<td><select class="field__input" data-f="provider"'
            + ' aria-label="' + esc(T('pf_m_provider', '供應者') + '：' + (r.code || '')) + '"'
            + (gone ? ' disabled' : '') + '>'
            + opt(MAP.providers, r.provider) + '</select></td>'
            + '<td><select class="field__input" data-f="category"'
            + ' aria-label="' + esc(T('pf_mm_cat', '類別') + '：' + (r.code || '')) + '"'
            + (gone ? ' disabled' : '') + '>'
            + opt(MAP.categories, r.category) + '</select></td>'
            + '<td class="num">' + (r.__new ? '—' : (r.seen ? esc(num(r.tx_count))
                : '<span class="footnote">' + esc(T('pf_mm_unseen', '沒出現過')) + '</span>')) + '</td>'
            + '<td class="num"><button class="btn btn--minor" type="button" data-mm-del="' + esc(id) + '">'
            // ZH: 刪除在編輯中只是**標記**，按「儲存設定」才真的送出 ——
            //     跟其他欄位同一個節奏，按錯了「取消」就全部回復。
            + esc(gone ? T('pf_mm_undel', '不刪了') : T('pf_m_del', '刪除')) + '</button></td>'
            + '</tr>';
    }

    function wireMapRows() {
        var seed = $('mm-seed');
        if (seed) seed.addEventListener('click', seedMap);
        $('mm-list').querySelectorAll('[data-mm-del]').forEach(function (b) {
            b.addEventListener('click', function () {
                var id = b.dataset.mmDel;
                // ZH: 新增的空白列直接拿掉，不必標記 —— 它還不存在於後端。
                if (id.indexOf('new-') === 0) {
                    MAP_NEW = MAP_NEW.filter(function (x) { return x.id !== id; });
                } else if (MAP_DEL[id]) {
                    delete MAP_DEL[id];
                } else {
                    MAP_DEL[id] = true;
                }
                mapKeep();          // ZH: 重畫前先把畫面上的改動收起來，不然會被洗掉
                renderMap();
            });
        });
    }

    // ZH: 把畫面上的輸入值寫回 MAP / MAP_NEW。
    //     重畫（例如按了刪除）之前一定要先做，否則使用者剛打的字會不見。
    function mapKeep() {
        if (!MAP_EDIT) return;
        $('mm-list').querySelectorAll('[data-row]').forEach(function (tr) {
            var id = tr.dataset.row;
            var target = (MAP.items || []).filter(function (x) { return x.id === id; })[0]
                || MAP_NEW.filter(function (x) { return x.id === id; })[0];
            if (!target) return;
            tr.querySelectorAll('[data-f]').forEach(function (el) {
                target[el.dataset.f] = el.value;
            });
        });
    }

    async function saveMap() {
        mapKeep();
        var base = MAP.__base || {};
        var fails = [], writes = 0, dels = 0;

        // ZH: 先刪再寫 —— 若有人刪掉某列又新增同一個代碼，順序反了會把新的刪掉。
        for (var id in MAP_DEL) {
            try {
                await api('/external-ai/admin/model-map/' + encodeURIComponent(id), { method: 'DELETE' });
                dels++;
            } catch (e) {
                fails.push((base[id] ? base[id].code : id) + '：' + e.message);
            }
        }

        var rows = (MAP.items || []).filter(function (r) { return !MAP_DEL[r.id]; })
            .concat(MAP_NEW);
        for (var i = 0; i < rows.length; i++) {
            var r = rows[i];
            var code = (r.code || '').trim();
            // ZH: 新增的空白列沒填代碼就當作沒新增，不要跳錯誤攔住整批儲存。
            if (!code) continue;
            var was = base[r.id];
            if (was && was.display_name === (r.display_name || '')
                && was.provider === (r.provider || '')
                && was.category === (r.category || '')) continue;   // 沒改就不送
            try {
                await api('/external-ai/admin/model-map', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        code: code,
                        display_name: r.display_name || '',
                        provider: r.provider || '',
                        category: r.category || '',
                    }),
                });
                writes++;
            } catch (e) {
                fails.push(code + '：' + e.message);
            }
        }

        if (fails.length) {
            say('mm-msg', T('pf_save_fail', '存不起來（{w}）').replace('{w}', fails.join('；')));
        } else {
            flash('mm-msg', T('pf_mm_saved', '存好了：改了 {a} 列、刪了 {b} 列。')
                .replace('{a}', writes).replace('{b}', dels));
            mapExitEdit();
        }
        await loadMap();       // ZH: 不論成敗都重讀 —— 畫面要顯示真正存進去的樣子
    }

    async function seedMap() {
        try {
            var r = await api('/external-ai/admin/model-map/seed', { method: 'POST' });
            flash('mm-msg', T('pf_mm_seeded', '帶入了 {n} 筆，記得檢查一下名字。')
                .replace('{n}', r && r.created));
            await loadMap();
        } catch (e) {
            say('mm-msg', T('pf_save_fail', '存不起來（{w}）').replace('{w}', e.message));
        }
    }

    async function loadMap() {
        try {
            MAP = await api('/external-ai/admin/model-map');
            // ZH: 留一份原樣，儲存時用來比對「哪幾列真的被改過」，
            //     取消時也靠它回復（items 會被編輯中的輸入值就地覆寫）。
            MAP.__base = {};
            (MAP.items || []).forEach(function (r) {
                MAP.__base[r.id] = {
                    code: r.code,
                    display_name: r.display_name || '',
                    provider: r.provider || '',
                    category: r.category || '',
                };
            });
            renderMap();
        } catch (e) {
            say('mm-msg', T('pf_mm_fail', '讀不到對應表（{w}）').replace('{w}', e.message));
        }
    }

    function scrollToHash() {
        if (scrolled) return;
        // ZH: ⚠ 這行原本寫成 `!(...).indexOf('#node-') === 0` ——
        //     運算優先序讓它**永遠是 false**，於是直接打開這一頁也會被拉到 GPU 節點。
        //     （用 node 實際跑過三種 hash 才確認的，不是看出來的。）
        if ((location.hash || '').indexOf('#node-') !== 0) return;
        var el = $('h-nodes');
        if (!el) return;
        scrolled = true;

        // ZH: 🔴 原本是「等一次 rAF 再捲」—— 實測**完全不會捲**（scrollY 全程 0）。
        //     這是旧缺陷，不是檢視滑條造成的：我用 git stash 退回上一個 commit
        //     量過，那邊也是 0。
        //
        // ZH: 兩個都說得通的原因，而且**同一個修法對兩者都成立**：
        //       a. rAF 那一刻版面還在長（各區塊剛換掉骷架），
        //          scrollIntoView 算出來的目標就是 0。
        //       b. history.scrollRestoration 是 'auto'，重新整理時瀏覽器會在
        //          我們捲完**之後**把位置還原成 0。
        //
        // ZH: 所以改成「捲了再確認」：位置還在變就再捲一次，
        //     穩下來就停。次數有上限 —— 不要寫成沒有出口的迴圈，
        //     那會變成使用者捲不動頁面（比沒捲到更糟）。
        var tries = 0;
        var lastY = -1;
        (function settle() {
            el.scrollIntoView({ block: 'start' });
            var y = Math.round(window.scrollY);
            if (++tries < 6 && y !== lastY) {
                lastY = y;
                setTimeout(settle, 120);
            }
        })();
    }

    async function loadAll() {
        await Promise.all([loadSettings(), loadModels(), loadNodes(), loadExt(), loadMap()]);
        scrollToHash();
    }

    // ZH: 滑條要先接、且**在 loadAll 之前** —— 它會把不屬於目前檢視的區塊收起來。
    //     放後面的話，畫面會先閃過「全部區塊都在」再收合。
    wireViewSeg();
    loadAll();
    document.addEventListener('prefs:langchanged', loadAll);
})();
