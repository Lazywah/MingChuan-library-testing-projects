/* ==============================================================================
   app.js — v2 使用者端（主線首頁）
   ==============================================================================
   規格：docs/06-ui-V1-design.md。四個狀態全做，可用 ?state= 強制展示。

   本檔只負責主線首頁。其餘畫面各自有自己的 HTML+JS：
   login / myai / gpu / usage / provision / lab / news / report。

   ZH: v3.9 額度卡與「前往 MYAI」整組搬去 myai.js —— 首頁現在只剩公告與分組卡片。
       ⚠ 不要為了「首頁看得到額度」把那段複製回來：同一台狀態機兩份實作，
       分岔的時候沒有任何錯誤訊息。要的話請另做一條獨立的一行提示。
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
            // ZH: v4.1 整列可點 → news.html（2026-09-01 修）。
            //     內文與附件**只活在 news.html**，但首頁的項目原本是死文字、
            //     「看全部公告」又只在超過 7 則時出現 —— 只有 1 則公告時，
            //     內文與圖片變成「存在但到不了」。實際發生：管理員發了
            //     帶圖公告，使用端點不開、什麼都看不到。
            const go = document.createElement('a');
            go.className = 'news__go';
            // ZH: v4.2 帶 ?open=<id> —— news.html 會直接開那一則的彈窗，
            //     省掉「點了標題還要再點一次」。
            go.href = 'news.html?open=' + encodeURIComponent(a.id);
            go.setAttribute('aria-label',
                T('idx_news_open', '看公告內文與附件'));

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
            // ZH: 英文介面且有英文標題才用英文（見 news.js 的 pickLang）。
            //     這裡只有標題，內文不在首頁上。
            const en = (window.Prefs && window.Prefs.get().ui_lang) === 'en';
            t.textContent = (en && a.title_en) || a.title || '';

            // ZH: 日期/徽章/標題全部收進連結，整列都是點擊面。
            while (li.firstChild) go.appendChild(li.firstChild);
            go.appendChild(t);
            li.appendChild(go);

            list.appendChild(li);
        });

        // ZH: v4.1 —— 有公告就顯示「看全部公告」。
        //     原本只在超過 7 則時出現（想省一個重複入口），但 news.html 是
        //     內文與附件的**唯一**去處，入口藏起來等於整個功能藏起來。
        //     （項目本身 v4.1 起也可點，這條是給「習慣找按鈕」的人的第二入口。）
        $('news-all').hidden = false;
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
// ZH: 這裡原本寫著「問 AI」的開通分流。v3.9 那段連同額度卡一起搬去 myai.js ——
//     首頁的「體驗大模型」現在只是一個連結，不需要知道開通了沒。
// ZH: 先擋登入。requireLogin() 為 false 時已經在導向了，不要再發請求 ——
//     那些請求必定 401，只會在 console 留下看起來像壞掉的紅字。
if (requireLogin()) {
    loadNews();
}


// ── 語言切換時重繪 ───────────────────────────────────────────────────
// ZH: prefs.js 的字典掃描只換得掉 `data-i18n` 元素；本頁 JS 產生的內容要自己重跑。
//     只在語言**改變**時觸發（不是每次套用），所以不會在載入時多跑一次。
document.addEventListener('prefs:langchanged', () => {
    loadNews();
    // ZH: 分組卡片的文案全部帶 data-i18n，prefs.js 的字典掃描換得掉，
    //     所以這裡不必再重畫它 —— 只有 JS 產生的（額度提示、公告）要自己重跑。
});
