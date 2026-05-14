const API_BASE = '/api/v1';
let authToken = localStorage.getItem('admin_hud_token');

const TRANSLATIONS = {
    zh: {
        btn_back_hub: "返回大廳",
        admin_dashboard: "管理員儀表板",
        admin_cluster_status: "叢集資源即時監控",
        admin_users: "使用者管理",
        admin_models: "模型管理",
        btn_add_model: "新增模型",
        btn_edit_model: "編輯",
        btn_delete_model: "刪除",
        edit_model_title: "編輯模型",
        confirm_delete_model: "確定要刪除模型 {name} 嗎？",
        toast_model_created: "模型已新增",
        toast_model_updated: "模型已更新",
        toast_model_deleted: "模型已刪除",
        toast_model_failed: "模型操作失敗",
        th_description: "描述",
        th_storage_path: "儲存路徑",
        admin_jobs: "全域任務",
        tab_api_models: "API 模型",
        tab_local_models: "本地模型",
        tab_management: "管理介面",
        tab_analytics: "數據分析",
        admin_configs: "系統設定檔",
        tab_high_compute: "高算力運算",
        tab_midlow_compute: "中低算力運算",
        filter_all: "全部",
        filter_pending: "等待中",
        filter_running: "執行中",
        filter_completed: "已完成",
        filter_failed: "失敗",
        filter_cancelled: "已取消",
        btn_cancel_job: "取消任務",
        btn_reprioritize: "修改優先級",
        confirm_cancel_job: "確定要取消任務 {name} 嗎？",
        prompt_new_priority: "請輸入新的優先級 (0~5)：",
        toast_job_cancelled: "任務已取消",
        toast_job_priority_updated: "優先級已更新",
        toast_job_action_failed: "操作失敗",
        th_progress: "進度",
        msg_loading: "載入中...",
        toast_refresh: "已重新整理管理員資料",
        btn_logout: "登出",
        toast_login_failed: "登入失敗，請檢查帳號密碼或權限",
        admin_login_title: "管理員登入",
        admin_username: "管理員帳號",
        admin_password: "管理員密碼",
        btn_login: "登入",
        select_config: "選擇設定檔",
        btn_load_config: "載入",
        placeholder_config_editor: "請先選擇並載入設定檔...",
        btn_save_config: "儲存變更",
        th_username: "帳號",
        th_email: "信箱",
        th_role: "權限",
        th_status: "狀態",
        th_last_ip: "最後登入 IP",
        th_last_login: "最後登入",
        th_created_at: "建立時間",
        th_tokens: "代幣",
        th_name: "名稱",
        th_framework: "框架",
        th_public: "公開",
        th_job: "任務",
        th_user: "使用者",
        th_priority: "優先級",
        no_cluster_data: "無可用叢集資料",
        th_actions: "操作",
        btn_edit: "編輯",
        edit_user_title: "編輯使用者",
        edit_new_password: "新密碼（留空則不變更）",
        edit_tokens_limit: "Token 月度上限",
        edit_tokens_used: "已使用",
        status_active: "啟用",
        status_disabled: "停用",
        toast_user_updated: "使用者資料已更新",
        toast_user_update_failed: "更新失敗",
        batch_token_label: "批量設定所有使用者 Token 上限：",
        btn_batch_apply: "套用到所有人",
        toast_batch_updated: "已更新 {count} 位使用者的 Token 上限",
        btn_reset_all_usage: "歸零所有用量",
        confirm_reset_all_usage: "確定要將所有使用者的 Token 用量歸零嗎？此操作無法復原。",
        toast_batch_reset: "已歸零 {count} 位使用者的 Token 用量",
        btn_reset_usage: "歸零用量",
        toast_user_usage_reset: "使用者用量已歸零",
        btn_reset: "初始化",
        confirm_reset_user: "確定要初始化使用者 {name} 的帳號嗎？\n密碼將被重置，用量將歸零。",
        toast_user_reset: "帳號已初始化",
        btn_add_test: "建立帳號",
        add_test_title: "建立帳號",
        btn_add_test_submit: "建立帳號",
        add_test_temp_password: "臨時密碼（僅顯示一次）：",
        toast_add_test_ok: "測試帳號已建立",
        toast_add_test_fail: "建立失敗",
        danger_zone: "危險區域",
        placeholder_admin_pwd: "請輸入您的管理員密碼以確認",
        btn_delete_user: "刪除帳號",
        btn_confirm_delete: "確認刪除",
        btn_cancel: "取消",
        toast_delete_pwd_required: "請輸入管理員密碼",
        confirm_delete_user: "確定要永久刪除此帳號嗎？",
        toast_user_deleted: "帳號已刪除",
        th_department: "學系",
        btn_analytics: "分析",
        analytics_title: "使用者數據分析",
        ua_monthly_tokens: "本月 Tokens",
        ua_lifetime_tokens: "累計 Tokens",
        ua_login_count: "登入次數",
        ua_sessions: "對話數",
        ua_tool_breakdown: "工具使用分布",
        ua_top_sessions: "前 10 對話（依 Token 用量排序）",
        ua_session_id: "對話 ID",
        ua_started_at: "開始時間",
        ua_messages: "訊息數",
        ua_tokens: "Tokens",
        toast_analytics_failed: "載入分析資料失敗",
        // Analytics tab headers & stat cards
        analytics_overview: "數據總覽",
        stat_total_users: "總帳號數",
        stat_total_logins: "總登入次數",
        stat_total_tokens: "總消耗 Tokens",
        chart_dept_usage: "各系所 Token 用量",
        chart_tool_usage: "工具使用佔比",
        btn_export_chart: "匯出圖表",
        filter_dept: "學系",
        opt_dept_all: "全校",
        // Config tab
        config_coming_soon: "系統設定介面正在重新設計中",
        config_coming_soon_desc: "後續將以個別輸入框方式對各設定值進行受控修改，取代直接編輯原始設定檔。",
        // Status & Role badges
        label_online: "線上",
        label_offline: "離線",
        role_admin: "管理員",
        role_teacher: "教師",
        role_student: "學生",
        status_public: "公開",
        status_private: "私有",
        label_auto_refresh: "自動重新整理",
        // Model select options
        opt_model_api: "API 模型（雲端）",
        opt_model_local: "本地模型",
        opt_provider_openai: "OpenAI",
        opt_provider_anthropic: "Anthropic (Claude)",
        opt_provider_google: "Google (Gemini)",
        opt_provider_ollama: "Ollama（本地 API）",
        opt_provider_other: "其他",
        opt_visibility_private: "私有",
        opt_visibility_public: "公開",
        // Placeholders
        placeholder_search_users: "搜尋使用者...（密碼已加密）",
        placeholder_batch_token: "例如 5000000",
        placeholder_model_name: "模型名稱",
        placeholder_model_desc: "描述",
        placeholder_model_endpoint: "API Endpoint（例如 https://api.openai.com/v1）",
        placeholder_model_id: "上游模型 ID（例如 gpt-4o, claude-3.5-sonnet）",
        placeholder_model_framework: "框架（例如 PyTorch, TensorFlow, ONNX）",
        placeholder_model_storage: "儲存路徑",
        placeholder_dept: "學系（選填）",
        add_test_custom_password: "密碼（留空自動產生）",
        // Modals
        view_user_title: "檢視使用者",
        // Empty states
        msg_no_jobs: "無任務",
        msg_no_api_models: "無 API 模型",
        msg_no_local_models: "無本地模型",
        // Cluster
        cluster_label_temp: "溫度",
        cluster_label_util: "使用率",
        cluster_label_memory: "記憶體",
        // Chart labels
        chart_label_total_tokens: "Tokens 用量",
        chart_label_tokens: "Tokens",
        // Tool type display names
        tool_chat: "對話",
        tool_video_gen: "影片生成",
        tool_writing: "文字生成",
        // Toast / error messages
        toast_edit_unlocked: "編輯模式已解鎖",
        error_loading_analytics: "載入分析資料出錯",
        error_priority_range: "優先級必須為 0~5",
        error_session_expired: "工作階段已過期，請重新登入"
    },
    en: {
        btn_back_hub: "Back to Hub",
        admin_dashboard: "Admin Dashboard",
        admin_cluster_status: "Cluster Hardware Status",
        admin_users: "User Management",
        admin_models: "Models",
        btn_add_model: "Add Model",
        btn_edit_model: "Edit",
        btn_delete_model: "Delete",
        edit_model_title: "Edit Model",
        confirm_delete_model: "Are you sure you want to delete model {name}?",
        toast_model_created: "Model created",
        toast_model_updated: "Model updated",
        toast_model_deleted: "Model deleted",
        toast_model_failed: "Model operation failed",
        th_description: "Description",
        th_storage_path: "Storage Path",
        admin_jobs: "All Jobs",
        tab_api_models: "API Models",
        tab_local_models: "Local Models",
        tab_management: "Management",
        tab_analytics: "Analytics",
        admin_configs: "System Configs",
        tab_high_compute: "High Compute",
        tab_midlow_compute: "Mid/Low Compute",
        filter_all: "All",
        filter_pending: "Pending",
        filter_running: "Running",
        filter_completed: "Completed",
        filter_failed: "Failed",
        filter_cancelled: "Cancelled",
        btn_cancel_job: "Cancel Job",
        btn_reprioritize: "Reprioritize",
        confirm_cancel_job: "Are you sure you want to cancel job {name}?",
        prompt_new_priority: "Enter new priority (0~5):",
        toast_job_cancelled: "Job cancelled",
        toast_job_priority_updated: "Priority updated",
        toast_job_action_failed: "Action failed",
        th_progress: "Progress",
        msg_loading: "Loading...",
        toast_refresh: "Refreshed Admin Data",
        btn_logout: "Logout",
        toast_login_failed: "Login failed. Check credentials or permissions.",
        admin_login_title: "Admin Login",
        admin_username: "Administrator Username",
        admin_password: "Administrator Password",
        btn_login: "Login",
        select_config: "Select config file",
        btn_load_config: "Load",
        placeholder_config_editor: "Select and load a config file first...",
        btn_save_config: "Save Changes",
        th_username: "Username",
        th_email: "Email",
        th_role: "Role",
        th_status: "Status",
        th_last_ip: "Last IP",
        th_last_login: "Last Login",
        th_created_at: "Created At",
        th_tokens: "Tokens",
        th_name: "Name",
        th_framework: "Framework",
        th_public: "Public",
        th_job: "Job",
        th_user: "User",
        th_priority: "Priority",
        no_cluster_data: "No cluster data available",
        th_actions: "Actions",
        btn_edit: "Edit",
        edit_user_title: "Edit User",
        edit_new_password: "New Password (leave blank to keep)",
        edit_tokens_limit: "Token Monthly Limit",
        edit_tokens_used: "Used",
        status_active: "Active",
        status_disabled: "Disabled",
        toast_user_updated: "User updated successfully",
        toast_user_update_failed: "Update failed",
        batch_token_label: "Batch set all users' token limit:",
        btn_batch_apply: "Apply to All",
        toast_batch_updated: "Updated {count} users' token limit",
        btn_reset_all_usage: "Reset All Usage",
        confirm_reset_all_usage: "Reset token usage to 0 for ALL users? This cannot be undone.",
        toast_batch_reset: "Reset usage for {count} users",
        btn_reset_usage: "Reset Usage",
        toast_user_usage_reset: "User usage reset to 0",
        btn_reset: "Initialize",
        confirm_reset_user: "Are you sure to initialize user {name}?\nPassword will be reset, usage will be cleared.",
        toast_user_reset: "Account initialized",
        btn_add_test: "Provision User",
        add_test_title: "Provision User",
        btn_add_test_submit: "Create Account",
        add_test_temp_password: "Temporary Password (shown once):",
        toast_add_test_ok: "Test account created",
        toast_add_test_fail: "Creation failed",
        danger_zone: "Danger Zone",
        placeholder_admin_pwd: "Enter your admin password to confirm",
        btn_delete_user: "Delete Account",
        btn_confirm_delete: "Confirm Delete",
        btn_cancel: "Cancel",
        toast_delete_pwd_required: "Admin password required",
        confirm_delete_user: "Are you sure you want to permanently delete this account?",
        toast_user_deleted: "Account deleted",
        th_department: "Department",
        btn_analytics: "Analytics",
        analytics_title: "User Analytics",
        ua_monthly_tokens: "Monthly Tokens",
        ua_lifetime_tokens: "Lifetime Tokens",
        ua_login_count: "Total Logins",
        ua_sessions: "Chat Sessions",
        ua_tool_breakdown: "Tool Breakdown",
        ua_top_sessions: "Top 10 Sessions (by Token Cost)",
        ua_session_id: "Session ID",
        ua_started_at: "Started At",
        ua_messages: "Messages",
        ua_tokens: "Tokens",
        toast_analytics_failed: "Failed to load analytics",
        // Analytics tab headers & stat cards
        analytics_overview: "Data Overview",
        stat_total_users: "Total Accounts",
        stat_total_logins: "Total Logins",
        stat_total_tokens: "Total Tokens Used",
        chart_dept_usage: "Token Usage by Department",
        chart_tool_usage: "Tool Usage Distribution",
        btn_export_chart: "Export Charts",
        filter_dept: "Department",
        opt_dept_all: "All Schools",
        // Config tab
        config_coming_soon: "System settings UI is being redesigned",
        config_coming_soon_desc: "Settings will be configurable via typed inputs instead of direct file editing.",
        // Status & Role badges
        label_online: "Online",
        label_offline: "Offline",
        role_admin: "Admin",
        role_teacher: "Teacher",
        role_student: "Student",
        status_public: "Public",
        status_private: "Private",
        label_auto_refresh: "Auto Refresh",
        // Model select options
        opt_model_api: "API Model (Cloud)",
        opt_model_local: "Local Model",
        opt_provider_openai: "OpenAI",
        opt_provider_anthropic: "Anthropic (Claude)",
        opt_provider_google: "Google (Gemini)",
        opt_provider_ollama: "Ollama (Local API)",
        opt_provider_other: "Other",
        opt_visibility_private: "Private",
        opt_visibility_public: "Public",
        // Placeholders
        placeholder_search_users: "Search users... (Passwords are encrypted)",
        placeholder_batch_token: "e.g. 5000000",
        placeholder_model_name: "Model Name",
        placeholder_model_desc: "Description",
        placeholder_model_endpoint: "API Endpoint (e.g. https://api.openai.com/v1)",
        placeholder_model_id: "Model ID (e.g. gpt-4o, claude-3.5-sonnet)",
        placeholder_model_framework: "Framework (e.g. PyTorch, TensorFlow, ONNX)",
        placeholder_model_storage: "Storage Path",
        placeholder_dept: "Department (Optional)",
        add_test_custom_password: "Password (Leave blank to auto-generate)",
        // Modals
        view_user_title: "View User",
        // Empty states
        msg_no_jobs: "No jobs",
        msg_no_api_models: "No API models",
        msg_no_local_models: "No local models",
        // Cluster
        cluster_label_temp: "Temperature",
        cluster_label_util: "Utilization",
        cluster_label_memory: "Memory",
        // Chart labels
        chart_label_total_tokens: "Token Usage",
        chart_label_tokens: "Tokens",
        // Tool type display names
        tool_chat: "Chat",
        tool_video_gen: "Video Gen",
        tool_writing: "Writing",
        // Toast / error messages
        toast_edit_unlocked: "Edit mode unlocked",
        error_loading_analytics: "Error loading analytics data",
        error_priority_range: "Priority must be 0~5",
        error_session_expired: "Session expired. Please log in again."
    }
};

let currentLang = localStorage.getItem('ai_hud_lang') || 'zh';
let currentTheme = localStorage.getItem('ai_hud_theme') || 'dark';

function applyTranslations() {
    const t = TRANSLATIONS[currentLang] || {};

    // data-i18n: sets textContent on non-inputs, placeholder on inputs/textareas
    document.querySelectorAll('[data-i18n]').forEach(el => {
        const text = t[el.getAttribute('data-i18n')];
        if (!text) return;
        if (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA') {
            el.placeholder = text;
        } else {
            el.textContent = text;
        }
    });

    // data-i18n-placeholder: sets only the placeholder (for inputs that carry data-i18n for other purposes)
    document.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
        const text = t[el.getAttribute('data-i18n-placeholder')];
        if (text) el.placeholder = text;
    });
}

function applyTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    const themeIcon = theme === 'dark' ? 'moon-outline' : 'sunny-outline';
    document.querySelectorAll('.toggle-theme-btn ion-icon').forEach(icon => {
        icon.setAttribute('name', themeIcon);
    });
}

function showToast(msg, isError = false) {
    const toast = document.getElementById('toast');
    const msgEl = document.getElementById('toast-msg');
    const iconEl = document.getElementById('toast-icon');
    msgEl.textContent = msg;
    iconEl.innerHTML = isError ? '<ion-icon name="alert-circle-outline"></ion-icon>' : '<ion-icon name="checkmark-circle-outline"></ion-icon>';
    toast.className = `toast ${isError ? 'error' : ''} show`;
    setTimeout(() => { toast.classList.add('hidden'); }, 3000);
}

// ==========================================
// ZH: 認證錯誤處理 | EN: Auth error handler
// ==========================================
function handleAuthError() {
    authToken = null;
    localStorage.removeItem('admin_hud_token');
    document.getElementById('admin-main-layout').style.display = 'none';
    document.getElementById('admin-login-modal').style.display = 'flex';
    showToast(TRANSLATIONS[currentLang]?.error_session_expired || 'Session expired. Please log in again.', true);
}

// ==========================================
// ZH: 數據分析邏輯 | EN: Analytics Logic
// ==========================================
let deptChartInstance = null;
let toolChartInstance = null;

function switchAdminMainTab(tabId) {
    document.querySelectorAll('.model-tabs button[id^="nav-tab-"]').forEach(btn => btn.classList.remove('active'));
    document.getElementById('nav-tab-' + tabId).classList.add('active');

    document.querySelectorAll('.admin-tab-content').forEach(content => {
        content.style.display = 'none';
        content.classList.remove('active');
    });
    
    const target = document.getElementById('tab-' + tabId);
    if (target) {
        target.style.display = 'block';
        target.classList.add('active');
        
        if (tabId === 'analytics') {
            fetchAnalyticsData();
        }
    }
}

async function fetchAnalyticsData() {
    const dept = document.getElementById('analytics-dept-filter').value || 'all';
    try {
        const res = await fetch(`${API_BASE}/admin/analytics?department=${dept}`, {
            headers: { 'Authorization': `Bearer ${authToken}` }
        });
        if (res.status === 401) {
            handleAuthError();
            return;
        }
        if (!res.ok) throw new Error('Failed to fetch analytics data');
        
        const data = await res.json();
        renderAnalyticsUI(data);
    } catch (e) {
        console.error(e);
        showToast(TRANSLATIONS[currentLang]?.error_loading_analytics || 'Error loading analytics data', true);
    }
}

function renderAnalyticsUI(data) {
    // 1. Render Stats
    let totalUsers = 0, totalLogins = 0, totalTokens = 0;
    
    // Check if we need to populate department filter (only once when 'all' is selected and options are few)
    const select = document.getElementById('analytics-dept-filter');
    if (data.department_filter === 'all' && select.options.length === 1) {
        data.department_stats.forEach(stat => {
            if (stat.department && stat.department !== 'Unknown') {
                const opt = document.createElement('option');
                opt.value = stat.department;
                opt.textContent = stat.department;
                select.appendChild(opt);
            }
        });
    }

    data.department_stats.forEach(s => {
        totalUsers += s.user_count;
        totalLogins += s.total_logins;
        totalTokens += s.total_tokens;
    });

    document.getElementById('stat-total-users').textContent = totalUsers.toLocaleString();
    document.getElementById('stat-total-logins').textContent = totalLogins.toLocaleString();
    document.getElementById('stat-total-tokens').textContent = totalTokens.toLocaleString();

    // 2. Render Dept Usage Chart (Bar)
    const deptLabels = data.department_stats.map(s => s.department || 'Unknown');
    const deptTokens = data.department_stats.map(s => s.total_tokens);
    const deptCtx = document.getElementById('deptUsageChart').getContext('2d');
    
    if (deptChartInstance) {
        deptChartInstance.destroy();
    }
    
    deptChartInstance = new Chart(deptCtx, {
        type: 'bar',
        data: {
            labels: deptLabels,
            datasets: [{
                label: TRANSLATIONS[currentLang]?.chart_label_total_tokens || 'Token Usage',
                data: deptTokens,
                backgroundColor: 'rgba(56, 189, 248, 0.7)',
                borderColor: 'rgba(56, 189, 248, 1)',
                borderWidth: 1,
                borderRadius: 4
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { labels: { color: getComputedStyle(document.body).getPropertyValue('--text-primary') || '#888' } }
            },
            scales: {
                x: { ticks: { color: getComputedStyle(document.body).getPropertyValue('--text-primary') || '#888' }, grid: { color: 'rgba(128,128,128,0.2)' } },
                y: { ticks: { color: getComputedStyle(document.body).getPropertyValue('--text-primary') || '#888' }, grid: { color: 'rgba(128,128,128,0.2)' }, beginAtZero: true }
            }
        }
    });

    // 3. Render Tool Usage Chart (Pie)
    const toolLabels = data.tools_breakdown.map(t => {
        const tr = t.tool_type;
        const tl = TRANSLATIONS[currentLang] || {};
        return tr === 'chat' ? (tl.tool_chat || 'Chat')
             : tr === 'video_gen' ? (tl.tool_video_gen || 'Video Gen')
             : tr === 'writing' ? (tl.tool_writing || 'Writing')
             : tr;
    });
    const toolCounts = data.tools_breakdown.map(t => t.usage_count);
    const toolCtx = document.getElementById('toolUsageChart').getContext('2d');
    
    if (toolChartInstance) {
        toolChartInstance.destroy();
    }
    
    toolChartInstance = new Chart(toolCtx, {
        type: 'pie',
        data: {
            labels: toolLabels,
            datasets: [{
                data: toolCounts,
                backgroundColor: [
                    'rgba(244, 114, 182, 0.8)', // pink
                    'rgba(56, 189, 248, 0.8)',  // blue
                    'rgba(250, 204, 21, 0.8)',  // yellow
                    'rgba(167, 139, 250, 0.8)'  // purple
                ],
                borderWidth: 1,
                borderColor: '#1e293b'
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { position: 'right', labels: { color: getComputedStyle(document.body).getPropertyValue('--text-primary') || '#888' } }
            }
        }
    });
}

function exportAnalyticsCharts() {
    if (!deptChartInstance && !toolChartInstance) return;
    
    const downloadCanvas = (chart, filename) => {
        if (!chart) return;
        const link = document.createElement('a');
        link.download = filename;
        link.href = chart.toBase64Image();
        link.click();
    };

    downloadCanvas(deptChartInstance, 'department_usage.png');
    setTimeout(() => {
        downloadCanvas(toolChartInstance, 'tool_usage.png');
    }, 500);
}

// ==========================================
// ZH: 個人數據分析 Modal | EN: Per-user Analytics Modal
// ==========================================
let _uaChartInstance = null;
// ZH: 快取最後一次載入的數據，供語言切換時重繪圖表使用
// EN: Cache last-loaded data so charts can be re-rendered on language toggle
let _lastUaData = null;

async function openUserAnalytics(userId) {
    const modal = document.getElementById('user-analytics-modal');
    modal.classList.remove('hidden');

    // ZH: 清空舊資料，顯示載入中 | EN: Reset stale data, show loading state
    ['ua-username', 'ua-email', 'ua-role', 'ua-department',
     'ua-tokens-pct', 'ua-tokens-detail', 'ua-lifetime-tokens',
     'ua-login-count', 'ua-sessions-count'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.textContent = '…';
    });
    const bar = document.getElementById('ua-tokens-bar');
    if (bar) { bar.style.width = '0%'; bar.className = 'progress-bar-fill'; }
    const sessBody = document.getElementById('ua-sessions-body');
    if (sessBody) sessBody.innerHTML = '';

    if (_uaChartInstance) { _uaChartInstance.destroy(); _uaChartInstance = null; }

    try {
        const res = await fetch(`${API_BASE}/admin/users/${userId}/analytics`, {
            headers: { 'Authorization': `Bearer ${authToken}` }
        });
        if (res.status === 401) { handleAuthError(); return; }
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        renderUserAnalyticsModal(data);
        applyTranslations();
    } catch (err) {
        console.error('openUserAnalytics:', err);
        showToast(TRANSLATIONS[currentLang]?.toast_analytics_failed || 'Failed to load analytics', true);
        closeUserAnalytics();
    }
}

function closeUserAnalytics() {
    document.getElementById('user-analytics-modal').classList.add('hidden');
    if (_uaChartInstance) { _uaChartInstance.destroy(); _uaChartInstance = null; }
    _lastUaData = null;
}

function renderUserAnalyticsModal(data) {
    _lastUaData = data; // ZH: 快取資料供語言切換時重繪 | EN: cache for language-toggle re-render
    const u   = data.user        || {};
    const q   = data.token_quota || {};

    // ZH: 基本資訊（XSS 安全：使用 textContent）| EN: Basic info (XSS-safe via textContent)
    document.getElementById('ua-username').textContent   = u.username   || '—';
    document.getElementById('ua-email').textContent      = u.email      || '—';
    document.getElementById('ua-role').textContent       = u.role       || '—';
    document.getElementById('ua-department').textContent = u.department || '—';

    // ZH: 本月 Token 配額 | EN: Monthly token quota
    const pct = q.usage_pct || 0;
    const fillClass = pct >= 90 ? 'fill-danger' : pct >= 70 ? 'fill-warning' : '';
    document.getElementById('ua-tokens-pct').textContent    = pct + '%';
    document.getElementById('ua-tokens-detail').textContent =
        `${(q.tokens_used || 0).toLocaleString()} / ${(q.tokens_limit || 0).toLocaleString()}`;
    const bar = document.getElementById('ua-tokens-bar');
    bar.className  = `progress-bar-fill${fillClass ? ' ' + fillClass : ''}`;
    bar.style.width = Math.min(pct, 100) + '%';

    // ZH: 其餘統計數字 | EN: Other stat numbers
    document.getElementById('ua-lifetime-tokens').textContent =
        (u.lifetime_tokens_used || 0).toLocaleString();
    document.getElementById('ua-login-count').textContent =
        (u.login_count || 0).toLocaleString();
    document.getElementById('ua-sessions-count').textContent =
        (data.total_sessions || 0).toLocaleString();

    // ZH: 工具使用分布長條圖 | EN: Tool breakdown bar chart
    const breakdown = data.tool_breakdown || [];
    const toolLabels = breakdown.map(t => t.tool_type || 'unknown');
    const toolTokens = breakdown.map(t => t.tokens_sum || 0);

    if (_uaChartInstance) { _uaChartInstance.destroy(); _uaChartInstance = null; }
    const textColor = getComputedStyle(document.documentElement)
        .getPropertyValue('--text-primary').trim() || '#ccc';
    _uaChartInstance = new Chart(
        document.getElementById('ua-tool-chart').getContext('2d'),
        {
            type: 'bar',
            data: {
                labels: toolLabels,
                datasets: [{
                    label: TRANSLATIONS[currentLang]?.chart_label_tokens || 'Tokens',
                    data: toolTokens,
                    backgroundColor: 'rgba(56, 189, 248, 0.7)',
                    borderColor:     'rgba(56, 189, 248, 1)',
                    borderWidth: 1,
                    borderRadius: 4,
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false }
                },
                scales: {
                    x: { ticks: { color: textColor }, grid: { color: 'rgba(128,128,128,0.2)' } },
                    y: { ticks: { color: textColor }, grid: { color: 'rgba(128,128,128,0.2)' }, beginAtZero: true }
                }
            }
        }
    );

    // ZH: Top-10 Sessions 表格（XSS 安全：使用 textContent）
    // EN: Top-10 sessions table (XSS-safe via textContent)
    const tbody = document.getElementById('ua-sessions-body');
    tbody.innerHTML = '';
    const sessions = data.top_sessions || [];
    if (sessions.length === 0) {
        const tr = document.createElement('tr');
        const td = document.createElement('td');
        td.colSpan = 4;
        td.style.textAlign = 'center';
        td.style.color = 'var(--text-muted)';
        td.style.padding = '20px';
        td.textContent = '—';
        tr.appendChild(td);
        tbody.appendChild(tr);
        return;
    }
    sessions.forEach(s => {
        const tr = document.createElement('tr');

        const sidTd = document.createElement('td');
        sidTd.style.fontFamily = 'monospace';
        sidTd.style.fontSize   = '12px';
        sidTd.textContent = (s.session_id || '').substring(0, 8);

        const timeTd = document.createElement('td');
        timeTd.textContent = s.started_at
            ? new Date(s.started_at).toLocaleString()
            : 'N/A';

        const msgTd = document.createElement('td');
        msgTd.textContent = s.message_count || 0;

        const tokTd = document.createElement('td');
        tokTd.textContent = (s.tokens_sum || 0).toLocaleString();

        tr.appendChild(sidTd);
        tr.appendChild(timeTd);
        tr.appendChild(msgTd);
        tr.appendChild(tokTd);
        tbody.appendChild(tr);
    });
}

// 獨立的 Admin Login 流程
async function handleAdminLogin(e) {
    e.preventDefault();
    const username = document.getElementById('admin-username').value;
    const password = document.getElementById('admin-password').value;
    const formData = new URLSearchParams();
    formData.append('username', username);
    formData.append('password', password);

    try {
        const res = await fetch(`${API_BASE}/auth/login`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
            body: formData
        });
        
        if (!res.ok) throw new Error('Login failed');
        
        const data = await res.json();
        
        // 驗證是否為 admin
        const meRes = await fetch(`${API_BASE}/auth/me`, {
            headers: { 'Authorization': `Bearer ${data.access_token}` }
        });
        const user = await meRes.json();
        if (user.role !== 'admin') {
            throw new Error('Not an admin');
        }

        // 登入成功
        authToken = data.access_token;
        localStorage.setItem('admin_hud_token', authToken);
        
        document.getElementById('admin-login-modal').style.display = 'none';
        document.getElementById('admin-main-layout').style.display = 'flex';
        
        initAdminDashboard();
    } catch (err) {
        console.error(err);
        showToast(TRANSLATIONS[currentLang].toast_login_failed, true);
    }
}

// 啟動驗證
async function verifyAdmin() {
    if (!authToken) {
        document.getElementById('admin-login-modal').style.display = 'flex';
        return;
    }

    try {
        const res = await fetch(`${API_BASE}/auth/me`, {
            headers: { 'Authorization': `Bearer ${authToken}` }
        });
        if (!res.ok) throw new Error('Token invalid');
        const user = await res.json();
        if (user.role !== 'admin') {
            throw new Error('Not an admin');
        }
        
        // Token 有效，顯示主畫面
        document.getElementById('admin-login-modal').style.display = 'none';
        document.getElementById('admin-main-layout').style.display = 'flex';
        initAdminDashboard();
    } catch (err) {
        console.error(err);
        localStorage.removeItem('admin_hud_token');
        document.getElementById('admin-login-modal').style.display = 'flex';
    }
}

// -------------------------
// Cluster Stats (New)
// -------------------------
async function fetchClusterStats() {
    try {
        const res = await fetch(`${API_BASE}/admin/cluster/stats`, {
            headers: { 'Authorization': `Bearer ${authToken}` }
        });
        if (res.ok) {
            const stats = await res.json();
            renderClusterStats(stats);
        }
    } catch (e) {
        console.error("Failed to fetch cluster stats:", e);
    }
}

function renderClusterStats(stats) {
    const container = document.getElementById('cluster-stats-container');
    if (!stats || stats.length === 0) {
        const noDataMsg = TRANSLATIONS[currentLang]?.no_cluster_data || 'No cluster data available';
        container.innerHTML = `<div data-i18n="no_cluster_data" style="padding: 20px; text-align: center; color: var(--text-muted);">${noDataMsg}</div>`;
        return;
    }

    container.innerHTML = '';
    stats.forEach(gpu => {
        const tempClass = gpu.temperature > 80 ? 'fill-danger' : (gpu.temperature > 65 ? 'fill-warning' : '');
        const utilClass = gpu.utilization > 90 ? 'fill-danger' : (gpu.utilization > 75 ? 'fill-warning' : '');
        
        const memPercent = gpu.memory_total > 0 ? (gpu.memory_used / gpu.memory_total) * 100 : 0;
        const memClass = memPercent > 90 ? 'fill-danger' : (memPercent > 75 ? 'fill-warning' : '');

        const card = document.createElement('div');
        card.className = 'stat-card';
        const tl = TRANSLATIONS[currentLang] || {};
        const lTemp   = tl.cluster_label_temp   || 'Temperature';
        const lUtil   = tl.cluster_label_util   || 'Utilization';
        const lMemory = tl.cluster_label_memory || 'Memory';

        card.innerHTML = `
            <h4>
                <span style="display:flex; align-items:center; gap:8px;">
                    <ion-icon name="hardware-chip-outline"></ion-icon> ${gpu.name}
                </span>
                <span style="font-size: 0.8em; color: rgba(255,255,255,0.5); font-weight:normal;">ID: ${gpu.gpu_id} | Node: ${gpu.node_id}</span>
            </h4>

            <div>
                <div class="stat-row"><span>${lTemp}</span><span>${gpu.temperature} °C</span></div>
                <div class="progress-bar-bg"><div class="progress-bar-fill ${tempClass}" style="width: ${Math.min(gpu.temperature, 100)}%;"></div></div>
            </div>

            <div>
                <div class="stat-row"><span>${lUtil}</span><span>${gpu.utilization} %</span></div>
                <div class="progress-bar-bg"><div class="progress-bar-fill ${utilClass}" style="width: ${gpu.utilization}%;"></div></div>
            </div>

            <div>
                <div class="stat-row"><span>${lMemory}</span><span>${gpu.memory_used} / ${gpu.memory_total} MB</span></div>
                <div class="progress-bar-bg"><div class="progress-bar-fill ${memClass}" style="width: ${memPercent}%;"></div></div>
            </div>
        `;
        container.appendChild(card);
    });
}

// -------------------------
// Admin Table Fetching
// -------------------------
async function fetchAdminData() {
    try {
        const [usersRes, jobsRes, modelsRes] = await Promise.all([
            fetch(`${API_BASE}/admin/users`, { headers: { 'Authorization': `Bearer ${authToken}` } }),
            fetch(`${API_BASE}/admin/jobs`, { headers: { 'Authorization': `Bearer ${authToken}` } }),
            fetch(`${API_BASE}/admin/models`, { headers: { 'Authorization': `Bearer ${authToken}` } })
        ]);

        if (usersRes.ok) renderAdminUsers(await usersRes.json());
        if (jobsRes.ok) renderAdminJobs(await jobsRes.json());
        if (modelsRes.ok) renderAdminModels(await modelsRes.json());
    } catch (e) {
        console.error("Failed to fetch admin data", e);
    }
}

let _adminUsersCache = [];

function renderAdminUsers(users) {
    try {
        if (users) _adminUsersCache = users;
        const tbody = document.getElementById('admin-users-body');
        if (!tbody) return;
        
        // Apply search filter
        const searchInput = document.getElementById('admin-user-search');
        const query = searchInput ? searchInput.value.toLowerCase() : '';
        
        const filteredUsers = _adminUsersCache.filter(u => {
            if (!query) return true;
            return (u.username && u.username.toLowerCase().includes(query)) ||
                   (u.email && u.email.toLowerCase().includes(query)) ||
                   (u.role && u.role.toLowerCase().includes(query));
        });
        
        tbody.innerHTML = '';
        filteredUsers.forEach(u => {
            const tr = document.createElement('tr');
            const tl = TRANSLATIONS[currentLang] || {};
            const loginStr = u.last_login_time ? new Date(u.last_login_time).toLocaleString() : 'N/A';
            const createdStr = u.created_at ? new Date(u.created_at).toLocaleString() : 'N/A';
            const roleLabel = tl[`role_${u.role}`] || u.role;
            const roleStr = u.role === 'admin'
                ? `<span class="status-badge running">${roleLabel}</span>`
                : `<span class="status-badge completed">${roleLabel}</span>`;
            const activeLabel   = tl.status_active   || 'Active';
            const disabledLabel = tl.status_disabled  || 'Disabled';
            const statusStr = u.is_active
                ? `<span style="color:var(--neon-green)">${activeLabel}</span>`
                : `<span style="color:var(--neon-pink)">${disabledLabel}</span>`;

            // Online status indicator: red=disabled, green=online, gray=offline
            const lblOnline   = tl.label_online   || 'Online';
            const lblOffline  = tl.label_offline  || 'Offline';
            const lblDisabled = tl.status_disabled || 'Disabled';
            let onlineDot;
            if (!u.is_active) {
                onlineDot = `<span style="display:inline-block; width:8px; height:8px; border-radius:50%; background:#ef4444; margin-right:6px; box-shadow:0 0 5px #ef4444;" title="${lblDisabled}"></span>`;
            } else if (u.online_status === 1) {
                onlineDot = `<span style="display:inline-block; width:8px; height:8px; border-radius:50%; background:#10b981; margin-right:6px; box-shadow:0 0 5px #10b981;" title="${lblOnline}"></span>`;
            } else {
                onlineDot = `<span style="display:inline-block; width:8px; height:8px; border-radius:50%; background:#6b7280; margin-right:6px;" title="${lblOffline}"></span>`;
            }
            
            // Token display
            let tokensStr = 'N/A';
            if (u.tokens_limit > 0) {
                const pct = Math.round((u.tokens_used / u.tokens_limit) * 100);
                tokensStr = `<span title="${u.tokens_used} / ${u.tokens_limit}">${pct}%</span>`;
            }

            tr.innerHTML = `
                <td>
                    <div style="display:flex; align-items:center;">
                        ${onlineDot}<span>${u.username}</span>
                    </div>
                </td>
                <td>${u.email}</td>
                <td>${u.department || 'N/A'}</td>
                <td>${roleStr}</td>
                <td>${statusStr}</td>
                <td>${u.last_login_ip || 'N/A'}</td>
                <td>${loginStr}</td>
                <td>${createdStr}</td>
                <td>${tokensStr}</td>
                <td>
                        <div style="display:flex; gap:4px; flex-wrap:wrap;">
                            <button class="ready-btn" style="width:auto; padding:4px 12px; margin:0; font-size:12px; min-width:auto;" onclick="openEditUser('${u.id}')" data-i18n="btn_edit">${TRANSLATIONS[currentLang]?.btn_edit || 'Edit'}</button>
                            <button class="ready-btn" style="width:auto; padding:4px 12px; margin:0; font-size:12px; min-width:auto; border-color:#a78bfa; color:#a78bfa; background:rgba(167,139,250,0.08);" onclick="openUserAnalytics('${u.id}')" data-i18n="btn_analytics">${TRANSLATIONS[currentLang]?.btn_analytics || 'Analytics'}</button>
                            <button class="ready-btn" style="width:auto; padding:4px 12px; margin:0; font-size:12px; min-width:auto; border-color:#f59e0b; color:#f59e0b;" onclick="resetUser('${u.id}', '${u.username}')" data-i18n="btn_reset">${TRANSLATIONS[currentLang]?.btn_reset || 'Initialize'}</button>
                        </div>
                    </td>
            `;
            tbody.appendChild(tr);
        });
    } catch(e) {
        fetch(`${API_BASE}/health?error=` + encodeURIComponent(e.message + " | " + e.stack));
        console.error(e);
    }
}

async function resetUser(userId, username) {
    const msg = (TRANSLATIONS[currentLang]?.confirm_reset_user || 'Initialize user {name}?').replace('{name}', username);
    if (!confirm(msg)) return;

    try {
        // Reset password to random + clear token usage
        const res = await fetch(`${API_BASE}/admin/users/${userId}/reset`, {
            method: 'POST',
            headers: { 'Authorization': `Bearer ${authToken}` }
        });
        if (!res.ok) throw new Error('Reset failed');
        const data = await res.json();
        
        // Show the new temp password
        alert((TRANSLATIONS[currentLang]?.add_test_temp_password || 'Temporary Password:') + '\n\n' + data.temp_password);
        
        showToast(TRANSLATIONS[currentLang]?.toast_user_reset || 'Account initialized');
        fetchAdminData();
    } catch (err) {
        console.error(err);
        showToast(TRANSLATIONS[currentLang]?.toast_user_update_failed || 'Failed', true);
    }
}

let _adminJobsCache = [];
let _activeJobTab = 'high';

function renderAdminJobs(jobs) {
    if (jobs) _adminJobsCache = jobs;

    const statusFilter = document.getElementById('admin-jobs-status-filter');
    const filterVal = statusFilter ? statusFilter.value : 'all';

    let filtered = _adminJobsCache;
    if (filterVal !== 'all') {
        filtered = _adminJobsCache.filter(j => j.status === filterVal);
    }

    const highJobs = filtered.filter(j => j.priority >= 2);
    const midlowJobs = filtered.filter(j => j.priority < 2);

    _renderJobTable('admin-jobs-high-body', highJobs);
    _renderJobTable('admin-jobs-midlow-body', midlowJobs);

    // Update tab counts
    const tabHigh = document.getElementById('tab-high-compute');
    const tabMidlow = document.getElementById('tab-midlow-compute');
    if (tabHigh) {
        let countEl = tabHigh.querySelector('.tab-count');
        if (!countEl) { countEl = document.createElement('span'); countEl.className = 'tab-count'; tabHigh.appendChild(countEl); }
        countEl.textContent = highJobs.length;
    }
    if (tabMidlow) {
        let countEl = tabMidlow.querySelector('.tab-count');
        if (!countEl) { countEl = document.createElement('span'); countEl.className = 'tab-count'; tabMidlow.appendChild(countEl); }
        countEl.textContent = midlowJobs.length;
    }
}

function _renderJobTable(tbodyId, jobs) {
    const tbody = document.getElementById(tbodyId);
    if (!tbody) return;
    tbody.innerHTML = '';
    const tl = TRANSLATIONS[currentLang] || {};
    if (jobs.length === 0) {
        const tr = document.createElement('tr');
        tr.innerHTML = `<td colspan="6" style="text-align:center; color:var(--text-muted); padding:20px;">${tl.msg_no_jobs || 'No jobs'}</td>`;
        tbody.appendChild(tr);
        return;
    }
    const statusLabels = {
        pending:   tl.filter_pending   || 'Pending',
        running:   tl.filter_running   || 'Running',
        completed: tl.filter_completed || 'Completed',
        failed:    tl.filter_failed    || 'Failed',
        cancelled: tl.filter_cancelled || 'Cancelled',
    };
    jobs.forEach(j => {
        const tr = document.createElement('tr');
        const sLabel = statusLabels[j.status] || j.status;
        let statusBadge = `<span class="status-badge pending">${sLabel}</span>`;
        if (j.status === 'running')   statusBadge = `<span class="status-badge running">${sLabel}</span>`;
        if (j.status === 'completed') statusBadge = `<span class="status-badge completed">${sLabel}</span>`;
        if (j.status === 'failed')    statusBadge = `<span class="status-badge failed">${sLabel}</span>`;
        if (j.status === 'cancelled') statusBadge = `<span class="status-badge" style="border-color:#6b7280; color:#6b7280;">${sLabel}</span>`;

        const progress = j.progress || 0;
        const progressBar = `<div class="job-progress-bar"><div class="job-progress-bar-fill" style="width:${progress}%;"></div></div><small style="color:var(--text-muted);">${Math.round(progress)}%</small>`;

        const canManage = (j.status === 'pending' || j.status === 'queued');
        const cancelLabel = TRANSLATIONS[currentLang]?.btn_cancel_job || 'Cancel';
        const prioLabel = TRANSLATIONS[currentLang]?.btn_reprioritize || 'Reprioritize';
        const actionsHtml = canManage ? `
            <div style="display:flex; gap:4px; flex-wrap:wrap;">
                <button class="job-action-btn priority-btn" onclick="reprioritizeJob('${j.id}', '${j.job_name}')">${prioLabel}</button>
                <button class="job-action-btn cancel-btn" onclick="cancelJobAdmin('${j.id}', '${j.job_name}')">${cancelLabel}</button>
            </div>` : `<span style="color:var(--text-muted); font-size:12px;">—</span>`;

        tr.innerHTML = `
            <td>${j.job_name}<br><small style="color:var(--text-muted)">${j.id.substring(0, 8)}</small></td>
            <td>${j.user_id ? j.user_id.substring(0, 8) : 'N/A'}</td>
            <td>${statusBadge}</td>
            <td>${j.priority}</td>
            <td>${progressBar}</td>
            <td>${actionsHtml}</td>
        `;
        tbody.appendChild(tr);
    });
}

function switchJobTab(tab) {
    _activeJobTab = tab;
    const tabHigh = document.getElementById('tab-high-compute');
    const tabMidlow = document.getElementById('tab-midlow-compute');
    const panelHigh = document.getElementById('admin-jobs-high-panel');
    const panelMidlow = document.getElementById('admin-jobs-midlow-panel');

    if (tab === 'high') {
        tabHigh.classList.add('active');
        tabMidlow.classList.remove('active');
        panelHigh.style.display = '';
        panelMidlow.style.display = 'none';
    } else {
        tabHigh.classList.remove('active');
        tabMidlow.classList.add('active');
        panelHigh.style.display = 'none';
        panelMidlow.style.display = '';
    }
}

function filterAdminJobs() {
    renderAdminJobs(); // Re-render with existing cache
}

async function cancelJobAdmin(jobId, jobName) {
    const msg = (TRANSLATIONS[currentLang]?.confirm_cancel_job || 'Cancel job {name}?').replace('{name}', jobName);
    if (!confirm(msg)) return;

    try {
        const res = await fetch(`${API_BASE}/admin/jobs/${jobId}/cancel`, {
            method: 'POST',
            headers: { 'Authorization': `Bearer ${authToken}` }
        });
        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.detail || 'Cancel failed');
        }
        showToast(TRANSLATIONS[currentLang]?.toast_job_cancelled || 'Job cancelled');
        fetchAdminData();
    } catch (err) {
        console.error(err);
        showToast((TRANSLATIONS[currentLang]?.toast_job_action_failed || 'Action failed') + ': ' + err.message, true);
    }
}

async function reprioritizeJob(jobId, jobName) {
    const input = prompt((TRANSLATIONS[currentLang]?.prompt_new_priority || 'Enter new priority (0~5):'));
    if (input === null) return;
    const newPriority = parseInt(input);
    if (isNaN(newPriority) || newPriority < 0 || newPriority > 5) {
        showToast(TRANSLATIONS[currentLang]?.error_priority_range || 'Priority must be 0~5', true);
        return;
    }

    try {
        const res = await fetch(`${API_BASE}/admin/jobs/${jobId}/priority`, {
            method: 'PUT',
            headers: {
                'Authorization': `Bearer ${authToken}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ priority: newPriority })
        });
        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.detail || 'Update failed');
        }
        showToast(TRANSLATIONS[currentLang]?.toast_job_priority_updated || 'Priority updated');
        fetchAdminData();
    } catch (err) {
        console.error(err);
        showToast((TRANSLATIONS[currentLang]?.toast_job_action_failed || 'Action failed') + ': ' + err.message, true);
    }
}

let _adminModelsCache = [];
let _activeModelTab = 'api';

function renderAdminModels(models) {
    if (models) _adminModelsCache = models;

    const apiModels = _adminModelsCache.filter(m => (m.model_type || 'local') === 'api');
    const localModels = _adminModelsCache.filter(m => (m.model_type || 'local') === 'local');

    _renderApiModelTable('admin-models-api-body', apiModels);
    _renderLocalModelTable('admin-models-local-body', localModels);

    // Update tab counts
    const tabApi = document.getElementById('tab-api-models');
    const tabLocal = document.getElementById('tab-local-models');
    if (tabApi) {
        let c = tabApi.querySelector('.tab-count');
        if (!c) { c = document.createElement('span'); c.className = 'tab-count'; tabApi.appendChild(c); }
        c.textContent = apiModels.length;
    }
    if (tabLocal) {
        let c = tabLocal.querySelector('.tab-count');
        if (!c) { c = document.createElement('span'); c.className = 'tab-count'; tabLocal.appendChild(c); }
        c.textContent = localModels.length;
    }
}

function _renderApiModelTable(tbodyId, models) {
    const tbody = document.getElementById(tbodyId);
    if (!tbody) return;
    tbody.innerHTML = '';
    const tl = TRANSLATIONS[currentLang] || {};
    if (models.length === 0) {
        tbody.innerHTML = `<tr><td colspan="6" style="text-align:center; color:var(--text-muted); padding:20px;">${tl.msg_no_api_models || 'No API models'}</td></tr>`;
        return;
    }
    const editLabel   = tl.btn_edit_model   || 'Edit';
    const deleteLabel = tl.btn_delete_model || 'Delete';
    const lblPublic   = tl.status_public    || 'Public';
    const lblPrivate  = tl.status_private   || 'Private';
    models.forEach(m => {
        const tr = document.createElement('tr');
        const publicBadge = m.is_public
            ? `<span class="status-badge completed">${lblPublic}</span>`
            : `<span class="status-badge pending">${lblPrivate}</span>`;
        const providerBadge = `<span class="status-badge running">${m.api_provider || 'N/A'}</span>`;
        tr.innerHTML = `
            <td><strong>${m.name}</strong><br><small style="color:var(--text-muted)">${m.id ? m.id.substring(0, 8) : ''}</small></td>
            <td>${providerBadge}</td>
            <td style="font-family:monospace; font-size:12px;">${m.api_model_id || 'N/A'}</td>
            <td style="max-width:180px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;" title="${m.description || ''}">${m.description || '\u2014'}</td>
            <td>${publicBadge}</td>
            <td>
                <div style="display:flex; gap:4px;">
                    <button class="job-action-btn priority-btn" onclick="openModelModal('${m.id}')">${editLabel}</button>
                    <button class="job-action-btn cancel-btn" onclick="deleteModel('${m.id}', '${m.name.replace(/'/g, "\\'")}')">${deleteLabel}</button>
                </div>
            </td>
        `;
        tbody.appendChild(tr);
    });
}

function _renderLocalModelTable(tbodyId, models) {
    const tbody = document.getElementById(tbodyId);
    if (!tbody) return;
    tbody.innerHTML = '';
    const tl = TRANSLATIONS[currentLang] || {};
    if (models.length === 0) {
        tbody.innerHTML = `<tr><td colspan="6" style="text-align:center; color:var(--text-muted); padding:20px;">${tl.msg_no_local_models || 'No local models'}</td></tr>`;
        return;
    }
    const editLabel   = tl.btn_edit_model   || 'Edit';
    const deleteLabel = tl.btn_delete_model || 'Delete';
    const lblPublic   = tl.status_public    || 'Public';
    const lblPrivate  = tl.status_private   || 'Private';
    models.forEach(m => {
        const tr = document.createElement('tr');
        const publicBadge = m.is_public
            ? `<span class="status-badge completed">${lblPublic}</span>`
            : `<span class="status-badge pending">${lblPrivate}</span>`;
        tr.innerHTML = `
            <td><strong>${m.name}</strong><br><small style="color:var(--text-muted)">${m.id ? m.id.substring(0, 8) : ''}</small></td>
            <td>${m.framework || 'N/A'}</td>
            <td style="max-width:180px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;" title="${m.description || ''}">${m.description || '\u2014'}</td>
            <td style="max-width:160px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;" title="${m.storage_path || ''}">${m.storage_path || 'N/A'}</td>
            <td>${publicBadge}</td>
            <td>
                <div style="display:flex; gap:4px;">
                    <button class="job-action-btn priority-btn" onclick="openModelModal('${m.id}')">${editLabel}</button>
                    <button class="job-action-btn cancel-btn" onclick="deleteModel('${m.id}', '${m.name.replace(/'/g, "\\'")}')">${deleteLabel}</button>
                </div>
            </td>
        `;
        tbody.appendChild(tr);
    });
}

function switchModelTab(tab) {
    _activeModelTab = tab;
    const tabApi = document.getElementById('tab-api-models');
    const tabLocal = document.getElementById('tab-local-models');
    const panelApi = document.getElementById('admin-models-api-panel');
    const panelLocal = document.getElementById('admin-models-local-panel');

    if (tab === 'api') {
        tabApi.classList.add('active');
        tabLocal.classList.remove('active');
        panelApi.style.display = '';
        panelLocal.style.display = 'none';
    } else {
        tabApi.classList.remove('active');
        tabLocal.classList.add('active');
        panelApi.style.display = 'none';
        panelLocal.style.display = '';
    }
}

function toggleModelTypeFields() {
    const type = document.getElementById('model-type').value;
    document.getElementById('model-api-fields').style.display = (type === 'api') ? '' : 'none';
    document.getElementById('model-local-fields').style.display = (type === 'local') ? '' : 'none';
}

function openModelModal(modelId) {
    const modal = document.getElementById('model-modal');
    const title = document.getElementById('model-modal-title');
    // Reset all fields
    document.getElementById('model-edit-id').value = '';
    document.getElementById('model-type').value = _activeModelTab || 'api';
    document.getElementById('model-name').value = '';
    document.getElementById('model-description').value = '';
    document.getElementById('model-framework').value = '';
    document.getElementById('model-storage-path').value = '';
    document.getElementById('model-api-provider').value = 'openai';
    document.getElementById('model-api-endpoint').value = '';
    document.getElementById('model-api-model-id').value = '';
    document.getElementById('model-is-public').value = '0';

    if (modelId) {
        const m = _adminModelsCache.find(x => x.id === modelId);
        if (m) {
            document.getElementById('model-edit-id').value = m.id;
            document.getElementById('model-type').value = m.model_type || 'local';
            document.getElementById('model-name').value = m.name || '';
            document.getElementById('model-description').value = m.description || '';
            document.getElementById('model-framework').value = m.framework || '';
            document.getElementById('model-storage-path').value = m.storage_path || '';
            document.getElementById('model-api-provider').value = m.api_provider || 'openai';
            document.getElementById('model-api-endpoint').value = m.api_endpoint || '';
            document.getElementById('model-api-model-id').value = m.api_model_id || '';
            document.getElementById('model-is-public').value = m.is_public ? '1' : '0';
        }
        title.textContent = TRANSLATIONS[currentLang]?.edit_model_title || 'Edit Model';
    } else {
        title.textContent = TRANSLATIONS[currentLang]?.btn_add_model || 'Add Model';
    }
    toggleModelTypeFields();
    modal.classList.remove('hidden');
}

function closeModelModal() {
    document.getElementById('model-modal').classList.add('hidden');
}

async function submitModelForm(e) {
    e.preventDefault();
    const editId = document.getElementById('model-edit-id').value;
    const modelType = document.getElementById('model-type').value;
    const payload = {
        name: document.getElementById('model-name').value,
        model_type: modelType,
        description: document.getElementById('model-description').value || null,
        is_public: parseInt(document.getElementById('model-is-public').value)
    };

    if (modelType === 'api') {
        payload.api_provider = document.getElementById('model-api-provider').value || null;
        payload.api_endpoint = document.getElementById('model-api-endpoint').value || null;
        payload.api_model_id = document.getElementById('model-api-model-id').value || null;
        payload.storage_path = '';
    } else {
        payload.framework = document.getElementById('model-framework').value || null;
        payload.storage_path = document.getElementById('model-storage-path').value || '';
    }

    try {
        let res;
        if (editId) {
            res = await fetch(`${API_BASE}/admin/models/${editId}`, {
                method: 'PUT',
                headers: { 'Authorization': `Bearer ${authToken}`, 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
        } else {
            res = await fetch(`${API_BASE}/admin/models`, {
                method: 'POST',
                headers: { 'Authorization': `Bearer ${authToken}`, 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
        }
        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.detail || 'Failed');
        }
        showToast(editId ? (TRANSLATIONS[currentLang]?.toast_model_updated || 'Model updated') : (TRANSLATIONS[currentLang]?.toast_model_created || 'Model created'));
        closeModelModal();
        fetchAdminData();
    } catch (err) {
        console.error(err);
        showToast((TRANSLATIONS[currentLang]?.toast_model_failed || 'Model operation failed') + ': ' + err.message, true);
    }
}

async function deleteModel(modelId, modelName) {
    const msg = (TRANSLATIONS[currentLang]?.confirm_delete_model || 'Delete model {name}?').replace('{name}', modelName);
    if (!confirm(msg)) return;

    try {
        const res = await fetch(`${API_BASE}/admin/models/${modelId}`, {
            method: 'DELETE',
            headers: { 'Authorization': `Bearer ${authToken}` }
        });
        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.detail || 'Delete failed');
        }
        showToast(TRANSLATIONS[currentLang]?.toast_model_deleted || 'Model deleted');
        fetchAdminData();
    } catch (err) {
        console.error(err);
        showToast((TRANSLATIONS[currentLang]?.toast_model_failed || 'Failed') + ': ' + err.message, true);
    }
}

// -------------------------
// Initialization
// -------------------------
let _adminRefreshInterval = null;

function initAdminDashboard() {
    fetchClusterStats();
    fetchAdminData();
    applyTranslations();

    // Auto refresh logic
    if (_adminRefreshInterval) clearInterval(_adminRefreshInterval);
    _adminRefreshInterval = setInterval(() => {
        const autoCheckbox = document.getElementById('auto-refresh-users');
        if (autoCheckbox && autoCheckbox.checked) {
            fetchAdminData();
            fetchClusterStats();
        }
    }, 5000);

    const refreshBtn = document.getElementById('refresh-admin-btn');
    if (refreshBtn) {
        // 防止重複綁定
        const newBtn = refreshBtn.cloneNode(true);
        refreshBtn.parentNode.replaceChild(newBtn, refreshBtn);
        newBtn.addEventListener('click', () => {
            fetchClusterStats();
            fetchAdminData();
            showToast(TRANSLATIONS[currentLang].toast_refresh);
        });
    }

    // Setup Logout Button
    const logoutBtn = document.getElementById('admin-logout-btn');
    if (logoutBtn) {
        logoutBtn.addEventListener('click', () => {
            localStorage.removeItem('admin_hud_token');
            window.location.reload();
        });
    }

    // Polling for cluster stats every 5 seconds
    if (!window.statsInterval) {
        window.statsInterval = setInterval(fetchClusterStats, 5000);
    }
}

// -------------------------
// User Edit Modal
// -------------------------
function openEditUser(userId) {
    const userData = _adminUsersCache.find(u => u.id === userId);
    if (!userData) return;
    document.getElementById('edit-user-id').value = userId;
    document.getElementById('edit-username').value = userData.username;
    document.getElementById('edit-email').value = userData.email;
    document.getElementById('edit-department').value = userData.department || '';
    document.getElementById('edit-password').value = '';
    document.getElementById('edit-role').value = userData.role;
    document.getElementById('edit-active').value = userData.is_active;
    document.getElementById('edit-tokens-limit').value = userData.tokens_limit || 5000000;
    document.getElementById('edit-tokens-used-display').textContent = (userData.tokens_used || 0).toLocaleString();
    
    // Reset to View Mode
    document.getElementById('edit-email').disabled = true;
    document.getElementById('edit-department').disabled = true;
    document.getElementById('edit-role').disabled = true;
    document.getElementById('edit-active').disabled = true;
    document.getElementById('edit-tokens-limit').disabled = true;
    document.getElementById('edit-dept-container').style.display = 'none';
    document.getElementById('edit-pwd-container').style.display = 'none';
    document.getElementById('btn-unlock-edit').style.display = 'block';
    document.getElementById('btn-save-edit').style.display = 'none';
    
    const modal = document.getElementById('user-edit-modal');
    modal.classList.remove('hidden');
    applyTranslations();
}

function closeEditUser() {
    document.getElementById('user-edit-modal').classList.add('hidden');
}

async function saveEditUser(e) {
    e.preventDefault();
    const userId = document.getElementById('edit-user-id').value;
    const payload = {
        email: document.getElementById('edit-email').value || null,
        department: document.getElementById('edit-department').value || null,
        role: document.getElementById('edit-role').value,
        is_active: parseInt(document.getElementById('edit-active').value),
        tokens_limit: parseInt(document.getElementById('edit-tokens-limit').value) || null
    };
    const pwd = document.getElementById('edit-password').value;
    if (pwd && pwd.trim()) {
        payload.password = pwd;
    }

    try {
        const res = await fetch(`${API_BASE}/admin/users/${userId}`, {
            method: 'PUT',
            headers: {
                'Authorization': `Bearer ${authToken}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(payload)
        });
        if (!res.ok) throw new Error('Update failed');
        
        showToast(TRANSLATIONS[currentLang]?.toast_user_updated || 'User updated');
        closeEditUser();
        fetchAdminData(); // Refresh table
    } catch (err) {
        console.error(err);
        showToast(TRANSLATIONS[currentLang]?.toast_user_update_failed || 'Update failed', true);
    }
}

async function unlockEdit() {
    const adminPwd = prompt(TRANSLATIONS[currentLang]?.placeholder_admin_pwd || 'Enter your admin password to confirm');
    
    if (adminPwd === null) return; // cancelled
    if (!adminPwd) {
        showToast(TRANSLATIONS[currentLang]?.toast_delete_pwd_required || 'Admin password required', true);
        return;
    }

    try {
        const payload = { admin_password: adminPwd };
        const res = await fetch(`${API_BASE}/admin/verify`, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${authToken}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(payload)
        });
        
        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.detail || 'Verification failed');
        }
        
        // Unlock the form fields
        document.getElementById('edit-email').disabled = false;
        document.getElementById('edit-department').disabled = false;
        document.getElementById('edit-role').disabled = false;
        document.getElementById('edit-active').disabled = false;
        document.getElementById('edit-tokens-limit').disabled = false;
        document.getElementById('edit-dept-container').style.display = 'block';
        document.getElementById('edit-pwd-container').style.display = 'block';
        
        // Swap buttons
        document.getElementById('btn-unlock-edit').style.display = 'none';
        document.getElementById('btn-save-edit').style.display = 'block';
        
        showToast(TRANSLATIONS[currentLang]?.toast_edit_unlocked || 'Edit mode unlocked');
    } catch (err) {
        console.error(err);
        showToast(err.message, true);
    }
}

async function deleteUserFromModal() {
    const userId = document.getElementById('edit-user-id').value;
    
    // ZH: 先詢問是否確定要刪除 | EN: Confirm deletion first
    if (!confirm(TRANSLATIONS[currentLang]?.confirm_delete_user || 'Are you sure you want to permanently delete this account?')) {
        return;
    }

    // ZH: 跳出密碼驗證視窗 | EN: Pop up password verification window
    const adminPwd = prompt(TRANSLATIONS[currentLang]?.placeholder_admin_pwd || 'Enter your admin password to confirm');
    
    if (adminPwd === null) {
        // ZH: 使用者點擊取消 | EN: User clicked cancel
        return;
    }

    if (!adminPwd) {
        showToast(TRANSLATIONS[currentLang]?.toast_delete_pwd_required || 'Admin password required', true);
        return;
    }

    try {
        const payload = { admin_password: adminPwd };
        const res = await fetch(`${API_BASE}/admin/users/${userId}/delete`, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${authToken}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(payload)
        });
        
        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.detail || 'Delete failed');
        }
        
        showToast(TRANSLATIONS[currentLang]?.toast_user_deleted || 'Account deleted');
        closeEditUser();
        fetchAdminData();
    } catch (err) {
        console.error(err);
        showToast(err.message, true);
    }
}

async function batchUpdateTokens() {
    const limitInput = document.getElementById('batch-token-limit');
    const newLimit = parseInt(limitInput.value);
    if (!newLimit || newLimit <= 0) return;

    const userIds = _adminUsersCache.map(u => u.id);
    if (userIds.length === 0) return;

    try {
        const res = await fetch(`${API_BASE}/admin/users/batch/tokens`, {
            method: 'PUT',
            headers: {
                'Authorization': `Bearer ${authToken}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ user_ids: userIds, action: 'set_limit', value: newLimit })
        });
        if (!res.ok) throw new Error('Batch update failed');
        const data = await res.json();
        const msg = (TRANSLATIONS[currentLang]?.toast_batch_updated || 'Updated {count} users').replace('{count}', data.updated_count);
        showToast(msg);
        fetchAdminData();
    } catch (err) {
        console.error(err);
        showToast(TRANSLATIONS[currentLang]?.toast_user_update_failed || 'Update failed', true);
    }
}

async function batchResetUsage() {
    const msg = TRANSLATIONS[currentLang]?.confirm_reset_all_usage || 'Reset token usage for ALL users?';
    if (!confirm(msg)) return;

    const userIds = _adminUsersCache.map(u => u.id);
    if (userIds.length === 0) return;

    try {
        const res = await fetch(`${API_BASE}/admin/users/batch/tokens`, {
            method: 'PUT',
            headers: {
                'Authorization': `Bearer ${authToken}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ user_ids: userIds, action: 'reset_usage', value: 0 })
        });
        if (!res.ok) throw new Error('Batch reset failed');
        const data = await res.json();
        const msg2 = (TRANSLATIONS[currentLang]?.toast_batch_reset || 'Reset usage for {count} users').replace('{count}', data.updated_count);
        showToast(msg2);
        fetchAdminData();
    } catch (err) {
        console.error(err);
        showToast(TRANSLATIONS[currentLang]?.toast_user_update_failed || 'Operation failed', true);
    }
}

async function resetUserUsage(userId) {
    try {
        const res = await fetch(`${API_BASE}/admin/users/batch/tokens`, {
            method: 'PUT',
            headers: {
                'Authorization': `Bearer ${authToken}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ user_ids: [userId], action: 'reset_usage', value: 0 })
        });
        if (!res.ok) throw new Error('Reset failed');
        showToast(TRANSLATIONS[currentLang]?.toast_user_usage_reset || 'User usage reset');
        // Update the displayed used count in the open modal
        document.getElementById('edit-tokens-used-display').textContent = '0';
        fetchAdminData();
    } catch (err) {
        console.error(err);
        showToast(TRANSLATIONS[currentLang]?.toast_user_update_failed || 'Reset failed', true);
    }
}

// -------------------------
// Provision User Modal
// -------------------------
function openProvision() {
    document.getElementById('provision-username').value = '';
    document.getElementById('provision-email').value = '';
    document.getElementById('provision-department').value = '';
    document.getElementById('provision-password').value = '';
    document.getElementById('provision-role').value = 'student';
    document.getElementById('provision-result').classList.add('hidden');
    document.getElementById('provision-modal').classList.remove('hidden');
    applyTranslations();
}

function closeProvision() {
    document.getElementById('provision-modal').classList.add('hidden');
}

async function submitProvision(e) {
    e.preventDefault();
    const payload = {
        username: document.getElementById('provision-username').value,
        email: document.getElementById('provision-email').value,
        department: document.getElementById('provision-department').value || null,
        role: document.getElementById('provision-role').value
    };
    const pw = document.getElementById('provision-password').value;
    if (pw) {
        payload.password = pw;
    }

    try {
        const res = await fetch(`${API_BASE}/admin/users/provision`, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${authToken}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(payload)
        });
        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.detail || 'Failed');
        }
        const data = await res.json();
        
        // Show temp password
        document.getElementById('provision-temp-pw').textContent = data.temp_password;
        document.getElementById('provision-result').classList.remove('hidden');
        
        showToast(TRANSLATIONS[currentLang]?.toast_add_test_ok || 'Test account created');
        fetchAdminData();
    } catch (err) {
        console.error(err);
        showToast((TRANSLATIONS[currentLang]?.toast_add_test_fail || 'Failed') + ': ' + err.message, true);
    }
}

document.addEventListener('DOMContentLoaded', () => {
    const loginForm = document.getElementById('admin-login-form');
    if (loginForm) {
        loginForm.addEventListener('submit', handleAdminLogin);
    }
    const eyeToggle = document.getElementById('admin-eye-toggle');
    if (eyeToggle) {
        eyeToggle.addEventListener('click', () => {
            const pwdInput = document.getElementById('admin-password');
            const eyeOff = eyeToggle.querySelector('.eye-off');
            const eyeOpen = eyeToggle.querySelector('.eye-open');
            if (pwdInput.type === 'password') {
                pwdInput.type = 'text';
                eyeOff.style.display = 'none';
                eyeOpen.style.display = 'inline-block';
            } else {
                pwdInput.type = 'password';
                eyeOff.style.display = 'inline-block';
                eyeOpen.style.display = 'none';
            }
        });
    }

    const logoutBtn = document.getElementById('admin-logout-btn');
    if (logoutBtn) {
        logoutBtn.addEventListener('click', async () => {
            if (authToken) {
                try {
                    await fetch(`${API_BASE}/auth/logout`, {
                        method: 'POST',
                        headers: { 'Authorization': `Bearer ${authToken}` }
                    });
                } catch (e) {
                    console.error('Logout API failed', e);
                }
            }
            authToken = null;
            localStorage.removeItem('admin_hud_token');
            document.getElementById('admin-main-layout').style.display = 'none';
            document.getElementById('admin-login-modal').style.display = 'flex';
        });
    }

    // User Edit Modal Bindings
    const editForm = document.getElementById('user-edit-form');
    if (editForm) editForm.addEventListener('submit', saveEditUser);
    const editCloseBtn = document.getElementById('user-edit-close-btn');
    if (editCloseBtn) editCloseBtn.addEventListener('click', closeEditUser);
    const editBackdrop = document.getElementById('user-edit-backdrop');
    if (editBackdrop) editBackdrop.addEventListener('click', closeEditUser);
    const unlockBtn = document.getElementById('btn-unlock-edit');
    if (unlockBtn) unlockBtn.addEventListener('click', unlockEdit);
    const deleteBtn = document.getElementById('btn-delete-user');
    if (deleteBtn) deleteBtn.addEventListener('click', deleteUserFromModal);

    // Batch Token Update Binding
    const batchBtn = document.getElementById('btn-batch-tokens');
    if (batchBtn) batchBtn.addEventListener('click', batchUpdateTokens);
    const batchResetBtn = document.getElementById('btn-batch-reset-usage');
    if (batchResetBtn) batchResetBtn.addEventListener('click', batchResetUsage);
    const resetUserUsageBtn = document.getElementById('btn-reset-user-usage');
    if (resetUserUsageBtn) resetUserUsageBtn.addEventListener('click', () => {
        const userId = document.getElementById('edit-user-id').value;
        if (userId) resetUserUsage(userId);
    });

    // Provision User Modal Bindings
    const provisionBtn = document.getElementById('btn-provision-user');
    if (provisionBtn) provisionBtn.addEventListener('click', openProvision);
    const provisionForm = document.getElementById('provision-form');
    if (provisionForm) provisionForm.addEventListener('submit', submitProvision);
    const provisionCloseBtn = document.getElementById('provision-close-btn');
    if (provisionCloseBtn) provisionCloseBtn.addEventListener('click', closeProvision);
    const provisionBackdrop = document.getElementById('provision-backdrop');
    if (provisionBackdrop) provisionBackdrop.addEventListener('click', closeProvision);

    // Model Modal Bindings
    const modelBackdrop = document.getElementById('model-modal-backdrop');
    if (modelBackdrop) modelBackdrop.addEventListener('click', closeModelModal);

    // User Analytics Modal Bindings
    const uaCloseBtn = document.getElementById('ua-close-btn');
    if (uaCloseBtn) uaCloseBtn.addEventListener('click', closeUserAnalytics);
    const uaBackdrop = document.getElementById('ua-backdrop');
    if (uaBackdrop) uaBackdrop.addEventListener('click', closeUserAnalytics);

    // Refresh Button Binding
    const refreshBtn = document.getElementById('refresh-admin-btn');
    if (refreshBtn) {
        refreshBtn.addEventListener('click', () => {
            fetchAdminData();
            fetchClusterStats();
        });
    }

    // Search Bar Binding
    const searchInput = document.getElementById('admin-user-search');
    if (searchInput) {
        searchInput.addEventListener('input', () => {
            renderAdminUsers(); // Re-render with existing cache
        });
    }

    // Initialize Theme & Lang
    applyTheme(currentTheme);
    applyTranslations();

    // Theme Toggle Binding
    document.querySelectorAll('.toggle-theme-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            currentTheme = currentTheme === 'dark' ? 'light' : 'dark';
            localStorage.setItem('ai_hud_theme', currentTheme);
            applyTheme(currentTheme);
        });
    });

    // Lang Toggle Binding
    document.querySelectorAll('.toggle-lang-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            currentLang = currentLang === 'zh' ? 'en' : 'zh';
            localStorage.setItem('ai_hud_lang', currentLang);
            applyTranslations();
            // ZH: 若個人分析 Modal 正在顯示，重繪圖表使標籤套用新語系
            // EN: If the per-user analytics modal is open, re-render charts with updated labels
            const uaModal = document.getElementById('user-analytics-modal');
            if (_lastUaData && uaModal && !uaModal.classList.contains('hidden')) {
                renderUserAnalyticsModal(_lastUaData);
            }
        });
    });

    verifyAdmin();
});
