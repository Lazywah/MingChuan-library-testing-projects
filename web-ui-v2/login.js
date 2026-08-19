/* ==========================================================================
 * [畫面: 登入] — 使用者在這裡要完成：進到平台裡面
 *
 * ZH: 線框（docs/06-ui-v2-design.md §4）的三個要點，實作時容易走鐘，寫在這裡：
 *   1. **主要動作唯一**。載入中與錯誤都表達在那顆按鈕上，不用整頁 spinner ——
 *      整頁 spinner 會把「還能不能操作」這件事藏起來。
 *   2. **錯誤時摺疊區維持收合**（C2 修正）。自動展開＝把管理者通道曝光給學生，
 *      而 admin 本來就知道它在哪，不需要系統替他打開。
 *   3. 這個畫面**只有一件事**，所以沒有層級 2。
 * ========================================================================== */
const API = '/api/v1';

// ZH: 狀態的手動觸發（與首頁同一套）：?state=loading | error | nosso
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

// ── 主要動作：學校 SSO ────────────────────────────────────────────────
// ZH: 三種結局各有不同的按鈕文字。**沒有一種是「按了沒反應」**。
function setPrimary({ label, note, enabled }) {
    const btn = $('go-sso');
    btn.textContent = label;
    btn.disabled = !enabled;
    $('sso-note').textContent = note || '';
    $('sso-note').hidden = !note;
}

async function loadProviders() {
    if (FORCED === 'loading') return;                    // 停在載入中，供檢視
    if (FORCED === 'error') return failSso('強制錯誤狀態');
    if (FORCED === 'nosso') return noSso();

    try {
        const r = await fetch(`${API}/sso/providers`, { headers: { Accept: 'application/json' } });
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        const data = await r.json();
        const list = Array.isArray(data.providers) ? data.providers : [];
        if (!list.includes('oidc')) return noSso();
        setPrimary({ label: '用學校帳號登入', note: '', enabled: true });
    } catch (e) {
        failSso(String(e.message || e));
    }
}

function failSso(why) {
    // ZH: 線框指定的文案。**不自動展開摺疊區**——那是 C2 修正的重點。
    setPrimary({
        label: '用學校帳號登入',
        note: `學校登入暫時不可用，請稍後再試。（${why}）`,
        enabled: false,
    });
}

function noSso() {
    // ZH: 設定上沒有啟用 OIDC —— 這不是錯誤，是這台機器的狀態，文案要分開。
    setPrimary({
        label: '用學校帳號登入',
        note: '這台伺服器尚未啟用學校登入。若你是管理者，請用下方的本機登入。',
        enabled: false,
    });
}

$('go-sso').addEventListener('click', () => {
    // ZH: 整頁轉址交給後端處理 OIDC 交握，前端不碰任何憑證。
    location.href = `${API}/sso/oidc/login`;
});

// ── 層級 3：管理者本機登入 ────────────────────────────────────────────
$('admin-form').addEventListener('submit', async (ev) => {
    ev.preventDefault();
    const btn = $('admin-submit');
    const err = $('admin-error');
    err.hidden = true;
    btn.disabled = true;
    btn.textContent = '登入中…';

    try {
        // ZH: ⚠ 這個端點用 OAuth2PasswordRequestForm，**吃 form-urlencoded 不吃 JSON**。
        //     送 JSON 會固定回 422，而 422 的訊息長得像「欄位缺少」，
        //     看起來像表單沒填好，不像格式送錯——我第一版就是這樣寫的。
        // ZH: credentials 明寫 —— 登入回應會 Set-Cookie `ai_hud_token`，
        //     而**開新分頁進 /code/ 靠的就是那個 cookie**（nginx auth_request，
        //     sessionStorage 的 token 帶不進新分頁）。
        const body = new URLSearchParams({
            username: $('admin-user').value.trim(),
            password: $('admin-pass').value,
        });
        const r = await fetch(`${API}/auth/login`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
            body: body.toString(),
            credentials: 'include',
        });
        const data = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(data.detail || `登入失敗（HTTP ${r.status}）`);

        // ZH: ⚠ 鍵名必須與 v1／v1.5／首頁一致（'ai_hud_token'）。
        //     用別的鍵名不會報錯，只會讓登入後的頁面「一直取不到額度」——
        //     實作首頁時已經踩過一次這個坑。
        sessionStorage.setItem('ai_hud_token', data.access_token);
        location.href = 'index.html';
    } catch (e) {
        err.textContent = String(e.message || e);
        err.hidden = false;
    } finally {
        btn.disabled = false;
        btn.textContent = '登入';
    }
});

$('forgot').addEventListener('click', (ev) => {
    ev.preventDefault();
    const err = $('admin-error');
    err.textContent = '忘記密碼：請聯絡圖書館 AI 基地管理者重設。（自助重設尚未接上）';
    err.hidden = false;
});

// ── 啟動 ─────────────────────────────────────────────────────────────
loadProviders();
