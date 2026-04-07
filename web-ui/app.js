// =========================
// ZH: 系統狀態與設定 | EN: State & Configuration
// =========================
const API_BASE = '/api/v1';
let authToken = localStorage.getItem('ai_hud_token') || null;
let pollInterval = null;

// ZH: 多對話管理狀態 | EN: Multi-session State Management
let sessions = JSON.parse(localStorage.getItem('ai_hud_sessions')) || [
    { id: 'default', name: 'New Chat', messages: [] }
];
let activeSessionId = localStorage.getItem('ai_hud_active_session') || 'default';

// ZH: i18n 翻譯字典 | EN: i18n Translation Dictionary
const TRANSLATIONS = {
    zh: {
        login_title: "系統登入",
        label_username: "使用者名稱",
        label_password: "密碼",
        btn_login: "傳送授權",
        // 導覽
        nav_dashboard: "儀表板",
        nav_assistant: "AI 助手",
        nav_settings: "系統設定",
        // 儀表板
        token_overview: "代幣資源概況",
        token_used: "已使用",
        token_limit: "總配額",
        token_reset: "重置日期",
        job_compose: "建立新任務",
        label_job_name: "任務名稱",
        label_model_name: "模型辨識碼",
        label_priority: "佇列優先級",
        priority_0: "0 - 批次處理",
        priority_1: "1 - 正常佇列",
        priority_2: "2 - 急件優先",
        label_epochs: "訓練迴圈數",
        label_batch: "批次大小",
        btn_dispatch: "派發任務",
        pipeline_active: "運行管線 / 佇列",
        msg_no_signal: "無訊號 / 佇列空閒",
        // AI 助手
        chat_sessions: "對話紀錄",
        label_ai_model: "選擇 AI 模型",
        chat_welcome: "哈囉！我是 AI 助手，今天有什麼我可以幫您的嗎？",
        btn_clear_chat: "清除內容",
        placeholder_chat: "輸入訊息...",
        // 設定
        settings_appearance: "外觀視覺",
        label_theme: "佈景主題",
        btn_toggle_theme: "切換深淺模式",
        settings_language: "語言與區域",
        label_lang: "系統語言",
        btn_toggle_lang: "切換中英文",
        settings_account: "管理帳戶",
        label_logout: "連線控制",
        btn_logout: "登出系統",
        // 提示
        toast_auth_ok: "連線建立成功",
        toast_auth_fail: "授權失敗",
        toast_job_ok: "任務已成功派發",
        toast_job_fail: "派發失敗",
        toast_job_abort: "任務已中止",
        status_pending: "待處理",
        status_queued: "排隊中",
        status_running: "運算中",
        status_completed: "已完成",
        status_failed: "失敗"
    },
    en: {
        login_title: "System Login",
        label_username: "Username",
        label_password: "Password",
        btn_login: "Submit Auth",
        // Navigation
        nav_dashboard: "Dashboard",
        nav_assistant: "Assistant",
        nav_settings: "Settings",
        // Dashboard
        token_overview: "Token Resources",
        token_used: "Used",
        token_limit: "Limit",
        token_reset: "Reset Date",
        job_compose: "New Task",
        label_job_name: "Job Name",
        label_model_name: "Model Identifier",
        label_priority: "Queue Priority",
        priority_0: "0 - BATCH",
        priority_1: "1 - NORMAL",
        priority_2: "2 - HIGH",
        label_epochs: "Epochs",
        label_batch: "Batch Size",
        btn_dispatch: "Dispatch Task",
        pipeline_active: "Active Pipeline",
        msg_no_signal: "No Signal / Queue Empty",
        // Assistant
        chat_sessions: "Sessions",
        label_ai_model: "AI Model",
        chat_welcome: "Hello! I am your AI assistant. How can I help you today?",
        btn_clear_chat: "Clear",
        placeholder_chat: "Type a message...",
        // Settings
        settings_appearance: "Appearance",
        label_theme: "Theme Mode",
        btn_toggle_theme: "Toggle Theme",
        settings_language: "Localization",
        label_lang: "System Language",
        btn_toggle_lang: "Switch Lang",
        settings_account: "Account",
        label_logout: "Session Control",
        btn_logout: "Logout",
        // Toasts
        toast_auth_ok: "Connection Established",
        toast_auth_fail: "Authentication Failed",
        toast_job_ok: "Task Dispatched Successfully",
        toast_job_fail: "Failed to dispatch",
        toast_job_abort: "Task Aborted",
        status_pending: "PENDING",
        status_queued: "QUEUED",
        status_running: "RUNNING",
        status_completed: "COMPLETED",
        status_failed: "FAILED"
    }
};

let currentLang = localStorage.getItem('ai_hud_lang') || 'zh';
let currentTheme = localStorage.getItem('ai_hud_theme') || 'dark';

// DOM Elements
const bodyEl = document.documentElement;
const loginView = document.getElementById('login-view');
const dashView = document.getElementById('dashboard-view');
const loginForm = document.getElementById('login-form');
const loginBtn = document.getElementById('login-btn');
const toastEl = document.getElementById('toast');
const toastMsg = document.getElementById('toast-msg');
const toastIcon = document.getElementById('toast-icon');

// HUD/Nav Nodes
const tabBtns = document.querySelectorAll('.tab-btn');
const pageViews = document.querySelectorAll('.page-view');
const userDisplay = document.getElementById('user-display');
const userRole = document.getElementById('user-role');

// Assistant Nodes
const sessionListEl = document.getElementById('session-list');
const newChatBtn = document.getElementById('new-chat-btn');
const chatHistoryEl = document.getElementById('chat-history');
const chatForm = document.getElementById('chat-form');
const chatInput = document.getElementById('chat-input');
const chatModelSelect = document.getElementById('chat-model-select');
const clearChatBtn = document.getElementById('clear-chat-btn');

// Dashboard Nodes
const tokenPercent = document.getElementById('token-percent');
const tokenRingFill = document.getElementById('token-ring-fill');
const tokenUsed = document.getElementById('token-used');
const tokenLimit = document.getElementById('token-limit');
const tokenReset = document.getElementById('token-reset');
const jobForm = document.getElementById('job-form');
const jobListContainer = document.getElementById('job-list-container');
const refreshJobsBtn = document.getElementById('refresh-jobs-btn');
const submitJobBtn = document.getElementById('submit-job-btn');

// =========================
// ZH: 初始化階段 | EN: Initialization Phase
// =========================
document.addEventListener('DOMContentLoaded', () => {
    applyTheme(currentTheme);
    applyLanguage(currentLang);
    renderSessions();
    if (authToken) {
        checkAuth();
    }
    
    // ZH: 設定頁面事件綁定 | EN: Settings Page Event Binding
    document.querySelectorAll('.toggle-theme-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            currentTheme = currentTheme === 'dark' ? 'light' : 'dark';
            applyTheme(currentTheme);
        });
    });

    document.querySelectorAll('.toggle-lang-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            currentLang = currentLang === 'zh' ? 'en' : 'zh';
            applyLanguage(currentLang);
            if(authToken && !dashView.classList.contains('hidden')) {
                fetchJobs();
            }
        });
    });

    document.querySelectorAll('#logout-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            authToken = null;
            localStorage.removeItem('ai_hud_token');
            if(pollInterval) clearInterval(pollInterval);
            switchToLogin();
        });
    });

    newChatBtn.addEventListener('click', createNewSession);
    
    if(jobForm) jobForm.addEventListener('submit', handleJobSubmit);
    if(refreshJobsBtn) refreshJobsBtn.addEventListener('click', fetchJobs);
});

// =========================
// ZH: 導覽與分頁切換 | EN: Navigation & Tab Switching
// =========================
tabBtns.forEach(btn => {
    btn.addEventListener('click', () => {
        const targetTab = btn.getAttribute('data-tab');
        switchTab(targetTab);
    });
});

function switchTab(tabId) {
    tabBtns.forEach(b => {
        if(b.getAttribute('data-tab') === tabId) b.classList.add('active');
        else b.classList.remove('active');
    });

    pageViews.forEach(p => {
        if(p.id === `${tabId}-page`) p.classList.add('active');
        else p.classList.remove('active');
    });

    if(tabId === 'assistant') {
        renderActiveChat();
    }
}

// =========================
// ZH: 聊天室會話管理 | EN: Chat Session Management
// =========================
function renderSessions() {
    if(!sessionListEl) return;
    sessionListEl.innerHTML = '';
    sessions.forEach(session => {
        const item = document.createElement('div');
        item.className = `session-item ${session.id === activeSessionId ? 'active' : ''}`;
        item.onclick = () => selectSession(session.id);
        
        item.innerHTML = `
            <span class="session-name" id="name-${session.id}">${session.name}</span>
            <div class="session-actions">
                <ion-icon name="create-outline" title="Rename" class="action-rename"></ion-icon>
                <ion-icon name="trash-outline" title="Delete" class="action-delete"></ion-icon>
            </div>
        `;
        sessionListEl.appendChild(item);
        
        item.querySelector('.action-rename').onclick = (e) => renameSession(e, session.id);
        item.querySelector('.action-delete').onclick = (e) => deleteSession(e, session.id);
    });
}

function selectSession(id) {
    activeSessionId = id;
    localStorage.setItem('ai_hud_active_session', id);
    renderSessions();
    renderActiveChat();
}

function createNewSession() {
    const id = 'sess_' + Date.now();
    sessions.unshift({ id, name: 'New Research', messages: [] });
    saveSessions();
    selectSession(id);
}

function renameSession(e, id) {
    e.stopPropagation();
    const newName = prompt('Enter new name:', sessions.find(s => s.id === id).name);
    if(newName) {
        sessions.find(s => s.id === id).name = newName;
        saveSessions();
        renderSessions();
    }
}

function deleteSession(e, id) {
    e.stopPropagation();
    if(sessions.length <= 1) {
        alert('Cannot delete the last session.');
        return;
    }
    if(!confirm('Delete this session?')) return;
    
    sessions = sessions.filter(s => s.id !== id);
    if(activeSessionId === id) activeSessionId = sessions[0].id;
    saveSessions();
    renderSessions();
    renderActiveChat();
}

function saveSessions() {
    localStorage.setItem('ai_hud_sessions', JSON.stringify(sessions));
}

function renderActiveChat() {
    if(!chatHistoryEl) return;
    const active = sessions.find(s => s.id === activeSessionId) || sessions[0];
    chatHistoryEl.innerHTML = `
        <div class="ai-bubble intro">
            <div class="bubble-content" data-i18n="chat_welcome">${t('chat_welcome')}</div>
        </div>
    `;
    active.messages.forEach(msg => renderBubble(msg));
    chatHistoryEl.scrollTop = chatHistoryEl.scrollHeight;
}

// =========================
// ZH: 主題與多語系引擎 | EN: Theme & Language Engines
// =========================
function applyTheme(theme) {
    bodyEl.setAttribute('data-theme', theme);
    localStorage.setItem('ai_hud_theme', theme);
    document.querySelectorAll('.toggle-theme-btn ion-icon').forEach(icon => {
        icon.setAttribute('name', theme === 'dark' ? 'moon-outline' : 'sunny-outline');
    });
}

function applyLanguage(lang) {
    localStorage.setItem('ai_hud_lang', lang);
    const dict = TRANSLATIONS[lang];
    document.querySelectorAll('[data-i18n]').forEach(el => {
        const key = el.getAttribute('data-i18n');
        if(dict[key]) el.textContent = dict[key];
    });
    document.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
        const key = el.getAttribute('data-i18n-placeholder');
        if(dict[key]) el.placeholder = dict[key];
    });
}

function t(key) {
    return (TRANSLATIONS[currentLang] && TRANSLATIONS[currentLang][key]) || key;
}

function showToast(msgKey, isError = false) {
    if(!toastMsg) return;
    toastMsg.textContent = t(msgKey);
    toastIcon.innerHTML = isError ? '<ion-icon name="warning-outline" style="color:#fb7185"></ion-icon>' : '<ion-icon name="checkmark-circle-outline" style="color:var(--accent-glow)"></ion-icon>';
    toastEl.style.borderColor = isError ? '#fb7185' : 'var(--border-color)';
    toastEl.classList.remove('hidden');
    setTimeout(() => { toastEl.classList.add('hidden'); }, 3000);
}

// =========================
// ZH: 身份驗證 | EN: Authentication
// =========================
if(loginForm) {
    loginForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const userValue = document.getElementById('username').value;
        const passValue = document.getElementById('password').value;
        loginBtn.disabled = true;

        try {
            const formData = new URLSearchParams();
            formData.set('username', userValue);
            formData.set('password', passValue);

            const res = await fetch(`${API_BASE}/auth/login`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                body: formData
            });

            if (!res.ok) throw new Error('fail');
            const data = await res.json();
            authToken = data.access_token;
            localStorage.setItem('ai_hud_token', authToken);
            showToast('toast_auth_ok');
            await fetchDashboardData();
            switchToDashboard();
        } catch {
            showToast('toast_auth_fail', true);
        } finally {
            loginBtn.disabled = false;
        }
    });
}

async function checkAuth() {
    try {
        const res = await fetch(`${API_BASE}/auth/me`, {
            headers: { 'Authorization': `Bearer ${authToken}` }
        });
        if (!res.ok) throw new Error('expired');
        await fetchDashboardData();
        switchToDashboard();
    } catch {
        switchToLogin();
    }
}

function switchToDashboard() {
    if(loginView) loginView.classList.add('hidden');
    if(dashView) dashView.classList.remove('hidden');
    if(pollInterval) clearInterval(pollInterval);
    pollInterval = setInterval(fetchJobs, 5000);
    switchTab('dashboard');
}

function switchToLogin() {
    if(dashView) dashView.classList.add('hidden');
    if(loginView) loginView.classList.remove('hidden');
}

// =========================
// ZH: 儀表板與任務邏輯 | EN: Dashboard & Jobs
// =========================
async function fetchDashboardData() {
    await Promise.all([fetchUserProfile(), fetchTokenUsage(), fetchJobs()]);
}

async function fetchUserProfile() {
    const res = await fetch(`${API_BASE}/auth/me`, { headers: { 'Authorization': `Bearer ${authToken}` } });
    if(res.ok) {
        const data = await res.json();
        if(userDisplay) userDisplay.textContent = data.username;
        if(userRole) userRole.textContent = data.role.toUpperCase();
    }
}

async function fetchTokenUsage() {
    const res = await fetch(`${API_BASE}/auth/usage`, { headers: { 'Authorization': `Bearer ${authToken}` } });
    if(res.ok) {
        const data = await res.json();
        const percentage = (data.usage_percentage * 100).toFixed(1);
        if(tokenPercent) tokenPercent.textContent = `${percentage}%`;
        if(tokenUsed) tokenUsed.textContent = data.tokens_used.toLocaleString();
        if(tokenLimit) tokenLimit.textContent = data.tokens_limit.toLocaleString();
        if(tokenReset) tokenReset.textContent = formatDate(data.reset_date);
        if(tokenRingFill) tokenRingFill.style.strokeDashoffset = 314 - (314 * data.usage_percentage);
    }
}

function formatDate(dateStr) {
    if (!dateStr) return '--';
    const d = new Date(dateStr);
    return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
}

async function fetchJobs() {
    try {
        const res = await fetch(`${API_BASE}/jobs`, { headers: { 'Authorization': `Bearer ${authToken}` } });
        if(res.ok) {
            const data = await res.json();
            renderJobs(data.items || []);
        }
    } catch(e) {}
}

function renderJobs(jobs) {
    if(!jobListContainer) return;
    jobListContainer.innerHTML = jobs.length ? '' : `
        <div class="empty-state">
            <ion-icon name="radio-outline"></ion-icon>
            <p data-i18n="msg_no_signal">No Signal</p>
        </div>
    `;
    jobs.forEach(job => {
        const card = document.createElement('div');
        card.className = 'job-card';
        card.innerHTML = `
            <div class="job-head">
                <span class="job-title">${job.job_name}</span>
                <span class="job-status" style="border:1px solid var(--accent-glow); color:var(--accent-glow);">${job.status.toUpperCase()}</span>
            </div>
            <div class="job-progress-bar">
                <div class="job-progress-fill" style="width: ${job.progress || 0}%"></div>
            </div>
        `;
        jobListContainer.appendChild(card);
    });
}

async function handleJobSubmit(e) {
    e.preventDefault();
    const jobData = {
        job_name: document.getElementById('job-name').value,
        model_name: document.getElementById('model-name').value,
        gpu_required: 1,
        priority: parseInt(document.getElementById('job-priority').value),
        config: {
            epochs: parseInt(document.getElementById('job-epochs').value),
            batch_size: parseInt(document.getElementById('job-batch').value)
        }
    };

    try {
        const res = await fetch(`${API_BASE}/jobs`, {
            method: 'POST',
            headers: { 'Authorization': `Bearer ${authToken}`, 'Content-Type': 'application/json' },
            body: JSON.stringify(jobData)
        });
        if(!res.ok) throw new Error('fail');
        showToast('toast_job_ok');
        jobForm.reset();
        fetchJobs();
    } catch {
        showToast('toast_job_fail', true);
    }
}

// =========================
// ZH: AI 助手串流邏輯 | EN: AI Assistant Streaming
// =========================
if(chatForm) {
    chatForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const prompt = chatInput.value.trim();
        if(!prompt) return;

        chatInput.value = '';
        chatInput.style.height = '60px';

        const currentSession = sessions.find(s => s.id === activeSessionId) || sessions[0];
        
        // User message
        const userMsg = { role: 'user', content: prompt };
        currentSession.messages.push(userMsg);
        renderBubble(userMsg);
        saveSessions();

        // Create empty AI bubble
        const aiBubble = createBubble('assistant', '');
        const contentEl = aiBubble.querySelector('.bubble-content');
        chatHistoryEl.appendChild(aiBubble);
        chatHistoryEl.scrollTop = chatHistoryEl.scrollHeight;

        try {
            const response = await fetch(`${API_BASE}/chat/completions`, {
                method: 'POST',
                headers: { 
                    'Authorization': `Bearer ${authToken}`,
                    'Content-Type': 'application/json' 
                },
                body: JSON.stringify({ 
                    model_id: chatModelSelect.value, 
                    messages: currentSession.messages, 
                    stream: true 
                })
            });
            
            if(!response.ok) throw new Error('Stream Error');

            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let aiFullText = '';

            while(true) {
                const { value, done } = await reader.read();
                if(done) break;

                const chunk = decoder.decode(value);
                const lines = chunk.split('\n');
                
                for(const line of lines) {
                    if(line.startsWith('data: ')) {
                        const dataStr = line.replace('data: ', '').trim();
                        if(dataStr === '[DONE]') continue;
                        try {
                            const json = JSON.parse(dataStr);
                            const content = json.choices[0].delta.content || '';
                            aiFullText += content;
                            contentEl.textContent = aiFullText;
                            chatHistoryEl.scrollTop = chatHistoryEl.scrollHeight;
                        } catch(e) {}
                    }
                }
            }
            
            currentSession.messages.push({ role: 'assistant', content: aiFullText });
            saveSessions();
        } catch (err) {
            contentEl.textContent = "Error occurred during AI generation.";
        }
    });
}

function renderBubble(msg) {
    if(!chatHistoryEl) return;
    const div = createBubble(msg.role, msg.content);
    chatHistoryEl.appendChild(div);
    chatHistoryEl.scrollTop = chatHistoryEl.scrollHeight;
}

function createBubble(role, content) {
    const div = document.createElement('div');
    div.className = role === 'user' ? 'user-bubble' : 'ai-bubble';
    div.innerHTML = `<div class="bubble-content">${content}</div>`;
    return div;
}

if(clearChatBtn) {
    clearChatBtn.addEventListener('click', () => {
        if(!confirm('Clear this session?')) return;
        const session = sessions.find(s => s.id === activeSessionId);
        if(session) {
            session.messages = [];
            saveSessions();
            renderActiveChat();
        }
    });
}

if(chatInput) {
    chatInput.addEventListener('input', () => {
        chatInput.style.height = '60px';
        chatInput.style.height = (chatInput.scrollHeight) + 'px';
    });
}
