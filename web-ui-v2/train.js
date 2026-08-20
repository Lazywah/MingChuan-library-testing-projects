/* ==========================================================================
 * [畫面: 交給平台訓練] — 使用者在這裡要完成：把一包分好類的圖片變成一個模型，
 *                        全程不寫程式。
 *
 * ZH: 這一頁只問兩件事（圖片、幾輪），其餘由平台決定。會調 batch_size 的人
 *     本來就該去程式實驗室；不會調的人看到那些欄位只會卡住。
 *
 * ZH: 失敗要說得出「為什麼」。這條路上有四個地方會失敗，症狀完全不同：
 *       上傳（檔案太大／型別不對）、送單（沒算力／配額不足）、
 *       資料集準備（解壓失敗）、訓練本身（類別太少、圖片太少）。
 *     全部落到「失敗了」的話，使用者無從下一步。
 * ========================================================================== */
const API = '/api/v1';

const $ = (id) => document.getElementById(id);

// ZH: ⚠ 鍵名必須與其他頁一致。用錯不會報錯，只會讓每個請求都 401，
//     而畫面看起來像「後端壞了」。
function authHeaders() {
    const t = sessionStorage.getItem('ai_hud_token') || localStorage.getItem('ai_hud_token');
    return t ? { Authorization: 'Bearer ' + t } : {};
}

// ── 狀態 ─────────────────────────────────────────────────────────────
let picked = null;        // ZH: 使用者選的檔案（尚未上傳）
let jobId = null;
let polling = null;
let lastLogLen = 0;

// ── 主要動作的樣貌 ───────────────────────────────────────────────────
function setNote(html) {
    const n = $('note');
    n.innerHTML = html || '';
    n.hidden = !html;
}

function setGo({ label, enabled }) {
    $('go').textContent = label;
    $('go').disabled = !enabled;
}

// ZH: 位元組換成人看得懂的單位。上限 2 GB 的訊息裡直接寫「你的檔案 2.4 GB」，
//     比「超過上限」有用得多。
function human(bytes) {
    if (bytes >= 1024 ** 3) return (bytes / 1024 ** 3).toFixed(1) + ' GB';
    if (bytes >= 1024 ** 2) return (bytes / 1024 ** 2).toFixed(1) + ' MB';
    return Math.max(1, Math.round(bytes / 1024)) + ' KB';
}

// ── 選檔 ─────────────────────────────────────────────────────────────
function choose(file) {
    if (!file) return;
    if (!/\.zip$/i.test(file.name)) {
        // ZH: 在**選檔當下**就講，不要等按了開始訓練、上傳完才退回來。
        setNote(T('tr_not_zip', '這不是 zip 檔。請把整個資料夾壓成 .zip 再上傳。'));
        picked = null;
        setGo({ label: T('tr_go', '開始訓練'), enabled: false });
        return;
    }
    picked = file;
    setNote('');
    $('drop-main').textContent = file.name;
    $('drop-hint').textContent = human(file.size);
    $('drop').classList.add('drop--has');
    setGo({ label: T('tr_go', '開始訓練'), enabled: true });
}

$('drop').addEventListener('click', () => $('file').click());
$('drop').addEventListener('keydown', (e) => {
    // ZH: 這是 role="button" 的 div，鍵盤要自己接（Enter / Space），
    //     不然只有滑鼠使用者進得來。
    if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); $('file').click(); }
});
$('file').addEventListener('change', (e) => choose(e.target.files[0]));

['dragenter', 'dragover'].forEach((ev) =>
    $('drop').addEventListener(ev, (e) => {
        e.preventDefault();
        $('drop').classList.add('drop--over');
    }));
['dragleave', 'drop'].forEach((ev) =>
    $('drop').addEventListener(ev, (e) => {
        e.preventDefault();
        $('drop').classList.remove('drop--over');
    }));
$('drop').addEventListener('drop', (e) => choose(e.dataTransfer.files[0]));

// ── 送出 ─────────────────────────────────────────────────────────────
$('go').addEventListener('click', async () => {
    if (!picked) return;
    setGo({ label: T('tr_uploading', '上傳中…'), enabled: false });
    setNote('');

    let datasetPath;
    try {
        const fd = new FormData();
        fd.append('file', picked, picked.name);
        const r = await fetch(`${API}/datasets/upload`, {
            method: 'POST', headers: authHeaders(), body: fd,
        });
        const body = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(detailText(body.detail) || `HTTP ${r.status}`);
        datasetPath = body.dataset_path;
    } catch (e) {
        // ZH: 上傳失敗與送單失敗要分得開——前者重選檔案，後者是等一下再試。
        setNote(T('tr_upload_fail', '上傳失敗') + `（${clean(e.message)}）`);
        setGo({ label: T('tr_go', '開始訓練'), enabled: true });
        return;
    }

    setGo({ label: T('tr_submitting', '送出中…'), enabled: false });
    const epochs = Math.min(50, Math.max(1, parseInt($('epochs').value, 10) || 10));
    try {
        const r = await fetch(`${API}/jobs`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', ...authHeaders() },
            body: JSON.stringify({
                job_name: picked.name.replace(/\.zip$/i, ''),
                model_name: 'resnet18',
                dataset_path: datasetPath,
                // ZH: 種類寫明。不寫也會落到預設，但寫出來的話**日後多一種任務時
                //     這張舊單仍然指向同一支腳本**，不會跟著預設值漂走。
                config: { epochs: epochs, task: 'image_classification' },
            }),
        });
        const body = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(detailText(body.detail) || `HTTP ${r.status}`);
        jobId = body.job_id;
    } catch (e) {
        setNote(T('tr_submit_fail', '送不出去') + `（${clean(e.message)}）`);
        setGo({ label: T('tr_go', '開始訓練'), enabled: true });
        return;
    }

    setGo({ label: T('tr_running', '訓練中…'), enabled: false });
    $('run').hidden = false;
    $('run').scrollIntoView({ behavior: 'smooth', block: 'start' });
    poll();
    polling = setInterval(poll, 3000);
});

// ZH: 後端的錯誤有兩種形狀：
//       422（欄位驗證）→ detail 是**一個陣列**，每筆是物件
//       其他            → detail 是一個雙語字串「ZH: … | EN: …」
//     直接 String() 前者會得到 `[object Object]` —— 實測踩過，畫面上就是那六個字。
//     使用者看到那個等於什麼都沒說。
function detailText(detail) {
    if (detail == null) return '';
    if (typeof detail === 'string') return detail;
    if (Array.isArray(detail)) {
        return detail.map((d) => {
            const field = Array.isArray(d.loc) ? d.loc[d.loc.length - 1] : '';
            return field ? `${field}: ${d.msg || ''}` : (d.msg || JSON.stringify(d));
        }).join('；');
    }
    return JSON.stringify(detail);
}

// ZH: 後端的雙語 detail 是「ZH: … | EN: …」。畫面只該出現一種語言，
//     不然使用者會看到一句自己看得懂、一句看不懂的黏在一起。
function clean(msg) {
    const s = String(msg || '');
    const wantEn = (window.Prefs && Prefs.lang && Prefs.lang() === 'en');
    const m = s.match(/ZH:\s*(.*?)\s*\|\s*EN:\s*(.*)$/s);
    if (!m) return s;
    return wantEn ? m[2] : m[1];
}

// ── 進度 ─────────────────────────────────────────────────────────────
const STATE_TEXT = () => ({
    pending:   T('tr_queued', '排隊中…'),
    queued:    T('tr_queued', '排隊中…'),
    running:   T('tr_training', '訓練中…'),
    completed: T('tr_done', '完成'),
    failed:    T('tr_failed', '失敗'),
    cancelled: T('tr_cancelled', '已取消'),
});

function setBar(pct) {
    $('bar').style.width = `${Math.max(0, Math.min(100, pct || 0))}%`;
    $('bar-wrap').setAttribute('aria-valuenow', String(Math.round(pct || 0)));
}

async function poll() {
    if (!jobId) return;
    let j;
    try {
        const r = await fetch(`${API}/jobs/${jobId}`, { headers: authHeaders() });
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        j = await r.json();
    } catch {
        // ZH: 查詢失敗**不等於**訓練失敗。這裡只是這一次沒問到，下一輪再問。
        //     宣告「失敗了」會讓使用者以為要重來，而任務其實還在跑。
        $('run-state').textContent = T('tr_poll_fail', '暫時查不到進度（訓練仍在進行）');
        return;
    }

    setBar(j.progress);
    $('run-state').textContent = STATE_TEXT()[j.status] || j.status;

    renderMetrics(j.metrics || []);

    const logs = j.logs || '';
    if (logs.length !== lastLogLen) {
        lastLogLen = logs.length;
        $('log').textContent = logs;
        $('log-fold').hidden = false;
    }

    if (j.status === 'completed' || j.status === 'failed' || j.status === 'cancelled') {
        clearInterval(polling);
        polling = null;
        finish(j);
    }
}

function finish(j) {
    if (j.status === 'completed') {
        setBar(100);
        setGo({ label: T('tr_again', '再訓練一次'), enabled: true });
        picked = null;
        $('drop').classList.remove('drop--has');
        $('drop-main').textContent = T('tr_drop', '把 zip 拖到這裡，或點一下選檔案');
        $('drop-hint').textContent = T('tr_drop_sub', '只收 .zip，每人上限 2 GB');
        setNote(T('tr_done_note', '訓練完成，結果在下面。模型檔留在運算主機上，這一版還不能下載。'));
    } else {
        setGo({ label: T('tr_go', '開始訓練'), enabled: true });
        $('log-fold').hidden = false;
        $('log-fold').open = true;
        setNote(T('tr_failed_note', '這次沒有跑完') +
                (j.error_message ? `（${clean(j.error_message)}）` : '') +
                ' ' + T('tr_failed_hint', '常見原因：類別少於兩個、或圖片太少。'));
    }
}

// ── 指標 ─────────────────────────────────────────────────────────────
// ZH: 後端的 metrics 是一個陣列，每筆有 kind：dataset（開頭一次）、
//     epoch（每輪）、summary（結尾）。畫面只讀，不做計算以外的假設——
//     多出不認得的 kind 就忽略，不要壞掉。
function renderMetrics(metrics) {
    const ds = metrics.filter((m) => m.kind === 'dataset').pop();
    const sum = metrics.filter((m) => m.kind === 'summary').pop();
    const eps = metrics.filter((m) => m.kind === 'epoch');

    const cards = [];
    if (ds) {
        // ZH: 頓號是中文的列舉符號；英文模式要用逗號。這種字元層級的東西
        //     字典掃描抓不到——它不是一個 key，是一個 join 的參數。
        const sep = (window.Prefs && Prefs.lang && Prefs.lang() === 'en') ? ', ' : '、';
        cards.push([T('tr_m_classes', '類別'), (ds.classes || []).join(sep) || '—',
                    T('tr_m_images', '{n} 張圖片').replace('{n}', ds.images)]);
    }
    const best = sum ? sum.best_val_accuracy
                     : (eps.length ? Math.max(...eps.map((e) => e.val_accuracy)) : null);
    if (best != null) {
        cards.push([T('tr_m_acc', '正確率'), (best * 100).toFixed(1) + '%',
                    T('tr_m_acc_sub', '在沒看過的圖片上')]);
    }
    if (sum) {
        cards.push([T('tr_m_time', '花費時間'),
                    sum.elapsed_seconds < 60 ? `${Math.round(sum.elapsed_seconds)} ${T('tr_sec', '秒')}`
                                             : `${(sum.elapsed_seconds / 60).toFixed(1)} ${T('tr_min', '分鐘')}`,
                    '']);
    }

    const box = $('run-stats');
    box.hidden = cards.length === 0;
    box.innerHTML = cards.map(([label, value, sub]) => `
        <div>
            <div class="stat__label">${esc(label)}</div>
            <div class="stat__value">${esc(value)}</div>
            ${sub ? `<div class="stat__sub">${esc(sub)}</div>` : ''}
        </div>`).join('');

    $('epochs-title').hidden = eps.length === 0;
    $('epochs-table').hidden = eps.length === 0;
    if (eps.length) {
        $('epochs-table').innerHTML = `
            <table class="tbl">
              <thead><tr>
                <th>${esc(T('tr_th_epoch', '第幾輪'))}</th>
                <th>${esc(T('tr_th_acc', '正確率'))}</th>
                <th>${esc(T('tr_th_loss', '誤差'))}</th>
              </tr></thead>
              <tbody>${eps.map((e) => `
                <tr>
                  <td>${e.epoch} / ${e.epochs}</td>
                  <td>${(e.val_accuracy * 100).toFixed(1)}%</td>
                  <td>${e.train_loss}</td>
                </tr>`).join('')}</tbody>
            </table>`;
    }
}

// ZH: 這些值有一部分來自使用者自己的檔名與資料夾名（＝類別名），所以一律逸出。
function esc(s) {
    return String(s).replace(/[&<>"']/g, (c) =>
        ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

// ── 語言切換時重繪 ───────────────────────────────────────────────────
// ZH: prefs.js 的字典掃描只換得掉 `data-i18n` 元素；本頁 JS 產生的內容要自己重跑。
document.addEventListener('prefs:langchanged', () => {
    if (!picked) {
        $('drop-main').textContent = T('tr_drop', '把 zip 拖到這裡，或點一下選檔案');
        $('drop-hint').textContent = T('tr_drop_sub', '只收 .zip，每人上限 2 GB');
    }
    setGo({ label: $('go').disabled && jobId ? T('tr_running', '訓練中…') : T('tr_go', '開始訓練'),
            enabled: !$('go').disabled });
    if (jobId) poll();
});
