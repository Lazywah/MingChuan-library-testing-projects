/* ==============================================================================
   app.js — v2 使用者端（主線首頁）
   ==============================================================================
   規格：docs/06-ui-v2-design.md。四個狀態全做，可用 ?state= 強制展示。

   本檔只實作主線首頁。其餘畫面（登入 / GPU 引導 / 使用量）尚未實作，
   入口先接到明確的「尚未實作」提示，而不是死連結——連到空頁比沒有連結更糟。
   ============================================================================== */

const API = '/api/v1';

/* ZH: 開發期強制狀態：?state=empty|loading|error|overflow
       四個狀態不可能都靠真實資料湊出來（例如「MYAI 未開通」需要一個沒開通的帳號），
       沒有這個開關就等於沒辦法檢查它們——而那正是 0→1 設計最常漏掉的部分。 */
const FORCED = new URLSearchParams(location.search).get('state');

const $ = (id) => document.getElementById(id);

// ── 色系切換（開發期）────────────────────────────────────────────────
(function themeSwitch() {
    const saved = localStorage.getItem('v2-theme') || 'yellow';
    apply(saved);
    document.querySelectorAll('[data-set-theme]').forEach((b) => {
        b.addEventListener('click', () => apply(b.dataset.setTheme));
    });
    function apply(name) {
        document.documentElement.dataset.theme = name;
        localStorage.setItem('v2-theme', name);
        document.querySelectorAll('[data-set-theme]').forEach((b) => {
            b.setAttribute('aria-pressed', String(b.dataset.setTheme === name));
        });
    }
})();

// ── 取資料 ───────────────────────────────────────────────────────────
function authHeaders() {
    // ZH: ⚠ 鍵名必須與 v1／v1.5 一致（'ai_hud_token'）。
    //     三個版本同源，共用同一份 session——用不同的鍵名等於 v2 永遠讀不到既有登入，
    //     而症狀是「一直顯示取不到額度」，看起來像 API 壞掉。實作時就踩過一次。
    const t = sessionStorage.getItem('ai_hud_token') || localStorage.getItem('ai_hud_token');
    return t ? { Authorization: 'Bearer ' + t } : {};
}

async function get(path) {
    const res = await fetch(API + path, { headers: authHeaders() });
    if (!res.ok) throw new Error(path + ' → ' + res.status);
    return res.json();
}

// ── 額度（層級 1）─────────────────────────────────────────────────────
async function loadBalance() {
    const card = $('balance-card');
    const value = $('balance-value');
    const unit = $('balance-unit');
    const meta = $('balance-meta');

    // 載入中：骨架已在 HTML 裡，保留高度不跳動
    if (FORCED === 'loading') return;

    // 空：MYAI 帳號尚未開通
    if (FORCED === 'empty') return renderNotProvisioned();

    try {
        if (FORCED === 'error') throw new Error('forced');

        const [bal, prov] = await Promise.all([
            get('/external-ai/my-balance'),
            get('/external-ai/my-provision').catch(() => null),
        ]);

        if (prov && prov.provisioned === false) return renderNotProvisioned();

        if (bal.points == null) return renderNotProvisioned();

        value.textContent = bal.points.toLocaleString('en-US');
        unit.hidden = false;
        // ZH: Token 即基準（Decision Log #15）——不換算成「約可再問 N 次」。
        //     但「低於門檻」要看得出來，用的是後端已回傳的 below 旗標。
        card.dataset.low = bal.below ? '1' : '0';
        meta.innerHTML = bal.below
            ? '額度偏低（低於 ' + bal.threshold.toLocaleString('en-US') + '）'
              + ' · <a href="#" id="link-usage-inline">看用在哪</a>'
            : '<a href="#" id="link-usage-inline">使用量明細</a>';
        wireUsageLink();
    } catch (e) {
        // 錯誤：**主要動作照常可用**——看不到額度不是不能用 AI 的理由
        value.textContent = '—';
        unit.hidden = true;
        meta.innerHTML = '<span class="inline-error">暫時取不到額度，不影響使用</span>';
    }
}

function renderNotProvisioned() {
    $('balance-value').textContent = '—';
    $('balance-unit').hidden = true;
    $('balance-meta').innerHTML =
        '你的 AI 帳號正在開通 · <a href="#" id="link-provision">確認我的初始密碼</a>';
    const a = $('link-provision');
    if (a) a.addEventListener('click', (ev) => { ev.preventDefault(); notImplemented('開通確認'); });
}

// ── 公告（層級 0，條件式）──────────────────────────────────────────────
async function loadNotice() {
    const box = $('notice');
    try {
        let list;
        if (FORCED === 'overflow') {
            list = Array.from({ length: 12 }, (_, i) => ({
                title: '示範公告第 ' + (i + 1) + ' 則：系統維護與功能更新說明',
                posted_at: '2026-08-16T09:00:00',
            }));
        } else if (FORCED === 'empty' || FORCED === 'error') {
            // 空／錯誤：橫幅不出現，其餘照常（部分失敗不整頁死）
            return;
        } else {
            list = await get('/announcements');
        }
        if (!list || !list.length) return;    // 沒有公告 → 整條不存在

        const top = list[0];
        $('notice-date').textContent = (top.posted_at || '').slice(0, 10);
        $('notice-title').textContent = top.title;
        if (list.length > 1) {
            const more = $('notice-more');
            more.textContent = '查看全部 ' + list.length + ' 則';
            more.hidden = false;
            more.addEventListener('click', (ev) => { ev.preventDefault(); notImplemented('公告列表'); });
        }
        box.hidden = false;
    } catch (e) {
        /* 公告取不到 → 橫幅不出現，首頁其餘照常 */
    }
}

// ── 主要動作：前往 MYAI（V1 修正）────────────────────────────────────
async function goMyai() {
    const box = $('handoff');
    box.hidden = false;
    box.textContent = '正在帶你前往 MYAI…（會另開分頁，並需要登入一次）';

    let logoutUrl = 'https://www.myai168.com/mcu/ai/user/logout_info';
    try {
        const me = await get('/external-ai/me');
        if (me && me.logout_url) logoutUrl = me.logout_url;
    } catch (e) { /* 取不到就用預設，不擋住動作 */ }

    const loginUrl = logoutUrl.replace(/\/[^/]*$/, '/login');

    // ZH: 先開登出頁再轉登入頁——確保是「這位學生」登入，而不是沿用上一個人的 session。
    //     不加 noopener：要保留 win 控制權才能做第二段跳轉。
    const win = window.open(logoutUrl, '_blank');

    if (!win) {
        // ⚠ V1 的核心修正：被瀏覽器阻擋時**不可以毫無反應**
        box.innerHTML = '瀏覽器擋下了新分頁。'
            + '<a href="' + loginUrl + '" target="_blank" rel="noopener">點這裡前往 MYAI</a>';
        return;
    }
    setTimeout(() => {
        try { if (win && !win.closed) win.location.replace(loginUrl); } catch (e) { /* 跨網域寫入被拒 */ }
        box.innerHTML = '已在新分頁開啟 MYAI。'
            + '<a href="' + loginUrl + '" target="_blank" rel="noopener">沒看到的話點這裡</a>';
    }, 1000);
}

// ── 尚未實作的去處：明講，不做死連結 ──────────────────────────────────
function notImplemented(what) {
    const box = $('handoff');
    box.hidden = false;
    box.textContent = '「' + what + '」在 v2 還沒實作（設計已定稿，見 docs/06-ui-v2-design.md）。';
}

function wireUsageLink() {
    const a = $('link-usage-inline');
    if (a) a.addEventListener('click', (ev) => { ev.preventDefault(); notImplemented('使用量明細'); });
}

// ── 啟動 ─────────────────────────────────────────────────────────────
$('go-myai').addEventListener('click', goMyai);
$('go-gpu').addEventListener('click', () => notImplemented('GPU 引導'));
['link-usage', 'link-lab', 'link-report'].forEach((id) => {
    $(id).addEventListener('click', (ev) => { ev.preventDefault(); notImplemented($(id).textContent); });
});

loadBalance();
loadNotice();
