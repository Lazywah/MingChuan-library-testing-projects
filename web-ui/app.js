// =========================
// ZH: 系統狀態與設定 | EN: State & Configuration
// =========================
const API_BASE = '/api/v1';
let authToken = localStorage.getItem('ai_hud_token') || null;
let pollInterval = null;

// ZH: i18n 翻譯字典 | EN: i18n Translation Dictionary
const TRANSLATIONS = {
    zh: {
        login_title: "系統登入",
        label_username: "使用者名稱",
        label_password: "密碼",
        btn_login: "傳送授權",
        token_overview: "代幣資源概況",
        token_used: "已使用",
        token_limit: "總管額",
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
const bodyEl = document.documentElement; // ZH: 使用 root 用於 data-theme | EN: using root for data-theme
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

// HUD Data Nodes
const userDisplay = document.getElementById('user-display');
const userRole = document.getElementById('user-role');
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
        // ZH: 如果已經登入，刷新任務列表以獲取最新翻譯狀態 | EN: Refresh jobs list to update status translations if logged in
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
        if(dict[key]) {
            el.textContent = dict[key];
        }
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
    const user = document.getElementById('username').value;
    const pass = document.getElementById('password').value;
    
    loginBtn.disabled = true;

    try {
        const formData = new URLSearchParams();
        formData.append('username', user);
        formData.append('password', pass);

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
    } catch {
        logoutBtn.click();
    }
}

function switchToDashboard() {
    loginView.classList.add('hidden');
    setTimeout(() => {
        dashView.classList.remove('hidden');
        if(pollInterval) clearInterval(pollInterval);
        pollInterval = setInterval(fetchJobs, 5000); // ZH: 輪詢任務狀態 | EN: Poll job status
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
