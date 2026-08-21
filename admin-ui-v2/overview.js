/* ==========================================================================
 * overview.js — 總覽（開機看一眼）
 *
 * ZH: 這一頁要回答的問題只有一個：**現在有沒有需要我處理的事？**
 *     所以第一區是「需要你處理的」，而且**沒事的時候要明確說沒事**——
 *     空白會讓人以為還沒載入完，然後多等、重新整理、再懷疑是不是壞了。
 *
 * ZH: 四個資料來源各自獨立抓、獨立失敗：
 *       GET /admin/gpu-nodes        節點六態 + 撞名 + 執行中
 *       GET /admin/cluster/stats    每張 GPU 的溫度／使用率／記憶體
 *       GET /admin/jobs             最近的任務
 *       GET /admin/reports/summary  未處理的回報數
 *     ⚠ **一段讀不到不可以讓整頁空白** —— 那會把「回報服務掛了」
 *       表現成「GPU 也不見了」，人就會去查錯的東西。
 *
 * ZH: 自動更新 10 秒一次，**而且畫面上要寫最後更新時間**。
 *     沒有那個時間戳的話，「資料沒變」與「更新卡住了」長得一模一樣。
 * ========================================================================== */
(function () {
    'use strict';

    var API = '/api/v1';
    var REFRESH_MS = 10000;
    var WAITING_MIN = 15;          // ZH: 排隊超過這麼久就算「卡住」，值得看一眼
    var RECENT_JOBS = 10;

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

    function failBox(x) {
        return '<p class="footnote">'
            + esc(T('ov_fail_part', '這一段暫時讀不到（{w}）').replace('{w}', x.__failed))
            + '</p>';
    }

    // ── 需要你處理的 ──────────────────────────────────────────────────────
    function renderAlerts(nodes, jobs, reports) {
        var items = [];

        if (!failed(nodes)) {
            var list = nodes.nodes || [];
            var off = list.filter(function (n) { return n.state === 'offline'; }).length;
            var dis = list.filter(function (n) { return n.state === 'disabled'; }).length;
            var conflict = list.some(function (n) { return n.ip_conflict; });
            // ZH: 🔴 撞名放在最前面 —— 它會讓派工結果**無聲地錯**，
            //     比掉線嚴重（掉線至少看得出來沒在跑）。
            if (conflict) items.push({ sev: 'error', go: 'platform.html',
                                text: T('ov_a_conflict',
                                    '有節點回報 NODE_ID 撞名 —— 兩台機器用了同一個名字，派工會亂') });
            if (off) items.push({ sev: 'warn', text: T('ov_a_offline', '{n} 個 GPU 節點掉線').replace('{n}', off), go: 'platform.html' });
            if (dis) items.push({ sev: 'warn', text: T('ov_a_disabled', '{n} 個 GPU 節點被停用中').replace('{n}', dis), go: 'platform.html' });
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
                go: 'reports.html',
            });
        }

        if (!items.length) {
            // ZH: **明確說沒事。** 空白與「還在載入」在畫面上長得一樣。
            $('alerts').innerHTML =
                '<p class="adm-clear">' + esc(T('ov_all_clear', '目前沒有需要處理的事。')) + '</p>';
            return;
        }

        $('alerts').innerHTML = items.map(function (a) {
            return '<div class="adm-alert adm-alert--' + a.sev + '">'
                + '<span>' + esc(a.text) + '</span>'
                + (a.go ? '<a class="btn btn--minor" href="' + a.go + '">'
                    + esc(T('ov_a_go', '去看')) + '</a>' : '')
                + '</div>';
        }).join('');
    }

    // ── GPU 現況 ──────────────────────────────────────────────────────────
    function meter(label, value, max, unit) {
        var pct = max ? Math.min(100, Math.round(value / max * 100)) : 0;
        return '<div class="adm-meter">'
            + '<span class="adm-meter__label">' + esc(label) + '</span>'
            + '<span class="adm-meter__bar"><i style="width:' + pct + '%"></i></span>'
            + '<span class="adm-meter__val">' + esc(value + unit) + '</span>'
            + '</div>';
    }

    function renderGpus(stats) {
        if (failed(stats)) { $('gpus').innerHTML = failBox(stats); return; }
        if (!stats.length) {
            $('gpus').innerHTML = '<p class="footnote">'
                + esc(T('ov_gpu_none', '沒有任何 GPU 節點回報過心跳。')) + '</p>';
            return;
        }
        $('gpus').innerHTML = stats.map(function (g) {
            var offline = g.status !== 'online';
            // ZH: 整張卡可點 → 平台設定的那個節點。
            //     在總覽看到「這張卡溫度不對／掉線了」之後，下一個動作幾乎一定是
            //     去調它 —— 讓他自己在導覽裡找到平台設定、再捲到對的節點，
            //     是把一個已知的去處變成一段尋找。
            //
            // ZH: 用 <a> 而不是在 div 上綁 click：Ctrl+點開新分頁、鍵盤 Tab 到它、
            //     滑鼠移上去看得到網址 —— 這些是瀏覽器本來就會做的事，
            //     自己用 JS 模擬只會做出一個半殘的連結。
            return '<a class="adm-card adm-card--link' + (offline ? ' is-offline' : '') + '"'
                + ' href="platform.html#node-' + encodeURIComponent(g.node_id) + '"'
                + ' title="' + esc(T('ov_gpu_go', '到平台設定調整這個節點')) + '">'
                + '<div class="adm-card__title">' + esc(g.name)
                + '<span class="footnote">　' + esc(g.node_id) + ' · GPU ' + esc(g.gpu_id) + '</span></div>'
                + meter(T('ov_util', '使用率'), g.utilization || 0, 100, ' %')
                + meter(T('ov_temp', '溫度'), g.temperature || 0, 100, ' °C')
                + meter(T('ov_mem', '記憶體'), g.memory_used || 0, g.memory_total || 0,
                        ' / ' + (g.memory_total || 0) + ' MB')
                + '</a>';
        }).join('');
    }

    // ── 節點 ──────────────────────────────────────────────────────────────
    function renderNodes(nodes) {
        if (failed(nodes)) { $('nodes').innerHTML = failBox(nodes); return; }
        var list = nodes.nodes || [];
        if (!list.length) { $('nodes').innerHTML = ''; return; }

        // ZH: key 與中文**寫在一起**，不要拆成兩個平行陣列。
        //     除了不會對錯位置之外，還有一個實際理由：`check_i18n.py` 的判準是
        //     「key 後面緊接一個含中文的 fallback」——拆開之後它看不到，
        //     會把**實際有在用**的 key 報成「沒有人用」（我已經中過一次）。
        var head = [
            ['ov_n_node', '節點'], ['ov_n_state', '狀態'], ['ov_n_pool', '池別'],
            ['ov_n_running', '執行中'], ['ov_n_next', '下次變化'], ['ov_n_seen', '最後心跳'],
        ];

        $('nodes').innerHTML =
            '<div class="adm-tablewrap"><table class="adm-table"><thead><tr>'
            + head.map(function (h) { return '<th>' + esc(T(h[0], h[1])) + '</th>'; }).join('')
            + '</tr></thead><tbody>'
            + list.map(function (n) {
                return '<tr>'
                    + '<td><a href="platform.html#node-' + encodeURIComponent(n.node_id) + '">'
                    + esc(n.display_name || n.node_id) + '</a>'
                    + (n.ip_conflict ? ' <span class="adm-pill adm-pill--error">!</span>' : '')
                    + '</td>'
                    + '<td><span class="adm-pill adm-pill--' + esc(n.state) + '">'
                    + esc(T('st_' + n.state, n.state)) + '</span></td>'
                    + '<td>' + esc(n.effective_pool || '—') + '</td>'
                    + '<td class="num">' + esc(n.running_jobs != null ? n.running_jobs : '—') + '</td>'
                    + '<td>' + esc(n.next_change ? TW.when(n.next_change) : '—') + '</td>'
                    + '<td>' + esc(n.last_seen ? TW.when(n.last_seen) : '—') + '</td>'
                    + '</tr>';
            }).join('')
            + '</tbody></table></div>';
    }

    // ── 最近的任務 ────────────────────────────────────────────────────────
    function renderJobs(jobs) {
        if (failed(jobs)) { $('jobs').innerHTML = failBox(jobs); return; }
        if (!jobs.length) {
            $('jobs').innerHTML = '<p class="footnote">' + esc(T('ov_j_none', '還沒有任何任務。')) + '</p>';
            return;
        }
        var head = [
            ['ov_j_name', '任務'], ['ov_j_user', '使用者'], ['ov_j_status', '狀態'],
            ['ov_j_node', '節點'], ['ov_j_when', '時間'],
        ];

        $('jobs').innerHTML =
            '<div class="adm-tablewrap"><table class="adm-table"><thead><tr>'
            + head.map(function (h) { return '<th>' + esc(T(h[0], h[1])) + '</th>'; }).join('')
            + '</tr></thead><tbody>'
            + jobs.slice(0, RECENT_JOBS).map(function (j) {
                return '<tr>'
                    + '<td>' + esc(j.job_name || j.job_id) + '</td>'
                    // ZH: 只顯示 user_id 的前 8 碼 —— 這一頁不需要知道是誰，
                    //     只需要看得出「是不是同一個人」。要查人請去「人」那一頁。
                    + '<td class="mono">' + esc((j.user_id || '—').slice(0, 8)) + '</td>'
                    + '<td><span class="adm-pill adm-pill--' + esc(j.status) + '">'
                    + esc(j.status) + '</span></td>'
                    + '<td>' + esc(j.gpu_server || '—') + '</td>'
                    + '<td>' + esc(TW.when(j.completed_at || j.started_at || j.created_at) || '—') + '</td>'
                    + '</tr>';
            }).join('')
            + '</tbody></table></div>';
    }

    // ── 載入 ──────────────────────────────────────────────────────────────
    var timer = null;

    async function load() {
        var out = await Promise.all([
            safe(get('/admin/gpu-nodes'), 'gpu-nodes'),
            safe(get('/admin/cluster/stats'), 'cluster'),
            safe(get('/admin/jobs?limit=100'), 'jobs'),
            safe(get('/admin/reports/summary'), 'reports'),
        ]);
        var nodes = out[0], stats = out[1], jobs = out[2], reports = out[3];

        renderAlerts(nodes, jobs, reports);
        renderGpus(stats);
        renderNodes(nodes);
        renderJobs(jobs);

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
