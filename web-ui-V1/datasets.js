/* ==========================================================================
 * [畫面: 我的資料與模型] — 使用者在這裡要完成：拿回／重用／刪掉資料，拿到模型
 *
 * ZH: v4.29 從「我的資料集」擴成兩區（擁有者 2026-09-24）：
 *       · 資料 —— 拿回來（新）、再訓練一次、刪掉騰出空間
 *       · 模型 —— 下載，以及**看得到規則**（每人幾個、幾天後清掉）
 *     理由寫在 datasets.html 的註解裡。
 *
 * ZH: 資料那一區**不是方便功能**。每人 2 GB 配額，而在這之前沒有任何刪除的方法——
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

    $('list').querySelectorAll('[data-del]').forEach((b) =>
        b.addEventListener('click', () => remove(b.dataset.del, b)));
    // ZH: v4.29 拿回自己上傳的那一包。檔名用當初的原名（後端的 Content-Disposition 帶著），
    //     這裡給的只是後備。
    $('list').querySelectorAll('[data-dlds]').forEach((b) =>
        b.addEventListener('click', () => {
            const d = items.find((x) => x.id === b.dataset.dlds);
            downloadFile(`/datasets/${encodeURIComponent(b.dataset.dlds)}/download`,
                         (d && d.name) || 'dataset.zip', b);
        }));
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

// ══════════════════════════════════════════════════════════════════════
// ZH: 模型區（v4.29）—— 這一頁的下半部
// ══════════════════════════════════════════════════════════════════════
// ZH: 🔴 規則（每人幾個、幾天後清）**跟著資料一起從後端來**，不寫死在文案裡。
//     那幾個值是環境變數，改了之後寫死的數字就會說謊，而且沒有守衛抓得到。
// ZH: 🔴 被清掉的模型也列出來，寫「已過保留期（幾月幾日清掉）」——
//     只列還在的，過期的那幾張就從畫面上消失，跟「平台弄丟了」分不出來。
//     在此之前畫面就是這樣：下載鈕安靜消失。

async function loadModels() {
    try {
        const r = await fetch(`${API}/jobs/models`, { headers: authHeaders() });
        if (r.status === 401 || r.status === 403) return signedOut();
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        renderModels(await r.json());
    } catch (e) {
        // ZH: 讀不到就說讀不到 —— 不要顯示空列表（那看起來像「你沒有模型」）。
        $('models').innerHTML =
            `<p class="inline-error">${esc(T('ds_models_load_fail', '暫時讀不到你的模型。這不代表它們不見了，稍後重新整理即可。'))}</p>`;
        $('models-rule').hidden = true;
    }
}

function renderModels(body) {
    const rule = $('models-rule');
    if (body.keep && body.ttl_days) {
        rule.textContent = T('ds_models_rule',
            '每人保留最近 {k} 個，跑完 {d} 天後自動清掉。不算在上面的資料配額裡。')
            .replace('{k}', body.keep).replace('{d}', body.ttl_days);
        rule.hidden = false;
    } else {
        rule.hidden = true;
    }

    const rows = body.models || [];
    if (!rows.length) {
        $('models').innerHTML = `<p class="footnote">${esc(
            T('ds_models_empty', '還沒有訓練出任何模型。跑完一次「交給平台訓練」就會出現在這裡。'))}</p>`;
        return;
    }
    $('models').innerHTML = rows.map((m) => {
        const when = TW.when(m.completed_at) || '';
        // ZH: 三種狀態各講各的：還在（保留到哪一天）／清掉了（哪一天清的）。
        const keep = m.has_model
            ? T('ds_model_until', '保留到 {d}').replace('{d}', TW.date(m.expires_at) || '—')
            : T('ds_model_gone', '已過保留期（{d} 清掉）').replace('{d}', TW.date(m.purged_at) || '—');
        return `
        <div class="entry">
            <div class="entry__title">${esc(m.job_name || '—')}</div>
            <div class="entry__desc">${m.has_model ? esc(human(m.model_bytes)) + '　' : ''}${esc(when)}　${esc(keep)}</div>
            <div class="ds__actions">
                ${m.has_model ? `<button class="btn btn--minor" type="button" data-dl="${esc(m.job_id)}">
                    ${esc(T('tr_download', '下載模型檔'))}</button>` : ''}
                <a class="btn btn--minor" href="train.html?job=${encodeURIComponent(m.job_id)}">
                    ${esc(T('ds_model_open', '看那張訓練單'))}</a>
            </div>
        </div>`;
    }).join('');

    $('models').querySelectorAll('[data-dl]').forEach((b) =>
        b.addEventListener('click', () =>
            downloadFile(`/jobs/${encodeURIComponent(b.dataset.dl)}/model`, 'model.pt', b)));
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

// ── 啟動 ─────────────────────────────────────────────────────────────
load();
loadModels();

// ZH: prefs.js 的字典掃描只換得掉 `data-i18n` 元素；本頁 JS 產生的內容要自己重跑。
document.addEventListener('prefs:langchanged', () => { load(); loadModels(); });
