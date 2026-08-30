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

        $('filters').innerHTML = opts.map(function (o) {
            var n = o[0] ? (counts[o[0]] || 0)
                         : STATUSES.reduce(function (a, s) { return a + (counts[s] || 0); }, 0);
            return '<button class="btn btn--minor' + (FILTER === o[0] ? ' is-current' : '') + '"'
                + ' type="button" data-filter="' + esc(o[0]) + '"'
                + (FILTER === o[0] ? ' aria-current="true"' : '') + '>'
                // ZH: 每個篩選都帶數量 —— 不帶的話你得逐一點過才知道哪裡有事。
                + esc(o[1]) + '　' + n + '</button>';
        }).join('');

        // ZH: 類別篩選另起一排。不帶數量 —— summary 端點只算狀態，
        //     硬湊一個前端算的數字會與狀態那排的來源不同，兩排對不起來時
        //     沒有人分得出是資料錯還是篩選錯。
        $('cat-filters').innerHTML =
            [['', T('rp_all', '全部')]].concat(CATEGORIES.map(function (c) {
                return [c[0], T(c[1], c[2])];
            })).map(function (o) {
                // ZH: 每個類別帶自己的 class，選中時才上色（見 admin.css）——
                //     沒選中就保持中性，五顆全上色的話反而看不出選了哪一個。
                return '<button class="btn btn--minor btn--cat-' + esc(o[0] || 'all')
                    + (CAT_FILTER === o[0] ? ' is-current' : '') + '"'
                    + ' type="button" data-cat="' + esc(o[0]) + '"'
                    + (CAT_FILTER === o[0] ? ' aria-current="true"' : '') + '>'
                    + esc(o[1]) + '</button>';
            }).join('');
        $('cat-filters').querySelectorAll('[data-cat]').forEach(function (b) {
            b.addEventListener('click', function () {
                CAT_FILTER = b.dataset.cat;
                load();
            });
        });

        $('filters').querySelectorAll('[data-filter]').forEach(function (b) {
            b.addEventListener('click', function () {
                FILTER = b.dataset.filter;
                load();
            });
        });
    }

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

    function renderReports() {
        if (!REPORTS.length) {
            $('list').innerHTML = '<p class="footnote">' + esc(T('rp_none', '沒有符合的回報。')) + '</p>';
            return;
        }

        $('list').innerHTML = REPORTS.map(function (r) {
            var who = r.username_at_report || T('rp_anon', '（帳號已刪除）');
            // ZH: 摘要 —— 內文的第一行，換行與連續空白壓成一個空格。
            //     不壓的話一則有換行的回報會把整列撐成好幾行。
            var snip = (r.body || '').replace(/\s+/g, ' ').trim();
            if (snip.length > 60) snip = snip.slice(0, 60) + '…';

            // ZH: 一列 = 一顆按鈕。用 <button> 不用 <div onclick> ——
            //     鍵盤 Tab 到得了、Enter/Space 都能開，
            //     螢幕閱讀器也唸得出這是一個動作而不是一段文字。
            return '<button class="rp adm-card rp__row" type="button"'
                + ' data-open="' + esc(r.id) + '">'
                +   '<span class="adm-pill adm-pill--' + esc(r.status) + '">'
                +     esc(T('st_' + r.status, r.status)) + '</span>'
                +   (r.category
                        ? '<span class="rp__cat rp__cat--' + esc(r.category) + '">'
                          + esc(catLabel(r.category)) + '</span>'
                        : '')
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
        }).join('');

        $('list').querySelectorAll('[data-open]').forEach(function (b) {
            b.addEventListener('click', function () { openReport(b.dataset.open); });
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
            +   (r.category
                    ? '<span class="rp__cat rp__cat--' + esc(r.category) + '">'
                      + esc(catLabel(r.category)) + '</span>'
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

            + '<div class="adm-inline rmod__foot">'
            + '<select class="field__input" id="rp-status"'
            + ' aria-label="' + esc(T('rp_mark', '改狀態')) + '">'
            + STATUSES.map(function (st) {
                return '<option value="' + st + '"' + (r.status === st ? ' selected' : '') + '>'
                    + esc(T('st_' + st, st)) + '</option>';
            }).join('')
            + '</select>'
            + '<button class="btn btn--primary" type="button" id="rp-save">'
            + esc(locked ? T('rp_save_status', '更新狀態') : T('rp_save', '送出回覆'))
            + '</button>'
            + '</div>'
            + '<div class="inline-error" id="rp-msg" hidden></div>';

        $('rp-save').addEventListener('click', function () { save(r.id, locked); });
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
    //       伺服器／信箱／間隔進標題旁的 icon（設定值，看一次就夠）。
    //     原本四段擠成一行，真正要看的「最後一次」被推到最尾巴。
    // ZH: ⚠ icon 的內容用 textContent 填，不用 innerHTML ——
    //     host 與 folder 是設定檔來的字串，不是常數。
    function fillMailTip(b) {
        var tip = $('mail-tip');
        var body = $('mail-tip-body');
        if (!tip || !body) return;
        if (!b) { tip.hidden = true; return; }
        body.textContent = b.enabled
            ? T('rp_bounce_cfg', '退信回收：{h} · {f} · 每 {m} 分鐘')
                .replace('{h}', b.host).replace('{f}', b.folder)
                .replace('{m}', b.interval_minutes)
            : T('rp_bounce_off_why',
                '退信回收未啟用。寄給不存在信箱的信會永遠停在「已交付」，看不出來。');
        tip.hidden = false;
    }

    function bounceLine(b) {
        if (!b) return '';
        fillMailTip(b);
        // ZH: 未啟用時畫面上只留一句狀態，理由在 icon 裡 ——
        //     「為什麼要在意」看一次就夠，「現在是關的」才是每次都要看到的。
        if (!b.enabled) {
            return '<p class="footnote">' + esc(T('rp_bounce_off', '退信回收：未啟用')) + '</p>';
        }
        var when = T('rp_bounce_never', '尚未掃描過');
        if (b.last_scan) {
            var p = String(b.last_scan).split('|');
            when = (TW.when(p[0]) || p[0])
                + '（' + T('rp_bounce_counts', '讀 {s} 封、退信 {b} 封、回填 {a} 筆')
                    .replace('{s}', p[1] || 0).replace('{b}', p[2] || 0).replace('{a}', p[3] || 0) + '）';
        }
        return '<p class="footnote">'
            + esc(T('rp_bounce_on', '最後退信回收：{w}').replace('{w}', when))
            + '</p>';
    }

    async function loadMail() {
        var data;
        try {
            data = await api('/admin/email-log?limit=50');
        } catch (e) {
            $('mail').innerHTML = '<p class="footnote">'
                + esc(T('ov_fail_part', '這一段暫時讀不到（{w}）').replace('{w}', e.message)) + '</p>';
            return;
        }
        // ZH: 🔴 這支端點回的是**物件** `{counts, smtp_configured, from_email, bounce, logs}`，
        //     不是陣列。原本直接對它做 `rows.length` —— undefined 恆為 falsy，
        //     於是**不論有幾筆紀錄都顯示「沒有寄信紀錄。」**，而且不會有任何錯誤。
        //     （端點在 `14fbddd` 就改成物件了，前端一直沒跟上。）
        var rows = (data && data.logs) || [];
        var head0 = bounceLine(data && data.bounce);
        if (!rows.length) {
            $('mail').innerHTML = head0
                + '<p class="footnote">' + esc(T('rp_mail_none', '沒有寄信紀錄。')) + '</p>';
            return;
        }
        var head = [
            ['rp_m_to', '收件者'], ['rp_m_kind', '種類'],
            ['rp_m_status', '結果'], ['rp_m_when', '時間'],
        ];
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
        //     那正是上面 bounceLine() 的「退信回收：未啟用」要一直看得到的原因。
        $('mail').innerHTML =
            head0
            + '<div class="adm-tablewrap"><table class="adm-table"><thead><tr>'
            + head.map(function (h) { return '<th>' + esc(T(h[0], h[1])) + '</th>'; }).join('')
            + '</tr></thead><tbody>'
            + rows.map(function (m) {
                return '<tr>'
                    + '<td>' + esc(m.to_email) + '</td>'
                    + '<td class="mono">' + esc(m.kind || '—') + '</td>'
                    + '<td><span class="adm-pill adm-pill--' + esc(m.status) + '">'
                    + esc(T('st_' + m.status, m.status)) + '</span></td>'
                    + '<td>' + esc(TW.when(m.created_at) || '—') + '</td>'
                    + '</tr>';
            }).join('')
            + '</tbody></table></div>';
    }

    // ── 管理動作紀錄 ──────────────────────────────────────────────────────
    async function loadAudit() {
        var rows;
        try {
            rows = await api('/admin/audit?limit=50');
        } catch (e) {
            $('audit').innerHTML = '<p class="footnote">'
                + esc(T('ov_fail_part', '這一段暫時讀不到（{w}）').replace('{w}', e.message)) + '</p>';
            return;
        }
        var list = rows.items || rows || [];
        if (!list.length) {
            $('audit').innerHTML = '<p class="footnote">'
                + esc(T('rp_audit_none', '還沒有任何管理動作。')) + '</p>';
            return;
        }
        var head = [
            ['rp_a_who', '管理者'], ['rp_a_what', '動作'],
            ['rp_a_target', '對象'], ['rp_a_when', '時間'],
        ];
        $('audit').innerHTML =
            '<div class="adm-tablewrap"><table class="adm-table"><thead><tr>'
            + head.map(function (h) { return '<th>' + esc(T(h[0], h[1])) + '</th>'; }).join('')
            + '</tr></thead><tbody>'
            + list.map(function (a) {
                return '<tr>'
                    + '<td>' + esc(a.admin_username || (a.admin_id || '').slice(0, 8) || '—') + '</td>'
                    + '<td class="mono">' + esc(a.action) + '</td>'
                    + '<td>' + esc(a.target_username || (a.target_user || '').slice(0, 8) || '—') + '</td>'
                    + '<td>' + esc(TW.when(a.timestamp) || '—') + '</td>'
                    + '</tr>';
            }).join('')
            + '</tbody></table></div>';
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

    function renderNews() {
        var live = NEWS.filter(function (a) { return a.is_visible; }).length;
        $('news-sum').textContent = T('rp_news_sum', '{n} 則，其中 {v} 則公開中')
            .replace('{n}', NEWS.length).replace('{v}', live);

        if (!NEWS.length) {
            $('news').innerHTML = '<p class="footnote">'
                + esc(T('rp_news_none', '還沒有任何公告。')) + '</p>';
            return;
        }

        var cols = [['rp_news_title', '標題'], ['rp_news_when', '發布時間'],
                    ['rp_news_state', '狀態'], ['', '']];
        $('news').innerHTML =
            '<div class="adm-tablewrap"><table class="adm-table"><thead><tr>'
            + cols.map(function (c) {
                return '<th>' + esc(c[0] ? T(c[0], c[1]) : '') + '</th>';
            }).join('')
            + '</tr></thead><tbody>'
            + NEWS.map(function (a) {
                return '<tr>'
                    + '<td>' + (a.is_pinned
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
                    + '<button class="btn btn--minor" type="button" data-news-edit="' + esc(a.id) + '">'
                    + esc(T('pp_edit', '編輯')) + '</button> '
                    + '<button class="btn btn--minor" type="button" data-news-del="' + esc(a.id) + '">'
                    + esc(T('pf_m_del', '刪除')) + '</button></td>'
                    + '</tr>';
            }).join('')
            + '</tbody></table></div>';

        $('news').querySelectorAll('[data-news-edit]').forEach(function (b) {
            b.addEventListener('click', function () {
                openNewsForm(NEWS.filter(function (x) {
                    return String(x.id) === b.dataset.newsEdit;
                })[0]);
            });
        });
        $('news').querySelectorAll('[data-news-del]').forEach(function (b) {
            b.addEventListener('click', function () { delNews(b.dataset.newsDel); });
        });
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
            + '<label class="field"><span class="field__label" for="nw-title">'
            + esc(T('rp_news_title', '標題')) + '</span>'
            + '<input class="field__input" id="nw-title" type="text" value="'
            + esc(e.title || '') + '"></label>'
            + '<label class="field"><span class="field__label" for="nw-body">'
            + esc(T('rp_news_body', '內容')) + '</span>'
            + '<textarea class="field__input" id="nw-body" rows="8">'
            + esc(e.body || '') + '</textarea></label>'
            // ZH: 明講會原樣顯示 —— 有人會想貼 HTML 進來。
            + '<p class="footnote">' + esc(T('rp_news_plain',
                '純文字，會原樣顯示給使用者。貼 HTML 進來不會變成排版，會看到標籤本身。')) + '</p>'
            + pick('nw-pin', 'rp_news_pin', '置頂', e.is_pinned)
            + pick('nw-vis', 'rp_news_vis', '公開', a ? e.is_visible : 1)
            // ZH: 附件。新公告還沒有 id，所以檔案是**存檔之後**才送上去的
            //     （見 saveNews）——這裡先收在 input 裡。
            + '<label class="field"><span class="field__label" for="nw-files">'
            + esc(T('rp_news_attach', '附件')) + '</span>'
            + '<input class="field__input" id="nw-files" type="file" multiple '
            + 'accept=".pdf,.docx,.xlsx,.pptx,.png,.jpg,.jpeg,.zip"></label>'
            + '<p class="footnote">' + esc(T('rp_news_attach_hint',
                '可以放 pdf / docx / xlsx / pptx / png / jpg / zip。單檔上限見系統設定。')) + '</p>'
            + '<div id="nw-have"></div>'
            + '<div class="adm-inline rmod__foot">'
            + '<button class="btn btn--primary" type="button" id="nw-ok">'
            + esc(T('pp_save', '儲存')) + '</button>'
            + '<button class="btn btn--minor" type="button" id="nw-x">'
            + esc(T('pf_cancel', '取消')) + '</button></div>';

        renderHave(a);
        dlg.showModal();
        $('nw-ok').addEventListener('click', function () { saveNews(a); });
        $('nw-x').addEventListener('click', function () { dlg.close(); });
        $('nw-title').focus();
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
                    say('news-msg', e.message);
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
            say('news-msg', T('rp_news_need', '標題與內容都要填。'));
            return;
        }
        // ZH: 下拉的值是字串，'0' 是 truthy —— 要明確比對，不能用 !!。
        var payload = {
            title: title, body: body,
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
            say('news-msg', e.message);
        }
    }

    async function delNews(id) {
        var a = NEWS.filter(function (x) { return String(x.id) === String(id); })[0] || {};
        // ZH: 明講刪掉之後使用者端也會消失 —— 這是唯一一個會影響到所有人的操作。
        if (!confirm(T('rp_news_del_confirm',
                '要刪掉「{n}」嗎？使用者端也會跟著消失，而且沒辦法復原。')
                .replace('{n}', a.title || id))) return;
        try {
            await api('/admin/announcements/' + encodeURIComponent(id), { method: 'DELETE' });
            await loadNews();
        } catch (e) { say('news-msg', e.message); }
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

    loadNews();
    load();
    loadMail();
    loadAudit();
    document.addEventListener('prefs:langchanged', function () {
        loadNews(); load(); loadMail(); loadAudit();
    });
})();
