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

/* ── 回報類別（v3.9）───────────────────────────────────────────────
 * ZH: 🔴 **代碼與 schemas.IssueReportCreate.CATEGORIES 必須一致。**
 *     不一致的表現是：使用者選得到、送出後被清空，而且沒有任何錯誤訊息 ——
 *     後端把未知代碼當成「沒選」處理。
 * ZH: 存的是代碼不是顯示文字：翻譯過的字串當篩選鍵的話，
 *     介面一切成英文，管理端就篩不到任何東西。
 */
const CATEGORIES = [
    ['quota',   'rep_cat_quota',   'AI 額度'],
    ['train',   'rep_cat_train',   '訓練任務'],
    ['lab',     'rep_cat_lab',     '程式實驗室'],
    ['account', 'rep_cat_account', '帳號與登入'],
    ['other',   'rep_cat_other',   '其他'],
];

function fillCategories(selected) {
    const sel = $('cat');
    if (!sel) return;
    // ZH: 第一項是空值 —— 類別**不強迫選**。強迫的話，不知道該選哪一個的人
    //     會隨便挑一個，而那比留空更難處理（看起來像分類過了）。
    sel.innerHTML = '<option value="">' + T('rep_cat_none', '（不指定）') + '</option>'
        + CATEGORIES.map(([code, key, zh]) =>
            `<option value="${code}"${code === selected ? ' selected' : ''}>${T(key, zh)}</option>`
        ).join('');
}
fillCategories('');

// ZH: 色系切換已集中到 prefs.js（跟帳號走）。
//     原本九個頁面各寫一份，**只有 app.js 那份會存與還原**——
//     於是「有些頁面換了顏色，其他頁面還沒變」。同一條規則不要有第二份實作。

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
        // ZH: 標明台灣時間 —— 這一行會被貼給管理者，對方不該去猜是哪個時區。
        [T('diag_time', '時間'), TW.full(new Date()) + T('diag_tw', '（台灣時間）')],
        [T('diag_user', '使用者'), ME ? `${ME.username || '?'}（${ME.id || '?'}）` : T('diag_no_user', '（未取得，可能未登入）')],
        // ZH: 2026-08-22 的 `1cf0b3b` 把 web-ui-v2 改名成 web-ui-V1，這裡漏改。
        //     診斷資訊寫錯版本會讓看回報的人對著不存在的版本查問題。
        [T('diag_ui', '介面版本'), 'V1'],
        [T('diag_ref', '來源頁'), document.referrer || T('diag_direct', '（直接開啟）')],
        [T('diag_url', '網址'), location.href],
        [T('diag_ua', '瀏覽器'), nav.userAgent || '?'],
        [T('diag_lang', '語言'), nav.language || '?'],
        [T('diag_win', '視窗'), `${window.innerWidth}×${window.innerHeight}`],
        [T('diag_theme', '色系'), document.documentElement.dataset.theme || '?'],
    ];
}

function renderDiag() {
    $('diag').textContent = diagnostics()
        .map(([k, v]) => `${k}：${v}`)
        .join('\n');
}

function fullText() {
    const what = $('what').value.trim() || T('rep_no_desc', '（使用者沒有填寫描述）');
    return [
        T('rep_ticket_head', '【MCU AI Base 問題回報】'),
        '',
        '■ ' + T('rep_what', '發生了什麼事'),
        what,
        '',
        '■ ' + T('rep_diag', '診斷資訊'),
        ...diagnostics().map(([k, v]) => `${k}：${v}`),
    ].join('\n');
}

function say(msg) {
    $('note').textContent = msg;
    $('note').hidden = false;
}

// ── 送出 ─────────────────────────────────────────────────────────────
// ZH: 改成函式而非常數——模組層的物件在載入時就定案，切換語言不會更新。
const statusText = (s) => ({
    open: T('rep_st_open', '未處理'),
    in_progress: T('rep_st_doing', '處理中'),
    resolved: T('rep_st_done', '已解決'),
}[s] || s);

$('send').addEventListener('click', async () => {
    const body = $('what').value.trim();
    if (!body) {
        // ZH: 後端也擋（純空白 422），但在這裡先擋掉才不會讓使用者按了沒反應。
        say(T('rep_need_desc', '請先填寫「發生了什麼事」，只有診斷資訊管理者看不懂問題在哪。'));
        $('what').focus();
        return;
    }

    const btn = $('send');
    btn.disabled = true;
    const original = btn.textContent;
    btn.textContent = T('rep_sending', '送出中…');

    try {
        const r = await fetch(`${API}/reports`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', ...authHeaders() },
            body: JSON.stringify({
                subject: $('subject').value.trim(),
                category: $('cat').value,
                body,
                diagnostics: Object.fromEntries(diagnostics()),
            }),
        });

        if (r.status === 401 || r.status === 403) {
            // ZH: 未登入是最可能的失敗。不要只說「送出失敗」——
            //     那會讓人重試三次還是失敗。直接指路，並留下複製這條路。
            say(T('rep_need_login', '要先登入才能送出。你也可以按下面的「改用複製」，自己把內容交給管理者。'));
            return;
        }
        if (r.status === 429) {
            say(T('rep_rate', '送太多次了，請稍後再試（每小時上限 5 次）。急件請用「改用複製」直接交給管理者。'));
            return;
        }
        if (!r.ok) {
            say(T('rep_failed', '送出失敗').replace('{s}', r.status) + `（${r.status}）` );
            return;
        }

        $('what').value = '';
        // ZH: 主旨與類別一起清 —— 只清內文的話，下一則回報會頂著上一則的主旨送出，
        //     而管理端清單看到的就是那個錯的主旨。
        $('subject').value = '';
        fillCategories('');
        say(T('rep_sent', '已送出。管理者的回覆會出現在下方「我的回報」——不會另外寄信通知你。'));
        await loadMine();
    } catch {
        // ZH: 連不上後端。這正是複製鈕存在的理由。
        say(T('rep_offline', '連不上伺服器。請按下面的「改用複製」，自己把內容交給管理者。'));
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
        say(T('rep_copied', '已複製。貼給管理者即可（描述與診斷資訊都在裡面）。'));
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
        say(T('copy_manual', '這個瀏覽器不允許自動複製。已經幫你選起來了，按 Ctrl+C 複製。'));
    }
});

// ── 我的回報 ─────────────────────────────────────────────────────────
// ZH: 時間一律走 tz.js（釘死 Asia/Taipei）。
//     本端點的 created_at 已帶 +00:00，但 tz.js 兩種形狀都吃，這裡不必分。
function fmtDate(s) {
    return TW.full(s) || (s ? String(s) : '');
}

function renderMine(rows) {
    const box = $('mine');
    box.textContent = '';

    if (!rows.length) {
        const p = document.createElement('p');
        p.className = 'footnote';
        p.textContent = T('rep_none', '你還沒有送出過回報。');
        box.appendChild(p);
        return;
    }

    // ZH: v4.2（擁有者裁定 2026-09-01，與公告同套）：**主旨條目＋彈窗**。
    //     原本每筆全文攤開，回報一多整頁就長。現在一列
    //     「狀態徽章＋日期＋主旨」，點擊開 <dialog> 看全文與管理者回覆。
    rows.forEach((row) => {
        const art = document.createElement('article');
        art.className = 'post post--entry';

        const head = document.createElement('button');
        head.type = 'button';
        head.className = 'post__head post__head--btn';
        head.setAttribute('aria-haspopup', 'dialog');

        const badge = document.createElement('span');
        // ZH: 狀態用**文字**標籤，不只用顏色（WCAG 1.4.1）。
        badge.className = 'rep-badge';
        badge.dataset.status = row.status || 'open';
        badge.textContent = statusText(row.status) || T('rep_st_open', '未處理');
        head.appendChild(badge);

        const date = document.createElement('span');
        date.className = 'post__date';
        date.textContent = fmtDate(row.created_at);
        head.appendChild(date);

        const h = document.createElement('h3');
        h.className = 'post__title';
        // ZH: 舊回報沒有主旨（欄位是後來加的）→ 拿內文開頭頂替，別顯示空白列。
        h.textContent = row.subject || (row.body || '').slice(0, 40)
                        || T('rep_untitled', '(無主旨)');
        head.appendChild(h);

        const chev = document.createElement('span');
        chev.className = 'post__chev';
        chev.setAttribute('aria-hidden', 'true');
        chev.textContent = '›';
        head.appendChild(chev);

        head.addEventListener('click', () => openReport(row));
        art.appendChild(head);
        box.appendChild(art);
    });
}

/* ZH: v4.2 回報內容彈窗。單一 dialog 重複填；ESC / ✕ 都能關。
 *     全部 textContent 不進 innerHTML —— 使用者的字與管理者的回覆
 *     都不該能注入標記（沿用原 renderMine 的紀律）。 */
function openReport(row) {
    const dlg = $('rep-dialog');
    dlg.textContent = '';

    const x = document.createElement('form');
    x.method = 'dialog';
    x.className = 'nmod__x';
    const xb = document.createElement('button');
    xb.className = 'btn btn--minor';
    xb.type = 'submit';
    xb.setAttribute('aria-label', T('news_close', '關閉'));
    xb.textContent = '✕';
    x.appendChild(xb);

    const meta = document.createElement('div');
    meta.className = 'nmod__meta';
    const badge = document.createElement('span');
    badge.className = 'rep-badge';
    badge.dataset.status = row.status || 'open';
    badge.textContent = statusText(row.status) || T('rep_st_open', '未處理');
    meta.appendChild(badge);
    const date = document.createElement('span');
    date.className = 'post__date';
    date.textContent = fmtDate(row.created_at);
    meta.appendChild(date);

    const h = document.createElement('h2');
    h.className = 'nmod__title';
    h.textContent = row.subject || T('rep_untitled', '(無主旨)');

    const b = document.createElement('p');
    b.className = 'post__body';
    b.textContent = row.body;

    dlg.append(x, meta, h, b);

    if (row.admin_reply) {
        const reply = document.createElement('div');
        reply.className = 'rep-reply';
        const rh = document.createElement('div');
        rh.className = 'rep-reply__head';
        rh.textContent = `${T('rep_admin_reply', '管理者回覆')} · ${fmtDate(row.replied_at)}`;
        const rb = document.createElement('p');
        rb.className = 'post__body';
        rb.textContent = row.admin_reply;
        reply.appendChild(rh);
        reply.appendChild(rb);
        dlg.appendChild(reply);
    }
    dlg.showModal();
}

async function loadMine() {
    try {
        const r = await fetch(`${API}/reports/mine`,
                              { headers: { Accept: 'application/json', ...authHeaders() } });
        if (r.status === 401 || r.status === 403) {
            $('mine').textContent = '';
            const p = document.createElement('p');
            p.className = 'footnote';
            p.textContent = T('rep_login_to_see', '登入之後才看得到自己的歷史回報。');
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
        p.textContent = T('rep_load_fail', '暫時讀不到歷史回報。這不代表你送出的回報不見了，稍後重新整理即可。');
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


/* ── 預填主題（v3.9）────────────────────────────────────────────────
 * ZH: `?topic=quota` —— 從「額度已用完」的提示按過來時，先把申請的骨架填好。
 *
 * ZH: 為什麼是預填**而不是**做一個獨立的「申請額度」表單：
 *     問題回報這條路已經完整了（管理端看得到、回得了、使用者看得到回覆）。
 *     另開一條的話會有第二個收件匣，而第二個收件匣總是那個沒人看的。
 *
 * ZH: ⚠ 只填**空的**輸入框。使用者已經打了字還被蓋掉的話，那是資料遺失
 *     —— 而且他不會知道自己剛剛打的東西去哪了。
 * ZH: ⚠ 填完把游標移到最後，讓他直接接著打，不用先點一下再按 End。
 */
(function prefillTopic() {
    var topic = new URLSearchParams(location.search).get('topic');
    if (topic !== 'quota') return;
    var el = $('what');
    if (!el || el.value.trim()) return;
    // ZH: 用陣列 join 換行，不寫跳脫字元 —— 這一行的字典值裡也有換行，
    //     兩邊都用同一個組法，改文案時不會有人漏掉一個 \n。
    el.value = T('rep_prefill_quota',
        ['我想申請額外的 AI 額度。', '', '用途：', '大概需要多少：'].join('\n'));
    // ZH: 類別與主旨一起填好 —— 從「額度已用完」點過來的人，這三欄他都不必想。
    //     同樣只在**空的**時候才填（見上面的理由）。
    fillCategories('quota');
    const sub = $('subject');
    if (sub && !sub.value.trim()) sub.value = T('rep_subject_quota', '申請額外的 AI 額度');
    el.focus();
    el.setSelectionRange(el.value.length, el.value.length);
})();


// ── 語言切換時重繪 ───────────────────────────────────────────────────
// ZH: prefs.js 的字典掃描只換得掉 `data-i18n` 元素；本頁 JS 產生的內容要自己重跑。
//     只在語言**改變**時觸發（不是每次套用），所以不會在載入時多跑一次。
document.addEventListener('prefs:langchanged', () => {
    // ZH: 類別的顯示文字是 build 當下用 T() 組進 <option> 的，
    //     字典掃描換不掉 —— 要自己重畫，並**保留已經選好的那一個**。
    fillCategories($('cat') ? $('cat').value : '');
    renderDiag();
    loadMine();
});
