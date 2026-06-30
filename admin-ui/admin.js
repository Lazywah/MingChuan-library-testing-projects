const API_BASE = '/api/v1';
let authToken = localStorage.getItem('admin_hud_token');

const TRANSLATIONS = {
    zh: {
        btn_back_hub: "返回大廳",
        admin_dashboard: "管理員儀表板",
        admin_cluster_status: "叢集資源即時監控",
        admin_users: "使用者管理",
        auth_tab_local: "本機帳號",
        auth_tab_oidc: "學校 SSO",
        auth_tab_mock: "Mock SSO",
        label_na: "不適用",
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
        tab_external_ai: "外部 AI",
        ext_admin_url_title: "外部 AI 平台網址",
        ext_admin_url_hint: "留空 = 未啟用，使用者端顯示「即將開放」；填入後非 admin 使用者點「AI 助手」會被導向此網址。",
        ext_admin_add_title: "新增單筆對應",
        ext_admin_csv_title: "CSV 批次匯入造冊結果",
        ext_admin_csv_hint: "每行格式：platform_username,vendor_username（可含表頭，重複者更新）。",
        ext_admin_list_title: "帳號對應表",
        myai_sync_title: "廠商 Token 同步（myai168）",
        myai_sync_now: "立即同步",
        myai_sync_hint: "以管理者帳密（.env）headless 登入 myai168 → 匯出使用者清單 → 顯示每人 Token 點數。唯讀，不回寫廠商。",
        myai_col_sn: "編號",
        myai_col_type: "身分",
        myai_col_name: "名稱",
        myai_col_points: "Token 點數",
        myai_col_expiry: "有效期間",
        admin_col_email: "電子郵件",
        myai_bind_title: "Email 綁定管理",
        myai_bind_automatch: "一鍵 Email 配對",
        myai_bind_hint: "以 email 對應「平台使用者 ↔ myai 帳號」。一鍵配對會把 email 相同且尚未綁定者自動建立綁定（只寫本平台、不碰廠商）。",
        myai_bind_user: "平台帳號",
        myai_bind_email: "myai Email",
        myai_bind_unmatched_users: "未綁定的平台使用者",
        myai_bind_unmatched_myai: "未配對的 myai 帳號",
        myai_bind_match: "可配對",
        col_actions: "操作",
        ext_col_platform: "平台帳號",
        ext_col_vendor: "廠商帳號",
        ext_ai_logout_label: "廠商登出網址（共用機台換手用）",
        btn_save: "儲存",
        btn_add: "新增",
        btn_import: "匯入",
        label_font_size: "字體大小",
        admin_guide: "管理導覽",
        guide_prev: "上一步",
        guide_next: "下一步",
        guide_done: "完成",
        // 管理者引導式教學（原使用者介面 Unit 6 移入；改為左側 Side Bar 分頁導覽）
        tut_u6_s1_title: "👤 歡迎使用管理中心",
        tut_u6_s1_body: "管理員專用介面在 port 8888（學生 UI 在 :80）。左側 Side Bar 三個分頁涵蓋全部管理功能。接下來逐一介紹。",
        tut_u6_s2_title: "Step 2 — 管理介面分頁",
        tut_u6_s2_body: "叢集 GPU 即時監控、使用者管理（線上狀態 / Token 用量 / Provision / 停用 / 重設密碼）、模型與運算任務、公告，以及「📊 匯出」Excel/CSV 都在這。",
        tut_u6_s3_title: "Step 3 — 數據分析分頁",
        tut_u6_s3_body: "依系所 / 工具檢視 Token 使用與活躍度圖表，掌握全校使用概況。",
        tut_u6_s4_title: "Step 4 — Lab 管理分頁",
        tut_u6_s4_body: "監控與管理使用者的 Lab 容器、每日配額、儲存空間與操作稽核紀錄。",
        tut_u6_s5_title: "🎉 個人化 & 完成",
        tut_u6_s5_body: "Side Bar 底部可調整字體大小、切換主題 / 語言，並隨時重看本導覽。更多功能見 docs/04-operations.md，記得開學前換強 admin 密碼。",
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
        // v2.2: Announcements
        admin_announcements: "公告管理",
        btn_new_announcement: "新增公告",
        th_pinned: "置頂",
        th_title: "標題",
        th_posted_at: "發布時間",
        th_visible: "顯示",
        placeholder_announcement_title: "公告標題（最多 200 字）",
        placeholder_announcement_body: "公告內容（支援多行）",
        label_pinned: "置頂顯示",
        label_visible: "公開可見",
        announcement_new_title: "新增公告",
        announcement_edit_title: "編輯公告",
        // v2.2: Export users modal
        btn_export_users: "匯出 Excel / CSV",
        btn_export_confirm: "匯出",
        btn_cancel: "取消",
        export_title: "匯出使用者資料",
        export_scope_label: "範圍：",
        export_scope_filter: "目前篩選結果（依 3-tab 與搜尋）",
        export_scope_all: "全部使用者",
        export_columns_label: "要包含的欄位：",
        export_select_all: "全選",
        export_select_none: "全不選",
        export_format_label: "格式：",
        export_format_xlsx: "Excel (.xlsx)",
        export_format_csv: "CSV (UTF-8 BOM)",
        export_no_columns: "請至少勾選一個欄位",
        export_success: "匯出完成",
        export_failed: "匯出失敗：",
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
        analytics_overview: "數據總覽（外部 AI / myai）",
        stat_total_users: "廠商帳號數",
        stat_total_logins: "總剩餘點數",
        stat_total_tokens: "平均點數/帳號",
        chart_dept_usage: "點數 Top 10 帳號",
        chart_tool_usage: "帳號狀態分佈",
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
        label_tool_types: "適用工具",
        tool_chat: "文字聊天",
        tool_presentation: "文書簡報",
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
        auth_tab_local: "Local Accounts",
        auth_tab_oidc: "School SSO",
        auth_tab_mock: "Mock SSO",
        label_na: "N/A",
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
        tab_external_ai: "External AI",
        ext_admin_url_title: "External AI Platform URL",
        ext_admin_url_hint: "Empty = disabled (users see \"coming soon\"); once set, non-admin users clicking \"AI Assistant\" are redirected here.",
        ext_admin_add_title: "Add Single Mapping",
        ext_admin_csv_title: "Bulk Import (CSV)",
        ext_admin_csv_hint: "Per line: platform_username,vendor_username (header allowed; existing rows updated).",
        ext_admin_list_title: "Account Mapping Table",
        myai_sync_title: "Vendor Token Sync (myai168)",
        myai_sync_now: "Sync now",
        myai_sync_hint: "Headless-login to myai168 with admin creds (.env) → export users → show each user's token points. Read-only.",
        myai_col_sn: "ID",
        myai_col_type: "Role",
        myai_col_name: "Name",
        myai_col_points: "Token Points",
        myai_col_expiry: "Expiry",
        admin_col_email: "Email",
        myai_bind_title: "Email Binding",
        myai_bind_automatch: "Auto-match by Email",
        myai_bind_hint: "Map platform users to myai accounts by email. Auto-match binds same-email users that aren't bound yet (writes our DB only; never touches the vendor).",
        myai_bind_user: "Platform Account",
        myai_bind_email: "myai Email",
        myai_bind_unmatched_users: "Unbound platform users",
        myai_bind_unmatched_myai: "Unmatched myai accounts",
        myai_bind_match: "Matchable",
        col_actions: "Actions",
        ext_col_platform: "Platform Account",
        ext_col_vendor: "Vendor Account",
        ext_ai_logout_label: "Vendor logout URL (for shared-machine handoff)",
        btn_save: "Save",
        btn_add: "Add",
        btn_import: "Import",
        label_font_size: "Font Size",
        admin_guide: "Admin Guide",
        guide_prev: "Back",
        guide_next: "Next",
        guide_done: "Done",
        // Admin guided tutorial (moved from user-UI Unit 6; now a Side Bar tab tour)
        tut_u6_s1_title: "👤 Welcome to the Admin Center",
        tut_u6_s1_body: "The admin-only interface runs on port 8888 (student UI is on :80). The three Side Bar tabs on the left cover every admin function. Let's walk through them.",
        tut_u6_s2_title: "Step 2 — Management tab",
        tut_u6_s2_body: "Real-time GPU cluster monitoring, user management (online status / token usage / provision / disable / reset password), models, compute jobs, announcements, and the \"📊 Export\" Excel/CSV button all live here.",
        tut_u6_s3_title: "Step 3 — Analytics tab",
        tut_u6_s3_body: "Token usage and activity charts by department / tool — see the whole campus usage at a glance.",
        tut_u6_s4_title: "Step 4 — Lab Admin tab",
        tut_u6_s4_body: "Monitor and manage user Lab containers, daily quota, storage and audit logs.",
        tut_u6_s5_title: "🎉 Personalize & Done",
        tut_u6_s5_body: "The Side Bar footer lets you adjust font size, switch theme / language, and replay this guide anytime. More in docs/04-operations.md — remember to set a strong admin password before term starts.",
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
        // v2.2: Announcements
        admin_announcements: "Announcements",
        btn_new_announcement: "New Announcement",
        th_pinned: "Pinned",
        th_title: "Title",
        th_posted_at: "Posted At",
        th_visible: "Visible",
        placeholder_announcement_title: "Title (max 200 chars)",
        placeholder_announcement_body: "Body (supports multiple lines)",
        label_pinned: "Pin to top",
        label_visible: "Publicly visible",
        announcement_new_title: "New Announcement",
        announcement_edit_title: "Edit Announcement",
        // v2.2: Export users modal
        btn_export_users: "Export Excel / CSV",
        btn_export_confirm: "Export",
        btn_cancel: "Cancel",
        export_title: "Export User Data",
        export_scope_label: "Scope:",
        export_scope_filter: "Current filtered results (by 3-tab and search)",
        export_scope_all: "All users",
        export_columns_label: "Columns to include:",
        export_select_all: "Select all",
        export_select_none: "Select none",
        export_format_label: "Format:",
        export_format_xlsx: "Excel (.xlsx)",
        export_format_csv: "CSV (UTF-8 BOM)",
        export_no_columns: "Please select at least one column",
        export_success: "Export complete",
        export_failed: "Export failed: ",
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
        analytics_overview: "Data Overview (External AI / myai)",
        stat_total_users: "Vendor Accounts",
        stat_total_logins: "Total Remaining Credits",
        stat_total_tokens: "Avg Credits / Account",
        chart_dept_usage: "Top 10 Accounts by Credits",
        chart_tool_usage: "Account Status Distribution",
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
        label_tool_types: "Applicable tools",
        tool_chat: "Text Chat",
        tool_presentation: "Presentation",
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

    // data-i18n-title: sets the title (tooltip) attribute
    document.querySelectorAll('[data-i18n-title]').forEach(el => {
        const text = t[el.getAttribute('data-i18n-title')];
        if (text) el.title = text;
    });
}

function applyTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    const themeIcon = theme === 'dark' ? 'moon-outline' : 'sunny-outline';
    document.querySelectorAll('.toggle-theme-btn ion-icon').forEach(icon => {
        icon.setAttribute('name', themeIcon);
    });
}

// v2.3: 介面字體大小 — 只放大字體（根層 font-size %），不縮放排版/位置（非放大鏡）
const FONT_SCALE_MIN = 80, FONT_SCALE_MAX = 150, FONT_SCALE_STEP = 10;
function applyFontScale(percent) {
    const p = Math.min(FONT_SCALE_MAX, Math.max(FONT_SCALE_MIN, parseInt(percent, 10) || 100));
    document.documentElement.style.fontSize = p + '%';
    localStorage.setItem('ai_hud_font_scale', String(p));
    const valEl = document.getElementById('admin-font-value');
    if (valEl) valEl.textContent = p + '%';
    return p;
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
    document.querySelectorAll('.admin-side-tab').forEach(btn => btn.classList.remove('active'));
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
        } else if (tabId === 'lab') {
            adminLab.init();
        } else if (tabId === 'external-ai') {
            externalAi.init();
        }
    }
}

// ============================================================
// v2.5 外部 AI 分流管理 | External AI routing admin
// ============================================================
const externalAi = {
    _authHeaders() {
        return { 'Authorization': `Bearer ${authToken}`, 'Content-Type': 'application/json' };
    },
    init() {
        this.loadUrl();
        this.refresh();
        this.loadMyai();
        this.loadBindings();
    },
    // v2.8 廠商 Token 同步（唯讀）
    async loadMyai() {
        try {
            const res = await fetch(`${API_BASE}/external-ai/admin/myai-accounts`, { headers: this._authHeaders() });
            if (!res.ok) throw new Error('load failed');
            const data = await res.json();
            this._renderMyai(data);
        } catch (e) { /* 靜默 */ }
    },
    _renderMyai(data) {
        const at = document.getElementById('myai-synced-at');
        if (at) at.textContent = data.synced_at ? ('上次同步：' + new Date(data.synced_at).toLocaleString()) : '尚未同步';
        const tbody = document.querySelector('#myai-accounts-table tbody');
        if (!tbody) return;
        const rows = data.accounts || [];
        if (!rows.length) {
            tbody.innerHTML = '<tr><td colspan="7" style="text-align:center; color:var(--text-muted);">尚未同步</td></tr>';
            return;
        }
        tbody.innerHTML = rows.map(r => {
            const ok = (r.status || '') === '確定' || (r.status || '').toLowerCase() === 'active';
            return `<tr>
                <td style="font-family:monospace;">${this._esc(r.vendor_sn)}</td>
                <td>${this._esc(r.user_type)}</td>
                <td>${this._esc(r.name)}</td>
                <td>${this._esc(r.email)}</td>
                <td style="font-family:monospace;">${Number(r.points || 0).toLocaleString()}</td>
                <td>${this._esc(r.expiry)}</td>
                <td style="color:${ok ? '#4ade80' : 'var(--text-muted)'};">${this._esc(r.status)}</td>
            </tr>`;
        }).join('');
    },
    async syncMyai() {
        const msg = document.getElementById('myai-sync-msg');
        if (msg) { msg.style.color = 'var(--text-muted)'; msg.textContent = '同步中…（headless 登入廠商，請稍候）'; }
        try {
            const res = await fetch(`${API_BASE}/external-ai/admin/sync-myai`, { method: 'POST', headers: this._authHeaders() });
            const data = await res.json().catch(() => ({}));
            if (!res.ok) throw new Error(data.detail || ('HTTP ' + res.status));
            if (msg) {
                msg.style.color = '#4ade80';
                const bind = (data.matched_created != null) ? `，自動綁定 ${data.matched_created}` : '';
                msg.textContent = `✓ 同步完成：共 ${data.total}（新增 ${data.created}、更新 ${data.updated}${bind}）`;
            }
            this.loadMyai();
            this.loadBindings();
        } catch (e) {
            if (msg) { msg.style.color = '#fb7185'; msg.textContent = '✗ 同步失敗：' + e.message; }
        }
    },

    // ============================================================
    // v2.8 Email 綁定管理（平台帳號 ↔ myai email ↔ 點數）
    // ============================================================
    async loadBindings() {
        try {
            const [bRes, uRes] = await Promise.all([
                fetch(`${API_BASE}/external-ai/admin/bindings`, { headers: this._authHeaders() }),
                fetch(`${API_BASE}/external-ai/admin/unmatched`, { headers: this._authHeaders() }),
            ]);
            if (bRes.ok) this._renderBindings(await bRes.json());
            if (uRes.ok) this._renderUnmatched(await uRes.json());
        } catch (e) { /* 靜默 */ }
    },
    _renderBindings(data) {
        const tbody = document.querySelector('#myai-bindings-table tbody');
        if (!tbody) return;
        const rows = data.bindings || [];
        if (!rows.length) {
            tbody.innerHTML = '<tr><td colspan="5" style="text-align:center; color:var(--text-muted);">尚無綁定</td></tr>';
            return;
        }
        tbody.innerHTML = rows.map(r => {
            const active = (r.status || 'active') === 'active';
            const pts = (r.points == null) ? '—' : Number(r.points).toLocaleString();
            const warn = r.synced ? '' : ' <span style="color:#fbbf24;" title="對不到同步快取，請先同步或檢查 email">⚠</span>';
            return `<tr>
                <td>${this._esc(r.platform_username)}</td>
                <td style="font-family:monospace; font-size:12px;">${this._esc(r.myai_email)}${warn}</td>
                <td style="font-family:monospace;">${pts}</td>
                <td style="color:${active ? '#4ade80' : 'var(--text-muted)'};">${active ? '啟用' : '停用'}</td>
                <td><button onclick="externalAi.unbind('${r.id}','${encodeURIComponent(r.platform_username || '')}')" title="解綁"
                        style="background:none; border:none; color:#fb7185; cursor:pointer; font-size:16px;">
                    <ion-icon name="unlink-outline"></ion-icon></button></td>
            </tr>`;
        }).join('');
    },
    _renderUnmatched(data) {
        const uc = document.getElementById('myai-unmatched-users-count');
        const mc = document.getElementById('myai-unmatched-myai-count');
        if (uc) uc.textContent = data.unmatched_user_count || 0;
        if (mc) mc.textContent = data.unmatched_myai_count || 0;
        const ut = document.querySelector('#myai-unmatched-users-table tbody');
        if (ut) {
            const rows = data.unmatched_users || [];
            ut.innerHTML = rows.length ? rows.map(u => `<tr>
                <td>${this._esc(u.username)}</td>
                <td style="font-size:12px;">${this._esc(u.email)}</td>
                <td>${u.has_myai_match ? '<span style="color:#4ade80;">✓ 可</span>' : '—'}</td>
            </tr>`).join('') : '<tr><td colspan="3" style="text-align:center; color:var(--text-muted);">（無）</td></tr>';
        }
        const mt = document.querySelector('#myai-unmatched-myai-table tbody');
        if (mt) {
            const rows = data.unmatched_myai || [];
            mt.innerHTML = rows.length ? rows.map(m => `<tr>
                <td style="font-size:12px;">${this._esc(m.email)}</td>
                <td>${this._esc(m.name)}</td>
                <td style="font-family:monospace;">${Number(m.points || 0).toLocaleString()}</td>
            </tr>`).join('') : '<tr><td colspan="3" style="text-align:center; color:var(--text-muted);">（無）</td></tr>';
        }
    },
    async autoMatch() {
        const msg = document.getElementById('myai-bind-msg');
        if (msg) { msg.style.color = 'var(--text-muted)'; msg.textContent = '配對中…'; }
        try {
            const res = await fetch(`${API_BASE}/external-ai/admin/auto-match`, { method: 'POST', headers: this._authHeaders() });
            const data = await res.json().catch(() => ({}));
            if (!res.ok) throw new Error(data.detail || ('HTTP ' + res.status));
            if (msg) { msg.style.color = '#4ade80'; msg.textContent = `✓ 配對完成：新增綁定 ${data.matched_created}、回填 ${data.backfilled}`; }
            this.loadBindings();
        } catch (e) {
            if (msg) { msg.style.color = '#fb7185'; msg.textContent = '✗ 配對失敗：' + e.message; }
        }
    },
    async unbind(id, usernameEnc) {
        const username = decodeURIComponent(usernameEnc || '');
        if (!confirm(`確定解除「${username}」的 myai 綁定？(只移除對應關係，不影響該帳號本身)`)) return;
        try {
            const res = await fetch(`${API_BASE}/external-ai/admin/accounts/${id}`, { method: 'DELETE', headers: this._authHeaders() });
            if (!res.ok) throw new Error('delete failed');
            showToast('已解除綁定');
            this.loadBindings();
            this.refresh();
        } catch (e) { showToast('解綁失敗', true); }
    },
    async loadUrl() {
        try {
            const res = await fetch(`${API_BASE}/external-ai/admin/url`, { headers: this._authHeaders() });
            if (!res.ok) throw new Error('load url failed');
            const data = await res.json();
            const el = document.getElementById('ext-ai-url');
            if (el) el.value = data.url || '';
            const lo = document.getElementById('ext-ai-logout-url');
            if (lo) lo.value = data.logout_url || '';
        } catch (e) { /* 靜默 | silent */ }
    },
    async saveUrl() {
        const el = document.getElementById('ext-ai-url');
        const lo = document.getElementById('ext-ai-logout-url');
        const msg = document.getElementById('ext-ai-url-msg');
        try {
            const res = await fetch(`${API_BASE}/external-ai/admin/url`, {
                method: 'PUT', headers: this._authHeaders(),
                body: JSON.stringify({
                    url: (el.value || '').trim(),
                    logout_url: lo ? (lo.value || '').trim() : null,
                }),
            });
            if (!res.ok) throw new Error('save failed');
            if (msg) { msg.style.color = '#4ade80'; msg.textContent = '✓ 已儲存'; }
            showToast('外部 AI 網址已更新');
        } catch (e) {
            if (msg) { msg.style.color = '#fb7185'; msg.textContent = '✗ 儲存失敗'; }
            showToast('儲存失敗', true);
        }
    },
    async refresh() {
        const tbody = document.querySelector('#ext-ai-accounts-table tbody');
        try {
            const res = await fetch(`${API_BASE}/external-ai/admin/accounts`, { headers: this._authHeaders() });
            if (!res.ok) throw new Error('list failed');
            const rows = await res.json();
            if (!rows.length) {
                tbody.innerHTML = '<tr><td colspan="4" style="text-align:center; color:var(--text-muted);">尚無對應</td></tr>';
                return;
            }
            tbody.innerHTML = rows.map(r => {
                const active = (r.status || 'active') === 'active';
                const statusBadge = active
                    ? '<span style="color:#4ade80;">active</span>'
                    : '<span style="color:#fb7185;">disabled</span>';
                const pf = this._esc(r.platform_username || r.user_id);
                const vd = this._esc(r.vendor_username);
                return `<tr>
                    <td>${pf}</td>
                    <td><code>${vd}</code></td>
                    <td>${statusBadge}</td>
                    <td style="white-space:nowrap;">
                        <button class="ready-btn" style="width:auto;padding:3px 8px;font-size:12px;" onclick="externalAi.editVendor('${r.id}','${vd}')">改帳號</button>
                        <button class="ready-btn" style="width:auto;padding:3px 8px;font-size:12px;" onclick="externalAi.toggleStatus('${r.id}','${active ? 'disabled' : 'active'}')">${active ? '停用' : '啟用'}</button>
                        <button class="ready-btn" style="width:auto;padding:3px 8px;font-size:12px;background:rgba(251,113,133,0.12);color:#fb7185;" onclick="externalAi.remove('${r.id}','${pf}')">刪除</button>
                    </td>
                </tr>`;
            }).join('');
        } catch (e) {
            tbody.innerHTML = '<tr><td colspan="4" style="text-align:center; color:#fb7185;">載入失敗</td></tr>';
        }
    },
    async addMapping() {
        const pf = document.getElementById('ext-ai-add-platform');
        const vd = document.getElementById('ext-ai-add-vendor');
        const msg = document.getElementById('ext-ai-add-msg');
        if (!pf.value.trim() || !vd.value.trim()) {
            if (msg) { msg.style.color = '#fb7185'; msg.textContent = '請填寫平台帳號與廠商帳號'; }
            return;
        }
        try {
            const res = await fetch(`${API_BASE}/external-ai/admin/accounts`, {
                method: 'POST', headers: this._authHeaders(),
                body: JSON.stringify({ platform_username: pf.value.trim(), vendor_username: vd.value.trim() }),
            });
            if (!res.ok) {
                const err = await res.json().catch(() => ({}));
                throw new Error(err.detail || 'add failed');
            }
            if (msg) { msg.style.color = '#4ade80'; msg.textContent = '✓ 已新增'; }
            pf.value = ''; vd.value = '';
            this.refresh();
            this.loadBindings();  // v2.8 同步刷新綁定/未配對面板
        } catch (e) {
            if (msg) { msg.style.color = '#fb7185'; msg.textContent = '✗ ' + e.message; }
        }
    },
    async editVendor(id, current) {
        const next = prompt('輸入新的廠商帳號名：', current);
        if (next === null || !next.trim()) return;
        await this._update(id, { vendor_username: next.trim() });
    },
    async toggleStatus(id, status) {
        await this._update(id, { status });
    },
    async _update(id, payload) {
        try {
            const res = await fetch(`${API_BASE}/external-ai/admin/accounts/${id}`, {
                method: 'PUT', headers: this._authHeaders(), body: JSON.stringify(payload),
            });
            if (!res.ok) throw new Error('update failed');
            showToast('已更新');
            this.refresh();
            this.loadBindings();  // v2.8 同步刷新綁定/未配對面板
        } catch (e) { showToast('更新失敗', true); }
    },
    async remove(id, name) {
        if (!confirm(`確定刪除「${name}」的對應？`)) return;
        try {
            const res = await fetch(`${API_BASE}/external-ai/admin/accounts/${id}`, {
                method: 'DELETE', headers: this._authHeaders(),
            });
            if (!res.ok) throw new Error('delete failed');
            showToast('已刪除');
            this.refresh();
            this.loadBindings();  // v2.8 同步刷新綁定/未配對面板
        } catch (e) { showToast('刪除失敗', true); }
    },
    async importCsv() {
        const ta = document.getElementById('ext-ai-csv');
        const msg = document.getElementById('ext-ai-csv-msg');
        if (!ta.value.trim()) {
            if (msg) { msg.style.color = '#fb7185'; msg.textContent = '請貼上 CSV 內容'; }
            return;
        }
        try {
            const res = await fetch(`${API_BASE}/external-ai/admin/import`, {
                method: 'POST', headers: this._authHeaders(),
                body: JSON.stringify({ csv: ta.value }),
            });
            if (!res.ok) throw new Error('import failed');
            const r = await res.json();
            let txt = `新增 ${r.created}、更新 ${r.updated}、略過 ${r.skipped}`;
            if (r.errors && r.errors.length) txt += '\n錯誤：\n' + r.errors.join('\n');
            if (msg) { msg.style.color = (r.errors && r.errors.length) ? '#fbbf24' : '#4ade80'; msg.textContent = txt; }
            this.refresh();
            this.loadBindings();  // v2.8 同步刷新綁定/未配對面板
        } catch (e) {
            if (msg) { msg.style.color = '#fb7185'; msg.textContent = '✗ 匯入失敗'; }
        }
    },
    _esc(s) {
        return String(s == null ? '' : s).replace(/[&<>"']/g, c => (
            { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
        ));
    },
};

// v2.8: 數據分析改吃外部廠商(myai)資料 —— 從 /external-ai/admin/myai-accounts 聚合。
async function fetchAnalyticsData() {
    try {
        const res = await fetch(`${API_BASE}/external-ai/admin/myai-accounts`, {
            headers: { 'Authorization': `Bearer ${authToken}` }
        });
        if (res.status === 401) { handleAuthError(); return; }
        if (!res.ok) throw new Error('Failed to fetch analytics data');
        renderAnalyticsUI(await res.json());
    } catch (e) {
        console.error(e);
        showToast(TRANSLATIONS[currentLang]?.error_loading_analytics || 'Error loading analytics data', true);
    }
}

function renderAnalyticsUI(data) {
    const txtColor = getComputedStyle(document.body).getPropertyValue('--text-primary') || '#888';
    const rows = (data && data.accounts) || [];

    // 1) 總覽：廠商帳號數 / 總剩餘點數 / 平均點數
    const count = rows.length;
    const totalPoints = rows.reduce((a, r) => a + (Number(r.points) || 0), 0);
    const avg = count ? Math.round(totalPoints / count) : 0;
    document.getElementById('stat-total-users').textContent = count.toLocaleString();
    document.getElementById('stat-total-logins').textContent = totalPoints.toLocaleString();
    document.getElementById('stat-total-tokens').textContent = avg.toLocaleString();
    const at = document.getElementById('analytics-synced-at');
    if (at) at.textContent = data.synced_at ? ('上次同步：' + new Date(data.synced_at).toLocaleString()) : '尚未同步';

    // 2) 長條圖：點數 Top 10 帳號
    const top = [...rows].sort((a, b) => (Number(b.points) || 0) - (Number(a.points) || 0)).slice(0, 10);
    const barLabels = top.map(r => r.name || r.email || r.vendor_sn || '?');
    const barData = top.map(r => Number(r.points) || 0);
    const deptCtx = document.getElementById('deptUsageChart').getContext('2d');
    if (deptChartInstance) deptChartInstance.destroy();
    deptChartInstance = new Chart(deptCtx, {
        type: 'bar',
        data: { labels: barLabels, datasets: [{
            label: TRANSLATIONS[currentLang]?.chart_dept_usage || 'Top accounts',
            data: barData,
            backgroundColor: 'rgba(56, 189, 248, 0.7)', borderColor: 'rgba(56, 189, 248, 1)',
            borderWidth: 1, borderRadius: 4 }] },
        options: { responsive: true, maintainAspectRatio: false,
            plugins: { legend: { labels: { color: txtColor } } },
            scales: {
                x: { ticks: { color: txtColor }, grid: { color: 'rgba(128,128,128,0.2)' } },
                y: { ticks: { color: txtColor }, grid: { color: 'rgba(128,128,128,0.2)' }, beginAtZero: true }
            } }
    });

    // 3) 圓餅圖：帳號狀態分佈
    const statusMap = {};
    rows.forEach(r => { const s = (r.status || '未知'); statusMap[s] = (statusMap[s] || 0) + 1; });
    const pieLabels = Object.keys(statusMap);
    const pieData = pieLabels.map(k => statusMap[k]);
    const toolCtx = document.getElementById('toolUsageChart').getContext('2d');
    if (toolChartInstance) toolChartInstance.destroy();
    toolChartInstance = new Chart(toolCtx, {
        type: 'pie',
        data: { labels: pieLabels, datasets: [{
            data: pieData,
            backgroundColor: ['rgba(74,222,128,0.8)','rgba(56,189,248,0.8)','rgba(250,204,21,0.8)','rgba(244,114,182,0.8)','rgba(167,139,250,0.8)'],
            borderWidth: 1, borderColor: '#1e293b' }] },
        options: { responsive: true, maintainAspectRatio: false,
            plugins: { legend: { position: 'right', labels: { color: txtColor } } } }
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
// v2.1: 使用者管理依 auth_source 分 3 個 tab；切 tab 時只 refetch 對應分類
let _currentAuthSource = 'local';   // 預設顯示本機帳號（admin + provisioned 學生）

async function fetchAdminData() {
    try {
        const [usersRes, jobsRes, modelsRes] = await Promise.all([
            fetch(`${API_BASE}/admin/users?auth_source=${encodeURIComponent(_currentAuthSource)}`, { headers: { 'Authorization': `Bearer ${authToken}` } }),
            fetch(`${API_BASE}/admin/jobs`, { headers: { 'Authorization': `Bearer ${authToken}` } }),
            fetch(`${API_BASE}/admin/models`, { headers: { 'Authorization': `Bearer ${authToken}` } })
        ]);

        if (usersRes.ok) renderAdminUsers(await usersRes.json());
        if (jobsRes.ok) renderAdminJobs(await jobsRes.json());
        if (modelsRes.ok) renderAdminModels(await modelsRes.json());

        // v2.1: 同步更新 3 個 tab 的 badge 計數（額外打 3 個 light request）
        updateAuthSourceCounts();
        // v2.2: 同步拉公告列表（admin UI 用）
        fetchAnnouncementsAdmin();
    } catch (e) {
        console.error("Failed to fetch admin data", e);
    }
}

// v2.1: 為 3 個 tab 顯示各自的使用者數
async function updateAuthSourceCounts() {
    const sources = ['local', 'sso_oidc', 'sso_mock'];
    await Promise.all(sources.map(async (src) => {
        try {
            const res = await fetch(`${API_BASE}/admin/users?auth_source=${src}&limit=500`, {
                headers: { 'Authorization': `Bearer ${authToken}` },
            });
            if (!res.ok) return;
            const data = await res.json();
            const el = document.getElementById(`user-source-count-${src}`);
            if (el) el.textContent = String((data || []).length);
        } catch (_) { /* 計數失敗不影響主流程 */ }
    }));
}

let _adminUsersCache = [];

function renderAdminUsers(users) {
    try {
        if (users) {
            _adminUsersCache = users;
            // v2.2: 更新「最後刷新時間」徽章，讓 admin 知道 polling 真的在跑
            const stamp = document.getElementById('admin-users-last-updated');
            if (stamp) {
                const t = new Date();
                stamp.textContent = `${t.getHours().toString().padStart(2,'0')}:${t.getMinutes().toString().padStart(2,'0')}:${t.getSeconds().toString().padStart(2,'0')}`;
            }
        }
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

            // Online status indicator: red=disabled, green=online, gray=offline, dash="N/A"
            // v2.1 修正：admin 從未登入 user UI → online_status=null → 顯示「—」（不適用）
            // v2.2: hover 顯示「上次活動：N 分鐘前」讓 admin 知道判斷依據
            const lblOnline   = tl.label_online   || 'Online';
            const lblOffline  = tl.label_offline  || 'Offline';
            const lblDisabled = tl.status_disabled || 'Disabled';
            const lblNA       = tl.label_na       || 'Not applicable';

            // 計算「上次登入距今多久」當 tooltip 補充資訊
            let detailTooltip = '';
            if (u.last_login_time) {
                const diffMs = Date.now() - new Date(u.last_login_time).getTime();
                const diffMin = Math.floor(diffMs / 60000);
                if (diffMin < 1) detailTooltip = ' (剛剛登入)';
                else if (diffMin < 60) detailTooltip = ` (上次登入 ${diffMin} 分鐘前)`;
                else if (diffMin < 1440) detailTooltip = ` (上次登入 ${Math.floor(diffMin/60)} 小時前)`;
                else detailTooltip = ` (上次登入 ${Math.floor(diffMin/1440)} 天前)`;
            } else {
                detailTooltip = ' (從未登入)';
            }

            let onlineDot;
            if (!u.is_active) {
                onlineDot = `<span style="display:inline-block; width:8px; height:8px; border-radius:50%; background:#ef4444; margin-right:6px; box-shadow:0 0 5px #ef4444;" title="${lblDisabled}${detailTooltip}"></span>`;
            } else if (u.online_status === null || u.online_status === undefined) {
                // v2.1: admin 未登入 user UI → 線上狀態不適用
                onlineDot = `<span style="display:inline-block; width:8px; height:8px; line-height:8px; text-align:center; color:#9ca3af; margin-right:6px; font-size:10px;" title="${lblNA} (本機 admin，沒登入 user UI 不顯示在線狀態)">—</span>`;
            } else if (u.online_status === 1) {
                onlineDot = `<span style="display:inline-block; width:8px; height:8px; border-radius:50%; background:#10b981; margin-right:6px; box-shadow:0 0 5px #10b981;" title="${lblOnline} (10 分鐘內活躍)${detailTooltip}"></span>`;
            } else {
                onlineDot = `<span style="display:inline-block; width:8px; height:8px; border-radius:50%; background:#6b7280; margin-right:6px;" title="${lblOffline} (>10 分鐘未活動)${detailTooltip}"></span>`;
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
                <td style="display:none;">${tokensStr}</td>
                <td>
                        <div style="display:flex; gap:4px; flex-wrap:wrap;">
                            <button class="ready-btn" style="width:auto; padding:4px 12px; margin:0; font-size:12px; min-width:auto;" onclick="openEditUser('${u.id}')" data-i18n="btn_edit">${TRANSLATIONS[currentLang]?.btn_edit || 'Edit'}</button>
                            <button class="ready-btn" style="display:none; width:auto; padding:4px 12px; margin:0; font-size:12px; min-width:auto; border-color:#a78bfa; color:#a78bfa; background:rgba(167,139,250,0.08);" onclick="openUserAnalytics('${u.id}')" data-i18n="btn_analytics">${TRANSLATIONS[currentLang]?.btn_analytics || 'Analytics'}</button>
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
                <button class="job-action-btn priority-btn" onclick="reprioritizeJob('${j.job_id}', '${j.job_name}')">${prioLabel}</button>
                <button class="job-action-btn cancel-btn" onclick="cancelJobAdmin('${j.job_id}', '${j.job_name}')">${cancelLabel}</button>
            </div>` : `<span style="color:var(--text-muted); font-size:12px;">—</span>`;

        tr.innerHTML = `
            <td>${j.job_name}<br><small style="color:var(--text-muted)">${(j.job_id || '').substring(0, 8)}</small></td>
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
    // v2.4: 適用工具 — 預設只勾 chat
    _setModelToolTypes('chat');

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
            _setModelToolTypes(m.tool_types || 'chat');
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

// v2.4: 適用工具 checkbox 讀寫輔助
function _setModelToolTypes(csv) {
    const set = new Set(String(csv || 'chat').split(',').map(s => s.trim().toLowerCase()).filter(Boolean));
    document.querySelectorAll('.model-tool-type').forEach(cb => { cb.checked = set.has(cb.value); });
}
function _getModelToolTypes() {
    const vals = Array.from(document.querySelectorAll('.model-tool-type:checked')).map(cb => cb.value);
    return vals.length ? vals.join(',') : 'chat';   // 至少保底 chat
}

async function submitModelForm(e) {
    e.preventDefault();
    const editId = document.getElementById('model-edit-id').value;
    const modelType = document.getElementById('model-type').value;
    const payload = {
        name: document.getElementById('model-name').value,
        model_type: modelType,
        description: document.getElementById('model-description').value || null,
        is_public: parseInt(document.getElementById('model-is-public').value),
        tool_types: _getModelToolTypes()
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
// v2.2: Announcements Management (公告管理)
// -------------------------
async function fetchAnnouncementsAdmin() {
    const tbody = document.getElementById('announcements-body');
    if (!tbody) return;
    try {
        const res = await fetch(`${API_BASE}/admin/announcements?include_hidden=true`, {
            headers: { 'Authorization': `Bearer ${authToken}` },
        });
        if (!res.ok) throw new Error('HTTP ' + res.status);
        const items = await res.json();
        if (items.length === 0) {
            tbody.innerHTML = `<tr><td colspan="5" style="text-align:center; color:var(--text-muted); padding:16px;">尚無公告</td></tr>`;
            return;
        }
        tbody.innerHTML = items.map(a => {
            const dt = new Date(a.posted_at);
            const dateStr = `${dt.getFullYear()}-${String(dt.getMonth()+1).padStart(2,'0')}-${String(dt.getDate()).padStart(2,'0')} ${String(dt.getHours()).padStart(2,'0')}:${String(dt.getMinutes()).padStart(2,'0')}`;
            const pinIcon = a.is_pinned ? '<ion-icon name="pin" style="color:var(--neon-yellow); font-size:18px;" title="置頂"></ion-icon>' : '<span style="color:var(--text-muted);">—</span>';
            const visIcon = a.is_visible ? '<ion-icon name="eye-outline" style="color:var(--neon-green); font-size:18px;" title="公開"></ion-icon>' : '<ion-icon name="eye-off-outline" style="color:var(--text-muted); font-size:18px;" title="隱藏"></ion-icon>';
            const titleSpan = document.createElement('span');
            titleSpan.textContent = a.title;
            return `
                <tr>
                    <td style="text-align:center;">${pinIcon}</td>
                    <td>${titleSpan.outerHTML.replace(/<\/?span>/g, '')}</td>
                    <td style="font-family:monospace; font-size:12px;">${dateStr}</td>
                    <td style="text-align:center;">${visIcon}</td>
                    <td>
                        <button class="job-action-btn" onclick="editAnnouncement(${a.id})" title="編輯">
                            <ion-icon name="create-outline"></ion-icon>
                        </button>
                        <button class="job-action-btn cancel-btn" onclick="deleteAnnouncement(${a.id})" title="刪除">
                            <ion-icon name="trash-outline"></ion-icon>
                        </button>
                    </td>
                </tr>
            `;
        }).join('');
    } catch (e) {
        console.error('Failed to fetch announcements:', e);
        tbody.innerHTML = `<tr><td colspan="5" style="text-align:center; color:var(--neon-pink); padding:16px;">載入失敗：${e.message}</td></tr>`;
    }
}

let _announcementsCache = [];
async function _loadAnnouncementsCache() {
    const res = await fetch(`${API_BASE}/admin/announcements?include_hidden=true`, {
        headers: { 'Authorization': `Bearer ${authToken}` },
    });
    if (res.ok) _announcementsCache = await res.json();
}

function openAnnouncementModal(ann) {
    const modal = document.getElementById('announcement-modal');
    document.getElementById('announcement-id').value = ann ? ann.id : '';
    document.getElementById('announcement-title').value = ann ? ann.title : '';
    document.getElementById('announcement-body').value = ann ? ann.body : '';
    document.getElementById('announcement-pinned').checked = ann ? !!ann.is_pinned : false;
    document.getElementById('announcement-visible').checked = ann ? !!ann.is_visible : true;
    document.querySelector('#announcement-modal-title span').textContent = ann ? '編輯公告' : '新增公告';
    modal.classList.remove('hidden');
}

function closeAnnouncementModal() {
    document.getElementById('announcement-modal').classList.add('hidden');
}

async function submitAnnouncementForm(e) {
    e.preventDefault();
    const id = document.getElementById('announcement-id').value;
    const payload = {
        title: document.getElementById('announcement-title').value.trim(),
        body: document.getElementById('announcement-body').value.trim(),
        is_pinned: document.getElementById('announcement-pinned').checked ? 1 : 0,
        is_visible: document.getElementById('announcement-visible').checked ? 1 : 0,
    };
    if (!payload.title || !payload.body) {
        showToast('請填寫標題與內容', true);
        return;
    }
    try {
        const url = id ? `${API_BASE}/admin/announcements/${id}` : `${API_BASE}/admin/announcements`;
        const method = id ? 'PUT' : 'POST';
        const res = await fetch(url, {
            method,
            headers: { 'Authorization': `Bearer ${authToken}`, 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        if (!res.ok) throw new Error('HTTP ' + res.status);
        closeAnnouncementModal();
        fetchAnnouncementsAdmin();
        showToast(id ? '公告已更新' : '公告已建立', false);
    } catch (e) {
        showToast('儲存失敗：' + e.message, true);
    }
}

async function editAnnouncement(id) {
    await _loadAnnouncementsCache();
    const ann = _announcementsCache.find(a => a.id === id);
    if (ann) openAnnouncementModal(ann);
}

async function deleteAnnouncement(id) {
    if (!confirm('確定要刪除這則公告嗎？')) return;
    try {
        const res = await fetch(`${API_BASE}/admin/announcements/${id}`, {
            method: 'DELETE',
            headers: { 'Authorization': `Bearer ${authToken}` },
        });
        if (!res.ok) throw new Error('HTTP ' + res.status);
        fetchAnnouncementsAdmin();
        showToast('公告已刪除', false);
    } catch (e) {
        showToast('刪除失敗：' + e.message, true);
    }
}

// -------------------------
// v2.2: Export Users Modal — 匯出使用者資料 (Excel / CSV)
// -------------------------
async function openExportModal() {
    const modal = document.getElementById('export-modal');
    modal.classList.remove('hidden');

    // 重置選項
    document.querySelector('input[name="export-scope"][value="filter"]').checked = true;
    document.querySelector('input[name="export-format"][value="xlsx"]').checked = true;

    // fetch 欄位清單
    const listEl = document.getElementById('export-columns-list');
    const tl = TRANSLATIONS[currentLang] || {};
    listEl.innerHTML = `<div style="grid-column: 1 / -1; color: var(--text-muted); font-size: 13px; text-align: center; padding: 10px;">${tl.msg_loading || '載入中...'}</div>`;
    try {
        const res = await fetch(`${API_BASE}/admin/users/export/columns`, {
            headers: { 'Authorization': `Bearer ${authToken}` },
        });
        if (!res.ok) throw new Error('HTTP ' + res.status);
        const cols = await res.json();
        // 預設勾選的欄位（基本資料）
        const defaultChecked = new Set(['username', 'email', 'role', 'auth_source', 'is_active', 'department', 'last_login_time', 'tokens_used', 'tokens_limit']);
        listEl.innerHTML = cols.map(c => `
            <label style="font-size: 13px; cursor: pointer; display: flex; align-items: center; gap: 6px;">
                <input type="checkbox" class="export-col-cb" value="${c.key}" ${defaultChecked.has(c.key) ? 'checked' : ''}>
                ${c.label}
            </label>
        `).join('');
    } catch (e) {
        console.error('Failed to load export columns:', e);
        listEl.innerHTML = `<div style="grid-column: 1 / -1; color: var(--neon-pink); font-size: 13px; text-align: center; padding: 10px;">載入欄位失敗：${e.message}</div>`;
    }
}

function closeExportModal() {
    document.getElementById('export-modal').classList.add('hidden');
}

function toggleExportColumns(checked) {
    document.querySelectorAll('.export-col-cb').forEach(cb => { cb.checked = checked; });
}

async function submitExport() {
    const checked = Array.from(document.querySelectorAll('.export-col-cb:checked')).map(cb => cb.value);
    if (checked.length === 0) {
        const tl = TRANSLATIONS[currentLang] || {};
        showToast(tl.export_no_columns || '請至少勾選一個欄位', true);
        return;
    }
    const scope = document.querySelector('input[name="export-scope"]:checked').value;
    const fmt = document.querySelector('input[name="export-format"]:checked').value;

    // 組 query
    const params = new URLSearchParams({
        fmt,
        scope,
        columns: checked.join(','),
    });
    if (scope === 'filter' && typeof _currentAuthSource !== 'undefined' && _currentAuthSource) {
        params.set('auth_source', _currentAuthSource);
    }

    const btn = document.getElementById('export-confirm-btn');
    const originalText = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = '<ion-icon name="hourglass-outline"></ion-icon> 匯出中...';
    try {
        const res = await fetch(`${API_BASE}/admin/users/export?${params}`, {
            headers: { 'Authorization': `Bearer ${authToken}` },
        });
        if (!res.ok) throw new Error('HTTP ' + res.status);
        // 抓 Content-Disposition 取得檔名（fallback 用日期）
        const cd = res.headers.get('content-disposition') || '';
        const m = cd.match(/filename="?([^";]+)"?/);
        const filename = m ? m[1] : `users-${Date.now()}.${fmt}`;

        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);

        const tl = TRANSLATIONS[currentLang] || {};
        showToast(tl.export_success || '匯出完成', false);
        closeExportModal();
    } catch (e) {
        console.error('Export failed:', e);
        const tl = TRANSLATIONS[currentLang] || {};
        showToast((tl.export_failed || '匯出失敗：') + e.message, true);
    } finally {
        btn.disabled = false;
        btn.innerHTML = originalText;
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

    // v2.2: Announcements Modal Bindings
    const newAnnBtn = document.getElementById('btn-new-announcement');
    if (newAnnBtn) newAnnBtn.addEventListener('click', () => openAnnouncementModal(null));
    const annForm = document.getElementById('announcement-form');
    if (annForm) annForm.addEventListener('submit', submitAnnouncementForm);
    const annCloseBtn = document.getElementById('announcement-close-btn');
    if (annCloseBtn) annCloseBtn.addEventListener('click', closeAnnouncementModal);
    const annCancelBtn = document.getElementById('announcement-cancel-btn');
    if (annCancelBtn) annCancelBtn.addEventListener('click', closeAnnouncementModal);
    const annBackdrop = document.getElementById('announcement-backdrop');
    if (annBackdrop) annBackdrop.addEventListener('click', closeAnnouncementModal);

    // v2.2: Export Users Modal Bindings
    const exportBtn = document.getElementById('btn-export-users');
    if (exportBtn) exportBtn.addEventListener('click', openExportModal);
    const exportCloseBtn = document.getElementById('export-close-btn');
    if (exportCloseBtn) exportCloseBtn.addEventListener('click', closeExportModal);
    const exportBackdrop = document.getElementById('export-backdrop');
    if (exportBackdrop) exportBackdrop.addEventListener('click', closeExportModal);
    const exportCancelBtn = document.getElementById('export-cancel-btn');
    if (exportCancelBtn) exportCancelBtn.addEventListener('click', closeExportModal);
    const exportConfirmBtn = document.getElementById('export-confirm-btn');
    if (exportConfirmBtn) exportConfirmBtn.addEventListener('click', submitExport);
    const exportSelectAll = document.getElementById('export-select-all');
    if (exportSelectAll) exportSelectAll.addEventListener('click', (e) => { e.preventDefault(); toggleExportColumns(true); });
    const exportSelectNone = document.getElementById('export-select-none');
    if (exportSelectNone) exportSelectNone.addEventListener('click', (e) => { e.preventDefault(); toggleExportColumns(false); });

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

    // v2.1: 使用者管理 auth_source tab 切換
    document.querySelectorAll('.user-source-tab').forEach(btn => {
        btn.addEventListener('click', () => {
            const src = btn.getAttribute('data-source');
            if (!src || src === _currentAuthSource) return;
            _currentAuthSource = src;
            // 視覺切換
            document.querySelectorAll('.user-source-tab').forEach(b => b.classList.toggle('active', b === btn));
            // 重抓對應分類 + 更新計數
            fetchAdminData();
        });
    });

    // Initialize Theme & Lang
    applyTheme(currentTheme);
    applyTranslations();

    // v2.3: 字體大小初始化 + A- / A+ 綁定
    let currentFontScale = applyFontScale(localStorage.getItem('ai_hud_font_scale') || 100);
    const fontDec = document.getElementById('admin-font-dec');
    const fontInc = document.getElementById('admin-font-inc');
    if (fontDec) fontDec.addEventListener('click', () => { currentFontScale = applyFontScale(currentFontScale - FONT_SCALE_STEP); });
    if (fontInc) fontInc.addEventListener('click', () => { currentFontScale = applyFontScale(currentFontScale + FONT_SCALE_STEP); });

    // v2.3: 管理者引導式教學（overlay + 高亮框 + 氣泡；5 步；原使用者介面 Unit 6 移入）
    const GUIDE_STEPS = [
        { t: 'tut_u6_s1_title', b: 'tut_u6_s1_body' },                                   // 居中歡迎
        { t: 'tut_u6_s2_title', b: 'tut_u6_s2_body', sel: '#nav-tab-management' },
        { t: 'tut_u6_s3_title', b: 'tut_u6_s3_body', sel: '#nav-tab-analytics' },
        { t: 'tut_u6_s4_title', b: 'tut_u6_s4_body', sel: '#nav-tab-lab' },
        { t: 'tut_u6_s5_title', b: 'tut_u6_s5_body', sel: '.admin-sidebar-actions' },
    ];
    let guideIdx = 0, guideHL = null;
    const guideOverlay = document.getElementById('admin-guide-overlay');
    const guideRing = document.getElementById('admin-guide-ring');
    function guidePositionRing(el) {
        if (!guideRing || !el) return;
        const r = el.getBoundingClientRect(), gap = 5;
        guideRing.style.top = (r.top - gap) + 'px';
        guideRing.style.left = (r.left - gap) + 'px';
        guideRing.style.width = (r.width + gap * 2) + 'px';
        guideRing.style.height = (r.height + gap * 2) + 'px';
        guideRing.classList.remove('hidden');
    }
    function guideClearRing() { if (guideRing) guideRing.classList.add('hidden'); guideHL = null; }
    function guidePositionBubble(el) {
        const wrap = document.getElementById('admin-guide-bubble-wrap');
        if (!wrap) return;
        if (!el) { wrap.style.left = '50%'; wrap.style.top = '50%'; wrap.style.transform = 'translate(-50%, -50%)'; return; }
        wrap.style.transform = 'none';
        const rect = el.getBoundingClientRect();
        const bubble = document.getElementById('admin-guide-bubble');
        const bb = bubble ? bubble.getBoundingClientRect() : { width: 320, height: 200 };
        const bw = bb.width || 320, bh = bb.height || 200, gap = 16, margin = 12;
        let left = rect.right + gap, top = rect.top;
        if (left + bw > window.innerWidth - margin) left = rect.left - gap - bw;  // 右側放不下 → 左側
        if (left < margin) { left = Math.max(margin, rect.left); top = rect.bottom + gap; }  // 左也不下 → 下方
        if (top + bh > window.innerHeight - margin) top = Math.max(margin, window.innerHeight - bh - margin);
        if (top < margin) top = margin;
        wrap.style.left = Math.round(left) + 'px';
        wrap.style.top = Math.round(top) + 'px';
    }
    function guideRender() {
        const tr = TRANSLATIONS[currentLang] || {};
        const step = GUIDE_STEPS[guideIdx];
        const titleEl = document.getElementById('admin-guide-step-title');
        const bodyEl = document.getElementById('admin-guide-step-body');
        const badge = document.getElementById('admin-guide-badge');
        const prevBtn = document.getElementById('admin-guide-prev');
        const nextBtn = document.getElementById('admin-guide-next');
        const bubble = document.getElementById('admin-guide-bubble');
        if (!titleEl) return;
        if (bubble) { bubble.style.visibility = 'hidden'; bubble.classList.remove('animate-in'); }
        guideClearRing();
        badge.textContent = (guideIdx + 1) + ' / ' + GUIDE_STEPS.length;
        titleEl.textContent = tr[step.t] || '';
        bodyEl.textContent = tr[step.b] || '';
        prevBtn.style.visibility = guideIdx === 0 ? 'hidden' : 'visible';
        const isLast = guideIdx === GUIDE_STEPS.length - 1;
        nextBtn.querySelector('span').textContent = isLast ? (tr.guide_done || 'Done') : (tr.guide_next || 'Next');
        requestAnimationFrame(() => {
            let target = null;
            if (step.sel) {
                target = document.querySelector(step.sel);
                if (target) { guidePositionRing(target); guideHL = target; }
            }
            guidePositionBubble(target);
            if (guideOverlay) guideOverlay.classList.remove('hidden');
            if (bubble) { bubble.style.visibility = 'visible'; void bubble.offsetWidth; bubble.classList.add('animate-in'); }
        });
    }
    function guideOpen() { guideIdx = 0; guideRender(); }
    function guideClose() { guideClearRing(); if (guideOverlay) guideOverlay.classList.add('hidden'); }
    function guideNext() { if (guideIdx < GUIDE_STEPS.length - 1) { guideIdx++; guideRender(); } else { guideClose(); } }
    function guidePrev() { if (guideIdx > 0) { guideIdx--; guideRender(); } }
    const guideBtn = document.getElementById('admin-tutorial-btn');
    if (guideBtn) guideBtn.addEventListener('click', guideOpen);
    document.getElementById('admin-guide-next')?.addEventListener('click', guideNext);
    document.getElementById('admin-guide-prev')?.addEventListener('click', guidePrev);
    document.getElementById('admin-guide-abort')?.addEventListener('click', guideClose);
    document.addEventListener('keydown', (e) => {
        if (guideOverlay && !guideOverlay.classList.contains('hidden')) {
            if (e.key === 'Escape') guideClose();
            else if (e.key === 'ArrowRight' || e.key === 'Enter') guideNext();
            else if (e.key === 'ArrowLeft') guidePrev();
        }
    });
    const _guideTrack = () => { if (guideHL) { guidePositionRing(guideHL); guidePositionBubble(guideHL); } };
    window.addEventListener('resize', _guideTrack);
    window.addEventListener('scroll', _guideTrack, true);

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
            // v2.3: 導覽教學開啟時，切換語言一併重繪當前步驟（步驟文字由 JS 設定，非 data-i18n）
            const gm = document.getElementById('admin-guide-overlay');
            if (gm && !gm.classList.contains('hidden')) guideRender();
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


// ==============================================================================
// v2.0 LAB ADMIN MODULE — Lab Sessions / Quota / Storage / Audit / Secrets
// ==============================================================================
const adminLab = (() => {
    function esc(s) {
        return String(s ?? '').replace(/[&<>"']/g, m => ({
            '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'
        }[m]));
    }

    async function api(path, opts = {}) {
        const resp = await fetch(`${API_BASE}/admin${path}`, {
            ...opts,
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${authToken}`,
                ...(opts.headers || {}),
            },
        });
        if (resp.status === 401) { handleAuthError(); throw new Error('auth'); }
        if (!resp.ok) {
            const text = await resp.text();
            throw new Error(`HTTP ${resp.status}: ${text.slice(0, 200)}`);
        }
        return resp.status === 204 ? null : resp.json();
    }

    // ── Lab Sessions ─────────────────────────────────────────────────────────
    async function refreshSessions() {
        const tbody = document.querySelector('#admin-lab-sessions-table tbody');
        if (!tbody) return;
        tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;color:var(--text-muted);">Loading…</td></tr>';
        try {
            const data = await api('/lab/sessions');
            const sessions = data.sessions || [];
            if (sessions.length === 0) {
                tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;color:var(--text-muted);">No active sessions</td></tr>';
                return;
            }
            tbody.innerHTML = sessions.map(s => `
                <tr>
                    <td>${esc(s.username || s.user_id)}</td>
                    <td><span class="status-badge status-${esc(s.status)}">${esc(s.status)}</span></td>
                    <td>${esc(s.base_image)}</td>
                    <td>${esc(s.started_at || '—')}</td>
                    <td>${esc(s.last_activity || '—')}</td>
                    <td>${esc(s.cpu_quota || '?')} core · ${esc(s.mem_quota_mb || '?')} MB</td>
                    <td><button class="ready-btn" style="background:rgba(251,113,133,0.1);color:#fb7185;width:auto;padding:4px 10px;font-size:12px;" onclick="adminLab.forceStop('${esc(s.user_id)}')">強制停止</button></td>
                </tr>
            `).join('');
        } catch (e) {
            tbody.innerHTML = `<tr><td colspan="7" style="text-align:center;color:#ef4444;">Error: ${esc(e.message)}</td></tr>`;
        }
    }

    async function forceStop(userId) {
        if (!confirm(`強制停止 ${userId} 的 Lab session？`)) return;
        try {
            await api(`/lab/sessions/${encodeURIComponent(userId)}/force-stop`, { method: 'POST' });
            refreshSessions();
        } catch (e) { alert(`錯誤: ${e.message}`); }
    }

    // ── Quota Grants ─────────────────────────────────────────────────────────
    async function lookupQuota() {
        const userId = document.getElementById('quota-user-id').value.trim();
        if (!userId) { alert('請輸入 user_id'); return; }
        const result = document.getElementById('quota-result');
        result.innerHTML = 'Loading…';
        try {
            const data = await api(`/quota/${encodeURIComponent(userId)}`);
            const grants = (data.grants || []).map(g => `
                <tr>
                    <td>${esc(g.id.slice(0,8))}</td>
                    <td>+${esc(g.extra_quota_gb)} GB</td>
                    <td>${esc(g.reason)}</td>
                    <td>${esc(g.granted_at || '—')}</td>
                    <td>${g.revoked_at ? `<span style="color:var(--text-muted);">revoked</span>` : `<button class="ready-btn" style="background:rgba(251,113,133,0.1);color:#fb7185;width:auto;padding:2px 8px;font-size:11px;" onclick="adminLab.revokeQuota('${esc(g.id)}')">撤銷</button>`}</td>
                </tr>
            `).join('') || '<tr><td colspan="5" style="text-align:center;color:var(--text-muted);">無提權紀錄</td></tr>';
            result.innerHTML = `
                <div style="padding:8px 0; font-size:14px;">
                    <strong>${esc(data.user_id)}</strong> · base = ${esc(data.base_quota_gb)} GB · <strong>effective = ${esc(data.effective_quota_gb)} GB</strong>
                </div>
                <table class="admin-table"><thead><tr><th>ID</th><th>Extra</th><th>Reason</th><th>Granted</th><th>動作</th></tr></thead><tbody>${grants}</tbody></table>
            `;
        } catch (e) { result.innerHTML = `<div style="color:#ef4444;">Error: ${esc(e.message)}</div>`; }
    }

    async function grantQuota() {
        const userId = document.getElementById('quota-user-id').value.trim();
        const extraGb = parseInt(document.getElementById('quota-extra-gb').value, 10);
        const reason = document.getElementById('quota-reason').value.trim();
        if (!userId || !extraGb || extraGb <= 0) { alert('user_id 與 extra GB 為必填'); return; }
        if (reason.length < 5) { alert('reason 至少需 5 字（會寫入 audit log）'); return; }
        try {
            await api('/quota/grant', {
                method: 'POST',
                body: JSON.stringify({ user_id: userId, extra_quota_gb: extraGb, reason }),
            });
            document.getElementById('quota-reason').value = '';
            document.getElementById('quota-extra-gb').value = '';
            lookupQuota();
        } catch (e) { alert(`錯誤: ${e.message}`); }
    }

    async function revokeQuota(grantId) {
        if (!confirm(`撤銷此 grant？`)) return;
        try {
            await api(`/quota/grant/${encodeURIComponent(grantId)}`, { method: 'DELETE' });
            lookupQuota();
        } catch (e) { alert(`錯誤: ${e.message}`); }
    }

    function revokeQuotaSelected() {
        alert('請於下方表格點擊每筆 grant 旁的「撤銷」按鈕');
    }

    // ── Storage Lifecycle ────────────────────────────────────────────────────
    async function refreshStorage() {
        const tbody = document.querySelector('#admin-storage-table tbody');
        if (!tbody) return;
        const filter = document.getElementById('storage-filter').value;
        tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;color:var(--text-muted);">Loading…</td></tr>';
        try {
            const data = await api(`/storage/states${filter ? `?state=${encodeURIComponent(filter)}` : ''}`);
            const rows = data.states || [];
            if (rows.length === 0) {
                tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;color:var(--text-muted);">無紀錄</td></tr>';
                return;
            }
            tbody.innerHTML = rows.map(s => `
                <tr>
                    <td>${esc(s.user_id)}</td>
                    <td><span class="status-badge status-${esc(s.state)}">${esc(s.state)}</span></td>
                    <td>${esc(s.current_size_gb)} GB</td>
                    <td>${esc(s.state_since || '—')}</td>
                    <td>
                        <button class="ready-btn" style="width:auto;padding:2px 8px;font-size:11px;" onclick="adminLab.changeStorageState('${esc(s.user_id)}','freeze')">Freeze</button>
                        <button class="ready-btn" style="width:auto;padding:2px 8px;font-size:11px;" onclick="adminLab.changeStorageState('${esc(s.user_id)}','archive')">Archive</button>
                        <button class="ready-btn" style="width:auto;padding:2px 8px;font-size:11px;" onclick="adminLab.changeStorageState('${esc(s.user_id)}','restore')">Restore</button>
                        <button class="ready-btn" style="background:rgba(251,113,133,0.1);color:#fb7185;width:auto;padding:2px 8px;font-size:11px;" onclick="adminLab.permanentDelete('${esc(s.user_id)}')">⚠ Delete</button>
                    </td>
                </tr>
            `).join('');
        } catch (e) {
            tbody.innerHTML = `<tr><td colspan="5" style="text-align:center;color:#ef4444;">Error: ${esc(e.message)}</td></tr>`;
        }
    }

    async function changeStorageState(userId, action) {
        const reason = prompt(`${action} ${userId} — 請輸入理由 (audit log)：`);
        if (!reason) return;
        try {
            await api(`/storage/${action}`, {
                method: 'POST',
                body: JSON.stringify({ user_id: userId, reason }),
            });
            refreshStorage();
        } catch (e) { alert(`錯誤: ${e.message}`); }
    }

    async function permanentDelete(userId) {
        const reason = prompt(`⚠️ 永久刪除 ${userId} — 請輸入理由 (audit log)：`);
        if (!reason) return;
        const adminPwd = prompt('需驗證 admin 密碼：');
        if (!adminPwd) return;
        if (!confirm(`再次確認永久刪除 ${userId}？此操作不可復原！`)) return;
        try {
            await api('/storage/permanent-delete', {
                method: 'POST',
                body: JSON.stringify({ user_id: userId, reason, admin_password: adminPwd }),
            });
            refreshStorage();
        } catch (e) { alert(`錯誤: ${e.message}`); }
    }

    // ── Audit Log ────────────────────────────────────────────────────────────
    async function refreshAudit() {
        const tbody = document.querySelector('#admin-audit-table tbody');
        if (!tbody) return;
        const action = document.getElementById('audit-filter-action').value.trim();
        const user   = document.getElementById('audit-filter-user').value.trim();
        const params = new URLSearchParams({ limit: '100' });
        if (action) params.set('action', action);
        if (user)   params.set('target_user', user);
        tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;color:var(--text-muted);">Loading…</td></tr>';
        try {
            const data = await api(`/audit?${params}`);
            const items = data.items || [];
            if (items.length === 0) {
                tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;color:var(--text-muted);">無紀錄</td></tr>';
                return;
            }
            tbody.innerHTML = items.map(r => `
                <tr>
                    <td style="font-family:monospace;font-size:11px;">${esc(r.timestamp)}</td>
                    <td>${esc((r.admin_id||'').slice(0,8))}</td>
                    <td>${esc(r.action)}</td>
                    <td>${esc((r.target_user||'').slice(0,8))}</td>
                    <td style="font-family:monospace;font-size:11px;max-width:300px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="${esc(r.payload)}">${esc(r.payload || '')}</td>
                    <td>${esc(r.ip_address || '—')}</td>
                </tr>
            `).join('');
        } catch (e) {
            tbody.innerHTML = `<tr><td colspan="6" style="text-align:center;color:#ef4444;">Error: ${esc(e.message)}</td></tr>`;
        }
    }

    // ── User Secrets Monitor ─────────────────────────────────────────────────
    async function listUserSecrets() {
        const userId = document.getElementById('admin-secret-user').value.trim();
        if (!userId) { alert('請輸入 user_id'); return; }
        const result = document.getElementById('admin-secrets-result');
        result.innerHTML = 'Loading…';
        try {
            const data = await api(`/secrets/${encodeURIComponent(userId)}/names`);
            const items = data.secrets || [];
            if (items.length === 0) {
                result.innerHTML = '<div style="color:var(--text-muted);text-align:center;padding:12px;">該使用者尚無 secrets</div>';
                return;
            }
            result.innerHTML = `
                <table class="admin-table">
                    <thead><tr><th>Name</th><th>Masked</th><th>Updated</th><th>動作</th></tr></thead>
                    <tbody>${items.map(s => `
                        <tr>
                            <td>${esc(s.name)}</td>
                            <td style="font-family:monospace;">${esc(s.masked_value || '****')}</td>
                            <td style="font-size:12px;">${esc(s.updated_at || '—')}</td>
                            <td><button class="ready-btn" style="background:rgba(251,113,133,0.1);color:#fb7185;width:auto;padding:2px 8px;font-size:11px;" onclick="adminLab.deleteUserSecret('${esc(userId)}','${esc(s.name)}')">刪除</button></td>
                        </tr>
                    `).join('')}</tbody>
                </table>
            `;
        } catch (e) { result.innerHTML = `<div style="color:#ef4444;">Error: ${esc(e.message)}</div>`; }
    }

    async function deleteUserSecret(userId, name) {
        if (!confirm(`刪除 ${userId} 的 secret "${name}"？管理員無法看到 value，但可以刪除。`)) return;
        try {
            await api(`/secrets/${encodeURIComponent(userId)}/${encodeURIComponent(name)}`, { method: 'DELETE' });
            listUserSecrets();
        } catch (e) { alert(`錯誤: ${e.message}`); }
    }

    // ── Init ─────────────────────────────────────────────────────────────────
    let _initialized = false;
    function init() {
        if (_initialized) {
            refreshSessions();
            return;
        }
        _initialized = true;
        refreshSessions();
        refreshStorage();
    }

    return {
        init, refreshSessions, forceStop,
        lookupQuota, grantQuota, revokeQuota, revokeQuotaSelected,
        refreshStorage, changeStorageState, permanentDelete,
        refreshAudit,
        listUserSecrets, deleteUserSecret,
    };
})();
window.adminLab = adminLab;
