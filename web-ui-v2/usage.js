/* ==========================================================================
 * [畫面: 使用量明細] — 使用者在這裡要完成：知道點數花在哪，以便調整用法
 *
 * ZH: D4 定為**獨立頁**（有圖表要空間），C3 要求**頁首重述當前額度** ——
 *     使用者是「看著額度覺得快沒了」才點進來的。
 *
 * 相對 v1.5 的三處完善（v1.5 是抽屜裡的 modal）：
 *   1. 額度從角落小灰字升為層級 1。它是這個頁面存在的理由，不是註腳。
 *   2. **圖表顏色由 token 驅動，且切換色系時重繪**。v1.5 的圖表寫死 rgba，
 *      主題換了圖表不會跟著換——在只有一種主題時看不出來，v2 有兩種。
 *   3. 模型清單被截斷時明講截了幾個（v1.5 靜默取前 5/8）。
 *
 * 隱私邊界沿用後端設計，前端不得放寬：只有自己的用量 + 全體「人均」，
 * 無排名、無他人資訊；樣本不足時後端直接不給對照（show=false）。
 * ========================================================================== */
const API = '/api/v1';
const FORCED = new URLSearchParams(location.search).get('state');
const $ = (id) => document.getElementById(id);

let DAYS = 30;
let LAST = null;                 // 最近一次的資料，供切換色系時重繪
let charts = { trend: null, models: null };

// ── 色系切換：**要重繪圖表**，否則顏色停在切換前 ─────────────────────
document.querySelectorAll('[data-set-theme]').forEach((b) => {
    b.addEventListener('click', () => {
        const t = b.dataset.setTheme;
        document.documentElement.dataset.theme = t;
        document.querySelectorAll('[data-set-theme]').forEach((x) => {
            x.setAttribute('aria-pressed', String(x.dataset.setTheme === t));
        });
        if (LAST) drawCharts(LAST);
    });
});

// ── 期間切換 ─────────────────────────────────────────────────────────
document.querySelectorAll('[data-days]').forEach((b) => {
    b.addEventListener('click', () => {
        DAYS = Number(b.dataset.days);
        document.querySelectorAll('[data-days]').forEach((x) => {
            x.setAttribute('aria-pressed', String(x === b));
        });
        load();
    });
});

// ── 取資料 ───────────────────────────────────────────────────────────
function authHeaders() {
    // ZH: ⚠ 鍵名必須與 v1／v1.5／其他 v2 畫面一致（'ai_hud_token'）。
    const t = sessionStorage.getItem('ai_hud_token') || localStorage.getItem('ai_hud_token');
    return t ? { Authorization: 'Bearer ' + t } : {};
}

function tok(name) {
    // ZH: 圖表色一律從 token 讀，元件不得自帶色值（v2 的規矩）。
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

const num = (v) => Number(v || 0).toLocaleString();

function showMsg(text) {
    $('msg').textContent = text;
    $('msg').hidden = false;
    $('content').hidden = true;
}

// ── 層級 1：額度（與首頁同一套語彙）────────────────────────────────────
function renderBalance(acc) {
    const pts = acc && acc.points;
    if (pts == null) {
        $('bal-value').textContent = '—';
        $('bal-unit').hidden = true;
        $('bal-meta').textContent = '暫時取不到額度，不影響以下統計';
        return;
    }
    $('bal-value').textContent = num(pts);
    $('bal-unit').hidden = false;
    $('bal-meta').textContent = acc.expiry ? `有效至 ${acc.expiry}` : '';
}

// ── 三個數字 ─────────────────────────────────────────────────────────
function renderStats(d) {
    const s = d.summary || {};
    const peer = d.peer || {};
    const show = !!peer.show;

    const cell = (label, value, sub) => `
        <div class="stat">
            <div class="stat__label">${label}</div>
            <div class="stat__value">${num(value)}</div>
            ${sub ? `<div class="stat__sub">${sub}</div>` : ''}
        </div>`;

    // ZH: 倍率只在人均 > 0 時算 —— 除以 0 會得到 Infinity，畫面上會出現「∞×平均」。
    const ratio = (show && peer.avg_consumed > 0)
        ? (s.consumed || 0) / peer.avg_consumed : null;

    $('stats').innerHTML =
        cell('消耗點數', s.consumed,
             show ? `全體人均 ${num(peer.avg_consumed)}`
                    + (ratio != null ? ` · ${ratio.toFixed(1)}× 平均` : '') : '')
        + cell('AI 使用次數', s.uses, show ? `全體人均 ${num(peer.avg_uses)}` : '')
        + cell('登入次數', s.logins, '');

    const np = $('no-peer');
    np.hidden = show;
    if (!show) {
        np.textContent = '目前使用者樣本太少，暫不顯示全體人均對照——'
            + '樣本太小時「人均」會反推出特定個人。你自己的數字不受影響。';
    }
}

// ── 圖表 ─────────────────────────────────────────────────────────────
function destroyCharts() {
    Object.values(charts).forEach((c) => c && c.destroy());
    charts = { trend: null, models: null };
}

function drawCharts(d) {
    if (typeof Chart === 'undefined') return;     // 圖表庫沒載到 → 數字照常顯示
    destroyCharts();

    const me = tok('--chart-me');
    const pr = tok('--chart-peer');
    const grid = { color: tok('--chart-grid') };
    const txt = tok('--text');
    const show = !!(d.peer && d.peer.show);
    const base = {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { labels: { color: txt, boxWidth: 10, font: { size: 11 } } } },
    };

    // 趨勢：我＝實線；全體人均＝虛線（樣本足夠時才有）
    const series = d.series || [];
    const ds = [{
        label: '我', data: series.map((x) => x.consumed),
        borderColor: me, backgroundColor: me + '22',
        fill: true, tension: 0.25, pointRadius: 0, borderWidth: 2,
    }];
    if (show) ds.push({
        label: '全體人均', data: series.map((x) => x.peer_avg),
        borderColor: pr, borderDash: [5, 4], borderWidth: 2,
        fill: false, tension: 0.25, pointRadius: 0,
    });
    charts.trend = new Chart($('trend').getContext('2d'), {
        type: 'line',
        data: { labels: series.map((x) => x.date), datasets: ds },
        options: { ...base, scales: {
            x: { ticks: { color: txt, font: { size: 10 }, maxTicksLimit: 6 }, grid },
            y: { ticks: { color: txt, font: { size: 10 } }, grid, beginAtZero: true } } },
    });

    // 模型別：有對照時比佔比 %，否則直接看點數
    const all = d.models || [];
    const cap = show ? 5 : 8;
    const mdl = all.slice(0, cap);
    const mds = show
        ? [{ label: '我的佔比 %', data: mdl.map((m) => m.share), backgroundColor: me, borderRadius: 3 },
           { label: '全體佔比 %', data: mdl.map((m) => m.peer_share), backgroundColor: pr, borderRadius: 3 }]
        : [{ label: '消耗點數', data: mdl.map((m) => m.points), backgroundColor: me, borderRadius: 3 }];

    charts.models = new Chart($('models').getContext('2d'), {
        type: 'bar',
        data: { labels: mdl.map((m) => m.display_name || m.model), datasets: mds },
        options: { ...base, indexAxis: 'y', scales: {
            x: { ticks: { color: txt, font: { size: 10 } }, grid, beginAtZero: true },
            // ZH: **關掉 autoSkip**（v1.5 已踩過）：列數一多 Chart.js 會砍掉一半標籤，
            //     變成「有長條卻不知道是哪個模型」。
            y: { ticks: { color: txt, font: { size: 10 }, autoSkip: false }, grid } } },
    });

    // 過多狀態：明講截斷了幾個。v1.5 是靜默取前 N —— 那讓人以為自己只用過這幾個。
    const more = $('models-more');
    more.hidden = all.length <= cap;
    if (!more.hidden) more.textContent = `另有 ${all.length - cap} 個模型未列出（依消耗排序取前 ${cap}）。`;
}

// ── 載入 ─────────────────────────────────────────────────────────────
async function load() {
    $('msg').hidden = true;
    if (FORCED === 'loading') return;                     // 停在骨架，供檢視

    try {
        let d;
        if (FORCED) {
            d = mock(FORCED);
        } else {
            const r = await fetch(`${API}/external-ai/my-consumption?days=${DAYS}`,
                                  { headers: { Accept: 'application/json', ...authHeaders() } });
            if (!r.ok) throw new Error(`HTTP ${r.status}`);
            d = await r.json();
        }

        renderBalance(d.account);

        if (!d.bound) {
            return showMsg('你的 AI 帳號還沒綁定，所以還沒有使用紀錄。'
                + '第一次前往 MYAI 使用後，這裡就會有資料。');
        }
        const s = d.summary || {};
        if (!(s.uses > 0) && !(s.logins > 0)) {
            return showMsg(DAYS === 0
                ? '目前還沒有任何使用紀錄。'
                : `近 ${DAYS} 天沒有使用紀錄。可以切到「全部」看看更早的。`);
        }

        LAST = d;
        $('content').hidden = false;
        renderStats(d);
        drawCharts(d);
    } catch (e) {
        // ZH: 額度區照常顯示（部分失敗不整頁死，與首頁同一條規則）。
        renderBalance(null);
        showMsg(`暫時取不到使用紀錄（${e.message || e}）。可以重新整理再試一次。`);
    }
}

// ── 假資料：供四狀態檢視 ──────────────────────────────────────────────
function mock(kind) {
    const days = 14;
    const series = Array.from({ length: days }, (_, i) => ({
        date: `08/${String(i + 1).padStart(2, '0')}`,
        consumed: Math.round(200 + 150 * Math.sin(i / 2)),
        peer_avg: 180,
    }));
    const models = ['gpt-4o', 'claude', 'gemini', 'llama', 'qwen', 'mistral', 'phi', 'gemma', 'yi', 'glm']
        .map((m, i) => ({ model: m, display_name: m, points: 900 - i * 80,
                          count: 40 - i * 3, share: 30 - i * 3, peer_share: 25 - i * 2 }));
    const base = { bound: true, account: { points: 4820, expiry: '2026-12-31' },
                   summary: { consumed: 3180, uses: 214, logins: 37 },
                   peer: { show: true, avg_consumed: 1900, avg_uses: 120 },
                   series, models };
    if (kind === 'error') throw new Error('強制錯誤狀態');
    if (kind === 'unbound') return { ...base, bound: false, account: {} };
    if (kind === 'empty') return { ...base, summary: { consumed: 0, uses: 0, logins: 0 } };
    if (kind === 'nopeer') return { ...base, peer: { show: false } };
    if (kind === 'overflow') return base;                 // models 有 10 個，會截斷
    return base;
}

// ── 啟動 ─────────────────────────────────────────────────────────────
function requireLogin() {
    const t = sessionStorage.getItem('ai_hud_token') || localStorage.getItem('ai_hud_token');
    if (t || FORCED) return true;
    location.replace('login.html');
    return false;
}
if (requireLogin()) load();
