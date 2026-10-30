/* ==========================================================================
 * overview.js — 總覽（開機看一眼）
 *
 * ZH: 這一頁要回答的問題只有一個：**現在有沒有需要我處理的事？**
 *     所以最上面是一排數字格、接著是「需要你處理的」，而且**沒事的時候要明確說沒事**——
 *     空白會讓人以為還沒載入完，然後多等、重新整理、再懷疑是不是壞了。
 *
 * ZH: 五個資料來源各自獨立抓、獨立失敗：
 *       GET /admin/gpu-nodes             節點六態 + 撞名 + 執行中
 *       GET /admin/cluster/stats         每張 GPU 的溫度／使用率／記憶體
 *       GET /admin/jobs                  最近的任務
 *       GET /admin/reports/summary       未處理的回報數
 *       GET /external-ai/admin/live-usage 誰在用外部 AI（廠商用量 × 平台在線）
 *     ⚠ **一段讀不到不可以讓整頁空白** —— 那會把「回報服務掛了」
 *       表現成「GPU 也不見了」，人就會去查錯的東西。
 *
 * ZH: 自動更新 10 秒一次，**而且畫面上要寫最後更新時間**。
 *     沒有那個時間戳的話，「資料沒變」與「更新卡住了」長得一模一樣。
 *
 * ZH: v4.45 版面整理（DEMO）：
 *       · 數字格（HTML 寫好結構，這裡只改數字）
 *       · GPU 卡片 + 節點表 → 一台機器一張卡
 *       · 外部 AI 四格 → 「有用量 × 不在平台」攤開並升成一列提醒，其他三格只給人數、名單點開才看
 *       · 最近任務的狀態翻成中文
 *     🔴 每 10 秒重畫時**不能把使用者點開的名單收回去**、也不能把鍵盤焦點洗掉 ——
 *       見 paint()。
 * ========================================================================== */
(function () {
    'use strict';

    var API = '/api/v1';
    var REFRESH_MS = 10000;
    var WAITING_MIN = 15;          // ZH: 排隊超過這麼久就算「卡住」，值得看一眼
    var RECENT_JOBS = 10;
    // ZH: 使用率到這個百分比才算「忙碌」。沒人用的卡也會有個位數的讀數
    //     （驅動、顯示輸出、監控本身），用 > 0 判斷的話「GPU 忙碌」永遠等於全部。
    var BUSY_PCT = 10;

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

    // ZH: 一段失敗只讓那一段顯示錯誤，其餘照常。回傳 null 代表這一段沒拿到。
    function safe(p, where) {
        return p.catch(function (e) {
            return { __failed: (e && e.message) || String(e), __where: where };
        });
    }

    function failed(x) { return x && x.__failed; }

    // ZH: withWhere：同一段裡有兩個來源時（機器卡＝節點清單＋GPU 讀數），
    //     兩行一模一樣的「這一段暫時讀不到（HTTP 500）」分不出是哪一個壞了 ——
    //     補上來源名（端點名，是識別碼，不翻）。
    function failBox(x, withWhere) {
        var w = withWhere && x.__where ? x.__where + ' · ' + x.__failed : x.__failed;
        return '<p class="footnote">'
            + esc(T('ov_fail_part', '這一段暫時讀不到（{w}）').replace('{w}', w))
            + '</p>';
    }

    // ── 重畫（保住焦點與展開狀態）────────────────────────────────────────
    //
    // ZH: 🔴 原本每 10 秒整段 innerHTML 換掉。外部 AI 的名單現在是收合區（<details>），
    //     照舊整段換的話，使用者剛點開的名單 10 秒後就被收回去；Tab 停在某張機器卡上的人，
    //     焦點也每 10 秒掉回 <body>。
    //
    // ZH: 兩層保護：
    //       1. 內容沒變就**不碰 DOM**（多數的 10 秒裡什麼都沒變）。
    //       2. 真的要換時：收合區的開合由 AdminFold.html() 照記住的狀態帶回 open；
    //          焦點則先記下「是哪一個」（data-k，或收合區的 data-fold），換完再放回去。
    //     ⚠ 不用元素參照記焦點 —— innerHTML 之後舊元素已經不在文件裡了。
    function focusKey(box) {
        var a = document.activeElement;
        if (!a || !box.contains(a)) return null;
        var k = a.closest('[data-k]');
        if (k) return { sel: '[data-k="' + k.getAttribute('data-k') + '"]' };
        var f = a.tagName === 'SUMMARY' ? a.closest('[data-fold]') : null;
        if (f) return { sel: '[data-fold="' + f.getAttribute('data-fold') + '"] > summary' };
        return null;
    }

    function paint(id, html) {
        var box = $(id);
        if (!box || box.__html === html) return;
        var fk = focusKey(box);
        box.innerHTML = html;
        box.__html = html;
        if (fk) {
            // ZH: data-k 的值是我們自己組的（節點 id 已 encodeURIComponent），可以直接放進選擇器。
            var el = box.querySelector(fk.sel);
            if (el) el.focus({ preventScroll: true });
        }
    }

    // ── 數字格 ────────────────────────────────────────────────────────────
    // ZH: value 為 null ＝這個來源讀不到，顯示「—」而不是 0 ——
    //     0 是「沒事」，讀不到是「不知道」，兩者不能長得一樣。
    // ZH: warn 只給「需要動作」的數字（與 .adm-head__count--warn 同一條原則）。
    function tile(key, value, warn) {
        var v = $('tv-' + key);
        if (v) v.textContent = value == null ? '—' : String(value);
        var t = $('tile-' + key);
        if (t) t.classList.toggle('is-warn', !!warn && value != null);
    }

    // ── 機器（節點 × GPU）───────────────────────────────────────────────
    // ZH: 兩個來源各自可能失敗，所以合併時以「有拿到的」為準：
    //     節點清單的順序在前（後端排過），只出現在 GPU 讀數裡的機器接在後面 ——
    //     節點清單讀不到的時候，至少還看得到有哪幾台在回報 GPU。
    function machines(nodes, stats) {
        var byId = {}, order = [];
        function slot(id) {
            if (!byId[id]) { byId[id] = { id: id, node: null, gpus: [] }; order.push(id); }
            return byId[id];
        }
        if (!failed(nodes)) (nodes.nodes || []).forEach(function (n) { slot(n.node_id).node = n; });
        if (!failed(stats)) (stats || []).forEach(function (g) { slot(g.node_id).gpus.push(g); });
        return order.map(function (id) { return byId[id]; });
    }

    function machineOffline(m) {
        if (m.node) return m.node.state === 'offline';
        return m.gpus.length > 0 && m.gpus.every(function (g) { return g.status !== 'online'; });
    }

    // ── 需要你處理的 ──────────────────────────────────────────────────────
    function renderAlerts(nodes, jobs, reports, ext) {
        var items = [];

        if (!failed(nodes)) {
            var list = nodes.nodes || [];
            var offList = list.filter(function (n) { return n.state === 'offline'; });
            var disList = list.filter(function (n) { return n.state === 'disabled'; });
            var off = offList.length;
            var dis = disList.length;
            var conflictNode = list.filter(function (n) { return n.ip_conflict; })[0];
            var conflict = !!conflictNode;

            // ZH: 「去看」要連到**那個節點**,不是只連到平台設定頁。
            //     只給 platform.html 的話會停在頁面最上面 ——
            //     GPU 節點那一區在很下面,使用者得自己找。
            //
            // ZH: `#node-<id>` 是平台設定頁認得的深層連結:它會切到「平台」檢視、
            //     捲到 GPU 節點區,而且**在下拉裡選中那一台**（見 platform.js 的
            //     viewFromHash / scrollToHash / hashNodeId 三支）。
            //
            // ZH: 多台同時掉線時取第一台 —— 捲動的目標是整個區塊,
            //     所以看得到全部;選中第一台只是給一個合理的起點。
            function nodeLink(n) {
                return n && n.node_id
                    ? 'platform.html#node-' + encodeURIComponent(n.node_id)
                    : 'platform.html';
            }
            // ZH: 🔴 撞名放在最前面 —— 它會讓派工結果**無聲地錯**，
            //     比掉線嚴重（掉線至少看得出來沒在跑）。
            if (conflict) items.push({ sev: 'error', go: nodeLink(conflictNode), k: 'a-conflict',
                                text: T('ov_a_conflict',
                                    '有節點回報 NODE_ID 撞名 —— 兩台機器用了同一個名字，派工會亂') });
            if (off) items.push({ sev: 'warn', go: nodeLink(offList[0]), k: 'a-offline',
                text: T('ov_a_offline', '{n} 個 GPU 節點掉線').replace('{n}', off) });
            if (dis) items.push({ sev: 'warn', go: nodeLink(disList[0]), k: 'a-disabled',
                text: T('ov_a_disabled', '{n} 個 GPU 節點被停用中').replace('{n}', dis) });
        }

        // ZH: 「有用量 × 不在平台」原本只是四格裡的一格，而且常常落在第一屏之外。
        //     它是外部 AI 那一區**唯一需要動作**的格子（帳號被別人拿去用的樣子就長這樣），
        //     所以升成提醒；「查看」捲到同一頁下面那份名單。
        if (!failed(ext)) {
            var nOff = (ext.using_offplat || []).length;
            if (nOff) items.push({ sev: 'warn', go: '#dz-ov-offplat', k: 'a-offplat',
                text: T('dz_ov_a_offplat', '{n} 人在外部 AI 有用量，人卻不在平台上（可能是帳號被借用）')
                    .replace('{n}', nOff) });
        }

        if (!failed(jobs)) {
            var now = Date.now();
            var dayAgo = now - 86400000;
            var nFail = jobs.filter(function (j) {
                var t = Date.parse(j.completed_at || j.created_at || 0);
                return j.status === 'failed' && t >= dayAgo;
            }).length;
            var nWait = jobs.filter(function (j) {
                if (j.status !== 'pending' && j.status !== 'queued') return false;
                var t = Date.parse(j.created_at || 0);
                return t && (now - t) > WAITING_MIN * 60000;
            }).length;
            if (nFail) items.push({ sev: 'warn', text: T('ov_a_failed', '最近 24 小時有 {n} 張任務失敗').replace('{n}', nFail), go: null });
            if (nWait) items.push({
                sev: 'warn',
                text: T('ov_a_waiting', '{n} 張任務排隊超過 {m} 分鐘')
                    .replace('{n}', nWait).replace('{m}', WAITING_MIN),
                go: null,
            });
        }

        if (!failed(reports) && reports.open) {
            items.push({
                sev: 'info',
                text: T('ov_a_reports', '{n} 則問題回報還沒處理').replace('{n}', reports.open),
                // ZH: 連到**回報區**，不是訊息頁頂端 —— 頂端是公告，落在那裡還得自己往下找。
                go: 'reports.html#h-reports',
                k: 'a-reports',
            });
        }

        // ZH: 有幾個來源讀不到。讀不到的那一段**不會**產生提醒 ——
        //     所以「一條提醒都沒有」不等於沒事，不能在這時候說「目前沒有需要處理的事」。
        var nBroken = [nodes, jobs, reports, ext].filter(failed).length;
        var partial = nBroken
            ? '<p class="footnote">' + esc(T('dz_ov_a_partial', '有 {n} 個資料來源暫時讀不到，這份清單可能不完整。')
                .replace('{n}', nBroken)) + '</p>'
            : '';

        var cnt = $('alerts-count');
        cnt.textContent = items.length ? String(items.length) : '';
        cnt.classList.toggle('adm-head__count--warn', items.length > 0);

        if (!items.length) {
            // ZH: **明確說沒事。** 空白與「還在載入」在畫面上長得一樣。
            paint('alerts', partial ||
                '<p class="adm-clear">' + esc(T('ov_all_clear', '目前沒有需要處理的事。')) + '</p>');
            return { n: 0, broken: nBroken };
        }

        // ZH: 動作欄**一律保留寬度**（沒有連結的列放一個空的 .dz-ov-alert__go）——
        //     原本有按鈕的列 68px、沒按鈕的 48px，一疊提醒高低不齊、右緣也不成一直線。
        paint('alerts', items.map(function (a) {
            return '<div class="adm-alert adm-alert--' + a.sev + '">'
                + '<span>' + esc(a.text) + '</span>'
                + '<div class="dz-ov-alert__go">'
                + (a.go ? '<a class="btn btn--minor" href="' + esc(a.go) + '"'
                    + (a.k ? ' data-k="' + a.k + '"' : '') + '>'
                    + esc(T('ov_a_go', '查看')) + '</a>' : '')
                + '</div>'
                + '</div>';
        }).join('') + partial);
        return { n: items.length, broken: nBroken };
    }

    // ── 機器卡 ────────────────────────────────────────────────────────────
    // ZH: 量表的三欄（標籤｜長條｜數值）由**整張卡共用一個 grid**（.dz-ov-meters，
    //     每個 .adm-meter 是 display:contents）。原本每一條自己一個 grid，
    //     數值欄各自 auto —— 「45 %」窄、「12034 / 24576 MB」寬，
    //     於是記憶體那條長條明顯比另外兩條短，右緣也不齊。
    function meter(label, pct, text) {
        pct = Math.max(0, Math.min(100, Math.round(pct || 0)));
        return '<div class="adm-meter">'
            + '<span class="adm-meter__label">' + esc(label) + '</span>'
            + '<span class="adm-meter__bar"><i style="width:' + pct + '%"></i></span>'
            + '<span class="adm-meter__val">' + esc(text) + '</span>'
            + '</div>';
    }

    // ZH: 記憶體改寫成 GB、一位小數：「12034 / 24576 MB」有 16 個字寬，
    //     是數值欄被撐寬、長條被擠短的主因。
    function gb(mb) { return (Number(mb || 0) / 1024).toFixed(1); }

    function gpuBlock(g, dim) {
        // ZH: 舊版 worker 沒有逐卡資料，後端回一筆聚合（gpu_id 為 '-'、name 就是節點 id）——
        //     那時不要印「GPU - · <節點 id>」這種看起來像壞掉的字。
        var label = (g.gpu_id != null && g.gpu_id !== '-' ? 'GPU ' + g.gpu_id : 'GPU')
            + (g.name && g.name !== g.node_id ? ' · ' + g.name : '');
        var memTxt = g.memory_total
            ? gb(g.memory_used) + ' / ' + gb(g.memory_total) + ' GB'
            : '—';
        return '<div class="dz-ov-gpu' + (dim ? ' dz-ov-gpu--off' : '') + '">'
            + '<div class="dz-ov-gpu__name">' + esc(label) + '</div>'
            + meter(T('ov_util', '使用率'), g.utilization, (g.utilization || 0) + ' %')
            + meter(T('ov_temp', '溫度'), g.temperature, (g.temperature || 0) + ' °C')
            + meter(T('ov_mem', '記憶體'),
                    g.memory_total ? (g.memory_used || 0) / g.memory_total * 100 : 0, memTxt)
            + '</div>';
    }

    function fact(key, zh, value) {
        return '<div><dt>' + esc(T(key, zh)) + '</dt><dd>' + esc(value) + '</dd></div>';
    }

    function machineCard(m) {
        var n = m.node;
        var off = machineOffline(m);
        var name = n ? (n.display_name || n.node_id) : m.id;
        var pill = n
            ? '<span class="adm-pill adm-pill--' + esc(n.state) + '">' + esc(T('st_' + n.state, n.state)) + '</span>'
            : (off ? '<span class="adm-pill adm-pill--offline">' + esc(T('st_offline', '掉線')) + '</span>' : '');

        // ZH: 整張卡可點 → 平台設定的那個節點。
        //     在總覽看到「這台溫度不對／掉線了」之後，下一個動作幾乎一定是
        //     去調它 —— 讓他自己在導覽裡找到平台設定、再捲到對的節點，
        //     是把一個已知的去處變成一段尋找。
        //
        // ZH: 用 <a> 而不是在 div 上綁 click：Ctrl+點開新分頁、鍵盤 Tab 到它、
        //     滑鼠移上去看得到網址 —— 這些是瀏覽器本來就會做的事，
        //     自己用 JS 模擬只會做出一個半殘的連結。
        //
        // ZH: 掉線的整張變淡（.is-offline），**不隱藏** ——
        //     它消失的話，「這台掉線了」與「這台被拆掉了」就分不出來。
        var key = encodeURIComponent(m.id);
        return '<a class="adm-card adm-card--link dz-ov-mach' + (off ? ' is-offline' : '') + '"'
            + ' href="platform.html#node-' + key + '" data-k="m-' + esc(key) + '"'
            + ' title="' + esc(T('ov_gpu_go', '到平台設定調整這個節點')) + '">'
            + '<div class="dz-ov-mach__head">'
            + '<span class="dz-ov-mach__name">' + esc(name) + '</span>'
            + pill
            + (n && n.ip_conflict ? '<span class="adm-pill adm-pill--error">!</span>' : '')
            + '</div>'
            + (n
                ? '<dl class="dz-ov-mach__facts">'
                    + fact('ov_n_pool', '池別', n.effective_pool || '—')
                    + fact('ov_n_running', '執行中', n.running_jobs != null ? n.running_jobs : '—')
                    + fact('ov_n_next', '下次變化', n.next_change ? TW.when(n.next_change) : '—')
                    + fact('ov_n_seen', '最後心跳', n.last_seen ? TW.when(n.last_seen) : '—')
                    + '</dl>'
                : '')
            + (m.gpus.length
                ? '<div class="dz-ov-meters">' + m.gpus.map(function (g) {
                    // ZH: 整張卡已經變淡時不再對單張 GPU 變淡一次（0.5 × 0.5 會淡到看不清）。
                    return gpuBlock(g, !off && g.status !== 'online');
                }).join('') + '</div>'
                : '')
            + '</a>';
    }

    function renderMachines(nodes, stats) {
        var list = machines(nodes, stats);
        var html = '';
        // ZH: 兩個來源各自報錯 —— 節點讀不到時卡片仍畫得出 GPU 讀數，反之亦然。
        if (failed(nodes)) html += failBox(nodes, true);
        if (failed(stats)) html += failBox(stats, true);

        var cnt = $('nodes-count');
        if (!list.length) {
            cnt.textContent = '';
            if (!failed(nodes) || !failed(stats)) {
                html += '<p class="footnote">' + esc(T('ov_gpu_none', '沒有任何 GPU 節點回報過心跳。')) + '</p>';
            }
            paint('nodes', html);
            // ZH: 🔴「沒有機器」與「讀不到」要分開回：前者是 0 / 0（真的沒有），後者才是 null →
            //     數字格顯示「—」（tile() 的規則：0＝沒事、—＝不知道，兩者不能長得一樣）。
            //     原本兩種都回 null，於是端點好好的、只是還沒有任何節點時也顯示「—」。
            //     判準與上面那句「沒有任何 GPU 節點」相同：至少一個來源讀得到就算知道。
            return failed(nodes) && failed(stats) ? null : { on: 0, all: 0 };
        }

        var on = list.filter(function (m) { return !machineOffline(m); }).length;
        cnt.textContent = T('dz_ov_m_count', '{on} / {all} 在線')
            .replace('{on}', on).replace('{all}', list.length);
        cnt.classList.toggle('adm-head__count--warn', on < list.length);

        paint('nodes', html + '<div class="adm-grid dz-ov-machines">' + list.map(machineCard).join('') + '</div>');
        return { on: on, all: list.length };
    }

    // ── 最近的任務 ────────────────────────────────────────────────────────
    // ZH: 狀態原本直接印後端的英文字串（completed／failed），同一頁的節點狀態卻有翻譯。
    //     沿用數據頁「訓練任務」那組 key —— 同一個狀態在兩頁叫同一個名字。
    // ZH: `queued` 併進「待執行」、膠囊顏色也跟 pending 一樣（數據頁同一個決定：
    //     它是舊別名，提醒那邊也把兩個都算成排隊）。
    // ZH: [key, 中文] 成對寫在一起 —— check_i18n 認的是「key 後面緊接中文」這個形狀。
    var JOB_ST = {
        pending:   ['an_j_pending',   '待執行'],
        queued:    ['an_j_pending',   '待執行'],
        running:   ['an_j_running',   '執行中'],
        completed: ['an_j_done',      '已完成'],
        failed:    ['an_j_failed',    '失敗'],
        cancelled: ['an_j_cancelled', '已取消'],
    };

    function renderJobs(jobs) {
        if (failed(jobs)) { paint('jobs', failBox(jobs)); return; }
        if (!jobs.length) {
            paint('jobs', '<p class="footnote">' + esc(T('ov_j_none', '還沒有任何任務。')) + '</p>');
            return;
        }
        // ZH: 「任務」那一欄吃掉剩下的寬度（.grow），其他欄只佔內容需要的寬度 ——
        //     原本五欄平均分 1440px，8 碼的使用者 id 和節點名中間隔了兩百多 px。
        var head = [
            ['ov_j_name', '任務', 'grow'], ['ov_j_user', '使用者', ''], ['ov_j_status', '狀態', ''],
            ['ov_j_node', '節點', ''], ['ov_j_when', '時間', ''],
        ];

        paint('jobs',
            '<div class="adm-tablewrap"><table class="adm-table"><thead><tr>'
            + head.map(function (h) {
                return '<th' + (h[2] ? ' class="' + h[2] + '"' : '') + '>' + esc(T(h[0], h[1])) + '</th>';
            }).join('')
            + '</tr></thead><tbody>'
            + jobs.slice(0, RECENT_JOBS).map(function (j) {
                var st = JOB_ST[j.status];
                var cls = j.status === 'queued' ? 'pending' : j.status;
                return '<tr>'
                    + '<td class="grow">' + esc(j.job_name || j.job_id) + '</td>'
                    // ZH: 只顯示 user_id 的前 8 碼 —— 這一頁不需要知道是誰，
                    //     只需要看得出「是不是同一個人」。要查人請去「人」那一頁。
                    + '<td class="mono">' + esc((j.user_id || '—').slice(0, 8)) + '</td>'
                    + '<td><span class="adm-pill adm-pill--' + esc(cls) + '">'
                    // ZH: 認不得的狀態照印原始字串 —— 醜，但看得見（與數據頁同一個取捨）。
                    + esc(st ? T(st[0], st[1]) : j.status) + '</span></td>'
                    + '<td>' + esc(j.gpu_server || '—') + '</td>'
                    + '<td>' + esc(TW.when(j.completed_at || j.started_at || j.created_at) || '—') + '</td>'
                    + '</tr>';
            }).join('')
            + '</tbody></table></div>');
    }

    // ── 外部 AI 使用狀況 ──────────────────────────────────────────────────
    //
    // ZH: 後端把兩個獨立的問題交叉起來：
    //       廠商那邊近期有沒有扣點？  ×  這個人近期有沒有在平台上活動？
    //     原本畫成四格，但四格裡**只有一格需要動作**（有用量、人卻不在平台）——
    //     其餘三格是資訊，卻跟它佔一樣大的版面，還讓這一區成了整頁最大的區塊。
    //
    // ZH: 現在：那一格攤開（而且上面已經升成一列提醒）；使用中／在平台沒動 AI／未綁定
    //     只給人數，名單收進 AdminFold，想看再點開。
    //
    // ZH: 沒用量也不在線的人**仍然不列**：那是絕大多數人的常態，列出來只是一份沒有用的通訊錄。
    //     原本那一格的說明搬進 ⓘ。
    //
    // ZH: 未綁定的人**不屬於那四種組合** —— 他們在廠商那邊有用量，但對不到任何平台帳號，
    //     所以「平台在線」這個軸對他們沒有意義。和另外兩格並排只是因為版面，
    //     標題寫的是「未綁定」而不是任何一個軸的名字。
    //
    // ZH: 🔴 兩個軸的新鮮度**不一樣**：平台在線是即時的，廠商用量是定期同步來的，
    //     最舊可能是幾小時前。後端的 docstring 特別要求前端把 last_tx_sync
    //     顯示出來 —— 寫在標題列右邊（#ext-sync），不收進 ⓘ。
    //
    // ZH: 名單上限：原本每格 6 人是因為四格一直攤開。現在攤開的只剩要處理的那一格，
    //     其他是使用者自己點開的 —— 給到 20 人，其餘用「還有 N 人」帶過。
    var LIST_NAMES = 20;

    function nameList(rows, timeKey) {
        if (!rows.length) return '<p class="footnote">' + esc(T('ov_ext_zero', '沒有人。')) + '</p>';
        var shown = rows.slice(0, LIST_NAMES);
        return '<ul class="adm-quad__list dz-ov-names">' + shown.map(function (r) {
            return '<li' + (r.email ? ' title="' + esc(r.email) + '"' : '') + '>'
                + '<span class="adm-quad__who">'
                + esc(r.username || r.vendor_name || r.vendor_sn || '—') + '</span>'
                + '<span class="adm-quad__meta">'
                + '<span>' + esc(r[timeKey] ? TW.time(r[timeKey]) : '—') + '</span>'
                // ZH: 點數只有「有用量」的人才有意義（在平台沒動 AI 的人沒有這個欄位）。
                + (r.points_used != null
                    ? '<span>' + esc(r.points_used) + esc(T('an_points', '點')) + '</span>' : '')
                + '</span></li>';
        }).join('') + '</ul>'
            + (rows.length > shown.length
                ? '<p class="footnote">' + esc(T('ov_ext_more', '還有 {n} 人。')
                    .replace('{n}', rows.length - shown.length)) + '</p>'
                : '');
    }

    // ZH: 收合區的 id 固定（ov-ext-*）—— AdminFold 以它記住開合，每 10 秒重畫時照著帶回 open。
    function extFold(id, key, zh, rows, timeKey) {
        return AdminFold.html({
            id: id, key: key, zh: zh, tag: 'h3', cls: 'dz-ov-fold',
            count: rows.length,
            body: nameList(rows, timeKey),
        });
    }

    function renderExt(d) {
        var sync = $('ext-sync');
        var win = $('ext-window');
        if (failed(d)) {
            sync.textContent = '';
            win.textContent = '';
            paint('ext', failBox(d));
            return null;
        }

        // ZH: 同步時間一定要講。沒有它的話，一份幾小時前的名單看起來像現在的名單。
        sync.textContent = d.last_tx_sync
            ? T('dz_ov_ext_synced', '用量同步到 {t}').replace('{t}', TW.dateTime(d.last_tx_sync))
            : T('ov_ext_nosync', '還沒有同步過廠商的交易日誌。');
        win.textContent = T('ov_ext_window', '用量看最近 {n} 分鐘。')
            .replace('{n}', d.usage_window_minutes);

        var offplat = d.using_offplat || [];
        // ZH: 要處理的那一格：標題旁的數字有人時上警示色，沒人時是中性的「0」——
        //     仍然留著這一塊（而不是整塊消失），「0 人」本身就是要看的答案。
        var hot = '<div class="dz-ov-hot' + (offplat.length ? ' is-hot' : '') + '" id="dz-ov-offplat">'
            + '<div class="dz-ov-hot__head">'
            + '<h3 class="adm-head__title">' + esc(T('ov_ext_offplat', '不在平台')) + '</h3>'
            + '<span class="adm-head__count' + (offplat.length ? ' adm-head__count--warn' : '') + '">'
            + esc(offplat.length) + '</span>'
            // ZH: 只寫「不在平台」會被讀成「不在線的人」—— 補上另一個軸：這些人**有用量**。
            + '<span class="adm-head__meta">' + esc(T('ov_ext_ax_used', '有用量')) + '</span>'
            + '</div>'
            + nameList(offplat, 'last_used_at')
            + '</div>';

        paint('ext', hot
            + '<div class="adm-cols dz-ov-folds">'
            + extFold('ov-ext-active', 'ov_ext_active', '使用中', d.using_active || [], 'last_used_at')
            + extFold('ov-ext-online', 'ov_ext_online', '在平台沒動 AI', d.online_idle || [], 'last_activity')
            + extFold('ov-ext-unlinked', 'ov_ext_unlinked', '未綁定', d.unlinked || [], 'last_used_at')
            + '</div>');
        return offplat.length;
    }

    // ── 載入 ──────────────────────────────────────────────────────────────
    var timer = null;

    async function load() {
        var out = await Promise.all([
            safe(get('/admin/gpu-nodes'), 'gpu-nodes'),
            safe(get('/admin/cluster/stats'), 'cluster'),
            safe(get('/admin/jobs?limit=100'), 'jobs'),
            safe(get('/admin/reports/summary'), 'reports'),
            safe(get('/external-ai/admin/live-usage'), 'live-usage'),
        ]);
        var nodes = out[0], stats = out[1], jobs = out[2], reports = out[3], ext = out[4];

        var todo = renderAlerts(nodes, jobs, reports, ext);
        var mach = renderMachines(nodes, stats);
        var nOff = renderExt(ext);
        renderJobs(jobs);

        // ZH: 數字格最後填 —— 它只是把上面各段算好的數字再講一次，不另外算一套
        //     （兩套算法遲早會對不上：格子寫 2、下面列了 3 條）。
        // ZH: 一條提醒都沒有、但有來源讀不到 → 「—」而不是「0」（理由同上面「清單可能不完整」那一句）。
        tile('todo', todo.n || !todo.broken ? todo.n : null, todo.n > 0);
        tile('nodes', mach ? mach.on + ' / ' + mach.all : null, mach && mach.on < mach.all);
        if (failed(stats)) {
            tile('gpu', null, false);
        } else {
            var busy = stats.filter(function (g) {
                return g.status === 'online' && (g.utilization || 0) >= BUSY_PCT;
            }).length;
            tile('gpu', busy + ' / ' + stats.length, false);
        }
        tile('reports', failed(reports) ? null : (reports.open || 0), !failed(reports) && reports.open > 0);
        tile('offplat', nOff, nOff > 0);

        // ZH: 時間戳一定要更新 —— 它是「這一頁還活著」的唯一證據。
        $('updated').textContent =
            T('ov_updated', '最後更新 {t}').replace('{t}', TW.time(new Date().toISOString()));
    }

    function start() {
        load();
        // ZH: 分頁在背景時不要空轉 —— 管理員常常開著這一頁一整天。
        clearInterval(timer);
        timer = setInterval(function () {
            if (!document.hidden) load();
        }, REFRESH_MS);
    }

    $('refresh').addEventListener('click', load);
    document.addEventListener('prefs:langchanged', load);
    // ZH: 從背景切回來時立刻補一次 —— 不然最多要等 10 秒才看到現況。
    document.addEventListener('visibilitychange', function () {
        if (!document.hidden) load();
    });

    start();
})();
