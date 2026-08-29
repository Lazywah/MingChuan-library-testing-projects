/* ==============================================================================
   myai.js — 體驗大模型（MYAI 專屬頁）
   ==============================================================================
   ZH: 這一頁與它的邏輯原本都在首頁（app.js）。v3.9 搬出來 —— 導覽列上
       「體驗大模型」與「首頁」原本指向同一個地方，名字與去處不一致。

   ZH: ⚠ 搬家不是複製。首頁已經**沒有**額度卡，也沒有 goMyai()。
       兩邊各留一份的話就是同一台狀態機的兩份實作，遲早分岔而且不會報錯。

   ZH: 可用 ?state=empty|loading|error|low|noquota 強制展示各種狀態 ——
       「MYAI 未開通」「額度用完」這些狀態沒辦法靠真實帳號隨時湊出來，
       沒有這個開關就等於改完之後沒有任何辦法看一眼對不對。
   ============================================================================== */

const API = '/api/v1';

const FORCED = new URLSearchParams(location.search).get('state');

const $ = (id) => document.getElementById(id);

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

// ══════════════════════════════════════════════════════════════════════
// ZH: 開通狀態。v3.9 之前這裡還有 `hasJobs` 與整套流程條的狀態機
//     （現在在這／下一步／已完成）—— B 方案改成分組卡片之後那些都不需要了：
//     卡片不編號、不排先後，所以也不必偵測「你走到第幾步」。
//
// ZH: `provisioned` 留著，因為最上面那顆「前往 MYAI」仍然要分流：
//     還沒開通的人跳過去只會看到廠商的登入頁，而他根本還沒有帳號。
// ══════════════════════════════════════════════════════════════════════
const STATE = { provisioned: null };

// ── 主要動作：前往 MYAI（V1 修正）────────────────────────────────────
// ZH: 只有這一頁有這個動作。頂部列的「MYAI」是**連到本頁**，不自己跳轉——
//     那樣「彈窗被擋時要說話」的處理就只需要存在於這裡（唯一有 #handoff 的地方），
//     不必散到八個頁面。
async function goMyai() {
    const box = $('handoff');
    // ZH: 這個位置本來可能有東西 ——「你的 MYAI 初始密碼還沒改 · 查看初始密碼」
    //     就是掛在這裡（見 loadBalance）。先抄下來，成功開啟之後還原回去。
    const before = { html: box.innerHTML, hidden: box.hidden };
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
        // ZH: 開成功了就**不要再給一個「點這裡前往 MYAI」** ——
        //     分頁已經在他眼前了，再放一個連結只會讓人以為剛才沒成功。
        //     這一句與那個連結是**給彈窗被擋的人看的**（上面 `!win` 那條路），
        //     成功時掛在這裡只是噪音。
        // ZH: 還原成點下去之前的樣子：有未修改的初始密碼時，
        //     這裡會回到「查看初始密碼」；沒有的話就是空白。
        box.innerHTML = before.html;
        box.hidden = before.hidden;
    }, 1000);
}

function wireUsageLink() {
    // ZH: 額度區裡的行內連結與底部的「使用量明細」是同一個去處。
    //     漏掉這個的話，同一頁上兩個同名連結一個能用一個說「尚未實作」。
    const a = $('link-usage-inline');
    if (a) a.addEventListener('click', (ev) => { ev.preventDefault(); location.href = 'usage.html'; });
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

        // ZH: v3.9 `?state=low` / `?state=noquota` —— 低額度與已用完的強制狀態。
        //     加這兩個的理由很實際：這一塊只有「真的沒額度的帳號」才看得到，
        //     所以改完之後沒有任何辦法看一眼對不對。這一頁本來就有
        //     `?state=` 的慣例（見檔頭），補齊它比每次借帳號來得便宜。
        const [bal, prov] = (FORCED === 'low' || FORCED === 'noquota')
            ? [{ points: FORCED === 'low' ? 2500 : 0, threshold: 30000,
                 state: FORCED === 'low' ? 'low' : 'empty', apply_guide_url: '' },
               { provisioned: true, initial_password: null }]
            : await Promise.all([
                get('/external-ai/my-balance'),
                get('/external-ai/my-provision').catch(() => null),
            ]);

        // ZH: 後端契約有**三種**開通狀態，先前只當成兩種，於是在「還沒有帳號」
        //     的狀態下也顯示「確認我的初始密碼」——點進去是空的。
        //       provisioned=false                        → 沒有密碼可看，不給動作
        //       provisioned=true + initial_password       → 有密碼可看
        //       provisioned=true + initial_password=null  → 已確認或逾期
        // ZH: 記下來給引導流程與「問 AI」的分流用（兩處都要，不能只記其一）。
        STATE.provisioned = !(prov && prov.provisioned === false);
        if (!STATE.provisioned) return renderProvisioning();

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
        // ZH: v3.8 #9 —— 兩段提醒:1=快用完, 2=已用完。狀態由後端算（crud.myai_balance_state），
        //     前端不自己比門檻 —— 兩邊各判一次的話，信裡說「已用完」而畫面說「偏低」
        //     是遲早的事，而那種不一致沒有任何錯誤訊息。
        const stage = bal.state || (bal.below ? 'low' : 'ok');   // ZH: 舊版後端沒有 state 時的退路
        card.dataset.low = stage === 'empty' ? '2' : stage === 'low' ? '1' : '0';
        // ZH: 一般狀態**不再**掛「使用量明細」——底部次要區與帳號選單都已經有了，
        //     同一頁三個入口通往同一個地方，是雜訊不是方便（擁有者裁定 2026-08-21）。
        // ZH: 但低額度時保留「看用在哪」：那不是導覽項，是**掛在警示上的行動點**，
        //     回答的是「為什麼變低」。把它一起拿掉會讓警示變成一句沒有下一步的話。
        // ZH: 🔴 申請連結：管理端本來就設定得了，但在 v3.8 之前**前後台都沒有地方顯示它** ——
        //     一個設定好卻永遠看不到的連結。已用完的人最需要的就是這個下一步。
        if (stage === 'ok') {
            meta.innerHTML = '';
        } else {
            const parts = [
                stage === 'empty'
                    ? T('idx_no_balance', '額度已用完')
                    : T('idx_low_balance', '額度偏低（低於 {n}）')
                          .replace('{n}', (bal.threshold || 0).toLocaleString('en-US')),
                `<a href="#" id="link-usage-inline">${T('idx_see_where', '看用在哪')}</a>`,
            ];
            const guide = window.Chrome.safeUrl(bal.apply_guide_url);
            if (guide) {
                parts.push(`<a href="${guide}" target="_blank" rel="noopener noreferrer">`
                           + `${T('idx_apply_more', '如何申請額度')}</a>`);
            }
            // ZH: v3.9 向管理者申請 —— 走**既有的問題回報**，不另開一條路。
            //     那條路已經完整了（管理端看得到、回得了、使用者看得到回覆）；
            //     另開一個申請表單會多出第二個收件匣，而第二個總是沒人看的那個。
            // ZH: 與上面的「如何申請額度」不衝突：那個是外部說明（怎麼申請），
            //     這個是動作（現在就申請）。而且說明網址沒設定時它根本不顯示 ——
            //     那正是最常見的狀態，於是「額度用完」曾經是一句沒有下一步的話。
            parts.push(`<a href="report.html?topic=quota">`
                       + `${T('idx_ask_quota', '向管理員申請額度')}</a>`);
            meta.innerHTML = parts.join(' · ');
        }
        wireUsageLink();
    } catch (e) {
        // ZH: 額度掛掉不該讓引導流程一起消失 —— 給一個保守值讓它照樣畫出來。
        //     沒有這一行的話 STATE.provisioned 會永遠是 null，
        //     「前往 MYAI」就會一直走到 provision.html 而不是真的去 MYAI。
        if (STATE.provisioned === null) { STATE.provisioned = true; }
        // 錯誤：**主要動作照常可用**——看不到額度不是不能用 AI 的理由
        value.textContent = '—';
        unit.hidden = true;
        meta.innerHTML = `<span class="inline-error">${T('idx_bal_fail', '暫時取不到額度，不影響使用')}</span>`;
    }
}

// ZH: 還沒有 MYAI 帳號 —— **不給動作**。這個狀態下沒有初始密碼，
//     給一個連結等於帶使用者去看一個空畫面。
function renderProvisioning() {
    // ZH: 這裡也可能是 FORCED==='empty' 直接進來的（沒經過 loadBalance 的主線）。
    if (STATE.provisioned === null) { STATE.provisioned = false; }
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
// ZH: 「前往 MYAI」分流（擁有者裁定 2026-08-24）——已開通就直接跳廠商；
//     還沒開通的人跳過去只會看到廠商的登入頁而他根本沒有帳號，
//     所以改帶到說明頁（provision.html 會講「還在開通中」，並提供回報入口）。
$('go-myai').addEventListener('click', () => {
    if (STATE.provisioned === false) { location.href = 'provision.html'; return; }
    goMyai();
});

// ZH: 先擋登入。requireLogin() 為 false 時已經在導向了，不要再發請求 ——
//     那些請求必定 401，只會在 console 留下看起來像壞掉的紅字。
if (requireLogin()) {
    loadBalance();
}


// ── 語言切換時重繪 ───────────────────────────────────────────────────
// ZH: prefs.js 的字典掃描只換得掉 `data-i18n` 元素；本頁 JS 產生的內容要自己重跑。
//     只在語言**改變**時觸發（不是每次套用），所以不會在載入時多跑一次。
document.addEventListener('prefs:langchanged', () => {
    loadBalance();
});
