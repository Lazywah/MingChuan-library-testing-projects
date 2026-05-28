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
        forgot_password: "忘記密碼",
        forgot_password_desc: "請輸入您的帳號與信箱以重設密碼",
        btn_reset_pwd: "重設密碼",
        temp_pwd_desc: "您的臨時密碼為：",
        temp_pwd_warning: "請使用此密碼登入後，盡速於設定中更改您的密碼。",
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
        compute_high: "大型訓練",
        compute_mid_low: "快速作業",
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
        ql_lab_title: "AI Base Lab",
        ql_lab_desc: "VS Code in Browser + Run on GPU",
        anno_loading: "載入公告中...",
        anno_empty: "目前沒有公告",
        anno_load_failed: "公告載入失敗",
        // v2.2: 本機帳號 fallback 登入
        local_login_summary: "沒有學校帳號？",
        local_login_hint: "本機帳號登入 — 請聯絡老師或管理員取得帳號。",
        label_username: "帳號",
        label_password: "密碼",
        btn_local_login: "登入",
        local_login_empty: "請輸入帳號與密碼",
        local_login_failed: "登入失敗：",
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
        doc_coming_soon: "內容建置中，敬請期待...",
        // 工具提示
        tooltip_toggle_lang: "切換語言",
        tooltip_toggle_theme: "切換主題",
        // 資料集上傳
        msg_uploading: "上傳中...",
        toast_upload_ok: "檔案已上傳並推薦參數",
        toast_upload_failed: "上傳失敗",
        // 忘記密碼
        msg_pwd_emailed: "臨時密碼已寄至您的信箱，請查收後盡快登入並修改。",
        // AI 聊天串流
        prefix_system_reject: "[系統拒絕]",
        error_quota_exceeded: "您的 Token 額度已用盡，請聯繫管理員擴充額度。",
        prefix_system_notice: "[系統提示]",
        error_stream_interrupted: "連線意外中斷或發生錯誤",
        // 任務日誌
        error_stream_failed: "無法連線至日誌串流",
        msg_job_status: "任務完成，狀態",
        error_stream_disconnected: "已從日誌串流中斷開",
        // 收斂曲線圖
        chart_label_training_loss: "訓練損失",
        chart_label_epoch: "訓練週期",
        chart_label_loss: "損失值",
        // Session 操作
        confirm_delete_session: "確定要刪除此對話？",
        prompt_rename_session: "請輸入新名稱：",
        // Notebook 子分頁標題（v1 nb_* 鍵已隨 Lab launcher 移除）
        compute_notebook: "Notebook",
        // v2.0 Lab launcher
        lab_title: "AI Base Lab",
        lab_subtitle: "在瀏覽器內使用完整的 VS Code 環境，含終端機、檔案總管、Notebook 編輯與 Run on GPU。",
        lab_status_label: "狀態 Status：",
        lab_status_loading: "載入中…",
        lab_status_stopped: "未啟動 Stopped",
        lab_status_starting: "啟動中… Starting…",
        lab_status_running: "已啟動 Running",
        lab_status_error: "錯誤 Error",
        lab_image_label: "Image：",
        lab_quota_label: "配額 Quota：",
        lab_remaining_label: "今日剩餘 Remaining：",
        lab_minutes: "分鐘",
        lab_image_select: "選擇 Image：",
        lab_open: "開啟 Notebook",
        lab_enter: "進入 Notebook",
        lab_stop: "停止 Session",
        lab_stop_confirm: "確認停止 Notebook session？檔案會保留。",
        lab_tip_1: "💡 第一次開啟會約 5–10 秒建立容器；之後 idle 30 分鐘自動關閉，檔案永久保留於個人 volume。",
        lab_tip_2: "💡 在 code-server 內寫完程式碼後，右鍵「AI Base: Run on GPU」即可送到 GPU 訓練，輸出會串流回 VS Code Output Panel。",
        lab_tip_3: "💡 共用模型快取在 /opt/models（read-only），自己的 pip 套件用 pip install --user 安裝到 ~/.local/ 永久保留。",
        // v2.0 Secrets management
        settings_secrets: "Secrets 管理",
        secrets_desc: "在這裡新增 API key 等敏感資訊（HF_TOKEN、WANDB_API_KEY 等），提交 GPU 任務時自動注入到容器環境變數。",
        secrets_name_placeholder: "名稱（例：HF_TOKEN）",
        secrets_value_placeholder: "值（vault 加密儲存）",
        secrets_add: "新增",
        secrets_empty: "尚未設定任何 secret",
        secrets_load_fail: "載入 Secrets 失敗",
        secrets_save_ok: "Secret 已儲存",
        secrets_delete_confirm: "確認刪除這個 secret？",
        // v2.1 SSO OIDC 整合
        login_title: "登入系統",
        sso_school_login: "使用學校帳號登入",
        sso_hint: "學生 / 老師請使用學校 Microsoft 帳號（學號@mcu.edu.tw）",
        sso_loading: "載入中…",
        sso_pending_msg: "系統登入功能尚在設定中",
        sso_pending_hint: "若您是管理員，請透過管理介面登入",
        auth_required_to_use: "請先登入才能使用此功能",
        lab_tip_secrets: "🔐 需要 API 金鑰嗎？到「設定 → Secrets 管理」新增（例：HF_TOKEN、OPENAI_API_KEY），啟動 Lab / 送 GPU 任務時會自動以環境變數注入容器。",
        lab_tip_secrets_link: "前往設定",
        secrets_help_summary: "什麼是環境變數？為什麼這樣設計？",
        secrets_help_body: "環境變數是程式啟動時從作業系統環境讀的「鍵 = 值」對。把金鑰寫死在程式碼會被誤 commit 到 git 外洩，所以業界做法是統一存在 Secrets 機制中、執行時注入。可以類比 Chrome 密碼管理員 — 程式不用知道密碼，只在需要時自動填入。本平台用 AES-256-GCM 加密儲存，僅在 Lab 容器啟動 / GPU 任務執行時解密注入。",
        password_sso_msg: "您使用學校 Microsoft 帳號登入，密碼由學校統一管理。",
        password_sso_open: "前往 Microsoft 變更密碼（新分頁）",
        password_sso_forgot: "忘記密碼？點此重設",
        password_sso_why: "為什麼不能在這裡改？",
        password_sso_why_explain: "學校採用單一登入 (SSO) 機制，您的密碼存在學校的 Microsoft 系統，本平台從未拿到您的密碼。這是業界標準的安全設計（Slack / Notion / Figma 等使用 SSO 的服務都是如此）。",
        toast_sso_password_blocked: "SSO 使用者無法在此變更密碼，請至 IdP 系統變更",
        // v2.1 Profile Modal 豐富資訊版
        settings_profile: "我的帳號資訊",
        profile_basic: "基本資訊",
        profile_auth: "認證與登入",
        profile_usage: "Token 用量",
        profile_editable: "變更個人資訊",
        label_role: "角色",
        label_department: "學系",
        label_auth_source: "認證來源",
        label_last_login: "最後登入",
        label_last_ip: "登入 IP",
        label_login_count: "累計登入次數",
        label_created_at: "帳號建立",
        label_lifetime_tokens: "歷史累計用量",
        label_reset_date: "下次重置",
        btn_update_profile: "儲存變更",
        profile_desc: "💡 此處變更會即時套用至帳號。要變更密碼請使用上方選單的「變更密碼」。",
        // v2.1 Password Modal 加強
        label_confirm_password: "確認新密碼",
        password_mismatch: "⚠ 兩次輸入的密碼不一致",
        password_too_short: "密碼長度需至少 8 字元",
        password_mismatch_toast: "兩次輸入的密碼不一致，請重新確認",
        password_strength_weak: "弱",
        password_strength_medium: "中",
        password_strength_strong: "強",
        password_strength_vstrong: "極強"
    },
    en: {
        login_title: "System Login",
        label_username: "Username",
        label_password: "Password",
        btn_login: "Login",
        forgot_password: "Forgot Password",
        forgot_password_desc: "Please enter your Username and Email to reset.",
        btn_reset_pwd: "Reset Password",
        temp_pwd_desc: "Your temporary password is:",
        temp_pwd_warning: "Please login with this password and change it immediately.",
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
        compute_high: "Large Training",
        compute_mid_low: "Quick Tasks",
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
        ql_lab_title: "AI Base Lab",
        ql_lab_desc: "VS Code in Browser + Run on GPU",
        anno_loading: "Loading announcements...",
        anno_empty: "No announcements at the moment",
        anno_load_failed: "Failed to load announcements",
        // v2.2: Local account fallback login
        local_login_summary: "No school account?",
        local_login_hint: "Local account login — please contact teacher or admin for credentials.",
        label_username: "Username",
        label_password: "Password",
        btn_local_login: "Sign In",
        local_login_empty: "Please enter username and password",
        local_login_failed: "Login failed: ",
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
        doc_coming_soon: "Content under construction, stay tuned...",
        // Tooltips
        tooltip_toggle_lang: "Switch Language",
        tooltip_toggle_theme: "Switch Theme",
        // Dataset upload
        msg_uploading: "Uploading...",
        toast_upload_ok: "File uploaded & parameters suggested",
        toast_upload_failed: "Upload failed",
        // Forgot password
        msg_pwd_emailed: "A temporary password has been sent to your email. Please log in and change it as soon as possible.",
        // AI chat stream
        prefix_system_reject: "[System Rejected]",
        error_quota_exceeded: "Your token quota has been exhausted. Please contact your administrator to increase your limit.",
        prefix_system_notice: "[System Notice]",
        error_stream_interrupted: "Connection unexpectedly interrupted or an error occurred",
        // Job logs
        error_stream_failed: "Failed to connect to log stream",
        msg_job_status: "Job finished with status",
        error_stream_disconnected: "Disconnected from log stream",
        // Loss chart
        chart_label_training_loss: "Training Loss",
        chart_label_epoch: "Epoch",
        chart_label_loss: "Loss",
        // Session actions
        confirm_delete_session: "Delete this session?",
        prompt_rename_session: "Enter new name:",
        // Notebook sub-tab label (v1 nb_* keys removed in Phase E along with Lab launcher)
        compute_notebook: "Notebook",
        // v2.0 Lab launcher
        lab_title: "AI Base Lab",
        lab_subtitle: "Full VS Code in your browser — terminal, file explorer, notebooks, and Run on GPU.",
        lab_status_label: "Status:",
        lab_status_loading: "Loading…",
        lab_status_stopped: "Stopped",
        lab_status_starting: "Starting…",
        lab_status_running: "Running",
        lab_status_error: "Error",
        lab_image_label: "Image:",
        lab_quota_label: "Quota:",
        lab_remaining_label: "Today remaining:",
        lab_minutes: "min",
        lab_image_select: "Pick Image:",
        lab_open: "Open Notebook",
        lab_enter: "Enter Notebook",
        lab_stop: "Stop Session",
        lab_stop_confirm: "Stop this Notebook session? Your files are preserved.",
        lab_tip_1: "💡 First launch takes ~5–10s; idle 30 min auto-stops, files persist in your volume.",
        lab_tip_2: "💡 In code-server, right-click → 'AI Base: Run on GPU' submits to the GPU cluster; output streams back to the VS Code Output Panel.",
        lab_tip_3: "💡 Shared model cache is at /opt/models (read-only); install your pip packages with `pip install --user` to ~/.local/ for persistence.",
        // v2.0 Secrets management
        settings_secrets: "Secrets Management",
        secrets_desc: "Store API keys (HF_TOKEN, WANDB_API_KEY, etc.). They're auto-injected as env vars when you submit a GPU job.",
        secrets_name_placeholder: "Name (e.g. HF_TOKEN)",
        secrets_value_placeholder: "Value (encrypted at rest)",
        secrets_add: "Add",
        secrets_empty: "No secrets configured yet",
        secrets_load_fail: "Failed to load secrets",
        secrets_save_ok: "Secret saved",
        secrets_delete_confirm: "Delete this secret?",
        // v2.1 SSO OIDC integration
        login_title: "Sign in",
        sso_school_login: "Sign in with school account",
        sso_hint: "Students / teachers: use your school Microsoft account (studentid@mcu.edu.tw)",
        sso_loading: "Loading…",
        sso_pending_msg: "Login system is being configured",
        sso_pending_hint: "Administrators please use the admin panel to log in",
        auth_required_to_use: "Please sign in to use this feature",
        lab_tip_secrets: "🔐 Need an API key? Add it in Settings → Secrets (e.g. HF_TOKEN, OPENAI_API_KEY). It will be injected as an environment variable into your Lab container and GPU jobs automatically.",
        lab_tip_secrets_link: "Open settings",
        secrets_help_summary: "What are environment variables and why this design?",
        secrets_help_body: "Environment variables are key=value pairs read from the OS environment when a program starts. Hard-coding keys in source code risks committing them to git. The industry pattern is to keep them in a Secrets store and inject at runtime — like Chrome's password manager: programs don't know your password, the system fills it in when needed. This platform uses AES-256-GCM encryption at rest and decrypts only when the Lab container starts or a GPU job runs.",
        password_sso_msg: "You are signed in with your school Microsoft account; passwords are managed by the school.",
        password_sso_open: "Open Microsoft password change (new tab)",
        password_sso_forgot: "Forgot password? Reset here",
        password_sso_why: "Why can't I change it here?",
        password_sso_why_explain: "The school uses Single Sign-On (SSO); your password lives at Microsoft and this platform never sees it. This is the industry-standard design (Slack / Notion / Figma all do the same).",
        toast_sso_password_blocked: "SSO users cannot change password here — please use the IdP",
        // v2.1 Profile Modal rich info
        settings_profile: "My Account",
        profile_basic: "Basic Info",
        profile_auth: "Authentication",
        profile_usage: "Token Usage",
        profile_editable: "Edit Profile",
        label_role: "Role",
        label_department: "Department",
        label_auth_source: "Auth Source",
        label_last_login: "Last Login",
        label_last_ip: "Last IP",
        label_login_count: "Login Count",
        label_created_at: "Account Created",
        label_lifetime_tokens: "Lifetime Tokens",
        label_reset_date: "Next Reset",
        btn_update_profile: "Save Changes",
        profile_desc: "💡 Changes apply immediately. To change password, use the 'Change Password' option in the menu.",
        // v2.1 Password Modal enhancements
        label_confirm_password: "Confirm New Password",
        password_mismatch: "⚠ Passwords do not match",
        password_too_short: "Password must be at least 8 characters",
        password_mismatch_toast: "Passwords do not match, please retype",
        password_strength_weak: "Weak",
        password_strength_medium: "Medium",
        password_strength_strong: "Strong",
        password_strength_vstrong: "Very Strong"
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
const loginForm = document.getElementById('login-form');  // v2.1: form 仍存在但無 submit 行為（已改 SSO 按鈕觸發）
// v2.1: loginBtn 已移除（user UI 不再有 username/password 提交按鈕；admin 走 port 8888）
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
// v2.1: profile-update-form 已從 user UI 移除 — 個人資料變更須由 admin 或學校 SSO 端處理

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
        btn.addEventListener('click', async () => {
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

    // ZH: 下拉選單內的 Profile / Password 按鈕綁定 | EN: Bind Profile/Password buttons in dropdown
    const navProfileBtn = document.getElementById('nav-profile-btn');
    const profileModal = document.getElementById('profile-modal');
    if (navProfileBtn && profileModal) {
        navProfileBtn.addEventListener('click', async () => {
            profileModal.classList.remove('hidden');
            if (userDropdownMenu) userDropdownMenu.style.display = 'none';
            // v2.1: 開啟時 fetch 最新資料並渲染豐富版資訊
            await refreshCurrentUserData();
            renderProfileInfo();
        });
        document.getElementById('profile-close-btn').addEventListener('click', () => profileModal.classList.add('hidden'));
        document.getElementById('profile-backdrop').addEventListener('click', () => profileModal.classList.add('hidden'));
    }

    const navPasswordBtn = document.getElementById('nav-password-btn');
    const passwordModal = document.getElementById('password-modal');
    if (navPasswordBtn && passwordModal) {
        navPasswordBtn.addEventListener('click', () => {
            passwordModal.classList.remove('hidden');
            if (userDropdownMenu) userDropdownMenu.style.display = 'none';
        });
        document.getElementById('password-close-btn').addEventListener('click', () => passwordModal.classList.add('hidden'));
        document.getElementById('password-backdrop').addEventListener('click', () => passwordModal.classList.add('hidden'));
    }

    const navAdminBtn = document.getElementById('nav-admin-btn');
    if (navAdminBtn) {
        navAdminBtn.addEventListener('click', () => {
            // ZH: 導向管理面板前，確保 admin_hud_token 有值 | EN: Ensure admin_hud_token is set before redirect
            if (authToken) {
                localStorage.setItem('admin_hud_token', authToken);
            }
            window.location.href = window.location.protocol + '//' + window.location.hostname + ':8888/';
        });
    }

    newChatBtn.addEventListener('click', createNewSession);

    const jobFormHigh = document.getElementById('job-form-high');
    const jobFormMidLow = document.getElementById('job-form-midlow');
    if (jobFormHigh) jobFormHigh.addEventListener('submit', (e) => handleJobSubmit(e, 2, 'job-form-high'));
    if (jobFormMidLow) jobFormMidLow.addEventListener('submit', (e) => handleJobSubmit(e, 1, 'job-form-midlow'));

    // v2.1: profile-update-form 已移除 — 不再綁定 handleProfileUpdate
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
            // 停止冒泡，避免被下面的「點外面收起」listener 立刻又關掉
            e.stopPropagation();
            sideDrawer.classList.toggle('closed');
        });

        // v2.1 UX: 點 sidebar 外部 + 目前是展開狀態 → 自動收起
        document.addEventListener('click', (e) => {
            // 已收起就不用管
            if (sideDrawer.classList.contains('closed')) return;
            // 點在 sidebar 內部 → 略過
            if (sideDrawer.contains(e.target)) return;
            // 點在 toggle 按鈕本身（理論上 stopPropagation 已擋下但保險）→ 略過
            if (sideDrawerToggle.contains(e.target)) return;
            sideDrawer.classList.add('closed');
        });
    }

    // v2.2: 本機帳號 fallback 登入表單
    const localLoginBtn = document.getElementById('local-login-btn');
    if (localLoginBtn) {
        localLoginBtn.addEventListener('click', async () => {
            const usernameInput = document.getElementById('local-username');
            const passwordInput = document.getElementById('local-password');
            const errEl = document.getElementById('local-login-error');
            const username = (usernameInput?.value || '').trim();
            const password = passwordInput?.value || '';
            if (!username || !password) {
                errEl.textContent = t('local_login_empty') || '請輸入帳號與密碼';
                return;
            }
            localLoginBtn.disabled = true;
            errEl.textContent = '';
            try {
                const body = new URLSearchParams({ username, password });
                const res = await fetch(`${API_BASE}/auth/login`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                    body: body.toString(),
                    credentials: 'include',
                });
                if (!res.ok) {
                    const err = await res.json().catch(() => ({ detail: 'login failed' }));
                    throw new Error(err.detail || 'login failed');
                }
                const data = await res.json();
                localStorage.setItem('ai_hud_token', data.access_token);
                authToken = data.access_token;
                if (passwordInput) passwordInput.value = '';
                window.location.href = '/train/';
            } catch (e) {
                errEl.textContent = (t('local_login_failed') || '登入失敗：') + e.message;
            } finally {
                localLoginBtn.disabled = false;
            }
        });
        // Enter 鍵也能送出
        ['local-username', 'local-password'].forEach(id => {
            const el = document.getElementById(id);
            if (el) el.addEventListener('keypress', (e) => {
                if (e.key === 'Enter') { e.preventDefault(); localLoginBtn.click(); }
            });
        });
    }

    // v2.2: Quick Link「AI Base Lab」→ 跳到 Compute → Notebook 分頁
    const qlLabGo = document.getElementById('ql-lab-go');
    if (qlLabGo) {
        qlLabGo.addEventListener('click', (e) => {
            e.preventDefault();
            if (!authToken) {
                if (typeof showToast === 'function') showToast('auth_required_to_use', 'warning');
                return;
            }
            switchTab('dashboard');
            setTimeout(() => {
                const subTab = document.getElementById('sub-tab-notebook');
                if (subTab) subTab.click();
            }, 100);
        });
    }

    // v2.1: 從 Lab 卡片快速跳到 Settings → Secrets 區塊
    const labJumpToSecrets = document.getElementById('lab-jump-to-secrets');
    if (labJumpToSecrets) {
        labJumpToSecrets.addEventListener('click', (e) => {
            e.preventDefault();
            if (!authToken) {
                if (typeof showToast === 'function') showToast('auth_required_to_use', 'warning');
                return;
            }
            switchTab('settings');
            // 等 DOM 渲染完再 scroll，避免 page-view active 切換時還沒佈局好
            setTimeout(() => {
                const sec = document.getElementById('secrets-section');
                if (sec) sec.scrollIntoView({ behavior: 'smooth', block: 'start' });
            }, 80);
        });
    }

    // v2.1 UX: 滑鼠滾輪覆蓋全頁面 — 即使滑到 sidebar / header 上滾動也能捲動主內容區
    // body 是 overflow:hidden，內容靠 .page-view.active 內部捲動；以下將外部 wheel 事件轉發進去
    document.addEventListener('wheel', (e) => {
        // 找出當下活躍的主內容區
        const activePane = document.querySelector('.page-view.active');
        if (!activePane) return;
        // 事件起源已經在可捲動容器內 → 讓瀏覽器自己處理，不要重複捲
        let node = e.target;
        while (node && node !== document.body) {
            if (node === activePane) return;            // 起源就在 activePane → 略過
            // 起源在其他自帶 scroll 的容器（modal / dropdown 等）→ 也略過
            const style = node.nodeType === 1 ? window.getComputedStyle(node) : null;
            if (style && /(auto|scroll)/.test(style.overflowY) && node.scrollHeight > node.clientHeight) {
                return;
            }
            node = node.parentNode;
        }
        // 起源在 body / sidebar / header → 強制把 deltaY 轉發給 activePane
        activePane.scrollBy({ top: e.deltaY, behavior: 'auto' });
    }, { passive: true });

    // v2.1: Password Eye Toggle 區段已移除（HTML 內 #eye-toggle / #password 已刪）
    // 原因：user UI 不再有 username/password 輸入框，admin 走 port 8888 admin-ui

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

    // ZH: 忘記密碼相關綁定 | EN: Forgot password bindings
    // v2.1: #forgot-pwd-link 已從 user UI 移除（無本機 username/password 入口）
    //       但 #forgot-pwd-modal HTML 與 form handler 保留供 admin-ui 使用
    const forgotPwdModal = document.getElementById('forgot-pwd-modal');
    const forgotPwdCloseBtn = document.getElementById('forgot-pwd-close-btn');
    const forgotPwdForm = document.getElementById('forgot-pwd-form');

    if (forgotPwdCloseBtn && forgotPwdModal) {
        forgotPwdCloseBtn.addEventListener('click', () => {
            forgotPwdModal.classList.add('hidden');
            document.getElementById('temp-pwd-result').classList.add('hidden');
        });
    }

    if (forgotPwdForm) {
        forgotPwdForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const uname = document.getElementById('forgot-username').value;
            const email = document.getElementById('forgot-email').value;
            const btn = document.getElementById('forgot-pwd-submit-btn');
            btn.disabled = true;

            try {
                const res = await fetch(`${API_BASE}/auth/forgot-password`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ username: uname, email: email })
                });

                if (!res.ok) {
                    const err = await res.json();
                    throw new Error(err.detail || 'Reset failed');
                }

                const data = await res.json();
                // C-11: ZH: 若 SMTP 未設定，後端回傳 temp_password；已設定則回傳 null (密碼寄至信箱)
                // EN: When SMTP is not configured the backend returns temp_password; configured → null (emailed)
                const pwdDisplay = document.getElementById('temp-pwd-display');
                const pwdResult = document.getElementById('temp-pwd-result');
                if (data.temp_password) {
                    // ZH: SMTP 未設定，直接顯示臨時密碼 | EN: SMTP not configured — display directly
                    pwdDisplay.textContent = data.temp_password;
                    pwdDisplay.style.display = '';
                    pwdResult.querySelector('[data-i18n="temp_pwd_desc"]').textContent =
                        t('temp_pwd_desc');
                } else {
                    // ZH: 密碼已寄出，不顯示 | EN: Password emailed — hide the code block
                    pwdDisplay.textContent = '';
                    pwdDisplay.style.display = 'none';
                    pwdResult.querySelector('[data-i18n="temp_pwd_desc"]').textContent =
                        t('msg_pwd_emailed');
                }
                pwdResult.classList.remove('hidden');
                showToast('toast_auth_ok');
            } catch (err) {
                console.error(err);
                showToast(err.message, true);
            } finally {
                btn.disabled = false;
            }
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

// ZH: v2.1 P0 安全 — 需登入才能進入的 tab 白名單
// EN: v2.1 P0 security — auth-gated tab whitelist
const AUTH_GATED_TABS = ['dashboard', 'assistant', 'settings'];

function switchTab(tabId) {
    // ZH: v2.1 P0 安全 — 未登入時擋下需登入的 tab，避免可從 console 或瀏覽器歷史繞過
    // EN: v2.1 P0 security — block auth-gated tabs when not logged in
    if (!authToken && AUTH_GATED_TABS.includes(tabId)) {
        console.warn(`[auth] Attempted to switch to gated tab "${tabId}" without auth — redirecting to home`);
        // 給使用者一個明確提示（如果 i18n 有 key 就用，否則退回中文）
        try {
            const msg = (typeof t === 'function' ? t('auth_required_to_use') : null) || '請先登入才能使用此功能';
            if (typeof showToast === 'function') {
                showToast(msg, 'warning');
            } else {
                alert(msg);
            }
        } catch (_) { /* 提示失敗不影響 redirect */ }
        tabId = 'home';
    }

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
    const newName = prompt(t('prompt_rename_session'), sessions.find(s => s.id === id).name);
    if (newName) {
        sessions.find(s => s.id === id).name = newName;
        saveSessions();
        renderSessions();
    }
}

function deleteSession(e, id) {
    e.stopPropagation();
    if (!confirm(t('confirm_delete_session'))) return;

    sessions = sessions.filter(s => s.id !== id);

    // If no sessions left, create a new one automatically
    if (sessions.length === 0) {
        const newId = 'sess_' + Date.now();
        sessions.unshift({ id: newId, name: t('new_session_name'), messages: [] });
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
    document.querySelectorAll('[data-i18n-title]').forEach(el => {
        const key = el.getAttribute('data-i18n-title');
        if (dict[key]) el.setAttribute('title', dict[key]);
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
// ZH: 身份驗證 — v2.1 改走 SSO（user UI 不再有本機 username/password 提交）
// EN: Authentication — v2.1 SSO-only on user UI
// =========================
// 既有本機 /api/v1/auth/login POST 邏輯已搬到 admin-ui (port 8888)。
// User UI 透過 SSO 取得 token，由 setupSSOLogin() 處理（見下方）。

async function checkAuth() {
    try {
        const res = await fetch(`${API_BASE}/auth/me`, {
            headers: { 'Authorization': `Bearer ${authToken}` }
        });
        if (!res.ok) throw new Error('expired');
        const userData = await res.json();

        // ZH: 管理員不再自動導向，允許使用使用者大廳 | EN: Admin can now use the user hub
        // if (userData.role === 'admin') ...

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

    // ZH: v2.1 P0 安全 — 隱藏對應的 content pane，避免 hash / 直接 DOM 操作繞過 tab
    // EN: v2.1 P0 security — hide content panes too, so URL hash / DOM ops can't bypass
    const authPages = ['dashboard-page', 'assistant-page', 'settings-page'];
    authPages.forEach(id => {
        const el = document.getElementById(id);
        if (!el) return;
        if (show) {
            // 登入：移除 force-hidden（active class 由 switchTab 自己管）
            el.classList.remove('auth-locked');
        } else {
            // 未登入：強制隱藏 + 移除 active（即使先前是當前 tab）
            el.classList.add('auth-locked');
            el.classList.remove('active');
        }
    });

    // ZH: 若目前 active tab 是 auth-gated 而使用者登出 → 強制回 home
    // EN: If current active tab is auth-gated and user logs out → force back to home
    if (!show) {
        const activePage = document.querySelector('.page-view.active');
        if (!activePage || ['dashboard-page', 'assistant-page', 'settings-page'].includes(activePage.id)) {
            // 直接呼叫 switchTab('home') 會再過 guard，但這時 !authToken 已成立、本就會跑去 home，無害
            if (typeof switchTab === 'function') switchTab('home');
        }
    }
}

// =========================
// ZH: 儀表板與任務邏輯 | EN: Dashboard & Jobs
// =========================
async function fetchDashboardData() {
    await Promise.all([fetchUserProfile(), fetchTokenUsage(), fetchJobs(), fetchAnnouncements()]);
}

// v2.2: 拉動態公告 (admin 在 admin UI 可編輯)
async function fetchAnnouncements() {
    const listEl = document.getElementById('announcement-list');
    if (!listEl) return;
    try {
        const res = await fetch(`${API_BASE}/announcements?limit=10`, {
            headers: { 'Authorization': `Bearer ${authToken}` },
        });
        if (!res.ok) throw new Error('HTTP ' + res.status);
        const items = await res.json();
        renderAnnouncements(items);
    } catch (e) {
        console.error('Error fetching announcements:', e);
        listEl.innerHTML = `<div class="announcement-item"><p style="color: var(--text-muted); text-align: center; padding: 12px;">${t('anno_load_failed') || '公告載入失敗'}</p></div>`;
    }
}

function renderAnnouncements(items) {
    const listEl = document.getElementById('announcement-list');
    if (!listEl) return;
    if (!items || items.length === 0) {
        listEl.innerHTML = `<div class="announcement-item"><p style="color: var(--text-muted); text-align: center; padding: 20px;">${t('anno_empty') || '目前沒有公告'}</p></div>`;
        return;
    }
    listEl.innerHTML = items.map(a => {
        const dt = new Date(a.posted_at);
        const dateStr = `${dt.getFullYear()}-${String(dt.getMonth()+1).padStart(2,'0')}-${String(dt.getDate()).padStart(2,'0')}`;
        const titleEl = document.createElement('span');
        titleEl.textContent = a.title;
        const bodyEl = document.createElement('p');
        bodyEl.textContent = a.body;
        const pinned = a.is_pinned ? '<ion-icon name="pin" style="color:var(--neon-yellow); margin-right:4px; vertical-align:middle;" title="置頂"></ion-icon>' : '';
        return `
            <div class="announcement-item">
                <span class="date">${dateStr}</span>
                <p>${pinned}<strong>${titleEl.outerHTML.replace(/<\/?span>/g, '')}</strong> — ${bodyEl.outerHTML.replace(/<\/?p>/g, '')}</p>
            </div>
        `;
    }).join('');
}

async function fetchUserProfile() {
    const res = await fetch(`${API_BASE}/auth/me`, { headers: { 'Authorization': `Bearer ${authToken}` } });
    if (res.ok) {
        const data = await res.json();
        if (userDisplay) userDisplay.textContent = data.username;
        if (userRole) userRole.textContent = data.role.toUpperCase();
        
        // ZH: 顯示或隱藏管理員面板按鈕 | EN: Toggle admin panel button
        const navAdminBtn = document.getElementById('nav-admin-btn');
        if (navAdminBtn) {
            navAdminBtn.style.display = data.role === 'admin' ? 'flex' : 'none';
        }

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
    if (drawerTokenUsed) drawerTokenUsed.textContent = String(data.tokens_used || 0).padStart(8, ' ');
    if (drawerTokenLimit) drawerTokenLimit.textContent = String(data.tokens_limit || 0).padStart(8, ' ');

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
        const res = await fetch(`${API_BASE}/jobs`, {
            headers: { 'Authorization': `Bearer ${authToken}` }
        });

        if (!res.ok) {
            renderJobs([]);
            return;
        }

        const data = await res.json();
        // C-10: ZH: API 回傳 {total, jobs:[...]}，修正之前錯誤的 data.items 取值
        // EN: API returns {total, jobs:[...]} — fix incorrect data.items key
        const jobs = data.jobs || [];
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
            // C-7: ZH: 結構 HTML 用 innerHTML（無使用者輸入），動態文字用 textContent 防 XSS
            // EN: Static structure via innerHTML (no user input); user-supplied text via textContent to prevent XSS
            card.innerHTML = `
                <div class="job-head">
                    <div class="job-info">
                        <span class="job-title"></span>
                        <span class="job-id"></span>
                    </div>
                    <span class="job-status" style="background:${statusBg}; border:1px solid ${statusColor}; color:${statusColor};">
                        ${t(`status_${jobStatus.toLowerCase()}`) || jobStatus.toUpperCase()}
                    </span>
                </div>
                <div class="job-meta">
                    <span class="job-model"></span>
                    <span class="job-priority">Priority: ${job.priority || 0}</span>
                </div>
                <div class="job-progress-bar"><div class="job-progress-fill" style="width:${jobProgress}%"></div></div>
                <div style="margin-top: 10px; text-align: right;">
                    <button class="ready-btn" style="padding: 4px 10px; font-size: 0.8em; min-width: auto; width: auto;" data-i18n="btn_view_details">查看詳情</button>
                </div>
            `;
            // C-7: ZH: 用 textContent 寫入使用者可控的欄位，確保不被解析為 HTML
            // EN: Use textContent for user-controlled fields — never parsed as HTML
            card.querySelector('.job-title').textContent = jobName;
            card.querySelector('.job-id').textContent = `ID: ${jobId}`;
            card.querySelector('.job-model').textContent = modelName;
            // C-7: ZH: 用 addEventListener 取代 onclick 屬性，避免 jobId 逃逸引號
            // EN: Use addEventListener instead of inline onclick to avoid jobId string-escape
            card.querySelector('button.ready-btn').addEventListener('click', () => openJobDetails(jobId));
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
    btn.innerHTML = `<span class="spinner" style="margin-right:5px"></span><span>${t('msg_uploading')}</span>`;
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
        
        showToast('toast_upload_ok');
    } catch (err) {
        console.error(err);
        showToast('toast_upload_failed', true);
        e.target.value = '';
    } finally {
        btn.innerHTML = originalText;
        btn.disabled = false;
    }
}

// v2.1: handleProfileUpdate() 已移除
// 個人資訊變更須由管理者或學校 SSO 端進行，user UI 不再提供自助修改入口
// 後端 PUT /api/v1/auth/me 端點保留供 admin UI 使用

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
                    stream: true,
                    session_id: activeSessionId
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
                                const errMsg = json.error === 'Token quota exceeded'
                                    ? t('error_quota_exceeded')
                                    : json.error;
                                aiFullText = `${t('prefix_system_reject')}: ${errMsg}`;
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
            const errorHint = `<br><br><span style="color: #ff4d4f; font-size: 13px; font-weight: bold;">${t('prefix_system_notice')}: ${t('error_stream_interrupted')} (${err.message})</span>`;
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
    // C-8: ZH: 使用 textContent 防止歷史訊息中的 HTML 注入
    // EN: Use textContent to prevent HTML injection from chat history content
    const bubbleContent = document.createElement('div');
    bubbleContent.className = 'bubble-content';
    bubbleContent.textContent = content;
    div.appendChild(bubbleContent);
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
                label: t('chart_label_training_loss'),
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
                    title: { display: true, text: t('chart_label_epoch'), color: 'rgba(255,255,255,0.7)' },
                    grid: { color: 'rgba(255,255,255,0.1)' },
                    ticks: { color: 'rgba(255,255,255,0.7)' }
                },
                y: {
                    title: { display: true, text: t('chart_label_loss'), color: 'rgba(255,255,255,0.7)' },
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
        currentEventSource = null;
    }

    // C-9: ZH: 使用 fetch + ReadableStream 取代 EventSource，使能攜帶 Authorization header
    // EN: Replace EventSource with fetch + ReadableStream to support Authorization header
    //     (native EventSource cannot send custom headers, causing 401 on every request)
    (async () => {
        const abortCtrl = new AbortController();
        // ZH: 建立相容舊有 .close() 呼叫的包裝器 | EN: Wrap AbortController to keep .close() API
        currentEventSource = { close: () => abortCtrl.abort() };

        try {
            const resp = await fetch(`${API_BASE}/jobs/${jobId}/stream`, {
                headers: { 'Authorization': `Bearer ${authToken}` },
                signal: abortCtrl.signal,
            });

            if (!resp.ok) {
                jobLogsContainer.textContent += `\n[${t('error_stream_failed')}] (HTTP ${resp.status})\n`;
                return;
            }

            const reader = resp.body.getReader();
            const decoder = new TextDecoder();
            let buf = '';

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                buf += decoder.decode(value, { stream: true });

                // ZH: SSE 訊息以 "\n\n" 分隔 | EN: SSE messages separated by double newline
                const parts = buf.split('\n\n');
                buf = parts.pop(); // ZH: 保留不完整的尾段 | EN: Keep incomplete trailing chunk

                for (const part of parts) {
                    const dataLine = part.split('\n').find(l => l.startsWith('data: '));
                    if (!dataLine) continue;
                    try {
                        const data = JSON.parse(dataLine.slice(6));

                        // Append Logs
                        if (data.logs !== undefined) {
                            jobLogsContainer.textContent = data.logs;
                        } else if (data.new_logs) {
                            jobLogsContainer.textContent += data.new_logs;
                        }

                        // Auto Scroll
                        if (autoScrollCheckbox && autoScrollCheckbox.checked) {
                            jobLogsContainer.scrollTop = jobLogsContainer.scrollHeight;
                        }

                        // Append Metrics
                        const metricsToAdd = data.metrics || data.new_metrics || [];
                        if (metricsToAdd.length > 0 && lossChart) {
                            metricsToAdd.forEach(m => {
                                lossChart.data.labels.push(m.epoch);
                                lossChart.data.datasets[0].data.push(m.loss);
                            });
                            lossChart.update();
                        }

                        // Check if finished
                        if (['completed', 'failed', 'cancelled'].includes(data.status)) {
                            abortCtrl.abort();
                            jobLogsContainer.textContent += `\n[${t('msg_job_status')}: ${data.status}]\n`;
                            if (autoScrollCheckbox && autoScrollCheckbox.checked) {
                                jobLogsContainer.scrollTop = jobLogsContainer.scrollHeight;
                            }
                            return;
                        }
                    } catch (e) {
                        console.error('SSE parse error', e);
                    }
                }
            }
        } catch (e) {
            if (e.name !== 'AbortError') {
                console.error('SSE stream error:', e);
                jobLogsContainer.textContent += `\n[${t('error_stream_disconnected')}]\n`;
            }
        }
    })();
};


// ==============================================================================
// v2.0 LAB MODULE — 取代 v1 偽 Notebook，啟動 code-server (VS Code in browser)
// ==============================================================================

const Lab = (() => {
    let _state = 'unknown';   // 'stopped' | 'starting' | 'running'
    let _pollTimer = null;

    function _t(key, fallback) {
        // v2.1 修正：原本用 window.translations / 'zh-TW' 都對不到 (主程式用 TRANSLATIONS / 'zh')
        // EN fix: original `window.translations` / 'zh-TW' never matched (main app uses TRANSLATIONS / 'zh')
        try {
            const lang = (typeof currentLang !== 'undefined' && currentLang) || 'zh';
            const dict = (typeof TRANSLATIONS !== 'undefined') ? TRANSLATIONS[lang] : null;
            return (dict && dict[key]) || fallback;
        } catch (_) {
            return fallback;
        }
    }

    async function _api(path, opts = {}) {
        // v2.1 修正：使用 ai_hud_token (與 app.js 其他地方一致)，舊版誤用 'jwt' 導致永遠 401
        const token = localStorage.getItem('ai_hud_token');
        if (!token) throw new Error('Not authenticated');
        const resp = await fetch(`/api/v1/lab${path}`, {
            ...opts,
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`,
                ...(opts.headers || {}),
            },
        });
        if (!resp.ok) {
            const text = await resp.text();
            throw new Error(`HTTP ${resp.status}: ${text.slice(0, 200)}`);
        }
        return resp.json();
    }

    async function _refreshStatus() {
        try {
            const data = await _api('/status');
            _state = data.status || 'stopped';
            _renderStatus(data);
        } catch (e) {
            _setStatusText(_t('lab_status_error', '無法取得狀態 Error fetching status'), 'error');
        }
    }

    function _setStatusText(text, kind = 'info') {
        const el = document.getElementById('lab-status-text');
        if (!el) return;
        el.textContent = text;
        el.dataset.kind = kind;
    }

    function _renderStatus(data) {
        const openBtn = document.getElementById('lab-open-btn');
        const stopBtn = document.getElementById('lab-stop-btn');
        const meta    = document.getElementById('lab-meta');

        if (_state === 'running' || _state === 'starting') {
            _setStatusText(
                _state === 'running'
                    ? _t('lab_status_running', '已啟動 Running') + (data.last_activity ? ` · ${data.last_activity}` : '')
                    : _t('lab_status_starting', '啟動中… Starting…'),
                _state === 'running' ? 'ok' : 'warn'
            );
            openBtn.innerHTML = `<ion-icon name="arrow-forward-outline"></ion-icon><span>${_t('lab_enter', '進入 Notebook')}</span>`;
            openBtn.classList.remove('hidden');
            stopBtn.classList.remove('hidden');

            if (meta) {
                meta.style.display = 'flex';
                document.getElementById('lab-meta-image').textContent     = data.base_image || '—';
                document.getElementById('lab-meta-quota').textContent     = data.disk_quota_gb ? `${data.disk_quota_gb} GB` : '—';
                document.getElementById('lab-meta-remaining').textContent =
                    typeof data.today_remaining_minutes === 'number'
                        ? `${data.today_remaining_minutes} ${_t('lab_minutes', '分鐘')}`
                        : '—';
            }
        } else {
            _setStatusText(_t('lab_status_stopped', '未啟動 Stopped'), 'info');
            openBtn.innerHTML = `<ion-icon name="open-outline"></ion-icon><span>${_t('lab_open', '開啟 Notebook')}</span>`;
            openBtn.classList.remove('hidden');
            stopBtn.classList.add('hidden');
            if (meta) meta.style.display = 'none';
        }
    }

    async function _onOpenClick() {
        const openBtn = document.getElementById('lab-open-btn');
        const userId  = (window.currentUser?.id) || localStorage.getItem('user_id') || '';

        // ZH: 若已 running，直接開新 tab 跳轉
        // EN: If already running, just open new tab
        if (_state === 'running' && userId) {
            window.open(`/code/${userId}/`, '_blank', 'noopener');
            return;
        }

        const image = document.getElementById('lab-image-select')?.value || 'aibase/pytorch:2026-spring';
        openBtn.disabled = true;
        _setStatusText(_t('lab_status_starting', '啟動中… Starting…'), 'warn');

        try {
            const resp = await _api('/start', {
                method: 'POST',
                body: JSON.stringify({ base_image: image }),
            });
            _state = resp.status || 'starting';
            // ZH: 服務層回傳 code_url 直接跳轉 | EN: Service returned code_url → open
            if (resp.code_url) {
                window.open(resp.code_url, '_blank', 'noopener');
            } else if (userId) {
                window.open(`/code/${userId}/`, '_blank', 'noopener');
            }
            // 啟動後輪詢狀態直到 running
            _startPolling();
        } catch (e) {
            _setStatusText(`${_t('lab_status_error', '啟動失敗 Failed')}: ${e.message}`, 'error');
        } finally {
            openBtn.disabled = false;
        }
    }

    async function _onStopClick() {
        if (!confirm(_t('lab_stop_confirm', '確認停止 Notebook session？檔案會保留。'))) return;
        const stopBtn = document.getElementById('lab-stop-btn');
        stopBtn.disabled = true;
        try {
            await _api('/stop', { method: 'POST' });
            _state = 'stopped';
            _stopPolling();
            await _refreshStatus();
        } catch (e) {
            _setStatusText(`${_t('lab_status_error', '錯誤 Error')}: ${e.message}`, 'error');
        } finally {
            stopBtn.disabled = false;
        }
    }

    function _startPolling() {
        if (_pollTimer) return;
        _pollTimer = setInterval(_refreshStatus, 5000);
    }

    function _stopPolling() {
        if (_pollTimer) { clearInterval(_pollTimer); _pollTimer = null; }
    }

    function init() {
        if (!document.getElementById('lab-open-btn')) return;
        document.getElementById('lab-open-btn').addEventListener('click', _onOpenClick);
        document.getElementById('lab-stop-btn').addEventListener('click', _onStopClick);
        _refreshStatus();
        _startPolling();
    }

    return { init };
})();


// ==============================================================================
// 整合：切換到 Notebook 頁籤時初始化 Lab 啟動器
// ==============================================================================
(function _patchSubTabForLab() {
    document.addEventListener('click', e => {
        const btn = e.target.closest('.sub-tab-btn');
        if (!btn) return;
        if (btn.dataset.subtab === 'compute-notebook') {
            document.querySelectorAll('.sub-page-view').forEach(p => p.classList.remove('active'));
            document.getElementById('compute-notebook-page')?.classList.add('active');
            document.querySelectorAll('.sub-tab-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            Lab.init();
        }
    }, true);
})();


// ==============================================================================
// v2.0 SECRETS MODULE — 設定頁面 Secrets 管理
// ==============================================================================
const Secrets = (() => {
    let _loaded = false;

    function _t(key, fallback) {
        // v2.1 修正：TRANSLATIONS 是檔內 const，window.TRANSLATIONS 取不到
        try {
            const lang = (typeof currentLang !== 'undefined' && currentLang) || 'zh';
            const dict = (typeof TRANSLATIONS !== 'undefined') ? TRANSLATIONS[lang] : null;
            return (dict && dict[key]) || fallback;
        } catch (_) {
            return fallback;
        }
    }

    async function _api(path, opts = {}) {
        const token = localStorage.getItem('ai_hud_token');
        if (!token) throw new Error('Not authenticated');
        const resp = await fetch(`/api/v1/secrets${path}`, {
            ...opts,
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`,
                ...(opts.headers || {}),
            },
        });
        if (!resp.ok && resp.status !== 204) {
            const text = await resp.text();
            throw new Error(`HTTP ${resp.status}: ${text.slice(0, 200)}`);
        }
        return resp.status === 204 ? null : resp.json();
    }

    function _renderList(items) {
        const list = document.getElementById('secrets-list');
        if (!list) return;
        if (!items || items.length === 0) {
            list.innerHTML = `<div class="secret-item" style="justify-content:center; color:var(--text-muted);">${_t('secrets_empty', '尚未設定任何 secret')}</div>`;
            return;
        }
        list.innerHTML = items.map(s => `
            <div class="secret-item" data-name="${escapeHtml(s.name)}">
                <span class="secret-name">${escapeHtml(s.name)}</span>
                <span class="secret-masked-value">${escapeHtml(s.masked_value || '****')}</span>
                <button class="secret-delete-btn" title="${_t('secrets_delete_confirm', '刪除')}">
                    <ion-icon name="trash-outline"></ion-icon>
                </button>
            </div>
        `).join('');

        list.querySelectorAll('.secret-delete-btn').forEach(btn => {
            btn.addEventListener('click', async (e) => {
                const item = e.target.closest('.secret-item');
                const name = item.dataset.name;
                if (!confirm(_t('secrets_delete_confirm', '確認刪除這個 secret？'))) return;
                try {
                    await _api(`/${encodeURIComponent(name)}`, { method: 'DELETE' });
                    await load();
                } catch (err) {
                    alert(`${_t('secrets_load_fail', '錯誤')}: ${err.message}`);
                }
            });
        });
    }

    function escapeHtml(s) {
        return String(s).replace(/[&<>"']/g, m => ({
            '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
        }[m]));
    }

    async function load() {
        try {
            const data = await _api('/');
            _renderList(data?.secrets || data || []);
            _loaded = true;
        } catch (e) {
            const list = document.getElementById('secrets-list');
            if (list) list.innerHTML = `<div class="secret-item" style="color:#ef4444;">${_t('secrets_load_fail', '載入 Secrets 失敗')}: ${e.message}</div>`;
        }
    }

    async function _onAdd() {
        const nameEl  = document.getElementById('secret-name-input');
        const valueEl = document.getElementById('secret-value-input');
        const name  = (nameEl?.value || '').trim();
        const value = (valueEl?.value || '').trim();
        if (!name || !value) return;
        if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(name)) {
            alert('Name must match /^[A-Za-z_][A-Za-z0-9_]*$/');
            return;
        }
        try {
            await _api(`/${encodeURIComponent(name)}`, {
                method: 'PUT',
                body: JSON.stringify({ value }),
            });
            nameEl.value = '';
            valueEl.value = '';
            await load();
        } catch (e) {
            alert(`${_t('secrets_load_fail', '錯誤')}: ${e.message}`);
        }
    }

    function init() {
        if (_loaded) return;
        const addBtn = document.getElementById('secret-add-btn');
        if (!addBtn) return;
        addBtn.addEventListener('click', _onAdd);
        document.getElementById('secret-value-input')?.addEventListener('keydown', e => {
            if (e.key === 'Enter') _onAdd();
        });
        load();
    }

    return { init, load };
})();

// 在切到設定頁面時初始化 Secrets 區塊
document.addEventListener('click', (e) => {
    const btn = e.target.closest('[data-page="settings-page"], #nav-settings-btn');
    if (btn) {
        setTimeout(() => Secrets.init(), 50);
    }
}, true);

// 也讓全域可用
window.TRANSLATIONS = window.TRANSLATIONS || TRANSLATIONS;
window.Secrets = Secrets;
window.Lab = Lab;


// ==============================================================================
// DEAD CODE — v1 NOTEBOOK MODULE (kept as block-comment for diff reviewability;
// Phase E will remove this entirely along with the backend Notebook router.)
// ==============================================================================

// ZH: v1 NB IIFE 已於 Phase D 刪除，原本約 670 行（const NB = (() => {...})() + 子頁籤掛勾）
// EN: v1 NB IIFE removed in Phase D (~670 lines); replaced by Lab launcher above


// ==============================================================================
// v2.1 SSO OIDC 整合模組
// v2.1 SSO OIDC Integration Module
// ==============================================================================
// ZH: 功能：
//   1. 頁面載入時處理 ?sso_token= URL 參數（OIDC callback 後 302 回來會帶這個）
//   2. fetch /api/v1/sso/providers 決定登入頁顯示 #sso-section 或 #sso-pending
//   3. 綁定 #sso-oidc-btn click → 跳轉 /api/v1/sso/oidc/login
//   4. 密碼變更 modal 依使用者 auth_source 分流（local 顯示 form / SSO 顯示 IdP 連結）
//   5. Logout 只清本機 localStorage（不主動登出 Microsoft session — v1.1 I10）
// EN: Handles sso_token URL params, providers fetch, button click, password split, logout.
// ==============================================================================
(function setupSSOLogin() {
    // ── 1. 處理 ?sso_token= URL 參數（OIDC callback 後 302 回來會帶）─────────
    const params = new URLSearchParams(window.location.search);
    const ssoToken = params.get('sso_token');
    if (ssoToken) {
        localStorage.setItem('ai_hud_token', ssoToken);
        authToken = ssoToken;
        // 清掉 URL 參數，避免 token 留在瀏覽歷史
        window.history.replaceState({}, document.title, window.location.pathname);
    }

    // ── 2. fetch /providers 決定顯示哪個區塊 ─────────────────────────────
    // 不認證即可呼叫（無敏感資料），這在 DOMContentLoaded 之前就跑也 OK
    function applyProvidersUI(providers) {
        const loading = document.getElementById('sso-loading');
        const ssoSec  = document.getElementById('sso-section');
        const pending = document.getElementById('sso-pending');
        if (!loading || !ssoSec || !pending) return;   // login HTML 還沒渲染

        loading.style.display = 'none';
        if (providers.includes('oidc')) {
            ssoSec.style.display = 'flex';
        } else {
            pending.style.display = 'flex';
        }
    }

    // 延遲到 DOMContentLoaded 後執行，確保 DOM 已有 #sso-loading 等元素
    document.addEventListener('DOMContentLoaded', () => {
        // 已登入則完全跳過 SSO UI（loginView 本來就是 hidden）
        if (authToken) return;

        fetch(`${API_BASE}/sso/providers`)
            .then(r => r.ok ? r.json() : { providers: [] })
            .then(({ providers }) => applyProvidersUI(providers || []))
            .catch(() => applyProvidersUI([]));   // 失敗也顯示 pending fallback

        // ── 3. 綁定 OIDC 按鈕 ─────────────────────────────────────────────
        const oidcBtn = document.getElementById('sso-oidc-btn');
        if (oidcBtn) {
            oidcBtn.addEventListener('click', () => {
                oidcBtn.disabled = true;
                window.location.href = `${API_BASE}/sso/oidc/login`;
            });
        }
    });
})();


// ==============================================================================
// v2.1 密碼變更 modal 分流（依 currentUserData.auth_source）
// ==============================================================================
// 開啟 #password-modal 時呼叫：
//   - local → 顯示 #password-change-form（既有 form）
//   - sso_* → 顯示 #password-change-sso（IdP 連結 + 為什麼說明）
async function applyPasswordModalMode() {
    const localForm = document.getElementById('password-change-form');
    const ssoBlock  = document.getElementById('password-change-sso');
    if (!localForm || !ssoBlock) return;

    const authSource = (window.currentUserData && window.currentUserData.auth_source) || 'local';

    if (authSource === 'local') {
        localForm.style.display = 'flex';
        ssoBlock.classList.add('hidden');
        return;
    }

    // SSO 模式：隱藏本機 form，顯示 IdP 連結區塊
    localForm.style.display = 'none';
    ssoBlock.classList.remove('hidden');

    // fetch /sso/password-change-info 拿對應 IdP URL（含 reset_url）
    try {
        const res = await fetch(`${API_BASE}/sso/password-change-info`);
        if (!res.ok) return;
        const data = await res.json();
        const info = (data.providers || {})[authSource] || {};

        const linkEl  = document.getElementById('password-sso-link');
        const resetEl = document.getElementById('password-sso-reset-link');
        const msgEl   = document.getElementById('password-sso-msg');

        if (info.change_url && linkEl) linkEl.href = info.change_url;
        if (info.reset_url && resetEl) resetEl.href = info.reset_url;
        if (info.message && msgEl) msgEl.textContent = info.message;

        // 若 reset_url 不存在，隱藏「忘記密碼」連結
        if (!info.reset_url && resetEl) resetEl.style.display = 'none';
    } catch (e) {
        console.warn('[SSO] fetch password-change-info failed:', e);
    }
}

// 攔截「變更密碼」按鈕的 click（在 #nav-password-btn 既有 handler 之外加一層）
document.addEventListener('DOMContentLoaded', () => {
    const navPasswordBtn = document.getElementById('nav-password-btn');
    if (navPasswordBtn) {
        navPasswordBtn.addEventListener('click', () => {
            // 既有 handler 已把 modal 顯示出來，這裡只負責切換 mode
            setTimeout(applyPasswordModalMode, 0);
        });
    }

    // v2.1: Password Modal 加強 — 強度提示 + 確認密碼 + eye toggle
    setupPasswordModalEnhancements();

    // 也讓 #password-change-form (modal 內 form) 真正可送出
    // 過去這個 form 沒 submit handler → 送出後 page reload。修為呼叫 PUT /me
    const modalForm = document.getElementById('password-change-form');
    if (modalForm) {
        modalForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const newPwd = document.getElementById('profile-password').value;
            const confirmPwd = document.getElementById('profile-password-confirm').value;

            // v2.1: 前端二次驗證
            if (newPwd.length < 8) {
                showToast('password_too_short', true);
                return;
            }
            if (newPwd !== confirmPwd) {
                showToast('password_mismatch_toast', true);
                return;
            }

            try {
                const res = await fetch(`${API_BASE}/auth/me`, {
                    method: 'PUT',
                    headers: {
                        'Authorization': `Bearer ${authToken}`,
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({ password: newPwd }),
                });
                if (!res.ok) {
                    const err = await res.json().catch(() => ({}));
                    if (res.status === 400 && /sso/i.test(err.detail || '')) {
                        showToast('toast_sso_password_blocked', true);
                    } else {
                        throw new Error(err.detail || 'Update failed');
                    }
                    return;
                }
                showToast('toast_auth_ok');
                // 清空所有欄位
                document.getElementById('profile-password').value = '';
                document.getElementById('profile-password-confirm').value = '';
                resetPasswordStrength();
                document.getElementById('password-modal').classList.add('hidden');
            } catch (err) {
                console.error(err);
                showToast('toast_auth_fail', true);
            }
        });
    }
});


// ==============================================================================
// v2.1 Profile Modal 豐富資訊版 — refresh + render helpers
// ==============================================================================

const AUTH_SOURCE_LABEL = {
    local:    { zh: '本機帳號',           en: 'Local',              hint: '可在本系統變更密碼' },
    sso_mock: { zh: 'Mock SSO（測試）',   en: 'Mock SSO',           hint: '開發測試帳號' },
    sso_cas:  { zh: 'CAS（學校 SSO）',     en: 'CAS',                hint: '密碼請至學校 CAS 變更' },
    sso_oidc: { zh: 'Microsoft Entra ID', en: 'Microsoft Entra ID', hint: '密碼請至 Microsoft 變更' },
};

const ROLE_LABEL = {
    student: { zh: '學生',  en: 'Student' },
    teacher: { zh: '教師',  en: 'Teacher' },
    admin:   { zh: '管理員', en: 'Admin' },
};

/** 從 /api/v1/auth/me 重新拉一次當前使用者資料 */
async function refreshCurrentUserData() {
    if (!authToken) return;
    try {
        const res = await fetch(`${API_BASE}/auth/me`, {
            headers: { 'Authorization': `Bearer ${authToken}` },
        });
        if (res.ok) {
            window.currentUserData = await res.json();
        }
    } catch (e) {
        console.warn('[Profile] refresh user data failed:', e);
    }
}

/** 將時間字串格式化為 "YYYY-MM-DD HH:MM" */
function formatDateTime(iso) {
    if (!iso) return '—';
    try {
        const d = new Date(iso);
        const pad = (n) => String(n).padStart(2, '0');
        return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
    } catch { return iso; }
}

/** 數字加千分位 */
function formatNumber(n) {
    if (n == null || isNaN(n)) return '—';
    return Number(n).toLocaleString();
}

/** 渲染 Profile Modal 內容（從 currentUserData + fetch /usage） */
async function renderProfileInfo() {
    const u = window.currentUserData;
    if (!u) return;
    const lang = currentLang || 'zh';

    // ── 區塊 1: 基本資訊 ──
    const setText = (id, v) => {
        const el = document.getElementById(id);
        if (el) el.textContent = (v == null || v === '') ? '—' : String(v);
    };
    setText('profile-info-username', u.username);
    setText('profile-info-email', u.email);
    setText('profile-info-department', u.department);

    // Role badge (顯示中/英對應 + data-role 給 CSS 變色)
    const roleEl = document.getElementById('profile-info-role');
    if (roleEl) {
        const r = u.role || 'student';
        roleEl.textContent = (ROLE_LABEL[r] && ROLE_LABEL[r][lang]) || r;
        roleEl.setAttribute('data-role', r);
    }

    // ── 區塊 2: 認證資訊 ──
    const authEl = document.getElementById('profile-info-auth-source');
    if (authEl) {
        const src = u.auth_source || 'local';
        const meta = AUTH_SOURCE_LABEL[src] || { zh: src, en: src };
        authEl.textContent = meta[lang] || meta.zh;
        authEl.title = meta.hint || '';
    }
    setText('profile-info-last-login', formatDateTime(u.last_login_time));
    setText('profile-info-last-ip', u.last_login_ip);
    setText('profile-info-login-count', formatNumber(u.login_count));
    setText('profile-info-created-at', formatDateTime(u.created_at));

    // ── 區塊 4 (編輯欄位) 已移除 — v2.1: 自助修改下架 ──

    // ── 區塊 3: Token 用量（fetch /usage） ──
    try {
        const usageRes = await fetch(`${API_BASE}/auth/usage`, {
            headers: { 'Authorization': `Bearer ${authToken}` },
        });
        if (usageRes.ok) {
            const usage = await usageRes.json();
            const used = usage.tokens_used || 0;
            const limit = usage.tokens_limit || 0;
            const pct = limit > 0 ? (used / limit * 100) : 0;

            setText('profile-usage-used', formatNumber(used));
            setText('profile-usage-limit', formatNumber(limit));
            setText('profile-usage-pct', pct.toFixed(2) + '%');
            setText('profile-info-lifetime', formatNumber(u.lifetime_tokens_used));
            setText('profile-info-reset-date', formatDateTime(usage.reset_date));

            const fillEl = document.getElementById('profile-usage-fill');
            if (fillEl) {
                fillEl.style.width = Math.min(pct, 100) + '%';
                fillEl.classList.remove('warning', 'danger');
                if (pct >= 90) fillEl.classList.add('danger');
                else if (pct >= 70) fillEl.classList.add('warning');
            }
        }
    } catch (e) {
        console.warn('[Profile] fetch usage failed:', e);
    }
}

window.refreshCurrentUserData = refreshCurrentUserData;
window.renderProfileInfo = renderProfileInfo;


// ==============================================================================
// v2.1 Password Modal 加強 — 強度提示 / 確認密碼 / eye-toggle
// ==============================================================================

/**
 * 計算密碼強度 (0-4)：
 *   0 = 空 / < 8 字元
 *   1 = weak    (基本長度)
 *   2 = medium  (加字母+數字)
 *   3 = strong  (加特殊符號)
 *   4 = vstrong (≥ 12 字元 + 全部類型)
 */
function calcPasswordStrength(pwd) {
    if (!pwd || pwd.length < 8) return 0;
    let score = 1;
    const hasLower = /[a-z]/.test(pwd);
    const hasUpper = /[A-Z]/.test(pwd);
    const hasDigit = /\d/.test(pwd);
    const hasSymbol = /[^a-zA-Z0-9]/.test(pwd);
    const types = [hasLower, hasUpper, hasDigit, hasSymbol].filter(Boolean).length;
    if (types >= 2) score = 2;
    if (types >= 3) score = 3;
    if (types >= 3 && pwd.length >= 12) score = 4;
    return score;
}

function resetPasswordStrength() {
    const wrap = document.getElementById('password-strength-wrap');
    const fill = document.getElementById('password-strength-fill');
    const text = document.getElementById('password-strength-text');
    const mismatch = document.getElementById('password-mismatch-hint');
    if (wrap) wrap.classList.add('hidden');
    if (fill) { fill.style.width = '0%'; fill.className = 'password-strength-fill'; }
    if (text) { text.textContent = ''; text.removeAttribute('data-level'); }
    if (mismatch) mismatch.classList.add('hidden');
    const submitBtn = document.getElementById('password-submit-btn');
    if (submitBtn) submitBtn.disabled = true;
}

function setupPasswordModalEnhancements() {
    const newPwd = document.getElementById('profile-password');
    const confirmPwd = document.getElementById('profile-password-confirm');
    const wrap = document.getElementById('password-strength-wrap');
    const fill = document.getElementById('password-strength-fill');
    const text = document.getElementById('password-strength-text');
    const mismatch = document.getElementById('password-mismatch-hint');
    const submitBtn = document.getElementById('password-submit-btn');
    if (!newPwd || !confirmPwd) return;  // SSO 模式無此欄位

    const STRENGTH_LABEL = {
        zh: ['', '弱 Weak', '中 Medium', '強 Strong', '極強 Very Strong'],
        en: ['', 'Weak', 'Medium', 'Strong', 'Very Strong'],
    };
    const STRENGTH_CLASS = ['', 'weak', 'medium', 'strong', 'vstrong'];

    function refresh() {
        const v = newPwd.value;
        const score = calcPasswordStrength(v);
        if (v.length === 0) {
            wrap.classList.add('hidden');
        } else {
            wrap.classList.remove('hidden');
            const lang = currentLang || 'zh';
            fill.style.width = (score * 25) + '%';
            fill.className = 'password-strength-fill ' + STRENGTH_CLASS[score];
            text.textContent = STRENGTH_LABEL[lang][score] || STRENGTH_LABEL.zh[score];
            text.setAttribute('data-level', STRENGTH_CLASS[score] || 'weak');
        }
        // 比對 confirm
        const matches = confirmPwd.value.length > 0 && newPwd.value === confirmPwd.value;
        const showMismatch = confirmPwd.value.length > 0 && !matches;
        if (mismatch) mismatch.classList.toggle('hidden', !showMismatch);

        // 可送出條件: 兩個都填、相符、score ≥ 1
        if (submitBtn) {
            submitBtn.disabled = !(score >= 1 && matches);
        }
    }

    newPwd.addEventListener('input', refresh);
    confirmPwd.addEventListener('input', refresh);

    // 眼睛 toggle 顯示/隱藏密碼
    document.querySelectorAll('.eye-toggle-pwd[data-target]').forEach(btn => {
        btn.addEventListener('click', () => {
            const target = document.getElementById(btn.getAttribute('data-target'));
            if (!target) return;
            const icon = btn.querySelector('ion-icon');
            if (target.type === 'password') {
                target.type = 'text';
                if (icon) icon.setAttribute('name', 'eye-outline');
            } else {
                target.type = 'password';
                if (icon) icon.setAttribute('name', 'eye-off-outline');
            }
        });
    });
}

window.calcPasswordStrength = calcPasswordStrength;
window.resetPasswordStrength = resetPasswordStrength;
