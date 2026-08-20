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

function showMsg(text) {
    $('msg').textContent = text;
    $('msg').hidden = false;
    $('list').textContent = '';
    $('more').hidden = true;
}

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
        body.textContent = a.body || '';      // ⚠ 不用 innerHTML，見檔頭

        art.append(head, h, body);
        box.appendChild(art);
    });

    // 過多：後端 limit 上限 100，這裡只取 LIMIT。取滿就明講可能還有更舊的。
    $('more').hidden = list.length < LIMIT;
    if (!$('more').hidden) {
        $('more').textContent = T('news_truncated', '只顯示最新的 {n} 則。更舊的公告目前無法在這裡瀏覽。')
            .replace('{n}', LIMIT);
    }
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
            return showMsg(T('news_empty', '目前沒有公告。'));
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
        body: '這是公告內容。第二段說明維護時間與影響範圍，以及使用者需要做什麼。',
        posted_by: 'admin', posted_at: `2026-08-${String((i % 28) + 1).padStart(2, '0')}T09:00:00`,
        is_pinned: pinned ? 1 : 0, is_visible: 1,
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
