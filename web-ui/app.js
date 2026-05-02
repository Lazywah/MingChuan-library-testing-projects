// =========================
// ZH: 系統狀態與設定 | EN: State & Configuration
// =========================
const API_BASE = '/api/v1';
let authToken = localStorage.getItem('ai_hud_token') || null;
let uploadedDatasetPath = null;
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
        btn_login: "登入",
        // 導覽
        nav_compute: "運算任務",
        nav_assistant: "AI 助手",
        nav_settings: "系統設定",
        nav_admin: "管理中心",
        // 儀表板
        token_overview: "代幣資源概況",
        token_used: "已使用",
        token_limit: "總配額",
        token_reset: "重置日期",
        job_compose: "建立新任務",
        label_job_name: "任務名稱",
        label_model_name: "模型辨識碼",
        label_priority: "佇列優先級",
        label_dataset: "資料集 (自動推薦)",
        priority_0: "0 - 批次處理",
        priority_1: "1 - 正常佇列",
        priority_2: "2 - 急件優先",
        label_epochs: "訓練迴圈數",
        label_batch: "批次大小",
        btn_dispatch: "派發任務",
        compute_high: "高算力運算",
        compute_mid_low: "中低算力運算",
        pipeline_active: "運行管線 / 佇列",
        msg_no_signal: "無訊號 / 佇列空閒",
        btn_view_details: "查看詳情",
        job_details_title: "任務詳情",
        tab_logs: "終端日誌 (Console Logs)",
        tab_metrics: "收斂曲線 (Loss Curve)",
        label_auto_scroll: "自動捲動 (Auto-scroll)",
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
        btn_back_hub: "返回大廳",
        // 管理員
        admin_users: "使用者管理",
        admin_models: "模型管理",
        admin_jobs: "全域排程",
        admin_col_user: "帳號",
        admin_col_email: "信箱",
        admin_col_role: "角色",
        admin_col_status: "狀態",
        admin_col_ip: "最後IP",
        admin_col_login_time: "最後登入",
        admin_col_tokens: "Token用量",
        // 教學
        settings_tutorial: "教學手冊",
        label_reopen_tutorial: "入站導覽",
        btn_reopen_tutorial: "開啟教學",
        tutorial_title: "歡迎來到 AI Base！",
        tutorial_step1_title: "運算任務",
        tutorial_step1_desc: "提交高算力或中低算力運算任務，並即時監控您的作業佇列。",
        tutorial_step2_title: "AI 助手",
        tutorial_step2_desc: "存取各類 AI 模型進行文字聊天、圖片辨識、搜尋等功能。",
        tutorial_step3_title: "系統設定",
        tutorial_step3_desc: "查看您的 Token 配額、切換主題和語言、管理帳戶。",
        tutorial_dismiss: "不再顯示",
        tutorial_ok: "了解！",
        // 首頁 & 面板
        nav_home: "首頁",
        nav_docs: "文件庫",
        drawer_title: "資訊面板",
        drawer_token: "Token 用量",
        drawer_features: "可用功能",
        drawer_announcements: "公告與更新",
        feat_1: "高算力 GPU",
        feat_2: "AI 文字助手",
        feat_3: "圖片生成 (即將推出)",
        anno_1: "系統升級至 Blackwell 架構完成。",
        ql_jupyter_title: "JupyterLab",
        ql_jupyter_desc: "進入進階開發環境",
        ql_school_title: "學校首頁",
        ql_school_desc: "前往 MCU 官方網站",
        ql_support_title: "問題回報",
        ql_support_desc: "回報系統問題與建議",
        compute_high_desc: "高算力佇列 (GPU 處理)",
        compute_midlow_desc: "中低算力佇列 (服務層處理)",
        priority_high_desc: "高算力 GPU 運算",
        priority_normal_desc: "一般算力運算",
        // 文件庫頁面
        doc_lib_title: "文件庫",
        doc_portfolio_title: "未來作品集",
        doc_portfolio_desc: "展示您的 AI 訓練成果與模型作品。",
        doc_solutions_title: "問題解法",
        doc_solutions_desc: "常見問題的解決方案與除錯技巧。",
        doc_tutorial_title: "模型製作教學",
        doc_tutorial_desc: "從零開始學習如何訓練與部署 AI 模型。",
        doc_coming_soon: "內容建置中，敬請期待..."
    },
    en: {
        login_title: "System Login",
        label_username: "Username",
        label_password: "Password",
        btn_login: "Login",
        // Navigation
        nav_compute: "Compute",
        nav_assistant: "Assistant",
        nav_settings: "Settings",
        nav_admin: "Admin",
        // Dashboard
        token_overview: "Token Resources",
        token_used: "Used",
        token_limit: "Limit",
        token_reset: "Reset Date",
        job_compose: "New Task",
        label_job_name: "Job Name",
        label_model_name: "Model Identifier",
        label_priority: "Queue Priority",
        label_dataset: "Dataset (Auto Config)",
        priority_0: "0 - BATCH",
        priority_1: "1 - NORMAL",
        priority_2: "2 - HIGH",
        label_epochs: "Epochs",
        label_batch: "Batch Size",
        btn_dispatch: "Dispatch Task",
        compute_high: "High Compute",
        compute_mid_low: "Mid / Low Compute",
        pipeline_active: "Active Pipeline",
        msg_no_signal: "No Signal / Queue Empty",
        btn_view_details: "View Details",
        job_details_title: "Job Details",
        tab_logs: "Console Logs",
        tab_metrics: "Loss Curve",
        label_auto_scroll: "Auto-scroll",
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
        btn_back_hub: "Back to Hub",
        // Admin
        admin_users: "User Management",
        admin_models: "Models",
        admin_jobs: "All Jobs",
        admin_col_user: "Username",
        admin_col_email: "Email",
        admin_col_role: "Role",
        admin_col_status: "Status",
        admin_col_ip: "Last IP",
        admin_col_login_time: "Last Login",
        admin_col_tokens: "Tokens",
        // Tutorial
        settings_tutorial: "Tutorial Guide",
        label_reopen_tutorial: "Onboarding Guide",
        btn_reopen_tutorial: "Show Tutorial",
        tutorial_title: "Welcome to AI Base!",
        tutorial_step1_title: "Compute Tasks",
        tutorial_step1_desc: "Submit high or mid/low compute tasks and monitor your job queue in real time.",
        tutorial_step2_title: "AI Assistant",
        tutorial_step2_desc: "Access various AI models for text chat, image recognition, web search and more.",
        tutorial_step3_title: "Settings",
        tutorial_step3_desc: "Check your token quota, switch themes & language, and manage your account.",
        tutorial_dismiss: "Don't show again",
        tutorial_ok: "Got it!",
        // Home & Drawer
        nav_home: "Home",
        nav_docs: "Documents",
        drawer_title: "Info Board",
        drawer_token: "Token Usage",
        drawer_features: "Available Features",
        drawer_announcements: "Announcements & Updates",
        feat_1: "High Compute GPU",
        feat_2: "AI Text Assistant",
        feat_3: "Image Gen (Soon)",
        anno_1: "System upgraded to Blackwell architecture.",
        ql_jupyter_title: "JupyterLab",
        ql_jupyter_desc: "Access advanced dev environment",
        ql_school_title: "School Homepage",
        ql_school_desc: "Visit MCU official website",
        ql_support_title: "Report Issues",
        ql_support_desc: "Report bugs & suggestions",
        compute_high_desc: "High Compute Queue (GPU Processing)",
        compute_midlow_desc: "Mid/Low Compute Queue (Service Layer)",
        priority_high_desc: "High Priority GPU Processing",
        priority_normal_desc: "Normal Priority Processing",
        // Document Library page
        doc_lib_title: "Document Library",
        doc_portfolio_title: "Future Portfolio",
        doc_portfolio_desc: "Showcase your AI training results and model works.",
        doc_solutions_title: "Problem Solutions",
        doc_solutions_desc: "Common solutions and debugging tips.",
        doc_tutorial_title: "Model Training Tutorial",
        doc_tutorial_desc: "Learn to train and deploy AI models from scratch.",
        doc_coming_soon: "Content under construction, stay tuned..."
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
const jobListHigh = document.getElementById('job-list-high');
const jobListMidLow = document.getElementById('job-list-midlow');
const submitJobBtn = document.getElementById('submit-job-btn');
const profileUpdateForm = document.getElementById('profile-update-form');

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
            // Close dropdown if open
            const menu = document.getElementById('user-dropdown-menu');
            if (menu) menu.style.display = 'none';
            switchToLogin();
        });
    });

    // ZH: 使用者下拉選單切換 | EN: User dropdown toggle
    const userDropdownToggle = document.getElementById('user-dropdown-toggle');
    const userDropdownMenu = document.getElementById('user-dropdown-menu');
    if (userDropdownToggle && userDropdownMenu) {
        userDropdownToggle.addEventListener('click', (e) => {
            e.stopPropagation();
            const isOpen = userDropdownMenu.style.display === 'block';
            userDropdownMenu.style.display = isOpen ? 'none' : 'block';
        });
        // Close on outside click
        document.addEventListener('click', (e) => {
            if (!userDropdownToggle.contains(e.target) && !userDropdownMenu.contains(e.target)) {
                userDropdownMenu.style.display = 'none';
            }
        });
    }

    newChatBtn.addEventListener('click', createNewSession);

    const jobFormHigh = document.getElementById('job-form-high');
    const jobFormMidLow = document.getElementById('job-form-midlow');
    if (jobFormHigh) jobFormHigh.addEventListener('submit', (e) => handleJobSubmit(e, 2, 'job-form-high'));
    if (jobFormMidLow) jobFormMidLow.addEventListener('submit', (e) => handleJobSubmit(e, 1, 'job-form-midlow'));

    if (profileUpdateForm) profileUpdateForm.addEventListener('submit', handleProfileUpdate);
    const datasetInputHigh = document.getElementById('datasetFile-high');
    const datasetInputMidLow = document.getElementById('datasetFile-midlow');
    if (datasetInputHigh) datasetInputHigh.addEventListener('change', (e) => handleDatasetUpload(e, 'high'));
    if (datasetInputMidLow) datasetInputMidLow.addEventListener('change', (e) => handleDatasetUpload(e, 'midlow'));
    document.querySelectorAll('.refresh-jobs-btn').forEach(btn => {
        btn.addEventListener('click', fetchJobs);
    });

    // ZH: Info Board Toggle (Side Drawer) | EN: Info Board Toggle
    const sideDrawerToggle = document.getElementById('nav-sidebar-toggle');
    const sideDrawer = document.getElementById('side-drawer');
    if (sideDrawerToggle && sideDrawer) {
        sideDrawerToggle.addEventListener('click', (e) => {
            e.preventDefault();
            sideDrawer.classList.toggle('closed');
        });
    }

    // ZH: Compute Sub Tabs Toggle | EN: Compute Sub Tabs Toggle
    document.querySelectorAll('.sub-tab-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.sub-tab-btn').forEach(b => b.classList.remove('active'));
            document.querySelectorAll('.sub-page-view').forEach(p => p.classList.remove('active'));
            btn.classList.add('active');
            const targetId = btn.getAttribute('data-subtab') + '-page';
            const targetPage = document.getElementById(targetId);
            if (targetPage) targetPage.classList.add('active');
        });
    });
    
    // Quick tutorial Nav - bind the info button to the global showTutorial()
    const navQuickTutorial = document.getElementById('nav-quick-tutorial');
    if (navQuickTutorial) {
        navQuickTutorial.addEventListener('click', (e) => {
            e.preventDefault();
            showTutorial();
        });
    }

    // ZH: 標頭登入按鈕 | EN: Header login button - opens login modal
    const headerLoginBtn = document.getElementById('header-login-btn');
    if (headerLoginBtn) {
        headerLoginBtn.addEventListener('click', () => {
            if (loginView) loginView.classList.remove('hidden');
        });
    }

    // ZH: 登入視窗關閉按鈕 | EN: Login modal close button
    const loginCloseBtn = document.querySelector('#login-form-box .close');
    if (loginCloseBtn) {
        loginCloseBtn.addEventListener('click', () => {
            if (loginView) loginView.classList.add('hidden');
        });
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

            // ZH: 管理員直接導向管理面板 | EN: Redirect admin to admin panel
            const meRes = await fetch(`${API_BASE}/auth/me`, {
                headers: { 'Authorization': `Bearer ${authToken}` }
            });
            if (meRes.ok) {
                const meData = await meRes.json();
                if (meData.role === 'admin') {
                    window.location.href = 'admin.html';
                    return;
                }
            }

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
        const userData = await res.json();

        // ZH: 管理員自動導向管理面板 | EN: Redirect admin to admin panel
        if (userData.role === 'admin') {
            window.location.href = 'admin.html';
            return;
        }

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
    setInterval(fetchTokenUsage, 10000);
    switchTab('home'); // Default to home after login

    // ZH: 切換標頭: 隱藏登入按鈕, 顯示使用者資訊 | EN: Toggle header: hide login btn, show user info
    const headerLoginBtn = document.getElementById('header-login-btn');
    const userInfoDisplay = document.getElementById('user-info-display');
    if (headerLoginBtn) headerLoginBtn.style.display = 'none';
    if (userInfoDisplay) userInfoDisplay.style.display = 'flex';

    // ZH: 顯示需登入才能用的導覽項目 | EN: Show auth-gated nav items
    toggleAuthGatedUI(true);

    // ZH: 教學導覽: 首次登入時顯示 | EN: Show tutorial on first login
    if (!isTutorialDismissed()) {
        showTutorial();
    }
}

function switchToLogin() {
    // ZH: 不再自動彈出登入框, 使用者可瀏覽首頁 | EN: Don't auto-show login, user can browse Home
    if (dashView) dashView.classList.remove('hidden');
    switchTab('home');

    // ZH: 切換標頭: 顯示登入按鈕, 隱藏使用者資訊 | EN: Toggle header: show login btn, hide user info
    const headerLoginBtn = document.getElementById('header-login-btn');
    const userInfoDisplay = document.getElementById('user-info-display');
    if (headerLoginBtn) headerLoginBtn.style.display = 'flex';
    if (userInfoDisplay) userInfoDisplay.style.display = 'none';

    // ZH: 隱藏需登入才能用的導覽項目 | EN: Hide auth-gated nav items
    toggleAuthGatedUI(false);
}

// ZH: 切換需登入才能用的 UI 元素 | EN: Toggle auth-gated UI elements
function toggleAuthGatedUI(show) {
    const authTabs = ['tab-dash', 'tab-chat', 'tab-settings'];
    authTabs.forEach(id => {
        const el = document.getElementById(id);
        if (el) el.style.display = show ? 'flex' : 'none';
    });
    // ZH: 教學按鈕 (底部 ⓘ) | EN: Tutorial info button
    const tutorialBtn = document.getElementById('nav-quick-tutorial');
    if (tutorialBtn) tutorialBtn.style.display = show ? 'flex' : 'none';
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
        window.currentUserRole = data.role;
        window.currentUserData = data;
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

        // ZH: 管理員處理 | EN: Admin role handling
        const adminPortalSec = document.getElementById('admin-portal-section');
        if (data.role === 'admin' && adminPortalSec) {
            adminPortalSec.style.display = 'block';
        }
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

    // Update Side Drawer Token Stats
    const drawerTokenUsed = document.getElementById('drawer-token-used');
    const drawerTokenLimit = document.getElementById('drawer-token-limit');
    if (drawerTokenUsed) drawerTokenUsed.textContent = (data.tokens_used || 0).toLocaleString();
    if (drawerTokenLimit) drawerTokenLimit.textContent = (data.tokens_limit || 0).toLocaleString();

    // Update drawer donut chart
    const drawerTokenRing = document.getElementById('drawer-token-ring');
    const drawerTokenPercent = document.getElementById('drawer-token-percent');
    if (drawerTokenRing) drawerTokenRing.style.strokeDashoffset = 100 - (100 * normalizedPercentage);
    if (drawerTokenPercent) drawerTokenPercent.textContent = `${percentage}%`;

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
    const emptyHTML = `<div class="empty-state"><ion-icon name="radio-outline"></ion-icon><p data-i18n="msg_no_signal">${t('msg_no_signal')}</p></div>`;

    if (!jobs || jobs.length === 0) {
        if (jobListHigh) jobListHigh.innerHTML = emptyHTML;
        if (jobListMidLow) jobListMidLow.innerHTML = emptyHTML;
        return;
    }

    const highJobs = jobs.filter(j => (j.priority || 0) >= 2);
    const midLowJobs = jobs.filter(j => (j.priority || 0) < 2);

    function renderToContainer(container, list) {
        if (!container) return;
        if (list.length === 0) { container.innerHTML = emptyHTML; return; }
        container.innerHTML = '';
        list.forEach((job, index) => {
            const card = document.createElement('div');
            card.className = 'job-card';
            const jobName = job.job_name || job.name || `Job ${index + 1}`;
            const jobStatus = job.status || 'unknown';
            const jobProgress = job.progress || job.progress_percentage || 0;
            const jobId = job.id || job.job_id || `job_${index}`;
            const modelName = job.model_name || job.model || 'Unknown Model';
            let statusColor = 'var(--accent-glow)', statusBg = 'transparent';
            switch (jobStatus.toLowerCase()) {
                case 'running': statusColor = '#10b981'; statusBg = 'rgba(16,185,129,0.1)'; break;
                case 'completed': statusColor = '#3b82f6'; statusBg = 'rgba(59,130,246,0.1)'; break;
                case 'failed': statusColor = '#ef4444'; statusBg = 'rgba(239,68,68,0.1)'; break;
                case 'queued': case 'pending': statusColor = '#f59e0b'; statusBg = 'rgba(245,158,11,0.1)'; break;
            }
            card.innerHTML = `
                <div class="job-head">
                    <div class="job-info">
                        <span class="job-title">${jobName}</span>
                        <span class="job-id">ID: ${jobId}</span>
                    </div>
                    <span class="job-status" style="background:${statusBg}; border:1px solid ${statusColor}; color:${statusColor};">
                        ${t(`status_${jobStatus.toLowerCase()}`) || jobStatus.toUpperCase()}
                    </span>
                </div>
                <div class="job-meta">
                    <span class="job-model">${modelName}</span>
                    <span class="job-priority">Priority: ${job.priority || 0}</span>
                </div>
                <div class="job-progress-bar"><div class="job-progress-fill" style="width:${jobProgress}%"></div></div>
                <div style="margin-top: 10px; text-align: right;">
                    <button class="ready-btn" style="padding: 4px 10px; font-size: 0.8em; min-width: auto; width: auto;" onclick="openJobDetails('${jobId}')" data-i18n="btn_view_details">查看詳情</button>
                </div>
            `;
            container.appendChild(card);
        });
        applyTranslations(); // Translate the newly added buttons
    }

    renderToContainer(jobListHigh, highJobs);
    renderToContainer(jobListMidLow, midLowJobs);
}

async function handleJobSubmit(e, priority, formId) {
    e.preventDefault();
    let suffix = formId === 'job-form-high' ? '-high' : '-midlow';
    const jobData = {
        job_name: document.getElementById('job-name' + suffix).value,
        model_name: document.getElementById('model-name' + suffix).value,
        gpu_required: priority >= 2 ? 1 : 0,
        priority: priority,
        dataset_path: uploadedDatasetPath,
        config: {
            epochs: parseInt(document.getElementById('job-epochs' + suffix).value),
            batch_size: parseInt(document.getElementById('job-batch' + suffix).value)
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
        document.getElementById(formId).reset();
        const group = document.getElementById('auto-detect-group' + suffix);
        if (group) group.style.display = 'none';
        uploadedDatasetPath = null;
        fetchJobs();
    } catch {
        showToast('toast_job_fail', true);
    }
}

async function handleDatasetUpload(e, type) {
    const file = e.target.files[0];
    if (!file) return;

    const formData = new FormData();
    formData.append('file', file);

    const suffix = type === 'high' ? '-high' : '-midlow';
    const btn = document.querySelector(`#job-form-${type} button[type="submit"]`);
    const originalText = btn.innerHTML;
    btn.innerHTML = `<span class="spinner" style="margin-right:5px"></span><span>Uploading...</span>`;
    btn.disabled = true;

    try {
        const res = await fetch(`${API_BASE}/datasets/upload`, {
            method: 'POST',
            headers: { 'Authorization': `Bearer ${authToken}` },
            body: formData
        });
        if (!res.ok) throw new Error('Upload failed');
        
        const data = await res.json();
        uploadedDatasetPath = data.dataset_path;
        
        // Show auto-detect group
        const group = document.getElementById('auto-detect-group' + suffix);
        if (group) group.style.display = 'grid';

        if (data.suggested_config) {
            document.getElementById('model-name' + suffix).value = type === 'high' ? 'LLaMA-3' : 'BERT-Mini';

            if (data.suggested_config.epochs) {
                document.getElementById('job-epochs' + suffix).value = data.suggested_config.epochs;
            }
            if (data.suggested_config.batch_size) {
                document.getElementById('job-batch' + suffix).value = data.suggested_config.batch_size;
            }
            // highlight the fields to show they were auto-filled
            const modelInput = document.getElementById('model-name' + suffix);
            const epochsInput = document.getElementById('job-epochs' + suffix);
            const batchInput = document.getElementById('job-batch' + suffix);
            epochsInput.style.borderColor = 'var(--neon-green)';
            batchInput.style.borderColor = 'var(--neon-green)';
            modelInput.style.borderColor = 'var(--neon-green)';
            setTimeout(() => {
                epochsInput.style.borderColor = '';
                batchInput.style.borderColor = '';
                modelInput.style.borderColor = '';
            }, 2000);
        }
        
        showToast('File uploaded & parameters suggested');
    } catch (err) {
        console.error(err);
        showToast('Upload failed', true);
        e.target.value = '';
    } finally {
        btn.innerHTML = originalText;
        btn.disabled = false;
    }
}

async function handleProfileUpdate(e) {
    e.preventDefault();
    const emailVal = document.getElementById('profile-email').value.trim();
    const passVal = document.getElementById('profile-password').value.trim();
    const submitBtn = e.target.querySelector('button[type="submit"]');

    const updateData = {};
    if (emailVal) updateData.email = emailVal;
    if (passVal) updateData.password = passVal;

    if (Object.keys(updateData).length === 0) {
        // Nothing to update
        showToast('toast_auth_fail', true);
        return;
    }

    submitBtn.disabled = true;
    try {
        const res = await fetch(`${API_BASE}/auth/me`, {
            method: 'PUT',
            headers: { 
                'Authorization': `Bearer ${authToken}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(updateData)
        });
        if (!res.ok) throw new Error('Update failed');
        showToast('toast_auth_ok');
        document.getElementById('profile-password').value = '';
    } catch (err) {
        console.error(err);
        showToast('toast_auth_fail', true);
    } finally {
        submitBtn.disabled = false;
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

// =========================
// ZH: 教學導覽邏輯 | EN: Tutorial Modal Logic
// =========================
const TUTORIAL_DISMISSED_KEY = 'ai_hud_tutorial_dismissed';

function showTutorial() {
    const modal = document.getElementById('tutorial-modal');
    if (modal) modal.classList.remove('hidden');
}

async function hideTutorial() {
    const modal = document.getElementById('tutorial-modal');
    if (modal) modal.classList.add('hidden');
    const check = document.getElementById('tutorial-dismiss-check');
    if (check && check.checked) {
        localStorage.setItem(TUTORIAL_DISMISSED_KEY, 'true');
        if (authToken && window.currentUserData) {
            window.currentUserData.tutorial_dismissed = 1;
            try {
                await fetch(`${API_BASE}/auth/me`, {
                    method: 'PUT',
                    headers: {
                        'Content-Type': 'application/json',
                        'Authorization': `Bearer ${authToken}`
                    },
                    body: JSON.stringify({ tutorial_dismissed: 1 })
                });
            } catch (e) {
                console.error("Failed to sync tutorial state to DB", e);
            }
        }
    }
}

function isTutorialDismissed() {
    if (window.currentUserData && window.currentUserData.tutorial_dismissed === 1) {
        return true;
    }
    return localStorage.getItem(TUTORIAL_DISMISSED_KEY) === 'true';
}

// Tutorial event bindings
const _tutorialCloseBtn = document.getElementById('tutorial-close-btn');
const _tutorialOkBtn = document.getElementById('tutorial-ok-btn');
const reopenTutorialBtn = document.getElementById('reopen-tutorial-btn');
if (_tutorialCloseBtn) _tutorialCloseBtn.addEventListener('click', hideTutorial);
if (_tutorialOkBtn) _tutorialOkBtn.addEventListener('click', hideTutorial);
if (reopenTutorialBtn) reopenTutorialBtn.addEventListener('click', showTutorial);

// =========================
// ZH: 任務詳情邏輯 | EN: Job Details Modal & SSE Logic
// =========================
const jobDetailsModal = document.getElementById('job-details-modal');
const jobDetailsCloseBtn = document.getElementById('job-details-close-btn');
const jobDetailsBackdrop = document.getElementById('job-details-backdrop');
const detailJobId = document.getElementById('detail-job-id');
const jobLogsContainer = document.getElementById('job-logs-container');
const autoScrollCheckbox = document.getElementById('auto-scroll-logs');

const tabBtnLogs = document.getElementById('tab-btn-logs');
const tabBtnMetrics = document.getElementById('tab-btn-metrics');
const viewLogs = document.getElementById('view-logs');
const viewMetrics = document.getElementById('view-metrics');

let currentEventSource = null;
let lossChart = null;

if (jobDetailsCloseBtn) {
    jobDetailsCloseBtn.addEventListener('click', closeJobDetails);
    jobDetailsBackdrop.addEventListener('click', closeJobDetails);
}

if (tabBtnLogs && tabBtnMetrics) {
    tabBtnLogs.addEventListener('click', () => {
        tabBtnLogs.classList.add('active');
        tabBtnMetrics.classList.remove('active');
        viewLogs.classList.remove('hidden');
        viewMetrics.classList.add('hidden');
    });
    tabBtnMetrics.addEventListener('click', () => {
        tabBtnMetrics.classList.add('active');
        tabBtnLogs.classList.remove('active');
        viewMetrics.classList.remove('hidden');
        viewLogs.classList.add('hidden');
        if (lossChart) lossChart.update(); // Fix canvas render issues
    });
}

function initChart() {
    const ctx = document.getElementById('lossChart');
    if (!ctx) return;
    if (lossChart) lossChart.destroy();
    
    lossChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: [],
            datasets: [{
                label: 'Training Loss',
                data: [],
                borderColor: '#10b981',
                backgroundColor: 'rgba(16, 185, 129, 0.1)',
                borderWidth: 2,
                pointBackgroundColor: '#10b981',
                fill: true,
                tension: 0.3
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            color: '#fff',
            scales: {
                x: {
                    title: { display: true, text: 'Epoch', color: 'rgba(255,255,255,0.7)' },
                    grid: { color: 'rgba(255,255,255,0.1)' },
                    ticks: { color: 'rgba(255,255,255,0.7)' }
                },
                y: {
                    title: { display: true, text: 'Loss', color: 'rgba(255,255,255,0.7)' },
                    grid: { color: 'rgba(255,255,255,0.1)' },
                    ticks: { color: 'rgba(255,255,255,0.7)' }
                }
            },
            plugins: {
                legend: { labels: { color: '#fff' } }
            }
        }
    });
}

function closeJobDetails() {
    if (jobDetailsModal) jobDetailsModal.classList.add('hidden');
    if (currentEventSource) {
        currentEventSource.close();
        currentEventSource = null;
    }
}

window.openJobDetails = function(jobId) {
    if (!jobDetailsModal) return;
    detailJobId.textContent = jobId;
    jobLogsContainer.textContent = '';
    initChart();
    
    // Switch to Logs tab by default
    if (tabBtnLogs) tabBtnLogs.click();
    
    jobDetailsModal.classList.remove('hidden');

    if (currentEventSource) {
        currentEventSource.close();
    }

    // Connect to SSE
    currentEventSource = new EventSource(`${API_BASE}/jobs/${jobId}/stream`);
    
    currentEventSource.onmessage = function(event) {
        try {
            const data = JSON.parse(event.data);
            
            // Append Logs
            if (data.logs !== undefined) { // Initial load
                jobLogsContainer.textContent = data.logs;
            } else if (data.new_logs) { // Updates
                jobLogsContainer.textContent += data.new_logs;
            }
            
            // Auto Scroll
            if (autoScrollCheckbox && autoScrollCheckbox.checked) {
                jobLogsContainer.scrollTop = jobLogsContainer.scrollHeight;
            }

            // Append Metrics
            let metricsToAdd = [];
            if (data.metrics) metricsToAdd = data.metrics; // Initial load
            if (data.new_metrics) metricsToAdd = data.new_metrics; // Updates
            
            if (metricsToAdd.length > 0 && lossChart) {
                metricsToAdd.forEach(m => {
                    lossChart.data.labels.push(m.epoch);
                    lossChart.data.datasets[0].data.push(m.loss);
                });
                lossChart.update();
            }

            // Check if finished
            if (['completed', 'failed', 'cancelled'].includes(data.status)) {
                currentEventSource.close();
                jobLogsContainer.textContent += `\n[System] Job finished with status: ${data.status}\n`;
                if (autoScrollCheckbox && autoScrollCheckbox.checked) {
                    jobLogsContainer.scrollTop = jobLogsContainer.scrollHeight;
                }
            }
            
        } catch(e) {
            console.error("Error parsing SSE data", e);
        }
    };
    
    currentEventSource.onerror = function(err) {
        console.error("EventSource failed:", err);
        currentEventSource.close();
        jobLogsContainer.textContent += `\n[System] Disconnected from log stream.\n`;
    };
};
