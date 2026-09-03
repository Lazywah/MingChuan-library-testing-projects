/* ==========================================================================
 * analytics.js — 數據（要交報告時才看）
 *
 * ZH: 兩個來源：
 *       GET /external-ai/admin/consumption   MYAI 點數（**目前唯一有量的資料**）
 *       POST /external-ai/admin/sync-transactions  向廠商重新抓交易日誌
 *       GET /admin/analytics                 平台自己的學系／工具用量
 *       GET /admin/jobs                      訓練任務
 *
 * ZH: 🔴 **圖表全部自繪，不引入 chart.js。**
 *     舊版把 chart.js 的預設樣式直接放進去（灰底、預設藍綠、預設圖例），
 *     與頁面完全沒有整合；而且它是外部 CDN —— 圖書館對外連線受限或 CDN 掛掉時，
 *     這一頁會整片壞掉。
 *
 * ZH: 圓餅只用在**完整切分**的四塊（依類別／依供應者／依身分／依學系）——
 *     那裡「加起來是全部」正是要傳達的事。趨勢與排名仍然是折線與橫條：
 *     圓餅比不出接近的大小，也排不出名次。
 *
 * ZH: ⚠ 舊版那張「帳號狀態分佈」是一整片單色的圓（只有一個分類），完全不傳達
 *     資訊。所以只剩一類時這裡直接不畫圓，改印一句話。
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

    // ZH: 起訖日期。两個都空 = 沒在用，走上面的 DAYS。
    // ZH: 🔴 日期直接送字串，**不在前端換算成天數** ——
    //     廠商的 occurred_at 是當地時間，換算一定會在月初月末差一天，
    //     而那種差异在畫面上看不出來（只會覺得數字好像不太對）。
    var RANGE = { start: '', end: '' };

    /* ZH: 組織名稱的中英挑選（v3.9，擁有者裁定 2026-08-30）。
     *
     * ZH: 規則：**英文介面且有英文名才用英文，否則一律中文。**
     *     與公告的 pickLang、models 的 name_en 同一條規則。
     * ZH: 🔴 判斷用 truthy 不是 `!= null` —— 空字串也算沒有。
     *     後端已經把空的正規化成 None，但前端不假設後端一定做對：
     *     漏掉的話畫面上會出現**空白的學系欄**，而且不會有錯誤。
     * ZH: ⚠ 行政單位**沒有**英文名可挑（後端刻意不送 unit_en，只有 53/97）——
     *     那一欄一律中文，不是漏做。
     */
    function orgName(zh, en) {
        var isEn = (window.Prefs && window.Prefs.get().ui_lang) === 'en';
        return (isEn && en) || zh || '';
    }

    function rangeOn() { return !!(RANGE.start || RANGE.end); }

    // ZH: 「用量」有兩種量法，看的是不同的事：
    //       次數 = 被叫了幾次（便宜的模型可能次數很高）
    //       點數 = 花掉多少廠商計費單位（貴的模型叫兩次就很可觀）
    //     ⚠ 這裡沒有「Token」——廠商的交易日誌只回報點數，沒有 token 欄位。
    //       把點數叫成 Token 會跟本頁開頭那句註記自相矛盾。
    var METRICS = [['count', 'an_m_count', '次數', 'an_times', '次'],
                   ['points', 'an_m_points', '點數', 'an_points', '點']];
    var METRIC = 'count';
    // ZH: 切換指標時不重打 API —— 同一份資料換個欄位看而已。
    var LAST = null;

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

    // ZH: 這個檔案原本只讀不寫，所以只有 get()。
    async function post(path) {
        var r = await fetch(API + path, {
            method: 'POST',
            headers: { Authorization: 'Bearer ' + token() },
        });
        if (r.status === 401) { location.replace('login.html'); throw new Error('401'); }
        var body = await r.json().catch(function () { return {}; });
        if (!r.ok) throw new Error(detailText(body) || ('HTTP ' + r.status));
        return body;
    }

    // ZH: 後端的錯誤訊息是「ZH: … | EN: …」的雙語格式，只挑當前語言那半。
    function detailText(body) {
        var d = body && body.detail;
        if (!d) return '';
        if (typeof d !== 'string') return String(d);
        var parts = d.split(' | ');
        var lang = (window.Prefs && Prefs.get().ui_lang) || 'zh';
        var want = parts.filter(function (p) {
            return p.indexOf(lang === 'en' ? 'EN:' : 'ZH:') === 0;
        })[0];
        return (want || parts[0] || '').replace(/^(ZH|EN):\s*/, '');
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
        if (rangeOn()) {
            // ZH: 🔴 用起訖日期當軸的範圍。**不能沿用下面的 DAYS 分支** ——
            //     DAYS 還停在上一次選的快選值（預設 30），於是軸會畫到「今天」，
            //     選了 7 月卻看到一條拖到 8 月底的線。數字是對的、圖是錯的，
            //     而且不會報錯（實測：選 7/1–7/31，軸是 7/02–8/27）。
            // ZH: 只給一邊時，另一邊退回資料本身的邊界。
            var first = (series && series.length) ? dnum(series[0].date) : null;
            var last = (series && series.length) ? dnum(series[series.length - 1].date) : null;
            start = RANGE.start ? dnum(RANGE.start) : first;
            end = RANGE.end ? dnum(RANGE.end) : last;
            if (start == null || end == null) return [];
        } else if (DAYS > 0) {
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

        // ZH: 每個資料點一塊透明的感應區。位置對齊折線的節點（i/(n-1)），
        //     不是等分格子的中心 —— 差半格，圓點就會浮在線外。
        //
        // ZH: 資料放在 data-*，提示框由 wireLine() 用 textContent 組 ——
        //     不走 innerHTML，帳號名稱之類的內容就不必擔心跳脫。
        var sum = rows.reduce(function (a, r) { return a + r.consumed; }, 0);
        var w = n > 1 ? 100 / (n - 1) : 100;
        var hits = rows.map(function (r, k) {
            var share = sum ? Math.round(r.consumed / sum * 100) : 0;
            return '<span class="adm-line__hit" style="left:' + xOf(k).toFixed(3) + '%;'
                + 'width:' + w.toFixed(3) + '%;--y:' + (100 - yOf(k)).toFixed(3) + '%"'
                + ' data-date="' + esc(r.date) + '"'
                + ' data-val="' + esc(num(r.consumed) + ' ' + unit) + '"'
                + ' data-share="' + esc(T('an_tip_share', '佔期間 {p}%').replace('{p}', share)) + '"'
                + '></span>';
        }).join('');

        // ZH: 點多的時候不畫圓點，會糊成一條粗線。
        var dots = n <= 31 ? ' adm-line--dots' : '';
        // ZH: 整張圖一個 tabindex，用左右鍵在點之間移動 —— 90 個點各自可聚焦的話，
        //     用鍵盤的人要按 90 次 Tab 才過得去。
        var label = T('an_chart_a11y', '每日消耗折線圖，{a} 到 {b}')
            .replace('{a}', rows[0].date).replace('{b}', rows[n - 1].date);
        return '<div class="adm-line">'
            + '<div class="adm-line__max">' + esc(num(max) + ' ' + unit) + '</div>'
            + '<div class="adm-line__plot' + dots + '" tabindex="0" role="img"'
            + ' aria-label="' + esc(label) + '">'
            + '<svg viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true" focusable="false">'
            + '<path class="adm-line__area" d="' + area + '"/>'
            + '<path class="adm-line__path" d="' + path + '" vector-effect="non-scaling-stroke"/>'
            + '</svg>'
            + hits
            + '<div class="adm-tip" hidden></div>'
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
    // ZH: 這裡**不放佔比**。橫條圖只用在 top-N（消耗 Top 10、用量 Top 10），
    //     那是截斷過的清單 —— 加百分比會讓人以為那就是全部。
    //     真正「加起來是全部」的四塊改用圓餅，佔比寫在圖例裡。
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
                + '<span class="adm-bar__val">' + esc(num(v)) + (unit ? ' ' + esc(unit) : '')
                + '</span>'
                + '</div>';
        }).join('') + '</div>';
    }

    // ZH: 提示框的內容 —— 折線與圓餅共用。用 textContent 一個一個塞，
    //     不走 innerHTML，帳號名稱之類的內容就不必擔心跳脫。
    function fillTip(tip, parts) {
        tip.textContent = '';
        [['b', parts[0]], ['span', parts[1]], ['i', parts[2]]].forEach(function (p) {
            if (p[1] == null || p[1] === '') return;
            var el = document.createElement(p[0]);
            el.textContent = p[1];
            tip.appendChild(el);
        });
    }

    // ZH: 把提示框夾在容器內 —— 貼邊時會被切掉。
    function placeTip(tip, box, x, y) {
        var tw = tip.offsetWidth, th = tip.offsetHeight;
        tip.style.left = Math.max(tw / 2, Math.min(box.clientWidth - tw / 2, x)) + 'px';
        // ZH: 預設放在上方；頂出去就翻到下方。
        var top = y - th - 10;
        tip.style.top = (top < 0 ? y + 10 : top) + 'px';
    }

    // ZH: 折線圖的互動 —— 滑鼠移過或鍵盤聚焦時，在該點旁邊顯示日期與數值。
    function wireLine(root) {
        var plot = root.querySelector('.adm-line__plot');
        if (!plot) return;
        var hits = [].slice.call(plot.querySelectorAll('.adm-line__hit'));
        var tip = plot.querySelector('.adm-tip');
        var at = -1;

        function show(i) {
            if (i < 0 || i >= hits.length) return;
            at = i;
            hits.forEach(function (h, k) { h.classList.toggle('is-active', k === i); });
            var h = hits[i];
            fillTip(tip, [h.dataset.date, h.dataset.val, h.dataset.share]);
            // ZH: 先取消 hidden 才量得到尺寸 —— 隱藏的元素量出來是 0。
            tip.hidden = false;
            var ph = plot.clientHeight;
            var x = parseFloat(h.style.left) / 100 * plot.clientWidth;
            var yPx = parseFloat(h.style.getPropertyValue('--y')) / 100 * ph;
            placeTip(tip, plot, x, ph - yPx);
        }

        function hide() {
            tip.hidden = true;
            hits.forEach(function (h) { h.classList.remove('is-active'); });
        }

        hits.forEach(function (h, i) {
            h.addEventListener('mouseenter', function () { show(i); });
        });
        plot.addEventListener('mouseleave', hide);
        plot.addEventListener('focus', function () { show(at < 0 ? 0 : at); });
        plot.addEventListener('blur', hide);
        plot.addEventListener('keydown', function (e) {
            if (e.key === 'Escape') { hide(); return; }
            var d = e.key === 'ArrowRight' ? 1 : e.key === 'ArrowLeft' ? -1 : 0;
            if (!d) return;
            e.preventDefault();
            show(Math.max(0, Math.min(hits.length - 1, (at < 0 ? 0 : at) + d)));
        });
    }

    // ── 圓餅圖（完整切分專用）─────────────────────────────────────────────
    //
    // ZH: 只用在「每一筆都屬於其中一類、加起來就是全部」的資料。
    //     排名用橫條、趨勢用折線 —— 圓餅比不出接近的大小，也排不出名次。
    //
    // ZH: 顏色用**同一個資料色的深淺**，不引入一組新色相：兩個主題（黃／藍）
    //     與深淺色都自動跟著走。相鄰的深淺可能接近，所以每片之間再描一道
    //     底色的邊 —— 不靠顏色也分得出片與片的界線。
    function pie(rows, labelKey, valueKey, unit) {
        if (!rows || !rows.length) return '';
        var data = rows.filter(function (r) { return (Number(r[valueKey]) || 0) > 0; });
        if (!data.length) return '';
        var total = data.reduce(function (a, r) { return a + Number(r[valueKey]); }, 0);

        // ZH: 只有一類時整個圓是單一顏色，那就是舊版那張什麼都沒說的圖。
        //     直接寫一句話，比畫一個沒有資訊的圓誠實。
        if (data.length === 1) {
            var only = data[0].__label != null ? data[0].__label : data[0][labelKey];
            return '<p class="footnote">'
                + esc(T('an_pie_one', '這段期間全部集中在「{n}」（{v}）。')
                    .replace('{n}', only)
                    // ZH: 用這一類自己的值，不用 total —— 只有一類時兩者相等，
                    //     但寫成 total 的話，日後這個分支若放寬就會對不起來。
                    .replace('{v}', num(Number(data[0][valueKey])) + ' ' + unit))
                + '</p>';
        }

        // ZH: 從 12 點鐘開始順時針 —— 一般人讀圓餅就是從那裡開始。
        function xy(turn) {
            var t = (turn - 0.25) * 2 * Math.PI;
            return Math.cos(t).toFixed(5) + ' ' + Math.sin(t).toFixed(5);
        }
        var acc = 0;
        var slices = data.map(function (r, i) {
            var v = Number(r[valueKey]);
            var a0 = acc; acc += v / total; var a1 = acc;
            var share = Math.round(v / total * 100);
            return {
                d: 'M 0 0 L ' + xy(a0) + ' A 1 1 0 ' + ((a1 - a0) > 0.5 ? 1 : 0)
                    + ' 1 ' + xy(a1) + ' Z',
                // ZH: 由深到淺，最淺留 0.32 —— 再淡就跟底色分不開了。
                op: (1 - i * (0.68 / (data.length - 1))).toFixed(3),
                label: r.__label != null ? r.__label : r[labelKey],
                val: num(v) + ' ' + unit,
                share: share + '%',
                mid: (a0 + a1) / 2,
            };
        });

        var paths = slices.map(function (sl, i) {
            return '<path class="adm-pie__slice" data-i="' + i + '" d="' + sl.d + '"'
                + ' fill-opacity="' + sl.op + '"></path>';
        }).join('');

        var legend = slices.map(function (sl, i) {
            return '<li class="adm-pie__row" data-i="' + i + '">'
                + '<span class="adm-pie__key" style="opacity:' + sl.op + '"></span>'
                + '<span class="adm-pie__name">' + esc(sl.label || '—') + '</span>'
                + '<span class="adm-pie__val">' + esc(sl.val) + '</span>'
                + '<span class="adm-pie__pct">' + esc(sl.share) + '</span>'
                + '</li>';
        }).join('');

        // ZH: 每片的提示框位置：中線方向、半徑 0.62 處（片內，不會蓋到邊）。
        var pos = slices.map(function (sl) {
            var t = (sl.mid - 0.25) * 2 * Math.PI;
            return [(50 + Math.cos(t) * 31).toFixed(2), (50 + Math.sin(t) * 31).toFixed(2)];
        });
        var tips = slices.map(function (sl, i) {
            return '<span class="adm-pie__anchor" data-i="' + i + '"'
                + ' style="left:' + pos[i][0] + '%;top:' + pos[i][1] + '%"'
                + ' data-label="' + esc(sl.label || '—') + '"'
                + ' data-val="' + esc(sl.val) + '"'
                + ' data-share="' + esc(sl.share) + '"></span>';
        }).join('');

        return '<div class="adm-pie">'
            + '<div class="adm-pie__wrap" tabindex="0" role="img"'
            + ' aria-label="' + esc(T('an_pie_a11y', '圓餅圖，共 {n} 類')
                .replace('{n}', data.length)) + '">'
            + '<svg viewBox="-1.05 -1.05 2.1 2.1" aria-hidden="true" focusable="false">'
            + paths + '</svg>'
            + tips
            + '<div class="adm-tip" hidden></div>'
            + '</div>'
            + '<ul class="adm-pie__legend">' + legend + '</ul>'
            + '</div>';
    }

    // ZH: 圓餅的互動 —— 跟折線圖一樣：滑鼠移過或鍵盤聚焦顯示提示框，
    //     左右鍵在片之間移動。圖例那一列也連動，指到哪一列就亮哪一片。
    function wirePie(root) {
        [].slice.call(root.querySelectorAll('.adm-pie')).forEach(function (box) {
            var wrap = box.querySelector('.adm-pie__wrap');
            var tip = box.querySelector('.adm-tip');
            var anchors = [].slice.call(box.querySelectorAll('.adm-pie__anchor'));
            var slices = [].slice.call(box.querySelectorAll('.adm-pie__slice'));
            var rowsEl = [].slice.call(box.querySelectorAll('.adm-pie__row'));
            var at = -1;

            function show(i) {
                if (i < 0 || i >= anchors.length) return;
                at = i;
                slices.forEach(function (p, k) { p.classList.toggle('is-active', k === i); });
                rowsEl.forEach(function (r, k) { r.classList.toggle('is-active', k === i); });
                var a = anchors[i];
                fillTip(tip, [a.dataset.label, a.dataset.val, a.dataset.share]);
                tip.hidden = false;
                placeTip(tip, wrap,
                    parseFloat(a.style.left) / 100 * wrap.clientWidth,
                    parseFloat(a.style.top) / 100 * wrap.clientHeight);
            }

            function hide() {
                tip.hidden = true;
                slices.forEach(function (p) { p.classList.remove('is-active'); });
                rowsEl.forEach(function (r) { r.classList.remove('is-active'); });
            }

            slices.forEach(function (p, i) {
                p.addEventListener('mouseenter', function () { show(i); });
            });
            rowsEl.forEach(function (r, i) {
                r.addEventListener('mouseenter', function () { show(i); });
                r.addEventListener('mouseleave', hide);
            });
            wrap.addEventListener('mouseleave', hide);
            wrap.addEventListener('focus', function () { show(at < 0 ? 0 : at); });
            wrap.addEventListener('blur', hide);
            wrap.addEventListener('keydown', function (e) {
                if (e.key === 'Escape') { hide(); return; }
                var d = e.key === 'ArrowRight' ? 1 : e.key === 'ArrowLeft' ? -1 : 0;
                if (!d) return;
                e.preventDefault();
                show(((at < 0 ? 0 : at) + d + anchors.length) % anchors.length);
            });
        });
    }

    // ── 向廠商重新同步 ────────────────────────────────────────────────────
    //
    // ZH: 🔴 這一步是**headless 登入廠商網站再匯出**，慢，而且慢得沒有徵兆。
    //     所以按下去要立刻把按鈕停用並改字 —— 不然使用者會以為沒反應而一直按，
    //     每按一次就多開一個 session。
    //
    // ZH: 成功用 flash（看完就沒用了），失敗用 say（留著讓人看清楚）。
    var SYNCING = false;

    async function syncNow() {
        if (SYNCING) return;
        SYNCING = true;
        var btn = $('sync');
        var was = btn.textContent;
        btn.disabled = true;
        btn.textContent = T('an_syncing', '同步中…');
        say('sync-msg', '');
        try {
            var r = await post('/external-ai/admin/sync-transactions');
            // ZH: 三個數字分開講：抓到幾筆、其中幾筆是新的、幾筆被重新分類。
            //     只說「同步完成」的話，沒有人知道到底有沒有拿到東西。
            flash('sync-msg', T('an_synced', '抓到 {f} 筆，新增 {c} 筆，重新分類 {r} 筆。')
                .replace('{f}', num(r.fetched)).replace('{c}', num(r.created))
                .replace('{r}', num(r.reclassified)));
            await load();
        } catch (e) {
            say('sync-msg', T('an_sync_fail', '同步失敗（{w}）').replace('{w}', e.message));
        } finally {
            SYNCING = false;
            btn.disabled = false;
            btn.textContent = was;
        }
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

    // ZH: 只給成功訊息用的短暫提示。錯誤訊息不要用它 ——
    //     還沒解決的事情需要留在畫面上。
    var _t = null;
    function flash(id, text) {
        say(id, text);
        // ZH: 成功訊息不要用紅底 —— say() 剛把它設成錯誤樣式，這裡換掉。
        var okEl = $(id);
        if (okEl) {
            okEl.classList.remove('inline-error');
            okEl.classList.add('inline-note');
        }
        clearTimeout(_t);
        _t = setTimeout(function () {
            var el = $(id);
            if (el && el.textContent === text) say(id, '');
        }, 6000);
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
        LAST = d;

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
        var mHtml = modelBars(d);
        var byRole = (d.by_role || []).map(function (r) {
            return Object.assign({}, r, {
                __label: r.role === 'unbound' ? T('an_unbound', '未綁定') : T('role_' + r.role, r.role),
            });
        });

        $('myai').innerHTML =
            // ZH: v3.9 資料來源那句搬進標題旁的 icon（見 analytics.html）。
            //     它回答的是「這些數字哪來的」—— 看一次就夠，不必每次進來都讀。
            '<div class="adm-stats">'
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
            // ZH: #an-models 是切換時唯一被替換的部分，外層留著滑塊才動得起來。
            + block('an_models', '用量 Top 10 模型',
                    mHtml && '<div id="an-models">' + mHtml + '</div>',
                    metricToggle())
            + '</div>'
            + '<div class="adm-cols">'
            + block('an_by_category', '依類別', pie(d.by_category, 'category', 'consumed', pts))
            + block('an_by_provider', '依供應者', pie(d.by_provider, 'provider', 'consumed', pts))
            + block('an_by_role', '依身分', pie(byRole, 'role', 'consumed', pts))
            // ZH: v3.8 #13 —— 學系／學院／單位共用一張圖 + 滑條。
            //     學院由後端查對照表推導,前端不自己推（自己推的話對照表改了這裡還是舊的）。
            //     行政單位只有職員有值,所以學生會全落在「未設定」—— 那是正確的。
            + block('an_by_org', '依組織', '<div id="an-org">' + orgPie(d) + '</div>',
                    orgToggle())
            + '</div>';

        wireLine($('myai'));
        wireMetric($('myai'));
        wireOrg($('myai'));
        wirePie($('myai'));
    }

    function block(key, zh, inner, actions) {
        if (!inner) return '';
        return '<section class="adm-block">'
            + '<div class="adm-block__head">'
            + '<h3 class="adm-block__title">' + esc(T(key, zh)) + '</h3>'
            + (actions || '')
            + '</div>' + inner + '</section>';
    }

    // ZH: 指標切換 —— 左右滑動的分段控制。
    //
    // ZH: 這是「同一份資料換個看法」，不是「兩個獨立的動作」，所以用
    //     radiogroup 而不是兩顆各自獨立的按鈕：讀螢幕的人會聽到
    //     「二選一，目前選的是次數」，而不是兩個來歷不明的按鈕。
    //
    // ZH: 滑塊位置直接寫 inline transform。JS 本來就知道選到第幾格，
    //     再繞一層 CSS 變數（`translateX(calc(var(--i) * 100%))`）只是多一層
    //     間接，好處有限。
    //
    // ⚠ ZH: 驗這個轉場時，**隱藏分頁的動畫時間軸是凍結的**——
    //     `getComputedStyle` 會一直讀到起始值，看起來像「滑塊壞了不會動」，
    //     但 `document.visibilityState === 'hidden'` 才是原因。
    //     要量就用 `el.getAnimations()[0].finish()` 讓它跳到終點再量。
    // ZH: v3.8 #13 —— 學系／學院／單位是**同一批人的三種切法**,
    //     並排成三張圓餅會讓人以為是三組不同的資料。改成一張圖 + 滑條。
    //     三份資料後端一次都給了,切換不必重打 API。
    // ZH: 滑條的選項不加「依」—— 區塊標題已經是「依組織」,
    //     選項再寫「依學系」會變成「依組織：依學系」。
    var ORGS = [['department', 'an_by_dept', '學系'],
                ['college', 'an_by_college', '學院'],
                ['unit', 'an_by_unit', '單位'],
                ['campus', 'an_by_campus', '校區']];
    var ORG = 'department';

    function orgKey() { return ORG; }

    function orgPie(d) {
        if (!d) return '';
        var map = { department: [d.by_department, 'department'],
                    college: [d.by_college, 'college'],
                    unit: [d.by_unit, 'unit'],
                    campus: [d.by_campus, 'campus'] }[ORG];
        // ZH: `pts` 是 renderMyai 裡的區域變數（單位文字「點」）,這裡拿不到 ——
        //     自己取一次。第一版寫成 pts(d),那會在切換時直接炸,
        //     而語法檢查抓不到（它是執行期錯誤）。
        return pie(map[0], map[1], 'consumed', T('an_points', '點'));
    }

    function orgToggle() {
        var at = 0;
        ORGS.forEach(function (o, i) { if (o[0] === ORG) at = i; });
        // ZH: `--seg-n` 告訴 CSS 這個滑條有幾格 —— 滑塊寬度由它算。
        //     不設的話會沿用預設的 2,滑塊過寬而且切到第三格會衝出邊界。
        return '<div class="adm-seg" role="radiogroup" style="--seg-n:' + ORGS.length + '"'
            + ' aria-label="' + esc(T('an_org_group', '要依哪一種組織分群')) + '">'
            + '<span class="adm-seg__thumb" aria-hidden="true"'
            + ' style="transform:translateX(' + (at * 100) + '%)"></span>'
            + ORGS.map(function (o) {
                var on = ORG === o[0];
                return '<button type="button" class="adm-seg__opt' + (on ? ' is-current' : '') + '"'
                    + ' role="radio" aria-checked="' + (on ? 'true' : 'false') + '"'
                    + ' tabindex="' + (on ? '0' : '-1') + '" data-org="' + o[0] + '">'
                    + esc(T(o[1], o[2])) + '</button>';
            }).join('')
            + '</div>';
    }

    function wireOrg(root) {
        var first = root.querySelector('[data-org]');
        var seg = first && first.closest('.adm-seg');
        if (!seg) return;
        var thumb = seg.querySelector('.adm-seg__thumb');
        var opts = [].slice.call(seg.querySelectorAll('[data-org]'));

        function pick(i, focus) {
            if (i < 0 || i >= opts.length || opts[i].dataset.org === ORG) return;
            ORG = opts[i].dataset.org;
            thumb.style.transform = 'translateX(' + (i * 100) + '%)';
            opts.forEach(function (o, k) {
                var on = k === i;
                o.classList.toggle('is-current', on);
                o.setAttribute('aria-checked', on ? 'true' : 'false');
                o.setAttribute('tabindex', on ? '0' : '-1');
            });
            if (focus) opts[i].focus();
            // ZH: 只換那張圖 —— 整個 renderMyai 重畫會把指標滑條也重設回預設。
            var host = root.querySelector('#an-org');
            if (host) {
                host.innerHTML = orgPie(LAST);
                wirePie(host);      // ZH: 重畫過的圖要重新接互動,不然滑過去沒反應
            }
        }

        opts.forEach(function (o, i) {
            o.addEventListener('click', function () { pick(i, false); });
        });
        seg.addEventListener('keydown', function (e) {
            var d = e.key === 'ArrowRight' ? 1 : e.key === 'ArrowLeft' ? -1 : 0;
            if (!d) return;
            e.preventDefault();
            var cur = 0;
            opts.forEach(function (o, k) { if (o.dataset.org === ORG) cur = k; });
            pick((cur + d + opts.length) % opts.length, true);
        });
    }

    function metricToggle() {
        var at = 0;
        METRICS.forEach(function (m, i) { if (m[0] === METRIC) at = i; });
        return '<div class="adm-seg" role="radiogroup"'
            + ' aria-label="' + esc(T('an_metric_group', '用量的計算方式')) + '">'
            + '<span class="adm-seg__thumb" aria-hidden="true"'
            + ' style="transform:translateX(' + (at * 100) + '%)"></span>'
            + METRICS.map(function (m) {
                var on = METRIC === m[0];
                return '<button type="button" class="adm-seg__opt' + (on ? ' is-current' : '') + '"'
                    + ' role="radio" aria-checked="' + (on ? 'true' : 'false') + '"'
                    + ' tabindex="' + (on ? '0' : '-1') + '" data-metric="' + m[0] + '">'
                    + esc(T(m[1], m[2])) + '</button>';
            }).join('')
            + '</div>';
    }

    // ZH: 依當前指標排出 Top 10。後端的 models 固定按點數排，所以要重排 ——
    //     否則切到「次數」時，拿到的仍是「點數前十名」再按次數排，
    //     次數高但點數低的模型會整個看不到。
    function modelBars(d) {
        var m = METRICS.filter(function (x) { return x[0] === METRIC; })[0] || METRICS[0];
        var rows = (d.models || []).slice()
            .sort(function (a, b) { return (b[m[0]] || 0) - (a[m[0]] || 0); })
            .slice(0, 10);
        return bars(rows, 'display_name', m[0], T(m[3], m[4]));
    }

    // ZH: 🔴 切換時**只換長條，不重繪整塊** —— 重繪會把滑塊也換成新的元素，
    //     新元素從一開始就在新位置，CSS transition 沒有起點可以動，
    //     於是「滑動」變成瞬移。
    function wireMetric(root) {
        // ZH: 🔴 用 `[data-metric]` 反查它所屬的滑條,不要抓 `.adm-seg` 的第一個 ——
        //     這一頁現在有兩個滑條（指標、組織維度）,抓第一個會接錯。
        var first = root.querySelector('[data-metric]');
        var seg = first && first.closest('.adm-seg');
        if (!seg) return;
        var thumb = seg.querySelector('.adm-seg__thumb');
        var opts = [].slice.call(seg.querySelectorAll('[data-metric]'));

        function pick(i, focus) {
            if (i < 0 || i >= opts.length || opts[i].dataset.metric === METRIC) return;
            METRIC = opts[i].dataset.metric;
            thumb.style.transform = 'translateX(' + (i * 100) + '%)';
            opts.forEach(function (o, k) {
                var on = k === i;
                o.classList.toggle('is-current', on);
                o.setAttribute('aria-checked', on ? 'true' : 'false');
                o.setAttribute('tabindex', on ? '0' : '-1');
            });
            if (focus) opts[i].focus();
            var host = root.querySelector('#an-models');
            if (host) host.innerHTML = modelBars(LAST);
        }

        opts.forEach(function (o, i) {
            o.addEventListener('click', function () { pick(i, false); });
        });
        // ZH: radiogroup 的慣例是左右鍵換選項（群組本身只佔一個 Tab 位）。
        seg.addEventListener('keydown', function (e) {
            var d = e.key === 'ArrowRight' ? 1 : e.key === 'ArrowLeft' ? -1 : 0;
            if (!d) return;
            e.preventDefault();
            var cur = 0;
            opts.forEach(function (o, k) { if (o.dataset.metric === METRIC) cur = k; });
            pick((cur + d + opts.length) % opts.length, true);
        });
    }

    // ── 訓練任務 ──────────────────────────────────────────────────────────
    // ZH: 🔴 2026-08-28：原本只畫 completed / failed / running 三桶，
    //     但後端實際有五個狀態（`pending` 是欄位預設值，`cancelled` 由
    //     `crud.cancel_job` 寫入）。於是唯一一筆已取消的任務讓畫面變成
    //     **「總數 1、其他全 0」** —— 每個數字都對，但看的人無從得知那 1 筆去哪了。
    //
    // ZH: 所以這裡不寫死桶的清單：認得的狀態照下面的順序顯示，
    //     **認不得的狀態以原始名稱自成一桶**。「各桶相加 = 總數」變成由構造保證，
    //     而不是靠我記得在後端新增狀態時回來改這裡。
    // ZH: 形狀是 [i18n key, 中文, 對應的後端狀態]。**成對寫在一起是有原因的** ——
    //     `check_i18n` 認的是「key 後面緊接中文 fallback」這個形狀，
    //     寫成 `{key:…, zh:…}` 它就看不到，會把真的有在用的 key 報成「沒人用」。
    var JOB_BUCKETS = [
        // ZH: `queued` 併進「待執行」—— 它在後端只被讀、沒有任何地方寫入（舊別名）。
        ['an_j_pending',   '待執行', ['pending', 'queued']],
        ['an_j_running',   '執行中', ['running']],
        ['an_j_done',      '已完成', ['completed']],
        ['an_j_failed',    '失敗',   ['failed']],
        ['an_j_cancelled', '已取消', ['cancelled']],
    ];

    function renderJobs(jobs) {
        if (failed(jobs)) { $('jobs').innerHTML = failBox(jobs); return; }
        if (!jobs.length) {
            $('jobs').innerHTML = '<p class="footnote">'
                + esc(T('an_jobs_none', '還沒有任何訓練任務。')) + '</p>';
            return;
        }
        var by = {};
        jobs.forEach(function (j) { by[j.status] = (by[j.status] || 0) + 1; });

        var html = stat('an_j_total', '總數', jobs.length);
        JOB_BUCKETS.forEach(function (b) {
            var n = 0;
            b[2].forEach(function (st) { n += by[st] || 0; delete by[st]; });
            html += stat(b[0], b[1], n);
        });
        // ZH: 沒被上面認領的 —— 直接把後端給的字串當標籤印出來。
        //     醜，但看得見；比安靜地少算一筆好。
        Object.keys(by).sort().forEach(function (st) {
            html += stat('', st, by[st]);
        });
        $('jobs').innerHTML = '<div class="adm-stats">' + html + '</div>';
    }

    // ── 平台使用（依學院／學系／行政單位）─────────────────────────────────
    // ZH: v3.8 #13。分組方式由後端算,前端只送 group_by ——
    //     學院是由學系經對照表推的,前端自己推的話對照表改了這裡還是舊的。
    function groupBy() {
        var el = $('an-group');
        return (el && el.value) || 'department';
    }

    function groupHeadKey() {
        return { college: ['an_dept_college', '學院'],
                 unit:    ['an_dept_unit', '單位'],
                 campus:  ['an_dept_campus', '校區'] }[groupBy()]
            || ['an_dept', '學系'];
    }

    // ZH: 平台統計的網址。期間參數與 MYAI 那支**同一套寫法** ——
    //     兩邊不一致的話，同一個畫面上兩張表會是不同期間的數字，
    //     而畫面上完全看不出來。
    function platformUrl() {
        return '/admin/analytics?group_by=' + encodeURIComponent(groupBy())
            + '&' + (rangeOn()
                ? 'start=' + encodeURIComponent(RANGE.start || '')
                  + '&end=' + encodeURIComponent(RANGE.end || '')
                : 'days=' + DAYS);
    }

    function renderPlatform(a) {
        if (failed(a)) { $('platform').innerHTML = failBox(a); return; }
        var rows = a.group_stats || [];
        if (!rows.length) {
            $('platform').innerHTML = '<p class="footnote">'
                + esc(T('an_platform_none', '還沒有足夠的資料。')) + '</p>';
            return;
        }
        // ZH: 🔴 欄位順序是刻意的：**人數 → 有多少人在用 → 各項用了多少**。
        //     先答「這一組推得開嗎」，再答「用在哪」。
        //     把使用量放前面的話，大系永遠在最上面，而那不是要看的事。
        //
        // ZH: v3.9 加了**兩層表頭**（擁有者裁定 2026-08-30）——
        //     「有用的人」「滲透率」單獨看不出在講什麼。上面那一列
        //     把欄位分成「這一組的人」與「用了多少」兩塊，一眼看得出
        //     哪幾欄是同一件事的不同切面。
        //
        // ZH: 第三個欄位是 tip：難懂的欄位掛一顆資訊 icon（tip.js）。
        //     ⚠ 只掛在**真的會誤解**的欄位上。每一欄都掛的話，
        //     icon 就變成背景，需要它的那幾欄反而不顯眼了。
        var head = [
            [groupHeadKey(), null],
            [['an_users', '人數'], null],
            [['an_active', '有用的人'],
             ['an_tip_active',
              '這段期間內，至少做過一件事的人數：跳去 MYAI、開實驗室、或送出訓練。'
              + '同一個人只算一次。⚠ 這是**下限** —— 跨四張表去重在資料庫端做不到，'
              + '所以取各項的最大值。真實人數只會更多，不會更少。']],
            [['an_adoption', '滲透率'],
             ['an_tip_adoption',
              '「有用的人」÷「這一組在平台上的人數」。用來看**哪一組還沒推開** ——'
              + '與旁邊的佔比不同，它不會因為系大就比較高。'
              + '⚠ 分母是**登入過平台**的人，不是全系人數：完全沒來過的人不在分母裡，'
              + '所以這個數字偏高。']],
            [['an_c_visits', 'MYAI 次數'],
             ['an_tip_visits',
              '從平台按「前往 MYAI」的次數。'
              + '⚠ 這只代表他**走進去了**，不代表真的用了 AI —— 那要看旁邊的點數。'
              + '括號裡是佔全平台的百分比。']],
            [['an_c_points', 'MYAI 點數'],
             ['an_tip_points',
              '這段期間**用掉**的點數。管理員補的點不算在內 ——'
              + '算進去的話，補過點的系會看起來用得特別多，而那正好是用得少才要補的那些。']],
            // ZH: Lab·GPU / Lab·CPU 中英一樣，**不給 key** —— 給了會被
            //     check_i18n 報成「字典有但沒人用」（它的判準是 key 後面
            //     緊接一個含中文的 fallback）。與 Token 那欄同一個處理。
            [['an_c_jobs', '訓練'], null],
            [['', 'Lab·GPU'],
             ['an_tip_lab',
              '開實驗室的次數，依**當次有沒有勾 GPU** 分成兩欄。'
              + '⚠ 這兩欄自 v3.9 才開始記，在那之前的 0 是「還沒開始記」。']],
            [['', 'Lab·CPU'], null],
            [['an_dept_logins', '登入次數'], null],
            [['', 'Token'],
             ['an_tip_token',
              '平台**自己的** Token 額度用量，與 MYAI 點數完全無關 ——'
              + '兩者是不同的東西，不要拿來互相比較。']],
        ];
        // ZH: 分隔線落在「有用的人」與「MYAI 次數」之前 —— 那是兩塊的交界。
        var SEP = { 2: 1, 4: 1 };
        $('platform').innerHTML =
            trackingNote(a)
            + '<div class="adm-tablewrap"><table class="adm-table">'
            + '<thead>'
            + '<tr class="an-grouphead">'
            +   '<th></th>'
            +   '<th colspan="3">' + esc(T('an_g_people', '這一組的人')) + '</th>'
            +   '<th colspan="7" class="an-sep">' + esc(T('an_g_usage', '用了多少')) + '</th>'
            + '</tr>'
            + '<tr>'
            + head.map(function (h, i) {
                var cls = SEP[i] ? ' class="an-sep"' : '';
                return '<th' + cls + '>' + esc(T(h[0][0], h[0][1])) + tipHtml(h[1]) + '</th>';
            }).join('')
            + '</tr></thead><tbody>'
            + rows.map(function (r) {
                return '<tr>'
                    // ZH: 後端對不到對照表時回 null（不是字串）——
                    //     文案在前端決定,才翻得了中英。
                    // ZH: 英文介面且該分類有英文名才用英文（見 orgName）。
                    //     ⚠ 依「行政單位」分組時一律中文 —— 後端刻意不送英文名。
                    + '<td>'
                    + esc(orgName(r.group, r.group_en) || T('an_unclassified', '未分類'))
                    + '</td>'
                    + '<td class="num">' + esc(num(r.user_count)) + '</td>'
                    // ZH: 「有用的人」寫成 45/52 而不是只寫 45 ——
                    //     分母就在旁邊，讀的人不必自己去對上一欄。
                    // ZH: 分隔線在每一列都要畫，只畫表頭的話中間就斷了。
                    + '<td class="num an-sep">' + esc(num(r.active_users_min))
                    +     ' / ' + esc(num(r.user_count)) + '</td>'
                    + '<td class="num">' + esc(pct(r.adoption)) + '</td>'
                    + cell(r.myai_visits, r.share_visits, true)
                    + cell(r.myai_points, r.share_points)
                    + cell(r.jobs, r.share_jobs)
                    // ZH: Lab 的兩欄共用同一個佔比（share_lab 是兩者相加算的）——
                    //     所以只在 GPU 那欄顯示 %，CPU 那欄只給次數。
                    //     兩欄都掛同一個百分比會讓人以為那是各自的佔比。
                    + '<td class="num">' + esc(num(r.lab_gpu)) + '</td>'
                    + '<td class="num">' + esc(num(r.lab_cpu)) + '</td>'
                    + '<td class="num">' + esc(num(r.total_logins)) + '</td>'
                    // ZH: ⚠ Token 是**平台自己的**額度，與 MYAI 點數完全無關。
                    //     這一欄在 v3.9 加新欄位時被我改表頭時弄丟過一次 ——
                    //     欄位對帳（後端送了前端沒用）才抓出來。
                    + '<td class="num">' + esc(num(r.total_tokens)) + '</td>'
                    + '</tr>';
            }).join('')
            + '</tbody></table></div>';
    }

    // ZH: 數字 + 佔比。佔比為 0 時只寫數字 —— 「0（0.0%）」是兩次噪音。
    function cell(n, share, sep) {
        var v = esc(num(n));
        if (share) v += ' <span class="an-share">(' + esc(pct(share)) + ')</span>';
        return '<td class="num' + (sep ? ' an-sep' : '') + '">' + v + '</td>';
    }

    /* ZH: 表頭上的資訊 icon。用共用的 tip.js（行為、樣式都在那邊）。
     * ZH: 泡泡的 id 由 key 推出來 —— 表頭有好幾顆，寫死一個 id 的話
     *     只有第一顆打得開（aria-controls 只會指到第一個相同的 id）。
     * ZH: 傳 null 就不掛 —— 只有真的會誤解的欄位才需要。
     */
    function tipHtml(spec) {
        if (!spec) return '';
        var id = 'tip-' + spec[0];
        return '<span class="tip">'
            + '<button type="button" class="tip__btn" aria-expanded="false"'
            + ' aria-controls="' + esc(id) + '"'
            + ' aria-label="' + esc(T('tip_more', '這是什麼')) + '">i</button>'
            + '<span class="tip__body tip__body--wide" id="' + esc(id) + '"'
            + ' role="tooltip" hidden>' + esc(T(spec[0], spec[1])) + '</span>'
            + '</span>';
    }

    function pct(v) {
        var n = Number(v) || 0;
        return n.toFixed(1) + '%';
    }

    /* ZH: 🔴 「自 X 日起才有資料」的註記。
     *
     * ZH: MYAI 跳轉與 Lab 的 CPU/GPU 之分是 v3.9 才開始記的。選的期間比第一筆
     *     還早時，那幾欄的 0 會被讀成「這個系都沒在用」—— 而其實是
     *     「那時候還沒開始記」。兩者在畫面上長得一模一樣。
     * ZH: 日期由後端從資料本身推（最早一筆），不是寫死的 ——
     *     寫死的話換一台機器部署就錯了。
     */
    function trackingNote(a) {
        var since = (a && a.tracking_since) || {};
        var first = since.myai_visits || since.lab_usage;
        if (!first) return '';
        var d = String(first).slice(0, 10);
        // ZH: 只在「選的期間比它早」時才提醒。期間完全在記錄之後的話，
        //     這句話是多餘的，而多餘的警語會讓人開始略過所有警語。
        var startsBefore = rangeOn()
            ? (RANGE.start && RANGE.start < d)
            : (DAYS === 0 || daysAgo(DAYS) < d);
        if (!startsBefore) return '';
        return '<p class="footnote">'
            + esc(T('an_tracking_since',
                    'MYAI 次數與 Lab 的 GPU／CPU 之分自 {d} 起才有紀錄；'
                    + '在那之前的 0 代表「還沒開始記」，不是「沒有人用」。')
                .replace('{d}', d))
            + '</p>';
    }

    function daysAgo(n) {
        return new Date(Date.now() - n * 86400000).toISOString().slice(0, 10);
    }

    // ── 期間 ──────────────────────────────────────────────────────────────
    function renderPeriods() {
        // ZH: 用起訖日期時，快選一律不反白（見 analytics.html 的說明）。
        var presetOn = !rangeOn();
        $('periods').innerHTML = PERIODS.map(function (p) {
            var on = presetOn && DAYS === p[0];
            return '<button class="btn btn--minor' + (on ? ' is-current' : '') + '"'
                + ' type="button" data-days="' + p[0] + '"'
                + (on ? ' aria-current="true"' : '') + '>'
                + esc(T(p[1], p[2])) + '</button>';
        }).join('');
        $('periods').querySelectorAll('[data-days]').forEach(function (b) {
            b.addEventListener('click', function () {
                DAYS = parseInt(b.dataset.days, 10);
                // ZH: 按了快選就把起訖清掉 —— 否則下一次請求還是帶著日期，
                //     畫面反白的是「近 30 天」而資料是 7 月，而且**不會報錯**。
                RANGE.start = RANGE.end = '';
                $('r-from').value = ''; $('r-to').value = '';
                load();
            });
        });
        $('r-clear').hidden = !rangeOn();
    }

    // ZH: 套用起訖。兩個都空就當作清除。
    function wireRange() {
        $('r-go').addEventListener('click', function () {
            RANGE.start = $('r-from').value;
            RANGE.end = $('r-to').value;
            load();
        });
        $('r-clear').addEventListener('click', function () {
            RANGE.start = RANGE.end = '';
            $('r-from').value = ''; $('r-to').value = '';
            load();
        });
    }

    async function load() {
        renderPeriods();
        var out = await Promise.all([
            safe(get('/external-ai/admin/consumption?'
                + (rangeOn()
                    ? 'start=' + encodeURIComponent(RANGE.start)
                      + '&end=' + encodeURIComponent(RANGE.end)
                    : 'days=' + DAYS))),
            safe(get('/admin/jobs?limit=500')),
            safe(get(platformUrl())),
        ]);
        renderMyai(out[0]);
        renderJobs(out[1]);
        renderPlatform(out[2]);
    }


    // ZH: 切換分組只重打**平台那一支** —— 整頁 load() 會連 MYAI 與訓練任務
    //     一起重打，那兩支跟分組無關，白等而且會讓畫面整個閃一次。
    (function wireGroupSwitch() {
        var el = $('an-group');
        if (!el) return;
        el.addEventListener('change', async function () {
            renderPlatform(await safe(
                get(platformUrl())));
        });
    })();

    // ==================================================================
    // ZH: 匯出。端點要 Authorization 標頭，所以**不能用 <a href> 直接下載**
    //     （那樣帶不上 token，會拿到一個 401 的檔案）。
    //     改成 fetch → blob → 臨時 <a download> —— 與 V0.5 使用者匯出同一個做法。
    // ZH: 檔名優先取 Content-Disposition（後端已經把區間寫進去了）。
    // ==================================================================
    async function exportAs(fmt, btn) {
        var qs = rangeOn()
            ? 'start=' + encodeURIComponent(RANGE.start) + '&end=' + encodeURIComponent(RANGE.end)
            : 'days=' + DAYS;
        var old = btn.textContent;
        btn.disabled = true;
        btn.textContent = T('an_exporting', '匯出中…');
        try {
            var res = await fetch(API + '/external-ai/admin/consumption/export?fmt=' + fmt + '&' + qs,
                                  { headers: { Authorization: 'Bearer ' + token() } });
            if (!res.ok) throw new Error('HTTP ' + res.status);
            var cd = res.headers.get('content-disposition') || '';
            var m = cd.match(/filename="?([^";]+)"?/);
            var name = m ? m[1] : 'consumption.' + fmt;
            var blob = await res.blob();
            var url = URL.createObjectURL(blob);
            var a = document.createElement('a');
            a.href = url; a.download = name;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
        } catch (e) {
            // ZH: 失敗要講 —— 下載沒發生時畫面上完全沒有痕跡，
            //     使用者只會以為自己沒按到。
            alert(T('an_export_fail', '匯出失敗（{w}）').replace('{w}', e.message));
        } finally {
            btn.disabled = false;
            btn.textContent = old;
        }
    }

    $('x-xlsx').addEventListener('click', function () { exportAs('xlsx', $('x-xlsx')); });
    $('x-csv').addEventListener('click', function () { exportAs('csv', $('x-csv')); });

    $('sync').addEventListener('click', syncNow);
    wireRange();

    load();
    document.addEventListener('prefs:langchanged', load);
})();
