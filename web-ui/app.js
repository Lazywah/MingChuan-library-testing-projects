// =========================
// ZH: 系統狀態與設定 | EN: State & Configuration
// =========================
const API_BASE = '/api/v1';
let authToken = localStorage.getItem('ai_hud_token') || null;
let pollInterval = null;
let chatMessages = []; // ZH: 記憶體內對話歷史 | EN: In-memory chat history

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
        chat_config: "助手設定",
        label_ai_model: "選擇 AI 模型",
        chat_welcome: "哈囉！我是 AI 助手，今天有什麼我可以幫您的嗎？",
        btn_clear_chat: "清除對話",
        placeholder_chat: "輸入訊息...",
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
        chat_config: "Assistant Config",
        label_ai_model: "Select AI Model",
        chat_welcome: "Hello! I am your AI assistant. How can I help you today?",
        btn_clear_chat: "Clear History",
        placeholder_chat: "Type a message...",
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
const toggleLangBtns = document.querySelectorAll('.toggle-lang-btn');
const toggleThemeBtns = document.querySelectorAll('.toggle-theme-btn');

const loginView = document.getElementById('login-view');
const dashView = document.getElementById('dashboard-view');
const loginForm = document.getElementById('login-form');
const loginBtn = document.getElementById('login-btn');
const logoutBtn = document.getElementById('logout-btn');
const toastEl = document.getElementById('toast');
const toastMsg = document.getElementById('toast-msg');
const toastIcon = document.getElementById('toast-icon');

// HUD/Nav Nodes
const tabBtns = document.querySelectorAll('.tab-btn');
const pageViews = document.querySelectorAll('.page-view');
const userDisplay = document.getElementById('user-display');
const userRole = document.getElementById('user-role');

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
const eyeToggle = document.getElementById('eye-toggle');

// Assistant Nodes
const chatHistoryEl = document.getElementById('chat-history');
const chatForm = document.getElementById('chat-form');
const chatInput = document.getElementById('chat-input');
const chatModelSelect = document.getElementById('chat-model-select');
const clearChatBtn = document.getElementById('clear-chat-btn');

// =========================
// ZH: 初始化階段 | EN: Initialization Phase
// =========================
document.addEventListener('DOMContentLoaded', () => {
    applyTheme(currentTheme);
    applyLanguage(currentLang);
    if (authToken) {
        checkAuth();
    }
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
    // ZH: 更新按鈕狀態 | EN: Update button states
    tabBtns.forEach(b => {
        if(b.getAttribute('data-tab') === tabId) b.classList.add('active');
        else b.classList.remove('active');
    });

    // ZH: 更新視圖狀態 | EN: Update view states
    pageViews.forEach(p => {
        if(p.id === `${tabId}-page`) p.classList.add('active');
        else p.classList.remove('active');
    });

    // ZH: 進入特定分頁的額外邏輯 | EN: Extra logic for specific tabs
    if(tabId === 'assistant') {
        chatHistoryEl.scrollTop = chatHistoryEl.scrollHeight;
    }
}

// =========================
// ZH: 主題與多語系引擎 | EN: Theme & Language Engines
// =========================
toggleThemeBtns.forEach(btn => {
    btn.addEventListener('click', () => {
        currentTheme = currentTheme === 'dark' ? 'light' : 'dark';
        applyTheme(currentTheme);
    });
});

toggleLangBtns.forEach(btn => {
    btn.addEventListener('click', () => {
        currentLang = currentLang === 'zh' ? 'en' : 'zh';
        applyLanguage(currentLang);
        if(authToken && !dashView.classList.contains('hidden')) {
            fetchJobs();
        }
    });
});

function applyTheme(theme) {
    bodyEl.setAttribute('data-theme', theme);
    localStorage.setItem('ai_hud_theme', theme);
    toggleThemeBtns.forEach(btn => {
        const icon = btn.querySelector('ion-icon');
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
    return TRANSLATIONS[currentLang][key] || key;
}

// =========================
// ZH: 彈窗提示系統 | EN: Toast Notification System
// =========================
function showToast(msgKey, isError = false) {
    toastMsg.textContent = t(msgKey);
    if (isError) {
        toastIcon.innerHTML = '<ion-icon name="warning-outline" style="color:var(--text-primary);"></ion-icon>';
        toastEl.style.borderColor = '#fb7185';
    } else {
        toastIcon.innerHTML = '<ion-icon name="information-circle-outline" style="color:var(--accent-glow);"></ion-icon>';
        toastEl.style.borderColor = 'var(--border-color)';
    }
    toastEl.classList.remove('hidden');
    setTimeout(() => { toastEl.classList.add('hidden'); }, 3000);
}

// =========================
// ZH: 介面互動事件 | EN: UI Interactions
// =========================
eyeToggle.addEventListener('click', () => {
    const pwInput = document.getElementById('password');
    const loginEye = document.querySelector('.login-eye');
    if(pwInput.type === 'password') {
        pwInput.type = 'text';
        loginEye.classList.add('open');
    } else {
        pwInput.type = 'password';
        loginEye.classList.remove('open');
    }
});

function formatDate(dateStr) {
    if (!dateStr) return '--';
    const d = new Date(dateStr);
    return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')} ${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}`;
}

// =========================
// ZH: 身份驗證 | EN: Authentication
// =========================
loginForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const userValue = document.getElementById('username').value;
    const passValue = document.getElementById('password').value;
    loginBtn.disabled = true;

    try {
        const formData = new URLSearchParams();
        formData.append('username', userValue);
        formData.append('password', passValue);

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

logoutBtn.addEventListener('click', () => {
    authToken = null;
    localStorage.removeItem('ai_hud_token');
    if(pollInterval) clearInterval(pollInterval);
    switchToLogin();
});

async function checkAuth() {
    try {
        const res = await fetch(`${API_BASE}/auth/me`, {
            headers: { 'Authorization': `Bearer ${authToken}` }
        });
        if (!res.ok) throw new Error('expired');
        await fetchDashboardData();
        switchToDashboard();
        fetchChatHistory(); // ZH: 載入聊天紀錄 | EN: Load chat history
    } catch {
        logoutBtn.click();
    }
}

function switchToDashboard() {
    loginView.classList.add('hidden');
    setTimeout(() => {
        dashView.classList.remove('hidden');
        if(pollInterval) clearInterval(pollInterval);
        pollInterval = setInterval(fetchJobs, 5000);
        switchTab('dashboard');
    }, 400);
}
function switchToLogin() {
    dashView.classList.add('hidden');
    setTimeout(() => {
        loginView.classList.remove('hidden');
    }, 400);
}

// =========================
// ZH: 儀表板資料獲取 | EN: Dashboard Data Fetching
// =========================
async function fetchDashboardData() {
    await Promise.all([
        fetchUserProfile(),
        fetchTokenUsage(),
        fetchJobs()
    ]);
}

async function fetchUserProfile() {
    const res = await fetch(`${API_BASE}/auth/me`, { headers: { 'Authorization': `Bearer ${authToken}` } });
    if(res.ok) {
        const data = await res.json();
        userDisplay.textContent = data.username;
        userRole.textContent = data.role.toUpperCase();
    }
}

async function fetchTokenUsage() {
    const res = await fetch(`${API_BASE}/auth/usage`, { headers: { 'Authorization': `Bearer ${authToken}` } });
    if(res.ok) {
        const data = await res.json();
        tokenUsed.textContent = data.tokens_used.toLocaleString();
        tokenLimit.textContent = data.tokens_limit.toLocaleString();
        tokenReset.textContent = formatDate(data.reset_date);
        
        const percentage = Math.min(100, Math.max(0, data.usage_percentage * 100)).toFixed(1);
        tokenPercent.textContent = `${percentage}%`;
        
        const circle = tokenRingFill;
        const radius = circle.r.baseVal.value;
        const circumference = radius * 2 * Math.PI;
        const offset = circumference - (percentage / 100) * circumference;
        circle.style.strokeDashoffset = offset;
    }
}

// =========================
// ZH: 任務管理 | EN: Jobs Management
// =========================
jobForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    submitJobBtn.disabled = true;
    
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
        await fetchDashboardData();
    } catch {
        showToast('toast_job_fail', true);
    } finally {
        submitJobBtn.disabled = false;
    }
});

refreshJobsBtn.addEventListener('click', () => {
    fetchDashboardData();
});

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
    if (jobs.length === 0) {
        jobListContainer.innerHTML = `
            <div class="empty-state">
                <ion-icon name="radio-outline" style="font-size:3rem; margin-bottom:10px;"></ion-icon>
                <p>${t('msg_no_signal')}</p>
            </div>
        `;
        return;
    }

    jobListContainer.innerHTML = '';
    jobs.forEach(job => {
        let statusTrans = t('status_' + job.status);
        let colorTheme = "var(--text-primary)";
        if(job.status === 'running') colorTheme = "var(--accent-glow)";
        if(job.status === 'completed') colorTheme = "#34d399";
        if(job.status === 'failed') colorTheme = "#fb7185";
        
        const card = document.createElement('div');
        card.className = 'job-card';
        card.style.borderLeftColor = colorTheme;
        card.style.borderLeftWidth = '3px';
        
        const isCancellable = job.status === 'pending' || job.status === 'queued';
        const cancelBtnStr = isCancellable ? `<button class="icon-action" style="position:absolute; top:10px; right:10px; font-size:20px;" onclick="cancelJob('${job.job_id}')" title="Abort"><ion-icon name="trash-outline" style="color:#fb7185"></ion-icon></button>` : '';

        card.innerHTML = `
            ${cancelBtnStr}
            <div class="job-head">
                <span class="job-title">${job.job_name}</span>
                <span class="job-status" style="border: 1px solid ${colorTheme}; color:${colorTheme}">${statusTrans}</span>
            </div>
            <div class="job-id">${job.job_id}</div>
            <div class="job-meta">
                <span><ion-icon name="cube-outline"></ion-icon> ${job.model_name}</span>
                <span><ion-icon name="hardware-chip-outline"></ion-icon> ${job.gpu_server || 'WAITING'}</span>
            </div>
            <div class="job-progress-bar">
                <div class="job-progress-fill" style="width: ${job.progress || 0}%; background-color: ${colorTheme}"></div>
            </div>
            <div style="font-size:12px; text-align:right; margin-top:2px; color:var(--text-muted)">${(job.progress || 0).toFixed(1)}%</div>
        `;
        jobListContainer.appendChild(card);
    });
}

window.cancelJob = async function(jobId) {
    if(!confirm('CONFIRM ABORT TASK?')) return;
    try {
        const res = await fetch(`${API_BASE}/jobs/${jobId}`, {
            method: 'DELETE',
            headers: { 'Authorization': `Bearer ${authToken}` }
        });
        if(!res.ok) throw new Error('fail');
        showToast('toast_job_abort');
        fetchJobs(); 
    } catch {
        showToast('toast_job_fail', true);
    }
};

// =========================
// ZH: AI 助手邏輯 | EN: AI Assistant Logic
// =========================
chatForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const prompt = chatInput.value.trim();
    if(!prompt) return;

    chatInput.value = '';
    chatInput.style.height = '60px';

    // ZH: 顯示使用的訊息 | EN: Display user message
    const userMsg = { role: 'user', content: prompt };
    chatMessages.push(userMsg);
    renderBubble(userMsg);

    // ZH: 建立空的 AI 氣泡準備填入 | EN: Create empty AI bubble for streaming
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
                messages: chatMessages,
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
                        contentEl.textContent = aiFullText; // ZH: 實時更新文字 | EN: Update text in real-time
                        chatHistoryEl.scrollTop = chatHistoryEl.scrollHeight;
                    } catch(e) {}
                }
            }
        }
        
        chatMessages.push({ role: 'assistant', content: aiFullText });

    } catch (err) {
        contentEl.textContent = "Error occurred during AI generation.";
        contentEl.classList.add('error');
    }
});

function renderBubble(msg) {
    const bubble = createBubble(msg.role, msg.content);
    chatHistoryEl.appendChild(bubble);
    chatHistoryEl.scrollTop = chatHistoryEl.scrollHeight;
}

function createBubble(role, content) {
    const div = document.createElement('div');
    div.className = role === 'user' ? 'user-bubble' : 'ai-bubble';
    div.innerHTML = `<div class="bubble-content">${content}</div>`;
    return div;
}

async function fetchChatHistory() {
    try {
        const res = await fetch(`${API_BASE}/chat/history`, {
            headers: { 'Authorization': `Bearer ${authToken}` }
        });
        if(res.ok) {
            const history = await res.json();
            chatMessages = history;
            // ZH: 清空並重新渲染 (保留 Welcome) | EN: Clear and re-render (keep welcome)
            const welcomeMsg = chatHistoryEl.querySelector('.intro');
            chatHistoryEl.innerHTML = '';
            if(welcomeMsg) chatHistoryEl.appendChild(welcomeMsg);
            
            history.forEach(msg => renderBubble(msg));
        }
    } catch(e) {}
}

clearChatBtn.addEventListener('click', () => {
    if(!confirm('Clear conversation?')) return;
    chatHistoryEl.innerHTML = `
        <div class="ai-bubble intro">
            <div class="bubble-content" data-i18n="chat_welcome">${t('chat_welcome')}</div>
        </div>
    `;
    chatMessages = [];
});

// ZH: 自動調整 Input 高度 | EN: Auto auto-resize textarea
chatInput.addEventListener('input', () => {
    chatInput.style.height = '60px';
    chatInput.style.height = (chatInput.scrollHeight) + 'px';
});
