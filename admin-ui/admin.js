const API_BASE = '/api/v1';
let authToken = localStorage.getItem('admin_hud_token');

const TRANSLATIONS = {
    zh: {
        btn_back_hub: "返回大廳",
        admin_dashboard: "管理員儀表板",
        admin_cluster_status: "叢集資源即時監控",
        admin_users: "使用者管理",
        admin_models: "模型管理",
        admin_jobs: "全域任務",
        admin_configs: "系統設定檔",
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
        btn_reset: "初始化",
        confirm_reset_user: "確定要初始化使用者 {name} 的帳號嗎？\n密碼將被重置，用量將歸零。",
        toast_user_reset: "帳號已初始化",
        btn_add_test: "新增測試用帳號",
        add_test_title: "新增測試用帳號",
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
        toast_user_deleted: "帳號已刪除"
    },
    en: {
        btn_back_hub: "Back to Hub",
        admin_dashboard: "Admin Dashboard",
        admin_cluster_status: "Cluster Hardware Status",
        admin_users: "User Management",
        admin_models: "Models",
        admin_jobs: "All Jobs",
        admin_configs: "System Configs",
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
        btn_reset: "Initialize",
        confirm_reset_user: "Are you sure to initialize user {name}?\nPassword will be reset, usage will be cleared.",
        toast_user_reset: "Account initialized",
        btn_add_test: "Add Test Account",
        add_test_title: "Add Test Account",
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
        toast_user_deleted: "Account deleted"
    }
};

let currentLang = localStorage.getItem('ai_hud_lang') || 'zh';
let currentTheme = localStorage.getItem('ai_hud_theme') || 'dark';

function applyTranslations() {
    const els = document.querySelectorAll('[data-i18n]');
    els.forEach(el => {
        const key = el.getAttribute('data-i18n');
        if (TRANSLATIONS[currentLang] && TRANSLATIONS[currentLang][key]) {
            if (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA') {
                el.placeholder = TRANSLATIONS[currentLang][key];
            } else {
                el.textContent = TRANSLATIONS[currentLang][key];
            }
        }
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
    setTimeout(() => { toast.classList.remove('show'); }, 3000);
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
        card.innerHTML = `
            <h4>
                <span style="display:flex; align-items:center; gap:8px;">
                    <ion-icon name="hardware-chip-outline"></ion-icon> ${gpu.name}
                </span>
                <span style="font-size: 0.8em; color: rgba(255,255,255,0.5); font-weight:normal;">ID: ${gpu.gpu_id} | Node: ${gpu.node_id}</span>
            </h4>
            
            <div>
                <div class="stat-row"><span>溫度 (Temp)</span><span>${gpu.temperature} °C</span></div>
                <div class="progress-bar-bg"><div class="progress-bar-fill ${tempClass}" style="width: ${Math.min(gpu.temperature, 100)}%;"></div></div>
            </div>
            
            <div>
                <div class="stat-row"><span>使用率 (Utilization)</span><span>${gpu.utilization} %</span></div>
                <div class="progress-bar-bg"><div class="progress-bar-fill ${utilClass}" style="width: ${gpu.utilization}%;"></div></div>
            </div>

            <div>
                <div class="stat-row"><span>記憶體 (Memory)</span><span>${gpu.memory_used} / ${gpu.memory_total} MB</span></div>
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
            const loginStr = u.last_login_time ? new Date(u.last_login_time).toLocaleString() : 'N/A';
            const createdStr = u.created_at ? new Date(u.created_at).toLocaleString() : 'N/A';
            const roleStr = u.role === 'admin' ? '<span class="status-badge running">Admin</span>' : `<span class="status-badge completed">${u.role}</span>`;
            const statusStr = u.is_active ? '<span style="color:var(--neon-green)">Active</span>' : '<span style="color:var(--neon-pink)">Disabled</span>';
            
            // Online status indicator (within 5 mins)
            const isOnline = u.online_status === 1;
            const onlineDot = isOnline 
                ? '<span style="display:inline-block; width:8px; height:8px; border-radius:50%; background:#10b981; margin-right:6px; box-shadow:0 0 5px #10b981;" title="Online"></span>'
                : '<span style="display:inline-block; width:8px; height:8px; border-radius:50%; background:#6b7280; margin-right:6px;" title="Offline"></span>';
            
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
                <td>${roleStr}</td>
                <td>${statusStr}</td>
                <td>${u.last_login_ip || 'N/A'}</td>
                <td>${loginStr}</td>
                <td>${createdStr}</td>
                <td>${tokensStr}</td>
                <td>
                        <div style="display:flex; gap:4px;">
                            <button class="ready-btn" style="width:auto; padding:4px 12px; margin:0; font-size:12px; min-width:auto;" onclick="openEditUser('${u.id}')" data-i18n="btn_edit">${TRANSLATIONS[currentLang]?.btn_edit || 'Edit'}</button>
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

function renderAdminJobs(jobs) {
    const tbody = document.getElementById('admin-jobs-body');
    if (!tbody) return;
    tbody.innerHTML = '';
    jobs.forEach(j => {
        const tr = document.createElement('tr');
        let statusBadge = `<span class="status-badge pending">${j.status}</span>`;
        if (j.status === 'running') statusBadge = `<span class="status-badge running">${j.status}</span>`;
        if (j.status === 'completed') statusBadge = `<span class="status-badge completed">${j.status}</span>`;
        if (j.status === 'failed') statusBadge = `<span class="status-badge failed">${j.status}</span>`;
        
        tr.innerHTML = `
            <td>${j.job_name}<br><small style="color:var(--text-muted)">${j.id.split('-')[0]}</small></td>
            <td>${j.user_id}</td>
            <td>${statusBadge}</td>
            <td>${j.priority}</td>
        `;
        tbody.appendChild(tr);
    });
}

function renderAdminModels(models) {
    const tbody = document.getElementById('admin-models-body');
    if (!tbody) return;
    tbody.innerHTML = '';
    models.forEach(m => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td>${m.name}</td>
            <td>${m.framework || 'N/A'}</td>
            <td>${m.is_public ? 'Yes' : 'No'}</td>
        `;
        tbody.appendChild(tr);
    });
}

// -------------------------
// System Config Management
// -------------------------
async function fetchConfigList() {
    try {
        const res = await fetch(`${API_BASE}/system/files`, { headers: { 'Authorization': `Bearer ${authToken}` } });
        if (res.ok) {
            const data = await res.json();
            const select = document.getElementById('config-file-select');
            select.innerHTML = `<option value="" data-i18n="select_config">${TRANSLATIONS[currentLang]?.select_config || 'Select config file'}</option>`;
            data.files.forEach(f => {
                const opt = document.createElement('option');
                opt.value = f;
                opt.textContent = f;
                select.appendChild(opt);
            });
        }
    } catch (e) {
        console.error("Failed to fetch config list:", e);
    }
}

async function loadConfig() {
    const filename = document.getElementById('config-file-select').value;
    if (!filename) return showToast("請先選擇設定檔", true);
    
    try {
        const res = await fetch(`${API_BASE}/system/files/${filename}`, { headers: { 'Authorization': `Bearer ${authToken}` } });
        if (!res.ok) throw new Error("Load failed");
        const data = await res.json();
        document.getElementById('config-editor').value = data.content;
        showToast(`已載入 ${filename}`);
    } catch (e) {
        showToast("載入失敗", true);
        console.error(e);
    }
}

async function saveConfig() {
    const filename = document.getElementById('config-file-select').value;
    const content = document.getElementById('config-editor').value;
    if (!filename) return showToast("請先選擇設定檔", true);
    
    try {
        const res = await fetch(`${API_BASE}/system/files/${filename}`, {
            method: 'PUT',
            headers: { 
                'Authorization': `Bearer ${authToken}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ content })
        });
        if (!res.ok) throw new Error("Save failed");
        showToast(`已儲存 ${filename}`);
    } catch (e) {
        showToast("儲存失敗", true);
        console.error(e);
    }
}

// -------------------------
// Initialization
// -------------------------
let _adminRefreshInterval = null;

function initAdminDashboard() {
    fetchClusterStats();
    fetchAdminData();
    fetchConfigList();
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

    // Setup Config Buttons
    const btnLoad = document.getElementById('btn-load-config');
    if (btnLoad) {
        const newBtnLoad = btnLoad.cloneNode(true);
        btnLoad.parentNode.replaceChild(newBtnLoad, btnLoad);
        newBtnLoad.addEventListener('click', loadConfig);
    }
    
    const btnSave = document.getElementById('btn-save-config');
    if (btnSave) {
        const newBtnSave = btnSave.cloneNode(true);
        btnSave.parentNode.replaceChild(newBtnSave, btnSave);
        newBtnSave.addEventListener('click', saveConfig);
    }
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
    document.getElementById('edit-password').value = '';
    document.getElementById('edit-role').value = userData.role;
    document.getElementById('edit-active').value = userData.is_active;
    document.getElementById('edit-tokens-limit').value = userData.tokens_limit || 5000000;
    document.getElementById('edit-tokens-used-display').textContent = (userData.tokens_used || 0).toLocaleString();
    
    // Reset to View Mode
    document.getElementById('edit-email').disabled = true;
    document.getElementById('edit-role').disabled = true;
    document.getElementById('edit-active').disabled = true;
    document.getElementById('edit-tokens-limit').disabled = true;
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
        document.getElementById('edit-role').disabled = false;
        document.getElementById('edit-active').disabled = false;
        document.getElementById('edit-tokens-limit').disabled = false;
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

    try {
        const res = await fetch(`${API_BASE}/admin/users/batch/tokens?new_limit=${newLimit}`, {
            method: 'PUT',
            headers: { 'Authorization': `Bearer ${authToken}` }
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

// -------------------------
// Provision User Modal
// -------------------------
function openProvision() {
    document.getElementById('provision-username').value = '';
    document.getElementById('provision-email').value = '';
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
        role: document.getElementById('provision-role').value
    };

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

    // Provision User Modal Bindings
    const provisionBtn = document.getElementById('btn-provision-user');
    if (provisionBtn) provisionBtn.addEventListener('click', openProvision);
    const provisionForm = document.getElementById('provision-form');
    if (provisionForm) provisionForm.addEventListener('submit', submitProvision);
    const provisionCloseBtn = document.getElementById('provision-close-btn');
    if (provisionCloseBtn) provisionCloseBtn.addEventListener('click', closeProvision);
    const provisionBackdrop = document.getElementById('provision-backdrop');
    if (provisionBackdrop) provisionBackdrop.addEventListener('click', closeProvision);

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
        });
    });

    verifyAdmin();
});
