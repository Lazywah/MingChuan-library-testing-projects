/* ==========================================================================
 * i18n-admin.js — 管理端專屬文案（zh / en）
 *
 * ZH: 共用的 `i18n.js` 是**正本，一個字都不改**（`check_shared_ui_files.py` 守著
 *     它與 web-ui-v2 逐位元組相同）。管理端要多出來的 key 全部放這裡，
 *     用 Object.assign 併進同一本字典。
 *
 * ZH: 為什麼不把管理端的 key 直接寫進共用的 i18n.js：
 *     那會讓使用者端載入幾百條它永遠用不到的管理端文案，
 *     而且共用檔一改就要同步四份副本。分開之後，
 *     「共用的」與「管理端的」各自有清楚的歸屬。
 *
 * ⚠ 載入順序：一定要在 `i18n.js` **之後**、`prefs.js` **之前**。
 *   在 i18n.js 之前會 assign 到不存在的物件上；
 *   在 prefs.js 之後則是字典還沒併好就已經套用過一次，畫面會先閃一次原文。
 *   `scripts/check_js_globals.py` 只檢查「有沒有載」，**不檢查順序** —— 這裡靠註解。
 *
 * ⚠ key 是契約，不要因為文案改了就改 key（理由見 i18n.js 檔頭）。
 * ========================================================================== */
(function (global) {
    'use strict';

    if (!global.I18N) {
        // ZH: 大聲壞掉，不要靜默失敗 —— 少載 i18n.js 的症狀會偽裝成「翻譯漏了」，
        //     而那會讓人去翻字典找一個根本存在的 key。
        throw new Error('i18n-admin.js 必須在 i18n.js 之後載入');
    }

    Object.assign(global.I18N.zh, {
        // ── 登入 ─────────────────────────────────────────────
        adm_login_title: '管理員登入 · MCU AI Base',
        adm_login_h1: '管理員登入',
        adm_login_sub: '這裡是平台的管理介面。學生請從一般入口登入。',
        adm_login_submit: '登入',
        adm_login_fail: '登入失敗，請檢查帳號密碼。',
        adm_login_not_admin: '這個帳號不是管理員。',
        adm_login_offline: '連不上伺服器，請確認服務是否啟動。',

        // ── 外框 ─────────────────────────────────────────────
        adm_brand: 'MCU AI Base 管理端',
        adm_nav_overview: '總覽',
        adm_nav_people: '人',
        adm_nav_platform: '平台設定',
        adm_nav_reports: '回報',
        adm_nav_analytics: '數據',
        adm_logout: '登出',
        adm_to_user_site: '回使用者端',
        adm_old_ui: '舊版管理介面',

        // ── 總覽 ─────────────────────────────────────────────
        ov_updated: '最後更新 {t}',
        ov_refresh: '重新整理',
        ov_alerts: '需要你處理的',
        ov_all_clear: '目前沒有需要處理的事。',
        ov_a_offline: '{n} 個 GPU 節點掉線',
        ov_a_disabled: '{n} 個 GPU 節點被停用中',
        ov_a_conflict: '有節點回報 NODE_ID 撞名 —— 兩台機器用了同一個名字，派工會亂',
        ov_a_failed: '最近 24 小時有 {n} 張任務失敗',
        ov_a_waiting: '{n} 張任務排隊超過 {m} 分鐘',
        ov_a_reports: '{n} 則問題回報還沒處理',
        ov_a_go: '去看',

        ov_gpu: 'GPU 現況',
        ov_gpu_none: '沒有任何 GPU 節點回報過心跳。',
        ov_util: '使用率',
        ov_temp: '溫度',
        ov_mem: '記憶體',

        ov_nodes: '節點',
        ov_n_node: '節點',
        ov_n_state: '狀態',
        ov_n_pool: '池別',
        ov_n_running: '執行中',
        ov_n_next: '下次變化',
        ov_n_seen: '最後心跳',
        st_working: '執行中',
        st_idle: '閒置',
        st_offline: '掉線',
        st_disabled: '已停用',
        st_out_of_window: '非開放時段',
        st_out_of_window_draining: '非開放時段（收尾中）',

        ov_jobs: '最近的任務',
        ov_j_none: '還沒有任何任務。',
        ov_j_name: '任務',
        ov_j_user: '使用者',
        ov_j_status: '狀態',
        ov_j_node: '節點',
        ov_j_when: '時間',
        ov_fail_part: '這一段暫時讀不到（{w}）',

        // ── 人 ───────────────────────────────────────────────
        pp_search: '搜尋帳號、Email、學系…',
        pp_search_label: '搜尋',
        pp_no_email: '—（無信箱）',
        pp_count: '{n} 人',
        pp_count_filtered: '{n} / {t} 人',
        pp_none: '找不到符合的人。',
        pp_fail: '讀不到使用者清單（{w}）。',
        pp_c_user: '帳號',
        pp_c_dept: '學系',
        pp_c_role: '角色',
        pp_c_state: '狀態',
        pp_c_source: '來源',
        pp_c_seen: '最後登入',
        pp_active: '啟用',
        pp_inactive: '已停用',
        pp_pick: '點一列看這個人的詳細資料。',

        pp_detail: '{name} 的資料',
        pp_basic: '基本資料',
        pp_save: '儲存',
        pp_saved: '已儲存',
        pp_save_fail: '存不起來（{w}）',
        pp_pw_hint: '留空就不改密碼',
        pp_new_pw: '新密碼',

        pp_quota: '磁碟配額',
        pp_q_base: '基本',
        pp_q_effective: '實際可用',
        pp_q_grants: '額外授與',
        pp_q_none: '沒有額外授與。',
        pp_q_add: '加額度',
        pp_q_reason: '原因（必填）',
        pp_q_expires: '到期日（可留空）',
        pp_q_revoke: '收回',

        pp_lab: '程式實驗室',
        pp_lab_none: '目前沒有執行中的實驗室。',
        pp_lab_stop: '強制關閉',
        pp_lab_confirm: '要強制關閉「{n}」的實驗室嗎？他正在編輯的檔案會保留，但未存檔的東西可能會不見。',

        pp_danger: '需要再確認的操作',
        pp_danger_why: '這幾項會影響使用者，所以要再輸入一次你的密碼。',
        pp_admin_pw: '你的管理員密碼',
        pp_disable: '停用帳號',
        pp_enable: '啟用帳號',
        pp_delete: '刪除帳號',
        pp_delete_confirm: '要刪除「{n}」嗎？他的 Lab 資料會封存（可在期限內還原），其餘資料會消失。',
        pp_need_pw: '請先輸入你的管理員密碼。',

        // ── 臨時帳號 ─────────────────────────────────────────
        tmp_new: '建立臨時帳號',
        tmp_title: '建立臨時帳號',
        tmp_why: '給校外人士、長官視察或其他例外用途。到期會自動停用，帳號與紀錄都留著。',
        tmp_user: '帳號名稱',
        tmp_purpose: '用途（必填）',
        tmp_purpose_hint: '例如「教育部訪視 2026-09-03」。半年後看到一個沒有用途的帳號，沒有人敢刪它。',
        tmp_days: '有效天數',
        tmp_days_hint: '1–90 天',
        tmp_email: 'Email（可留空，平台不會寄信）',
        tmp_create: '建立',
        tmp_cancel: '取消',
        tmp_fail: '建立失敗（{w}）',

        tmp_done: '帳號建好了',
        tmp_pw_once: '🔴 這組密碼只會顯示這一次。現在就抄下來交給對方 —— 關掉之後就看不到了。',
        tmp_pw: '密碼',
        tmp_expires: '到期',
        tmp_copy: '複製帳號與密碼',
        tmp_copied: '已複製',
        tmp_close: '知道了',

        tmp_expired: '已到期',
        tmp_until: '到期 {d}',

        // ── 階段 1 佔位 ──────────────────────────────────────
        adm_wip_title: '這一頁還沒做',
        adm_wip_body: '階段 1 只做骨架（登入、外框、顯示設定）。這一頁會在後面的階段補上。',
    });

    Object.assign(global.I18N.en, {
        adm_login_title: 'Admin sign-in · MCU AI Base',
        adm_login_h1: 'Admin sign-in',
        adm_login_sub: 'This is the platform admin console. Students, please use the main entrance.',
        adm_login_submit: 'Sign in',
        adm_login_fail: 'Sign-in failed. Check your username and password.',
        adm_login_not_admin: 'That account is not an administrator.',
        adm_login_offline: 'Cannot reach the server. Check that the service is running.',

        adm_brand: 'MCU AI Base Admin',
        adm_nav_overview: 'Overview',
        adm_nav_people: 'People',
        adm_nav_platform: 'Platform',
        adm_nav_reports: 'Reports',
        adm_nav_analytics: 'Analytics',
        adm_logout: 'Sign out',
        adm_to_user_site: 'Back to the user site',
        adm_old_ui: 'Old admin console',

        ov_updated: 'Updated {t}',
        ov_refresh: 'Refresh',
        ov_alerts: 'Needs your attention',
        ov_all_clear: 'Nothing needs attention right now.',
        ov_a_offline: '{n} GPU node(s) offline',
        ov_a_disabled: '{n} GPU node(s) disabled',
        ov_a_conflict: 'A node reports a duplicate NODE_ID — two machines share a name, dispatch will misbehave',
        ov_a_failed: '{n} job(s) failed in the last 24 hours',
        ov_a_waiting: '{n} job(s) queued for over {m} minutes',
        ov_a_reports: '{n} issue report(s) still open',
        ov_a_go: 'Open',

        ov_gpu: 'GPUs right now',
        ov_gpu_none: 'No GPU node has ever sent a heartbeat.',
        ov_util: 'Utilisation',
        ov_temp: 'Temperature',
        ov_mem: 'Memory',

        ov_nodes: 'Nodes',
        ov_n_node: 'Node',
        ov_n_state: 'State',
        ov_n_pool: 'Pool',
        ov_n_running: 'Running',
        ov_n_next: 'Next change',
        ov_n_seen: 'Last heartbeat',
        st_working: 'Working',
        st_idle: 'Idle',
        st_offline: 'Offline',
        st_disabled: 'Disabled',
        st_out_of_window: 'Outside window',
        st_out_of_window_draining: 'Outside window (draining)',

        ov_jobs: 'Recent jobs',
        ov_j_none: 'No jobs yet.',
        ov_j_name: 'Job',
        ov_j_user: 'User',
        ov_j_status: 'Status',
        ov_j_node: 'Node',
        ov_j_when: 'When',
        ov_fail_part: 'This section is unavailable ({w})',

        pp_search: 'Search username, email, department…',
        pp_search_label: 'Search',
        pp_no_email: '— (no email)',
        pp_count: '{n} people',
        pp_count_filtered: '{n} of {t}',
        pp_none: 'No one matches.',
        pp_fail: 'Cannot load the user list ({w}).',
        pp_c_user: 'Username',
        pp_c_dept: 'Department',
        pp_c_role: 'Role',
        pp_c_state: 'State',
        pp_c_source: 'Source',
        pp_c_seen: 'Last sign-in',
        pp_active: 'Active',
        pp_inactive: 'Disabled',
        pp_pick: 'Pick a row to see that person.',

        pp_detail: '{name}',
        pp_basic: 'Details',
        pp_save: 'Save',
        pp_saved: 'Saved',
        pp_save_fail: 'Could not save ({w})',
        pp_pw_hint: 'Leave blank to keep the current password',
        pp_new_pw: 'New password',

        pp_quota: 'Disk quota',
        pp_q_base: 'Base',
        pp_q_effective: 'Effective',
        pp_q_grants: 'Extra grants',
        pp_q_none: 'No extra grants.',
        pp_q_add: 'Add quota',
        pp_q_reason: 'Reason (required)',
        pp_q_expires: 'Expires (optional)',
        pp_q_revoke: 'Revoke',

        pp_lab: 'Code Lab',
        pp_lab_none: 'No running lab.',
        pp_lab_stop: 'Force stop',
        pp_lab_confirm: 'Force-stop the lab for {n}? Saved files are kept, but unsaved work may be lost.',

        pp_danger: 'Actions that need confirmation',
        pp_danger_why: 'These affect the user, so enter your password again.',
        pp_admin_pw: 'Your admin password',
        pp_disable: 'Disable account',
        pp_enable: 'Enable account',
        pp_delete: 'Delete account',
        pp_delete_confirm: 'Delete {n}? Their lab data is archived (restorable for a while); everything else is gone.',
        pp_need_pw: 'Enter your admin password first.',

        tmp_new: 'New temporary account',
        tmp_title: 'New temporary account',
        tmp_why: 'For external visitors, official visits, or other exceptions. Disabled automatically on expiry; the account and its record stay.',
        tmp_user: 'Username',
        tmp_purpose: 'Purpose (required)',
        tmp_purpose_hint: 'e.g. "Ministry visit 2026-09-03". Six months on, nobody dares delete an account with no stated purpose.',
        tmp_days: 'Valid for (days)',
        tmp_days_hint: '1-90 days',
        tmp_email: 'Email (optional; no mail is sent)',
        tmp_create: 'Create',
        tmp_cancel: 'Cancel',
        tmp_fail: 'Could not create ({w})',

        tmp_done: 'Account created',
        tmp_pw_once: '🔴 This password is shown once only. Copy it now and hand it over — it cannot be retrieved later.',
        tmp_pw: 'Password',
        tmp_expires: 'Expires',
        tmp_copy: 'Copy username and password',
        tmp_copied: 'Copied',
        tmp_close: 'Got it',

        tmp_expired: 'Expired',
        tmp_until: 'until {d}',

        adm_wip_title: 'This page is not built yet',
        adm_wip_body: 'Stage 1 covers the shell only (sign-in, chrome, display settings). '
            + 'This page arrives in a later stage.',
    });
})(window);
