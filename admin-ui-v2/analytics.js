/* ==========================================================================
 * analytics.js — 數據（要交報告時才看）
 *
 * ZH: 兩個來源：
 *       GET /external-ai/admin/consumption   MYAI 點數（**目前唯一有量的資料**）
 *       GET /admin/analytics                 平台自己的學系／工具用量
 *       GET /admin/jobs                      訓練任務
 *
 * ZH: 🔴 **圖表全部自繪 SVG，不引入 chart.js。**
 *     舊版把 chart.js 的預設樣式直接放進去（灰底、預設藍綠、預設圖例），
 *     與頁面完全沒有整合；而且它是外部 CDN —— 圖書館對外連線受限或 CDN 掛掉時，
 *     這一頁會整片壞掉。
 *
 * ZH: 🔴 **不畫圓餅。** 舊版那張「帳號狀態分佈」是一整片單色的圓（只有一個分類），
 *     完全不傳達資訊。橫條圖在任何筆數下都讀得出來，而且長度可以直接比。
 *
 * ⚠ `top` 裡有**真實姓名與 email**。這一頁是看趨勢的，不是查人的 ——
 *   只顯示名字，email 收在 title 裡（要查某個人請去「人」那一頁）。
 * ========================================================================== */
(function () {
    'use strict';

    var API = '/api/v1';
    var PERIODS = [[7, 'an_d7', '近 7 天'], [30, 'an_d30', '近 30 天'],
                   [90, 'an_d90', '近 90 天'], [0, 'an_all', '全部']];
    // ZH: ⚠ 0 = 全部。後端註解特別提過「不能用 `days or 30`」——
    //     0 在 Python 是 falsy，會被當成沒給值。
    var DAYS = 30;

    function $(id) { return document.getElementById(id); }

    function token() {
        return sessionStorage.getItem('ai_hud_token') || localStorage.getItem('ai_hud_token');
    }

    function esc(s) {
        return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
            return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
        });
    }

    async function get(path) {
        var r = await fetch(API + path, { headers: { Authorization: 'Bearer ' + token() } });
        if (r.status === 401) { location.replace('login.html'); throw new Error('401'); }
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.json();
    }

    function safe(p) {
        return p.catch(function (e) { return { __failed: (e && e.message) || String(e) }; });
    }

    function failed(x) { return x && x.__failed; }

    function failBox(x) {
        return '<p class="footnote">'
            + esc(T('ov_fail_part', '這一段暫時讀不到（{w}）').replace('{w}', x.__failed)) + '</p>';
    }

    // ZH: 大數字要有千分位 —— 7288 與 72880 在沒有分隔時一眼分不出來。
    function num(n) {
        return Number(n || 0).toLocaleString('en-US');
    }

    // ── 橫條圖（自繪，不用任何函式庫）────────────────────────────────────
    //
    // ZH: 為什麼是橫條而不是圓餅或折線：
    //   - 標籤可以是完整的中文（圓餅的標籤要嘛擠在一起要嘛拉線出去）
    //   - 一筆與二十筆都讀得出來（圓餅在一筆時是一整片，二十筆時全是細片）
    //   - 長度可以直接比，不必解讀角度
    //
    // ZH: 用 HTML + CSS 而不是 <svg>：這是「長度成比例的長條」，
    //     div 的寬度百分比就做得到，而且字會跟著字級設定縮放、可以被選取。
    function bars(rows, labelKey, valueKey, unit) {
        if (!rows || !rows.length) return '';
        var max = rows.reduce(function (m, r) { return Math.max(m, Number(r[valueKey]) || 0); }, 0) || 1;
        return '<div class="adm-bars">' + rows.map(function (r) {
            var v = Number(r[valueKey]) || 0;
            var label = r.__label != null ? r.__label : r[labelKey];
            return '<div class="adm-bar">'
                + '<span class="adm-bar__label"' + (r.__title ? ' title="' + esc(r.__title) + '"' : '') + '>'
                + esc(label || '—') + '</span>'
                + '<span class="adm-bar__track">'
                + '<i style="width:' + (v / max * 100) + '%"></i></span>'
                + '<span class="adm-bar__val">' + esc(num(v)) + (unit ? ' ' + esc(unit) : '') + '</span>'
                + '</div>';
        }).join('') + '</div>';
    }

    function stat(labelKey, zh, value) {
        return '<div class="adm-stat">'
            + '<div class="adm-stat__label">' + esc(T(labelKey, zh)) + '</div>'
            + '<div class="adm-stat__value">' + esc(num(value)) + '</div>'
            + '</div>';
    }

    // ── MYAI 消耗 ─────────────────────────────────────────────────────────
    function renderMyai(d) {
        if (failed(d)) { $('myai').innerHTML = failBox(d); return; }

        if (!d.tx_count) {
            // ZH: 明確說「這段期間沒有」，而不是畫一張空圖 ——
            //     空圖看起來像壞掉，而這其實是一個正常的答案。
            $('myai').innerHTML = '<p class="footnote">'
                + esc(T('an_none', '這段期間沒有任何交易紀錄。')) + '</p>';
            return;
        }

        var pts = T('an_points', '點');
        var top = (d.top || [])
            // ZH: 0 點的不放進「消耗最多的帳號」—— 那份清單要回答的是
            //     「誰花得多」，列出沒有消耗的人只是雜訊，
            //     而且會讓實際有消耗的那幾個被擠到看不清楚。
            .filter(function (r) { return Number(r.consumed) > 0; })
            .map(function (r) {
                // ⚠ ZH: 這一頁是看趨勢的，不是查人的。只顯示名字，
                //     email 收在 title 裡 —— 要查某個人請去「人」那一頁。
                return Object.assign({}, r, { __label: r.name || r.vendor_sn, __title: r.email || '' });
            });
        var byRole = (d.by_role || []).map(function (r) {
            return Object.assign({}, r, {
                __label: r.role === 'unbound' ? T('an_unbound', '未綁定') : T('role_' + r.role, r.role),
            });
        });

        $('myai').innerHTML =
            '<p class="footnote">' + esc(T('an_myai_src', '')) + '</p>'
            + '<div class="adm-stats">'
            + stat('an_consumed', '期間總消耗', d.total_consumed)
            + stat('an_tx', '交易筆數', d.tx_count)
            + stat('an_uses', 'AI 使用次數', d.total_uses)
            + stat('an_logins', '登入次數', d.total_logins)
            + stat('an_accounts', '有資料的帳號', d.accounts_with_data)
            + '</div>'

            + (d.unmapped_models ? '<div class="adm-alert adm-alert--warn"><span>'
                + esc(T('an_unmapped', '有 {n} 個模型代碼還沒對應 —— 它們會以原始代碼顯示。')
                    .replace('{n}', d.unmapped_models))
                + '</span><a class="btn btn--minor" href="platform.html">'
                + esc(T('ov_a_go', '去看')) + '</a></div>' : '')

            // ZH: 有交易但完全沒有消耗時（例如這期間只有人登入），後端不會回任何
            //     圖表資料，下面會是一整片空白 —— 那看起來像載入失敗，其實是個
            //     正常的答案。明講一句，跟 tx_count === 0 的處理是同一個道理。
            + (!d.total_consumed ? '<p class="footnote">'
                + esc(T('an_no_spend', '這段期間沒有任何點數消耗（上面的交易是登入之類不計費的紀錄）。'))
                + '</p>' : '')

            + block('an_trend', '每日消耗', bars(d.series, 'date', 'consumed', pts))
            + block('an_top', '消耗最多的帳號', bars(top, 'name', 'consumed', pts))
            + block('an_models', '用了哪些模型', bars(d.models, 'display_name', 'points', pts))
            + '<div class="adm-cols">'
            + block('an_by_category', '依類別', bars(d.by_category, 'category', 'consumed', pts))
            + block('an_by_provider', '依供應者', bars(d.by_provider, 'provider', 'consumed', pts))
            + block('an_by_role', '依身分', bars(byRole, 'role', 'consumed', pts))
            + block('an_by_dept', '依學系', bars(d.by_department, 'department', 'consumed', pts))
            + '</div>';
    }

    function block(key, zh, inner) {
        if (!inner) return '';
        return '<section class="adm-block">'
            + '<h3 class="adm-block__title">' + esc(T(key, zh)) + '</h3>' + inner + '</section>';
    }

    // ── 訓練任務 ──────────────────────────────────────────────────────────
    function renderJobs(jobs) {
        if (failed(jobs)) { $('jobs').innerHTML = failBox(jobs); return; }
        if (!jobs.length) {
            $('jobs').innerHTML = '<p class="footnote">'
                + esc(T('an_jobs_none', '還沒有任何訓練任務。')) + '</p>';
            return;
        }
        var by = {};
        jobs.forEach(function (j) { by[j.status] = (by[j.status] || 0) + 1; });
        $('jobs').innerHTML = '<div class="adm-stats">'
            + stat('an_j_total', '總數', jobs.length)
            + stat('an_j_done', '已完成', by.completed || 0)
            + stat('an_j_failed', '失敗', by.failed || 0)
            + stat('an_j_running', '執行中', by.running || 0)
            + '</div>';
    }

    // ── 平台使用（學系）───────────────────────────────────────────────────
    function renderPlatform(a) {
        if (failed(a)) { $('platform').innerHTML = failBox(a); return; }
        var rows = a.department_stats || [];
        if (!rows.length) {
            $('platform').innerHTML = '<p class="footnote">'
                + esc(T('an_platform_none', '還沒有足夠的資料。')) + '</p>';
            return;
        }
        var head = [
            ['an_dept', '學系'], ['an_users', '人數'],
            ['an_dept_logins', '登入次數'], ['', 'Token'],       // ZH: 中英一樣，不需要 key
        ];
        $('platform').innerHTML =
            '<div class="adm-tablewrap"><table class="adm-table"><thead><tr>'
            + head.map(function (h) { return '<th>' + esc(T(h[0], h[1])) + '</th>'; }).join('')
            + '</tr></thead><tbody>'
            + rows.map(function (r) {
                return '<tr>'
                    + '<td>' + esc(r.department) + '</td>'
                    + '<td class="num">' + esc(num(r.user_count)) + '</td>'
                    + '<td class="num">' + esc(num(r.total_logins)) + '</td>'
                    + '<td class="num">' + esc(num(r.total_tokens)) + '</td>'
                    + '</tr>';
            }).join('')
            + '</tbody></table></div>';
    }

    // ── 期間 ──────────────────────────────────────────────────────────────
    function renderPeriods() {
        $('periods').innerHTML = PERIODS.map(function (p) {
            return '<button class="btn btn--minor' + (DAYS === p[0] ? ' is-current' : '') + '"'
                + ' type="button" data-days="' + p[0] + '"'
                + (DAYS === p[0] ? ' aria-current="true"' : '') + '>'
                + esc(T(p[1], p[2])) + '</button>';
        }).join('');
        $('periods').querySelectorAll('[data-days]').forEach(function (b) {
            b.addEventListener('click', function () {
                DAYS = parseInt(b.dataset.days, 10);
                load();
            });
        });
    }

    async function load() {
        renderPeriods();
        var out = await Promise.all([
            safe(get('/external-ai/admin/consumption?days=' + DAYS)),
            safe(get('/admin/jobs?limit=500')),
            safe(get('/admin/analytics')),
        ]);
        renderMyai(out[0]);
        renderJobs(out[1]);
        renderPlatform(out[2]);
    }

    load();
    document.addEventListener('prefs:langchanged', load);
})();
