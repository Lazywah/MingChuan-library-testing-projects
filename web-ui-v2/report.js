/* ==========================================================================
 * [畫面: 問題回報] — 使用者在這裡要完成：把問題交給管理者，而且交得出重點
 *
 * ZH: 為什麼這一頁沒有「送出」按鈕 ——
 *     後端**沒有任何接收回報的端點**（grep routers 全無），
 *     也沒有設定任何聯絡地址（SMTP_FROM_EMAIL 是 noreply@ai-platform.local 佔位）。
 *
 *     在這個前提下：
 *       做一顆「送出」→ 送去哪裡？那是假的按鈕。
 *       做 mailto     → 要編一個收件地址。編造的地址比沒有更糟。
 *       只跳一句「請洽管理員」→ v1.5 就是這樣，使用者仍然不知道要講什麼。
 *     所以這一頁做的是**幫他整理好，他自己交出去**。零後端、零編造、有實際用處。
 *
 * ⚠ 接上真正的回報管道是**產品決定**（收件人？存資料庫還是寄信？要不要附截圖？），
 *   不是實作細節。決定之後這一頁只要多一顆送出鈕。
 * ========================================================================== */
const API = '/api/v1';
const $ = (id) => document.getElementById(id);

let ME = null;

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

// ── 診斷資訊 ─────────────────────────────────────────────────────────
// ZH: 只收「管理者查問題真的會用到」的欄位。
//     **刻意不收**：完整 user agent 以外的指紋、IP（前端也拿不到）、
//     任何 token 或密碼。回報單會被貼到聊天室或 email，內容要能安心外流。
function diagnostics() {
    const nav = window.navigator || {};
    return [
        ['時間', new Date().toString()],
        ['使用者', ME ? `${ME.username || '?'}（${ME.id || '?'}）` : '（未取得，可能未登入）'],
        ['介面版本', 'v2'],
        ['來源頁', document.referrer || '（直接開啟）'],
        ['網址', location.href],
        ['瀏覽器', nav.userAgent || '?'],
        ['語言', nav.language || '?'],
        ['視窗', `${window.innerWidth}×${window.innerHeight}`],
        ['色系', document.documentElement.dataset.theme || '?'],
    ];
}

function renderDiag() {
    $('diag').textContent = diagnostics()
        .map(([k, v]) => `${k}：${v}`)
        .join('\n');
}

function fullText() {
    const what = $('what').value.trim() || '（使用者沒有填寫描述）';
    return [
        '【MCU AI Base 問題回報】',
        '',
        '■ 發生了什麼事',
        what,
        '',
        '■ 診斷資訊',
        ...diagnostics().map(([k, v]) => `${k}：${v}`),
    ].join('\n');
}

$('copy').addEventListener('click', async () => {
    const text = fullText();
    try {
        await navigator.clipboard.writeText(text);
        $('note').textContent = '已複製。貼給管理者即可（描述與診斷資訊都在裡面）。';
    } catch {
        // ZH: 剪貼簿在非 https 或權限被拒時不可用。不要靜默失敗——
        //     直接把整段選起來，使用者按 Ctrl+C 就好。
        const pre = $('diag');
        pre.textContent = text;
        const r = document.createRange();
        r.selectNodeContents(pre);
        const sel = window.getSelection();
        sel.removeAllRanges();
        sel.addRange(r);
        $('note').textContent = '這個瀏覽器不允許自動複製。已經幫你選起來了，按 Ctrl+C 複製。';
    }
    $('note').hidden = false;
});

// ZH: 使用者一邊打字，診斷區不需要跟著變 —— 但時間要在按下複製時才定案，
//     所以 fullText() 每次重算，不用 render 出來的那份。

// ── 啟動 ─────────────────────────────────────────────────────────────
async function load() {
    renderDiag();
    try {
        const r = await fetch(`${API}/auth/me`,
                              { headers: { Accept: 'application/json', ...authHeaders() } });
        if (r.ok) { ME = await r.json(); renderDiag(); }
    } catch { /* 取不到身分不影響回報——診斷區會註明「未取得」 */ }
}

load();
