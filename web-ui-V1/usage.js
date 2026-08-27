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

// ZH: 色系切換已集中到 prefs.js（跟帳號走）。
//     原本九個頁面各寫一份，**只有 app.js 那份會存與還原**——
//     於是「有些頁面換了顏色，其他頁面還沒變」。同一條規則不要有第二份實作。
//     ⚠ 但**圖表仍要自己重繪**：Chart.js 把顏色烤進 dataset，
//     改 CSS 變數不會讓已經畫好的圖跟著變。初次套用時 LAST 還是 null，所以無害。
document.addEventListener('prefs:applied', () => { if (LAST) drawCharts(LAST); });

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
// ZH: v3.8 #9 —— 這一頁在此之前**完全沒有低額度提示**。
//     使用者是「看著首頁的警示」點進來的，結果進來反而看不到警示，
//     只剩一個中性的數字 —— 等於警示在他最想弄清楚的那一步消失了。
// ZH: bal 可能是 null（那支 API 掛了）→ 只是不畫提示，額度數字照常顯示。
function renderBalance(acc, bal) {
    const card = document.querySelector('.primary-card');
    const pts = acc && acc.points;
    if (pts == null) {
        $('bal-value').textContent = '—';
        $('bal-unit').hidden = true;
        $('bal-meta').textContent = T('usage_bal_fail', '暫時取不到額度，不影響以下統計');
        if (card) card.dataset.low = '0';
        return;
    }
    $('bal-value').textContent = num(pts);
    $('bal-unit').hidden = false;

    // ZH: 狀態一律由後端算（crud.myai_balance_state），前端不自己比門檻 ——
    //     首頁、這一頁、寄出去的信共用同一份規則，才不會三個地方講不同的話。
    const stage = bal ? (bal.state || (bal.below ? 'low' : 'ok')) : 'ok';
    if (card) card.dataset.low = stage === 'empty' ? '2' : stage === 'low' ? '1' : '0';

    const parts = [];
    if (stage === 'empty') {
        parts.push(T('idx_no_balance', '額度已用完'));
    } else if (stage === 'low') {
        parts.push(T('idx_low_balance', '額度偏低（低於 {n}）')
            .replace('{n}', ((bal && bal.threshold) || 0).toLocaleString('en-US')));
    }
    if (stage !== 'ok' && bal && bal.apply_guide_url) {
        const guide = window.Chrome.safeUrl(bal.apply_guide_url);
        if (guide) {
            parts.push(`<a href="${guide}" target="_blank" rel="noopener noreferrer">`
                       + `${T('idx_apply_more', '如何申請額度')}</a>`);
        }
    }
    if (acc.expiry) parts.push(T('usage_valid_until', '有效至 {d}').replace('{d}', acc.expiry));
    // ZH: 這裡改用 innerHTML 是因為要放連結；除了 safeUrl 過的網址之外，
    //     其餘都是字典裡的固定字串與數字，沒有資料庫來的自由文字。
    $('bal-meta').innerHTML = parts.join(' · ');
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
        cell(T('usage_consumed', '消耗點數'), s.consumed,
             show ? T('usage_peer_avg', '全體人均 {n}').replace('{n}', num(peer.avg_consumed))
                    + (ratio != null ? ` · ${ratio.toFixed(1)}× ${T('usage_avg', '平均')}` : '') : '')
        + cell(T('usage_uses', 'AI 使用次數'), s.uses,
               show ? T('usage_peer_avg', '全體人均 {n}').replace('{n}', num(peer.avg_uses)) : '')
        + cell(T('usage_logins', '登入次數'), s.logins, '');

    const np = $('no-peer');
    np.hidden = show;
    if (!show) {
        np.textContent = T('usage_small_sample',
            '目前使用者樣本太少，暫不顯示全體人均對照——樣本太小時「人均」會反推出特定個人。你自己的數字不受影響。');
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
        label: T('usage_me', '我'), data: series.map((x) => x.consumed),
        borderColor: me, backgroundColor: me + '22',
        fill: true, tension: 0.25, pointRadius: 0, borderWidth: 2,
    }];
    if (show) ds.push({
        label: T('usage_peer', '全體人均'), data: series.map((x) => x.peer_avg),
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
        ? [{ label: T('usage_my_share', '我的佔比 %'), data: mdl.map((m) => m.share), backgroundColor: me, borderRadius: 3 },
           { label: T('usage_peer_share', '全體佔比 %'), data: mdl.map((m) => m.peer_share), backgroundColor: pr, borderRadius: 3 }]
        : [{ label: T('usage_consumed', '消耗點數'), data: mdl.map((m) => m.points), backgroundColor: me, borderRadius: 3 }];

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
    if (!more.hidden) more.textContent = T('usage_more_models', '另有 {n} 個模型未列出（依消耗排序取前 {c}）。')
        .replace('{n}', all.length - cap).replace('{c}', cap);
}

// ── 載入 ─────────────────────────────────────────────────────────────
async function load() {
    $('msg').hidden = true;
    if (FORCED === 'loading') return;                     // 停在骨架，供檢視

    try {
        let d;
        let bal = null;
        if (FORCED) {
            d = mock(FORCED);
            bal = mockBalance(FORCED, d);
            // ZH: 讓卡片上的數字跟狀態對得起來 —— 顯示 4820 卻寫「額度偏低」,
            //     檢視的人會以為是判斷寫錯了,而不是假資料沒對齊。
            if (bal.state !== 'ok') d.account = { ...d.account, points: bal.points };
        } else {
            const r = await fetch(`${API}/external-ai/my-consumption?days=${DAYS}`,
                                  { headers: { Accept: 'application/json', ...authHeaders() } });
            if (!r.ok) throw new Error(`HTTP ${r.status}`);
            d = await r.json();
            // ZH: 額度狀態另外拿（消耗那支不含門檻與申請連結）。
            //     🔴 用 catch 吞掉失敗是刻意的：這一頁的本體是使用紀錄，
            //     提示只是附加 —— 提示掛了不該讓整頁變成錯誤畫面。
            bal = await fetch(`${API}/external-ai/my-balance`,
                              { headers: { Accept: 'application/json', ...authHeaders() } })
                .then((x) => (x.ok ? x.json() : null))
                .catch(() => null);
        }

        renderBalance(d.account, bal);

        if (!d.bound) {
            return showMsg(T('usage_unbound', '你的 AI 帳號還沒綁定，所以還沒有使用紀錄。第一次前往 MYAI 使用後，這裡就會有資料。'));
        }
        const s = d.summary || {};
        if (!(s.uses > 0) && !(s.logins > 0)) {
            return showMsg(DAYS === 0
                ? T('usage_none_ever', '目前還沒有任何使用紀錄。')
                : T('usage_none_range', '近 {d} 天沒有使用紀錄。可以切到「全部」看看更早的。').replace('{d}', DAYS));
        }

        LAST = d;
        $('content').hidden = false;
        renderStats(d);
        drawCharts(d);
    } catch (e) {
        // ZH: 額度區照常顯示（部分失敗不整頁死，與首頁同一條規則）。
        renderBalance(null, null);
        showMsg(T('usage_fail', '暫時取不到使用紀錄') + `（${e.message || e}）。`
            + T('retry_refresh', '可以重新整理再試一次。'));
    }
}

// ── 假資料：供四狀態檢視 ──────────────────────────────────────────────
// ZH: 額度狀態的假資料。`?state=lowbal` / `?state=nobal` 可以直接看到兩段提示長什麼樣 ——
//     這兩種狀態在真實環境**很難重現**（要真的把某個人的點數用到見底），
//     沒有假資料就只能靠想像，而想像不會發現顏色對比不夠。
// ZH: ⚠ 名字刻意**不叫 `empty`** —— 這一頁的 `?state=empty` 早就是
//     「沒有使用紀錄」的意思。同一個字兩種意思，看的人會以為自己看到的是另一種狀態。
function mockBalance(kind, d) {
    const pts = (d && d.account && d.account.points) || 0;
    if (kind === 'lowbal') return { points: 120, threshold: 500, state: 'low',
                                    apply_guide_url: 'https://example.com/apply' };
    if (kind === 'nobal')  return { points: 0, threshold: 500, state: 'empty',
                                    apply_guide_url: 'https://example.com/apply' };
    return { points: pts, threshold: 500, state: 'ok', apply_guide_url: null };
}
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


// ── 語言切換時重繪 ───────────────────────────────────────────────────
// ZH: prefs.js 的字典掃描只換得掉 `data-i18n` 元素；本頁 JS 產生的內容要自己重跑。
//     只在語言**改變**時觸發（不是每次套用），所以不會在載入時多跑一次。
document.addEventListener('prefs:langchanged', () => { load(); });


/* ── 營運設定的補充說明（v3.8）──────────────────────────────────────
 * ZH: 這個數字是**管理者可以在營運設定裡改的**，所以不能寫死在 HTML ——
 *     寫死的話管理者調過之後，畫面上就是一個錯的數字，而且不會有人回報。
 *     值一律現取（Chrome.publicSettings 會在同一頁內快取）。
 *
 * ZH: 讀不到就**維持隱藏**，不要顯示「—」或 0。
 *     這是一句補充說明，缺了不影響這一頁本來要做的事；
 *     顯示一個假的 0 反而會被當成真的。
 * ------------------------------------------------------------------ */
function renderResetNote(s) {
    const el = $('reset-note');
    if (!el) return;
    const v = s && s['token_reset_day'];
    if (v == null) { el.hidden = true; return; }
    el.textContent = T('usage_reset_note', '額度每月 {d} 號重置。').replace('{d}', v);
    el.hidden = false;
}

let PUB_SETTINGS = null;
Chrome.publicSettings().then((s) => { PUB_SETTINGS = s; renderResetNote(s); });
// ZH: 文案是 JS 組出來的，沒有 data-i18n，字典掃描換不掉它 —— 語言改變時要自己重畫。
document.addEventListener('prefs:langchanged', () => renderResetNote(PUB_SETTINGS));
