/* ==========================================================================
 * [畫面: GPU 引導] — 使用者在這裡要完成：看懂「用學校 GPU 能做到什麼」，
 *                    並決定要不要開始
 *
 * ZH: 線框（docs/06-ui-v2-design.md §4）的關鍵一條，實作時最容易做反：
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
            setPrimary({ label: T('gpu_start_sample', '用範例資料開始'), note: '', enabled: true });
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
$('go-example').addEventListener('click', async () => {
    const btn = $('go-example');
    btn.disabled = true;
    btn.textContent = T('gpu_opening', '正在開啟實驗室…');
    try {
        await fetch(`${API}/lab/start`, { method: 'POST', headers: authHeaders() });
        // ZH: 交給 v2 自己的 Lab 畫面接手 —— 它會輪詢到就緒才開新分頁（D3）。
        //     這裡不直接開 /code/，因為容器剛送出 start 還沒起來。
        location.href = 'lab.html';
    } catch (e) {
        setPrimary({
            label: T('gpu_start_sample', '用範例資料開始'),
            note: T('gpu_open_fail', '開啟失敗') + `（${e.message || e}）。` + T('retry_once', '可以再試一次。'),
            enabled: true,
        });
    }
});

$('link-own-data').addEventListener('click', (ev) => {
    ev.preventDefault();
    location.href = 'lab.html';
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
