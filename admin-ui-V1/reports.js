/* ==========================================================================
 * reports.js — 回報（回答問題時要查的東西）
 *
 * ZH: 這一頁的使用時機：**有人問了問題，你要回答他**。
 *     三段資料都是為了那件事：
 *       GET/PUT /admin/reports    他問了什麼、你怎麼回
 *       GET /admin/email-log      「我沒收到信」——是真的沒寄，還是退信了？
 *       GET /admin/audit          「我的額度怎麼變了」——誰動的、什麼時候
 *
 * ZH: 舊版把寄信紀錄與稽核放在別的地方，於是回答一個問題要跳三個分頁。
 *     它們單獨看都沒什麼意思，是**回答問題時**才有用。
 *
 * ⚠ 回覆使用者**刻意不寄通知信**（既有設計）。畫面上要講出來，
 *   不然管理者會以為對方馬上會收到提醒。
 * ========================================================================== */
(function () {
    'use strict';

    var API = '/api/v1';
    var STATUSES = ['open', 'in_progress', 'resolved'];

    var FILTER = 'open';       // ZH: 預設看「待處理」—— 打開這一頁通常是為了處理事情
    // ZH: v3.9 類別篩選。'' = 全部。與狀態篩選**分開**：兩者是不同的問題
    //     （「還沒處理的」與「關於額度的」），合成一排會變成十幾顆按鈕。
    var REPORTS = [];

    // ── 分頁（v4.41，擁有者 2026-10-10：寄信紀錄與管理動作 10 條一頁）────────
    // ZH: v4.45 回報清單與「全部公告」也用同一個數字（計畫第 4 節「訊息」：回報加上分頁）。
    //     一頁裡三種每頁筆數的話，換區時要重新適應「這裡一頁有幾筆」。
    // ZH: 頁碼一律**從 1 算**（AdminPager 的約定，也是畫面上顯示的數字）。
    var PER_PAGE = 10;
    var RP_PAGE = 1;

    function $(id) { return document.getElementById(id); }

    function token() {
        return sessionStorage.getItem('ai_hud_token') || localStorage.getItem('ai_hud_token');
    }

    function esc(s) {
        return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
            return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
        });
    }

    function zhOnly(text) {
        var parts = String(text).split(' | ');
        var lang = (window.Prefs && Prefs.get().ui_lang) || 'zh';
        var want = parts.filter(function (p) {
            return p.indexOf(lang === 'en' ? 'EN:' : 'ZH:') === 0;
        })[0];
        return (want || parts[0] || '').replace(/^(ZH|EN):\s*/, '');
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

    function say(id, text) {
        var el = $(id);
        if (!el) return;
        el.textContent = text;
        // ZH: 這個容器兩用 —— 預設回到錯誤樣式，成功訊息由 flash() 換過去。
        //     每次都重設，否則上一則成功訊息的中性底會留給下一則錯誤訊息。
        el.classList.remove('inline-note');
        el.classList.add('inline-error');
        el.hidden = !text;
    }

    // ZH: 只給成功訊息用（錯誤不該自己消失，讀者需要時間看）。
    var _timers = {};
    function flash(id, text, ms) {
        say(id, text);
        // ZH: 成功訊息不要用紅底 —— say() 剛把它設成錯誤樣式，這裡換掉。
        var okEl = $(id);
        if (okEl) {
            okEl.classList.remove('inline-error');
            okEl.classList.add('inline-note');
        }
        clearTimeout(_timers[id]);
        _timers[id] = setTimeout(function () {
            var el = $(id);
            if (el && el.textContent === text) say(id, '');
        }, ms || 3000);
    }

    // ── 回報 ──────────────────────────────────────────────────────────────
    function renderFilters(counts) {
        var opts = [['', T('rp_all', '全部')]].concat(
            // ZH: 狀態標籤用 `st_` 前綴 —— 與節點狀態、寄信狀態一致，
        //     而且 `st_` 已經在 check_i18n 的 DYNAMIC_PREFIXES 裡
        //     （執行時組出來的 key，掃描器看不到字面值）。
        STATUSES.map(function (s) { return [s, T('st_' + s, s)]; }));

        // ZH: v4.41 下拉（擁有者 2026-10-11）。只換 <option>、不換 <select> 本身 ——
        //     每次 load() 都會重畫一次（數量會變），整個換掉的話剛選完焦點就掉回 <body>。
        $('filters').innerHTML = opts.map(function (o) {
            var n = o[0] ? (counts[o[0]] || 0)
                         : STATUSES.reduce(function (a, s) { return a + (counts[s] || 0); }, 0);
            // ZH: 每個篩選都帶數量 —— 不帶的話你得逐一切過才知道哪裡有事。
            return '<option value="' + esc(o[0]) + '"' + (FILTER === o[0] ? ' selected' : '') + '>'
                + esc(o[1]) + '（' + n + '）</option>';
        }).join('');

        // ZH: 類別篩選另起一排。不帶數量 —— summary 端點只算狀態，
        //     硬湊一個前端算的數字會與狀態那排的來源不同，兩排對不起來時
        //     沒有人分得出是資料錯還是篩選錯。
        $('cat-filters').innerHTML =
            [['', T('rp_all', '全部')]].concat(CATEGORIES.map(function (c) {
                return [c[0], T(c[1], c[2])];
            })).map(function (o) {
                return '<option value="' + esc(o[0]) + '"' + (CAT_FILTER === o[0] ? ' selected' : '') + '>'
                    + esc(o[1]) + '</option>';
            }).join('');
    }

    // ZH: v4.45 標題旁的「N 則待處理」（計畫：要處理的數量貼著標題、而且上色）。
    //     不論目前篩的是哪一種都顯示 —— 切到「已結案」時也要看得到還有幾則沒處理。
    //     0 則就整顆不出現（.adm-head__count:empty），不留一顆「0」的警示色藥丸。
    function renderOpenCount(counts) {
        var n = counts.open || 0;
        $('rp-open-n').textContent = n
            ? T('dz_rp_open_n', '{n} 則待處理').replace('{n}', n) : '';
    }

    // ZH: 監聽只掛一次（<select> 本身不會被重畫，見 renderFilters）。
    // ZH: 換篩選就回第一頁 —— 停在第 3 頁換成只有 4 則的類別，畫面會是空的。
    $('filters').addEventListener('change', function (e) { FILTER = e.target.value; RP_PAGE = 1; load(); });
    $('cat-filters').addEventListener('change', function (e) { CAT_FILTER = e.target.value; RP_PAGE = 1; load(); });

    // ZH: 展開中的回報（id → 1）。跨重畫保留，見 renderReports 末尾的說明。
    // ZH: 類別代碼 → 顯示文字。🔴 代碼必須與 schemas.IssueReportCreate.CATEGORIES
    //     以及使用者端 report.js 的 CATEGORIES 三邊一致。
    //     這裡只負責顯示；篩選送出去的一律是代碼。
    var CATEGORIES = [
        ['quota',   'rep_cat_quota',   'AI 額度'],
        ['train',   'rep_cat_train',   '訓練任務'],
        ['lab',     'rep_cat_lab',     '程式實驗室'],
        ['account', 'rep_cat_account', '帳號與登入'],
        ['other',   'rep_cat_other',   '其他'],
    ];
    function catLabel(code) {
        for (var i = 0; i < CATEGORIES.length; i++) {
            if (CATEGORIES[i][0] === code) return T(CATEGORIES[i][1], CATEGORIES[i][2]);
        }
        // ZH: 不認得的代碼**原樣顯示**，不要當成沒分類 ——
        //     那代表前後端漂開了，而藏起來就沒有人會發現。
        return code || '';
    }

    var CAT_FILTER = '';

    // ZH: v4.45 一列仍是一顆 <button>（v3.9 擁有者裁定：一則一列、點開是彈窗），
    //     但改成**固定欄寬**（.dz-rp-row 是 grid，見 admin.css）。原本是 flex，
    //     狀態、類別、名字的寬度都跟著內容走，於是主旨與時間在每一列的起點都不同。
    // ZH: 類別改成中性標籤（不帶 rp__cat--<代碼> 的配色）—— 顏色只留給狀態：
    //     「待處理」的黃與「AI 額度」的黃放在同一列，眼睛分不出哪個是要處理的。
    // ZH: 沒有類別的舊回報要放一個**空的佔位格**，不能省略 ——
    //     少一格的話後面每一欄都往左移一格，固定欄寬就白做了。
    function renderReports(focus) {
        if (!REPORTS.length) {
            $('list').innerHTML = '<p class="footnote">' + esc(T('rp_none', '沒有符合的回報。')) + '</p>';
            return;
        }

        // ZH: 重讀之後筆數可能變少（剛結案的那則離開了「待處理」）——
        //     停在已經不存在的頁就退回最後一頁，不要停在空白頁。
        var pages = Math.max(1, Math.ceil(REPORTS.length / PER_PAGE));
        if (RP_PAGE > pages) RP_PAGE = pages;
        var shown = REPORTS.slice((RP_PAGE - 1) * PER_PAGE, RP_PAGE * PER_PAGE);

        $('list').innerHTML = shown.map(function (r) {
            var who = r.username_at_report || T('rp_anon', '（帳號已刪除）');
            // ZH: 摘要 —— 內文的第一行，換行與連續空白壓成一個空格。
            //     不壓的話一則有換行的回報會把整列撐成好幾行。
            var snip = (r.body || '').replace(/\s+/g, ' ').trim();
            if (snip.length > 60) snip = snip.slice(0, 60) + '…';

            // ZH: 一列 = 一顆按鈕。用 <button> 不用 <div onclick> ——
            //     鍵盤 Tab 到得了、Enter/Space 都能開，
            //     螢幕閱讀器也唸得出這是一個動作而不是一段文字。
            return '<button class="rp adm-card rp__row dz-rp-row" type="button"'
                + ' data-open="' + esc(r.id) + '">'
                +   '<span class="adm-pill adm-pill--' + esc(r.status) + '">'
                +     esc(T('st_' + r.status, r.status)) + '</span>'
                +   (r.category
                        ? '<span class="rp__cat">' + esc(catLabel(r.category)) + '</span>'
                        : '<span class="dz-rp-nocat" aria-hidden="true"></span>')
                +   '<span class="rp__who">' + esc(who) + '</span>'
                // ZH: 有主旨就用主旨當標題 —— 那是使用者自己下的一句話，
                //     比從內文切前 60 字準得多。舊回報沒有主旨，退回用摘要。
                +   '<span class="rp__snip">' + esc(r.subject || snip) + '</span>'
                +   '<span class="rp__when footnote">' + esc(TW.dateTime(r.created_at)) + '</span>'
                // ZH: 已回覆的標記留在列上 —— 不放的話要一則一則點開才知道
                //     哪些處理過了，而那正是收起內容之後最容易失去的資訊。
                +   (r.replied_at
                        ? '<span class="rp__done">' + esc(T('rp_has_reply', '已回覆')) + '</span>'
                        : '<span class="rp__done"></span>')
                + '</button>';
        }).join('')
            // ZH: 分頁在前端切 —— 後端這支沒有 offset（一次回最多 200 則，與改版前相同）。
            //     總筆數一直顯示（計畫：分頁器一直顯示總筆數），只有一頁時就只剩「共 N 筆」。
            + AdminPager.html({ id: 'rp', page: RP_PAGE, pages: pages, total: REPORTS.length });

        $('list').querySelectorAll('[data-open]').forEach(function (b) {
            b.addEventListener('click', function () { openReport(b.dataset.open); });
        });
        AdminPager.wire({
            id: 'rp', page: RP_PAGE, pages: pages, focus: focus,
            onGo: function (p, which) { RP_PAGE = p; renderReports(which); },
        });
    }

    // ══════════════════════════════════════════════════════════════════
    // ZH: 單則回報的彈窗（v3.9）
    // ══════════════════════════════════════════════════════════════════
    // ZH: 用原生 <dialog> + showModal()，不自己做遮罩。理由不只是省事：
    //     · **top layer 渲染** —— 祖先有 transform / filter / overflow 時，
    //       自製的 `position: fixed` 遮罩會以那個祖先為基準，蓋不滿整頁
    //       而且捲動時會跑掉（初次設定那個對話框的註解裡記過這個坑）。
    //     · Esc 關閉、焦點鎖在對話框內、背景不可 Tab —— 全部免費。
    //
    // ZH: 只用**一個** dialog，每次填內容 —— 一則一個的話，
    //     一百則回報就有一百份隱藏的表單掛在 DOM 上。
    function openReport(id) {
        var r = null;
        for (var i = 0; i < REPORTS.length; i++) {
            if (String(REPORTS[i].id) === String(id)) { r = REPORTS[i]; break; }
        }
        if (!r) return;

        var dlg = $('rp-dialog');
        var who = r.username_at_report || T('rp_anon', '（帳號已刪除）');

        // ZH: 🔴 已回覆的就唯讀（擁有者裁定 2026-08-29）。
        //     回覆是**單則**的，而且學生已經看到了 —— 事後改掉它等於
        //     偷偷換掉他讀過的東西，而他不會收到任何通知。
        // ZH: ⚠ 唯讀的只有**回覆內容**。狀態仍然改得動：
        //     「回覆了」與「處理完了」是兩件事，回覆當下常常還沒結案。
        //     連狀態一起鎖的話，回覆過的回報會永遠停在「處理中」。
        var locked = !!r.replied_at;

        dlg.innerHTML =
            '<form method="dialog" class="rmod__x">'
            + '<button class="btn btn--minor" value="close" aria-label="'
            + esc(T('rp_close', '關閉')) + '">✕</button></form>'

            // ZH: 主旨在**最上面靠左**（擁有者裁定 2026-08-29）——
            //     它是這則回報的標題，先看到它才知道下面那排標籤在講什麼。
            //     沒有主旨的是舊回報，那一行就不出現，狀態列自然遞補到最上面。
            + (r.subject ? '<h2 class="rmod__title">' + esc(r.subject) + '</h2>' : '')

            + '<div class="rmod__head">'
            +   '<span class="adm-pill adm-pill--' + esc(r.status) + '">'
            +     esc(T('st_' + r.status, r.status)) + '</span>'
            // ZH: v4.45 類別用中性標籤（與清單同一個理由：顏色只留給狀態）。
            +   (r.category
                    ? '<span class="rp__cat">' + esc(catLabel(r.category)) + '</span>'
                    : '')
            +   '<span class="rmod__meta">' + esc(who) + '　'
            +     esc(TW.dateTime(r.created_at)) + '</span>'
            + '</div>'

            + '<p class="adm-report__body">' + esc(r.body) + '</p>'

            + (r.diagnostics ? '<details class="fold">'
                + '<summary class="fold__summary">' + esc(T('rp_diag', '一起送出的診斷資訊')) + '</summary>'
                + '<pre class="diag">' + esc(prettyDiag(r.diagnostics)) + '</pre>'
                + '</details>' : '')

            + (locked
                // ZH: 唯讀時顯示的是**已送出的那段文字**，不是一個關不掉的輸入框 ——
                //     disabled 的 textarea 看起來仍然像可以編輯，只是壞掉了。
                ? '<div class="rmod__replied">'
                  + '<div class="field__label">' + esc(T('rp_reply', '回覆')) + '</div>'
                  + '<p class="adm-report__body">' + esc(r.admin_reply || '') + '</p>'
                  + '<p class="footnote">'
                  + esc(T('rp_replied', '已於 {when} 回覆').replace('{when}', TW.dateTime(r.replied_at)))
                  + '　' + esc(T('rp_locked', '回覆送出後不能再改 —— 對方已經看到了。'))
                  + '</p></div>'
                : '<label class="field">'
                  + '<span class="field__label" for="rp-reply">' + esc(T('rp_reply', '回覆')) + '</span>'
                  + '<textarea class="field__input" id="rp-reply" rows="5"'
                  + ' placeholder="' + esc(T('rp_reply_ph', '寫給他看的回覆…')) + '"></textarea></label>'
                  + '<p class="footnote">' + esc(T('rp_reply_hint',
                      '他會在「問題回報」那一頁看到這段話。刻意不寄通知信。')) + '</p>')

            // ZH: v4.45 頁腳靠右（計畫第 3 節：確認鍵永遠在右下角）。改狀態的下拉
            //     改成剛好裝得下選項的寬度 —— 原本撐滿整列，把送出鈕擠到最右邊。
            + '<div class="adm-inline rmod__foot dz-rp-foot">'
            + '<select class="field__input" id="rp-status"'
            + ' aria-label="' + esc(T('rp_mark', '改狀態')) + '">'
            + STATUSES.map(function (st) {
                return '<option value="' + st + '"' + (r.status === st ? ' selected' : '') + '>'
                    + esc(T('st_' + st, st)) + '</option>';
            }).join('')
            + '</select>'
            // ZH: v4.45 補上［取消］—— 對話框頁腳一律［取消］［確認］、確認在最右（同公告對話框）。
            //     只關掉對話框，不送任何東西（跟右上角 ✕ 同一件事，但在手邊）。
            + '<button class="btn btn--minor" type="button" id="rp-x">'
            + esc(T('pf_cancel', '取消')) + '</button>'
            + '<button class="btn btn--primary" type="button" id="rp-save">'
            + esc(locked ? T('rp_save_status', '更新狀態') : T('rp_save', '送出回覆'))
            + '</button>'
            + '</div>'
            + '<div class="inline-error" id="rp-msg" hidden></div>';

        $('rp-save').addEventListener('click', function () { save(r.id, locked); });
        $('rp-x').addEventListener('click', function () { dlg.close(); });
        dlg.showModal();
    }

    // ZH: 診斷是 JSON 字串。排版過再顯示 —— 一整行的 JSON 讀不出東西來。
    //     解析失敗就原樣顯示，**不要吞掉**：那可能正是問題所在。
    function prettyDiag(raw) {
        try {
            return JSON.stringify(JSON.parse(raw), null, 2);
        } catch (e) {
            return String(raw);
        }
    }

    async function save(id, locked) {
        // ZH: 唯讀時**不送 admin_reply** —— 送一個空字串會把既有的回覆清掉，
        //     而畫面上完全看不出發生了什麼事。
        var body = { status: $('rp-status').value };
        if (!locked) body.admin_reply = $('rp-reply').value;
        try {
            await api('/admin/reports/' + encodeURIComponent(id), {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });
            $('rp-dialog').close();
            await load();          // ZH: 重讀 —— 狀態改了之後可能就不屬於目前的篩選了
        } catch (e) {
            say('rp-msg', T('rp_fail', '存不起來（{w}）').replace('{w}', e.message));
        }
    }

    // ── 寄信紀錄 ──────────────────────────────────────────────────────────
    // ZH: 把 "<ISO>|scanned|bounces|applied" 轉成一句人話。
    //     空字串＝服務啟動後還沒掃過（與「掃過但沒東西」是兩件事，不能混）。
    // ZH: v3.9 一行拆成兩處（擁有者裁定 2026-08-30）：
    //       畫面上留**這一次掃描的結果**（會變的、要看的），
    //       伺服器／信箱／間隔另外放（設定值，看一次就夠）。
    //     原本四段擠成一行，真正要看的「最後一次」被推到最尾巴。
    // ZH: v4.45 寄信紀錄預設收起之後，「這一次的結果」搬到收合列上（#mail-bounce），
    //     收起來也看得到；設定值從標題旁的 ⓘ 搬到展開後的第一行 ——
    //     <summary> 整列是「點一下展開」，裡面不能再放 ⓘ 那顆按鈕。
    // ZH: ⚠ 一律用 textContent / esc()，不直接進 innerHTML ——
    //     host 與 folder 是設定檔來的字串，不是常數。
    function bounceText(b) {
        if (!b) return '';
        // ZH: 未啟用時只留一句狀態，理由在展開後那一行 ——
        //     「為什麼要在意」看一次就夠，「現在是關的」才是每次都要看到的。
        if (!b.enabled) return T('rp_bounce_off', '退信回收：未啟用');
        var when = T('rp_bounce_never', '尚未掃描過');
        if (b.last_scan) {
            var p = String(b.last_scan).split('|');
            when = (TW.when(p[0]) || p[0])
                + '（' + T('rp_bounce_counts', '讀 {s} 封、退信 {b} 封、回填 {a} 筆')
                    .replace('{s}', p[1] || 0).replace('{b}', p[2] || 0).replace('{a}', p[3] || 0) + '）';
        }
        return T('rp_bounce_on', '最後退信回收：{w}').replace('{w}', when);
    }

    function bounceCfgHtml(b) {
        if (!b) return '';
        return '<p class="footnote">' + esc(b.enabled
            ? T('rp_bounce_cfg', '退信回收：{h} · {f} · 每 {m} 分鐘')
                .replace('{h}', b.host).replace('{f}', b.folder)
                .replace('{m}', b.interval_minutes)
            : T('rp_bounce_off_why',
                '退信回收未啟用。寄給不存在信箱的信會永遠停在「已交付」，看不出來。')) + '</p>';
    }

    // ZH: 收合列上的兩樣東西（退信回收狀態、總筆數）。表格本身與這裡分開畫 ——
    //     收起來時只有這兩樣要更新。
    function showMailHead(data) {
        $('mail-bounce').textContent = bounceText(data && data.bounce);
        if (MAIL_FOLD) MAIL_FOLD.setCount(data && data.total != null ? String(data.total) : '');
    }

    // ZH: v4.45 種類代碼 → 中文（計畫：紀錄表的代碼翻成中文）。
    //     原本直接印 `myai_balance:low` 這種內部代碼（等寬字），要自己在腦中解碼。
    // ZH: 代碼來源是 email_service.send_email 的 kind= 參數：固定的幾種，
    //     加上三種「前綴:階段」（alert: / lab_purge: / myai_balance:）。
    // ZH: 不認得的代碼**原樣顯示**（與 catLabel 同一條理由：藏起來就沒有人發現前後端漂開了）。
    //     ⚠ 這張表不要取名叫 …CATEGORIES —— tests/test_report_subject_category.py
    //       用「那個名字＋等號＋左括號」的字樣找回報類別表，撞名會讓它讀到這一張
    //       （所以這句註解也刻意不把那串字照抄出來）。
    var MAIL_KINDS = [
        ['login_alert',            'dz_rp_k_login_alert',      '新的登入通知'],
        ['password_change_alert',  'dz_rp_k_pw_changed',       '密碼已變更通知'],
        ['account_provisioned',    'dz_rp_k_provisioned',      '帳號已開通（臨時密碼）'],
        ['password_reset',         'dz_rp_k_pw_reset',         '密碼已重設（臨時密碼）'],
        ['myai_provisioned',       'dz_rp_k_myai_provisioned', 'MYAI 開通通知'],
        ['lab_purge:first',        'dz_rp_k_lab_purge_first',  '程式實驗室檔案即將刪除（第一次提醒）'],
        ['lab_purge:final',        'dz_rp_k_lab_purge_final',  '程式實驗室檔案即將刪除（最後提醒）'],
        ['myai_balance:low_early', 'dz_rp_k_bal_early',        'AI 額度開始變少'],
        ['myai_balance:low',       'dz_rp_k_bal_low',          'AI 額度偏低'],
        ['myai_balance:empty',     'dz_rp_k_bal_empty',        'AI 額度用完'],
    ];
    // ZH: 給管理員的告警（alert:<種類>，scheduler._alert 與 worker 心跳寄的）。
    //     種類是後端隨時會加的，所以不認得的也照樣標成「告警：<代碼>」，不整個退回原碼。
    var ALERT_KINDS = [
        ['myai_sync',          'dz_rp_ka_myai_sync',    'MYAI 自動同步失敗'],
        ['myai_balance_alert', 'dz_rp_ka_myai_balance', 'MYAI 點數提醒寄送失敗'],
        ['myai_topup',         'dz_rp_ka_myai_topup',   'MYAI 每月補點異常'],
        ['bounce_scan',        'dz_rp_ka_bounce_scan',  '退信回收異常'],
        ['gpu_unhealthy',      'dz_rp_ka_gpu',          'GPU 節點有卡不能用'],
    ];

    function lookup(table, code) {
        for (var i = 0; i < table.length; i++) {
            if (table[i][0] === code) return T(table[i][1], table[i][2]);
        }
        return null;
    }

    // ZH: 代碼欄的一格。認得的是一般文字，不認得的維持原本的等寬原碼。
    //     兩種都把原碼放在 title 上 —— 要對照後端日誌或程式時查得到。
    //     cls 是這一格另外要掛的類別（例如吃剩下寬度的 grow）。
    function codeCell(label, code, cls) {
        var c = cls ? [cls] : [];
        if (!code) return '<td' + (c.length ? ' class="' + c.join(' ') + '"' : '') + '>—</td>';
        if (!label) c.push('mono');
        return '<td' + (c.length ? ' class="' + c.join(' ') + '"' : '')
            + ' title="' + esc(code) + '">' + esc(label || code) + '</td>';
    }

    function kindLabel(kind) {
        if (!kind) return null;
        var hit = lookup(MAIL_KINDS, kind);
        if (hit) return hit;
        if (kind.indexOf('alert:') === 0) {
            var sub = kind.slice(6);
            return T('dz_rp_k_alert', '告警：{w}').replace('{w}', lookup(ALERT_KINDS, sub) || sub);
        }
        return null;
    }

    // ── 分頁 ─────────────────────────────────────────────────────────────
    // ZH: 兩區共用。由後端分頁（offset/limit/total），不是一次撈全部再切 ——
    //     這兩張表只會越來越長，一次撈 50 筆的舊做法到後面就看不到更早的紀錄了。
    // ZH: v4.45 分頁器換成共用的 AdminPager（admin-chrome.js）：原本這裡與帳號頁各抄一份，
    //     現在全站只有一份。換頁後焦點放回同一顆鈕（原本 wirePager 做的事）由它負責。
    var PAGES = { mail: 1, audit: 1 };      // ZH: 目前第幾頁（從 1 算）

    // ZH: v4.45 收合區（預設收起，第一次點開才載入）。在檔尾「載入」那段接上。
    var MAIL_FOLD = null, AUDIT_FOLD = null;
    // ZH: 表格載過了沒。載過之後切語言要重畫表格；沒載過只更新收合列上的數字與狀態。
    var LOADED = { mail: false, audit: false };

    // ZH: 回傳 true／false（有沒有讀到）。收合區靠它決定下次點開要不要重試 ——
    //     讀不到就永遠停在錯誤訊息、重新點開也沒用，那看起來像壞掉。
    async function loadMail(focus) {
        var data;
        try {
            data = await api('/admin/email-log?limit=' + PER_PAGE + '&offset=' + ((PAGES.mail - 1) * PER_PAGE));
        } catch (e) {
            $('mail').innerHTML = '<p class="footnote">'
                + esc(T('ov_fail_part', '這一段暫時讀不到（{w}）').replace('{w}', e.message)) + '</p>';
            return false;
        }
        LOADED.mail = true;
        // ZH: 🔴 這支端點回的是**物件** `{counts, smtp_configured, from_email, bounce, logs}`，
        //     不是陣列。原本直接對它做 `rows.length` —— undefined 恆為 falsy，
        //     於是**不論有幾筆紀錄都顯示「沒有寄信紀錄。」**，而且不會有任何錯誤。
        //     （端點在 `14fbddd` 就改成物件了，前端一直沒跟上。）
        var rows = (data && data.logs) || [];
        showMailHead(data);
        var head0 = bounceCfgHtml(data && data.bounce);
        // ZH: 別人刪了資料、或停在最後一頁時筆數變少 → 那一頁空了就退回上一頁，不要停在空白頁。
        if (!rows.length && PAGES.mail > 1) { PAGES.mail--; return loadMail(focus); }
        if (!rows.length) {
            $('mail').innerHTML = head0
                + '<p class="footnote">' + esc(T('rp_mail_none', '沒有寄信紀錄。')) + '</p>';
            return true;
        }
        // ZH: v4.45 「種類」是吃剩下寬度的那一欄（.grow）——其餘三欄只佔內容需要的寬度，
        //     不然四欄短資料平均攤在 1440px 上，眼睛要在收件者與時間之間跳 300px。
        var head = [
            ['rp_m_to', '收件者', ''], ['rp_m_kind', '種類', 'grow'],
            ['rp_m_status', '結果', ''], ['rp_m_when', '時間', ''],
        ];
        var total = (data && data.total) || rows.length;
        // ZH: v3.9 這裡原本有一句「⚠『已交付』不代表送達 —— 網域存在但信箱
        //     不存在時會稍後才退信」。拿掉了（擁有者裁定 2026-08-30）。
        //
        // ZH: 理由是一條通則，不只適用這一句：
        //     **人不會去在意自己確認不了的事。**
        //     管理員看到「已交付」時，沒有任何辦法自己驗證對方收到沒有 ——
        //     給他一句警語，他做不了任何事，只是多一個沒有出口的疑慮。
        //     不如就給一個狀態，等查證回來（退信回收掃到）再把它更新掉。
        // ZH: ⚠ 所以這條規則的前提是**那個更新真的會發生**。
        //     退信回收停掉的話，狀態就永遠停在「已交付」而沒有人知道 ——
        //     那正是收合列上「退信回收：未啟用」要一直看得到的原因（bounceText）。
        $('mail').innerHTML =
            head0
            + '<div class="adm-tablewrap"><table class="adm-table"><thead><tr>'
            + head.map(function (h) {
                return '<th' + (h[2] ? ' class="' + h[2] + '"' : '') + '>' + esc(T(h[0], h[1])) + '</th>';
            }).join('')
            + '</tr></thead><tbody>'
            + rows.map(function (m) {
                return '<tr>'
                    + '<td>' + esc(m.to_email) + '</td>'
                    + codeCell(kindLabel(m.kind), m.kind, 'grow')
                    + '<td><span class="adm-pill adm-pill--' + esc(m.status) + '">'
                    + esc(T('st_' + m.status, m.status)) + '</span></td>'
                    + '<td>' + esc(TW.when(m.created_at) || '—') + '</td>'
                    + '</tr>';
            }).join('')
            + '</tbody></table></div>'
            + AdminPager.html({ id: 'mail', page: PAGES.mail, perPage: PER_PAGE, total: total });
        AdminPager.wire({
            id: 'mail', page: PAGES.mail, perPage: PER_PAGE, total: total, focus: focus,
            onGo: function (p, which) { PAGES.mail = p; loadMail(which); },
        });
        return true;
    }

    // ── 管理動作紀錄 ──────────────────────────────────────────────────────
    // ZH: v4.45 動作代碼 → 中文。代碼來源：寫進 admin_actions 的每一處
    //     （routers/admin.py、admin_ai.py、lab_manager、myai_sync、quota_service、storage_lifecycle）。
    //     不認得的照樣原樣顯示（理由同 MAIL_KINDS）。
    var AUDIT_ACTIONS = [
        ['create_temp_account',   'dz_rp_a_create_temp',       '建立臨時帳號'],
        ['extend_temp_account',   'dz_rp_a_extend_temp',       '延長臨時帳號'],
        ['delete_user',           'dz_rp_a_delete_user',       '刪除帳號'],
        ['export_users',          'dz_rp_a_export_users',      '匯出帳號清單'],
        ['grant_profile_unlock',  'dz_rp_a_unlock',            '開放一次修改個人資料'],
        ['revoke_profile_unlock', 'dz_rp_a_unlock_revoke',     '收回修改個人資料'],
        ['myai_grant_points',     'dz_rp_a_myai_grant',        '加 MYAI 點數'],
        ['myai_reclaim_points',   'dz_rp_a_myai_reclaim',      '回收 MYAI 點數'],
        ['myai_manual_topup',     'dz_rp_a_myai_topup',        '手動補齊 MYAI 點數'],
        ['myai_manual_reclaim',   'dz_rp_a_myai_bulk_reclaim', '手動批次回收 MYAI 點數'],
        ['grant_quota',           'dz_rp_a_grant_quota',       '磁碟額外授與'],
        ['revoke_quota',          'dz_rp_a_revoke_quota',      '收回磁碟額外授與'],
        ['force_stop_lab',        'dz_rp_a_force_stop_lab',    '強制關閉程式實驗室'],
        ['freeze',                'dz_rp_a_freeze',            '凍結儲存空間'],
        ['restore',               'dz_rp_a_restore',           '還原封存的資料'],
        ['mark_pending_delete',   'dz_rp_a_pending_delete',    '標記為待刪除'],
        ['permanent_delete',      'dz_rp_a_permanent_delete',  '永久刪除資料'],
        ['ai_query',              'dz_rp_a_ai_query',          'AI 查詢'],
    ];

    async function loadAudit(focus) {
        var rows;
        try {
            rows = await api('/admin/audit?limit=' + PER_PAGE + '&offset=' + ((PAGES.audit - 1) * PER_PAGE));
        } catch (e) {
            $('audit').innerHTML = '<p class="footnote">'
                + esc(T('ov_fail_part', '這一段暫時讀不到（{w}）').replace('{w}', e.message)) + '</p>';
            return false;
        }
        LOADED.audit = true;
        var list = rows.items || rows || [];
        if (AUDIT_FOLD) AUDIT_FOLD.setCount(rows.total != null ? String(rows.total) : '');
        if (!list.length && PAGES.audit > 1) { PAGES.audit--; return loadAudit(focus); }
        if (!list.length) {
            $('audit').innerHTML = '<p class="footnote">'
                + esc(T('rp_audit_none', '還沒有任何管理動作。')) + '</p>';
            return true;
        }
        // ZH: 「對象」吃剩下的寬度 —— 「誰、做了什麼、對誰」三欄貼在一起讀成一句話，
        //     空白留在句子後面、時間前面。
        var head = [
            ['rp_a_who', '管理者', ''], ['rp_a_what', '動作', ''],
            ['rp_a_target', '對象', 'grow'], ['rp_a_when', '時間', ''],
        ];
        var total = rows.total || list.length;
        $('audit').innerHTML =
            '<div class="adm-tablewrap"><table class="adm-table"><thead><tr>'
            + head.map(function (h) {
                return '<th' + (h[2] ? ' class="' + h[2] + '"' : '') + '>' + esc(T(h[0], h[1])) + '</th>';
            }).join('')
            + '</tr></thead><tbody>'
            + list.map(function (a) {
                return '<tr>'
                    + '<td>' + esc(a.admin_username || (a.admin_id || '').slice(0, 8) || '—') + '</td>'
                    + codeCell(lookup(AUDIT_ACTIONS, a.action), a.action)
                    + '<td class="grow">' + esc(a.target_username || (a.target_user || '').slice(0, 8) || '—') + '</td>'
                    + '<td>' + esc(TW.when(a.timestamp) || '—') + '</td>'
                    + '</tr>';
            }).join('')
            + '</tbody></table></div>'
            + AdminPager.html({ id: 'audit', page: PAGES.audit, perPage: PER_PAGE, total: total });
        AdminPager.wire({
            id: 'audit', page: PAGES.audit, perPage: PER_PAGE, total: total, focus: focus,
            onGo: function (p, which) { PAGES.audit = p; loadAudit(which); },
        });
        return true;
    }

    // ZH: 收起來時的那一列：只要筆數（與寄信紀錄的退信回收狀態），不要表格。
    //     limit=1 是同一支端點、同一組參數，只是只拿一筆 —— 回應裡的 total 與 bounce
    //     不受 limit 影響（見 routers/admin.py 的 get_email_log / get_audit_log）。
    // ZH: ⚠ 不能整個等到點開才讀：「退信回收：未啟用」要一直看得到，
    //     而它只有這支端點回得出來。
    // ZH: 管理動作讀不到就讓數字空著（收合列上不擠錯誤訊息）—— 點開時表格那邊會講清楚為什麼。
    //     寄信紀錄讀不到則要講出來：空白的話看起來像「退信回收沒問題」。
    async function loadLogHeads() {
        if (!LOADED.mail) {
            try {
                showMailHead(await api('/admin/email-log?limit=1&offset=0'));
            } catch (e) {
                $('mail-bounce').textContent =
                    T('ov_fail_part', '這一段暫時讀不到（{w}）').replace('{w}', e.message);
            }
        }
        if (!LOADED.audit) {
            try {
                var a = await api('/admin/audit?limit=1&offset=0');
                if (AUDIT_FOLD) AUDIT_FOLD.setCount(a && a.total != null ? String(a.total) : '');
            } catch (e) {
                if (AUDIT_FOLD) AUDIT_FOLD.setCount('');
            }
        }
    }

    // ── 載入 ──────────────────────────────────────────────────────────────
    // ── 公告 ──────────────────────────────────────────────────────────────
    //
    // ZH: 這是這一頁唯一「往外發」的東西 —— 其他三區都是回頭看已經發生的事。
    //     所以它排在最前面，而且有一顆明確的「寫一則公告」。
    //
    // ZH: 🔴 內容一律當**純文字**看待。使用者端現在就是純文字顯示，
    //     這裡若讓管理員寫 HTML，公告就變成一個注入管道 ——
    //     管理員寫的東西會送進每一個使用者的瀏覽器。
    var NEWS = [];

    async function loadNews() {
        try {
            NEWS = await api('/admin/announcements?include_hidden=true');
        } catch (e) {
            $('news').innerHTML = '<p class="footnote">'
                + esc(T('ov_fail_part', '這一段暫時讀不到（{w}）').replace('{w}', e.message)) + '</p>';
            return;
        }
        renderNews();
    }

    // ZH: v4.45 預設只列最前面 5 則（計畫第 4 節「訊息」）。順序照後端的（置頂的在前、
    //     其餘新到舊）—— 與使用者端看到的順序相同，所以「前 5 則」就是使用者最先看到的那 5 則。
    //     其餘收在「全部 N 則」後面，點開之後才分頁（每頁 PER_PAGE 則）。
    // ZH: 為什麼要收：公告是一週寫一次的東西，卻排在每天要處理的回報**前面**（擁有者定的順序，
    //     不動）；它沒有上限的話，回報就被越推越下面。
    var NEWS_SHOW = 5;
    var NEWS_ALL = false;     // ZH: 目前是不是在看「全部」
    var NEWS_PAGE = 1;

    function renderNews(focus) {
        var live = NEWS.filter(function (a) { return a.is_visible; }).length;
        // ZH: 總數貼在標題旁（數量徽章），「其中幾則公開中」是狀態，放右半。
        $('news-count').textContent = NEWS.length ? String(NEWS.length) : '';
        $('news-sum').textContent = NEWS.length
            ? T('dz_rp_news_pub', '{v} 則公開中').replace('{v}', live) : '';

        if (!NEWS.length) {
            $('news').innerHTML = '<p class="footnote">'
                + esc(T('rp_news_none', '還沒有任何公告。')) + '</p>';
            return;
        }

        // ZH: 刪到剩 5 則以下時，「全部」就沒有意義了 —— 退回預設，不留一個只有一頁的分頁器。
        if (NEWS.length <= NEWS_SHOW) NEWS_ALL = false;
        var pages = Math.max(1, Math.ceil(NEWS.length / PER_PAGE));
        if (NEWS_PAGE > pages) NEWS_PAGE = pages;
        var shown = NEWS_ALL
            ? NEWS.slice((NEWS_PAGE - 1) * PER_PAGE, NEWS_PAGE * PER_PAGE)
            : NEWS.slice(0, NEWS_SHOW);

        // ZH: 標題是吃剩下寬度的那一欄（.grow），其餘只佔內容需要的寬度。
        // ZH: v4.45 列上只留「編輯」（文字按鈕）。刪除移進編輯對話框的左下角 ——
        //     原本每一列都有一顆跟「編輯」一樣重的「刪除」緊貼在旁邊，十則就是二十顆一樣的按鈕。
        var cols = [['rp_news_title', '標題', 'grow'], ['rp_news_when', '發布時間', ''],
                    ['rp_news_state', '狀態', ''], ['', '', '']];
        var foot = '';
        if (NEWS_ALL) {
            foot = '<div class="dz-rp-newsfoot">'
                + '<button class="btn--quiet" type="button" id="news-less">'
                + '<span aria-hidden="true">‹</span> '
                + esc(T('dz_rp_news_less', '只看最前面 {n} 則').replace('{n}', NEWS_SHOW)) + '</button>'
                + AdminPager.html({ id: 'news', page: NEWS_PAGE, pages: pages, total: NEWS.length })
                + '</div>';
        } else if (NEWS.length > NEWS_SHOW) {
            // ZH: 借用分頁器的外框（.adm-pager：右下、右端對齊表格最後一欄）——
            //     它就是這張表的「下一步」，放在換頁鈕會出現的同一個位置。
            foot = '<div class="adm-pager">'
                + '<button class="btn--quiet" type="button" id="news-all">'
                + esc(T('dz_rp_news_all', '全部 {n} 則').replace('{n}', NEWS.length))
                + ' <span aria-hidden="true">›</span></button></div>';
        }

        $('news').innerHTML =
            '<div class="adm-tablewrap"><table class="adm-table"><thead><tr>'
            + cols.map(function (c) {
                return '<th' + (c[2] ? ' class="' + c[2] + '"' : '') + '>'
                    + esc(c[0] ? T(c[0], c[1]) : '') + '</th>';
            }).join('')
            + '</tr></thead><tbody>'
            + shown.map(function (a) {
                return '<tr>'
                    + '<td class="grow">' + (a.is_pinned
                        ? '<span class="adm-pill adm-pill--ok">'
                            + esc(T('rp_news_pinned', '置頂')) + '</span> ' : '')
                    + esc(a.title) + '</td>'
                    + '<td>' + esc(TW.dateTime(a.posted_at)) + '</td>'
                    // ZH: 沒公開的講「只有你看得到」不是「隱藏」——
                    //     後者聽起來像被系統擋下來，前者才說得出是誰的選擇。
                    + '<td>' + (a.is_visible
                        ? esc(T('rp_news_live', '公開中'))
                        : '<span class="adm-pill adm-pill--warn">'
                            + esc(T('rp_news_draft', '只有你看得到')) + '</span>') + '</td>'
                    + '<td class="num">'
                    + '<button class="btn--quiet" type="button" data-news-edit="' + esc(a.id) + '">'
                    + esc(T('pp_edit', '編輯')) + '</button></td>'
                    + '</tr>';
            }).join('')
            + '</tbody></table></div>'
            + foot;

        $('news').querySelectorAll('[data-news-edit]').forEach(function (b) {
            b.addEventListener('click', function () {
                openNewsForm(NEWS.filter(function (x) {
                    return String(x.id) === b.dataset.newsEdit;
                })[0]);
            });
        });
        // ZH: 展開／收回之後按的那顆鈕就不見了（整段重畫）—— 焦點放到對面那顆上，
        //     用鍵盤的人不必從頁首重新 Tab 過來（與分頁器同一個理由）。
        if ($('news-all')) {
            $('news-all').addEventListener('click', function () {
                NEWS_ALL = true; NEWS_PAGE = 1; renderNews();
                if ($('news-less')) $('news-less').focus();
            });
        }
        if ($('news-less')) {
            $('news-less').addEventListener('click', function () {
                NEWS_ALL = false; renderNews();
                if ($('news-all')) $('news-all').focus();
            });
        }
        if (NEWS_ALL) {
            AdminPager.wire({
                id: 'news', page: NEWS_PAGE, pages: pages, focus: focus,
                onGo: function (p, which) { NEWS_PAGE = p; renderNews(which); },
            });
        }
    }

    function openNewsForm(a) {
        var e = a || {};
        var pick = function (id, key, zh, on) {
            return '<label class="field"><span class="field__label" for="' + id + '">'
                + esc(T(key, zh)) + '</span>'
                + '<select class="field__input" id="' + id + '">'
                + [['1', T('pf_yes', '是')], ['0', T('pf_no', '否')]].map(function (o) {
                    return '<option value="' + o[0] + '"'
                        + ((on ? '1' : '0') === o[0] ? ' selected' : '') + '>'
                        + esc(o[1]) + '</option>';
                }).join('')
                + '</select></label>';
        };
        var dlg = $('news-dialog');
        dlg.innerHTML =
            // ZH: 右上角的關閉。`method="dialog"` 讓它不必接事件就能關。
            '<form method="dialog" class="rmod__x">'
            +   '<button class="btn btn--minor" type="submit" aria-label="'
            +   esc(T('pf_close', '關閉')) + '">✕</button></form>'
            + '<h2 class="rmod__title">'
            + esc(a ? T('rp_news_edit', '編輯公告') : T('rp_news_new', '寫一則公告')) + '</h2>'
            // ZH: v3.9 中英並排（擁有者裁定 2026-08-30）。
            //     並排不是上下排的理由：翻譯時眼睛要在兩邊來回對照，
            //     上下排的話長內文會讓對照的兩段隔了一整個畫面。
            // ZH: ⚠ 英文可以空著 —— 空的時候使用者端顯示中文版。
            //     做成必填的話，結果會是公告乾脆不發。
            + '<div class="nw-cols">'
            +   '<div>'
            +     '<label class="field"><span class="field__label" for="nw-title">'
            +     esc(T('rp_news_title', '標題')) + '</span>'
            +     '<input class="field__input" id="nw-title" type="text" value="'
            +     esc(e.title || '') + '"></label>'
            +     '<label class="field"><span class="field__label" for="nw-body">'
            +     esc(T('rp_news_body', '內容')) + '</span>'
            +     '<textarea class="field__input" id="nw-body" rows="8">'
            +     esc(e.body || '') + '</textarea></label>'
            +   '</div>'
            +   '<div>'
            +     '<label class="field"><span class="field__label" for="nw-title-en">'
            +     esc(T('rp_news_title_en', '標題（英文，可留空）')) + '</span>'
            +     '<input class="field__input" id="nw-title-en" type="text" value="'
            +     esc(e.title_en || '') + '"></label>'
            +     '<label class="field"><span class="field__label" for="nw-body-en">'
            +     esc(T('rp_news_body_en', '內容（英文，可留空）')) + '</span>'
            +     '<textarea class="field__input" id="nw-body-en" rows="8">'
            +     esc(e.body_en || '') + '</textarea></label>'
            +   '</div>'
            + '</div>'
            // ZH: 明講會原樣顯示 —— 有人會想貼 HTML 進來。
            + '<p class="footnote">' + esc(T('rp_news_plain',
                '純文字，會原樣顯示給使用者。貼 HTML 進來不會變成排版，會看到標籤本身。')) + '</p>'
            // ZH: v4.45 兩個是／否並排（與上面的中英欄同一個格線）——
            //     各自佔一整列的話，兩個二選一就吃掉兩列 44px 加兩行標籤。
            + '<div class="nw-cols">'
            + pick('nw-pin', 'rp_news_pin', '置頂', e.is_pinned)
            + pick('nw-vis', 'rp_news_vis', '公開', a ? e.is_visible : 1)
            + '</div>'
            // ZH: 附件。新公告還沒有 id，所以檔案是**存檔之後**才送上去的
            //     （見 saveNews）——這裡先收在 input 裡。
            + '<label class="field"><span class="field__label" for="nw-files">'
            + esc(T('rp_news_attach', '附件')) + '</span>'
            + '<input class="field__input" id="nw-files" type="file" multiple '
            + 'accept=".pdf,.docx,.xlsx,.pptx,.png,.jpg,.jpeg,.zip"></label>'
            + '<p class="footnote">' + esc(T('rp_news_attach_hint',
                '可以放 pdf / docx / xlsx / pptx / png / jpg / zip。單檔上限見系統設定。')) + '</p>'
            + '<div id="nw-have"></div>'
            // ZH: v4.45 對話框裡的錯誤訊息放在對話框裡 —— 原本寫到頁面上的 #news-msg，
            //     而那一塊被 modal 的背景蓋住，按了「儲存」沒反應、也看不到為什麼。
            + '<div class="inline-error" id="nw-msg" hidden></div>'
            // ZH: v4.45 頁腳照計畫第 3 節：危險動作在左下，右下依序［取消］［儲存］，
            //     確認鍵永遠在右下角。刪除只在編輯既有公告時才有（新公告還沒有東西可刪）。
            + '<div class="adm-inline rmod__foot dz-rp-foot">'
            + (a ? '<button class="btn--quiet btn--danger dz-rp-foot__danger" type="button" id="nw-del">'
                   + esc(T('pf_m_del', '刪除')) + '</button>' : '')
            + '<button class="btn btn--minor" type="button" id="nw-x">'
            + esc(T('pf_cancel', '取消')) + '</button>'
            + '<button class="btn btn--primary" type="button" id="nw-ok">'
            + esc(T('pp_save', '儲存')) + '</button></div>';

        renderHave(a);
        dlg.showModal();
        $('nw-ok').addEventListener('click', function () { saveNews(a); });
        $('nw-x').addEventListener('click', function () { dlg.close(); });
        if (a) $('nw-del').addEventListener('click', function () { delNews(a.id); });
        $('nw-title').focus();
    }

    // ZH: 對話框開著時，訊息寫進對話框裡（#nw-msg）；關著時寫到頁面上（#news-msg）。
    //     同一個呼叫點兩種情況都會遇到（例如存完公告、關掉對話框之後才知道附件失敗）。
    function newsSay(text) {
        var dlg = $('news-dialog');
        say(dlg && dlg.open && $('nw-msg') ? 'nw-msg' : 'news-msg', text);
    }

    /* ZH: 已經上傳的附件（只有編輯既有公告時才有）。
     * ZH: 每一個都給一顆刪除 —— 附件放錯了要有辦法拿掉，
     *     不然只能整則公告刪掉重寫。
     */
    function renderHave(a) {
        var box = $('nw-have');
        if (!box) return;
        var files = (a && a.files) || [];
        if (!files.length) { box.innerHTML = ''; return; }
        box.innerHTML = '<p class="footnote">'
            + esc(T('rp_news_have', '已上傳')) + '</p>';
        files.forEach(function (fobj) {
            var row = document.createElement('div');
            row.className = 'adm-inline';
            var name = document.createElement('span');
            // ZH: 檔名是管理員上傳時的原始字串 —— 用 textContent，不進 innerHTML。
            name.textContent = fobj.filename + '（' + fmtKb(fobj.size_bytes) + '）';
            var del = document.createElement('button');
            del.className = 'btn btn--minor';
            del.type = 'button';
            del.textContent = T('pp_delete', '刪除');
            del.addEventListener('click', async function () {
                if (!confirm(T('rp_news_file_del', '要刪掉這個附件嗎？無法復原。'))) return;
                try {
                    await api('/admin/announcements/' + encodeURIComponent(a.id)
                              + '/files/' + encodeURIComponent(fobj.id), { method: 'DELETE' });
                    a.files = files.filter(function (x) { return x.id !== fobj.id; });
                    renderHave(a);
                    await loadNews();
                } catch (e) {
                    newsSay(e.message);
                }
            });
            row.appendChild(name);
            row.appendChild(del);
            box.appendChild(row);
        });
    }

    function fmtKb(n) {
        var b = Number(n) || 0;
        if (b >= 1024 * 1024) return (b / 1024 / 1024).toFixed(1) + ' MB';
        return Math.max(1, Math.round(b / 1024)) + ' KB';
    }

    async function saveNews(a) {
        var title = $('nw-title').value.trim();
        var body = $('nw-body').value.trim();
        if (!title || !body) {
            newsSay(T('rp_news_need', '標題與內容都要填。'));
            return;
        }
        // ZH: 下拉的值是字串，'0' 是 truthy —— 要明確比對，不能用 !!。
        var payload = {
            title: title, body: body,
            // ZH: 空字串照送，後端會正規化成 null（見 admin_create_announcement）。
            title_en: $('nw-title-en').value.trim(),
            body_en: $('nw-body-en').value.trim(),
            is_pinned: $('nw-pin').value === '1' ? 1 : 0,
            is_visible: $('nw-vis').value === '1' ? 1 : 0,
        };
        try {
            var saved = await api(a ? '/admin/announcements/' + encodeURIComponent(a.id)
                                    : '/admin/announcements', {
                method: a ? 'PUT' : 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });

            // ZH: 🔴 附件**存完公告才送** —— 新公告在存檔之前沒有 id，
            //     沒有 id 就沒有可以掛附件的地方。
            // ZH: ⚠ 一個一個送，不併成一個請求：後端一次收一個檔，
            //     而且逐個送才知道是**哪一個**失敗（例如只有其中一個超過上限）。
            var annId = (a && a.id) || (saved && saved.id);
            var picked = $('nw-files') ? $('nw-files').files : null;
            var failed = [];
            if (annId && picked && picked.length) {
                for (var i = 0; i < picked.length; i++) {
                    var fd = new FormData();
                    fd.append('file', picked[i]);
                    try {
                        // ZH: ⚠ **不要**自己設 Content-Type —— FormData 的
                        //     multipart 邊界字串是瀏覽器產生的，手動設會少掉它，
                        //     後端就解不出檔案（而錯誤訊息看起來像「沒有收到檔名」）。
                        await api('/admin/announcements/' + encodeURIComponent(annId) + '/files',
                                  { method: 'POST', body: fd });
                    } catch (e2) {
                        failed.push(picked[i].name + '：' + e2.message);
                    }
                }
            }

            $('news-dialog').close();
            if (failed.length) {
                // ZH: 公告存成功了、附件有的沒上去 —— 要分開講。
                //     合成一句「儲存失敗」會讓人以為公告也沒存到而重寫一次。
                say('news-msg', T('rp_news_file_fail', '公告已儲存，但有附件沒有上傳成功：')
                    + failed.join('；'));
            } else {
                flash('news-msg', T('rp_news_saved', '公告已更新。'), 5000);
            }
            await loadNews();
        } catch (e) {
            newsSay(e.message);
        }
    }

    // ZH: v4.45 從編輯對話框的左下角呼叫（原本在每一列上）。確認文字不變 ——
    //     照樣講出是哪一則、使用者端也會消失、不能復原。
    async function delNews(id) {
        var a = NEWS.filter(function (x) { return String(x.id) === String(id); })[0] || {};
        // ZH: 明講刪掉之後使用者端也會消失 —— 這是唯一一個會影響到所有人的操作。
        if (!confirm(T('rp_news_del_confirm',
                '要刪掉「{n}」嗎？使用者端也會跟著消失，而且沒辦法復原。')
                .replace('{n}', a.title || id))) return;
        try {
            await api('/admin/announcements/' + encodeURIComponent(id), { method: 'DELETE' });
            // ZH: 刪掉了才關對話框 —— 失敗的話留著，錯誤訊息就寫在對話框裡（newsSay）。
            var dlg = $('news-dialog');
            if (dlg && dlg.open) dlg.close();
            await loadNews();
        } catch (e) { newsSay(e.message); }
    }

    async function load() {
        try {
            var qs = [];
            if (FILTER) qs.push('status=' + encodeURIComponent(FILTER));
            if (CAT_FILTER) qs.push('category=' + encodeURIComponent(CAT_FILTER));
            var q = qs.length ? '?' + qs.join('&') : '';
            var summary = await api('/admin/reports/summary');
            REPORTS = await api('/admin/reports' + q);
            renderFilters(summary.counts || {});
            renderOpenCount(summary.counts || {});
            renderReports();
        } catch (e) {
            $('list').innerHTML = '<p class="footnote">'
                + esc(T('ov_fail_part', '這一段暫時讀不到（{w}）').replace('{w}', e.message)) + '</p>';
        }
    }

    $('news-new').addEventListener('click', function () {
        // ZH: 一定要包一層 —— 直接傳 openNewsForm 的話，
        //     addEventListener 會把 Event 物件當成 `a`，於是永遠走「編輯」那條路。
        openNewsForm(null);
    });

    // ZH: v4.45 兩張紀錄表預設收起、第一次點開才載入（擁有者待決事項 3，A 案）。
    //     onFirstOpen 回傳的 Promise 失敗時，AdminFold 會在下次點開時再試一次 ——
    //     所以「沒讀到」要變成 reject，不能只是畫一句錯誤訊息就算了。
    function firstOpen(loader) {
        return function () {
            return loader().then(function (ok) { if (!ok) throw new Error('retry'); });
        };
    }
    MAIL_FOLD = AdminFold.wire('mail-fold', { onFirstOpen: firstOpen(loadMail) });
    AUDIT_FOLD = AdminFold.wire('audit-fold', { onFirstOpen: firstOpen(loadAudit) });

    loadNews();
    load();
    loadLogHeads();
    // ZH: 切語言：載過的表格整段重畫；還沒點開過的只更新收合列上的狀態與數字
    //     （不因為切了語言就把使用者沒打開的東西讀進來）。
    document.addEventListener('prefs:langchanged', function () {
        loadNews(); load();
        if (LOADED.mail) loadMail();
        if (LOADED.audit) loadAudit();
        loadLogHeads();
    });
})();
