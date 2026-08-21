/* ==========================================================================
 * analytics.js — 數據（要交報告時才看）
 *
 * ZH: 兩個來源：
 *       GET /external-ai/admin/consumption   MYAI 點數（**目前唯一有量的資料**）
 *       GET /admin/analytics                 平台自己的學系／工具用量
 *       GET /admin/jobs                      訓練任務
 *
 * ZH: 🔴 **圖表全部自繪，不引入 chart.js。**
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
    var PCT = { pct: true };

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

    // ── 日期工具 ──────────────────────────────────────────────────────────
    //
    // ZH: 用 Date.UTC 做加減，完全不碰本地時區 —— 這裡處理的是「日曆上的
    //     哪一天」，不是某個時刻。至於「今天是哪一天」交給 TW.date
    //     （釘死 Asia/Taipei），不用 new Date() 的本地日期：開發機剛好
    //     也在 +08:00，用錯了在這裡也量不出來。
    var DAY = 86400000;
    function dnum(s) { var p = String(s).split('-'); return Date.UTC(+p[0], +p[1] - 1, +p[2]); }
    function dstr(n) { return new Date(n).toISOString().slice(0, 10); }

    // ZH: 🔴 期間內的每一天都要有一列，沒有消耗的補 0。
    //     只列出「有消耗」的日期，會讓四根等距長條看起來像連續四天，
    //     中間空了幾天完全看不出來 —— 時間軸不連續就不叫時間軸。
    function fillDays(series) {
        var byDate = {}, start, end;
        (series || []).forEach(function (r) { byDate[r.date] = Number(r.consumed) || 0; });
        if (DAYS > 0) {
            end = dnum(TW.date(new Date()));
            start = end - (DAYS - 1) * DAY;
        } else {
            if (!series || !series.length) return [];
            start = dnum(series[0].date);
            end = dnum(series[series.length - 1].date);
        }
        // ZH: 資料有可能落在期間之外（廠商的 occurred_at 是**當地時間**，
        //     不是 UTC），寧可把軸撐開也不要把資料丟掉。
        (series || []).forEach(function (r) {
            var n = dnum(r.date);
            if (n < start) start = n;
            if (n > end) end = n;
        });
        var out = [];
        for (var n = start; n <= end; n += DAY) {
            out.push({ date: dstr(n), consumed: byDate[dstr(n)] || 0 });
        }
        return out;
    }

    // ── 折線圖（時間序列專用）─────────────────────────────────────────────
    //
    // ZH: 時間有先後順序，要由左到右讀。橫條的上下排列會被讀成**排名** ——
    //     那是另一種意思，用在這裡是錯的。
    //
    // ZH: 這裡用 <svg> 畫線（長條可以用 div 的寬度，折線不行），但**文字一律
    //     留在 HTML** —— SVG 裡的文字不會跟著字級設定縮放，也不能被選取。
    //     一樣不引入任何函式庫。
    //
    // ZH: viewBox 固定 100×100 配 preserveAspectRatio="none"，讓圖形跟著容器
    //     拉伸；線寬會一起被拉扁，所以加 vector-effect="non-scaling-stroke"。
    function line(rows, unit) {
        if (!rows.length) return '';
        var max = rows.reduce(function (m, r) { return Math.max(m, r.consumed); }, 0);
        // ZH: 整段期間都是 0 就不畫 —— 一條貼著底的直線沒有告訴讀者任何事，
        //     而上面那句「沒有任何點數消耗」已經講完了。
        if (!max) return '';

        var n = rows.length;
        var xOf = function (i) { return n === 1 ? 50 : (i / (n - 1) * 100); };
        var yOf = function (i) { return 100 - rows[i].consumed / max * 100; };

        var d = [], i;
        for (i = 0; i < n; i++) {
            d.push((i ? 'L' : 'M') + xOf(i).toFixed(3) + ',' + yOf(i).toFixed(3));
        }
        var path = d.join(' ');
        var area = path + ' L' + xOf(n - 1).toFixed(3) + ',100 L' + xOf(0).toFixed(3) + ',100 Z';

        // ZH: 每個資料點一塊透明的感應區，滑鼠停著看確切數字。位置對齊折線的
        //     節點（i/(n-1)），不是等分格子的中心 —— 差半格，圓點就會浮在線外。
        var w = n > 1 ? 100 / (n - 1) : 100;
        var hits = rows.map(function (r, k) {
            return '<span class="adm-line__hit" style="left:' + xOf(k).toFixed(3) + '%;'
                + 'width:' + w.toFixed(3) + '%;--y:' + (100 - yOf(k)).toFixed(3) + '%"'
                + ' title="' + esc(r.date + ' · ' + num(r.consumed) + ' ' + unit) + '"></span>';
        }).join('');

        // ZH: 點多的時候不畫圓點，會糊成一條粗線。
        var dots = n <= 31 ? ' adm-line--dots' : '';
        return '<div class="adm-line">'
            + '<div class="adm-line__max">' + esc(num(max) + ' ' + unit) + '</div>'
            + '<div class="adm-line__plot' + dots + '">'
            + '<svg viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true" focusable="false">'
            + '<path class="adm-line__area" d="' + area + '"/>'
            + '<path class="adm-line__path" d="' + path + '" vector-effect="non-scaling-stroke"/>'
            + '</svg>'
            + hits
            + '</div>'
            + '<div class="adm-line__ends"><span>' + esc(rows[0].date) + '</span>'
            + '<span>' + esc(rows[n - 1].date) + '</span></div>'
            + '</div>';
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
    //
    // ZH: opts.pct —— 在數值後面補上佔比。**只有「完整切分」的圖能開**
    //     （依類別／依供應者／依身分／依學系：每一筆都屬於其中一類，加起來
     //     就是全部）。像「消耗最多的帳號」那種 top-N 不能開 —— 清單被截掉了，
    //     百分比會讓人以為那就是全部。
    function bars(rows, labelKey, valueKey, unit, opts) {
        if (!rows || !rows.length) return '';
        var max = rows.reduce(function (m, r) { return Math.max(m, Number(r[valueKey]) || 0); }, 0) || 1;
        var total = (opts && opts.pct)
            ? rows.reduce(function (s, r) { return s + (Number(r[valueKey]) || 0); }, 0) : 0;
        return '<div class="adm-bars">' + rows.map(function (r) {
            var v = Number(r[valueKey]) || 0;
            var label = r.__label != null ? r.__label : r[labelKey];
            // ZH: 四捨五入到整數，但非零的小數不寫成 0% —— 那看起來像沒有用。
            var pct = '';
            if (total) {
                var p = v / total * 100;
                pct = ' · ' + (v && p < 0.5 ? T('an_lt1', '<1%') : Math.round(p) + '%');
            }
            return '<div class="adm-bar">'
                + '<span class="adm-bar__label"' + (r.__title ? ' title="' + esc(r.__title) + '"' : '') + '>'
                + esc(label || '—') + '</span>'
                + '<span class="adm-bar__track">'
                + '<i style="width:' + (v / max * 100) + '%"></i></span>'
                + '<span class="adm-bar__val">' + esc(num(v)) + (unit ? ' ' + esc(unit) : '')
                + '<span class="adm-bar__pct">' + esc(pct) + '</span></span>'
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
        var trend = fillDays(d.series);
        // ZH: 用量 Top 10 —— 後端的 models 是按點數排的，這裡要看的是
        //     **呼叫次數**（左邊那欄已經在講點數了），所以重新排一次。
        //     便宜的模型被叫一百次、貴的被叫兩次，是兩件不同的事。
        var models = (d.models || []).slice()
            .sort(function (a, b) { return (b.count || 0) - (a.count || 0); })
            .slice(0, 10);
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

            // ZH: 兩個分支各自把 key 寫全 —— 寫成 `block(x ? 'a' : 'b', ...)`
            //     的話 check_i18n 看不到它們被用過，會回報成「忘了刪」。
            + block('an_trend', '每日消耗', line(trend, pts))
            // ZH: 左右並排 —— 「誰在用」與「用了什麼」是同一個問題的兩面，
            //     擺在一起才看得出「消耗集中在某人」是不是「集中在某個貴模型」。
            + '<div class="adm-duo">'
            + block('an_top', '消耗 Top 10 帳號', bars(top, 'name', 'consumed', pts))
            + block('an_models', '用量 Top 10 模型',
                    bars(models, 'display_name', 'count', T('an_times', '次')))
            + '</div>'
            + '<div class="adm-cols">'
            + block('an_by_category', '依類別', bars(d.by_category, 'category', 'consumed', pts, PCT))
            + block('an_by_provider', '依供應者', bars(d.by_provider, 'provider', 'consumed', pts, PCT))
            + block('an_by_role', '依身分', bars(byRole, 'role', 'consumed', pts, PCT))
            + block('an_by_dept', '依學系', bars(d.by_department, 'department', 'consumed', pts, PCT))
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
