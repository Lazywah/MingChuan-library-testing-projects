const API_BASE = '/api/v1';
let authToken = localStorage.getItem('admin_hud_token');

const TRANSLATIONS = {
    zh: {
        btn_back_hub: "返回大廳 (Back to Hub)",
        admin_dashboard: "管理員儀表板",
        admin_cluster_status: "叢集資源即時監控",
        admin_users: "使用者管理",
        admin_models: "模型",
        admin_jobs: "全域任務",
        msg_loading: "載入中...",
        toast_refresh: "已重新整理管理員資料",
        btn_logout: "登出",
        toast_login_failed: "登入失敗，請檢查帳號密碼或權限"
    },
    en: {
        btn_back_hub: "Back to Hub",
        admin_dashboard: "Admin Dashboard",
        admin_cluster_status: "Cluster Hardware Status",
        admin_users: "User Management",
        admin_models: "Models",
        admin_jobs: "All Jobs",
        msg_loading: "Loading...",
        toast_refresh: "Refreshed Admin Data",
        btn_logout: "Logout",
        toast_login_failed: "Login failed. Check credentials or permissions."
    }
};

let currentLang = localStorage.getItem('ai_hud_lang') || 'zh';

function applyTranslations() {
    const els = document.querySelectorAll('[data-i18n]');
    els.forEach(el => {
        const key = el.getAttribute('data-i18n');
        if (TRANSLATIONS[currentLang] && TRANSLATIONS[currentLang][key]) {
            el.textContent = TRANSLATIONS[currentLang][key];
        }
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
        document.getElementById('admin-main-layout').style.display = 'block';
        
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
        document.getElementById('admin-main-layout').style.display = 'block';
        initAdminDashboard();
    } catch (err) {
        console.error(err);
        localStorage.removeItem('admin_hud_token');
        document.getElementById('admin-login-modal').style.display = 'flex';
    }
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
        container.innerHTML = '<div style="padding: 20px; text-align: center; color: rgba(255,255,255,0.5);">無可用叢集資料 (No cluster data available)</div>';
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

function renderAdminUsers(users) {
    const tbody = document.getElementById('admin-users-body');
    if (!tbody) return;
    tbody.innerHTML = '';
    users.forEach(u => {
        const tr = document.createElement('tr');
        const loginStr = u.last_login_time ? new Date(u.last_login_time).toLocaleString() : 'N/A';
        const roleStr = u.role === 'admin' ? '<span class="status-badge running">Admin</span>' : `<span class="status-badge completed">${u.role}</span>`;
        const statusStr = u.is_active ? '<span style="color:var(--neon-green)">Active</span>' : '<span style="color:var(--neon-pink)">Disabled</span>';
        
        // Token display
        let tokensStr = 'N/A';
        if (u.tokens_limit > 0) {
            const pct = Math.round((u.tokens_used / u.tokens_limit) * 100);
            tokensStr = `<span title="${u.tokens_used} / ${u.tokens_limit}">${pct}%</span>`;
        }

        tr.innerHTML = `
            <td>${u.username}</td>
            <td>${u.email}</td>
            <td>${roleStr}</td>
            <td>${statusStr}</td>
            <td>${u.last_login_ip || 'N/A'}</td>
            <td>${loginStr}</td>
            <td>${tokensStr}</td>
        `;
        tbody.appendChild(tr);
    });
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
            select.innerHTML = '<option value="">選擇設定檔 (Select config file)</option>';
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
function initAdminDashboard() {
    fetchClusterStats();
    fetchAdminData();
    fetchConfigList();
    applyTranslations();

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

    verifyAdmin();
});
