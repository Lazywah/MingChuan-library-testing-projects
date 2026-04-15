// =========================
// ZH: 系統狀態與設定 | EN: State & Configuration
// =========================
const API_BASE = '/api/v1';
let authToken = localStorage.getItem('ai_hud_token') || null;
let pollInterval = null;

// ZH: 多對話管理狀態 (於 TRANSLATIONS 宣告後再初始化) | EN: Multi-session state (initialized after TRANSLATIONS)
let sessions = null; // ZH: 將於 TRANSLATIONS 宣告後初始化 | EN: Initialized after TRANSLATIONS
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
        btn_new_chat: "開始新對話",
        new_session_name: "新對話",
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
        status_failed: "失敗",
        // AI Hub
        hub_title_models: "AI 模型",
        hub_desc_models: "文字、圖片辨識、搜尋、歸納、解任務！",
        hub_card_chat: "文字聊天",
        hub_card_search: "上網搜尋",
        hub_card_vision: "圖片辨識",
        hub_title_writing: "文書寫作",
        hub_desc_writing: "文字作業、歸納、會議紀錄整理、語音轉換！",
        hub_card_editor: "AI小編",
        hub_card_pdf: "PDF合約",
        hub_card_ppt: "文書簡報",
        hub_title_media: "影音創作",
        hub_desc_media: "生成圖片、生成影片、生成歌曲！",
        hub_card_image: "生成圖片",
        hub_card_video: "生成影片",
        hub_card_music: "生成歌曲",
        hub_title_life: "生活/翻譯",
        hub_desc_life: "多語翻譯、衛教知識、專屬知識庫！",
        hub_card_translate: "多語翻譯",
        hub_card_health: "衛生教育",
        hub_card_kb: "知識庫",
        hub_coming_soon_title: "🚧 此功能即將推出 🚧",
        hub_coming_soon_desc: "我們正在努力開發此模組，敬請期待未來更新！",
        btn_back_hub: "返回大廳"
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
        btn_new_chat: "Start New Conversation",
        new_session_name: "New Chat",
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
        status_failed: "FAILED",
        // AI Hub
        hub_title_models: "AI Models",
        hub_desc_models: "Text, vision, search, and tasks!",
        hub_card_chat: "Text Chat",
        hub_card_search: "Web Search",
        hub_card_vision: "Vision",
        hub_title_writing: "Writing",
        hub_desc_writing: "Essays, summaries, notes, and speech-to-text!",
        hub_card_editor: "AI Editor",
        hub_card_pdf: "PDF Contract",
        hub_card_ppt: "Presentation",
        hub_title_media: "Multimedia",
        hub_desc_media: "Generate images, videos, and music!",
        hub_card_image: "Image Gen",
        hub_card_video: "Video Gen",
        hub_card_music: "Music Gen",
        hub_title_life: "Life / Translate",
        hub_desc_life: "Translation, health, and knowledge base!",
        hub_card_translate: "Translation",
        hub_card_health: "Health Edu",
        hub_card_kb: "Knowledge Base",
        hub_coming_soon_title: "🚧 Coming Soon 🚧",
        hub_coming_soon_desc: "We are currently developing this module, stay tuned!",
        btn_back_hub: "Back to Hub"
    }
};

let currentLang = localStorage.getItem('ai_hud_lang') || 'zh';
let currentTheme = localStorage.getItem('ai_hud_theme') || 'dark';

// ZH: 在 TRANSLATIONS 宣告後才初始化 sessions，避免 ReferenceError
// EN: Initialize sessions AFTER TRANSLATIONS to avoid ReferenceError
sessions = JSON.parse(localStorage.getItem('ai_hud_sessions')) || [
    { id: 'default', name: TRANSLATIONS[currentLang].chat_sessions || 'New Chat', messages: [] }
];

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

// AI Hub Nodes
const aiHubContainer = document.getElementById('ai-hub-container');
const chatLayout = document.getElementById('chat-layout');
const comingSoonLayout = document.getElementById('coming-soon-layout');
const hubSubCards = document.querySelectorAll('.hub-sub-card');
const backToHubBtns = document.querySelectorAll('.back-to-hub-btn');

// Hub navigation helpers
function showHubView(targetId) {
    aiHubContainer.classList.remove('active');
    chatLayout.classList.add('hidden');
    comingSoonLayout.classList.remove('active');
    if (targetId === 'chat-layout') {
        chatLayout.classList.remove('hidden');
    } else if (targetId === 'coming-soon-layout') {
        comingSoonLayout.classList.add('active');
    }
}
function showHub() {
    aiHubContainer.classList.add('active');
    chatLayout.classList.add('hidden');
    comingSoonLayout.classList.remove('active');
}

// Bind hub card clicks
hubSubCards.forEach(card => {
    card.addEventListener('click', () => showHubView(card.getAttribute('data-target')));
});

// Bind back-to-hub buttons
backToHubBtns.forEach(btn => btn.addEventListener('click', () => showHub()));

// ZH: 切換離開 AI 助手分頁時，重設回大廳 | EN: Reset to hub when leaving assistant tab
document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        if (btn.getAttribute('data-tab') !== 'assistant') showHub();
    });
});

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
            if (authToken && !dashView.classList.contains('hidden')) {
                fetchJobs();
            }
        });
    });

    document.querySelectorAll('#logout-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            authToken = null;
            localStorage.removeItem('ai_hud_token');
            if (pollInterval) clearInterval(pollInterval);
            switchToLogin();
        });
    });

    newChatBtn.addEventListener('click', createNewSession);

    if (jobForm) jobForm.addEventListener('submit', handleJobSubmit);
    if (refreshJobsBtn) refreshJobsBtn.addEventListener('click', fetchJobs);
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
        if (b.getAttribute('data-tab') === tabId) b.classList.add('active');
        else b.classList.remove('active');
    });

    pageViews.forEach(p => {
        if (p.id === `${tabId}-page`) p.classList.add('active');
        else p.classList.remove('active');
    });

    if (tabId === 'assistant') {
        renderActiveChat();
    }
}

// =========================
// ZH: 聊天室會話管理 | EN: Chat Session Management
// =========================
function renderSessions() {
    if (!sessionListEl) return;

    // Clear all session items except the new chat button
    const newChatBtn = sessionListEl.querySelector('.new-chat-btn');
    sessionListEl.innerHTML = '';

    // Add the new chat button at the top
    if (newChatBtn) {
        sessionListEl.appendChild(newChatBtn);
    }

    // Render all sessions
    sessions.forEach(session => {
        const item = document.createElement('div');
        item.className = `session-item ${session.id === activeSessionId ? 'active' : ''}`;
        item.onclick = () => selectSession(session.id);

        item.innerHTML = `
            <span class="session-name" id="name-${session.id}">${session.name}</span>
            <div class="session-actions">
                <ion-icon name="create-outline" class="action-rename" title="Rename"></ion-icon>
                <ion-icon name="trash-outline" class="action-delete" title="Delete"></ion-icon>
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
    // ZH: 使用 i18n 取名，避免硬寫英文 | EN: Use i18n for name to avoid hardcoded English
    const defaultName = TRANSLATIONS[currentLang].new_session_name || 'New Research';
    sessions.unshift({ id, name: defaultName, messages: [] });
    saveSessions();
    selectSession(id);
}

function renameSession(e, id) {
    e.stopPropagation();
    const newName = prompt('Enter new name:', sessions.find(s => s.id === id).name);
    if (newName) {
        sessions.find(s => s.id === id).name = newName;
        saveSessions();
        renderSessions();
    }
}

function deleteSession(e, id) {
    e.stopPropagation();
    if (!confirm('Delete this session?')) return;

    sessions = sessions.filter(s => s.id !== id);

    // If no sessions left, create a new one automatically
    if (sessions.length === 0) {
        const newId = 'sess_' + Date.now();
        sessions.unshift({ id: newId, name: 'New Chat', messages: [] });
        activeSessionId = newId;
    } else if (activeSessionId === id) {
        activeSessionId = sessions[0].id;
    }

    saveSessions();
    renderSessions();
    renderActiveChat();
}

function saveSessions() {
    if (window.currentUsername) {
        localStorage.setItem(`ai_hud_sessions_${window.currentUsername}`, JSON.stringify(sessions));
    } else {
        localStorage.setItem('ai_hud_sessions', JSON.stringify(sessions));
    }
}

function renderActiveChat() {
    if (!chatHistoryEl) return;
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
        if (dict[key]) el.textContent = dict[key];
    });
    document.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
        const key = el.getAttribute('data-i18n-placeholder');
        if (dict[key]) el.placeholder = dict[key];
    });
    document.querySelectorAll('[data-i18n-aria]').forEach(el => {
        const key = el.getAttribute('data-i18n-aria');
        if (dict[key]) el.setAttribute('aria-label', dict[key]);
    });
}

function t(key) {
    return (TRANSLATIONS[currentLang] && TRANSLATIONS[currentLang][key]) || key;
}

function showToast(msgKey, isError = false) {
    if (!toastMsg) return;
    toastMsg.textContent = t(msgKey);
    toastIcon.innerHTML = isError ? '<ion-icon name="warning-outline" style="color:#fb7185"></ion-icon>' : '<ion-icon name="checkmark-circle-outline" style="color:var(--accent-glow)"></ion-icon>';
    toastEl.style.borderColor = isError ? '#fb7185' : 'var(--border-color)';
    toastEl.classList.remove('hidden');
    setTimeout(() => { toastEl.classList.add('hidden'); }, 3000);
}

// =========================
// ZH: 身份驗證 | EN: Authentication
// =========================
if (loginForm) {
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
    if (loginView) loginView.classList.add('hidden');
    if (dashView) dashView.classList.remove('hidden');
    if (pollInterval) clearInterval(pollInterval);
    pollInterval = setInterval(fetchJobs, 5000);
    // Add token usage refresh interval
    setInterval(fetchTokenUsage, 10000); // Refresh token usage every 10 seconds
    switchTab('dashboard');
}

function switchToLogin() {
    if (dashView) dashView.classList.add('hidden');
    if (loginView) loginView.classList.remove('hidden');
}

// =========================
// ZH: 儀表板與任務邏輯 | EN: Dashboard & Jobs
// =========================
async function fetchDashboardData() {
    await Promise.all([fetchUserProfile(), fetchTokenUsage(), fetchJobs()]);
}

async function fetchUserProfile() {
    const res = await fetch(`${API_BASE}/auth/me`, { headers: { 'Authorization': `Bearer ${authToken}` } });
    if (res.ok) {
        const data = await res.json();
        if (userDisplay) userDisplay.textContent = data.username;
        if (userRole) userRole.textContent = data.role.toUpperCase();
        
        // ZH: 依照帳號掛載其專屬的聊天歷史紀錄 | EN: Load specific chat sessions per user
        window.currentUsername = data.username;
        const userSessionsKey = `ai_hud_sessions_${data.username}`;
        let userSessions = JSON.parse(localStorage.getItem(userSessionsKey));
        
        if (!userSessions || userSessions.length === 0) {
            userSessions = [{ id: 'sess_' + Date.now(), name: TRANSLATIONS[currentLang].chat_sessions || 'New Chat', messages: [] }];
            localStorage.setItem(userSessionsKey, JSON.stringify(userSessions));
        }
        
        sessions = userSessions;
        activeSessionId = sessions[0].id;
        
        renderSessions();
        renderActiveChat();
    }
}

async function fetchTokenUsage() {
    try {
        const res = await fetch(`${API_BASE}/auth/usage`, { headers: { 'Authorization': `Bearer ${authToken}` } });
        if (res.ok) {
            const data = await res.json();
            console.log('Token usage data:', data);
            updateTokenDisplay(data);
        } else {
            console.error('Token usage API error:', res.status);
            // Use cached/local token tracking as fallback
            updateTokenDisplayFromLocal();
        }
    } catch (e) {
        console.error('Error fetching token usage:', e);
        updateTokenDisplayFromLocal();
    }
}

function updateTokenDisplay(data) {
    // Handle both percentage formats (0.1 or 10%)
    const usagePercentage = data.usage_percentage;
    const percentage = usagePercentage > 1 ? usagePercentage : (usagePercentage * 100).toFixed(1);

    if (tokenPercent) tokenPercent.textContent = `${percentage}%`;
    if (tokenUsed) tokenUsed.textContent = (data.tokens_used || 0).toLocaleString();
    if (tokenLimit) tokenLimit.textContent = (data.tokens_limit || 0).toLocaleString();
    if (tokenReset) tokenReset.textContent = formatDate(data.reset_date);

    // Update progress ring - handle both percentage formats
    const normalizedPercentage = usagePercentage > 1 ? usagePercentage / 100 : usagePercentage;
    if (tokenRingFill) tokenRingFill.style.strokeDashoffset = 314 - (314 * normalizedPercentage);

    // Store in localStorage for offline tracking
    localStorage.setItem('token_usage_data', JSON.stringify(data));

    console.log('Token display updated:', {
        percentage,
        tokens_used: data.tokens_used,
        tokens_limit: data.tokens_limit,
        reset_date: data.reset_date,
        normalizedPercentage
    });
}

function updateTokenDisplayFromLocal() {
    const localData = localStorage.getItem('token_usage_data');
    if (localData) {
        try {
            const data = JSON.parse(localData);
            updateTokenDisplay(data);
        } catch (e) {
            console.error('Error parsing local token data:', e);
            // Set default values
            if (tokenPercent) tokenPercent.textContent = '0%';
            if (tokenUsed) tokenUsed.textContent = '0';
            if (tokenLimit) tokenLimit.textContent = '10000';
            if (tokenReset) tokenReset.textContent = '--';
            if (tokenRingFill) tokenRingFill.style.strokeDashoffset = 314;
        }
    }
}

function trackTokenUsage(messageTokens, isUser = true) {
    // Simple token estimation (rough approximation: 1 token ≈ 4 characters for English, 2-3 for Chinese)
    const estimatedTokens = Math.ceil(messageTokens.length / 3);

    const localData = localStorage.getItem('token_usage_data');
    if (localData) {
        try {
            const data = JSON.parse(localData);
            data.tokens_used = (data.tokens_used || 0) + estimatedTokens;
            data.usage_percentage = Math.min(data.tokens_used / data.tokens_limit, 1);
            updateTokenDisplay(data);
        } catch (e) {
            console.error('Error updating local token tracking:', e);
        }
    }
}

function formatDate(dateStr) {
    if (!dateStr) return '--';
    const d = new Date(dateStr);
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

async function fetchJobs() {
    try {
        console.log('Fetching jobs from API...');
        const res = await fetch(`${API_BASE}/jobs`, {
            headers: { 'Authorization': `Bearer ${authToken}` }
        });

        if (!res.ok) {
            console.error('Jobs API response not OK:', res.status, res.statusText);
            renderJobs([]);
            return;
        }

        const data = await res.json();
        console.log('Jobs data received:', data);
        const jobs = data.items || data || [];
        console.log('Jobs to render:', jobs);
        renderJobs(jobs);
    } catch (e) {
        console.error('Error fetching jobs:', e);
        renderJobs([]);
    }
}

function renderJobs(jobs) {
    if (!jobListContainer) return;

    console.log('Rendering jobs:', jobs);

    if (!jobs || jobs.length === 0) {
        jobListContainer.innerHTML = `
            <div class="empty-state">
                <ion-icon name="radio-outline"></ion-icon>
                <p data-i18n="msg_no_signal">No Signal / Queue Empty</p>
            </div>
        `;
        return;
    }

    jobListContainer.innerHTML = '';
    jobs.forEach((job, index) => {
        const card = document.createElement('div');
        card.className = 'job-card';

        // Handle different job data structures
        const jobName = job.job_name || job.name || `Job ${index + 1}`;
        const jobStatus = job.status || 'unknown';
        const jobProgress = job.progress || job.progress_percentage || 0;
        const jobId = job.id || job.job_id || `job_${index}`;
        const modelName = job.model_name || job.model || 'Unknown Model';

        // Status color mapping
        let statusColor = 'var(--accent-glow)';
        let statusBg = 'transparent';

        switch (jobStatus.toLowerCase()) {
            case 'running':
                statusColor = '#10b981';
                statusBg = 'rgba(16, 185, 129, 0.1)';
                break;
            case 'completed':
                statusColor = '#3b82f6';
                statusBg = 'rgba(59, 130, 246, 0.1)';
                break;
            case 'failed':
                statusColor = '#ef4444';
                statusBg = 'rgba(239, 68, 68, 0.1)';
                break;
            case 'queued':
            case 'pending':
                statusColor = '#f59e0b';
                statusBg = 'rgba(245, 158, 11, 0.1)';
                break;
        }

        card.innerHTML = `
            <div class="job-head">
                <div class="job-info">
                    <span class="job-title">${jobName}</span>
                    <span class="job-id">ID: ${jobId}</span>
                </div>
                <span class="job-status" style="background: ${statusBg}; border:1px solid ${statusColor}; color:${statusColor};">
                    ${t(`status_${jobStatus.toLowerCase()}`) || jobStatus.toUpperCase()}
                </span>
            </div>
            <div class="job-meta">
                <span class="job-model">${modelName}</span>
                <span class="job-priority">Priority: ${job.priority || 1}</span>
            </div>
            <div class="job-progress-bar">
                <div class="job-progress-fill" style="width: ${jobProgress}%"></div>
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
        if (!res.ok) throw new Error('fail');
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
if (chatForm) {
    chatForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const prompt = chatInput.value.trim();
        if (!prompt) return;

        chatInput.value = '';
        // 重置为单行高度（42.4px = 22.4px + 20px padding）
        chatInput.style.height = '42.4px';

        const currentSession = sessions.find(s => s.id === activeSessionId) || sessions[0];

        // User message
        const userMsg = { role: 'user', content: prompt };
        currentSession.messages.push(userMsg);
        renderBubble(userMsg);
        saveSessions();

        // Track token usage for user message
        trackTokenUsage(prompt, true);

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

            if (!response.ok) throw new Error('Stream Error');

            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let aiFullText = '';

            while (true) {
                const { value, done } = await reader.read();
                if (done) break;

                const chunk = decoder.decode(value);
                const lines = chunk.split('\n');

                for (const line of lines) {
                    if (line.startsWith('data: ')) {
                        const dataStr = line.replace('data: ', '').trim();
                        if (dataStr === '[DONE]') continue;
                        try {
                            const json = JSON.parse(dataStr);

                            // 判斷是否為伺服器錯誤訊息 (例如 Token 用盡)
                            if (json.error) {
                                aiFullText = `[系統拒絕]: ${json.error === 'Token quota exceeded' ? '您的 Token 額度已用盡，請聯繫管理員擴充額度。' : json.error}`;
                                contentEl.innerHTML = `<span style="color: #ff4d4f; font-weight: bold;">${aiFullText}</span>`;
                                chatHistoryEl.scrollTop = chatHistoryEl.scrollHeight;
                                break;
                            }

                            const content = json.choices[0].delta.content || '';
                            aiFullText += content;
                            contentEl.textContent = aiFullText;
                            chatHistoryEl.scrollTop = chatHistoryEl.scrollHeight;
                        } catch (e) { }
                    }
                }
            }

            currentSession.messages.push({ role: 'assistant', content: aiFullText });
            saveSessions();

            // Track token usage for AI response
            trackTokenUsage(aiFullText, false);
        } catch (err) {
            // 保留已生成的文字，在末端追加紅色警告提示
            const errorHint = `<br><br><span style="color: #ff4d4f; font-size: 13px; font-weight: bold;">[系統提示]: 連線意外中斷或發生錯誤 (${err.message})</span>`;
            contentEl.innerHTML = (aiFullText ? aiFullText : contentEl.textContent) + errorHint;
        }
    });
}

function renderBubble(msg) {
    if (!chatHistoryEl) return;
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


if (chatInput) {
    // 精确行高 = font-size 16px * line-height 1.4 = 22.4px
    const LINE_HEIGHT = 22.4;
    const PADDING = 20; // 10px top + 10px bottom

    // 基础高度（单行 + padding）
    const MIN_HEIGHT = LINE_HEIGHT + PADDING; // 42.4px
    // 最大高度（三行 + padding）
    const MAX_HEIGHT = (LINE_HEIGHT * 3) + PADDING; // 87.2px

    const adjustHeight = () => {
        // 先重置為 1px 以獲取準確純文字所需之 scrollHeight (避免 auto 預設造成兩行)
        chatInput.style.height = '1px';

        // 获取包含padding的scrollHeight
        const scrollHeight = chatInput.scrollHeight;

        // 计算行数（基于纯内容高度）
        const contentHeight = scrollHeight - PADDING;
        let lines = Math.round(contentHeight / LINE_HEIGHT);
        if (lines < 1) lines = 1;
        if (lines > 3) lines = 3;

        // 根据行数计算高度
        const newHeight = (lines * LINE_HEIGHT) + PADDING;

        // 应用高度（在最小和最大之间）
        chatInput.style.height = Math.max(MIN_HEIGHT, Math.min(newHeight, MAX_HEIGHT)) + 'px';
    };

    // 输入时实时调整高度
    chatInput.addEventListener('input', adjustHeight);

    // 键盘事件也触发调整（处理删除、回车等）
    chatInput.addEventListener('keyup', adjustHeight);

    // 粘贴事件延迟处理
    chatInput.addEventListener('paste', () => {
        setTimeout(adjustHeight, 10);
    });

    // 窗口大小变化时重新计算
    window.addEventListener('resize', adjustHeight);

    // 初始化高度
    adjustHeight();
}
