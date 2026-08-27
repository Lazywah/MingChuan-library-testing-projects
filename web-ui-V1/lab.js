/* ==========================================================================
 * [畫面: Lab] — 使用者在這裡要完成：把瀏覽器版 VS Code 打開來寫程式
 *
 * ZH: D3 定的行為是**同頁顯示啟動狀態 → 就緒後才開新分頁**。
 *     容器要 5–10 秒；直接開新分頁會看到空白，而空白比等待更糟——
 *     使用者分不出「還沒好」和「壞了」。
 *
 * ⚠ 新分頁能不能進得去，靠的是 **`ai_hud_token` cookie**，不是 sessionStorage。
 *   nginx 對 `/code/<uid>/` 掛 `auth_request /_lab_authz`，而後端的 get_current_user
 *   同時吃 Bearer 與該 cookie（v2.1）。**sessionStorage 帶不進新分頁**，
 *   所以登入時必須拿到 Set-Cookie（login.js 已明寫 credentials）。
 *   若 cookie 不在，新分頁會是 401 頁面而不是 VS Code —— 下面有對應的說明文案。
 *
 * 與 v1.5 的差異：v1.5 在 v2.7 改成 iframe 內嵌（為了讓小基泡泡浮在上面）。
 *   v2 依 D3 走新分頁：v2 目前沒有小基，而 IDE 需要完整視窗高度。
 *   若日後 v2 也放小基，這個決定要重新檢視。
 * ========================================================================== */
const API = '/api/v1';

// ZH: v3.6 —— 目前選中的存檔。null＝預設那一份（既有使用者的行為完全不變）。
let currentSession = null;

// ZH: 名稱來自使用者自己取的名字，一律逸出。
function esc(s) {
    return String(s).replace(/[&<>"']/g, (c) =>
        ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}
const FORCED = new URLSearchParams(location.search).get('state');
const $ = (id) => document.getElementById(id);

let POLL = null;

// ZH: 色系切換已集中到 prefs.js（跟帳號走）。
//     原本九個頁面各寫一份，**只有 app.js 那份會存與還原**——
//     於是「有些頁面換了顏色，其他頁面還沒變」。同一條規則不要有第二份實作。

function authHeaders() {
    const t = sessionStorage.getItem('ai_hud_token') || localStorage.getItem('ai_hud_token');
    return t ? { Authorization: 'Bearer ' + t } : {};
}

async function api(path, opts = {}) {
    const r = await fetch(API + path, {
        headers: { Accept: 'application/json', ...authHeaders(), ...(opts.headers || {}) },
        credentials: 'include',
        ...opts,
    });
    if (!r.ok) {
        const d = await r.json().catch(() => ({}));
        throw new Error(d.detail || `HTTP ${r.status}`);
    }
    return r.json().catch(() => ({}));
}

function setPrimary({ label, enabled }) {
    $('go').textContent = label;
    $('go').disabled = !enabled;
}

function note(text) {
    $('note').textContent = text || '';
    $('note').hidden = !text;
}

const mins = (s) => (s == null ? '—' : `${Math.floor(s / 60)}${T('unit_min', ' 分')}`);

// ── 狀態 ─────────────────────────────────────────────────────────────
function render(d) {
    const running = d.status === 'running';
    $('state').textContent = running ? T('lab_st_running', '執行中') : T('lab_st_stopped', '未啟動');
    setPrimary({ label: running ? T('lab_open', '開啟實驗室') : T('lab_start_open', '啟動並開啟實驗室'), enabled: true });
    $('stop').hidden = !running;

    $('meta').hidden = !running;
    if (running) {
        $('m-remaining').textContent = d.today_remaining_min != null
            ? `${d.today_remaining_min}${T('unit_min', ' 分')}` : '—';
        $('m-elapsed').textContent = mins(d.elapsed_seconds);
        $('m-quota').textContent = d.effective_quota_gb != null
            ? `${d.effective_quota_gb} GB` : '—';
    }

    // ZH: 注入的密鑰是「你的程式跑起來時會拿到什麼」——屬於層級 3 的事實，
    //     但沒有它使用者會以為密鑰沒生效。只在有東西時出現。
    const sec = d.injected_secrets;
    const has = Array.isArray(sec) ? sec.length : (sec && Object.keys(sec).length);
    $('secrets').hidden = !has;
    if (has) {
        const names = Array.isArray(sec) ? sec : Object.keys(sec);
        $('secrets').textContent = T('lab_env', '啟動時會注入這些環境變數：{n}').replace('{n}', names.join('、'));
    }
}

async function load() {
    if (FORCED === 'loading') return;
    try {
        const d = FORCED ? mock(FORCED) : await api('/lab/status');
        render(d);
        note('');
    } catch (e) {
        $('state').textContent = T('lab_st_unknown', '讀不到');
        setPrimary({ label: T('btn_retry', '重試'), enabled: true });
        note(T('lab_state_fail', '暫時取不到實驗室狀態') + `（${e.message || e}）。`);
    }
}

// ── 主要動作 ─────────────────────────────────────────────────────────
function openTab(url) {
    const w = window.open(url, '_blank');
    if (!w) {
        // ZH: 被瀏覽器擋下時**不可以毫無反應**（與首頁前往 MYAI 同一條規則）。
        $('note').innerHTML = T('popup_blocked', '瀏覽器擋下了新分頁。')
            + `<a href="${url}" target="_blank" rel="noopener">${T('lab_open_here', '點這裡開啟實驗室')}</a>`;
        $('note').hidden = false;
        return;
    }
    note(T('lab_opened', '已在新分頁開啟。若看到「未授權」，請回首頁重新登入一次（新分頁靠 cookie 認證，與這一頁不同）。'));
}

$('go').addEventListener('click', async () => {
    setPrimary({ label: T('lab_starting', '啟動中…'), enabled: false });
    note(T('lab_start_hint', '容器啟動大約需要 5–10 秒，好了會自動開新分頁。'));

    if (FORCED) {                       // 檢視模式：走完流程但不打後端
        setTimeout(() => { setPrimary({ label: T('lab_open', '開啟實驗室'), enabled: true });
                           note('（檢視模式：不會真的開容器）'); }, 600);
        return;
    }

    try {
        const started = await api('/lab/start', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            // ZH: v3.6 —— 要開哪一份存檔。沒選過就是 default（既有行為）。
            body: JSON.stringify(currentSession ? { session: currentSession } : {}),
        });
        // ZH: 伺服器順手關掉了別份時會回報 —— **要說出來**，
        //     使用者按下「開啟 B」而 A 被靜靜關掉會以為 A 壞了。
        if (started.switched_from) {
            note(T('ws_switched', '已切換存檔（原本那一份已關閉，檔案都保留）'));
        }
        // ZH: /lab/start 回的 url 已經是 /code/<uid>/?folder=...，直接用。
        //     但**不要立刻開** —— 先輪詢到 running 再開，否則新分頁是空白。
        await waitReady(started.url);
    } catch (e) {
        setPrimary({ label: T('lab_start_open', '啟動並開啟實驗室'), enabled: true });
        // ZH: 429 是額度/頻率限制，訊息由後端給，照實顯示不要改寫。
        note(T('lab_start_fail', '啟動失敗') + `：${e.message || e}`);
    }
});

async function waitReady(url) {
    let tries = 0;
    clearInterval(POLL);
    POLL = setInterval(async () => {
        tries++;
        try {
            const d = await api('/lab/status');
            if (d.status === 'running') {
                clearInterval(POLL);
                render(d);
                openTab(d.url || url);
                return;
            }
        } catch (e) { /* 輪詢期間的暫時失敗不打斷，由次數上限收尾 */ }
        if (tries >= 20) {                     // 20 × 1.5s = 30 秒
            clearInterval(POLL);
            setPrimary({ label: T('lab_start_open', '啟動並開啟實驗室'), enabled: true });
            note(T('lab_timeout', '等了 30 秒仍未就緒。可以再試一次，或回報問題。（容器可能仍在背景啟動，重新整理這一頁可以看到最新狀態。）'));
        }
    }, 1500);
}

// ── 層級 3：停止 ─────────────────────────────────────────────────────
$('stop').addEventListener('click', async (ev) => {
    ev.preventDefault();
    // ZH: 停止會關掉容器但**不會刪檔案**——講明才不會有人不敢按。
    if (!confirm(T('lab_stop_confirm', '要關閉實驗室嗎？容器會停止，但你的檔案都會保留。'))) return;
    try {
        if (!FORCED) await api('/lab/stop', { method: 'POST' });
        note(T('lab_stopped', '已關閉。檔案都還在，下次啟動會回到原樣。'));
        await load();
    } catch (e) {
        note(T('lab_stop_fail', '關閉失敗') + `：${e.message || e}`);
    }
});

// ── 假資料 ───────────────────────────────────────────────────────────
function mock(kind) {
    if (kind === 'error') throw new Error('強制錯誤狀態');
    if (kind === 'stopped') return { status: 'stopped', today_remaining_min: 180 };
    return {
        status: 'running', elapsed_seconds: 742, today_remaining_min: 168,
        effective_quota_gb: 20, url: '/code/demo/?folder=/home/coder/projects',
        injected_secrets: ['HF_TOKEN', 'OPENAI_API_KEY'],
    };
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


// ==========================================================================
// ZH: v3.6 多份存檔
// ==========================================================================
// ZH: 一次只開一份 —— 切換就是關掉舊的、開新的。**檔案全部保留**，
//     這件事一定要在畫面上講，不然使用者會以為舊的那份壞了。

let sessions = [];

async function loadSessions() {
    // ZH: 🔴 try 只包**拿資料**這一段，不包渲染。
    //     原本連 renderSessions 一起包住，結果渲染裡的 `TW is not defined`
    //     被吃掉、畫面顯示「暫時讀不到存檔清單」——而網路其實好好的、資料也拿到了。
    //     一個假的網路錯誤訊息會把人帶去查完全錯的方向；渲染的錯就該是紅色的例外。
    let body;
    try {
        const r = await fetch(`${API}/lab/sessions`, { headers: authHeaders() });
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        body = await r.json();
    } catch {
        // ZH: 讀不到就說讀不到 —— **不要顯示空清單**，那看起來像「你沒有存檔」。
        $('ws-list').innerHTML =
            `<p class="footnote">${esc(T('ws_load_fail', '暫時讀不到存檔清單（不影響上面的開啟）'))}</p>`;
        return;
    }
    sessions = body.sessions || [];
    renderSessions(body.max || 5);
}

function renderSessions(max) {
    $('ws-count').textContent =
        T('ws_count', '{n} / {m} 份').replace('{n}', sessions.length).replace('{m}', max);
    $('ws-new').disabled = sessions.length >= max;

    $('ws-list').innerHTML = sessions.map((s) => {
        const running = s.status === 'running' || s.status === 'starting';
        const isDefault = s.session_name === 'default';
        return `
        <div class="entry">
            <div class="entry__title">${esc(s.display_name)}
                ${running ? `<span class="footnote">　${esc(T('ws_running', '執行中'))}</span>` : ''}</div>
            <div class="entry__desc">${s.last_activity
                ? esc(T('ws_last', '最後使用：{w}').replace('{w}', TW.when(s.last_activity) || ''))
                : esc(T('ws_never', '還沒開過'))}</div>
            <div class="ds__actions">
                <button class="btn btn--minor" type="button" data-open="${esc(s.session_name)}">
                    ${esc(running ? T('ws_go', '前往') : T('ws_open', '開啟這一份'))}</button>
                ${isDefault ? '' : `<button class="btn btn--minor" type="button"
                    data-del="${esc(s.session_name)}" ${running ? 'disabled' : ''}>
                    ${esc(T('ws_delete', '刪除'))}</button>`}
            </div>
        </div>`;
    }).join('');

    $('ws-list').querySelectorAll('[data-open]').forEach((b) =>
        b.addEventListener('click', () => openSession(b.dataset.open)));
    $('ws-list').querySelectorAll('[data-del]').forEach((b) =>
        b.addEventListener('click', () => deleteSession(b.dataset.del, b)));
}

async function openSession(name) {
    // ZH: 切換前先講清楚 —— 使用者按下「開啟 B」時，A 會被關掉。
    //     不問就關掉的話，他回頭找 A 會以為壞了。
    const running = sessions.find((s) => (s.status === 'running' || s.status === 'starting')
                                         && s.session_name !== name);
    if (running && !confirm(T('ws_switch_confirm',
            '要切換到這一份嗎？「{n}」會關閉，但它的檔案都會保留。')
            .replace('{n}', running.display_name))) return;

    // ZH: 交給既有的啟動流程（它會輪詢到就緒才開新分頁）。
    // ZH: 交給既有的啟動流程（`#go` 的 handler 會輪詢到就緒才開新分頁）。
    //     ⚠ 不要自己再寫一份啟動邏輯 —— 那條路已經處理了「容器要 5–10 秒」
    //       與「不要開出空白分頁」，重寫一定會漏掉其中一件。
    currentSession = name;
    $('go').click();
}

async function deleteSession(name, btn) {
    const s = sessions.find((x) => x.session_name === name);
    if (!confirm(T('ws_delete_confirm', '要刪掉「{n}」嗎？裡面的檔案會一起消失，沒辦法復原。')
        .replace('{n}', s ? s.display_name : ''))) return;
    btn.disabled = true;
    try {
        const r = await fetch(`${API}/lab/sessions/${encodeURIComponent(name)}`,
                              { method: 'DELETE', headers: authHeaders() });
        if (!r.ok) {
            const body = await r.json().catch(() => ({}));
            throw new Error(String(body.detail || `HTTP ${r.status}`));
        }
        await loadSessions();
    } catch (e) {
        btn.disabled = false;
        alert(String(e.message).replace(/^ZH:\s*/, '').split(' | ')[0]);
    }
}

$('ws-new').addEventListener('click', async () => {
    const name = prompt(T('ws_new_prompt', '這一份要叫什麼名字？'));
    if (!name || !name.trim()) return;
    try {
        const r = await fetch(`${API}/lab/sessions`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', ...authHeaders() },
            body: JSON.stringify({ display_name: name.trim() }),
        });
        if (!r.ok) {
            const body = await r.json().catch(() => ({}));
            throw new Error(String(body.detail || `HTTP ${r.status}`));
        }
        await loadSessions();
    } catch (e) {
        alert(String(e.message).replace(/^ZH:\s*/, '').split(' | ')[0]);
    }
});

loadSessions();
document.addEventListener('prefs:langchanged', () => loadSessions());


/* ── 營運設定的補充說明（v3.8）──────────────────────────────────────
 * ZH: 這個數字是**管理者可以在營運設定裡改的**，所以不能寫死在 HTML ——
 *     寫死的話管理者調過之後，畫面上就是一個錯的數字，而且不會有人回報。
 *     值一律現取（Chrome.publicSettings 會在同一頁內快取）。
 *
 * ZH: 讀不到就**維持隱藏**，不要顯示「—」或 0。
 *     這是一句補充說明，缺了不影響這一頁本來要做的事；
 *     顯示一個假的 0 反而會被當成真的。
 * ------------------------------------------------------------------ */
function renderArchiveNote(s) {
    const el = $('archive-note');
    if (!el) return;
    const v = s && s['lab_archive_days'];
    if (v == null) { el.hidden = true; return; }
    el.textContent = T('lab_archive_note', '如果帳號被刪除，這些存檔會先封存保留 {d} 天，逾期才真的銷毀。').replace('{d}', v);
    el.hidden = false;
}

let PUB_SETTINGS = null;
Chrome.publicSettings().then((s) => { PUB_SETTINGS = s; renderArchiveNote(s); });
// ZH: 文案是 JS 組出來的，沒有 data-i18n，字典掃描換不掉它 —— 語言改變時要自己重畫。
document.addEventListener('prefs:langchanged', () => renderArchiveNote(PUB_SETTINGS));
