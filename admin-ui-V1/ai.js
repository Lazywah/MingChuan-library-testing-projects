/* ==========================================================================
 * [畫面: 管理端 AI 查詢] — 用一句話查平台狀況（v4.37，擁有者 2026-10-04）
 *
 * ZH: 後端 POST /api/v1/admin/ai/ask。擁有者裁定：本機模型、只能查不能改。
 * ZH: 每一筆都畫三層：模型的說明 → 程式算出的「判斷」→ 可展開的原始資料。
 *     🔴 原始資料一定要畫 —— 本機 8B 模型整理的話可能講錯，
 *     管理員要能直接對照，不是只能相信模型。
 * ZH: 查詢紀錄只留在這一頁（重新整理就沒了）。稽核在後端（admin_actions 的 ai_query）。
 * ZH: v4.45 版面整理（計畫第 4 節）：預設問題收成「常用問題▾」、紀錄只留最近 AI_KEEP 筆、
 *     加「清除紀錄」。三層結構（模型說明 → 程式判斷 → 原始資料）一個字都沒動。
 * ========================================================================== */
(function () {
    'use strict';

    var API = '/api/v1';

    function $(id) { return document.getElementById(id); }

    // ZH: 畫面上最多留幾筆。新的在最上面，超過就從最舊的那筆刪。
    //     原本沒有上限 —— 每筆展開後又有好幾張表，查幾次之後整頁就是一疊長得一樣的框，
    //     要的那一筆反而找不到。10 是計畫定的數字（與紀錄表一頁 10 筆同一個量級）。
    // ZH: 這只是**畫面**。稽核紀錄在後端，刪畫面上的不影響它。
    var AI_KEEP = 10;

    /* ZH: 常用問題（v4.45 從八顆按鈕收成一個下拉，擁有者「一排按鈕收成 ▾」的方向）。
     * ZH: 兩組行為不同，所以分組、組名就寫行為：
     *       直接查 —— 點了就送出 q（原本的 data-q）
     *       先填入 —— 只把 fill 放進輸入框，等人補完再送（原本的 data-fill）
     *     原本兩種長得一模一樣，唯一的差別是結尾有沒有「…」。
     * ZH: 🔴 q／fill 是送給後端的**問句本身**，刻意不翻譯（與原本 HTML 的 data-q 相同）——
     *     後端先用中文關鍵字挑工具（services/admin_ai.py 的 _route_by_rules），
     *     送英文問句就掉到模型判斷那一路，慢而且不一定挑得對。按鈕上的字才走 i18n。
     */
    var PRESETS = [
        { label: true, key: 'dz_an_ai_grp_run', zh: '直接查' },
        { id: 'ai-ex-myai',  key: 'ai_ex_myai',  zh: 'MYAI 同步正常嗎',        q: 'MYAI 同步正常嗎' },
        { id: 'ai-ex-err',   key: 'ai_ex_err',   zh: '最近 24 小時有什麼錯誤', q: '最近 24 小時有什麼錯誤' },
        { id: 'ai-ex-sys',   key: 'ai_ex_sys',   zh: '系統狀態',               q: '系統狀態' },
        { id: 'ai-ex-mail',  key: 'ai_ex_mail',  zh: '最近 7 天寄出的信',      q: '最近 7 天寄出的信' },
        { id: 'ai-ex-alert', key: 'ai_ex_alert', zh: '最近的告警信',           q: '最近寄給管理員的告警信' },
        { id: 'ai-ex-audit', key: 'ai_ex_audit', zh: '最近的管理操作',         q: '最近 30 天的管理操作紀錄' },
        { label: true, key: 'dz_an_ai_grp_fill', zh: '先填入' },
        { id: 'ai-ex-log',   key: 'ai_ex_log',   zh: '在日誌裡找…',            fill: '在日誌裡找「」' },
        { id: 'ai-ex-user',  key: 'ai_ex_user',  zh: '查帳號（輸入學號）',     fill: '查帳號 ' },
    ];

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
            trimList();
            renderHead();
            $('ai-q').value = '';
        } catch (e) {
            $('ai-err').textContent = T('ai_fail', '查詢失敗') + '（' + e.message + '）';
            $('ai-err').hidden = false;
        } finally {
            go.disabled = false;
            go.textContent = T('ai_ask', '查詢');
        }
    }

    // ZH: 超過 AI_KEEP 筆就刪最舊的（在最下面）。
    function trimList() {
        var items = $('ai-list').querySelectorAll('.ai-item');
        for (var i = AI_KEEP; i < items.length; i++) items[i].remove();
    }

    // ZH: 結果區標題列：數量貼在標題旁，有紀錄時才出現「只保留最近 N 筆」與「清除紀錄」。
    //     沒有紀錄時數量清空（.adm-head__count:empty 會自己藏起來），不要留一顆「0」。
    // ZH: 「只保留…」的字在這裡組（不寫在 HTML 的 data-i18n 上）—— 字典裡是 {n} 佔位符，
    //     交給 prefs.js 換語言的話畫面上會出現字面的 {n}。所以換語言時也要重畫一次。
    function renderHead() {
        var n = $('ai-list').querySelectorAll('.ai-item').length;
        $('ai-count').textContent = n ? String(n) : '';
        $('ai-keep').textContent = T('dz_an_ai_keep', '只保留最近 {n} 筆').replace('{n}', AI_KEEP);
        $('ai-keep').hidden = !n;
        $('ai-clear').hidden = !n;
    }

    $('ai-clear').addEventListener('click', function () {
        $('ai-list').innerHTML = '<p class="footnote" id="ai-empty" data-i18n="ai_empty">'
            + esc(T('ai_empty', '還沒有查詢。')) + '</p>';
        renderHead();
        // ZH: 按鈕自己剛被藏起來 —— 焦點不放回去的話會掉到 <body>，鍵盤使用者要從頭 Tab。
        $('ai-q').focus();
    });

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
    // ZH: 常用問題▾。選單的開關、Esc、上下鍵、點外面收起來都在 AdminMenu.wire（admin-chrome.js）；
    //     這裡只接每一項自己的動作。
    $('ai-ex').innerHTML = AdminMenu.html({
        id: 'ai-presets',
        label: { key: 'ai_examples', zh: '常用問題' },
        items: PRESETS,
    });
    AdminMenu.wire('ai-presets');
    PRESETS.forEach(function (p) {
        if (!p.id) return;
        $(p.id).addEventListener('click', function () {
            var q = $('ai-q');
            if (p.q) {
                // ZH: 選單一點就收起來，焦點原本在選單項上 —— 放回「常用問題▾」，
                //     不然會掉到 <body>。
                $('ai-presets').focus();
                ask(p.q);
                return;
            }
            q.value = p.fill;
            q.focus();
            // ZH: 「在日誌裡找「」」—— 游標放進引號中間，直接打要找的字。
            var at = q.value.lastIndexOf('」');
            if (at > 0) q.setSelectionRange(at, at);
        });
    });

    renderHead();
    document.addEventListener('prefs:langchanged', renderHead);
})();
