/* ==============================================================================
   app.js — v2 使用者端（主線首頁）
   ==============================================================================
   規格：docs/06-ui-V1-design.md。四個狀態全做，可用 ?state= 強制展示。

   本檔只負責主線首頁。其餘畫面各自有自己的 HTML+JS：
   login / gpu / usage / provision / lab / news / report。
   首頁上每一個去處現在都有落點，notImplemented() 因此移除——
   留著一個說「尚未實作」的函式而實際上全都實作了，比沒有更誤導。
   ============================================================================== */

const API = '/api/v1';

/* ZH: 開發期強制狀態：?state=empty|loading|error|overflow
       四個狀態不可能都靠真實資料湊出來（例如「MYAI 未開通」需要一個沒開通的帳號），
       沒有這個開關就等於沒辦法檢查它們——而那正是 0→1 設計最常漏掉的部分。 */
const FORCED = new URLSearchParams(location.search).get('state');

const $ = (id) => document.getElementById(id);

// ZH: 色系切換已集中到 prefs.js（跟帳號走）。
//     原本九個頁面各寫一份，**只有 app.js 那份會存與還原**——
//     於是「有些頁面換了顏色，其他頁面還沒變」。同一條規則不要有第二份實作。

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
    if (FORCED === 'empty') return renderProvisioning();

    try {
        if (FORCED === 'error') throw new Error('forced');

        const [bal, prov] = await Promise.all([
            get('/external-ai/my-balance'),
            get('/external-ai/my-provision').catch(() => null),
        ]);

        // ZH: 後端契約有**三種**開通狀態，先前只當成兩種，於是在「還沒有帳號」
        //     的狀態下也顯示「確認我的初始密碼」——點進去是空的。
        //       provisioned=false                        → 沒有密碼可看，不給動作
        //       provisioned=true + initial_password       → 有密碼可看
        //       provisioned=true + initial_password=null  → 已確認或逾期
        if (prov && prov.provisioned === false) return renderProvisioning();

        if (bal.points == null) return renderNoBalance();

        value.textContent = bal.points.toLocaleString('en-US');
        unit.hidden = false;

        // ZH: 已開通且保留期內未確認 → 額度照常顯示，另外掛一個入口。
        //     不取代額度區：他有點數就能用，初始密碼是「還沒處理的事」不是「阻礙」。
        if (prov && prov.initial_password) {
            $('handoff').hidden = false;
            $('handoff').innerHTML =
                T('idx_pw_unchanged', '你的 MYAI 初始密碼還沒改')
                + ` · <a href="provision.html">${T('idx_see_pw', '查看初始密碼')}</a>`;
        }
        // ZH: Token 即基準（Decision Log #15）——不換算成「約可再問 N 次」。
        //     但「低於門檻」要看得出來，用的是後端已回傳的 below 旗標。
        card.dataset.low = bal.below ? '1' : '0';
        // ZH: 一般狀態**不再**掛「使用量明細」——底部次要區與帳號選單都已經有了，
        //     同一頁三個入口通往同一個地方，是雜訊不是方便（擁有者裁定 2026-08-21）。
        // ZH: 但低額度時保留「看用在哪」：那不是導覽項，是**掛在警示上的行動點**，
        //     回答的是「為什麼變低」。把它一起拿掉會讓警示變成一句沒有下一步的話。
        meta.innerHTML = bal.below
            ? T('idx_low_balance', '額度偏低（低於 {n}）').replace('{n}', bal.threshold.toLocaleString('en-US'))
              + ` · <a href="#" id="link-usage-inline">${T('idx_see_where', '看用在哪')}</a>`
            : '';
        wireUsageLink();
    } catch (e) {
        // 錯誤：**主要動作照常可用**——看不到額度不是不能用 AI 的理由
        value.textContent = '—';
        unit.hidden = true;
        meta.innerHTML = `<span class="inline-error">${T('idx_bal_fail', '暫時取不到額度，不影響使用')}</span>`;
    }
}

// ZH: 還沒有 MYAI 帳號 —— **不給動作**。這個狀態下沒有初始密碼，
//     給一個連結等於帶使用者去看一個空畫面。
function renderProvisioning() {
    $('balance-value').textContent = '—';
    $('balance-unit').hidden = true;
    $('balance-meta').textContent = T('idx_provisioning', '你的 AI 帳號正在開通，完成後這裡會顯示額度。');
}

// ZH: 已開通但額度讀不到 —— 那是額度的問題，不是開通的問題，兩者文案不能共用。
function renderNoBalance() {
    $('balance-value').textContent = '—';
    $('balance-unit').hidden = true;
    $('balance-meta').innerHTML =
        `<span class="inline-error">${T('idx_bal_fail', '暫時取不到額度，不影響使用')}</span>`;
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
            more.textContent = T('idx_see_all', '查看全部 {n} 則').replace('{n}', list.length);
            more.hidden = false;
            more.addEventListener('click', (ev) => { ev.preventDefault(); location.href = 'news.html'; });
        }
        box.hidden = false;
    } catch (e) {
        /* 公告取不到 → 橫幅不出現，首頁其餘照常 */
    }
}

// ── 主要動作：前往 MYAI（V1 修正）────────────────────────────────────
// ZH: 只有這一頁有這個動作。頂部列的「MYAI」是**連到本頁**，不自己跳轉——
//     那樣「彈窗被擋時要說話」的處理就只需要存在於這裡（唯一有 #handoff 的地方），
//     不必散到八個頁面。
async function goMyai() {
    const box = $('handoff');
    box.hidden = false;
    box.textContent = T('myai_going', '正在帶你前往 MYAI…（會另開分頁，並需要登入一次）');

    let logoutUrl = 'https://www.myai168.com/mcu/ai/user/logout_info';
    try {
        const me = await get('/external-ai/me');
        if (me && me.logout_url) logoutUrl = me.logout_url;
    } catch (e) { /* 取不到就用預設，不擋住動作 */ }

    const loginUrl = logoutUrl.replace(/\/[^/]*$/, '/login');

    // ZH: 先開登出頁再轉登入頁——確保是「這位學生」登入，而不是沿用上一個人的 session。
    //     不加 noopener：要保留 win 控制權才能做第二段跳轉。
    const win = window.open(logoutUrl, '_blank');

    const fallback = (lead) => {
        box.textContent = lead;
        const a = document.createElement('a');
        a.href = loginUrl; a.target = '_blank'; a.rel = 'noopener';
        a.textContent = T('myai_click_here', '點這裡前往 MYAI');
        box.appendChild(a);
    };

    if (!win) {
        // ⚠ V1 的核心修正：被瀏覽器阻擋時**不可以毫無反應**
        fallback(T('popup_blocked', '瀏覽器擋下了新分頁。'));
        return;
    }
    setTimeout(() => {
        try { if (win && !win.closed) win.location.replace(loginUrl); } catch (e) { /* 跨網域寫入被拒 */ }
        fallback(T('myai_opened', '已在新分頁開啟 MYAI。'));
    }, 1000);
}

function wireUsageLink() {
    // ZH: 額度區裡的行內連結與底部的「使用量明細」是同一個去處。
    //     漏掉這個的話，同一頁上兩個同名連結一個能用一個說「尚未實作」。
    const a = $('link-usage-inline');
    if (a) a.addEventListener('click', (ev) => { ev.preventDefault(); location.href = 'usage.html'; });
}

// ── 未登入 → 回登入頁 ─────────────────────────────────────────────────
// ZH: 主線流程是「登入 → 首頁」。沒有這段的話登入頁是孤兒頁，
//     而首頁會用「暫時取不到額度」來表達「你根本沒登入」—— 那是錯的訊息：
//     線框裡那句是給**已登入但額度讀取失敗**的人看的，兩者不能共用。
//
// ⚠ 有 ?state= 時不導向 —— 那是四狀態的檢視用途，導走就看不到了。
function requireLogin() {
    const t = sessionStorage.getItem('ai_hud_token') || localStorage.getItem('ai_hud_token');
    if (t || FORCED) return true;
    location.replace('login.html');
    return false;
}

// ── 啟動 ─────────────────────────────────────────────────────────────
$('go-myai').addEventListener('click', goMyai);
$('go-gpu').addEventListener('click', () => { location.href = 'gpu.html'; });
$('link-usage').addEventListener('click', (ev) => {
    ev.preventDefault();
    location.href = 'usage.html';
});
$('link-lab').addEventListener('click', (ev) => {
    ev.preventDefault();
    location.href = 'lab.html';
});
$('link-report').addEventListener('click', (ev) => {
    ev.preventDefault();
    location.href = 'report.html';
});

// ZH: 先擋登入。requireLogin() 為 false 時已經在導向了，不要再發請求 ——
//     那些請求必定 401，只會在 console 留下看起來像壞掉的紅字。
if (requireLogin()) {
    loadBalance();
    loadNotice();
}


// ── 語言切換時重繪 ───────────────────────────────────────────────────
// ZH: prefs.js 的字典掃描只換得掉 `data-i18n` 元素；本頁 JS 產生的內容要自己重跑。
//     只在語言**改變**時觸發（不是每次套用），所以不會在載入時多跑一次。
document.addEventListener('prefs:langchanged', () => { loadBalance(); loadNotice(); });
