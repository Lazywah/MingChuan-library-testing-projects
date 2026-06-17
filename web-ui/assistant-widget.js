/*
==============================================================================
ZH: 客服／導覽浮動助手 widget（v2.6）| EN: Floating support/guide assistant (v2.6)
==============================================================================
ZH: 自包含 IIFE：自行建立右下角浮動泡泡 + 對話面板，呼叫 /api/v1/assistant/ask。
    刻意「公開、不需登入、不扣 Token」，故登入頁也能用；對話僅存在記憶體。
EN: Self-contained IIFE: builds a bottom-right bubble + chat panel, calls
    /api/v1/assistant/ask. Public (no login, no token charge) so it works on the
    login page too; conversation lives in memory only.

ZH: SSE 格式與後端 chat.py 一致：data: {choices:[{delta:{content}}]} / data:[DONE]
EN: SSE format matches chat.py: data: {choices:[{delta:{content}}]} / data:[DONE]
==============================================================================
*/
(function () {
    'use strict';

    const ASSIST_BASE = '/api/v1/assistant';
    // ZH: 本次對話的 session id（僅前端記憶）| EN: per-session id (front-end only)
    const SESSION_ID = (window.crypto && crypto.randomUUID) ? crypto.randomUUID() : 'aibot-' + Date.now();
    // ZH: 對話歷史（送後端帶上下文）| EN: conversation history (sent for context)
    const messages = [];
    let busy = false;

    // ---- ZH: 建立 DOM | EN: Build DOM ----
    const root = document.createElement('div');
    root.id = 'aibot-root';
    root.innerHTML = `
        <button id="aibot-fab" aria-label="開啟客服助手" title="平台客服小基">
            <span class="aibot-fab-icon">💬</span>
        </button>
        <section id="aibot-panel" class="aibot-hidden" role="dialog" aria-label="客服助手">
            <header class="aibot-header">
                <div class="aibot-title">
                    <span class="aibot-avatar">🤖</span>
                    <div>
                        <strong>客服小基</strong>
                        <small id="aibot-status">平台操作小幫手</small>
                    </div>
                </div>
                <button id="aibot-close" aria-label="關閉">✕</button>
            </header>
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

    let greeted = false;

    function openPanel() {
        panel.classList.remove('aibot-hidden');
        fab.classList.add('aibot-open');
        if (!greeted) {
            greeted = true;
            addBubble('assistant',
                '你好，我是平台客服小基 🙂\n我可以幫你解答平台操作問題，例如「怎麼登入」「怎麼提交運算任務」「Lab 怎麼用」。');
        }
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
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            form.requestSubmit();
        }
    });

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

    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        const text = input.value.trim();
        if (!text || busy) return;

        input.value = '';
        input.style.height = 'auto';
        addBubble('user', text);
        messages.push({ role: 'user', content: text });

        busy = true;
        sendBtn.disabled = true;
        const aiBubble = addBubble('assistant', '');
        aiBubble.classList.add('aibot-typing');
        aiBubble.textContent = '…';

        let full = '';
        try {
            const resp = await fetch(`${ASSIST_BASE}/ask`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ messages, session_id: SESSION_ID })
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
                buffer = lines.pop();  // ZH: 留最後不完整行 | EN: keep last partial line

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
                    } catch (_) { /* ZH: 忽略解析不完整片段 | EN: ignore partial */ }
                }
            }
        } catch (err) {
            aiBubble.classList.remove('aibot-typing');
            aiBubble.classList.add('aibot-error');
            aiBubble.textContent = '連線失敗，請稍後再試。(' + err.message + ')';
        } finally {
            if (full) messages.push({ role: 'assistant', content: full });
            busy = false;
            sendBtn.disabled = false;
            input.focus();
        }
    });
})();
