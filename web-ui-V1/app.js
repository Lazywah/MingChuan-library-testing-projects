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

/* ZH: 開發期強制狀態：?state=empty|loading|error|overflow|low|noquota
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
        maybeRenderFlow();
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
        //     maybeRenderFlow 一直等，流程條**安靜地不出現**。
        if (STATE.provisioned === null) { STATE.provisioned = true; maybeRenderFlow(); }
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
    if (STATE.provisioned === null) { STATE.provisioned = false; maybeRenderFlow(); }
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
// ZH: 顯示上限 7 則。**排序完全交給後端** —— announcements 端點已經把 is_pinned
//     的排在最前面（見 routers/announcements.py::list_announcements）。
//     前端在這裡重排的話，兩邊的規則遲早會分岔，而分岔時沒有人會發現：
//     畫面看起來仍然「有排序」，只是順序是錯的。
const NEWS_MAX = 7;

async function loadNews() {
    const box = $('news');
    const list = $('news-list');
    try {
        let rows;
        if (FORCED === 'overflow') {
            rows = Array.from({ length: 12 }, (_, i) => ({
                title: '示範公告第 ' + (i + 1) + ' 則：系統維護與功能更新說明',
                posted_at: '2026-08-16T09:00:00',
                is_pinned: i === 0 ? 1 : 0,
            }));
        } else if (FORCED === 'empty' || FORCED === 'error') {
            // 空／錯誤：整塊不出現，其餘照常（部分失敗不整頁死）
            return;
        } else {
            // ZH: 🔴 多要一筆。只要 NEWS_MAX 筆的話，rows.length 永遠不會超過它，
            //     下面那行「還有沒有更多」就永遠是否 ——
            //     「看全部公告」永遠不會出現，而且**畫面上看不出來**（只是少一個連結）。
            //     這個錯誤我實際寫出來過：用 ?state=overflow 驗時它是**本地造 12 筆假資料**，
            //     繞過了 limit，於是連結正常出現 —— 驗的路徑不是使用者走的路徑。
            rows = await get('/announcements?limit=' + (NEWS_MAX + 1));
        }
        if (!rows || !rows.length) return;    // 沒有公告 → 整塊不存在

        list.textContent = '';
        rows.slice(0, NEWS_MAX).forEach((a) => {
            const li = document.createElement('li');
            li.className = 'news__item';

            const d = document.createElement('span');
            d.className = 'news__date';
            d.textContent = (a.posted_at || '').slice(5, 10).replace('-', '/');
            li.appendChild(d);

            // ZH: 置頂用「文字徽章 + 底色」兩個訊號，不要只靠底色 ——
            //     只有底色的話，色覺障礙或高對比模式下就完全沒有這個資訊。
            if (a.is_pinned) {
                li.classList.add('is-pinned');
                const p = document.createElement('span');
                p.className = 'news__pin';
                p.textContent = T('idx_news_pinned', '置頂');
                li.appendChild(p);
            }

            const t = document.createElement('span');
            t.className = 'news__title';
            // ZH: 用 textContent 不用 innerHTML —— 公告是管理端打進來的自由文字。
            t.textContent = a.title || '';
            li.appendChild(t);

            list.appendChild(li);
        });

        // ZH: 只有「還有沒顯示到的」才給看全部；剛好 7 則以內就不必了。
        //     上面要了 NEWS_MAX+1 筆，所以這裡才分得出「剛好 7 則」與「超過 7 則」。
        $('news-all').hidden = rows.length <= NEWS_MAX;
        box.hidden = false;
    } catch (e) {
        /* 公告取不到 → 整塊不出現，首頁其餘照常 */
    }
}

// ══════════════════════════════════════════════════════════════════════
// ZH: 引導流程的狀態
// ----------------------------------------------------------------------
// ZH: 🔴 **只有頭尾兩步偵測得到**，中間兩步刻意不標狀態：
//       開通 MYAI  → /external-ai/my-provision 的 provisioned（首頁本來就在打）
//       看文件庫    → 沒有任何追蹤，測不到
//       開實驗室    → /lab/status 會去問 Docker，放首頁太重
//       送 GPU 訓練 → /jobs?limit=1 的 total（多一支輕量呼叫）
//
// ZH: 所以「已完成」這個標籤**只會出現在偵測得到的步驟上**。
//     對測不到的步驟猜一個狀態，比不標更糟 —— 使用者會相信它。
// ══════════════════════════════════════════════════════════════════════
const STATE = { provisioned: null, hasJobs: null };
let FLOW_FORCED_OPEN = false;

async function loadJobCount() {
    try {
        const r = await get('/jobs?limit=1');
        STATE.hasJobs = !!(r && typeof r.total === 'number' && r.total > 0);
    } catch (e) {
        // ZH: 取不到就當「沒訓練過」——寧可多顯示一次引導，也不要把它藏起來。
        STATE.hasJobs = false;
    }
    maybeRenderFlow();
}

function maybeRenderFlow() {
    if (STATE.provisioned === null || STATE.hasJobs === null) return;
    renderFlow();
}

function renderFlow() {
    const sec = $('flow');
    const reopen = $('flow-reopen');

    // ZH: 送過訓練 ＝ 已經上手 → 引導讓位。不是永久拿掉，下面那一行叫得回來。
    if (STATE.hasJobs && !FLOW_FORCED_OPEN) {
        sec.hidden = true;
        reopen.hidden = false;
        return;
    }
    sec.hidden = false;
    reopen.hidden = true;

    // ZH: ⚠ 只排**看得見**的步驟。文件庫沒內容時那一格是 hidden，
    //     若照 HTML 的順序寫死標籤，就會出現「下一步」後面接「最後」中間跳掉一格。
    const items = Array.prototype.filter.call(
        $('flow-steps').children, (li) => !li.hidden);
    if (!items.length) return;

    // ZH: 目前在第幾步。只用偵測得到的兩個事實推：
    //     沒開通 → 停在開通那一步；已開通但沒訓練過 → 往後推一格。
    const idxMyai = items.findIndex((li) => li.querySelector('#step-myai'));
    let cur;
    if (!STATE.provisioned) {
        cur = idxMyai >= 0 ? idxMyai : 0;
    } else {
        cur = (idxMyai >= 0 ? idxMyai : -1) + 1;
        if (cur >= items.length) cur = items.length - 1;
    }

    items.forEach((li, n) => {
        const slot = li.querySelector('[data-state]');
        if (!slot) return;
        let key = '', fallback = '';
        if (n < cur) { key = 'st_done'; fallback = '已完成'; }
        else if (n === cur) { key = 'st_now'; fallback = '現在在這'; }
        else if (n === cur + 1) { key = 'st_next'; fallback = '下一步'; }
        slot.textContent = key ? T(key, fallback) : '';
        li.classList.toggle('is-now', n === cur);
        li.classList.toggle('is-done', n < cur);
    });

    // ZH: 文件庫那一格是 docs-entry.js **非同步**打開的（它要先抓 docs-content.json）。
    //     沒有這個 observer 的話，第一次算標籤時它還是 hidden，
    //     打開之後標籤就對不上了 —— 而且畫面上看不出哪裡怪。
    if (!renderFlow._observing) {
        renderFlow._observing = true;
        new MutationObserver(() => renderFlow()).observe(
            $('flow-steps'), { attributes: true, attributeFilter: ['hidden'], subtree: true });
    }
}

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
// ZH: 「問 AI」分流（擁有者裁定 2026-08-24）——已開通就直接跳廠商；
//     還沒開通的話跳過去只會看到廠商的登入頁而他根本沒有帳號，
//     所以改帶到說明頁（provision.html 已經會講「還在開通中」，
//     並且在那裡提供問題回報的入口）。
$('go-myai').addEventListener('click', () => {
    if (STATE.provisioned === false) { location.href = 'provision.html'; return; }
    goMyai();
});
$('link-usage').addEventListener('click', (ev) => {
    ev.preventDefault();
    location.href = 'usage.html';
});
$('link-report').addEventListener('click', (ev) => {
    ev.preventDefault();
    location.href = 'report.html';
});
// ZH: 引導收起來之後叫回來。只影響這一次瀏覽，不寫進偏好——
//     那是「我想再看一次」，不是「我要永遠顯示」。
$('flow-show').addEventListener('click', () => {
    FLOW_FORCED_OPEN = true;
    renderFlow();
});

// ZH: 先擋登入。requireLogin() 為 false 時已經在導向了，不要再發請求 ——
//     那些請求必定 401，只會在 console 留下看起來像壞掉的紅字。
if (requireLogin()) {
    loadBalance();
    loadNews();
    loadJobCount();
}


// ── 語言切換時重繪 ───────────────────────────────────────────────────
// ZH: prefs.js 的字典掃描只換得掉 `data-i18n` 元素；本頁 JS 產生的內容要自己重跑。
//     只在語言**改變**時觸發（不是每次套用），所以不會在載入時多跑一次。
document.addEventListener('prefs:langchanged', () => {
    loadBalance();
    loadNews();
    // ZH: 流程的狀態標籤也是 JS 產生的，換語言要一起重畫（狀態已在手上，不用重打 API）。
    if (STATE.provisioned !== null && STATE.hasJobs !== null) renderFlow();
});
