/* ==========================================================================
 * [畫面: 我的資料集] — 使用者在這裡要完成：騰出空間，或把舊資料再拿來訓練一次
 *
 * ZH: 這一頁**不是方便功能**。每人 2 GB 配額，而在這之前沒有任何刪除的方法——
 *     傳滿之後上傳一律 413，而使用者什麼都做不了。
 *
 * ZH: 刪除是不可逆的，所以：
 *       - 先問一次（confirm）
 *       - 還有任務在用的話**鈕直接是停用的**，並且說明原因——
 *         不要等他按下去才回一個 409
 * ========================================================================== */
const API = '/api/v1';

const $ = (id) => document.getElementById(id);

// ZH: ⚠ 鍵名必須與其他頁一致。用錯不會報錯，只會讓每個請求都 401，
//     而畫面看起來像「後端壞了」。
function authHeaders() {
    const t = sessionStorage.getItem('ai_hud_token') || localStorage.getItem('ai_hud_token');
    return t ? { Authorization: 'Bearer ' + t } : {};
}

// ZH: 目前的語言。**唯一定義**（train.js 那邊我曾經憑空假設過一個 `Prefs.lang()`，
//     它不存在，於是語言判斷永遠走中文分支，而中文模式下看不出來）。
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

// ZH: 名稱來自使用者自己的檔名，一律逸出。
function esc(s) {
    return String(s).replace(/[&<>"']/g, (c) =>
        ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

let items = [];

// ── 載入 ─────────────────────────────────────────────────────────────
async function load() {
    try {
        const r = await fetch(`${API}/datasets`, { headers: authHeaders() });
        if (r.status === 401 || r.status === 403) return signedOut();
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        const body = await r.json();
        items = body.datasets || [];
        renderQuota(body.used_bytes, body.quota_bytes);
        renderList();
    } catch (e) {
        // ZH: 取不到就說取不到。**不要顯示一個空列表**——那看起來像「你沒有資料集」，
        //     而使用者會因此以為他的東西不見了。
        $('list').innerHTML =
            `<p class="inline-error">${esc(T('ds_load_fail', '暫時讀不到你的資料集。這不代表它們不見了，稍後重新整理即可。'))}</p>`;
        $('quota').textContent = T('ds_quota_unknown', '用量：暫時讀不到');
    }
}

function signedOut() {
    $('list').innerHTML =
        `<p class="inline-error">${esc(T('tr_signed_out', '你的登入已經過期，請重新登入後再試一次。'))}` +
        ` <a class="btn btn--minor" href="login.html">${esc(T('btn_login', '登入'))}</a></p>`;
    $('quota').textContent = '';
}

function renderQuota(used, quota) {
    const pct = quota ? Math.min(100, (used / quota) * 100) : 0;
    $('quota-bar').style.width = `${pct}%`;
    $('quota-wrap').setAttribute('aria-valuenow', String(Math.round(pct)));
    $('quota').textContent =
        T('ds_quota', '已用 {u} / 上限 {q}').replace('{u}', human(used)).replace('{q}', human(quota));
    // ZH: 快滿了要看得出來——這一頁的來訪者多半就是為了這件事。
    $('quota-wrap').classList.toggle('bar--warn', pct >= 85);
}

function renderList() {
    if (!items.length) {
        $('list').innerHTML =
            `<p class="footnote">${esc(T('ds_empty', '還沒有上傳過任何資料集。'))}</p>`;
        return;
    }
    $('list').innerHTML = items.map((d) => {
        const busy = d.in_use_by_jobs > 0;
        return `
        <div class="entry">
            <div class="entry__title">${esc(d.name)}</div>
            <div class="entry__desc">${esc(human(d.size_bytes))}　${esc(TW.when(d.created_at) || '')}</div>
            <div class="ds__actions">
                <a class="btn btn--minor" href="train.html?dataset=${encodeURIComponent(d.id)}">
                    ${esc(T('ds_reuse', '再訓練一次'))}</a>
                <button class="btn btn--minor" type="button" data-del="${esc(d.id)}"
                        ${busy ? 'disabled' : ''}>
                    ${esc(T('ds_delete', '刪除'))}</button>
                ${busy ? `<span class="footnote">${esc(
                    T('ds_in_use', '有 {n} 個任務正在用，跑完才能刪').replace('{n}', d.in_use_by_jobs))}</span>` : ''}
            </div>
        </div>`;
    }).join('');

    $('list').querySelectorAll('[data-del]').forEach((b) =>
        b.addEventListener('click', () => remove(b.dataset.del, b)));
}

// ── 刪除 ─────────────────────────────────────────────────────────────
async function remove(id, btn) {
    const d = items.find((x) => x.id === id);
    // ZH: 刪除不可逆，先問一次。訊息裡帶上名字——「你確定嗎」問的是哪一個很重要。
    if (!confirm(T('ds_confirm', '要刪掉「{n}」嗎？這個動作沒辦法復原。')
        .replace('{n}', d ? d.name : ''))) return;

    btn.disabled = true;
    const original = btn.textContent;
    btn.textContent = T('ds_deleting', '刪除中…');
    try {
        const r = await fetch(`${API}/datasets/${encodeURIComponent(id)}`,
                              { method: 'DELETE', headers: authHeaders() });
        if (r.status === 401 || r.status === 403) return signedOut();
        if (!r.ok) {
            const body = await r.json().catch(() => ({}));
            throw new Error(detailText(body.detail) || `HTTP ${r.status}`);
        }
        await load();          // ZH: 重新讀 —— 用量要跟著更新，不要自己在前端減
    } catch (e) {
        btn.disabled = false;
        btn.textContent = original;
        alert(T('ds_delete_fail', '刪不掉') + `（${clean(e.message)}）`);
    }
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

// ZH: 雙語 detail 只留使用者當下的語言，不要兩句黏在一起。
function clean(msg) {
    const s = String(msg || '');
    const m = s.match(/ZH:\s*(.*?)\s*\|\s*EN:\s*(.*)$/s);
    if (!m) return s;
    return currentLang() === 'en' ? m[2] : m[1];
}

// ── 啟動 ─────────────────────────────────────────────────────────────
load();

// ZH: prefs.js 的字典掃描只換得掉 `data-i18n` 元素；本頁 JS 產生的內容要自己重跑。
document.addEventListener('prefs:langchanged', () => load());
