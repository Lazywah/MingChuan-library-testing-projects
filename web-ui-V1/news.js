/* ==========================================================================
 * [畫面: 公告列表] — 使用者在這裡要完成：看完首頁那條橫幅以外的公告
 *
 * ZH: 這個畫面的存在理由來自首頁的「過多」狀態：公告超過一則時只顯示最新，
 *     附「查看全部 N 則」——那個連結必須有落點，否則「過多」狀態沒被解決。
 *
 * ⚠ 內容一律用 textContent 寫入，**不用 innerHTML**。
 *   公告是 admin 從後台輸入的自由文字；用 innerHTML 等於讓後台輸入可以在
 *   每個學生的瀏覽器裡執行 script。這裡沒有需要富文字的理由，不冒那個險。
 * ========================================================================== */
const API = '/api/v1';
const FORCED = new URLSearchParams(location.search).get('state');
const $ = (id) => document.getElementById(id);

// ZH: 後端 limit 上限 100。要更多得先有分頁，不是把上限調大。
const LIMIT = 50;

// ZH: 色系切換已集中到 prefs.js（跟帳號走）。
//     原本九個頁面各寫一份，**只有 app.js 那份會存與還原**——
//     於是「有些頁面換了顏色，其他頁面還沒變」。同一條規則不要有第二份實作。

function authHeaders() {
    const t = sessionStorage.getItem('ai_hud_token') || localStorage.getItem('ai_hud_token');
    return t ? { Authorization: 'Bearer ' + t } : {};
}

function paintMsg(text, cls) {
    $('msg').textContent = text;
    $('msg').className = cls;
    $('msg').hidden = false;
    $('list').textContent = '';
    $('more').hidden = true;
}

// ZH: 錯誤（紅框）
function showMsg(text) { paintMsg(text, 'inline-error'); }
// ZH: 空狀態／正常狀態／成功 —— 與錯誤共用同一個框，但**不是紅的**。
//     🔴 這兩支之前是同一支：「文件庫還沒有內容」「已清除暫存的初始密碼」
//     都用錯誤樣式顯示，看起來像出事了。
function showNote(text) { paintMsg(text, 'inline-note'); }

// ZH: 時間一律走 tz.js（釘死 Asia/Taipei）——見該檔檔頭的兩個問題。
function fmtDate(iso) {
    return TW.date(iso, '/') || String(iso || '').slice(0, 10);
}

function render(list) {
    const box = $('list');
    box.textContent = '';                    // 清掉骨架

    list.forEach((a) => {
        const art = document.createElement('article');
        art.className = 'post';
        if (a.is_pinned) art.dataset.pinned = '1';

        const head = document.createElement('div');
        head.className = 'post__head';

        if (a.is_pinned) {
            const tag = document.createElement('span');
            tag.className = 'post__pin';
            tag.textContent = T('news_pinned', '置頂');
            head.appendChild(tag);
        }

        const date = document.createElement('span');
        date.className = 'post__date';
        date.textContent = fmtDate(a.posted_at);
        head.appendChild(date);

        // ZH: **不顯示 posted_by。** 後端回的是 `users.id` 的 UUID 而不是名字
        //     （AnnouncementResponse.posted_by 是外鍵），實際畫面上會變成
        //     「2026/08/20  3ad36141-3bd9-4a14-bcef-4b23dcbf92b3  標題」。
        //     假資料用的是 'admin' 這種人名，所以檢視模式下看起來正常——
        //     **這個缺陷只在接真實 API 時才會出現**。
        //     對學生而言「誰發的」本來也不重要；要顯示的話後端得另外回名字。

        const h = document.createElement('h2');
        h.className = 'post__title';
        h.textContent = a.title || T('news_untitled', '(無標題)');

        const body = document.createElement('p');
        body.className = 'post__body';
        linkify(body, a.body || '');

        art.append(head, h, body);
        if (a.files && a.files.length) art.appendChild(fileList(a));
        box.appendChild(art);
    });

    // 過多：後端 limit 上限 100，這裡只取 LIMIT。取滿就明講可能還有更舊的。
    $('more').hidden = list.length < LIMIT;
    if (!$('more').hidden) {
        $('more').textContent = T('news_truncated', '只顯示最新的 {n} 則。更舊的公告目前無法在這裡瀏覽。')
            .replace('{n}', LIMIT);
    }
}

/* ==========================================================================
 * ZH: 內文裡的網址自動變連結（v3.9，擁有者裁定 2026-08-30）
 *
 * ZH: 🔴 做法是**只認網址，不吃 HTML**。整段內文仍然一個字元都不當標籤解析：
 *     這裡把文字切成「網址」與「非網址」兩種片段，非網址的用 createTextNode，
 *     網址的建一個 <a> 並用 `a.href = …` 設值 —— 全程沒有 innerHTML。
 *     所以管理員貼 `<script>` 進來，畫面上仍然是那七個字元。
 *
 * ZH: 🔴 連結文字**一律是完整網址**，不支援自訂錨點文字。
 *     這是防釣魚：使用者永遠看得到自己要去哪裡。而且這個限制不花成本 ——
 *     真的需要短文字的時候，寫「詳見 https://…」讀起來一樣清楚。
 *
 * ZH: 協定的判斷交給 Chrome.httpUrl（唯一一份實作）——
 *     `javascript:` / `data:` 那類不會通過，於是連結建不出來，維持純文字。
 *
 * ZH: ⚠ 尾隨標點不算網址的一部分。中文裡「請看 https://x.com/a。」那個句號
 *     會被瀏覽器當成路徑的一部分，連過去是 404。所以右邊的 `。，、）」.,;)]`
 *     一律退回文字節點。
 * ========================================================================== */
// ZH: 只抓 http(s) 開頭。不做「www. 開頭也算」那種猜測 ——
//     猜錯的代價是把一段普通文字變成壞掉的連結，而那看起來像是平台的錯。
//
// ZH: 🔴 字元集是**白名單**（RFC 3986 允許未編碼出現的那些），不是「非空白就算」。
//     第一版就是後者，於是中文緊接網址時整串被吃進去 ——
//     「請看 https://x.com/a。謝謝」變成一個連到
//     `https://x.com/a%E3%80%82%E8%AC%9D%E8%AC%9D` 的死連結。
//     中文裡**網址後面通常沒有空白**，所以這不是邊角案例，是常態。
//     改用白名單之後，中文字元自然落在網址外面，不必去猜哪些標點該砍。
const URL_RE = /https?:\/\/[A-Za-z0-9\-._~:\/?#\[\]@!$&'()*+,;=%]+/g;

// ZH: 半形標點放在網址尾端時要退回文字：英文寫法「see https://x.com/a.」
//     那個句點是句子的，不是網址的。
// ZH: ⚠ 只列**半形**。全形的（。，、）】）已經不在上面的白名單裡，
//     根本不會被匹配進來 —— 列在這裡就是永遠不會執行的死碼。
const TRAIL = '.,;:!?\'"';

function linkify(el, text) {
    let last = 0;
    let m;
    URL_RE.lastIndex = 0;
    while ((m = URL_RE.exec(text)) !== null) {
        let url = m[0];
        // ZH: 把尾隨標點切掉，切下來的部分回到文字。
        while (url.length && TRAIL.indexOf(url[url.length - 1]) >= 0) {
            url = url.slice(0, -1);
        }
        // ZH: 收尾的 `)` 只有在**沒有配對的 `(`** 時才砍。
        //     維基百科那種 `…/Foo_(bar)` 的括號是網址的一部分，
        //     無條件砍掉會得到一個 404 的連結。
        while (url.endsWith(')') &&
               (url.match(/\(/g) || []).length < (url.match(/\)/g) || []).length) {
            url = url.slice(0, -1);
        }
        const safe = window.Chrome.httpUrl(url);
        if (!safe) continue;               // ZH: 不合格就整段留在文字裡

        if (m.index > last) el.appendChild(document.createTextNode(text.slice(last, m.index)));

        const a = document.createElement('a');
        a.href = safe;
        a.textContent = safe;              // ZH: 顯示完整網址（見檔頭）
        a.target = '_blank';
        // ZH: noopener 必要 —— 少了它，開啟的頁面可以用 window.opener 改寫這一頁。
        a.rel = 'noopener noreferrer';
        el.appendChild(a);

        last = m.index + safe.length;
    }
    // ZH: ⚠ 最後這一段不能省。省掉的話「網址後面還有話」的公告會被截斷，
    //     而畫面上看不出來 —— 只是少了幾個字。
    if (last < text.length) el.appendChild(document.createTextNode(text.slice(last)));
}


/* ZH: 附件（v3.9）。
 *
 * ZH: 做成**按鈕不是連結**：下載要帶 Authorization 標頭（見 Chrome.download 的
 *     說明），而 <a href> 帶不了。做成看起來像連結卻點了 401 更糟 ——
 *     使用者會以為檔案壞了。
 * ZH: 檔名用 textContent 放，不進 innerHTML —— 那是管理員上傳時的原始檔名。
 */
function fileList(a) {
    const wrap = document.createElement('div');
    wrap.className = 'post__files';

    const label = document.createElement('span');
    label.className = 'post__files-label';
    label.textContent = T('news_files', '附件');
    wrap.appendChild(label);

    a.files.forEach((f) => {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'post__file';
        btn.textContent = f.filename + '（' + fmtSize(f.size_bytes) + '）';
        btn.addEventListener('click', async () => {
            const before = btn.textContent;
            btn.disabled = true;
            btn.textContent = T('news_downloading', '下載中…');
            try {
                await window.Chrome.download(
                    '/announcements/' + encodeURIComponent(a.id)
                    + '/files/' + encodeURIComponent(f.id), f.filename);
                btn.textContent = before;
            } catch (e) {
                // ZH: 失敗要講出來。靜默失敗時使用者只會一直按同一顆按鈕。
                btn.textContent = T('news_dl_fail', '下載失敗，請再試一次');
            }
            btn.disabled = false;
        });
        wrap.appendChild(btn);
    });
    return wrap;
}

// ZH: 位元組轉人看得懂的大小。附件多半是 MB 等級，KB 以下就寫 KB。
function fmtSize(n) {
    const b = Number(n) || 0;
    if (b >= 1024 * 1024) return (b / 1024 / 1024).toFixed(1) + ' MB';
    return Math.max(1, Math.round(b / 1024)) + ' KB';
}


async function load() {
    if (FORCED === 'loading') return;
    try {
        let list;
        if (FORCED) {
            list = mock(FORCED);
        } else {
            const r = await fetch(`${API}/announcements?limit=${LIMIT}`,
                                  { headers: { Accept: 'application/json', ...authHeaders() } });
            if (!r.ok) throw new Error(`HTTP ${r.status}`);
            list = await r.json();
        }
        if (!Array.isArray(list) || !list.length) {
            return showNote(T('news_empty', '目前沒有公告。'));
        }
        render(list);
        $('msg').hidden = true;
    } catch (e) {
        showMsg(T('news_fail', '暫時取不到公告') + `（${e.message || e}）。`
            + T('retry_refresh', '可以重新整理再試一次。'));
    }
}

// ── 假資料 ───────────────────────────────────────────────────────────
function mock(kind) {
    if (kind === 'error') throw new Error('強制錯誤狀態');
    if (kind === 'empty') return [];
    const one = (i, pinned) => ({
        id: i, title: `示範公告第 ${i} 則：系統維護與功能更新說明`,
        body: '這是公告內容。詳情請看 https://www.mcu.edu.tw/announcement。第二段說明維護時間與影響範圍。',
        posted_by: 'admin', posted_at: `2026-08-${String((i % 28) + 1).padStart(2, '0')}T09:00:00`,
        is_pinned: pinned ? 1 : 0, is_visible: 1,
        // ZH: 第一則帶附件與網址，好讓 ?state= 看得到那兩塊的樣子。
        //     沒有這個的話，附件與自動連結**只有真的有資料時才驗得到** ——
        //     而那正是最容易改壞卻沒人發現的兩塊。
        files: i === 1
            ? [{ id: 1, filename: '維護說明.pdf', size_bytes: 1258291 },
               { id: 2, filename: '時程表.xlsx', size_bytes: 20480 }]
            : [],
    });
    if (kind === 'overflow') return Array.from({ length: LIMIT }, (_, i) => one(i + 1, i === 0));
    return [one(1, true), one(2, false), one(3, false)];
}

// ── 啟動 ─────────────────────────────────────────────────────────────
function requireLogin() {
    const t = sessionStorage.getItem('ai_hud_token') || localStorage.getItem('ai_hud_token');
    if (t || FORCED) return true;
    location.replace('login.html');
    return false;
}
if (requireLogin()) load();


// ── 語言切換時重繪 ───────────────────────────────────────────────────
// ZH: prefs.js 的字典掃描只換得掉 `data-i18n` 元素；本頁 JS 產生的內容要自己重跑。
//     只在語言**改變**時觸發（不是每次套用），所以不會在載入時多跑一次。
document.addEventListener('prefs:langchanged', () => { load(); });
