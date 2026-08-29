/* ==========================================================================
 * [畫面: Lab] — 使用者在這裡要完成：把瀏覽器版 VS Code 打開來寫程式
 *
 * ZH: D3 定的行為是**同頁顯示啟動狀態 → 就緒後才開新分頁**。
 *     容器要 5–10 秒；直接開新分頁會看到空白，而空白比等待更糟——
 *     使用者分不出「還沒好」和「壞了」。
 *
 * ⚠ 新分頁能不能進得去，靠的是 **`ai_hud_token` cookie**，不是 sessionStorage。
 *   nginx 對 `/code/<uid>/` 掛 `auth_request /_lab_authz`，而後端的 get_current_user
 *   同時吃 Bearer 與該 cookie（v2.1）。**sessionStorage 帶不進新分頁**，
 *   所以登入時必須拿到 Set-Cookie（login.js 已明寫 credentials）。
 *   若 cookie 不在，新分頁會是 401 頁面而不是 VS Code —— 下面有對應的說明文案。
 *
 * 與 v1.5 的差異：v1.5 在 v2.7 改成 iframe 內嵌（為了讓小基泡泡浮在上面）。
 *   v2 依 D3 走新分頁：v2 目前沒有小基，而 IDE 需要完整視窗高度。
 *   若日後 v2 也放小基，這個決定要重新檢視。
 * ========================================================================== */
const API = '/api/v1';

// ZH: v3.6 —— 目前選中的存檔。null＝預設那一份（既有使用者的行為完全不變）。
let currentSession = null;

// ZH: 名稱來自使用者自己取的名字，一律逸出。
function esc(s) {
    return String(s).replace(/[&<>"']/g, (c) =>
        ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}
const FORCED = new URLSearchParams(location.search).get('state');
const $ = (id) => document.getElementById(id);

let POLL = null;

// ZH: 色系切換已集中到 prefs.js（跟帳號走）。
//     原本九個頁面各寫一份，**只有 app.js 那份會存與還原**——
//     於是「有些頁面換了顏色，其他頁面還沒變」。同一條規則不要有第二份實作。

function authHeaders() {
    const t = sessionStorage.getItem('ai_hud_token') || localStorage.getItem('ai_hud_token');
    return t ? { Authorization: 'Bearer ' + t } : {};
}

async function api(path, opts = {}) {
    const r = await fetch(API + path, {
        headers: { Accept: 'application/json', ...authHeaders(), ...(opts.headers || {}) },
        credentials: 'include',
        ...opts,
    });
    if (!r.ok) {
        const d = await r.json().catch(() => ({}));
        throw new Error(d.detail || `HTTP ${r.status}`);
    }
    return r.json().catch(() => ({}));
}

function setPrimary({ label, enabled }) {
    $('go').textContent = label;
    $('go').disabled = !enabled;
}

function note(text) {
    $('note').textContent = text || '';
    $('note').hidden = !text;
}

const mins = (s) => (s == null ? '—' : `${Math.floor(s / 60)}${T('unit_min', ' 分')}`);

// ── 狀態 ─────────────────────────────────────────────────────────────
/* ZH: ⚠ 這四個是**頂層**函式。v3.9 加它們時曾經誤植到 render() 內部
 *     （縮排 0，所以看起來像頂層，語法也合法 —— check_js_syntax 照樣綠）。
 *     結果是每次 render 都重新建立一次，而且讀的人會以為它們是模組層的工具。
 *     放在這裡：render 只負責畫，判斷門檻的邏輯不歸它管。
 */
/* ── GPU 借用提示（v3.9）────────────────────────────────────────────
 * ZH: 桃園只有一張卡，實驗室會獨佔它 —— 所以除了「你正佔著卡」之外，
 *     還要講**還剩多久**。不講的話使用者不知道自己什麼時候會被關掉，
 *     而被關掉時他會以為是當機。
 *
 * ZH: 🔴 後端給的是**到期時刻**不是剩餘秒數。剩餘秒數在頁面放著不動時
 *     會越來越不準（而且看起來完全正常）；到期時刻由前端自己減，
 *     放多久、重新整理幾次都是對的。
 *
 * ZH: 剩 10 分鐘以內改用警示語氣 —— 那是「該存檔了」的時間點。
 */
/* ZH: 預警門檻（擁有者裁定 2026-08-29）：30 / 10 / 5 分鐘。
 *
 * ZH: GPU 借用與每日額度**共用同一組門檻**。兩套的話，使用者要記兩種規則，
 *     而且哪一個先到取決於當下狀態 —— 那不是他該花心思的地方。
 *
 * ZH: 回傳 'none' | 'notice'(≤30) | 'warn'(≤10) | 'urgent'(≤5) | 'over'(≤0)。
 *     只回級別不回文案 —— 兩個地方的句子不一樣，但緊急程度的判準要是同一個。
 */
const WARN_AT = [30, 10, 5];

function warnLevel(min) {
    if (min == null || !isFinite(min)) return 'none';
    if (min <= 0) return 'over';
    if (min <= WARN_AT[2]) return 'urgent';
    if (min <= WARN_AT[1]) return 'warn';
    if (min <= WARN_AT[0]) return 'notice';
    return 'none';
}

function gpuNote(d) {
    const base = T('lab_gpu_on', '這一份實驗室正在使用 GPU。用完請按「關閉實驗室」讓給下一位。');
    if (!d.gpu_deadline) return base;
    // ZH: 用**到期時刻**減，不是後端給的剩餘秒數 —— 頁面放著不動時
    //     剩餘秒數會越來越不準，而且看起來完全正常。
    const left = Math.round((new Date(d.gpu_deadline) - Date.now()) / 60000);
    const lv = warnLevel(left);
    if (lv === 'none') return base;
    if (lv === 'over') return `${base}　${T('lab_gpu_expiring', 'GPU 借用時間已到，實驗室即將自動關閉。')}`;
    const tmpl = lv === 'notice'
        ? T('lab_gpu_left', 'GPU 借用還剩 {n} 分鐘。')
        : T('lab_gpu_soon', 'GPU 只剩 {n} 分鐘，請盡快存檔。');
    return `${base}　${tmpl.replace('{n}', left)}`;
}

/* ZH: 每日額度的預警。
 * ZH: 🔴 額度用完是**當場關閉**（與 hard_limit 一致，檔案在 volume 裡不會遺失）。
 *     沒有預警的話那看起來像當機 —— 這幾句就是唯一的預告。
 * ZH: ⚠ 只在**執行中**才警示。關著的時候顯示「只剩 5 分鐘」沒有意義，
 *     他還沒開始用；而那個數字本來就一直在畫面上（m-remaining）。
 */
function dailyNote(d, running) {
    if (!running) return '';
    const lv = warnLevel(d.today_remaining_min);
    if (lv === 'none') return '';
    if (lv === 'over') return T('lab_daily_over', '今日可用時間已用完，實驗室即將自動關閉。');
    const tmpl = lv === 'notice'
        ? T('lab_daily_left', '今日可用時間還剩 {n} 分鐘。')
        : T('lab_daily_soon', '今日可用時間只剩 {n} 分鐘，請盡快存檔。');
    return tmpl.replace('{n}', d.today_remaining_min);
}


function render(d) {
    const running = d.status === 'running';
    // ZH: 🔴 這兩個元素的 HTML 上掛著 `data-i18n="loading"`（初始文案「讀取中…」）。
    //     那個屬性**留著的話，之後任何一次 Prefs.apply() 都會把這裡設的字蓋回「讀取中…」**
    //     —— 而 apply 會在偏好同步、切色系、切語言時各跑一次。
    //     症狀是「實驗室其實載好了，畫面卻一直寫讀取中」，而 console 乾淨。
    // ZH: 接手之後就把屬性拿掉：文案的主權從字典轉移到這裡了。
    //     ⚠ 不能改成「字典裡放正確的字」—— 這兩格的內容取決於狀態，不是固定文案。
    $('state').removeAttribute('data-i18n');
    $('go').removeAttribute('data-i18n');

    $('state').textContent = running ? T('lab_st_running', '執行中') : T('lab_st_stopped', '未啟動');
    setPrimary({ label: running ? T('lab_open', '開啟實驗室') : T('lab_start_open', '啟動並開啟實驗室'), enabled: true });
    $('stop').hidden = !running;

    // ZH: v3.9 GPU 勾選只在「還沒啟動」時出現 —— 已經在跑的容器改不了裝置，
    //     勾了也沒用，留著只會讓人以為勾一下就能加上去。
    //     要換成 GPU 版就得先關掉再開，那件事由「關閉實驗室」負責。
    if ($('gpu-wrap')) {
        $('gpu-wrap').hidden = running;
        $('gpu-hint').hidden = running;
    }

    // ZH: 已經在跑而且**這一份是 GPU 版**時，把它講出來 ——
    //     使用者要知道自己正佔著全校唯一那張卡。
    // ZH: ⚠ 這裡要**連「不是 GPU 版就清掉」一起做**。
    //     只設不清的話，從 GPU 版切到 CPU 版之後那句話還留在畫面上。
    // ZH: GPU 與每日額度可能同時要說話（例如借了卡又快到每日上限）。
    //     兩句都給 —— 少講一句就等於有一種被關掉的原因永遠沒有預告。
    note([
        running && d.gpu_index != null ? gpuNote(d) : '',
        dailyNote(d, running),
    ].filter(Boolean).join('　'));

    // ZH: 🔴 這一區原本整塊只在執行中顯示。但「今日剩餘時間」與「磁碟」
    //     停止時一樣有意義 —— 而且**想清空間的人正是在關著的狀態下看這一頁**，
    //     只在執行中才給的話，最需要那個數字的時候剛好看不到。
    //     只有「已執行」是跑起來才有意義的，單獨藏它。
    $('meta').hidden = false;
    $('m-elapsed-wrap').hidden = !running;

    $('m-remaining').textContent = d.today_remaining_min != null
        ? `${d.today_remaining_min}${T('unit_min', ' 分')}` : '—';
    // ZH: 把級別放到 data 屬性上，顏色交給 CSS。
    //     ⚠ 顏色是**次要**線索：上面那句話本身就寫著剩幾分鐘（WCAG 1.4.1）。
    $('m-remaining').dataset.warn = warnLevel(d.today_remaining_min);
    $('m-elapsed').textContent = mins(d.elapsed_seconds);

    // ZH: 顯示「用了多少 / 上限多少」。用量是後端**即時量**的（約 0.2 秒），
    //     不是每日 03:00 的快照 —— 顯示昨天的數字會讓「我明明刪了」變成客訴。
    // ZH: ⚠ used_gb 是 null 代表**量不到**（不是 0）。這時只顯示配額，
    //     不要把它寫成 0 —— 「量不到」看起來像「沒在用」是最會誤導人的。
    if (d.effective_quota_gb == null) {
        $('m-quota').textContent = '—';
    } else if (d.used_gb == null) {
        $('m-quota').textContent = `${d.effective_quota_gb} GB`;
    } else {
        $('m-quota').textContent = `${d.used_gb} / ${d.effective_quota_gb} GB`;
        // ZH: 超過了就講出來 —— 那時他開不了實驗室，要知道原因。
        if (d.used_gb > d.effective_quota_gb) {
            $('m-quota').textContent += ' ' + T('lab_disk_over', '（超出）');
        }
    }

    // ZH: 注入的密鑰是「你的程式跑起來時會拿到什麼」——屬於層級 3 的事實，
    //     但沒有它使用者會以為密鑰沒生效。只在有東西時出現。
    const sec = d.injected_secrets;
    const has = Array.isArray(sec) ? sec.length : (sec && Object.keys(sec).length);
    $('secrets').hidden = !has;
    if (has) {
        const names = Array.isArray(sec) ? sec : Object.keys(sec);
        $('secrets').textContent = T('lab_env', '啟動時會注入這些環境變數：{n}').replace('{n}', names.join('、'));
    }
}

async function load() {
    if (FORCED === 'loading') return;
    try {
        const d = FORCED ? mock(FORCED) : await api('/lab/status');
        // ZH: 🔴 這裡原本在 render 之後補一個 `note('')` 清訊息，
        //     於是 render 剛設好的「正在使用 GPU」提示**當場被清掉**——
        //     程式碼看起來完全正確，畫面上就是不出現。
        //     訊息由 render 自己負責（設或清），這裡不要再插手。
        render(d);
    } catch (e) {
        $('state').textContent = T('lab_st_unknown', '讀不到');
        setPrimary({ label: T('btn_retry', '重試'), enabled: true });
        note(T('lab_state_fail', '暫時取不到實驗室狀態') + `（${e.message || e}）。`);
    }
}

// ── 主要動作 ─────────────────────────────────────────────────────────
function openTab(url) {
    const w = window.open(url, '_blank');
    if (!w) {
        // ZH: 被瀏覽器擋下時**不可以毫無反應**（與首頁前往 MYAI 同一條規則）。
        $('note').innerHTML = T('popup_blocked', '瀏覽器擋下了新分頁。')
            + `<a href="${url}" target="_blank" rel="noopener">${T('lab_open_here', '點這裡開啟實驗室')}</a>`;
        $('note').hidden = false;
        return;
    }
    note(T('lab_opened', '已在新分頁開啟。若看到「未授權」，請回首頁重新登入一次（新分頁靠 cookie 認證，與這一頁不同）。'));
}

$('go').addEventListener('click', async () => {
    setPrimary({ label: T('lab_starting', '啟動中…'), enabled: false });
    note(T('lab_start_hint', '容器啟動大約需要 5–10 秒，好了會自動開新分頁。'));

    if (FORCED) {                       // 檢視模式：走完流程但不打後端
        setTimeout(() => { setPrimary({ label: T('lab_open', '開啟實驗室'), enabled: true });
                           note('（檢視模式：不會真的開容器）'); }, 600);
        return;
    }

    try {
        const started = await api('/lab/start', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            // ZH: v3.6 —— 要開哪一份存檔。沒選過就是 default（既有行為）。
            // ZH: v3.9 勾了才送 gpu:true。沒勾就完全不帶這個鍵 ——
            //     後端沒收到＝CPU 實驗室，行為與 v3.8 逐字相同。
            body: JSON.stringify(Object.assign(
                currentSession ? { session: currentSession } : {},
                ($('gpu-opt') && $('gpu-opt').checked) ? { gpu: true } : {})),
        });
        // ZH: 伺服器順手關掉了別份時會回報 —— **要說出來**，
        //     使用者按下「開啟 B」而 A 被靜靜關掉會以為 A 壞了。
        if (started.switched_from) {
            note(T('ws_switched', '已切換存檔（原本那一份已關閉，檔案都保留）'));
        }
        // ZH: /lab/start 回的 url 已經是 /code/<uid>/?folder=...，直接用。
        //     但**不要立刻開** —— 先輪詢到 running 再開，否則新分頁是空白。
        await waitReady(started.url);
    } catch (e) {
        setPrimary({ label: T('lab_start_open', '啟動並開啟實驗室'), enabled: true });
        // ZH: 429 是額度/頻率限制、409 是 GPU 被佔走 —— 兩種訊息都由後端給，
        //     **照實顯示不要改寫**：後端才知道是誰在用那張卡。
        // ZH: 409 不是故障，所以順手把勾選取消掉 ——
        //     使用者可以直接再按一次開 CPU 實驗室，不必自己想到要取消勾選。
        if (String(e.message || '').indexOf('GPU') >= 0 && $('gpu-opt')) {
            $('gpu-opt').checked = false;
        }
        note(T('lab_start_fail', '啟動失敗') + `：${e.message || e}`);
    }
});

async function waitReady(url) {
    let tries = 0;
    clearInterval(POLL);
    POLL = setInterval(async () => {
        tries++;
        try {
            const d = await api('/lab/status');
            if (d.status === 'running') {
                clearInterval(POLL);
                render(d);
                openTab(d.url || url);
                return;
            }
        } catch (e) { /* 輪詢期間的暫時失敗不打斷，由次數上限收尾 */ }
        if (tries >= 20) {                     // 20 × 1.5s = 30 秒
            clearInterval(POLL);
            setPrimary({ label: T('lab_start_open', '啟動並開啟實驗室'), enabled: true });
            note(T('lab_timeout', '等了 30 秒仍未就緒。可以再試一次，或回報問題。（容器可能仍在背景啟動，重新整理這一頁可以看到最新狀態。）'));
        }
    }, 1500);
}

// ── 層級 3：停止 ─────────────────────────────────────────────────────
$('stop').addEventListener('click', async (ev) => {
    ev.preventDefault();
    // ZH: 停止會關掉容器但**不會刪檔案**——講明才不會有人不敢按。
    if (!confirm(T('lab_stop_confirm', '要關閉實驗室嗎？容器會停止，但你的檔案都會保留。'))) return;
    try {
        if (!FORCED) await api('/lab/stop', { method: 'POST' });
        note(T('lab_stopped', '已關閉。檔案都還在，下次啟動會回到原樣。'));
        await load();
    } catch (e) {
        note(T('lab_stop_fail', '關閉失敗') + `：${e.message || e}`);
    }
});

// ── 假資料 ───────────────────────────────────────────────────────────
function mock(kind) {
    if (kind === 'error') throw new Error('強制錯誤狀態');
    // ZH: stopped 也要有磁碟數字 —— 那一格現在停止時照樣顯示。
    if (kind === 'stopped') return { status: 'stopped', today_remaining_min: 180,
                                     used_gb: 2.1, effective_quota_gb: 10 };
    // ZH: `?state=full` 看「超出配額」的樣子。
    if (kind === 'full') return { status: 'stopped', today_remaining_min: 180,
                                  used_gb: 12.4, effective_quota_gb: 10 };
    // ZH: v3.9 —— `?state=gpu` 看「正在佔著 GPU」的樣子。
    //     不加這個狀態的話，那條提示只有在真的借到卡時才看得到，
    //     光靠檢視模式驗不了版面。
    const base = {
        status: 'running', elapsed_seconds: 742, today_remaining_min: 168,
        effective_quota_gb: 20, used_gb: 3.7, url: '/code/demo/?folder=/home/coder/projects',
        injected_secrets: ['HF_TOKEN', 'OPENAI_API_KEY'],
    };
    if (kind === 'gpu') return Object.assign({}, base, { gpu_index: 0 });
    return base;
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


// ==========================================================================
// ZH: v3.6 多份存檔
// ==========================================================================
// ZH: 一次只開一份 —— 切換就是關掉舊的、開新的。**檔案全部保留**，
//     這件事一定要在畫面上講，不然使用者會以為舊的那份壞了。

let sessions = [];

async function loadSessions() {
    // ZH: 🔴 try 只包**拿資料**這一段，不包渲染。
    //     原本連 renderSessions 一起包住，結果渲染裡的 `TW is not defined`
    //     被吃掉、畫面顯示「暫時讀不到存檔清單」——而網路其實好好的、資料也拿到了。
    //     一個假的網路錯誤訊息會把人帶去查完全錯的方向；渲染的錯就該是紅色的例外。
    let body;
    try {
        const r = await fetch(`${API}/lab/sessions`, { headers: authHeaders() });
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        body = await r.json();
    } catch {
        // ZH: 讀不到就說讀不到 —— **不要顯示空清單**，那看起來像「你沒有存檔」。
        $('ws-list').innerHTML =
            `<p class="footnote">${esc(T('ws_load_fail', '暫時讀不到存檔清單（不影響上面的開啟）'))}</p>`;
        return;
    }
    sessions = body.sessions || [];
    renderSessions(body.max || 5);
}

function renderSessions(max) {
    $('ws-count').textContent =
        T('ws_count', '{n} / {m} 份').replace('{n}', sessions.length).replace('{m}', max);
    $('ws-new').disabled = sessions.length >= max;

    $('ws-list').innerHTML = sessions.map((s) => {
        const running = s.status === 'running' || s.status === 'starting';
        const isDefault = s.session_name === 'default';
        return `
        <div class="entry">
            <div class="entry__title">${esc(s.display_name)}
                ${running ? `<span class="footnote">　${esc(T('ws_running', '執行中'))}</span>` : ''}</div>
            <div class="entry__desc">${s.last_activity
                ? esc(T('ws_last', '最後使用：{w}').replace('{w}', TW.when(s.last_activity) || ''))
                : esc(T('ws_never', '還沒開過'))}</div>
            <div class="ds__actions">
                <button class="btn btn--minor" type="button" data-open="${esc(s.session_name)}">
                    ${esc(running ? T('ws_go', '前往') : T('ws_open', '開啟這一份'))}</button>
                ${isDefault ? '' : `<button class="btn btn--minor" type="button"
                    data-del="${esc(s.session_name)}" ${running ? 'disabled' : ''}>
                    ${esc(T('ws_delete', '刪除'))}</button>`}
            </div>
        </div>`;
    }).join('');

    $('ws-list').querySelectorAll('[data-open]').forEach((b) =>
        b.addEventListener('click', () => openSession(b.dataset.open)));
    $('ws-list').querySelectorAll('[data-del]').forEach((b) =>
        b.addEventListener('click', () => deleteSession(b.dataset.del, b)));
}

async function openSession(name) {
    // ZH: 切換前先講清楚 —— 使用者按下「開啟 B」時，A 會被關掉。
    //     不問就關掉的話，他回頭找 A 會以為壞了。
    const running = sessions.find((s) => (s.status === 'running' || s.status === 'starting')
                                         && s.session_name !== name);
    if (running && !confirm(T('ws_switch_confirm',
            '要切換到這一份嗎？「{n}」會關閉，但它的檔案都會保留。')
            .replace('{n}', running.display_name))) return;

    // ZH: 交給既有的啟動流程（它會輪詢到就緒才開新分頁）。
    // ZH: 交給既有的啟動流程（`#go` 的 handler 會輪詢到就緒才開新分頁）。
    //     ⚠ 不要自己再寫一份啟動邏輯 —— 那條路已經處理了「容器要 5–10 秒」
    //       與「不要開出空白分頁」，重寫一定會漏掉其中一件。
    currentSession = name;
    $('go').click();
}

async function deleteSession(name, btn) {
    const s = sessions.find((x) => x.session_name === name);
    if (!confirm(T('ws_delete_confirm', '要刪掉「{n}」嗎？裡面的檔案會一起消失，沒辦法復原。')
        .replace('{n}', s ? s.display_name : ''))) return;
    btn.disabled = true;
    try {
        const r = await fetch(`${API}/lab/sessions/${encodeURIComponent(name)}`,
                              { method: 'DELETE', headers: authHeaders() });
        if (!r.ok) {
            const body = await r.json().catch(() => ({}));
            throw new Error(String(body.detail || `HTTP ${r.status}`));
        }
        await loadSessions();
    } catch (e) {
        btn.disabled = false;
        alert(String(e.message).replace(/^ZH:\s*/, '').split(' | ')[0]);
    }
}

$('ws-new').addEventListener('click', async () => {
    const name = prompt(T('ws_new_prompt', '這一份要叫什麼名字？'));
    if (!name || !name.trim()) return;
    try {
        const r = await fetch(`${API}/lab/sessions`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', ...authHeaders() },
            body: JSON.stringify({ display_name: name.trim() }),
        });
        if (!r.ok) {
            const body = await r.json().catch(() => ({}));
            throw new Error(String(body.detail || `HTTP ${r.status}`));
        }
        await loadSessions();
    } catch (e) {
        alert(String(e.message).replace(/^ZH:\s*/, '').split(' | ')[0]);
    }
});

loadSessions();
document.addEventListener('prefs:langchanged', () => loadSessions());


/* ── 營運設定的補充說明（v3.8）──────────────────────────────────────
 * ZH: 這個數字是**管理者可以在營運設定裡改的**，所以不能寫死在 HTML ——
 *     寫死的話管理者調過之後，畫面上就是一個錯的數字，而且不會有人回報。
 *     值一律現取（Chrome.publicSettings 會在同一頁內快取）。
 *
 * ZH: 讀不到就**維持隱藏**，不要顯示「—」或 0。
 *     這是一句補充說明，缺了不影響這一頁本來要做的事；
 *     顯示一個假的 0 反而會被當成真的。
 * ------------------------------------------------------------------ */
function renderArchiveNote(s) {
    const el = $('archive-note');
    if (!el) return;
    const v = s && s['lab_archive_days'];
    if (v == null) { el.hidden = true; return; }
    el.textContent = T('lab_archive_note', '如果帳號被刪除，這些存檔會先封存保留 {d} 天，逾期才真的銷毀。').replace('{d}', v);
    el.hidden = false;
}

let PUB_SETTINGS = null;
Chrome.publicSettings().then((s) => { PUB_SETTINGS = s; renderArchiveNote(s); });
// ZH: 文案是 JS 組出來的，沒有 data-i18n，字典掃描換不掉它 —— 語言改變時要自己重畫。
document.addEventListener('prefs:langchanged', () => renderArchiveNote(PUB_SETTINGS));
