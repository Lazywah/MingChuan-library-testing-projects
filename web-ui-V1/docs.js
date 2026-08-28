/* ==========================================================================
 * [畫面: 文件庫] — 使用者在這裡要完成：看別人做過什麼，知道自己能做到什麼程度
 *
 * ZH: 內容來源是 `docs-content.json`（同目錄的靜態檔），不是後端 API。
 *     理由：內容量小、變動不頻繁；做一套 CRUD 後台的成本遠大於編輯一個檔案。
 *     等到「有人常常要改、而且那個人不該碰版控」時再做後台才划算。
 *
 * ⚠ 規格 V3 修正：**文件庫入口在有內容前不出現**——連到空頁比沒有連結更糟。
 *   那條規則的實作在 **docs-entry.js**，不在這裡；同一條規則有兩份實作，
 *   遲早會有一份被漏改。
 * ========================================================================== */
const MANIFEST = 'docs-content.json';
const FORCED = new URLSearchParams(location.search).get('state');
const $ = (id) => document.getElementById(id);

const MAX_ITEMS = 60;

// ZH: 分類的**鍵**是資料契約（docs-content.json 用它），不能翻；顯示名稱才翻。
//     用函式而非常數：模組層的物件在載入時就定案，切換語言不會更新。
//
// ZH: 這裡的順序就是篩選鈕的順序（見 buildFilters）——擁有者指定的排法是
//     教學 → 成品模型 → 問題交流。
const TYPE_KEYS = ['tutorial', 'model', 'qa'];
const typeLabel = (k) => ({
    tutorial: T('docs_t_tutorial', '教學'),
    model: T('docs_t_model', '過往學長姐成品模型'),
    qa: T('docs_t_qa', '問題交流'),
}[k] || T('docs_t_other', '其他'));

// ZH: 2026-08-28 改名前的舊鍵。內容檔裡當時只有一筆（已一併改掉），
//     但**範例區塊寫的是舊鍵**，可能有人照著複製過。
//     不做對照的話那些項目會落到「其他」，而且沒有篩選鈕收得到它們 ——
//     看起來像分類壞了，實際上是鍵過期。
const LEGACY_TYPE = { video: 'tutorial', work: 'model', solution: 'qa' };
const normType = (t) => LEGACY_TYPE[t] || t;

// ZH: 色系切換已集中到 prefs.js（跟帳號走）。
//     原本九個頁面各寫一份，**只有 app.js 那份會存與還原**——
//     於是「有些頁面換了顏色，其他頁面還沒變」。同一條規則不要有第二份實作。

// ── 取內容 ───────────────────────────────────────────────────────────
async function fetchItems() {
    if (FORCED === 'error') throw new Error('強制錯誤狀態');
    if (FORCED) return mock(FORCED);
    // ZH: cache: 'no-cache' —— 這個檔沒有 ?v= 版號（它是資料不是資產），
    //     不加的話管理者改完內容看不到變化，會以為沒存到。
    const r = await fetch(MANIFEST, { cache: 'no-cache' });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const d = await r.json();
    return Array.isArray(d.items) ? d.items : [];
}

function paintMsg(html, cls) {
    // ZH: 這裡用 innerHTML 是安全的 —— 參數全部是本檔的字面值（要放連結），
    //     不是外部資料。**外部資料一律 textContent**（見 card()）。
    $('msg').innerHTML = html;
    $('msg').className = cls;
    $('msg').hidden = false;
    $('list').textContent = '';
    $('more').hidden = true;
}

// ZH: 錯誤（紅框）
// ZH: ⚠ 只有這一支會把篩選列藏起來 —— 內容根本沒載到的時候，
//     一排點了沒反應的分類鈕比沒有分類鈕更糟。
//     空狀態不藏（見 showNote 與 load）。
function showMsg(html) { paintMsg(html, 'inline-error'); $('filters').hidden = true; }
// ZH: 空狀態／正常狀態／成功 —— 與錯誤共用同一個框，但**不是紅的**。
//     🔴 這兩支之前是同一支：「文件庫還沒有內容」「已清除暫存的初始密碼」
//     都用錯誤樣式顯示，看起來像出事了。
function showNote(html) { paintMsg(html, 'inline-note'); }

// ── 渲染 ─────────────────────────────────────────────────────────────
let ALL = [];
let FILTER = 'all';

function card(it) {
    const a = document.createElement('a');
    a.className = 'card';
    a.href = it.url || '#';
    // ZH: 外部連結一律新分頁 + noopener。站內相對路徑則同頁開，不打斷瀏覽。
    if (/^https?:/i.test(it.url || '')) {
        a.target = '_blank';
        a.rel = 'noopener noreferrer';
    }

    const tag = document.createElement('span');
    tag.className = 'card__tag';
    tag.textContent = typeLabel(normType(it.type));

    const h = document.createElement('h2');
    h.className = 'card__title';
    h.textContent = it.title || T('news_untitled', '(無標題)');      // ⚠ textContent，內容是人工輸入

    const p = document.createElement('p');
    p.className = 'card__desc';
    p.textContent = it.desc || '';

    const foot = document.createElement('div');
    foot.className = 'card__foot';
    foot.textContent = [it.author, it.date].filter(Boolean).join(' · ');

    a.append(tag, h, p, foot);
    return a;
}

function render() {
    const list = FILTER === 'all' ? ALL : ALL.filter((x) => normType(x.type) === FILTER);
    const box = $('list');
    box.textContent = '';
    list.slice(0, MAX_ITEMS).forEach((it) => box.appendChild(card(it)));

    // ZH: 分類鈕一律顯示，所以「點了某一類卻沒有東西」是**正常會發生的事**。
    //     不講的話那裡就是一片空白，看起來像載入失敗。
    // ZH: ⚠ 只在整個庫有內容時才講 —— 整個庫是空的時候 #msg 已經有引導訊息，
    //     兩則同時出現會互相干擾。
    if (!list.length && ALL.length) {
        const none = document.createElement('p');
        none.className = 'footnote';
        none.textContent = T('docs_none_in_type', '這個分類還沒有內容。');
        box.appendChild(none);
    }

    $('more').hidden = list.length <= MAX_ITEMS;
    if (!$('more').hidden) {
        $('more').textContent = T('docs_truncated', '只顯示前 {n} 筆（共 {t} 筆）。')
            .replace('{n}', MAX_ITEMS).replace('{t}', list.length);
    }
}

function buildFilters() {
    // ZH: 2026-08-28 擁有者裁定：**分類鈕一律顯示**，哪怕某一類、甚至整個庫
    //     都還沒有內容。理由是使用者要先看得出這個庫會放哪三種東西。
    //     先前的兩道門檻（至少 6 筆、至少 2 類）都拿掉了。
    // ZH: 順序取自 TYPE_KEYS —— 不是資料出現的順序，否則鈕的排法會隨著
    //     內容檔的編輯順序改變，同一個人兩次看到的順序不一樣。
    const box = $('filters');
    box.textContent = '';
    [['all', T('docs_all', '全部')], ...TYPE_KEYS.map((k) => [k, typeLabel(k)])].forEach(([k, label], i) => {
        const b = document.createElement('button');
        b.type = 'button';
        b.textContent = label;
        b.setAttribute('aria-pressed', String(i === 0));
        b.addEventListener('click', () => {
            FILTER = k;
            box.querySelectorAll('button').forEach((x) => x.setAttribute('aria-pressed', String(x === b)));
            render();
        });
        box.appendChild(b);
    });
    box.hidden = false;
}

async function load() {
    if (FORCED === 'loading') return;
    try {
        ALL = await fetchItems();
        // ZH: 在空狀態的 return 之前就建好 —— 沒有內容時也要看得到三個分類。
        buildFilters();
        if (!ALL.length) {
            // ZH: 空狀態兼任引導（Nielsen #10）——不要只說「沒有內容」就停在那裡。
            // ZH: 引導的去處用 .btn--minor 而非句中連結：實測句中那顆只有 19px，
            //     不到 --tap-min 44px。這裡是**動作**（去訓練第一個模型），不是引述連結。
            return showNote(T('docs_empty1', '文件庫還沒有內容。') + '<br>'
                + T('docs_empty2', '這裡之後會放同學的作品與教學影片。想成為第一個嗎？') + '<br>'
                + `<a class="btn--minor" href="gpu.html">${T('docs_empty_cta', '從訓練你的第一個模型開始')}</a>`);
        }
        ALL.sort((a, b) => String(b.date || '').localeCompare(String(a.date || '')));
        $('msg').hidden = true;
        render();
    } catch (e) {
        showMsg(T('docs_fail', '暫時取不到文件庫內容') + `（${e.message || e}）。`
            + T('retry_refresh', '可以重新整理再試一次。'));
    }
}

// ZH: 「入口要不要出現」的判斷**不在這裡**，在 docs-entry.js。
//     同一條規則有兩份實作，遲早會有一份被漏改。

// ── 假資料 ───────────────────────────────────────────────────────────
function mock(kind) {
    const one = (i, type) => ({
        type, title: `示範項目 ${i}：用 GPU 訓練影像分類器`,
        desc: '用 2000 張圖片訓練，正確率 94%。含資料前處理與訓練腳本。',
        author: '示範作者', date: `2026-08-${String((i % 28) + 1).padStart(2, '0')}`,
        url: 'https://example.mcu.edu.tw/',
    });
    if (kind === 'empty') return [];
    if (kind === 'few') return [one(1, 'model'), one(2, 'tutorial')];
    if (kind === 'overflow') {
        const kinds = ['tutorial', 'model', 'qa'];
        return Array.from({ length: 70 }, (_, i) => one(i + 1, kinds[i % 3]));
    }
    return Array.from({ length: 8 }, (_, i) => one(i + 1, ['tutorial', 'model', 'qa'][i % 3]));
}

// ── 啟動 ─────────────────────────────────────────────────────────────
// ZH: 這一頁**不擋登入**——文件庫是「看別人做過什麼」，沒有個人資料，
//     也是新生評估這個平台值不值得用的地方。要求先登入等於在入口就流失。
load();


// ── 語言切換時重繪 ───────────────────────────────────────────────────
// ZH: prefs.js 的字典掃描只換得掉 `data-i18n` 元素；本頁 JS 產生的內容要自己重跑。
//     只在語言**改變**時觸發（不是每次套用），所以不會在載入時多跑一次。
document.addEventListener('prefs:langchanged', () => { load(); });
