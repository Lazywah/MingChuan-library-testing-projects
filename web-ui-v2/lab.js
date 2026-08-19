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
const FORCED = new URLSearchParams(location.search).get('state');
const $ = (id) => document.getElementById(id);

let POLL = null;

// ── 色系切換（開發期）────────────────────────────────────────────────
document.querySelectorAll('[data-set-theme]').forEach((b) => {
    b.addEventListener('click', () => {
        const t = b.dataset.setTheme;
        document.documentElement.dataset.theme = t;
        document.querySelectorAll('[data-set-theme]').forEach((x) => {
            x.setAttribute('aria-pressed', String(x.dataset.setTheme === t));
        });
    });
});

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

const mins = (s) => (s == null ? '—' : `${Math.floor(s / 60)} 分`);

// ── 狀態 ─────────────────────────────────────────────────────────────
function render(d) {
    const running = d.status === 'running';
    $('state').textContent = running ? '執行中' : '未啟動';
    setPrimary({ label: running ? '開啟 Lab' : '啟動並開啟 Lab', enabled: true });
    $('stop').hidden = !running;

    $('meta').hidden = !running;
    if (running) {
        $('m-remaining').textContent = d.today_remaining_min != null
            ? `${d.today_remaining_min} 分` : '—';
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
        $('secrets').textContent = `啟動時會注入這些環境變數：${names.join('、')}`;
    }
}

async function load() {
    if (FORCED === 'loading') return;
    try {
        const d = FORCED ? mock(FORCED) : await api('/lab/status');
        render(d);
        note('');
    } catch (e) {
        $('state').textContent = '讀不到';
        setPrimary({ label: '重試', enabled: true });
        note(`暫時取不到 Lab 狀態（${e.message || e}）。`);
    }
}

// ── 主要動作 ─────────────────────────────────────────────────────────
function openTab(url) {
    const w = window.open(url, '_blank');
    if (!w) {
        // ZH: 被瀏覽器擋下時**不可以毫無反應**（與首頁前往 MYAI 同一條規則）。
        $('note').innerHTML = `瀏覽器擋下了新分頁。<a href="${url}" target="_blank" rel="noopener">點這裡開啟 Lab</a>`;
        $('note').hidden = false;
        return;
    }
    note('已在新分頁開啟。若看到「未授權」，請回首頁重新登入一次'
        + '（新分頁靠 cookie 認證，與這一頁不同）。');
}

$('go').addEventListener('click', async () => {
    setPrimary({ label: '啟動中…', enabled: false });
    note('容器啟動大約需要 5–10 秒，好了會自動開新分頁。');

    if (FORCED) {                       // 檢視模式：走完流程但不打後端
        setTimeout(() => { setPrimary({ label: '開啟 Lab', enabled: true });
                           note('（檢視模式：不會真的開容器）'); }, 600);
        return;
    }

    try {
        const started = await api('/lab/start', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({}),
        });
        // ZH: /lab/start 回的 url 已經是 /code/<uid>/?folder=...，直接用。
        //     但**不要立刻開** —— 先輪詢到 running 再開，否則新分頁是空白。
        await waitReady(started.url);
    } catch (e) {
        setPrimary({ label: '啟動並開啟 Lab', enabled: true });
        // ZH: 429 是額度/頻率限制，訊息由後端給，照實顯示不要改寫。
        note(`啟動失敗：${e.message || e}`);
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
            setPrimary({ label: '啟動並開啟 Lab', enabled: true });
            note('等了 30 秒仍未就緒。可以再試一次，或回報問題。'
                + '（容器可能仍在背景啟動，重新整理這一頁可以看到最新狀態。）');
        }
    }, 1500);
}

// ── 層級 3：停止 ─────────────────────────────────────────────────────
$('stop').addEventListener('click', async (ev) => {
    ev.preventDefault();
    // ZH: 停止會關掉容器但**不會刪檔案**——講明才不會有人不敢按。
    if (!confirm('要停止 Lab 嗎？容器會關閉，但你的檔案都會保留。')) return;
    try {
        if (!FORCED) await api('/lab/stop', { method: 'POST' });
        note('已停止。檔案都還在，下次啟動會回到原樣。');
        await load();
    } catch (e) {
        note(`停止失敗：${e.message || e}`);
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
