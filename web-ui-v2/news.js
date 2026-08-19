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

function fmtDate(iso) {
    if (!iso) return '';
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return String(iso).slice(0, 10);
    return `${d.getFullYear()}/${String(d.getMonth() + 1).padStart(2, '0')}/`
         + `${String(d.getDate()).padStart(2, '0')}`;
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
            tag.textContent = '置頂';
            head.appendChild(tag);
        }

        const date = document.createElement('span');
        date.className = 'post__date';
        date.textContent = fmtDate(a.posted_at);
        head.appendChild(date);

        if (a.posted_by) {
            const who = document.createElement('span');
            who.className = 'post__by';
            who.textContent = a.posted_by;
            head.appendChild(who);
        }

        const h = document.createElement('h2');
        h.className = 'post__title';
        h.textContent = a.title || '(無標題)';

        const body = document.createElement('p');
        body.className = 'post__body';
        body.textContent = a.body || '';      // ⚠ 不用 innerHTML，見檔頭

        art.append(head, h, body);
        box.appendChild(art);
    });

    // 過多：後端 limit 上限 100，這裡只取 LIMIT。取滿就明講可能還有更舊的。
    $('more').hidden = list.length < LIMIT;
    if (!$('more').hidden) {
        $('more').textContent = `只顯示最新的 ${LIMIT} 則。更舊的公告目前無法在這裡瀏覽。`;
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
            return showMsg('目前沒有公告。');
        }
        render(list);
        $('msg').hidden = true;
    } catch (e) {
        showMsg(`暫時取不到公告（${e.message || e}）。可以重新整理再試一次。`);
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
