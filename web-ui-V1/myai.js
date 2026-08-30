/* ==============================================================================
   myai.js — 體驗大模型（MYAI 專屬頁）
   ==============================================================================
   ZH: 這一頁與它的邏輯原本都在首頁（app.js）。v3.9 搬出來 —— 導覽列上
       「體驗大模型」與「首頁」原本指向同一個地方，名字與去處不一致。

   ZH: ⚠ 搬家不是複製。首頁已經**沒有**額度卡，也沒有 goMyai()。
       兩邊各留一份的話就是同一台狀態機的兩份實作，遲早分岔而且不會報錯。

   ZH: v3.9 初始密碼也併進來了（原本是 provision.html）——
       拿到密碼之後要做的事就是這一頁的主要動作，沒有理由分兩頁。

   ZH: 可用 ?state= 強制展示各種狀態 ——「MYAI 未開通」「額度用完」這些
       沒辦法靠真實帳號隨時湊出來，沒有這個開關就等於改完之後沒辦法看一眼對不對。
       ⚠ 這一頁有**兩塊**各自的狀態，值刻意不重疊：
         額度：loading | error | empty | low | noquota
         密碼：pw | pw-acked | pw-error
       `empty`（未開通）兩塊都吃 —— 那是同一個事實的兩面。
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
    // ZH: 先抄下這一格原本的樣子，成功開啟之後還原回去。
    // ZH: v3.9 起這裡在正常情況下是空的（初始密碼提示已移除），
    //     但**不要因此省掉還原** —— 省掉的話，「正在帶你前往 MYAI…」
    //     會永遠留在畫面上，看起來像卡住了。
    const before = { html: box.innerHTML, hidden: box.hidden };
    box.hidden = false;
    box.textContent = T('myai_going', '正在帶你前往 MYAI…（會另開分頁，並需要登入一次）');

    // ZH: v3.9 記一次跳轉（統計用）。
    // ZH: 🔴 **不 await**，而且失敗完全不管 —— 這一步是統計，
    //     讓它擋在「開新分頁」前面的話，後端慢一秒使用者就等一秒，
    //     後端掛掉他就去不了 MYAI。統計比不上那件事。
    // ZH: ⚠ 按下去就記，不管新分頁後來有沒有被瀏覽器擋掉 ——
    //     那是「他想去」的事實。
    fetch(`${API}/external-ai/visit`, { method: 'POST', headers: authHeaders() })
        .catch(() => { /* 統計失敗不影響任何事 */ });

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
        // ZH: 密碼區吃的是**這一份** prov，不另外發請求（見 renderProvision）。
        //     ⚠ 要放在下面那個 early return 之前 —— 額度讀不出數字（points 為 null）
        //     時密碼還是該顯示，那是兩件不同的事。
        if (!FORCED) renderProvision(prov);
        if (!STATE.provisioned) return renderProvisioning();

        if (bal.points == null) return renderNoBalance();

        value.textContent = bal.points.toLocaleString('en-US');
        unit.hidden = false;

        // ZH: 已開通且保留期內未確認 → 額度照常顯示，另外掛一個入口。
        //     不取代額度區：他有點數就能用，初始密碼是「還沒處理的事」不是「阻礙」。
        // ZH: v3.9 這裡原本會掛一句「你的 MYAI 初始密碼還沒改」（擁有者裁定拿掉）。
        //     密碼卡就在同一頁下面，而且標題就寫著「你的 MYAI 初始密碼」——
        //     在它上面再放一句話講同一件事，是同一個訊息說兩次。
        //     這一格留給額度提示（額度已用完 · 看用在哪 · 向管理員申請額度）。
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
        //     沒有這一行的話 STATE.provisioned 會永遠是 null，而 renderProvisioning()
        //     會把「前往 MYAI」停用 —— 額度讀不到就按不了 AI，那是錯的。
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
    // ZH: v3.9 還沒開通就**停用**主要動作，並給一個出口。
    //     在這之前是「按下去帶你到 provision.html」—— 那一頁的內容現在就在這一頁，
    //     跳到自己沒有意義；而讓他按下去開廠商登入頁更糟：他還沒有帳號。
    // ZH: ⚠ 這一頁沒有 lab.js 那支 setPrimary()，直接動按鈕。
    $('go-myai').disabled = true;
    $('stuck').hidden = false;
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
// ZH: 「前往 MYAI」分流（擁有者裁定 2026-08-24）——已開通就直接跳廠商。
// ZH: 還沒開通的人跳過去只會看到廠商的登入頁，而他根本還沒有帳號。
//     v3.9 之前的做法是帶他去 provision.html；那一頁已經併進這一頁，
//     所以改成**就地停用按鈕**並在旁邊講原因（見 renderProvisioning）。
$('go-myai').addEventListener('click', () => {
    // ZH: 未開通時按鈕已經是停用的（見 renderProvisioning），
    //     這一條是保險 —— 狀態還沒讀回來就被按到的話，不要送人去廠商登入頁。
    if (STATE.provisioned === false) { return; }
    goMyai();
});

// ZH: 先擋登入。requireLogin() 為 false 時已經在導向了，不要再發請求 ——
//     那些請求必定 401，只會在 console 留下看起來像壞掉的紅字。
if (requireLogin()) {
    loadBalance();
    // ZH: 檢視模式（?state=）不打後端，直接用假資料把密碼區畫出來。
    //     正常路徑由 loadBalance 拿到 prov 之後呼叫。
    if (FORCED) renderProvision(null);
}


// ── 語言切換時重繪 ───────────────────────────────────────────────────
// ZH: prefs.js 的字典掃描只換得掉 `data-i18n` 元素；本頁 JS 產生的內容要自己重跑。
//     只在語言**改變**時觸發（不是每次套用），所以不會在載入時多跑一次。
document.addEventListener('prefs:langchanged', () => {
    loadBalance();
    if (FORCED) renderProvision(null);
});


// ══════════════════════════════════════════════════════════════════════
// ZH: 初始密碼（v3.9 從 provision.js 搬過來）
//
// ZH: 後端契約（GET /external-ai/my-provision）有**三種**狀態：
//       provisioned=false                        → 還沒有 MYAI 帳號 → 沒有密碼可看
//       provisioned=true + initial_password       → 保留期內未確認 → 正常路徑
//       provisioned=true + initial_password=null  → 已確認或逾期 → 沒東西可看
//     當成兩種的話，「還沒有帳號」也會被帶去看一個空畫面。踩過一次。
//
// 隱私：身分一律由 JWT 推導，後端不吃任何身分參數，查不到別人的。
//       ack 會**立即銷毀**伺服器上的暫存密碼，不等保留期到 —— 所以文案要講明不可逆。
// ══════════════════════════════════════════════════════════════════════
/* ZH: ⚠ 這一支**不自己發請求**。loadBalance() 已經抓過 `/my-provision`
 *     （它要用 provisioned 來分流），再抓一次就是同一個端點打兩遍 ——
 *     而且兩份回應可能不一致，那種不一致沒有任何錯誤訊息。
 * ZH: 讀不到開通狀態時這一支根本不會被呼叫（loadBalance 進了 catch），
 *     密碼區就不出現。使用者看到的是額度那一塊的「暫時取不到額度」——
 *     一次失敗講一次就夠。
 */
function renderProvision(prov) {
    const d = FORCED ? mockProv(FORCED) : prov;

    // ZH: 沒有密碼可看（還沒開通／已確認／逾期）—— 整區不出現，也不留訊息。
    //     絕大多數人本來就沒有密碼，每次進來讀一次「你沒有密碼」是噪音。
    //     ⚠ 這與 provision.html 的行為不同：那一頁是**特地**點進去的，
    //     說「這裡沒有東西」才有意義。
    if (!d || !d.provisioned || !d.initial_password) return;

    $('acct').textContent = d.email || '—';
    $('pw').textContent = d.initial_password;
    $('pw-intro').textContent = d.retention_days
        ? T('prov_window', '這組密碼只在開通後 {d} 天內看得到。').replace('{d}', d.retention_days)
          + T('prov_change_soon', '請盡快到 MYAI 登入並改成自己的密碼。')
        : T('prov_change_soon', '請盡快到 MYAI 登入並改成自己的密碼。');
    $('pw-card').hidden = false;
}

$('copy').addEventListener('click', async () => {
    const pw = $('pw').textContent;
    try {
        await navigator.clipboard.writeText(pw);
        $('pw-note').textContent = T('prov_copied', '已複製到剪貼簿。');
    } catch {
        // ZH: 剪貼簿在非 https 或權限被拒時不可用。不要靜默失敗 ——
        //     密碼已設 user-select:all，直接告訴使用者可以手動選取。
        $('pw-note').textContent = T('prov_copy_manual', '這個瀏覽器不允許自動複製，請直接選取上面那一行。');
    }
    $('pw-note').hidden = false;
});

// ZH: 不可逆的動作。成功之後整區收起來 —— 密碼已經不存在了，留著會誤導。
$('ack').addEventListener('click', async () => {
    const btn = $('ack');
    btn.disabled = true;
    btn.textContent = T('prov_working', '處理中…');
    try {
        if (!FORCED) {
            const r = await fetch(`${API}/external-ai/my-provision/ack`,
                                  { method: 'POST', headers: authHeaders() });
            if (!r.ok) throw new Error(`HTTP ${r.status}`);
        }
        $('pw-card').hidden = true;
    } catch (e) {
        btn.disabled = false;
        btn.textContent = T('prov_ack', '我已經改好密碼了');
        $('pw-note').textContent = T('prov_clear_fail', '清除失敗') + `（${e.message || e}）。`
            + T('prov_clear_fail2', '可以再試一次；不影響你在 MYAI 已經改好的密碼。');
        $('pw-note').hidden = false;
    }
});

// ZH: 密碼區的假資料。與額度那支（mock）分開 —— 兩塊的狀態值不重疊。
function mockProv(kind) {
    if (kind === 'pw-error') throw new Error('強制錯誤狀態');
    if (kind === 'empty') return { provisioned: false };
    if (kind === 'pw-acked') return { provisioned: true, email: 'a1234567@example.com',
                                      initial_password: null, retention_days: 30 };
    if (kind === 'pw') return { provisioned: true, email: 'a1234567@example.com',
                                initial_password: 'Mcu-2026-x7Kq', retention_days: 30 };
    return null;
}
