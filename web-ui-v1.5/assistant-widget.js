/*
==============================================================================
ZH: 客服／程式家教 浮動助手 widget（v2.6 → v2.7）| Floating support/code-tutor widget
==============================================================================
ZH: 自包含 IIFE：右下角浮動泡泡 + 對話面板，呼叫 /api/v1/assistant/ask。
    兩種模式：
      - guide（客服）：公開、不需登入、不扣 Token（登入頁也能用）。
      - code（程式家教）：需登入；可「📎 附加 Lab 檔案」帶入使用者自己的程式碼。
    對外暴露 window.AibotWidget = { open(), openCodeMode() } 供 Notebook 頁呼叫。
EN: Self-contained IIFE. Two modes: public "guide" and login-gated "code" tutor
    (can attach the user's own Lab file). Exposes window.AibotWidget.

ZH: SSE 格式與 chat.py 一致：data: {choices:[{delta:{content}}]} / data:[DONE]
==============================================================================
*/
(function () {
    'use strict';

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
    const _sig = () => (localStorage.getItem('ai_hud_token') || 'anon');
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

    const MODES = {
        guide: {
            name: '客服小基', status: '平台操作小幫手',
            placeholder: '輸入問題，例如：怎麼登入？',
            greet: '你好，我是平台客服小基 🙂\n我可以幫你解答平台操作問題，例如「怎麼登入」「怎麼提交運算任務」「Lab 怎麼用」。',
        },
        code: {
            name: '程式家教小基', status: 'Notebook 程式輔導',
            placeholder: '描述你的程式問題，或先附上 Lab 檔…',
            greet: '嗨，我是程式家教小基 👨‍🏫\n你可以貼上程式碼，或用上方「📎 附加 Lab 檔案」帶入你 Lab 裡的檔，我陪你一起看。',
        },
    };

    const getToken = () => localStorage.getItem('ai_hud_token');

    // ---- ZH: 建立 DOM | EN: Build DOM ----
    const root = document.createElement('div');
    root.id = 'aibot-root';
    root.innerHTML = `
        <button id="aibot-fab" aria-label="開啟小基助手" title="小基助手">
            <span class="aibot-fab-icon">💬</span>
        </button>
        <section id="aibot-panel" class="aibot-hidden" role="dialog" aria-label="小基助手">
            <header class="aibot-header">
                <div class="aibot-title">
                    <span class="aibot-avatar">🤖</span>
                    <div>
                        <strong id="aibot-name">客服小基</strong>
                        <small id="aibot-status">平台操作小幫手</small>
                    </div>
                </div>
                <button id="aibot-close" aria-label="關閉">✕</button>
            </header>
            <div class="aibot-modes" role="tablist">
                <button type="button" class="aibot-mode-btn aibot-mode-active" data-mode="guide">客服</button>
                <button type="button" class="aibot-mode-btn" data-mode="code">程式家教</button>
            </div>
            <div id="aibot-attach" class="aibot-attach aibot-hidden">
                <button type="button" id="aibot-attach-btn">📎 附加 Lab 檔案</button>
                <span id="aibot-file-chip" class="aibot-file-chip aibot-hidden">
                    <span id="aibot-file-name"></span>
                    <button type="button" id="aibot-file-clear" aria-label="移除附檔">✕</button>
                </span>
                <div id="aibot-file-list" class="aibot-file-list aibot-hidden"></div>
            </div>
            <div id="aibot-log" class="aibot-log"></div>
            <form id="aibot-form" class="aibot-form">
                <textarea id="aibot-input" rows="1" placeholder="輸入問題，例如：怎麼登入？" autocomplete="off"></textarea>
                <button type="submit" id="aibot-send" aria-label="送出">➤</button>
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
        div.textContent = '參考：' + sources.join('、');
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
        if (!tok) { showListNotice('請先登入才能讀取你的 Lab 檔案。'); return; }
        showListNotice('讀取中…');
        try {
            const r = await fetch(`${ASSIST_BASE}/lab-files`, { headers: { 'Authorization': 'Bearer ' + tok } });
            if (!r.ok) throw new Error('HTTP ' + r.status);
            const data = await r.json();
            if (!data.running) {
                showListNotice(data.reason === 'lab_not_running'
                    ? '你的 Lab 沒在執行，請先到 Notebook 啟動。'
                    : '你的 Lab 尚未啟動，請先到 Notebook 開啟 Lab。');
                return;
            }
            if (!data.files || !data.files.length) { showListNotice('Lab 裡找不到可附加的程式檔。'); return; }
            renderFileList(data.files);
        } catch (e) {
            showListNotice('讀取檔案清單失敗，請稍後再試。');
        }
    });

    // ---- ZH: 開關面板 | EN: open/close ----
    function openPanel() {
        panel.classList.remove('aibot-hidden');
        fab.classList.add('aibot-open');
        if (logEl.children.length === 0) _renderLog();
        setTimeout(() => input.focus(), 50);
    }
    function closePanel() {
        panel.classList.add('aibot-hidden');
        fab.classList.remove('aibot-open');
    }
    fab.addEventListener('click', () => panel.classList.contains('aibot-hidden') ? openPanel() : closePanel());
    closeBtn.addEventListener('click', closePanel);

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
            b.textContent = '程式家教需要先登入才能使用喔，請先登入後再試。';
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
            aiBubble.textContent = '連線失敗，請稍後再試。(' + err.message + ')';
        } finally {
            if (full) messages.push({ role: 'assistant', content: full });
            _saveHistories();   // ZH: 寫入短暫記憶（單次登入）| persist room (per login)
            busy = false;
            sendBtn.disabled = false;
            input.focus();
        }
    });

    // ZH: 啟動時還原本次登入的聊天室記憶 | restore this-login rooms on start
    _loadHistories();

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
