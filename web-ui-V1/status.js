/* ==========================================================================
 * status.js — GPU 現在忙不忙（v4.24）
 *
 * ZH: 這一頁回答一個問題：**我現在能不能用，不能的話要等多久。**
 *     在它之前，任務排在佇列裡不動時使用者只能來問人 ——
 *     而「是誰佔著、還要多久」系統本來就知道（見 crud.gpu_status）。
 *
 * ZH: 🔴 **先給結論再給細節。** 最上面那一句是「現在可以借／現在借不到」，
 *     卡片是理由。倒過來的話，使用者要自己從六張卡的狀態推結論，
 *     而那正是他進來想避免的事。
 *
 * ZH: 🔴 **不顯示是誰在用**（後端也不給）。判斷「要等還是改天」用不到對方是誰，
 *     知道了只會變成互相催促。自己的任務才帶名稱。
 *
 * ZH: ⚠ 自動更新 20 秒一次，而且**分頁看不見時停掉**（visibilitychange）。
 *     開著不管的分頁每 20 秒打一次 API，30 台節點上線後那是白白的負載；
 *     「網頁一直輪詢」也正是 09-20 那次被校園 IPS 盯上的原因之一。
 * ========================================================================== */
(function () {
    'use strict';

    var API = '/api/v1';
    var TIMER = null;
    var EVERY_MS = 20000;

    function $(id) { return document.getElementById(id); }

    function T(key, fallback) {
        try { return (window.T ? window.T(key, fallback) : fallback); }
        catch (e) { return fallback; }
    }

    function esc(v) {
        return String(v == null ? '' : v).replace(/[&<>"']/g, function (c) {
            return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
        });
    }

    function authHeaders() {
        var t = sessionStorage.getItem('ai_hud_token') || localStorage.getItem('ai_hud_token');
        return t ? { Authorization: 'Bearer ' + t } : {};
    }

    /* ZH: 🔴 時間一律走 tz.js 的 `TW`（全站同一份規則）。
     *     後端回的字串**沒有時區標記**（SQLite 取回是 naive UTC），
     *     `new Date()` 會把它當本地時間 —— 台灣的使用者會看到早 8 小時的時刻。
     *     實際踩過：「最後心跳 上午11:44」而當下是 19:44。
     * ZH: ⚠ 全域名是 `TW` 不是 `TZ`（檔名 tz.js、匯出 window.TW）。
     *     寫錯的話不會報錯，只會安靜地退回錯的那條路 —— 也踩過。
     * ZH: 真的載不到才退回本地格式：只有**有時區標記**的字串那樣才對，
     *     所以退路裡把沒有標記的補上 Z，兩條路的結果一致。
     */
    function hhmm(iso) {
        if (!iso) return '';
        try {
            if (window.TW && window.TW.time) return window.TW.time(iso);
            var s = String(iso);
            if (!/(?:Z|[+-]\d{2}:?\d{2})$/.test(s)) s += 'Z';
            return new Date(s).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        } catch (e) { return ''; }
    }

    /* ZH: 「還要多久」。⚠ 只在**有到期時間**時才說 ——
     *     批次訓練沒有硬性期限，編一個出來比不說更糟。 */
    function remain(iso) {
        if (!iso) return '';
        var ms = new Date(iso) - new Date();
        if (isNaN(ms) || ms <= 0) return '';
        var m = Math.round(ms / 60000);
        if (m < 60) return T('gs_in_min', '約 {n} 分鐘後').replace('{n}', m);
        var h = Math.floor(m / 60);
        return T('gs_in_hm', '約 {h} 小時 {m} 分後')
            .replace('{h}', h).replace('{m}', m % 60);
    }

    // ── 結論那一句 ────────────────────────────────────────────────────
    function verdict(d) {
        var pool = (d.pools && (d.pools.interactive || d.pools.batch)) || {};
        var el = $('gs-verdict');
        var next = $('gs-next');
        next.hidden = true;

        if (pool.available) {
            el.textContent = T('gs_ok', '現在可以用 —— 有機器在線而且在開放時段內。');
            return;
        }
        el.textContent = T('gs_busy', '現在借不到 GPU。');
        if (pool.next_open) {
            next.textContent = T('gs_next_open', '下一個開放時段：{t}')
                .replace('{t}', hhmm(pool.next_open));
            next.hidden = false;
        } else {
            // ZH: next_open 為 null 的意思是「給不出時間」，不是「馬上就好」——
            //     那通常是機器離線。講清楚，不要讓他一直重新整理等一個不會來的時刻。
            next.textContent = T('gs_no_eta', '目前沒有機器在線，給不出預計時間。');
            next.hidden = false;
        }
    }

    // ── 每張卡 ────────────────────────────────────────────────────────
    function gpuCard(g, nodeName) {
        var badge, detail = '';
        if (g.state === 'lab') {
            badge = g.mine ? T('gs_st_lab_mine', '你的程式實驗室')
                           : T('gs_st_lab', '程式實驗室使用中');
            var r = remain(g.until);
            detail = r ? T('gs_free_at', '預計 {t} 釋放').replace('{t}', r) : '';
        } else if (g.state === 'job') {
            badge = g.mine ? T('gs_st_job_mine', '你的訓練任務')
                           : T('gs_st_job', '訓練任務執行中');
            // ZH: 訓練沒有到期時間 —— 只說「從幾點開始跑」，讓他自己判斷。
            detail = g.since ? T('gs_since', '{t} 開始').replace('{t}', hhmm(g.since)) : '';
        } else {
            badge = T('gs_st_idle', '空閒');
        }
        if (g.mine && g.label) {
            detail = (detail ? detail + '｜' : '') + esc(g.label);
        }

        var mem = '';
        if (g.memory_total) {
            mem = Math.round((g.memory_used || 0) / 1024) + ' / '
                + Math.round(g.memory_total / 1024) + ' GB';
        }

        return '<div class="gpucard gpucard--' + esc(g.state) + '">'
            + '<div class="gpucard__top">'
            + '<span class="gpucard__idx">GPU ' + esc(g.index) + '</span>'
            + '<span class="gpucard__badge">' + esc(badge) + '</span>'
            + '</div>'
            + '<div class="gpucard__name">' + esc(g.name || nodeName) + '</div>'
            + (detail ? '<div class="gpucard__meta">' + detail + '</div>' : '')
            + (mem ? '<div class="gpucard__meta">'
                   + esc(T('gs_mem', '顯示記憶體')) + '：' + esc(mem) + '</div>' : '')
            + '</div>';
    }

    function renderCards(d) {
        var html = [];
        (d.nodes || []).forEach(function (n) {
            // ZH: 離線節點的卡片不畫 —— 那是**最後一次看到的樣子**，不是現況。
            //     畫出來的話「空閒」會變成謊話。機器狀態那一區會講它離線了。
            if (!n.online) return;
            (n.gpus || []).forEach(function (g) { html.push(gpuCard(g, n.display_name)); });
        });
        $('gs-cards').innerHTML = html.length ? html.join('')
            : '<p class="gpuwall__note">' + esc(T('gs_no_gpu', '目前沒有在線的機器。')) + '</p>';
    }

    // ── 佇列 ──────────────────────────────────────────────────────────
    function renderQueue(d) {
        var q = d.queue || { pending: 0, mine: [] };
        $('gs-queue').textContent = q.pending
            ? T('gs_q_n', '現在有 {n} 個任務在排隊。').replace('{n}', q.pending)
            : T('gs_q_0', '現在沒有任務在排隊。');

        var ul = $('gs-mine');
        ul.innerHTML = (q.mine || []).map(function (j) {
            var pos = (j.position == null)
                ? T('gs_q_unknown', '位置計算中')
                : T('gs_q_pos', '第 {n} 位').replace('{n}', j.position);
            return '<li>' + esc(j.job_name) + ' —— ' + esc(pos) + '</li>';
        }).join('');
    }

    // ── 機器狀態 ──────────────────────────────────────────────────────
    function renderNodes(d) {
        $('gs-nodes').innerHTML = (d.nodes || []).map(function (n) {
            var state, cls;
            if (!n.online) { state = T('gs_n_off', '離線'); cls = 'off'; }
            else if (!n.enabled) { state = T('gs_n_disabled', '已停用'); cls = 'off'; }
            else if (!n.dispatch_allowed) { state = T('gs_n_closed', '不在開放時段'); cls = 'closed'; }
            else { state = T('gs_n_ok', '正常收工作'); cls = 'ok'; }

            return '<div class="gpucard gpucard--node-' + cls + '">'
                + '<div class="gpucard__top">'
                + '<span class="gpucard__idx">' + esc(n.display_name) + '</span>'
                + '<span class="gpucard__badge">' + esc(state) + '</span>'
                + '</div>'
                + '<div class="gpucard__meta">'
                + esc(T('gs_n_pool', '用途')) + '：'
                + esc(n.pool === 'interactive' ? T('gs_pool_i', '互動（實驗室優先）')
                                               : T('gs_pool_b', '批次訓練'))
                + '</div>'
                + (n.last_seen ? '<div class="gpucard__meta">'
                    + esc(T('gs_n_seen', '最後心跳')) + '：' + esc(hhmm(n.last_seen))
                    + '</div>' : '')
                + '</div>';
        }).join('');
    }

    // ── 抓資料 ────────────────────────────────────────────────────────
    async function load() {
        try {
            var r = await fetch(API + '/jobs/gpu-status', { headers: authHeaders() });
            if (r.status === 401) { location.replace('login.html'); return; }
            if (!r.ok) throw new Error('HTTP ' + r.status);
            var d = await r.json();

            verdict(d);
            renderCards(d);
            renderQueue(d);
            renderNodes(d);
            $('gs-asof').textContent = T('gs_asof', '更新於 {t}').replace('{t}', hhmm(d.as_of));
            $('gs-body').hidden = false;
            $('gs-msg').hidden = true;
        } catch (e) {
            // ZH: 讀不到就說讀不到，**不要留著上一輪的數字** ——
            //     停在舊畫面上的狀態頁會讓人根據過期資訊做決定。
            $('gs-msg').textContent = T('gs_fail', '暫時讀不到 GPU 狀態，稍後再試。');
            $('gs-msg').hidden = false;
            $('gs-body').hidden = true;
            $('gs-verdict').textContent = '';
        }
    }

    function start() {
        stop();
        load();
        TIMER = setInterval(load, EVERY_MS);
    }
    function stop() {
        if (TIMER) { clearInterval(TIMER); TIMER = null; }
    }

    // ZH: 分頁切走就停，切回來立刻更新一次 —— 見檔頭（不要做無人在看的輪詢）。
    document.addEventListener('visibilitychange', function () {
        if (document.hidden) stop(); else start();
    });

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', start);
    } else {
        start();
    }
}());
