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
        el.hidden = !text;
    }

    // ZH: 只給成功訊息用（錯誤不該自己消失，讀者需要時間看）。
    var _timers = {};
    function flash(id, text, ms) {
        say(id, text);
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

        $('filters').querySelectorAll('[data-filter]').forEach(function (b) {
            b.addEventListener('click', function () {
                FILTER = b.dataset.filter;
                load();
            });
        });
    }

    function renderReports() {
        if (!REPORTS.length) {
            $('list').innerHTML = '<p class="footnote">' + esc(T('rp_none', '沒有符合的回報。')) + '</p>';
            return;
        }

        $('list').innerHTML = REPORTS.map(function (r) {
            var who = r.username_at_report || T('rp_anon', '（帳號已刪除）');
            return '<section class="adm-card" data-report="' + esc(r.id) + '">'
                + '<div class="adm-card__title">'
                + '<span class="adm-pill adm-pill--' + esc(r.status) + '">'
                + esc(T('st_' + r.status, r.status)) + '</span>　'
                + esc(T('rp_from', '{who} 於 {when}')
                    .replace('{who}', who).replace('{when}', TW.dateTime(r.created_at)))
                + '</div>'

                // ZH: 用 textContent 的等價寫法（esc）—— 回報內容是使用者輸入的。
                + '<p class="adm-report__body">' + esc(r.body) + '</p>'

                + (r.diagnostics ? '<details class="fold">'
                    + '<summary class="fold__summary">' + esc(T('rp_diag', '一起送出的診斷資訊')) + '</summary>'
                    + '<pre class="diag">' + esc(prettyDiag(r.diagnostics)) + '</pre>'
                    + '</details>' : '')

                + '<label class="field">'
                + '<span class="field__label" for="rep-' + esc(r.id) + '">'
                + esc(T('rp_reply', '回覆')) + '</span>'
                + '<textarea class="field__input" id="rep-' + esc(r.id) + '" rows="3"'
                + ' placeholder="' + esc(T('rp_reply_ph', '寫給他看的回覆…')) + '">'
                + esc(r.admin_reply || '') + '</textarea></label>'
                + '<p class="footnote">' + esc(T('rp_reply_hint',
                    '他會在「問題回報」那一頁看到這段話。刻意不寄通知信。')) + '</p>'
                + (r.replied_at ? '<p class="footnote">'
                    + esc(T('rp_replied', '已於 {when} 回覆').replace('{when}', TW.dateTime(r.replied_at)))
                    + '</p>' : '')

                + '<div class="adm-inline">'
                + '<select class="field__input" id="st-' + esc(r.id) + '"'
                + ' aria-label="' + esc(T('rp_mark', '改狀態')) + '">'
                + STATUSES.map(function (s) {
                    return '<option value="' + s + '"' + (r.status === s ? ' selected' : '') + '>'
                        + esc(T('st_' + s, s)) + '</option>';
                }).join('')
                + '</select>'
                + '<button class="btn btn--minor" type="button" data-save="' + esc(r.id) + '">'
                + esc(T('rp_save', '送出回覆')) + '</button>'
                + '</div>'
                + '<div class="inline-error" id="msg-' + esc(r.id) + '" hidden></div>'
                + '</section>';
        }).join('');

        $('list').querySelectorAll('[data-save]').forEach(function (b) {
            b.addEventListener('click', function () { save(b.dataset.save); });
        });
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

    async function save(id) {
        var body = {
            admin_reply: $('rep-' + id).value,
            status: $('st-' + id).value,
        };
        try {
            await api('/admin/reports/' + encodeURIComponent(id), {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });
            flash('msg-' + id, T('rp_saved', '已送出'));
            await load();          // ZH: 重讀 —— 狀態改了之後可能就不屬於目前的篩選了
        } catch (e) {
            say('msg-' + id, T('rp_fail', '存不起來（{w}）').replace('{w}', e.message));
        }
    }

    // ── 寄信紀錄 ──────────────────────────────────────────────────────────
    async function loadMail() {
        var rows;
        try {
            rows = await api('/admin/email-log?limit=50');
        } catch (e) {
            $('mail').innerHTML = '<p class="footnote">'
                + esc(T('ov_fail_part', '這一段暫時讀不到（{w}）').replace('{w}', e.message)) + '</p>';
            return;
        }
        if (!rows.length) {
            $('mail').innerHTML = '<p class="footnote">' + esc(T('rp_mail_none', '沒有寄信紀錄。')) + '</p>';
            return;
        }
        var head = [
            ['rp_m_to', '收件者'], ['rp_m_kind', '種類'],
            ['rp_m_status', '結果'], ['rp_m_when', '時間'],
        ];
        $('mail').innerHTML =
            '<p class="footnote">' + esc(T('rp_mail_hint', '')) + '</p>'
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
    async function load() {
        try {
            var q = FILTER ? '?status=' + encodeURIComponent(FILTER) : '';
            var summary = await api('/admin/reports/summary');
            REPORTS = await api('/admin/reports' + q);
            renderFilters(summary.counts || {});
            renderReports();
        } catch (e) {
            $('list').innerHTML = '<p class="footnote">'
                + esc(T('ov_fail_part', '這一段暫時讀不到（{w}）').replace('{w}', e.message)) + '</p>';
        }
    }

    load();
    loadMail();
    loadAudit();
    document.addEventListener('prefs:langchanged', function () {
        load(); loadMail(); loadAudit();
    });
})();
