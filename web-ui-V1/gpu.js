/* ==========================================================================
 * [畫面: GPU 引導] — 使用者在這裡要完成：看懂「用學校 GPU 能做到什麼」，
 *                    並決定要不要開始
 *
 * ZH: 線框（docs/06-ui-V1-design.md §4）的關鍵一條，實作時最容易做反：
 *     **錯誤狀態下說明區照常顯示。** 看不到算力不影響「看懂能做什麼」——
 *     池不可用時只有那顆按鈕改變，上下文一個字都不動。
 *     這是首頁「部分失敗不整頁死」的同一條規則。
 * ========================================================================== */
const API = '/api/v1';

// ZH: 狀態的手動觸發：?state=loading | error | busy | noquota
const FORCED = new URLSearchParams(location.search).get('state');

const $ = (id) => document.getElementById(id);

// ZH: 色系切換已集中到 prefs.js（跟帳號走）。
//     原本九個頁面各寫一份，**只有 app.js 那份會存與還原**——
//     於是「有些頁面換了顏色，其他頁面還沒變」。同一條規則不要有第二份實作。

// ZH: ⚠ 鍵名必須與 v1／v1.5／首頁一致。用錯不會報錯，只會讓每個請求都 401，
//     而畫面看起來像「後端壞了」。首頁實作時踩過。
function authHeaders() {
    const t = sessionStorage.getItem('ai_hud_token') || localStorage.getItem('ai_hud_token');
    return t ? { Authorization: 'Bearer ' + t } : {};
}

async function get(path) {
    const r = await fetch(API + path, { headers: { Accept: 'application/json', ...authHeaders() } });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    return r.json();
}

// ── 主要動作的三種樣貌 ────────────────────────────────────────────────
function setPrimary({ label, note, enabled }) {
    const btn = $('go-example');
    btn.textContent = label;
    btn.disabled = !enabled;
    $('pool-note').textContent = note || '';
    $('pool-note').hidden = !note;
}

// ZH: 時間一律走 tz.js（釘死 Asia/Taipei）。原本用 getHours()/getMonth()，
//     那是**瀏覽器所在時區**，而且後端的 naive 字串會被當成本地時間，差 8 小時。
function fmtWhen(iso) {
    return TW.when(iso) || null;
}

async function loadPool() {
    if (FORCED === 'loading') return;                 // 停在檢查中，供檢視
    if (FORCED === 'error') return poolDown(null, '強制錯誤狀態');
    if (FORCED === 'busy') return poolDown(new Date(Date.now() + 5400e3).toISOString(), null);

    try {
        const p = await get('/jobs/pool-availability');
        // ZH: 互動池（Lab）才是這個畫面要的；批次池是訓練任務用的。
        //     後端語意：interactive 已含 batch 墊底。
        const pool = p.interactive || p.batch || {};
        if (pool.available) {
            setPrimary({ label: T('gpu_start_sample', '學習程式碼'), note: '', enabled: true });
        } else {
            poolDown(pool.next_open, null);
        }
    } catch (e) {
        // ZH: 取不到就說取不到，**不要假裝可用**——按下去才失敗更糟。
        poolDown(null, String(e.message || e));
    }
}

function poolDown(nextOpen, why) {
    const when = fmtWhen(nextOpen);
    setPrimary({
        label: T('gpu_no_capacity', '目前無可用算力'),
        note: when
            ? T('gpu_next_open', '下次開放：{w}。這段說明照常可看，之後再回來開始即可。').replace('{w}', when)
            : (why ? T('gpu_state_fail', '暫時查不到算力狀態') + `（${why}）。`
                   : T('gpu_waiting', '等待機器上線。')),
        enabled: false,
    });
}

// ── 主要動作：用範例開始 ──────────────────────────────────────────────
// ── 範例種類（v4.19）─────────────────────────────────────────────────
// ZH: 三種範例。選哪一種決定畫面上五段文案、開實驗室時放進工作區的範例
//     （後端 lab_manager.LAB_SAMPLE_KINDS 認得的名字）、以及「不想看程式，直接用資料集訓練」
//     預選的內建任務。用 T() 一個個寫是為了 check_i18n 抓得到 key。
const KINDS = {
    cats_dogs: {
        task: 'image_classification',
        h1:   () => T('gpu_h1', '做出一個能分辨貓和狗的模型'),
        sub1: () => T('gpu_sub1', '用學校的 GPU，大約 20 分鐘。'),
        s1d:  () => T('gpu_s1d', '每個類別一個資料夾。用範例的話這步跳過。'),
        s3d:  () => T('gpu_s3d', '正確率、以及模型判斷錯的那幾張圖。'),
        where: () => T('gpu_sample_where', '範例在哪？開啟實驗室後，左邊的檔案列表裡就有 cat_dog_data/（500 張貓、500 張狗）和 sample_cats_dogs.py —— 資料和程式都已經幫你放好，所以不用先上傳資料集，直接執行就能訓練。要用自己的資料才需要上傳。'),
        keys: { h1: 'gpu_h1', sub1: 'gpu_sub1', s1d: 'gpu_s1d', s3d: 'gpu_s3d', where: 'gpu_sample_where' },
    },
    tabular: {
        task: 'tabular_classification',
        h1:   () => T('gpu_h1_tab', '做出一個能預測學生會不會及格的模型'),
        sub1: () => T('gpu_sub1_tab', '用一份表格（CSV），幾秒鐘就訓練完。'),
        s1d:  () => T('gpu_s1d_tab', '一份 CSV：一列一筆、一欄一個特徵、其中一欄是答案。用範例的話這步跳過。'),
        s3d:  () => T('gpu_s3d_tab', '正確率、以及模型猜錯的那幾筆。'),
        where: () => T('gpu_sample_where_tab', '範例在哪？開啟實驗室後，左邊的檔案列表裡就有 students.csv（320 筆）和 sample_tabular.py —— 資料和程式都已經幫你放好，直接執行就能訓練。要用自己的資料才需要上傳。'),
        keys: { h1: 'gpu_h1_tab', sub1: 'gpu_sub1_tab', s1d: 'gpu_s1d_tab', s3d: 'gpu_s3d_tab', where: 'gpu_sample_where_tab' },
    },
    text: {
        task: 'text_classification',
        h1:   () => T('gpu_h1_text', '做出一個能分辨評論是正面還是負面的模型'),
        sub1: () => T('gpu_sub1_text', '用一份句子＋答案的表格（CSV），幾秒鐘就訓練完。'),
        s1d:  () => T('gpu_s1d_text', '一份 CSV，兩欄：句子與答案。用範例的話這步跳過。'),
        s3d:  () => T('gpu_s3d_text', '正確率、模型猜錯的那幾句，還可以拿自己寫的句子試。'),
        where: () => T('gpu_sample_where_text', '範例在哪？開啟實驗室後，左邊的檔案列表裡就有 reviews.csv（240 句）和 sample_text.py —— 資料和程式都已經幫你放好，直接執行就能訓練。要用自己的資料才需要上傳。'),
        keys: { h1: 'gpu_h1_text', sub1: 'gpu_sub1_text', s1d: 'gpu_s1d_text', s3d: 'gpu_s3d_text', where: 'gpu_sample_where_text' },
    },
};
let kind = 'cats_dogs';

// ZH: 同時改 data-i18n 與文字：prefs.js 換語言時是重掃 data-i18n，只改文字會跳回貓狗。
function setKind(k) {
    if (!KINDS[k]) return;
    kind = k;
    const c = KINDS[k];
    $('kind-seg').querySelectorAll('button').forEach((b) =>
        b.setAttribute('aria-pressed', String(b.dataset.kind === k)));
    [['gpu-title', 'h1'], ['gpu-sub1', 'sub1'], ['gpu-s1d', 's1d'], ['gpu-s3d', 's3d'], ['sample-where', 'where']]
        .forEach(([id, key]) => {
            const el = $(id);
            if (!el) return;
            el.setAttribute('data-i18n', c.keys[key]);
            el.textContent = c[key]();
        });
    // ZH: 「不想看程式，直接用資料集訓練」預選同一種 —— 他在這裡選了表格，過去不該又是圖片。
    const own = $('go-own-zip');
    if (own) own.href = `train.html?task=${encodeURIComponent(c.task)}`;
}
$('kind-seg').addEventListener('click', (e) => {
    const b = e.target.closest('button[data-kind]');
    if (b) setKind(b.dataset.kind);
});
setKind(kind);

$('go-example').addEventListener('click', async () => {
    const btn = $('go-example');
    btn.disabled = true;
    btn.textContent = T('gpu_opening', '正在開啟實驗室…');
    try {
        // ZH: v4.19 帶著選的範例；後端啟動容器後會把它放進 ~/projects/。
        await fetch(`${API}/lab/start`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', ...authHeaders() },
            body: JSON.stringify({ sample: kind }),
        });
        // ZH: 交給 v2 自己的 Lab 畫面接手 —— 它會輪詢到就緒才開新分頁（D3）。
        //     這裡不直接開 /code/，因為容器剛送出 start 還沒起來。
        location.href = 'lab.html';
    } catch (e) {
        setPrimary({
            label: T('gpu_start_sample', '學習程式碼'),
            note: T('gpu_open_fail', '開啟失敗') + `（${e.message || e}）。` + T('retry_once', '可以再試一次。'),
            enabled: true,
        });
    }
});

// ── 層級 3：磁碟配額 ─────────────────────────────────────────────────
async function loadQuota() {
    if (FORCED === 'noquota') { $('quota').textContent = T('gpu_quota_unknown', '磁碟配額：暫時查不到（不影響開始）'); return; }
    try {
        const s = await get('/lab/status');
        const gb = s.effective_quota_gb;
        $('quota').textContent = (gb == null)
            ? T('gpu_quota_unknown', '磁碟配額：暫時查不到（不影響開始）')
            : T('gpu_quota', '磁碟配額：{g} GB').replace('{g}', gb);
    } catch {
        // ZH: 這是層級 3，失敗不該吵。但也不能留著「讀取中…」假裝還在跑。
        $('quota').textContent = T('gpu_quota_unknown', '磁碟配額：暫時查不到（不影響開始）');
    }
}

// ── 啟動 ─────────────────────────────────────────────────────────────
loadPool();
loadQuota();


// ── 語言切換時重繪 ───────────────────────────────────────────────────
// ZH: prefs.js 的字典掃描只換得掉 `data-i18n` 元素；本頁 JS 產生的內容要自己重跑。
//     只在語言**改變**時觸發（不是每次套用），所以不會在載入時多跑一次。
document.addEventListener('prefs:langchanged', () => { loadPool(); loadQuota(); });
