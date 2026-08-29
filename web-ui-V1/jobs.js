/* ==========================================================================
 * [畫面: 我的訓練] — 使用者在這裡要完成：找回自己送出過的那張單
 *
 * ZH: 這一頁存在的理由：**送出之後關掉分頁就再也找不回來。**
 *     訓練通常要幾分鐘到幾十分鐘，沒有人會一直開著那一頁等——
 *     而在這之前，關掉就等於看不到進度、拿不到模型。
 *
 * ZH: 刻意**不在列表裡顯示正確率**：那要對每一列各打一次 `/jobs/{id}`
 *     （列表端點不含 metrics）。十列就是十個請求，只為了一個數字。
 *     點進去看詳細比較誠實，也比較快。
 * ========================================================================== */
const API = '/api/v1';

const $ = (id) => document.getElementById(id);

function authHeaders() {
    const t = sessionStorage.getItem('ai_hud_token') || localStorage.getItem('ai_hud_token');
    return t ? { Authorization: 'Bearer ' + t } : {};
}

function currentLang() {
    try {
        return (window.Prefs && Prefs.get && Prefs.get().ui_lang) || 'zh';
    } catch {
        return 'zh';
    }
}

function human(bytes) {
    if (bytes >= 1024 ** 3) return (bytes / 1024 ** 3).toFixed(1) + ' GB';
    if (bytes >= 1024 ** 2) return (bytes / 1024 ** 2).toFixed(1) + ' MB';
    return Math.max(1, Math.round(bytes / 1024)) + ' KB';
}

function esc(s) {
    return String(s).replace(/[&<>"']/g, (c) =>
        ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

// ZH: 還在跑的狀態。**這份清單是判準**——別處要用同一組值請引用這裡，
//     不要各自寫一份（那會出現「列表說跑完了、詳細頁說還在跑」）。
const ACTIVE = ['pending', 'queued', 'running'];

const STATE_TEXT = () => ({
    pending:   T('tr_queued', '排隊中…'),
    queued:    T('tr_queued', '排隊中…'),
    running:   T('tr_training', '訓練中…'),
    completed: T('tr_done', '完成'),
    failed:    T('tr_failed', '失敗'),
    cancelled: T('tr_cancelled', '已取消'),
});

/* ── 排隊說明（v3.9，會議交辦 #8）──────────────────────────────────
 * ZH: 只在**真的在排隊**時說話。常駐顯示 GPU 規格對學生沒有決策價值，
 *     而且會變成一個要維護的假資訊來源。
 *
 * ZH: 兩件事分開講：
 *     · 前面還有幾個 —— 只在前面真的有人時才出現（position > 1）。
 *       排第一個卻寫「前面還有 0 個」是廢話，還會讓人以為系統壞了。
 *     · 為什麼還沒開始 —— 只給排第一個的人。前面有人的話原因很明顯。
 *
 * ZH: 🔴 桃園目前只有一張卡，而程式實驗室會**獨佔**它。所以
 *     「有人開著實驗室」是這裡最常見的原因 —— 講清楚，使用者才知道
 *     是要等十分鐘還是去問管理員，而不是以為自己送單失敗了。
 */
const WAIT_REASON = () => ({
    lab:     T('jl_wait_lab', '有人正在使用程式實驗室的 GPU'),
    job:     T('jl_wait_job', '有其他訓練正在跑'),
    closed:  T('jl_wait_closed', '目前不在開放時段'),
    no_node: T('jl_wait_no_node', '目前沒有機器在線'),
});

function queueNote(j) {
    if (j.status !== 'pending' && j.status !== 'queued') return '';
    const parts = [];
    if (j.queue_position > 1) {
        parts.push(T('jl_queue_ahead', '前面還有 {n} 個')
            .replace('{n}', j.queue_position - 1));
    }
    const why = WAIT_REASON()[j.wait_reason];
    if (why) parts.push(why);
    return parts.length ? `　（${parts.join('，')}）` : '';
}

let filter = '';
let polling = null;

// ── 載入 ─────────────────────────────────────────────────────────────
async function load() {
    try {
        const r = await fetch(`${API}/jobs?limit=50`, { headers: authHeaders() });
        if (r.status === 401 || r.status === 403) return signedOut();
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        render(((await r.json()).jobs) || []);
    } catch {
        // ZH: 讀不到就說讀不到。**不要顯示空列表**——那看起來像「你沒有送過任何訓練」，
        //     而使用者會以為他的東西不見了。
        $('list').innerHTML =
            `<p class="inline-error">${esc(T('jl_load_fail', '暫時讀不到你的訓練紀錄。這不代表它們不見了，稍後重新整理即可。'))}</p>`;
        stopPolling();
    }
}

function signedOut() {
    $('list').innerHTML =
        `<p class="inline-error">${esc(T('tr_signed_out', '你的登入已經過期，請重新登入後再試一次。'))}` +
        ` <a class="btn btn--minor" href="login.html">${esc(T('btn_login', '登入'))}</a></p>`;
    stopPolling();
}

function render(all) {
    const jobs = filter === 'active' ? all.filter((j) => ACTIVE.includes(j.status)) : all;

    if (!jobs.length) {
        $('list').innerHTML = `<p class="footnote">${esc(
            filter === 'active' ? T('jl_none_active', '目前沒有正在跑的訓練。')
                                : T('jl_empty', '還沒有送出過任何訓練。'))}</p>`;
    } else {
        $('list').innerHTML = jobs.map(row).join('');
        $('list').querySelectorAll('[data-dl]').forEach((b) =>
            b.addEventListener('click', () => downloadModel(b.dataset.dl, b)));
    }

    // ZH: 只有「還有東西在跑」時才輪詢。全部跑完還每 5 秒打一次，
    //     是白白讓伺服器與電池付錢。
    if (all.some((j) => ACTIVE.includes(j.status))) startPolling();
    else stopPolling();
}

function row(j) {
    const active = ACTIVE.includes(j.status);
    const when = TW.when(j.completed_at || j.started_at || j.created_at) || '';
    return `
    <div class="entry">
        <div class="entry__title">${esc(j.job_name || '—')}</div>
        <div class="entry__desc">
            ${esc(STATE_TEXT()[j.status] || j.status)}
            ${esc(queueNote(j))}
            ${active && j.progress ? `　${Math.round(j.progress)}%` : ''}
            ${when ? `　${esc(when)}` : ''}
            ${j.status === 'failed' && j.error_message
                ? `<br><span class="inline-error">${esc(clean(j.error_message))}</span>` : ''}
        </div>
        <div class="ds__actions">
            <a class="btn btn--minor" href="train.html?job=${encodeURIComponent(j.job_id)}">
                ${esc(T('jl_open', '看進度與結果'))}</a>
            ${j.has_model ? `<button class="btn btn--minor" type="button" data-dl="${esc(j.job_id)}">
                ${esc(T('tr_download', '下載模型檔'))}${j.model_bytes ? '（' + human(j.model_bytes) + '）' : ''}
            </button>` : ''}
        </div>
    </div>`;
}

// ── 輪詢（只在有東西在跑時）───────────────────────────────────────────
function startPolling() {
    if (!polling) polling = setInterval(load, 5000);
}

function stopPolling() {
    if (polling) { clearInterval(polling); polling = null; }
}

// ZH: 分頁切到背景時停掉輪詢 —— 沒有人在看的時候不需要一直問。
document.addEventListener('visibilitychange', () => {
    if (document.hidden) stopPolling();
    else load();
});

// ── 下載（與 train.js 同一個道理：純連結不會帶 Authorization header）──
async function downloadModel(jobId, btn) {
    const original = btn.textContent;
    btn.disabled = true;
    btn.textContent = T('tr_downloading', '下載中…');
    try {
        const r = await fetch(`${API}/jobs/${encodeURIComponent(jobId)}/model`,
                              { headers: authHeaders() });
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        const cd = r.headers.get('content-disposition') || '';
        let name = 'model.pt';
        const star = cd.match(/filename\*=UTF-8''([^;]+)/i);
        const plain = cd.match(/filename="([^"]+)"/i);
        if (star) { try { name = decodeURIComponent(star[1]); } catch { /* 用下面那個 */ } }
        else if (plain) { name = plain[1]; }

        const url = URL.createObjectURL(await r.blob());
        const a = document.createElement('a');
        a.href = url;
        a.download = name;
        document.body.appendChild(a);
        a.click();
        a.remove();
        setTimeout(() => URL.revokeObjectURL(url), 60000);
        btn.textContent = original;
    } catch {
        btn.textContent = T('tr_download_fail', '下載失敗，請再試一次');
    } finally {
        btn.disabled = false;
    }
}

// ZH: 後端的雙語 detail 只留使用者當下的語言。
function clean(msg) {
    const s = String(msg || '');
    const m = s.match(/ZH:\s*(.*?)\s*\|\s*EN:\s*(.*)$/s);
    if (!m) return s;
    return currentLang() === 'en' ? m[2] : m[1];
}

// ── 篩選 ─────────────────────────────────────────────────────────────
document.querySelectorAll('[data-filter]').forEach((b) =>
    b.addEventListener('click', () => {
        filter = b.dataset.filter;
        document.querySelectorAll('[data-filter]').forEach((x) =>
            x.setAttribute('aria-pressed', String(x === b)));
        load();
    }));

// ── 啟動 ─────────────────────────────────────────────────────────────
load();

document.addEventListener('prefs:langchanged', () => load());
