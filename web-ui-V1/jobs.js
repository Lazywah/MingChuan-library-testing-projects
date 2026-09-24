/* ==========================================================================
 * [畫面: 我的訓練與資料] — 使用者在這裡要完成：找回自己送出過的那張單、拿到模型、
 *                          拿回／重用／刪掉上傳過的資料
 *
 * ZH: v4.30 兩頁合一（擁有者 2026-09-24：「這兩頁沒有區別，請整合，做 Tab 也行」）。
 *     原本「我的訓練進度」與「我的資料與模型」是兩個選單項、兩頁；
 *     同一次訓練的兩端（送出時用的資料、跑完留下的模型）被拆在兩邊。
 *     現在一頁兩個分頁：
 *       · 訓練與模型 —— 每一張單：進度、結果、下載模型（帶保留到哪一天）、取消
 *       · 上傳的資料 —— 每一包：再訓練一次、下載、刪除；配額條在最上面
 *     ⚠ 資料那一頁原本的三顆鈕**一顆都沒少**（擁有者特別交代「刪除之類的也要加回去」）。
 *
 * ZH: 這一頁存在的理由：**送出之後關掉分頁就再也找不回來。**
 *     訓練通常要幾分鐘到幾十分鐘，沒有人會一直開著那一頁等——
 *     而在這之前，關掉就等於看不到進度、拿不到模型。
 *
 * ZH: 刻意**不在列表裡顯示正確率**：那要對每一列各打一次 `/jobs/{id}`
 *     （列表端點不含 metrics）。十列就是十個請求，只為了一個數字。
 *     點進去看詳細比較誠實，也比較快。
 *
 * ZH: 🔴 資料那一區**不是方便功能**。每人 2 GB 配額，而在這之前沒有任何刪除的方法——
 *     傳滿之後上傳一律 413，而使用者什麼都做不了。刪除不可逆，所以先 confirm、
 *     還有任務在用時鈕直接停用並說明原因（不要等他按下去才回 409）。
 * ========================================================================== */
const API = '/api/v1';

const $ = (id) => document.getElementById(id);

// ZH: ⚠ 鍵名必須與其他頁一致。用錯不會報錯，只會讓每個請求都 401，
//     而畫面看起來像「後端壞了」。
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

// ZH: 名稱來自使用者自己的檔名／任務名，一律逸出。
function esc(s) {
    return String(s).replace(/[&<>"']/g, (c) =>
        ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

// ZH: 後端的雙語 detail 只留使用者當下的語言，不要兩句黏在一起。
function clean(msg) {
    const s = String(msg || '');
    const m = s.match(/ZH:\s*(.*?)\s*\|\s*EN:\s*(.*)$/s);
    if (!m) return s;
    return currentLang() === 'en' ? m[2] : m[1];
}

// ZH: 後端的錯誤有兩種形狀：422 的 detail 是陣列，其餘是雙語字串。
//     直接 String() 陣列會得到 `[object Object]` —— 實測踩過。
function detailText(detail) {
    if (detail == null) return '';
    if (typeof detail === 'string') return detail;
    if (Array.isArray(detail)) {
        return detail.map((x) => x.msg || JSON.stringify(x)).join('；');
    }
    return JSON.stringify(detail);
}

function signedOutInto(id) {
    $(id).innerHTML =
        `<p class="inline-error">${esc(T('tr_signed_out', '你的登入已經過期，請重新登入後再試一次。'))}` +
        ` <a class="btn btn--minor" href="login.html">${esc(T('btn_login', '登入'))}</a></p>`;
}

// ZH: 下載一律走 chrome.js 的 Chrome.download（唯一真相，v4.24 收斂的那一份）。
//     這裡只管按鈕的狀態 —— 那是這一頁的事。
async function downloadFile(path, fallbackName, btn) {
    const original = btn.textContent;
    btn.disabled = true;
    btn.textContent = T('tr_downloading', '下載中…');
    try {
        await Chrome.download(path, fallbackName);
        btn.textContent = original;
    } catch {
        btn.textContent = T('tr_download_fail', '下載失敗，請再試一次');
    } finally {
        btn.disabled = false;
    }
}

// ══════════════════════════════════════════════════════════════════════
// ZH: 分頁（v4.30）
// ══════════════════════════════════════════════════════════════════════
// ZH: 網址帶 `?tab=data` 就直接開資料那一頁 —— 「傳不上去了」的人是從
//     上傳頁被帶過來的，不該再多按一下。其餘情況預設訓練。
const TABS = ['train', 'data'];
let currentTab = 'train';

function showTab(name, pushUrl) {
    if (!TABS.includes(name)) name = 'train';
    currentTab = name;
    document.querySelectorAll('#tabs [data-tab]').forEach((b) => {
        const on = b.dataset.tab === name;
        b.setAttribute('aria-pressed', String(on));
        b.setAttribute('aria-selected', String(on));
    });
    $('tab-train').hidden = name !== 'train';
    $('tab-data').hidden = name !== 'data';
    if (pushUrl) {
        const u = new URL(location.href);
        if (name === 'train') u.searchParams.delete('tab'); else u.searchParams.set('tab', name);
        history.replaceState(null, '', u);
    }
    // ZH: 資料那一頁第一次打開才去讀（多數人只看訓練）；之後每次切過去都重讀，
    //     因為配額可能在別的分頁（上傳頁）變了。
    if (name === 'data') loadDatasets();
}

document.querySelectorAll('#tabs [data-tab]').forEach((b) =>
    b.addEventListener('click', () => showTab(b.dataset.tab, true)));

// ══════════════════════════════════════════════════════════════════════
// ZH: 分頁一 · 訓練與模型
// ══════════════════════════════════════════════════════════════════════

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

async function load() {
    try {
        const r = await fetch(`${API}/jobs?limit=50`, { headers: authHeaders() });
        if (r.status === 401 || r.status === 403) { signedOutInto('list'); stopPolling(); return; }
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        const body = await r.json();
        renderRule(body.retention);
        render(body.jobs || []);
    } catch {
        // ZH: 讀不到就說讀不到。**不要顯示空列表**——那看起來像「你沒有送過任何訓練」，
        //     而使用者會以為他的東西不見了。
        $('list').innerHTML =
            `<p class="inline-error">${esc(T('jl_load_fail', '暫時讀不到你的訓練紀錄。這不代表它們不見了，稍後重新整理即可。'))}</p>`;
        stopPolling();
    }
}

// ZH: 🔴 模型的保留規則（每人幾個、幾天後清）**跟著列表從後端來**，不寫死在文案裡。
//     那幾個值是環境變數，改了之後寫死的數字就會說謊，而且沒有守衛抓得到。
//     在此之前這三條規則畫面上一條都沒講，過期時下載鈕只是安靜消失。
function renderRule(ret) {
    const el = $('models-rule');
    if (ret && ret.keep && ret.ttl_days) {
        el.textContent = T('ds_models_rule',
            '每人保留最近 {k} 個，跑完 {d} 天後自動清掉；不佔「上傳的資料」那邊的配額。')
            .replace('{k}', ret.keep).replace('{d}', ret.ttl_days);
        el.hidden = false;
    } else {
        el.hidden = true;
    }
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
            b.addEventListener('click', () =>
                downloadFile(`/jobs/${encodeURIComponent(b.dataset.dl)}/model`, 'model.pt', b)));
        $('list').querySelectorAll('[data-cancel]').forEach((b) =>
            b.addEventListener('click', () => cancelJob(b.dataset.cancel, b)));
    }

    // ZH: 只有「還有東西在跑」時才輪詢。全部跑完還每 5 秒打一次，
    //     是白白讓伺服器與電池付錢。
    if (all.some((j) => ACTIVE.includes(j.status))) startPolling();
    else stopPolling();
}

function row(j) {
    const active = ACTIVE.includes(j.status);
    const when = TW.when(j.completed_at || j.started_at || j.created_at) || '';
    // ZH: 模型三種狀態各講各的：還在（保留到哪一天）／清掉了（哪一天清的）／從來沒有（不講）。
    //     「清掉了」與「從來沒有」靠 model_purged_at 分——沒有它兩者在資料上長得一樣。
    let keep = '';
    if (j.has_model && j.model_expires_at) {
        keep = T('ds_model_until', '保留到 {d}').replace('{d}', TW.date(j.model_expires_at) || '—');
    } else if (!j.has_model && j.model_purged_at) {
        keep = T('jl_model_gone', '模型已過保留期（{d} 清掉）').replace('{d}', TW.date(j.model_purged_at) || '—');
    }
    return `
    <div class="entry">
        <div class="entry__title">${esc(j.job_name || '—')}</div>
        <div class="entry__desc">
            ${esc(STATE_TEXT()[j.status] || j.status)}
            ${esc(queueNote(j))}
            ${active && j.progress ? `　${Math.round(j.progress)}%` : ''}
            ${when ? `　${esc(when)}` : ''}
            ${keep ? `　${esc(keep)}` : ''}
            ${j.status === 'failed' && j.error_message
                ? `<br><span class="inline-error">${esc(clean(j.error_message))}</span>` : ''}
        </div>
        <div class="ds__actions">
            <a class="btn btn--minor" href="train.html?job=${encodeURIComponent(j.job_id)}">
                ${esc(T('jl_open', '看進度與結果'))}</a>
            ${j.has_model ? `<button class="btn btn--minor" type="button" data-dl="${esc(j.job_id)}">
                ${esc(T('tr_download', '下載模型檔'))}${j.model_bytes ? '（' + human(j.model_bytes) + '）' : ''}
            </button>` : ''}
            ${active ? `<button class="btn btn--minor" type="button" data-cancel="${esc(j.job_id)}">
                ${esc(T('jl_cancel', '取消這個訓練'))}</button>` : ''}
        </div>
    </div>`;
}

// ── 取消（v4.19）─────────────────────────────────────────────────────
// ZH: 後端從 v4.14 起排隊中**與訓練中**都可以取消，但畫面上一直沒有按鈕 ——
//     送錯的單只能看著它跑完。這裡補上。
// ZH: 先問一次再送：取消不能復原，而這顆按鈕就在「看進度」旁邊，誤點很容易。
//     用瀏覽器原生的 confirm 就夠了，不另做對話框。
// ZH: 回 200 的意思是「已受理」，容器要幾秒後才真的停 —— 所以按完先把狀態
//     寫成「取消中…」，等下一輪 load() 拿到 cancelled 再換成正式文字。
async function cancelJob(jobId, btn) {
    if (!window.confirm(T('jl_cancel_confirm', '確定要取消這個訓練嗎？取消之後不能恢復。'))) return;
    btn.disabled = true;
    btn.textContent = T('jl_cancelling', '取消中…');
    try {
        const r = await fetch(`${API}/jobs/${encodeURIComponent(jobId)}`,
                              { method: 'DELETE', headers: authHeaders() });
        if (r.status === 401 || r.status === 403) { signedOutInto('list'); stopPolling(); return; }
        const body = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(clean(body.detail) || `HTTP ${r.status}`);
        load();
    } catch (e) {
        btn.disabled = false;
        btn.textContent = T('jl_cancel_fail', '取消失敗，請再試一次') + (e.message ? `（${e.message}）` : '');
    }
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

// ── 篩選 ─────────────────────────────────────────────────────────────
document.querySelectorAll('[data-filter]').forEach((b) =>
    b.addEventListener('click', () => {
        filter = b.dataset.filter;
        document.querySelectorAll('[data-filter]').forEach((x) =>
            x.setAttribute('aria-pressed', String(x === b)));
        load();
    }));

// ══════════════════════════════════════════════════════════════════════
// ZH: 分頁二 · 上傳的資料（原 datasets.js，v4.30 併進來；行為一個都沒少）
// ══════════════════════════════════════════════════════════════════════
let datasets = [];

async function loadDatasets() {
    try {
        const r = await fetch(`${API}/datasets`, { headers: authHeaders() });
        if (r.status === 401 || r.status === 403) { signedOutInto('ds-list'); $('quota').textContent = ''; return; }
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        const body = await r.json();
        datasets = body.datasets || [];
        renderQuota(body.used_bytes, body.quota_bytes);
        renderDatasets();
    } catch (e) {
        // ZH: 取不到就說取不到。**不要顯示一個空列表**——那看起來像「你沒有資料集」，
        //     而使用者會因此以為他的東西不見了。
        $('ds-list').innerHTML =
            `<p class="inline-error">${esc(T('ds_load_fail', '暫時讀不到你的資料集。這不代表它們不見了，稍後重新整理即可。'))}</p>`;
        $('quota').textContent = T('ds_quota_unknown', '用量：暫時讀不到');
    }
}

function renderQuota(used, quota) {
    const pct = quota ? Math.min(100, (used / quota) * 100) : 0;
    $('quota-bar').style.width = `${pct}%`;
    $('quota-wrap').setAttribute('aria-valuenow', String(Math.round(pct)));
    $('quota').textContent =
        T('ds_quota', '已用 {u} / 上限 {q}').replace('{u}', human(used)).replace('{q}', human(quota));
    // ZH: 快滿了要看得出來——會來這一區的人多半就是為了這件事。
    $('quota-wrap').classList.toggle('bar--warn', pct >= 85);
}

function renderDatasets() {
    if (!datasets.length) {
        $('ds-list').innerHTML =
            `<p class="footnote">${esc(T('ds_empty', '還沒有上傳過任何資料集。'))}</p>`;
        return;
    }
    $('ds-list').innerHTML = datasets.map((d) => {
        const busy = d.in_use_by_jobs > 0;
        return `
        <div class="entry">
            <div class="entry__title">${esc(d.name)}</div>
            <div class="entry__desc">${esc(human(d.size_bytes))}　${esc(TW.when(d.created_at) || '')}</div>
            <div class="ds__actions">
                <a class="btn btn--minor" href="train.html?dataset=${encodeURIComponent(d.id)}">
                    ${esc(T('ds_reuse', '再訓練一次'))}</a>
                <button class="btn btn--minor" type="button" data-dlds="${esc(d.id)}">
                    ${esc(T('ds_download', '下載'))}</button>
                <button class="btn btn--minor" type="button" data-del="${esc(d.id)}"
                        ${busy ? 'disabled' : ''}>
                    ${esc(T('ds_delete', '刪除'))}</button>
                ${busy ? `<span class="footnote">${esc(
                    T('ds_in_use', '有 {n} 個任務正在用，跑完才能刪').replace('{n}', d.in_use_by_jobs))}</span>` : ''}
            </div>
        </div>`;
    }).join('');

    $('ds-list').querySelectorAll('[data-del]').forEach((b) =>
        b.addEventListener('click', () => removeDataset(b.dataset.del, b)));
    // ZH: 拿回自己上傳的那一包。檔名用當初的原名（後端的 Content-Disposition 帶著），這裡只是後備。
    $('ds-list').querySelectorAll('[data-dlds]').forEach((b) =>
        b.addEventListener('click', () => {
            const d = datasets.find((x) => x.id === b.dataset.dlds);
            downloadFile(`/datasets/${encodeURIComponent(b.dataset.dlds)}/download`,
                         (d && d.name) || 'dataset.zip', b);
        }));
}

async function removeDataset(id, btn) {
    const d = datasets.find((x) => x.id === id);
    // ZH: 刪除不可逆，先問一次。訊息裡帶上名字——「你確定嗎」問的是哪一個很重要。
    if (!confirm(T('ds_confirm', '要刪掉「{n}」嗎？這個動作沒辦法復原。')
        .replace('{n}', d ? d.name : ''))) return;

    btn.disabled = true;
    const original = btn.textContent;
    btn.textContent = T('ds_deleting', '刪除中…');
    try {
        const r = await fetch(`${API}/datasets/${encodeURIComponent(id)}`,
                              { method: 'DELETE', headers: authHeaders() });
        if (r.status === 401 || r.status === 403) { signedOutInto('ds-list'); return; }
        if (!r.ok) {
            const body = await r.json().catch(() => ({}));
            throw new Error(detailText(body.detail) || `HTTP ${r.status}`);
        }
        await loadDatasets();          // ZH: 重新讀 —— 用量要跟著更新，不要自己在前端減
    } catch (e) {
        btn.disabled = false;
        btn.textContent = original;
        alert(T('ds_delete_fail', '刪不掉') + `（${clean(e.message)}）`);
    }
}

// ── 啟動 ─────────────────────────────────────────────────────────────
showTab(new URLSearchParams(location.search).get('tab') || 'train', false);
load();

// ZH: prefs.js 的字典掃描只換得掉 `data-i18n` 元素；本頁 JS 產生的內容要自己重跑。
document.addEventListener('prefs:langchanged', () => { load(); if (currentTab === 'data') loadDatasets(); });
