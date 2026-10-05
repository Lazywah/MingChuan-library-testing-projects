/* ==========================================================================
 * [畫面: 管理端 AI 查詢] — 用一句話查平台狀況（v4.37，擁有者 2026-10-04）
 *
 * ZH: 後端 POST /api/v1/admin/ai/ask。擁有者裁定：本機模型、只能查不能改。
 * ZH: 每一筆都畫三層：模型的說明 → 程式算出的「判斷」→ 可展開的原始資料。
 *     🔴 原始資料一定要畫 —— 本機 8B 模型整理的話可能講錯，
 *     管理員要能直接對照，不是只能相信模型。
 * ZH: 查詢紀錄只留在這一頁（重新整理就沒了）。稽核在後端（admin_actions 的 ai_query）。
 * ========================================================================== */
(function () {
    'use strict';

    var API = '/api/v1';

    function $(id) { return document.getElementById(id); }

    function token() {
        return sessionStorage.getItem('ai_hud_token') || localStorage.getItem('ai_hud_token');
    }

    function esc(s) {
        return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
            return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
        });
    }

    // ZH: 只認 **粗體** 一種標記（判斷句與模型回答都會用）。其餘照純文字、保留換行。
    //     先 esc 再換標記 —— 反過來的話資料裡的 <script> 會變成真的標籤。
    function rich(s) {
        return esc(s).replace(/\*\*(.+?)\*\*/g, '<b>$1</b>');
    }

    function zhOnly(text) {
        var parts = String(text).split(' | ');
        var lang = (window.Prefs && Prefs.get().ui_lang) || 'zh';
        var want = parts.filter(function (p) {
            return p.indexOf(lang === 'en' ? 'EN:' : 'ZH:') === 0;
        })[0];
        return (want || parts[0] || '').replace(/^(ZH|EN):\s*/, '');
    }

    var TOOL_LABEL = {
        user_report:   function () { return T('ai_tool_user', '帳號查詢'); },
        myai_status:   function () { return T('ai_tool_myai', 'MYAI 同步'); },
        recent_errors: function () { return T('ai_tool_err', '最近的錯誤'); },
        job_report:    function () { return T('ai_tool_job', '訓練查詢'); },
        system_status: function () { return T('ai_tool_sys', '系統狀態'); },
        email_report:  function () { return T('ai_tool_mail', '寄信紀錄'); },
        admin_activity: function () { return T('ai_tool_audit', '管理操作紀錄'); },
        log_search:    function () { return T('ai_tool_log', '日誌搜尋'); },
    };

    function valueText(v) {
        if (v == null || v === '') return '—';
        if (typeof v === 'boolean') return v ? T('ai_yes', '是') : T('ai_no', '否');
        if (typeof v === 'object') return JSON.stringify(v);
        return String(v);
    }

    function factsHtml(facts) {
        var keys = Object.keys(facts || {});
        if (!keys.length) return '';
        return '<div class="adm-tablewrap"><table class="adm-table ai-kv"><tbody>'
            + keys.map(function (k) {
                return '<tr><th scope="row">' + esc(k) + '</th><td>' + esc(valueText(facts[k])) + '</td></tr>';
            }).join('') + '</tbody></table></div>';
    }

    function tableHtml(name, rows) {
        if (!rows || !rows.length) {
            return '<h4 class="ai-sub">' + esc(name) + '</h4><p class="footnote">'
                + esc(T('ai_none', '（沒有資料）')) + '</p>';
        }
        var cols = Object.keys(rows[0]);
        return '<h4 class="ai-sub">' + esc(name) + '</h4><div class="adm-tablewrap"><table class="adm-table"><thead><tr>'
            + cols.map(function (c) { return '<th>' + esc(c) + '</th>'; }).join('')
            + '</tr></thead><tbody>'
            + rows.map(function (r) {
                return '<tr>' + cols.map(function (c) { return '<td>' + esc(valueText(r[c])) + '</td>'; }).join('') + '</tr>';
            }).join('') + '</tbody></table></div>';
    }

    function itemHtml(q, d) {
        var meta = d.tool
            ? T('ai_meta', '查詢：{t}　模型：{m}　{s} 秒')
                .replace('{t}', (TOOL_LABEL[d.tool] || function () { return d.tool; })())
                .replace('{m}', d.model).replace('{s}', d.elapsed)
            : T('ai_meta_none', '模型：{m}　{s} 秒').replace('{m}', d.model).replace('{s}', d.elapsed);
        var data = d.data || {};
        var findings = (data.findings || []).map(function (f) { return '<li>' + rich(f) + '</li>'; }).join('');
        var tables = Object.keys(data.tables || {}).map(function (k) { return tableHtml(k, data.tables[k]); }).join('');
        return '<article class="ai-item">'
            + '<p class="ai-q-text">' + esc(q) + '</p>'
            + '<p class="footnote">' + esc(meta) + '</p>'
            + '<div class="ai-answer">' + rich(d.answer || '') + '</div>'
            + (findings ? '<h3 class="ai-sub">' + esc(T('ai_findings', '程式算出的判斷')) + '</h3><ul class="ai-findings">' + findings + '</ul>' : '')
            + (d.data ? '<details class="ai-raw"><summary>' + esc(T('ai_raw', '原始資料（以這裡為準）')) + '</summary>'
                + factsHtml(data.facts) + tables + '</details>' : '')
            + '</article>';
    }

    async function ask(q) {
        q = (q || '').trim();
        if (!q) return;
        $('ai-err').hidden = true;
        var go = $('ai-go');
        go.disabled = true;
        go.textContent = T('ai_working', '查詢中…（本機模型，約 5–15 秒）');
        try {
            var r = await fetch(API + '/admin/ai/ask', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + token() },
                body: JSON.stringify({ question: q }),
            });
            if (r.status === 401) { location.replace('login.html'); return; }
            var body = await r.json().catch(function () { return {}; });
            if (!r.ok) throw new Error(zhOnly(body.detail || ('HTTP ' + r.status)));
            var empty = $('ai-empty');
            if (empty) empty.remove();
            $('ai-list').insertAdjacentHTML('afterbegin', itemHtml(q, body));
            $('ai-q').value = '';
        } catch (e) {
            $('ai-err').textContent = T('ai_fail', '查詢失敗') + '（' + e.message + '）';
            $('ai-err').hidden = false;
        } finally {
            go.disabled = false;
            go.textContent = T('ai_ask', '查詢');
        }
    }

    $('ai-form').addEventListener('submit', function (e) {
        e.preventDefault();
        ask($('ai-q').value);
    });
    // ZH: Enter 送出、Shift+Enter 換行（textarea 預設是換行，提問通常只有一句）。
    $('ai-q').addEventListener('keydown', function (e) {
        if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
            e.preventDefault();
            ask($('ai-q').value);
        }
    });
    document.querySelectorAll('.ai-chips [data-q]').forEach(function (b) {
        b.addEventListener('click', function () { ask(b.dataset.q); });
    });
    document.querySelectorAll('.ai-chips [data-fill]').forEach(function (b) {
        b.addEventListener('click', function () {
            var q = $('ai-q');
            q.value = b.dataset.fill;
            q.focus();
            // ZH: 「在日誌裡找「」」—— 游標放進引號中間，直接打要找的字。
            var at = q.value.lastIndexOf('」');
            if (at > 0) q.setSelectionRange(at, at);
        });
    });
})();
