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

function fmtWhen(iso) {
    if (!iso) return null;
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return null;
    const hh = String(d.getHours()).padStart(2, '0');
    const mm = String(d.getMinutes()).padStart(2, '0');
    const today = new Date().toDateString() === d.toDateString();
    return `${today ? '今天' : `${d.getMonth() + 1}/${d.getDate()}`} ${hh}:${mm}`;
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
            setPrimary({ label: '用範例資料開始', note: '', enabled: true });
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
        label: '目前無可用算力',
        note: when
            ? `下次開放：${when}。這段說明照常可看，之後再回來開始即可。`
            : (why ? `暫時查不到算力狀態（${why}）。` : '等待機器上線。'),
        enabled: false,
    });
}

// ── 主要動作：用範例開始 ──────────────────────────────────────────────
$('go-example').addEventListener('click', async () => {
    const btn = $('go-example');
    btn.disabled = true;
    btn.textContent = '正在開啟 Lab…';
    try {
        await fetch(`${API}/lab/start`, { method: 'POST', headers: authHeaders() });
        // ZH: 交給 v2 自己的 Lab 畫面接手 —— 它會輪詢到就緒才開新分頁（D3）。
        //     這裡不直接開 /code/，因為容器剛送出 start 還沒起來。
        location.href = 'lab.html';
    } catch (e) {
        setPrimary({
            label: '用範例資料開始',
            note: `開啟失敗（${e.message || e}）。可以再試一次。`,
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
    if (FORCED === 'noquota') { $('quota').textContent = '磁碟配額：暫時查不到（不影響開始）'; return; }
    try {
        const s = await get('/lab/status');
        const gb = s.effective_quota_gb;
        $('quota').textContent = (gb == null)
            ? '磁碟配額：暫時查不到（不影響開始）'
            : `磁碟配額：${gb} GB`;
    } catch {
        // ZH: 這是層級 3，失敗不該吵。但也不能留著「讀取中…」假裝還在跑。
        $('quota').textContent = '磁碟配額：暫時查不到（不影響開始）';
    }
}

// ── 啟動 ─────────────────────────────────────────────────────────────
loadPool();
loadQuota();
