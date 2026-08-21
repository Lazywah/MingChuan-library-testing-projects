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
        $('news-form').innerHTML =
            '<div class="adm-card__title">'
            + esc(a ? T('rp_news_edit', '編輯公告') : T('rp_news_new', '寫一則公告')) + '</div>'
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
            + '<div class="ds__actions">'
            + '<button class="btn btn--primary" type="button" id="nw-ok">'
            + esc(T('pp_save', '儲存')) + '</button>'
            + '<button class="btn btn--minor" type="button" id="nw-x">'
            + esc(T('pf_cancel', '取消')) + '</button></div>';
        $('news-form').hidden = false;
        $('nw-ok').addEventListener('click', function () { saveNews(a); });
        $('nw-x').addEventListener('click', function () { $('news-form').hidden = true; });
        $('nw-title').focus();
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
            await api(a ? '/admin/announcements/' + encodeURIComponent(a.id)
                        : '/admin/announcements', {
                method: a ? 'PUT' : 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });
            $('news-form').hidden = true;
            flash('news-msg', T('rp_news_saved', '公告已更新。'), 5000);
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
