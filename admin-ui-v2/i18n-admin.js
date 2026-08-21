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

        adm_wip_title: 'This page is not built yet',
        adm_wip_body: 'Stage 1 covers the shell only (sign-in, chrome, display settings). '
            + 'This page arrives in a later stage.',
    });
})(window);
