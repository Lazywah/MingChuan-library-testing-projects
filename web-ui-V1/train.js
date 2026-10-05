/* ==========================================================================
 * [畫面: 交給平台訓練] — 使用者在這裡要完成：把一包資料變成一個模型，
 *                        全程不寫程式。
 *
 * ZH: 這一頁只問三件事（哪一種、資料、幾輪），其餘由平台決定。會調 batch_size 的人
 *     本來就該去程式實驗室；不會調的人看到那些欄位只會卡住。
 * ZH: v4.19 —— 「哪一種」有三個：圖片分類、表格資料分類、文字分類（見 TASKS）。
 * ZH: v4.36 —— 「怎麼開始」也有三種：先體驗看看／用自己的資料／用自己的程式（見 MODE_SHOWS）。
 *     同一張表單，差別只在哪些欄位給人看、哪些已經替他決定好。
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
// ZH: v4.36 現在選的檔案是不是「這一種任務的範例」。體驗模式靠它判斷要不要重抓範例
//     （換了種類、或從別的方式切過來而手上是他自己的檔）。null＝不是範例。
let pickedIsSampleFor = null;
let mode = 'normal';      // ZH: v4.36 easy / normal / hard
// ZH: v4.38 全版遮罩「第一次、還沒選過」。🔴 **必須在這裡、而且宣告時就算好**：
//     下面 `if (TASKS[QS.get('task')]) setTask(...)` 在載入時就會跑 syncUrl，
//     宣告放在後面的話是 TDZ（直接 ReferenceError，整頁 JS 停擺）；
//     初值是 false 的話，遮罩還沒出現網址就被寫成 mode=normal，重新整理就跳過遮罩。
let pickerFirst = !viewJobId && !reuseId && !['easy', 'normal', 'hard'].includes(QS.get('mode'));
let LAST_JOB = null;      // ZH: 語言切換時重畫結果下方的說明用
// ZH: v3.6 使用者自帶的訓練程式（原始碼字串，不是檔案 —— 隨送單一起走）
let scriptSource = null;
let jobId = null;
let polling = null;
let finished = false;     // ZH: 目前這張單已到終態 —— 分頁回前景時不要再把輪詢開回來
let lastLogLen = 0;

// ── 訓練種類（v4.19）─────────────────────────────────────────────────
// ZH: 三種內建任務。**這裡是畫面上文案的真相**；後端認得哪些種類是
//     crud.BUILTIN_TASKS 說了算（多寫一種後端不認得的，送單會直接 400）。
// ZH: 每一種要換的東西：頁首那句、壓縮檔說明三段、失敗的常見原因、
//     範例檔、預設輪數。用 T() 一個個寫而不是塞成表，
//     是因為 scripts/check_i18n.py 靠 `T('key', '中文')` 的形狀找「用到的 key」。
const TASKS = {
    image_classification: {
        sub1:     () => T('tr_sub1', '上傳一包分好類的圖片，平台幫你訓練，不用寫程式。'),
        fmtP:     () => T('tr_fmt_p', '每個類別一個資料夾，圖片放進去，整包壓成 zip。資料夾的名字就是類別的名字。'),
        tree:     () => T('tr_tree', '我的資料.zip\n├── 貓/\n│   ├── 001.jpg\n│   └── 002.jpg\n└── 狗/\n    ├── 001.jpg\n    └── 002.jpg'),
        fmtNote:  () => T('tr_fmt_note', '外面多包一層資料夾也沒關係，平台會自己往下找。至少要兩個類別。'),
        failHint: () => T('tr_failed_hint', '常見原因：類別少於兩個、或圖片太少。'),
        sampleName: () => T('tr_sample_name_image', '範例_貓狗圖片.zip'),
        keys: { sub1: 'tr_sub1', fmtP: 'tr_fmt_p', tree: 'tr_tree', fmtNote: 'tr_fmt_note' },
        epochs: 10,
        // ZH: v4.36 體驗模式的三行。時間是實測（2026-10-02 正式環境的完成紀錄：
        //     送出到完成中位數 30 秒、最長 46 秒），不是估計。
        easyWhat: () => T('tr_easy_what_image', '分辨照片裡是貓還是狗'),
        easyData: () => T('tr_easy_data_image', '平台準備好的範例：500 張貓、500 張狗'),
        easyTime: () => T('tr_easy_time_image', '練 10 輪，通常不到一分鐘'),
        // ZH: 程式實驗室裡做同樣事情的範例（檔名不翻譯）。
        learnFile: 'sample_cats_dogs.py', learnData: 'cat_dog_data/',
    },
    tabular_classification: {
        sub1:     () => T('tr_sub1_tabular', '上傳一份表格（CSV），其中一欄是答案，平台幫你訓練一個會預測那一欄的模型。'),
        fmtP:     () => T('tr_fmt_p_tabular', 'zip 裡放一個 CSV。每一列一筆資料，每一欄一個特徵，其中一欄是答案（叫 label，或放在最後一欄）。'),
        tree:     () => T('tr_tree_tabular', '學生資料.zip\n└── students.csv\n      study_hours,attendance,midterm,label\n      3.5,0.9,72,pass\n      1.0,0.4,40,fail'),
        fmtNote:  () => T('tr_fmt_note_tabular', '數字欄照用、文字欄自動轉成類別、缺值自動補。至少要兩種答案，每種至少幾十筆。Excel 請「另存新檔 → CSV UTF-8」。'),
        failHint: () => T('tr_failed_hint_tabular', '常見原因：答案欄只有一種值、資料太少、或 CSV 不是 UTF-8。'),
        sampleName: () => T('tr_sample_name_tabular', '範例_學生及格預測.zip'),
        keys: { sub1: 'tr_sub1_tabular', fmtP: 'tr_fmt_p_tabular', tree: 'tr_tree_tabular', fmtNote: 'tr_fmt_note_tabular' },
        // ZH: 表格小、每輪只有幾十步，10 輪常常還沒收斂；30 輪也只要幾秒。
        epochs: 30,
        easyWhat: () => T('tr_easy_what_tabular', '預測學生會不會及格'),
        easyData: () => T('tr_easy_data_tabular', '平台準備好的範例：320 位學生的讀書時數、出席率與成績'),
        easyTime: () => T('tr_easy_time_tabular', '練 30 輪，大約十幾秒'),
        learnFile: 'sample_tabular.py', learnData: 'students.csv',
    },
    text_classification: {
        sub1:     () => T('tr_sub1_text', '上傳一份句子與答案的表格（CSV），平台幫你訓練一個會分類句子的模型。'),
        fmtP:     () => T('tr_fmt_p_text', 'zip 裡放一個 CSV，兩欄：句子（text）與答案（label）。中英文都可以。'),
        tree:     () => T('tr_tree_text', '評論.zip\n└── reviews.csv\n      text,label\n      這家店的服務很好，會再來,正面\n      等了四十分鐘餐還沒來,負面'),
        fmtNote:  () => T('tr_fmt_note_text', '至少要兩種答案，每種至少幾十句。不用下載任何語言模型，中文逐字、英文逐字學。'),
        failHint: () => T('tr_failed_hint_text', '常見原因：答案欄只有一種值、句子太少、或 CSV 只有一欄。'),
        sampleName: () => T('tr_sample_name_text', '範例_餐廳評論情緒.zip'),
        keys: { sub1: 'tr_sub1_text', fmtP: 'tr_fmt_p_text', tree: 'tr_tree_text', fmtNote: 'tr_fmt_note_text' },
        epochs: 20,
        easyWhat: () => T('tr_easy_what_text', '判斷餐廳評論是正面還是負面'),
        easyData: () => T('tr_easy_data_text', '平台準備好的範例：240 則餐廳評論'),
        easyTime: () => T('tr_easy_time_text', '練 20 輪，大約十幾秒'),
        learnFile: 'sample_text.py', learnData: 'reviews.csv',
    },
};
let task = 'image_classification';

// ZH: 切換種類 → 換文案、換預設輪數。已經選好的檔案**不清掉**：
//     使用者常是先選了檔再發現種類不對，清掉等於罰他重選一次。
function setTask(t) {
    if (!TASKS[t]) return;
    task = t;
    const c = TASKS[t];
    // ZH: v4.38 左側分頁（roving tabindex：只有選中的那一個在 Tab 順序裡）。
    taskTabs().forEach((b) => {
        const on = b.dataset.task === t;
        b.setAttribute('aria-selected', String(on));
        b.tabIndex = on ? 0 : -1;
    });
    // ZH: 同時改 data-i18n 與文字：prefs.js 換語言時是重掃 data-i18n，
    //     只改文字的話，一切換語言就會跳回圖片那一版。
    const targets = [['tr-sub1', 'sub1'], ['fmt-p', 'fmtP'], ['tree', 'tree'], ['fmt-note', 'fmtNote']];
    targets.forEach(([id, key]) => {
        $(id).setAttribute('data-i18n', c.keys[key]);
        $(id).textContent = c[key]();
    });
    $('epochs').value = c.epochs;
    // ZH: v4.36 副標題依方式而定（體驗／自己的程式各有一句），蓋掉上面那一行。
    renderSub();
    // ZH: 體驗模式換了種類 → 範例也要換成那一種的。
    if (mode === 'easy') { renderEasy(); loadSample(); }
    syncUrl();
}
function taskTabs() { return [...document.querySelectorAll('#task-tabs [role="tab"]')]; }
$('task-tabs').addEventListener('click', (e) => {
    const b = e.target.closest('[role="tab"]');
    if (b) setTask(b.dataset.task);
});
// ZH: 分頁的鍵盤操作：上下（窄畫面是左右）換一個、Home／End 到頭尾，換了就選（自動啟用）。
$('task-tabs').addEventListener('keydown', (e) => {
    const tabs = taskTabs();
    const i = tabs.indexOf(document.activeElement);
    if (i < 0) return;
    const step = { ArrowDown: 1, ArrowRight: 1, ArrowUp: -1, ArrowLeft: -1 }[e.key];
    let j = null;
    if (step) j = (i + step + tabs.length) % tabs.length;
    else if (e.key === 'Home') j = 0;
    else if (e.key === 'End') j = tabs.length - 1;
    if (j === null) return;
    e.preventDefault();
    setTask(tabs[j].dataset.task);
    tabs[j].focus();
});
// ZH: 網址帶 ?task=<種類>（選過之後 syncUrl 寫的、舊入口頁的連結、書籤）就預選同一種。
//     不認得的值就維持預設（圖片），不報錯。
if (TASKS[QS.get('task')]) setTask(QS.get('task'));

// ZH: 範例資料：抓靜態 zip 回來當成使用者選的檔案，之後走**同一條**上傳路。
//     檔名用翻譯過的名字（會變成任務名與「我的資料集」裡的名字）。
// ZH: v4.36 抽成 loadSample()：體驗模式一進來就自動抓（接管者：「用平台準備好的範例」
//     那顆鈕不夠明顯 —— 對初學者來說那正是主要動作，所以乾脆替他按）。
// ZH: v4.38 只有「先體驗看看」會用到（範例鈕拿掉了，見 train.html）。
async function loadSample() {
    const want = task;
    if (pickedIsSampleFor === want && picked) return;      // ZH: 手上已經是這一種的範例
    setGo({ label: T('tr_sample_loading', '正在取得範例…'), enabled: false });
    try {
        const r = await fetch(`samples/${want}.zip`, { cache: 'force-cache' });
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        const blob = await r.blob();
        // ZH: 抓的時候他又換了一種 —— 丟掉這份；新的那一次會自己抓。
        if (want !== task) return;
        choose(new File([blob], TASKS[want].sampleName(), { type: 'application/zip' }), want);
    } catch {
        setNote(T('tr_sample_fail', '範例暫時拿不到，請稍後再試，或上傳自己的資料。'));
        refreshGo();
    }
}

// ZH: 把手上的檔案清掉、上傳區回到空白。
function clearPicked() {
    picked = null;
    pickedIsSampleFor = null;
    $('drop').classList.remove('drop--has');
    $('drop-main').textContent = T('tr_drop', '把 zip 拖到這裡，或點一下選檔案');
    $('drop-hint').textContent = T('tr_drop_sub', '只收 .zip，每人上限 2 GB');
}

// ══════════════════════════════════════════════════════════════════════
// ZH: v4.36 三種方式（擁有者 2026-10-02，接管者回饋 2026-09-30）
// ══════════════════════════════════════════════════════════════════════
// ZH: 每個區塊在哪幾種方式出現。**這張表是唯一的真相**——不要在別處另外 hidden 這些元素，
//     不然切換方式時兩邊的規則會打架（某一塊切過去就再也出不來）。
//       easy   —— 只剩「要訓練什麼／資料／要多久」三行和開始鈕；範例自動載入
//       normal —— 原本的完整表單，少了自帶程式
//       hard   —— 不分種類（跑的是他自己的程式），自帶程式一進來就展開
const MODES = ['easy', 'normal', 'hard'];
const MODE_SHOWS = {
    'side-tasks':    ['easy', 'normal'],   // ZH: 用自己的程式不分種類（後端有 script_source 就不看）
    'easy-box':      ['easy'],
    'fmt-fold':      ['normal'],
    'drop':          ['normal', 'hard'],
    'epochs-field':  ['normal', 'hard'],
    'own-fold':      ['hard'],
};

// ZH: 「目前的方式」那一行的名字。用 T() 一個個寫是為了 check_i18n 抓得到 key。
//     key 也寫完整（不要 'tr_mode_' + m）：拼出來的 key check_i18n 驗不到。
const MODE_NAME = {
    easy:   { key: 'tr_mode_easy',   text: () => T('tr_mode_easy', '先體驗看看') },
    normal: { key: 'tr_mode_normal', text: () => T('tr_mode_normal', '用自己的資料') },
    hard:   { key: 'tr_mode_hard',   text: () => T('tr_mode_hard', '用自己的程式') },
};

function setMode(m) {
    if (!MODES.includes(m)) m = 'normal';
    mode = m;
    const name = $('mode-now-name');
    name.setAttribute('data-i18n', MODE_NAME[m].key);
    name.textContent = MODE_NAME[m].text();
    Object.entries(MODE_SHOWS).forEach(([id, modes]) => {
        const el = $(id);
        if (el) el.hidden = !modes.includes(m);
    });
    // ZH: v4.38 範例只屬於「先體驗看看」—— 離開體驗模式時手上的範例要清掉，
    //     不然「用自己的資料」會拿著範例送出去。
    if (m !== 'easy' && pickedIsSampleFor) clearPicked();
    renderSub();
    // ZH: 先算開始鈕，再抓範例 —— 反過來的話「正在取得範例…」會馬上被蓋回「開始訓練」。
    refreshGo();
    if (m === 'easy') { renderEasy(); loadSample(); }
    syncUrl();
}

// ZH: 網址跟著換（replaceState，不多一筆歷史）—— 重新整理時停在同一種方式與種類。
//     **方式與種類兩邊都要呼叫**：只在換方式時寫的話，體驗模式按「換一種範例」換成表格，
//     網址還停在圖片，一重新整理就跳回貓狗（2026-10-02 實測抓到）。
//     看結果（?job=）與重用資料集（?dataset=）兩條路不動網址：那裡的 id 才是重點。
function syncUrl() {
    // ZH: 遮罩還沒選（pickerFirst）時不寫 —— 否則底下先墊的 normal 會進網址，
    //     一重新整理就跳過遮罩，等於替他選了「用自己的資料」。
    if (viewJobId || reuseId || pickerFirst) return;
    try {
        const u = new URL(location.href);
        u.searchParams.set('task', task);
        u.searchParams.set('mode', mode);
        history.replaceState(null, '', u.toString());
    } catch { /* ZH: 改不了網址不影響這一頁 */ }
}

// ZH: 副標題。體驗與自己的程式各有一句；用自己的資料沿用種類那一句。
//     同時改 data-i18n：prefs.js 換語言時是重掃 data-i18n。
function renderSub() {
    const el = $('tr-sub1');
    if (mode === 'easy') {
        el.setAttribute('data-i18n', 'tr_sub1_easy');
        el.textContent = T('tr_sub1_easy', '用平台準備好的範例，按一下「開始訓練」就好。');
    } else if (mode === 'hard') {
        el.setAttribute('data-i18n', 'tr_sub1_hard');
        el.textContent = T('tr_sub1_hard', '上傳你的訓練程式和一份資料，平台用學校的 GPU 幫你跑。');
    } else {
        const c = TASKS[task];
        el.setAttribute('data-i18n', c.keys.sub1);
        el.textContent = c.sub1();
    }
}

function renderEasy() {
    const c = TASKS[task];
    $('easy-what').textContent = c.easyWhat();
    $('easy-data').textContent = c.easyData();
    $('easy-time').textContent = c.easyTime() + T('tr_easy_queue', '（GPU 忙的時候要先排隊）');
}

// ZH: 開始鈕能不能按，**只在這裡算**。訓練進行中不碰（那時的字是「訓練中…」）。
function refreshGo() {
    if (jobId && !finished) return;
    const ready = !!(picked || reuseId) && (mode !== 'hard' || !!scriptSource);
    setGo({ label: T('tr_go', '開始訓練'), enabled: ready });
}

// ZH: 結果下方「想看看剛才那支程式？」—— 只有內建程式訓練、而且完成的單才出現。
//     純說明，不放連結（擁有者 2026-10-02）。檔名不翻譯。
function renderLearnCode(j) {
    LAST_JOB = j;
    const box = $('learn-code');
    const c = j && TASKS[j.task];
    if (!c || j.status !== 'completed') { box.hidden = true; return; }
    $('learn-d').textContent = T('tr_learn_d',
        '剛才幫你訓練的是平台內建的程式。程式實驗室裡有一份做同樣事情的範例：到首頁的「程式實驗室」，按「啟動並開啟實驗室」，左邊 projects 資料夾裡的 {f} 就是（資料是旁邊的 {d}）。在檔案上按右鍵 →「Run on GPU」就會在 GPU 上跑一次；可以改裡面的數字（例如 EPOCHS），再跑看看結果有什麼不同。')
        .replace('{f}', c.learnFile).replace('{d}', c.learnData);
    box.hidden = false;
}

// ══════════════════════════════════════════════════════════════════════
// ZH: v4.38 全版遮罩三選一（擁有者 2026-10-05）。HTML 註解寫了為什麼第一次不能關。
// ══════════════════════════════════════════════════════════════════════
let pickerReturn = null;    // ZH: 關掉後焦點回到哪裡

function pickerOptions() { return [...document.querySelectorAll('#mpick .mpick__opt')]; }

function openPicker(first) {
    pickerFirst = !!first;
    const box = $('mpick');
    $('mpick-x').hidden = pickerFirst;
    $('mpick-foot').hidden = !pickerFirst;
    const kindName = document.querySelector(`#task-tabs [data-task="${task}"] .tr-tab__name`);
    $('mpick-sub').textContent = T('tr_pick_sub', '目前要練：{k}（可以在「要練哪一種」分頁換）。開始的方式選好之後，隨時可以按「重新選擇模式」再換。')
        .replace('{k}', kindName ? kindName.textContent.trim() : task);
    pickerOptions().forEach((b) => {
        const cur = !pickerFirst && b.dataset.mode === mode;
        b.classList.toggle('is-current', cur);
        if (cur) b.setAttribute('aria-current', 'true'); else b.removeAttribute('aria-current');
    });
    pickerReturn = pickerFirst ? null : document.activeElement;
    box.hidden = false;
    const target = pickerOptions().find((b) => b.classList.contains('is-current')) || pickerOptions()[0];
    if (target) target.focus();
}

function closePicker() {
    $('mpick').hidden = true;
    if (pickerReturn && pickerReturn.focus) pickerReturn.focus();
    pickerReturn = null;
}

$('mpick').addEventListener('click', (e) => {
    const b = e.target.closest('.mpick__opt');
    if (b) {
        const first = pickerFirst;
        pickerFirst = false;          // ZH: 先清掉，setMode 裡的 syncUrl 才會把選擇寫進網址
        setMode(b.dataset.mode);
        closePicker();
        // ZH: 第一次選完把焦點交給表單的第一個可按的東西，不要掉回 body 頂端。
        if (first) ($('go').disabled ? $('mode-reopen') : $('go')).focus();
        return;
    }
    // ZH: 點遮罩（不是點盒子裡面）＝關閉；第一次不行（見 HTML 註解）。
    if (!pickerFirst && (e.target === e.currentTarget || e.target.id === 'mpick-x')) closePicker();
});

// ZH: Esc 關閉、Tab 留在框裡（aria-modal 只是告訴讀屏，鍵盤要自己圈）。
$('mpick').addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && !pickerFirst) { e.preventDefault(); closePicker(); return; }
    if (e.key !== 'Tab') return;
    const items = [...$('mpick').querySelectorAll('button, a[href]')].filter((el) => el.offsetParent !== null);
    if (!items.length) return;
    const first = items[0], last = items[items.length - 1];
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
});

$('mode-reopen').addEventListener('click', () => openPicker(false));

// ══════════════════════════════════════════════════════════════════════
// ZH: v4.36 上傳一張圖片試試看（接管者回饋 2026-09-30 ①；後端 /jobs/{id}/try，服務層 CPU 推論）
// ══════════════════════════════════════════════════════════════════════
// ZH: 只有內建程式訓練、而且有模型檔的圖片任務才出現 —— 後端也會擋（409），
//     這裡不畫是為了不讓人按了才知道不能用。
let tryUrl = null;          // ZH: 預覽圖的 object URL（換下一張時要放掉，不然一直漏記憶體）

function renderTry(j) {
    const ok = j && j.status === 'completed' && j.task === 'image_classification' && j.has_model;
    $('try-box').hidden = !ok;
}

async function tryImage(file) {
    if (!file || !jobId) return;
    $('try-err').hidden = true;
    if (!/^image\//.test(file.type || '')) {
        $('try-err').textContent = T('tr_try_not_image', '這不是圖片檔，請選 JPG 或 PNG。');
        $('try-err').hidden = false;
        return;
    }
    if (tryUrl) URL.revokeObjectURL(tryUrl);
    tryUrl = URL.createObjectURL(file);
    $('try-img').src = tryUrl;
    $('try-out').hidden = false;
    $('try-label').textContent = T('tr_try_busy', '判斷中…');
    $('try-bars').innerHTML = '';
    try {
        const fd = new FormData();
        fd.append('file', file, file.name);
        const r = await fetch(`${API}/jobs/${encodeURIComponent(jobId)}/try`,
                              { method: 'POST', headers: authHeaders(), body: fd });
        const body = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(clean(detailText(body.detail)) || `HTTP ${r.status}`);
        $('try-label').textContent = T('tr_try_result', '模型判斷：{c}（{p}% 有把握）')
            .replace('{c}', body.label).replace('{p}', Math.round(body.confidence * 100));
        // ZH: 每一類都畫一條 —— 只給最高的那一個，會讓人以為模型「確定」；
        //     看到 55% 對 45%，才知道它其實很猶豫。
        $('try-bars').innerHTML = (body.scores || []).map((s) => `
            <div class="try__row">
                <span class="try__k">${esc(s.label)}</span>
                <span class="try__bar"><span style="width:${Math.round(s.p * 100)}%"></span></span>
                <span class="try__v">${Math.round(s.p * 100)}%</span>
            </div>`).join('');
    } catch (e) {
        $('try-label').textContent = '';
        $('try-err').textContent = T('tr_try_fail', '這次沒判斷成功') + `（${e.message}）`;
        $('try-err').hidden = false;
    }
}

$('try-drop').addEventListener('click', () => $('try-file').click());
$('try-drop').addEventListener('keydown', (e) => {
    if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); $('try-file').click(); }
});
$('try-file').addEventListener('change', (e) => { tryImage(e.target.files[0]); e.target.value = ''; });
['dragenter', 'dragover'].forEach((ev) => $('try-drop').addEventListener(ev, (e) => {
    e.preventDefault(); $('try-drop').classList.add('drop--over');
}));
['dragleave', 'drop'].forEach((ev) => $('try-drop').addEventListener(ev, (e) => {
    e.preventDefault(); $('try-drop').classList.remove('drop--over');
}));
$('try-drop').addEventListener('drop', (e) => tryImage(e.dataTransfer.files[0]));

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
function choose(file, sampleTask = null) {
    if (!file) return;
    if (!/\.zip$/i.test(file.name)) {
        // ZH: 在**選檔當下**就講，不要等按了開始訓練、上傳完才退回來。
        setNote(T('tr_not_zip', '這不是 zip 檔。請把整個資料夾壓成 .zip 再上傳。'));
        picked = null;
        pickedIsSampleFor = null;
        refreshGo();
        return;
    }
    picked = file;
    pickedIsSampleFor = sampleTask;
    setNote('');
    $('drop-main').textContent = file.name;
    $('drop-hint').textContent = human(file.size);
    $('drop').classList.add('drop--has');
    refreshGo();
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
    refreshGo();
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
    if (mode === 'hard' && !scriptSource) return;
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
                // ZH: v4.36 只有「用自己的程式」才送 —— 他在那邊選了 .py 又切回別的方式的話，
                //     不能默默跑他的程式而不是他現在選的那一種。
                ...(mode === 'hard' && scriptSource ? { script_source: scriptSource } : {}),
                // ZH: 種類寫明。不寫也會落到預設，但寫出來的話**日後多一種任務時
                //     這張舊單仍然指向同一支腳本**，不會跟著預設值漂走。
                // ZH: v4.38 用自己的程式不送種類（沒有「要練哪一種」，後端也不看）。
                config: Object.assign({ epochs: epochs }, mode === 'hard' ? {} : { task: task }),
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
        finished = false;
        lastLogLen = 0;
        // ZH: v4.36 —— 「再訓練一次」時上一輪的下載鈕與模型說明要收起來，
        //     不然新的一輪還在排隊，畫面上卻掛著上一輪的模型。
        $('run-actions').hidden = true;
        $('model-help').hidden = true;
        $('learn-code').hidden = true;
        $('try-box').hidden = true;
        $('try-out').hidden = true;
    } catch (e) {
        setNote(T('tr_submit_fail', '送不出去') + `（${clean(e.message)}）`);
        setGo({ label: T('tr_go', '開始訓練'), enabled: true });
        return;
    }

    setGo({ label: T('tr_running', '訓練中…'), enabled: false });
    $('run').hidden = false;
    $('run').scrollIntoView({ behavior: 'smooth', block: 'start' });
    poll();
    startPolling();
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
else {
    initReuse();
    // ZH: v4.38 方式：重用資料集一律「用自己的資料」（資料已經有了，不問）；
    //     網址帶了 ?mode=（選過之後 syncUrl 寫的、或書籤）就照它；
    //     都沒有＝一進來就蓋上全版遮罩讓他選。底下先墊 normal 把表單畫好，選完再換。
    const qm = QS.get('mode');
    if (reuseId) setMode('normal');
    else if (MODES.includes(qm)) setMode(qm);
    else { pickerFirst = true; setMode('normal'); openPicker(true); }
}


// ── 只看既有任務 ─────────────────────────────────────────────────────
function initViewMode() {
    // ZH: 從「我的訓練」進來的，回去也該回那裡（不是首頁）。
    $('tr-back-row').hidden = false;
    // ZH: 只看結果時沒有表單，側欄（方式、種類）也沒有意義 —— 收起來。
    $('tr-side').hidden = true;
    // ZH: 把送單那張卡整個收起來 —— 這條路不上傳、不設輪數、不送出。
    //     留著一顆按不了的按鈕比拿掉更讓人困惑。
    const card = document.querySelector('.primary-card');
    if (card) card.hidden = true;

    jobId = viewJobId;
    $('run').hidden = false;
    poll();
    // ZH: 已經跑完的單 poll() 一次就會 clearInterval，所以這裡照常起輪詢沒關係。
    startPolling();
}

// ── 輪詢的開關 ───────────────────────────────────────────────────────
// ZH: v4.19 —— 分頁切到背景就停，回到前景再問一次並重新開始。
//     原本這一頁每 3 秒問一次而且**永遠不停**：一個開著沒關的分頁一小時就是
//     1200 個請求，而 2026-09-20 一台校外電腦就是因為這種節奏被邊界防火牆
//     當成 DoS 攔下來（整個 IP 被封，連首頁都開不了）。jobs.js 早就這樣做，這裡漏了。
function startPolling() {
    if (!polling && jobId && !finished) polling = setInterval(poll, 3000);
}

function stopPolling() {
    if (polling) { clearInterval(polling); polling = null; }
}

document.addEventListener('visibilitychange', () => {
    if (document.hidden) { stopPolling(); return; }
    if (jobId && !finished) { poll(); startPolling(); }
});

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
        stopPolling();
        // ZH: 終態之後 visibilitychange 也不該再把輪詢開回來 —— jobId 留著給下載用，
        //     所以用一個旗標擋。
        finished = true;
        finish(j);
    }
}

// ══════════════════════════════════════════════════════════════════════
// ZH: v4.36 模型檔說明（接管者回饋 2026-09-30 ②）
// ══════════════════════════════════════════════════════════════════════
// ZH: 原本下載鈕旁邊**一個字都沒有**，只有檔案大小 —— 初學者拿到一個 .pt 不知道能做什麼。
// ZH: 三種情況講法不同，靠後端的 `task`（自帶程式的單是 null）判斷：
//       圖片 —— 架構是 torchvision 的 ResNet-18，給一段**真的跑得動**的載入程式
//       表格／文字 —— 架構是內建腳本自己定義的，光有權重載不起來；
//                     不硬塞一段跑不動的程式，指向實驗室裡有完整定義的範例
//       自帶程式 —— 格式是他自己的程式決定的，平台講不出更多
// ZH: 🔴 範例程式碼**不進字典**：程式碼不翻譯，而且字典裡放多行字串很難維護。
//     它必須與 gpu-worker/builtin_scripts/image_classification.py 存的格式一致
//     （state_dict / classes / img_size，ImageNet 的 Normalize）—— 那邊改了這裡要跟著改。
const MODEL_SNIPPET_IMAGE = `import torch
from torch import nn
from torchvision import models, transforms
from PIL import Image

ckpt = torch.load("model.pt", map_location="cpu")
model = models.resnet18()
model.fc = nn.Linear(model.fc.in_features, len(ckpt["classes"]))
model.load_state_dict(ckpt["state_dict"])
model.eval()

tf = transforms.Compose([
    transforms.Resize((ckpt["img_size"], ckpt["img_size"])),
    transforms.ToTensor(),
    transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
])
x = tf(Image.open("photo.jpg").convert("RGB")).unsqueeze(0)
with torch.no_grad():
    print(ckpt["classes"][model(x).argmax(1).item()])`;

function renderModelHelp(j) {
    const box = $('model-help');
    if (!box) return;
    const lab = { tabular_classification: 'sample_tabular.py', text_classification: 'sample_text.py' };
    if (j.task === 'image_classification') {
        box.innerHTML =
            `<p class="footnote">${esc(T('tr_model_what_image',
                '這是剛訓練好的模型（ResNet-18）。可以在自己的 Python 程式裡載入，拿新的照片讓它判斷是哪一類。'))}</p>` +
            `<details class="fold"><summary class="fold__summary">${esc(T('tr_model_how', '下載之後怎麼用'))}</summary>` +
            `<div class="fold__body"><p class="footnote">${esc(T('tr_model_how_note',
                '把 photo.jpg 換成你的照片，和 model.pt 放在同一個資料夾。需要 torch、torchvision、Pillow，程式實驗室裡都已經裝好了。'))}</p>` +
            `<pre class="diag">${esc(MODEL_SNIPPET_IMAGE)}</pre></div></details>`;
    } else if (lab[j.task]) {
        box.innerHTML = `<p class="footnote">${esc(T('tr_model_what_builtin',
            '這是剛訓練好的模型。它的結構是平台內建程式自己定義的，載入時要用同一份定義 —— 程式實驗室 projects 資料夾裡的 {f} 有完整寫法。')
            .replace('{f}', lab[j.task]))}</p>`;
    } else {
        box.innerHTML = `<p class="footnote">${esc(T('tr_model_what_own',
            '這是你的程式存到 OUTPUT_DIR 的檔案，格式由你的程式決定。'))}</p>`;
    }
    box.hidden = false;
}

function finish(j) {
    if (j.status === 'completed') {
        setBar(100);
        clearPicked();
        // ZH: 只看模式下那張卡是收起來的，不要去動裡面的按鈕。
        // ZH: 🔴 v4.36 修：原本這裡一律 enabled:true，但上面剛把 picked 清掉 ——
        //     「再訓練一次」按下去在 click 第一行就 return，**什麼都不會發生**。
        //     現在：體驗模式自動把範例抓回來；其他方式要等他重新選檔（重用資料集的不受影響）。
        if (!viewJobId) {
            setGo({ label: T('tr_again', '再訓練一次'), enabled: !!reuseId });
            if (mode === 'easy') loadSample();
        }
        renderLearnCode(j);
        renderTry(j);
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
            renderModelHelp(j);
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
        // ZH: 「常見原因」要對種類講：後端回的 `task` 是派工時判定的那一個
        //     （自帶程式的單是 null —— 那時候講「類別太少」是在猜，不講）。
        const hint = TASKS[j.task] ? ' ' + TASKS[j.task].failHint() : '';
        (viewJobId ? setRunNote : setNote)(T('tr_failed_note', '這次沒有跑完') +
                (j.error_message ? `（${clean(j.error_message)}）` : '') + hint);
    }
}

// ── 指標 ─────────────────────────────────────────────────────────────
// ZH: 每輪結果一次顯示幾列（擁有者 2026-09-24）。
//     🔴 **這是唯一的真相**：高度由 fitEpochBox() 依實際列高算出來，
//     文案裡的數字也用它。styles.css 的 max-height 只是 JS 還沒跑之前的保底。
const EPOCH_ROWS = 10;

/* ZH: 把捲動框調成「剛好十列 + 表頭」。
 *
 * ZH: 為什麼要用量的，不能在 CSS 裡寫死：列高不會跟著字級等比例變 ——
 *     字是 rem，但上下 padding（--space-2）是固定的 px。
 *     實測把字級放大到 130%，用 rem 算出來的框會露出 11 列，
 *     而下面的說明還寫著「一次顯示 10 輪」。
 * ZH: ⚠ 一列都沒有時什麼都不做（量不到列高，算出來會是表頭的高度）。
 */
function fitEpochBox() {
    const box = $('epochs-table');
    const head = box.querySelector('thead');
    const row = box.querySelector('tbody tr');
    if (!head || !row) return;
    box.style.maxHeight = (head.getBoundingClientRect().height
        + row.getBoundingClientRect().height * EPOCH_ROWS) + 'px';
}

// ZH: 字級是隨時可以改的（帳號選單裡的滑條）。改完不重算的話，
//     已經畫好的那張表會停在舊高度 —— 跑完的單不會再重畫，就一直錯著。
// ZH: 既有前例：prefs.js 在套用之後會發 `prefs:applied`。
document.addEventListener('prefs:applied', fitEpochBox);
// ZH: 後端的 metrics 是一個陣列，每筆有 kind：dataset（開頭一次）、
//     epoch（每輪）、summary（結尾）。畫面只讀，不做計算以外的假設——
//     多出不認得的 kind 就忽略，不要壞掉。
// ZH: 🔴 這幾張卡是 JS 組出來的字串，**沒有 data-i18n** —— 切語言時
//     字典掃描換不掉它們，畫面會停在舊語言。跑到一半的單下一次輪詢會
//     自己重畫，但**跑完的單不會再輪詢**，於是那一頁就一直是舊語言。
// ZH: 既有前例：同一個檔案的 renderTimeoutNote 已經這樣處理了
//     （那段註解把理由寫得很清楚），這裡補上同一條。
let LAST_METRICS = null;
document.addEventListener('prefs:langchanged', () => {
    if (LAST_METRICS) renderMetrics(LAST_METRICS);
});

function renderMetrics(metrics) {
    LAST_METRICS = metrics;
    const ds = metrics.filter((m) => m.kind === 'dataset').pop();
    const sum = metrics.filter((m) => m.kind === 'summary').pop();
    const eps = metrics.filter((m) => m.kind === 'epoch');
    // ZH: v4.36 判斷錯的那幾筆（內建腳本訓練完才有；自帶程式不會回報）。
    renderMistakes(metrics.filter((m) => m.kind === 'mistakes').pop());

    const cards = [];
    if (ds) {
        // ZH: 頓號是中文的列舉符號；英文模式要用逗號。這種字元層級的東西
        //     字典掃描抓不到——它不是一個 key，是一個 join 的參數。
        const sep = currentLang() === 'en' ? ', ' : '、';
        // ZH: 圖片任務回 images、表格／文字任務回 samples —— 用哪個欄位存在來決定
        //     要寫「張圖片」還是「筆資料」，不另外查任務種類（指標自己就說得清）。
        const count = ds.images != null
            ? T('tr_m_images', '{n} 張圖片').replace('{n}', ds.images)
            : T('tr_m_samples', '{n} 筆資料').replace('{n}', ds.samples ?? '—');
        cards.push([T('tr_m_classes', '類別'), (ds.classes || []).join(sep) || '—', count]);
    }
    const best = sum ? sum.best_val_accuracy
                     : (eps.length ? Math.max(...eps.map((e) => e.val_accuracy)) : null);
    if (best != null) {
        const onImages = !ds || ds.images != null;
        // ZH: 🔴 這個數字是**最佳的那一輪**，不是最後一輪 —— 標題要講出來。
        //     內建腳本只在正確率變好時才覆寫 model.pt（三支都是
        //     `if acc >= best_acc: torch.save(...)`），所以「最佳」與
        //     「你下載到的那個模型」指的是同一件事。不寫「最佳」的話，
        //     看到清單裡最後一輪比較低的人會以為數字灌水了
        //     （擁有者 2026-09-24 就是這樣問的）。
        cards.push([T('tr_m_acc', '最佳正確率'), (best * 100).toFixed(1) + '%',
                    onImages ? T('tr_m_acc_sub', '在沒看過的圖片上；下載的模型就是這一輪的')
                             : T('tr_m_acc_sub_rows', '在沒看過的資料上；下載的模型就是這一輪的')]);
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
    // ZH: 超過十輪才提示總數 —— 十輪以內整份都看得到，寫了只是雜訊。
    const note = $('epochs-note');
    note.hidden = eps.length <= EPOCH_ROWS;
    if (!note.hidden) {
        note.textContent = T('tr_epochs_more',
            '共 {n} 輪。這裡一次顯示 {k} 輪，其餘往下捲。')
            .replace('{n}', eps.length).replace('{k}', EPOCH_ROWS);
    }
    if (eps.length) {
        // ZH: 🔴 訓練中每次輪詢都會重畫這張表，而**新的一列加在最下面**。
        //     有了捲動框之後，正在跑的時候最該看的那一列會落在框外 ——
        //     所以重畫前先記住「剛剛是不是貼著底」，重畫後再貼回去。
        // ZH: ⚠ 只有原本就在底部時才捲（差 4px 內算貼著）。
        //     無條件捲的話，使用者往上翻看第 3 輪時會被硬拉回來，
        //     而那是每 3 秒一次 —— 等於根本翻不了。
        const box = $('epochs-table');
        const stuck = box.scrollHeight - box.scrollTop - box.clientHeight < 4;
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
        // ZH: ⚠ 順序：先量高度再還原捲動位置 —— 反過來的話
        //     scrollTop 會被還沒定案的高度夾掉。
        fitEpochBox();
        if (stuck) box.scrollTop = box.scrollHeight;
    }
}

// ZH: v4.36 「模型判斷錯的」。資料內容是使用者自己上傳的 —— 一律 esc()，不信任。
//     m.items 最多 10 筆（腳本端 MISTAKES_MAX），m.wrong 是真正錯了幾筆。
function renderMistakes(m) {
    const box = $('mistakes');
    if (!m) { box.hidden = true; return; }
    const items = m.items || [];
    const tpl = m.wrong === 0
        ? T('tr_mis_none', '驗證資料 {n} 筆，模型全部判斷正確。')
        : (items.length < m.wrong
            ? T('tr_mis_sum_more', '驗證資料 {n} 筆裡，模型判斷錯了 {w} 筆；下面列出前 {k} 筆。')
            : T('tr_mis_sum', '驗證資料 {n} 筆裡，模型判斷錯了 {w} 筆。'));
    $('mis-sum').textContent = tpl.replace('{n}', m.checked).replace('{w}', m.wrong)
        .replace('{k}', items.length);
    $('mis-list').innerHTML = items.length ? `
        <table class="tbl mis">
          <thead><tr>
            <th>${esc(T('tr_mis_th_item', '資料'))}</th>
            <th>${esc(T('tr_mis_th_truth', '正確答案'))}</th>
            <th>${esc(T('tr_mis_th_pred', '模型判成'))}</th>
          </tr></thead>
          <tbody>${items.map((it) => `
            <tr>
              <td>${it.path ? `<img class="mis__img" data-thumb="${esc(it.path)}" alt="">` : ''}${esc(it.text)}</td>
              <td>${esc(it.truth)}</td>
              <td>${esc(it.pred)}</td>
            </tr>`).join('')}</tbody>
        </table>` : '';
    box.hidden = false;
    loadThumbs();
}

// ZH: v4.36 圖片的縮圖。**不能直接 <img src="/api/…">**：瀏覽器載圖只帶 cookie、
//     不帶 Authorization，而 token 在 sessionStorage —— 必定 401（下載模型檔踩過同一個坑）。
//     所以 fetch 帶 header 取回 blob、轉成 object URL。
// ZH: 結果在輪詢與換語言時會整塊重畫 —— 記住拿過的，不要每 3 秒重抓十張圖。
//     拿不到（資料集被刪了、太大、格式不支援）就把 <img> 拿掉，只留檔名。
const THUMBS = new Map();
async function loadThumbs() {
    const imgs = [...$('mis-list').querySelectorAll('img[data-thumb]')];
    for (const img of imgs) {
        const path = img.dataset.thumb;
        const key = `${jobId}|${path}`;
        let url = THUMBS.get(key);
        if (url === undefined) {
            try {
                const r = await fetch(`${API}/jobs/${encodeURIComponent(jobId)}/val-image?path=${encodeURIComponent(path)}`,
                                      { headers: authHeaders() });
                url = r.ok ? URL.createObjectURL(await r.blob()) : null;
            } catch {
                url = null;
            }
            THUMBS.set(key, url);
        }
        if (url) img.src = url;
        else img.remove();
    }
}

// ZH: 只看模式的訊息落點（送單那張卡是收起來的）。
function setRunNote(html) {
    const acts = $('run-actions');
    acts.hidden = false;
    acts.innerHTML = `<span class="inline-error">${html}</span>`;
}

// ZH: v4.24 —— 這裡原本自己 fetch→blob→<a download> 抄了一份。
// ZH: 🔴 同一條規則有四份實作時，補一個邊界（例如中文檔名的 `filename*`）
//     只會補到其中一份，而另外三份**看起來仍然正常**。
//     收斂到 chrome.js 的 `Chrome.download()`（唯一真相）。
// ZH: ⚠ 按鈕狀態留在呼叫端 —— 那是**這一頁的事**（哪顆鈕、顯示什麼字），
//     不是下載本身的事。共用的那支只負責「把檔案交給瀏覽器」。
async function downloadModel(btn) {
    const original = btn.textContent;
    btn.disabled = true;
    btn.textContent = T('tr_downloading', '下載中…');
    try {
        await Chrome.download(`/jobs/${jobId}/model`, 'model.pt');
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
    if (mode === 'easy') renderEasy();
    if (LAST_JOB) renderLearnCode(LAST_JOB);
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
    el.textContent = T('tr_timeout_note',
        '單一任務最長跑 {n} 分鐘，超過會自動停止（那時也拿不到模型）。').replace('{n}', v);
    el.hidden = false;
}

let PUB_SETTINGS = null;
Chrome.publicSettings().then((s) => { PUB_SETTINGS = s; renderTimeoutNote(s); });
// ZH: 文案是 JS 組出來的，沒有 data-i18n，字典掃描換不掉它 —— 語言改變時要自己重畫。
document.addEventListener('prefs:langchanged', () => renderTimeoutNote(PUB_SETTINGS));
