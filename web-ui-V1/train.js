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
// ZH: v3.6 —— 從「我的資料集」按「再訓練一次」進來時，網址會帶 ?dataset=<id>。
//     這條路**完全不上傳**（檔案早就在伺服器上了），所以是另一條分支。
const QS = new URLSearchParams(location.search);
// ZH: v3.6 —— 從「我的訓練」點進來時帶 ?job=<id>：**只看**既有任務，不送新單。
//     這條路完全不碰上傳與送出，畫面上那張表單整個收起來。
const viewJobId = QS.get('job');
let reuseId = QS.get('dataset');
let reuseName = null;
let picked = null;        // ZH: 使用者選的檔案（尚未上傳）
// ZH: v3.6 使用者自帶的訓練程式（原始碼字串，不是檔案 —— 隨送單一起走）
let scriptSource = null;
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

// ── 自帶程式 ─────────────────────────────────────────────────────────
$('code-drop').addEventListener('click', () => $('codefile').click());
$('code-drop').addEventListener('keydown', (e) => {
    if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); $('codefile').click(); }
});
$('codefile').addEventListener('change', async (e) => {
    const f = e.target.files[0];
    if (!f) return;
    if (!/\.py$/i.test(f.name)) {
        setNote(T('tr_own_not_py', '請選一支 .py 檔。'));
        return;
    }
    // ZH: 原始碼隨送單一起走（不另外上傳）——沒有「先上傳、後送單」之間的競態，
    //     也不會留下孤兒檔案。
    scriptSource = await f.text();
    if (scriptSource.length > 262144) {
        // ZH: 後端也擋（422），但在這裡先說比較有用：他還沒等 GPU 排隊。
        setNote(T('tr_own_too_big', '這支程式太大了（上限 256 KB）。'));
        scriptSource = null;
        return;
    }
    setNote('');
    $('code-main').textContent = f.name;
    $('code-sub').textContent = `${Math.max(1, Math.round(scriptSource.length / 1024))} KB`;
    $('code-drop').classList.add('drop--has');
});

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
    if (!picked && !reuseId) return;
    setNote('');

    // ZH: 重用既有資料集 —— 檔案已經在伺服器上，這裡什麼都不用傳。
    if (reuseId) return submitJob({ dataset_id: reuseId }, reuseName || 'training');

    setGo({ label: T('tr_uploading', '上傳中…'), enabled: false });
    let datasetPath;
    try {
        const fd = new FormData();
        fd.append('file', picked, picked.name);
        const r = await fetch(`${API}/datasets/upload`, {
            method: 'POST', headers: authHeaders(), body: fd,
        });
        if (r.status === 401 || r.status === 403) throw new Error('__AUTH__');
        const body = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(detailText(body.detail) || `HTTP ${r.status}`);
        datasetPath = body.dataset_path;
    } catch (e) {
        // ZH: 上傳失敗與送單失敗要分得開——前者重選檔案，後者是等一下再試。
        // ZH: 而「登入過期」與兩者都不同：**再試幾次都不會好**，要重新登入。
        //     原本會顯示「上傳失敗（無法驗證憑證）」——那句話不會讓任何人去重新登入。
        if (e.message === '__AUTH__') {
            setNote(T('tr_signed_out', '你的登入已經過期，請重新登入後再試一次。') +
                    ` <a class="btn btn--minor" href="login.html">${esc(T('btn_login', '登入'))}</a>`);
            setGo({ label: T('tr_go', '開始訓練'), enabled: true });
            return;
        }
        setNote(T('tr_upload_fail', '上傳失敗') + `（${clean(e.message)}）`);
        setGo({ label: T('tr_go', '開始訓練'), enabled: true });
        return;
    }

    return submitJob({ dataset_path: datasetPath }, picked.name.replace(/\.zip$/i, ''));
});

// ZH: 送單。**上傳與重用兩條路共用這一支** —— 各寫一份的話，
//     日後改送單參數時一定會有一條被漏掉，而那條會安靜地繼續送舊格式。
async function submitJob(datasetRef, jobName) {
    setGo({ label: T('tr_submitting', '送出中…'), enabled: false });
    const epochs = Math.min(50, Math.max(1, parseInt($('epochs').value, 10) || 10));
    try {
        const r = await fetch(`${API}/jobs`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', ...authHeaders() },
            body: JSON.stringify(Object.assign({
                job_name: jobName,
                model_name: 'resnet18',
                // ZH: 有自帶程式就送出去；後端據此**不會**套用內建腳本。
                ...(scriptSource ? { script_source: scriptSource } : {}),
                // ZH: 種類寫明。不寫也會落到預設，但寫出來的話**日後多一種任務時
                //     這張舊單仍然指向同一支腳本**，不會跟著預設值漂走。
                config: { epochs: epochs, task: 'image_classification' },
            }, datasetRef)),
        });
        if (r.status === 401 || r.status === 403) {
            const body = await r.json().catch(() => ({}));
            // ZH: 403 在這裡有兩種意思：登入過期，或**這份資料集不是你的**。
            //     後者在正常使用下不會發生（是別人的 id 才會），但訊息要分得開。
            setNote(r.status === 401
                ? T('tr_signed_out', '你的登入已經過期，請重新登入後再試一次。')
                : clean(detailText(body.detail)) || T('tr_submit_fail', '送不出去'));
            setGo({ label: T('tr_go', '開始訓練'), enabled: true });
            return;
        }
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
}

// ZH: 帶著 ?dataset= 進來時，把拖放區換成「用這一包」的說明，
//     並讓開始鈕直接可按 —— 這條路不需要選檔案。
async function initReuse() {
    if (!reuseId) return;
    $('go').disabled = false;
    $('drop').classList.add('drop--has');
    $('drop-main').textContent = T('tr_reusing', '用你上傳過的資料');
    $('drop-hint').textContent = '';
    try {
        const r = await fetch(`${API}/datasets`, { headers: authHeaders() });
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        const found = ((await r.json()).datasets || []).find((d) => d.id === reuseId);
        if (!found) {
            // ZH: id 對不上（被刪了、或不是自己的）——**不要默默讓他按下去**，
            //     那會在送單時才拿到 403，而他不知道為什麼。
            reuseId = null;
            $('drop').classList.remove('drop--has');
            $('drop-main').textContent = T('tr_drop', '把 zip 拖到這裡，或點一下選檔案');
            $('drop-hint').textContent = T('tr_drop_sub', '只收 .zip，每人上限 2 GB');
            $('go').disabled = true;
            setNote(T('tr_reuse_gone', '找不到那份資料集，可能已經被刪掉了。請重新選一個檔案。'));
            return;
        }
        reuseName = found.name.replace(/\.zip$/i, '');
        $('drop-main').textContent = found.name;
        $('drop-hint').textContent = human(found.size_bytes);
    } catch {
        // ZH: 讀不到清單不影響送單（伺服器那邊仍會驗所有權），只是顯示不了名字。
        $('drop-main').textContent = T('tr_reusing', '用你上傳過的資料');
    }
}

// ZH: 三種進入方式，互斥：
//     ?job=<id>     只看既有任務（從「我的訓練」進來）
//     ?dataset=<id> 用既有資料集訓練（從「我的資料集」進來）
//     什麼都沒帶     一般的上傳流程
if (viewJobId) initViewMode();
else initReuse();


// ── 只看既有任務 ─────────────────────────────────────────────────────
function initViewMode() {
    // ZH: 從「我的訓練」進來的，回去也該回那裡（不是 gpu.html）。
    const back = document.querySelector('.minor a[href="gpu.html"]');
    if (back) {
        back.href = 'jobs.html';
        back.removeAttribute('data-i18n');
        back.textContent = T('jl_back', '回到我的訓練');
    }
    // ZH: 把送單那張卡整個收起來 —— 這條路不上傳、不設輪數、不送出。
    //     留著一顆按不了的按鈕比拿掉更讓人困惑。
    const card = document.querySelector('.primary-card');
    if (card) card.hidden = true;

    jobId = viewJobId;
    $('run').hidden = false;
    poll();
    // ZH: 已經跑完的單 poll() 一次就會 clearInterval，所以這裡照常起輪詢沒關係。
    polling = setInterval(poll, 3000);
}

// ZH: 目前的語言。**唯一定義** —— 散在各處自己取的話，總有一處會寫錯而且看不出來。
function currentLang() {
    try {
        return (window.Prefs && Prefs.get && Prefs.get().ui_lang) || 'zh';
    } catch {
        return 'zh';
    }
}

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
    // ZH: ⚠ 取語言是 `Prefs.get().ui_lang`。我原本寫成 `Prefs.lang()` ——
    //     那個函式**不存在**，於是這裡永遠走中文分支。
    //     中文模式下完全看不出來；英文模式才會出現「英文頁面配中文錯誤訊息」。
    const wantEn = currentLang() === 'en';
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
        // ZH: 只看模式下那張卡是收起來的，不要去動裡面的按鈕。
        if (!viewJobId) setGo({ label: T('tr_again', '再訓練一次'), enabled: true });
        picked = null;
        $('drop').classList.remove('drop--has');
        $('drop-main').textContent = T('tr_drop', '把 zip 拖到這裡，或點一下選檔案');
        $('drop-hint').textContent = T('tr_drop_sub', '只收 .zip，每人上限 2 GB');
        // ZH: v3.6 —— 模型檔已經由 worker 傳回服務層，可以下載了。
        //     `has_model` 由後端說了算，前端**不要自己猜**（訓練成功 ≠ 檔案送到了：
        //     傳輸可能失敗，那時模型還在運算主機上）。
        if (j.has_model) {
            // ZH: 🔴 **不能用純 `<a href download>`。**
            //     瀏覽器導覽只會帶 cookie，不會帶 Authorization header，
            //     而 token 在 sessionStorage —— 按下去必定 401。實測踩過。
            //     所以改成按鈕：用 fetch 帶 header 取回 blob 再存檔。
            //     ⚠ 也**不把 token 放進網址**：那會留在伺服器 log 與 referrer 裡。
            const acts = $('run-actions');
            acts.hidden = false;
            acts.innerHTML = `<button class="btn btn--minor" type="button" id="dl">` +
                             `${esc(T('tr_download', '下載模型檔'))}` +
                             `${j.model_bytes ? '（' + human(j.model_bytes) + '）' : ''}</button>`;
            $('dl').addEventListener('click', () => downloadModel($('dl')));
            if (!viewJobId) setNote(T('tr_done_note', '訓練完成，結果在下面。'));
        } else if (!viewJobId) {
            setNote(T('tr_done_no_model', '訓練完成，結果在下面。模型檔沒能傳回伺服器，' +
                                          '請把下面的訓練紀錄貼給管理者。'));
        }
    } else {
        if (!viewJobId) setGo({ label: T('tr_go', '開始訓練'), enabled: true });
        $('log-fold').hidden = false;
        $('log-fold').open = true;
        // ZH: 只看模式下 `#note` 在收起來的卡片裡，改用結果面板下方那一塊，
        //     不然失敗原因會整個看不到。
        (viewJobId ? setRunNote : setNote)(T('tr_failed_note', '這次沒有跑完') +
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
        const sep = currentLang() === 'en' ? ', ' : '、';
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

// ZH: 只看模式的訊息落點（送單那張卡是收起來的）。
function setRunNote(html) {
    const acts = $('run-actions');
    acts.hidden = false;
    acts.innerHTML = `<span class="inline-error">${html}</span>`;
}

// ZH: 取回模型檔並交給瀏覽器存檔。
// ZH: 為什麼要自己做而不是給一條連結：下載端點要 Authorization header，
//     而純連結導覽不會帶它（token 在 sessionStorage，不是 cookie）。
async function downloadModel(btn) {
    const original = btn.textContent;
    btn.disabled = true;
    btn.textContent = T('tr_downloading', '下載中…');
    try {
        const r = await fetch(`${API}/jobs/${jobId}/model`, { headers: authHeaders() });
        if (!r.ok) throw new Error(`HTTP ${r.status}`);

        // ZH: 檔名從 Content-Disposition 取，優先用 filename*（那份保得住中文）。
        const cd = r.headers.get('content-disposition') || '';
        let name = 'model.pt';
        const star = cd.match(/filename\*=UTF-8''([^;]+)/i);
        const plain = cd.match(/filename="([^"]+)"/i);
        if (star) { try { name = decodeURIComponent(star[1]); } catch { /* 壞掉就用下面那個 */ } }
        else if (plain) { name = plain[1]; }

        const url = URL.createObjectURL(await r.blob());
        const a = document.createElement('a');
        a.href = url;
        a.download = name;
        document.body.appendChild(a);
        a.click();
        a.remove();
        // ZH: 立刻 revoke 會讓某些瀏覽器來不及開始下載，隔一拍再放。
        setTimeout(() => URL.revokeObjectURL(url), 60000);
        btn.textContent = original;
    } catch (e) {
        btn.textContent = T('tr_download_fail', '下載失敗，請再試一次');
    } finally {
        btn.disabled = false;
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


/* ── 營運設定的補充說明（v3.8）──────────────────────────────────────
 * ZH: 這個數字是**管理者可以在營運設定裡改的**，所以不能寫死在 HTML ——
 *     寫死的話管理者調過之後，畫面上就是一個錯的數字，而且不會有人回報。
 *     值一律現取（Chrome.publicSettings 會在同一頁內快取）。
 *
 * ZH: 讀不到就**維持隱藏**，不要顯示「—」或 0。
 *     這是一句補充說明，缺了不影響這一頁本來要做的事；
 *     顯示一個假的 0 反而會被當成真的。
 * ------------------------------------------------------------------ */
function renderTimeoutNote(s) {
    const el = $('timeout-note');
    if (!el) return;
    const v = s && s['job_timeout_minutes'];
    if (v == null) { el.hidden = true; return; }
    el.textContent = T('tr_timeout_note', '單一任務最長跑 {n} 分鐘，超過會自動停止。').replace('{n}', v);
    el.hidden = false;
}

let PUB_SETTINGS = null;
Chrome.publicSettings().then((s) => { PUB_SETTINGS = s; renderTimeoutNote(s); });
// ZH: 文案是 JS 組出來的，沒有 data-i18n，字典掃描換不掉它 —— 語言改變時要自己重畫。
document.addEventListener('prefs:langchanged', () => renderTimeoutNote(PUB_SETTINGS));
