/*
==============================================================================
ZH: 客服／程式家教 浮動助手 widget（小基）| Floating support/code-tutor widget
==============================================================================
ZH: 自包含 IIFE：右下角浮動泡泡 + 對話面板，呼叫 /api/v1/assistant/ask。
    兩種模式：
      - guide（客服）：公開、不需登入、不扣 Token（登入頁也能用）。
      - code（程式家教）：需登入；可「📎 附加 Lab 檔案」帶入使用者自己的程式碼。
    對外暴露 window.AibotWidget = { open(), openCodeMode() }。
EN: Self-contained IIFE. Two modes: public "guide" and login-gated "code" tutor.

ZH: SSE 格式與 chat.py 一致：data: {choices:[{delta:{content}}]} / data:[DONE]

ZH: ── 2026-08-28 從 V0.5 移植到 V1，改了四件事 ──────────────────────
    1. **全部字串走 i18n**。V0.5 那份 22 個中文字串全部寫死，
       而 V1 有雙語規則與 `check_untranslated_html` 守門。
    2. **術語跟上 V1**：原文寫「Notebook」，V1 早在 `6e502de` 改名成
       「程式實驗室 / Code Lab」。照抄會把舊名帶回使用者眼前。
    3. **token 取法對齊 V1**：`sessionStorage` 優先再退 `localStorage`
       （V0.5 只讀 localStorage）。不一致的話換分頁登入會拿到舊身分。
    4. **CSS 放 `web.css`**（使用者端專屬）而不是 `styles.css` ——
       後者是與管理端逐位元組相同的共用檔，塞 45 條管理端用不到的規則
       會讓下一個人困惑。

ZH: ⚠ 已知限制（擁有者 2026-08-28 裁定接受）：V1 的 Lab 走**新分頁**
    （設計文件 Decision Log #26），所以使用者**在 IDE 裡的時候小基不在那個分頁上**。
    程式家教模式仍可用：切回平台分頁 → 附加 Lab 檔案 → 提問。
    當初 v1.5 把 Lab 改成 iframe 內嵌就是為了讓泡泡浮在上面，
    V1 選擇讓 IDE 保有完整視窗高度。
==============================================================================
*/
(function () {
    'use strict';

    // ZH: 取文案。字典裡沒有就用 fallback（＝原本的中文），**不清空** —— 與 chrome.js 同一套。
    function T(key, fallback) {
        return (window.Prefs && window.Prefs.t(key, fallback)) || fallback;
    }

    const ASSIST_BASE = '/api/v1/assistant';
    const SESSION_ID = (window.crypto && crypto.randomUUID) ? crypto.randomUUID() : 'aibot-' + Date.now();
    // ZH: v2.7 每個模式各自一間「聊天室」，切換模式 = 切換聊天室（不清空）
    // EN: v2.7 one chat room per mode; switching mode swaps rooms (no wipe)
    const histories = { guide: [], code: [] };
    let mode = 'guide';
    let messages = histories[mode];   // ZH: 指向目前模式的對話 | points at current room
    let busy = false;
    let attachedFile = null;   // ZH: 目前附加的 Lab 檔（相對路徑）| attached lab file (rel path)

    // ZH: 短暫記憶（單次登入）— 存 sessionStorage，並以 token 簽章；換登入/換人即失效
    // EN: short-term memory (per login) — sessionStorage, signed by token; new login invalidates
    const STORE_KEY = 'aibot_histories';
    // ZH: sessionStorage 優先 —— 與 chrome.js 一致。只讀 localStorage 的話，
    //     在另一個分頁登入之後這裡會拿到舊身分（V0.5 就是只讀 localStorage）。
    const _tok = () => sessionStorage.getItem('ai_hud_token') || localStorage.getItem('ai_hud_token');
    const _sig = () => (_tok() || 'anon');
    function _saveHistories() {
        try { sessionStorage.setItem(STORE_KEY, JSON.stringify({ sig: _sig(), histories })); } catch (_) {}
    }
    function _loadHistories() {
        try {
            const raw = sessionStorage.getItem(STORE_KEY);
            if (!raw) return;
            const obj = JSON.parse(raw);
            if (obj && obj.sig === _sig() && obj.histories) {
                histories.guide = Array.isArray(obj.histories.guide) ? obj.histories.guide : [];
                histories.code  = Array.isArray(obj.histories.code)  ? obj.histories.code  : [];
                messages = histories[mode];
            }
        } catch (_) {}
    }

    // ZH: 問候語有換行，拉出來當常數比塞在 T() 的參數裡好讀。
    //     這兩句同時是「字典裡沒有這個 key 時的 fallback」。
    const GREET_GUIDE = '你好，我是平台客服小基 🙂\n我可以幫你解答平台操作問題，例如「怎麼登入」「怎麼提交訓練」「程式實驗室怎麼用」。';
    const GREET_CODE = '嗨，我是程式家教小基 👨‍🏫\n你可以貼上程式碼，或用上方「📎 附加檔案」帶入你程式實驗室裡的檔，我陪你一起看。';

    // ZH: 用**函式**而不是常數物件 —— 使用者可以在頁面上切換語言（頂部列的 中/EN），
    //     寫成常數的話文案會停在載入當下那個語言。
    // ZH: ⚠ `status` 原文是「Notebook 程式輔導」。V1 早在 `6e502de` 把 Notebook
    //     改名成「程式實驗室 / Code Lab」，照抄會把舊名帶回使用者眼前。
    function modeText(m) {
        if (m === 'code') {
            return {
                name: T('bot_code_name', '程式家教小基'),
                status: T('bot_code_status', '程式實驗室輔導'),
                placeholder: T('bot_code_ph', '描述你的程式問題，或先附上實驗室的檔案…'),
                greet: T('bot_code_greet', GREET_CODE),
            };
        }
        return {
            name: T('bot_guide_name', '客服小基'),
            status: T('bot_guide_status', '平台操作小幫手'),
            placeholder: T('bot_guide_ph', '輸入問題，例如：怎麼登入？'),
            greet: T('bot_guide_greet', GREET_GUIDE),
        };
    }
    const MODES = { get guide() { return modeText('guide'); },
                    get code() { return modeText('code'); } };

    const getToken = () => _tok();

    // ---- ZH: 建立 DOM | EN: Build DOM ----
    const root = document.createElement('div');
    root.id = 'aibot-root';
    root.innerHTML = `
        <button id="aibot-fab" aria-label="${T('bot_open', '開啟小基助手')}" title="${T('bot_title', '小基助手')}">
<!-- ZH: 圖示用單色線條 SVG 不用 emoji（擁有者裁定 2026-09-01：要低調、顏色少）。
     線條吃 currentColor —— 黃底時是白線，面板開著（.aibot-open 灰底）時自動變深色。 -->
            <span class="aibot-fab-icon" aria-hidden="true"><svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="5" y="8" width="14" height="10" rx="3"/><line x1="12" y1="8" x2="12" y2="5.5"/><circle cx="12" cy="4.2" r="1.1" fill="currentColor" stroke="none"/><circle cx="9.5" cy="13" r="1.15" fill="currentColor" stroke="none"/><circle cx="14.5" cy="13" r="1.15" fill="currentColor" stroke="none"/></svg></span>
        </button>
        <section id="aibot-panel" class="aibot-hidden" role="dialog" aria-label="${T('bot_title', '小基助手')}">
            <header class="aibot-header">
                <div class="aibot-title">
                    <span class="aibot-avatar">🤖</span>
                    <div>
                        <strong id="aibot-name">${T('bot_guide_name', '客服小基')}</strong>
                        <small id="aibot-status">${T('bot_guide_status', '平台操作小幫手')}</small>
                    </div>
                </div>
                <button id="aibot-close" aria-label="${T('bot_close', '關閉')}">✕</button>
            </header>
            <div class="aibot-modes" role="tablist">
                <button type="button" class="aibot-mode-btn aibot-mode-active" data-mode="guide">客服</button>
                <button type="button" class="aibot-mode-btn" data-mode="code">程式家教</button>
            </div>
            <div id="aibot-attach" class="aibot-attach aibot-hidden">
                <button type="button" id="aibot-attach-btn">📎 附加 Lab 檔案</button>
                <span id="aibot-file-chip" class="aibot-file-chip aibot-hidden">
                    <span id="aibot-file-name"></span>
                    <button type="button" id="aibot-file-clear" aria-label="${T('bot_file_clear', '移除附檔')}">✕</button>
                </span>
                <div id="aibot-file-list" class="aibot-file-list aibot-hidden"></div>
            </div>
            <div id="aibot-log" class="aibot-log"></div>
            <form id="aibot-form" class="aibot-form">
                <textarea id="aibot-input" rows="1" placeholder="${T('bot_guide_ph', '輸入問題，例如：怎麼登入？')}" autocomplete="off"></textarea>
                <button type="submit" id="aibot-send" aria-label="${T('bot_send', '送出')}">➤</button>
            </form>
        </section>
    `;
    document.body.appendChild(root);

    const fab = root.querySelector('#aibot-fab');
    const panel = root.querySelector('#aibot-panel');
    const closeBtn = root.querySelector('#aibot-close');
    const logEl = root.querySelector('#aibot-log');
    const form = root.querySelector('#aibot-form');
    const input = root.querySelector('#aibot-input');
    const sendBtn = root.querySelector('#aibot-send');
    const nameEl = root.querySelector('#aibot-name');
    const statusEl = root.querySelector('#aibot-status');
    const attachBar = root.querySelector('#aibot-attach');
    const attachBtn = root.querySelector('#aibot-attach-btn');
    const fileChip = root.querySelector('#aibot-file-chip');
    const fileNameEl = root.querySelector('#aibot-file-name');
    const fileClearBtn = root.querySelector('#aibot-file-clear');
    const fileListEl = root.querySelector('#aibot-file-list');
    const modeBtns = root.querySelectorAll('.aibot-mode-btn');

    // ---- ZH: 訊息泡泡 | EN: bubbles ----
    function addBubble(role, text) {
        const div = document.createElement('div');
        div.className = 'aibot-bubble aibot-' + role;
        div.textContent = text;
        logEl.appendChild(div);
        logEl.scrollTop = logEl.scrollHeight;
        return div;
    }
    function addSources(sources) {
        if (!sources || !sources.length) return;
        const div = document.createElement('div');
        div.className = 'aibot-sources';
        div.textContent = T('bot_sources', '參考：') + sources.join('、');
        logEl.appendChild(div);
        logEl.scrollTop = logEl.scrollHeight;
    }
    function showGreeting() {
        addBubble('assistant', MODES[mode].greet);
    }

    // ZH: 依目前聊天室重畫對話（空房顯示問候語）| re-render the current room
    function _renderLog() {
        logEl.innerHTML = '';
        if (!messages.length) { showGreeting(); return; }
        messages.forEach(m => addBubble(m.role === 'user' ? 'user' : 'assistant', m.content));
        logEl.scrollTop = logEl.scrollHeight;
    }

    // ---- ZH: 模式切換 = 切換聊天室（保留各自對話）| switch chat room ----
    function setMode(m) {
        if (!MODES[m] || m === mode) return;   // ZH: 同模式不動作，避免清空 | no-op on same mode
        mode = m;
        messages = histories[m];               // ZH: 指向該聊天室 | point at that room
        const cfg = MODES[m];
        nameEl.textContent = cfg.name;
        statusEl.textContent = cfg.status;
        input.placeholder = cfg.placeholder;
        modeBtns.forEach(b => b.classList.toggle('aibot-mode-active', b.dataset.mode === m));
        attachBar.classList.toggle('aibot-hidden', m !== 'code');
        clearFile();
        fileListEl.classList.add('aibot-hidden');
        _renderLog();                          // ZH: 切到該聊天室並重畫 | swap & re-render
    }
    modeBtns.forEach(b => b.addEventListener('click', () => setMode(b.dataset.mode)));

    // ---- ZH: 附檔挑選器 | EN: file picker ----
    function showListNotice(text) {
        fileListEl.innerHTML = '';
        const d = document.createElement('div');
        d.className = 'aibot-file-notice';
        d.textContent = text;
        fileListEl.appendChild(d);
        fileListEl.classList.remove('aibot-hidden');
    }
    function renderFileList(files) {
        fileListEl.innerHTML = '';
        files.forEach(p => {
            const item = document.createElement('button');
            item.type = 'button';
            item.className = 'aibot-file-item';
            item.textContent = p;
            item.addEventListener('click', () => pickFile(p));
            fileListEl.appendChild(item);
        });
        fileListEl.classList.remove('aibot-hidden');
    }
    function pickFile(p) {
        attachedFile = p;
        fileNameEl.textContent = p.split('/').pop();
        fileChip.classList.remove('aibot-hidden');
        fileListEl.classList.add('aibot-hidden');
    }
    function clearFile() {
        attachedFile = null;
        fileNameEl.textContent = '';
        fileChip.classList.add('aibot-hidden');
    }
    fileClearBtn.addEventListener('click', clearFile);
    attachBtn.addEventListener('click', async () => {
        // ZH: 已開著清單就收起 | toggle
        if (!fileListEl.classList.contains('aibot-hidden')) {
            fileListEl.classList.add('aibot-hidden');
            return;
        }
        const tok = getToken();
        if (!tok) { showListNotice(T('bot_need_login_files', '請先登入才能讀取你的實驗室檔案。')); return; }
        showListNotice(T('bot_loading', '讀取中…'));
        try {
            const r = await fetch(`${ASSIST_BASE}/lab-files`, { headers: { 'Authorization': 'Bearer ' + tok } });
            if (!r.ok) throw new Error('HTTP ' + r.status);
            const data = await r.json();
            if (!data.running) {
                showListNotice(data.reason === 'lab_not_running'
                    ? T('bot_lab_stopped', '你的程式實驗室沒在執行，請先到「程式實驗室」啟動。')
                    : T('bot_lab_not_started', '你的程式實驗室尚未啟動，請先去開啟它。'));
                return;
            }
            if (!data.files || !data.files.length) { showListNotice(T('bot_no_files', '程式實驗室裡找不到可附加的程式檔。')); return; }
            renderFileList(data.files);
        } catch (e) {
            showListNotice(T('bot_files_fail', '讀取檔案清單失敗，請稍後再試。'));
        }
    });

    // ---- ZH: 開關面板 | EN: open/close ----
    // ==========================================================================
    // ZH: 側欄模式（v3.8）—— 擁有者 2026-08-28 裁定：不要小浮窗，要占版面 25~30% 的聊天室。
    //
    // ZH: 為什麼可以這樣做而不擠壓內容：`main` 是 `max-width: 720px` 置中，
    //     實測在 2134px 的視窗下**左右各空 707px**。側欄開在右邊等於用掉
    //     本來就空著的地方。開著時給 <body> 加 padding-right，
    //     頂部列與主內容（都是 static 流）會自己往左讓，不需要改任何頁面的版面。
    //
    // ZH: ⚠ 視窗窄的時候不能這樣做：1280px 時兩側各只剩 280px，
    //     側欄會壓到內容。所以 CSS 在 < 1100px 時退回浮動面板（不 dock）。
    //     手機目前不開放連線，但視窗拉窄是隨時會發生的事。
    //
    // ZH: 開關狀態記在 localStorage —— 這是 12 頁的多頁式網站，
    //     不記的話每換一頁側欄就自己彈回來，會很煩。
    // ==========================================================================
    const DOCK_KEY = 'ai_hud_bot_open';
    // ZH: 預設**關著**，只留右下角的泡泡按鈕（擁有者裁定 2026-08-31，
    //     推翻先前「版面太空所以預設開」的出發點）。
    //     使用者自己打開過（'1'）就記住；沒動過或關過都維持收合。
    //     ⚠ 改這裡要**連 12 個 html 的 head inline script 一起改**（判斷式相同），
    //     那段是為了首次繪製前就套 padding、避免換頁閃動 —— 兩邊不一致的話，
    //     頁面會先讓位再收回，每換一頁閃一次。
    function _wantOpen() {
        try { return localStorage.getItem(DOCK_KEY) === '1'; } catch (_) { return false; }
    }
    function _remember(open) {
        try { localStorage.setItem(DOCK_KEY, open ? '1' : '0'); } catch (_) {}
    }

    function openPanel(remember) {
        panel.classList.remove('aibot-hidden');
        fab.classList.add('aibot-open');
        document.documentElement.classList.add('aibot-docked');
        if (logEl.children.length === 0) _renderLog();
        if (remember !== false) _remember(true);
        // ZH: 首次開啟才把焦點搶過來。頁面載入就自動開的時候**不搶焦點** ——
        //     使用者可能正要用 Tab 逛頁面，游標突然跳進聊天框是很惱人的事。
        if (remember !== false) setTimeout(() => input.focus(), 50);
    }
    function closePanel() {
        panel.classList.add('aibot-hidden');
        fab.classList.remove('aibot-open');
        document.documentElement.classList.remove('aibot-docked');
        _remember(false);
    }
    fab.addEventListener('click', () => panel.classList.contains('aibot-hidden') ? openPanel() : closePanel());
    closeBtn.addEventListener('click', closePanel);

    // ZH: 依上次的選擇決定要不要一開始就展開。傳 false = 不搶焦點（見 openPanel）。
    // ZH: ⚠ `<html>` 的 `aibot-docked` **已經由 head 裡的 inline script 套好了**
    //     （避免每換一頁都看到內容滑動讓位）。這裡是把面板本身打開，
    //     class 再加一次是無害的 no-op。
    // ZH: 🔴 還原記憶必須在**第一次 _renderLog 之前**（2026-09-01 修）。
    //     原本這行在檔案更下面（對外 API 前面）——比自動開面板晚：
    //     換頁後面板先畫了「空的」紀錄（只有問候語），紀錄才載入、
    //     而載入不重畫 → 使用者要切一下模式（setMode 無條件重畫）才看得到。
    //     症狀的狡猾處：手動開合不會修（openPanel 只在 logEl 為空時才畫，
    //     問候語已佔位），只有切模式會好，看起來像「隨機需要撥一下」。
    _loadHistories();

    if (_wantOpen()) openPanel(false);

    // ZH: textarea 自動長高 + Enter 送出（Shift+Enter 換行）
    input.addEventListener('input', () => {
        input.style.height = 'auto';
        input.style.height = Math.min(input.scrollHeight, 120) + 'px';
    });
    input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); form.requestSubmit(); }
    });

    // ---- ZH: 送出 | EN: submit ----
    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        const text = input.value.trim();
        if (!text || busy) return;

        // ZH: 程式家教需登入 | code-tutor requires login
        if (mode === 'code' && !getToken()) {
            addBubble('user', text);
            const b = addBubble('assistant', '');
            b.classList.add('aibot-error');
            b.textContent = T('bot_need_login', '程式家教需要先登入才能使用，請登入後再試。');
            input.value = ''; input.style.height = 'auto';
            return;
        }

        input.value = '';
        input.style.height = 'auto';
        addBubble('user', text);
        messages.push({ role: 'user', content: text });

        busy = true;
        sendBtn.disabled = true;
        const aiBubble = addBubble('assistant', '');
        aiBubble.classList.add('aibot-typing');
        aiBubble.textContent = '…';

        const headers = { 'Content-Type': 'application/json' };
        const payload = { messages, session_id: SESSION_ID, mode };
        if (mode === 'code') {
            headers['Authorization'] = 'Bearer ' + getToken();
            if (attachedFile) payload.file_path = attachedFile;
        }

        let full = '';
        try {
            const resp = await fetch(`${ASSIST_BASE}/ask`, {
                method: 'POST', headers, body: JSON.stringify(payload)
            });
            if (!resp.ok || !resp.body) throw new Error('HTTP ' + resp.status);

            const reader = resp.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';
            while (true) {
                const { value, done } = await reader.read();
                if (done) break;
                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n');
                buffer = lines.pop();
                for (const line of lines) {
                    if (!line.startsWith('data: ')) continue;
                    const dataStr = line.slice(6).trim();
                    if (dataStr === '[DONE]') continue;
                    try {
                        const json = JSON.parse(dataStr);
                        if (json.error) {
                            aiBubble.classList.remove('aibot-typing');
                            aiBubble.classList.add('aibot-error');
                            aiBubble.textContent = json.error;
                            full = '';
                            break;
                        }
                        if (json.sources) { addSources(json.sources); continue; }
                        const delta = (json.choices && json.choices[0] && json.choices[0].delta.content) || '';
                        if (delta) {
                            if (aiBubble.classList.contains('aibot-typing')) {
                                aiBubble.classList.remove('aibot-typing');
                                aiBubble.textContent = '';
                            }
                            full += delta;
                            aiBubble.textContent = full;
                            logEl.scrollTop = logEl.scrollHeight;
                        }
                    } catch (_) { /* ignore partial */ }
                }
            }
        } catch (err) {
            aiBubble.classList.remove('aibot-typing');
            aiBubble.classList.add('aibot-error');
            aiBubble.textContent = T('bot_net_fail', '連線失敗，請稍後再試。') + '（' + err.message + '）';
        } finally {
            if (full) messages.push({ role: 'assistant', content: full });
            _saveHistories();   // ZH: 寫入短暫記憶（單次登入）| persist room (per login)
            busy = false;
            sendBtn.disabled = false;
            input.focus();
        }
    });

    // ---- ZH: 對外 API（Notebook 頁「問程式家教」呼叫）| EN: public API ----
    window.AibotWidget = {
        open() { openPanel(); },
        openCodeMode() { setMode('code'); openPanel(); },
        // ZH: 登出時清空（app.js 登出處呼叫）| clear on logout
        reset() {
            histories.guide.length = 0;
            histories.code.length = 0;
            try { sessionStorage.removeItem(STORE_KEY); } catch (_) {}
            logEl.innerHTML = '';
            showGreeting();
        },
    };
})();
