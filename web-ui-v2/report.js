/* ==========================================================================
 * [畫面: 問題回報] — 使用者在這裡要完成：把問題交給管理者，而且交得出重點
 *
 * ZH: v3.4 起這一頁**真的送得出去**：
 *       POST /api/v1/reports        送出（後端存 issue_reports，管理端可見）
 *       GET  /api/v1/reports/mine   自己的歷史 + 管理者回應
 *
 *     這一版刻意不做的事（不是還沒做，是決定不做）：
 *       - **不寄信、不通知**。回報只在管理介面可見，回覆出現在本頁下方。
 *         文案必須講清楚，否則使用者會以為有人會主動聯絡他。
 *       - **單則回應**。管理者回一段，使用者看得到，不能再回。
 *
 * ⚠ **複製鈕保留，送出鈕是新增不是取代。** 後端掛掉或使用者沒登入時，
 *   「複製後自己交出去」是唯一走得通的路。把降級路徑砍掉不划算。
 *
 * ⚠ **送出的診斷欄位＝頁面上顯示的那一份，一個不多。** 後端不補 IP 或 session
 *   （見 models.IssueReport 註解）。這一頁宣稱「你知道你交了什麼」，
 *   任一側偷加欄位都會讓那句話變成假的。
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
//     任何 token 或密碼。回報單可能被貼到聊天室或 email，內容要能安心外流。
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

function say(msg) {
    $('note').textContent = msg;
    $('note').hidden = false;
}

// ── 送出 ─────────────────────────────────────────────────────────────
const STATUS_TEXT = {
    open: '未處理',
    in_progress: '處理中',
    resolved: '已解決',
};

$('send').addEventListener('click', async () => {
    const body = $('what').value.trim();
    if (!body) {
        // ZH: 後端也擋（純空白 422），但在這裡先擋掉才不會讓使用者按了沒反應。
        say('請先填寫「發生了什麼事」，只有診斷資訊管理者看不懂問題在哪。');
        $('what').focus();
        return;
    }

    const btn = $('send');
    btn.disabled = true;
    const original = btn.textContent;
    btn.textContent = '送出中…';

    try {
        const r = await fetch(`${API}/reports`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', ...authHeaders() },
            body: JSON.stringify({ body, diagnostics: Object.fromEntries(diagnostics()) }),
        });

        if (r.status === 401 || r.status === 403) {
            // ZH: 未登入是最可能的失敗。不要只說「送出失敗」——
            //     那會讓人重試三次還是失敗。直接指路，並留下複製這條路。
            say('要先登入才能送出。你也可以按下面的「改用複製」，自己把內容交給管理者。');
            return;
        }
        if (r.status === 429) {
            say('送太多次了，請稍後再試（每小時上限 5 次）。急件請用「改用複製」直接交給管理者。');
            return;
        }
        if (!r.ok) {
            say(`送出失敗（${r.status}）。可以按下面的「改用複製」，自己交給管理者。`);
            return;
        }

        $('what').value = '';
        say('已送出。管理者的回覆會出現在下方「我的回報」——不會另外寄信通知你。');
        await loadMine();
    } catch {
        // ZH: 連不上後端。這正是複製鈕存在的理由。
        say('連不上伺服器。請按下面的「改用複製」，自己把內容交給管理者。');
    } finally {
        btn.disabled = false;
        btn.textContent = original;
    }
});

// ── 複製（降級路徑，永遠可用）─────────────────────────────────────────
$('copy').addEventListener('click', async () => {
    const text = fullText();
    try {
        await navigator.clipboard.writeText(text);
        say('已複製。貼給管理者即可（描述與診斷資訊都在裡面）。');
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
        say('這個瀏覽器不允許自動複製。已經幫你選起來了，按 Ctrl+C 複製。');
    }
});

// ── 我的回報 ─────────────────────────────────────────────────────────
function fmtDate(s) {
    if (!s) return '';
    const d = new Date(s);
    return Number.isNaN(d.getTime()) ? s : d.toLocaleString('zh-TW', { hour12: false });
}

function renderMine(rows) {
    const box = $('mine');
    box.textContent = '';

    if (!rows.length) {
        const p = document.createElement('p');
        p.className = 'footnote';
        p.textContent = '你還沒有送出過回報。';
        box.appendChild(p);
        return;
    }

    rows.forEach((row) => {
        const art = document.createElement('article');
        art.className = 'post';

        const head = document.createElement('div');
        head.className = 'post__head';
        const badge = document.createElement('span');
        // ZH: 狀態用**文字**標籤，不只用顏色（WCAG 1.4.1）。
        //     顏色只是次要強調：未處理有邊框、其餘中性。
        badge.className = 'rep-badge';
        badge.dataset.status = row.status || 'open';
        badge.textContent = STATUS_TEXT[row.status] || row.status || '未處理';
        head.appendChild(badge);
        head.appendChild(document.createTextNode(fmtDate(row.created_at)));
        art.appendChild(head);

        // ZH: 全部用 textContent，不用 innerHTML —— 這些是使用者自己打的字，
        //     但管理者的回覆也會走同一條路，兩邊都不該能注入標記。
        const b = document.createElement('p');
        b.className = 'post__body';
        b.textContent = row.body;
        art.appendChild(b);

        if (row.admin_reply) {
            const reply = document.createElement('div');
            reply.className = 'rep-reply';
            const rh = document.createElement('div');
            rh.className = 'rep-reply__head';
            rh.textContent = `管理者回覆 · ${fmtDate(row.replied_at)}`;
            const rb = document.createElement('p');
            rb.className = 'post__body';
            rb.textContent = row.admin_reply;
            reply.appendChild(rh);
            reply.appendChild(rb);
            art.appendChild(reply);
        }

        box.appendChild(art);
    });
}

async function loadMine() {
    try {
        const r = await fetch(`${API}/reports/mine`,
                              { headers: { Accept: 'application/json', ...authHeaders() } });
        if (r.status === 401 || r.status === 403) {
            $('mine').textContent = '';
            const p = document.createElement('p');
            p.className = 'footnote';
            p.textContent = '登入之後才看得到自己的歷史回報。';
            $('mine').appendChild(p);
            return;
        }
        if (!r.ok) throw new Error(String(r.status));
        renderMine(await r.json());
    } catch {
        $('mine').textContent = '';
        const p = document.createElement('p');
        p.className = 'inline-error';
        // ZH: 不要顯示空清單 —— 「沒有回報」與「拿不到清單」是兩件事，
        //     顯示成一樣會讓人以為自己送出的東西不見了。
        p.textContent = '暫時讀不到歷史回報。這不代表你送出的回報不見了，稍後重新整理即可。';
        $('mine').appendChild(p);
    }
}

// ── 啟動 ─────────────────────────────────────────────────────────────
async function load() {
    renderDiag();
    try {
        const r = await fetch(`${API}/auth/me`,
                              { headers: { Accept: 'application/json', ...authHeaders() } });
        if (r.ok) { ME = await r.json(); renderDiag(); }
    } catch { /* 取不到身分不影響回報——診斷區會註明「未取得」 */ }
    await loadMine();
}

load();
