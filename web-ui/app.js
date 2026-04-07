// Configuration
const API_BASE = '/api/v1';
let authToken = localStorage.getItem('ai_hud_token') || null;
let pollInterval = null;

// DOM Elements
const loginView = document.getElementById('login-view');
const dashView = document.getElementById('dashboard-view');
const loginForm = document.getElementById('login-form');
const loginBtn = document.getElementById('login-btn');
const logoutBtn = document.getElementById('logout-btn');
const toastEl = document.getElementById('toast');
const toastMsg = document.getElementById('toast-msg');
const toastIcon = document.getElementById('toast-icon');

// HUD Elements
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

// Initialization
document.addEventListener('DOMContentLoaded', () => {
    if (authToken) {
        checkAuth();
    }
});

// Toast Notification System
function showToast(msg, isError = false) {
    toastMsg.textContent = msg;
    if (isError) {
        toastEl.classList.add('error');
        toastIcon.innerHTML = '<i class="fas fa-exclamation-triangle"></i>';
    } else {
        toastEl.classList.remove('error');
        toastIcon.innerHTML = '<i class="fas fa-info-circle"></i>';
    }
    toastEl.classList.remove('hidden');
    setTimeout(() => {
        toastEl.classList.add('hidden');
    }, 3000);
}

// Format Date
function formatDate(dateStr) {
    if (!dateStr) return '--';
    const d = new Date(dateStr);
    return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')} ${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}`;
}

// Authentication Flow
async function handleLogin(e) {
    e.preventDefault();
    const user = document.getElementById('username').value;
    const pass = document.getElementById('password').value;
    
    loginBtn.disabled = true;
    loginBtn.querySelector('span').textContent = 'AUTHENTICATING...';

    try {
        // FastAPI OAuth2 expects form-urlencoded
        const formData = new URLSearchParams();
        formData.append('username', user);
        formData.append('password', pass);

        const res = await fetch(`${API_BASE}/auth/login`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
            body: formData
        });

        if (!res.ok) throw new Error('Authentication Failed');
        const data = await res.json();
        
        authToken = data.access_token;
        localStorage.setItem('ai_hud_token', authToken);
        showToast('CONNECTION ESTABLISHED');
        
        await fetchDashboardData();
        switchToDashboard();
    } catch (err) {
        showToast(err.message, true);
    } finally {
        loginBtn.disabled = false;
        loginBtn.querySelector('span').textContent = 'INITIALIZE_CONNECTION()';
    }
}
loginForm.addEventListener('submit', handleLogin);

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
        if (!res.ok) throw new Error('Token expired');
        await fetchDashboardData();
        switchToDashboard();
    } catch {
        authToken = null;
        localStorage.removeItem('ai_hud_token');
        switchToLogin();
    }
}

function switchToDashboard() {
    loginView.classList.add('hidden');
    setTimeout(() => {
        dashView.classList.remove('hidden');
        // Start polling
        if(pollInterval) clearInterval(pollInterval);
        pollInterval = setInterval(fetchJobs, 5000);
    }, 400);
}
function switchToLogin() {
    dashView.classList.add('hidden');
    setTimeout(() => {
        loginView.classList.remove('hidden');
    }, 400);
}

// Data Fetching
async function fetchDashboardData() {
    await Promise.all([
        fetchUserProfile(),
        fetchTokenUsage(),
        fetchJobs()
    ]);
}

async function fetchUserProfile() {
    const res = await fetch(`${API_BASE}/auth/me`, {
        headers: { 'Authorization': `Bearer ${authToken}` }
    });
    if(res.ok) {
        const data = await res.json();
        userDisplay.textContent = data.username;
        userRole.textContent = data.role.toUpperCase();
    }
}

async function fetchTokenUsage() {
    const res = await fetch(`${API_BASE}/auth/usage`, {
        headers: { 'Authorization': `Bearer ${authToken}` }
    });
    if(res.ok) {
        const data = await res.json();
        tokenUsed.textContent = data.tokens_used.toLocaleString();
        tokenLimit.textContent = data.tokens_limit.toLocaleString();
        tokenReset.textContent = formatDate(data.reset_date);
        
        // Update Ring
        const percentage = Math.min(100, Math.max(0, data.usage_percentage * 100)).toFixed(1);
        tokenPercent.textContent = `${percentage}%`;
        
        const circle = tokenRingFill;
        const radius = circle.r.baseVal.value;
        const circumference = radius * 2 * Math.PI;
        const offset = circumference - (percentage / 100) * circumference;
        circle.style.strokeDashoffset = offset;
        
        if (percentage > 90) circle.style.stroke = 'var(--neon-red)';
        else if (percentage > 75) circle.style.stroke = '#fbbf24'; // yellow
        else circle.style.stroke = 'var(--neon-blue)';
    }
}

// Job Management
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
            headers: {
                'Authorization': `Bearer ${authToken}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(jobData)
        });
        
        if(!res.ok) {
            const err = await res.json();
            throw new Error(err.detail || 'Dispatch failed');
        }
        
        showToast('TASK_DISPATCHED_SUCCESSFULLY');
        jobForm.reset();
        await fetchDashboardData(); // update tokens and list instantly
    } catch(err) {
        showToast(err.message, true);
    } finally {
        submitJobBtn.disabled = false;
    }
});

refreshJobsBtn.addEventListener('click', () => {
    refreshJobsBtn.querySelector('i').classList.add('fa-spin');
    fetchDashboardData().finally(() => {
        setTimeout(() => refreshJobsBtn.querySelector('i').classList.remove('fa-spin'), 500);
    });
});

async function fetchJobs() {
    try {
        const res = await fetch(`${API_BASE}/jobs`, {
            headers: { 'Authorization': `Bearer ${authToken}` }
        });
        if(res.ok) {
            const data = await res.json();
            renderJobs(data.items || []);
        }
    } catch(e) {
        console.error("Job fetch error", e);
    }
}

function renderJobs(jobs) {
    if (jobs.length === 0) {
        jobListContainer.innerHTML = `
            <div class="empty-state">
                <i class="fas fa-satellite-dish"></i>
                <p>NO SIGNAL / QUEUE EMPTY</p>
            </div>
        `;
        return;
    }

    jobListContainer.innerHTML = '';
    jobs.forEach(job => {
        // Status colors
        let statusClass = `status-${job.status}`;
        let statusIcon = 'fa-clock';
        if(job.status === 'running') statusIcon = 'fa-cog fa-spin';
        if(job.status === 'completed') statusIcon = 'fa-check';
        if(job.status === 'failed') statusIcon = 'fa-times';
        
        const card = document.createElement('div');
        card.className = `job-card ${statusClass}`;
        
        const isCancellable = job.status === 'pending' || job.status === 'queued';
        const cancelBtnStr = isCancellable ? `<button class="btn-cancel" onclick="cancelJob('${job.job_id}')" title="Abort Task"><i class="fas fa-trash-alt"></i></button>` : '';

        card.innerHTML = `
            ${cancelBtnStr}
            <div class="job-head">
                <span class="job-title">${job.job_name}</span>
                <span class="job-status ${statusClass}"><i class="fas ${statusIcon}"></i> ${job.status.toUpperCase()}</span>
            </div>
            <div class="job-id">${job.job_id}</div>
            <div class="job-meta">
                <span><i class="fas fa-cube"></i> ${job.model_name}</span>
                <span><i class="fas fa-microchip"></i> ${job.gpu_server || 'WAITING'}</span>
            </div>
            <div class="job-progress-bar">
                <div class="job-progress-fill" style="width: ${job.progress || 0}%"></div>
            </div>
            <div class="job-progress-text">${(job.progress || 0).toFixed(1)}%</div>
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
        if(!res.ok) throw new Error('Abort failed');
        showToast('TASK_ABORTED');
        fetchJobs(); // Update instantly
    } catch(err) {
        showToast(err.message, true);
    }
};
