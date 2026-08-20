/* ==========================================================================
 * i18n.js — 介面文案字典
 *
 * ZH: **這一版（2a）只翻頂部列與帳號選單**，其餘約 230 條在 2b 處理。
 *     刻意分開：機制與內容混在一起交，很難分辨「哪裡是機制壞了」與
 *     「哪裡只是措辭不好」。
 *
 * ZH: 用法：HTML 或 JS 產生的元素加 `data-i18n="key"`，
 *     prefs.js 會在套用語言時把 textContent 換掉。
 *     另有 `data-i18n-placeholder` 與 `data-i18n-aria`。
 *
 * ⚠ **字典裡沒有的 key 一律維持原文，不清空。**
 *     翻譯還沒補齊的期間，畫面會是中英混雜——那比一片空白好，
 *     而且哪些還沒翻**一眼就看得出來**（這是 2b 的工作清單）。
 * ========================================================================== */
(function (global) {
    'use strict';

    global.I18N = {
        zh: {
            // 頂部列
            nav_myai: 'MYAI',
            nav_lab: 'Lab',
            brand: 'MCU AI Base',
            // 帳號選單
            acct_menu: '帳號選單',
            acct_loading: '載入中…',
            acct_anon: '未登入',
            acct_go_login: '前往登入',
            acct_usage: '使用量明細',
            acct_report: '問題回報',
            acct_admin: '管理介面',
            acct_logout: '登出',
            acct_unknown: '（不明）',
            // 角色
            role_student: '學生',
            role_teacher: '教師',
            role_admin: '管理員',
            // 顯示設定
            prefs_title: '顯示設定',
            prefs_font: '字級',
            prefs_font_smaller: '縮小字級',
            prefs_font_bigger: '放大字級',
            prefs_font_reset: '還原為 100%',
            prefs_lang: '語言',
            prefs_saved_local_only: '已在這台機器上套用，但沒有存回帳號（稍後再試）。',
        },
        en: {
            nav_myai: 'MYAI',
            nav_lab: 'Lab',
            brand: 'MCU AI Base',
            acct_menu: 'Account menu',
            acct_loading: 'Loading…',
            acct_anon: 'Not signed in',
            acct_go_login: 'Go to sign in',
            acct_usage: 'Usage details',
            acct_report: 'Report a problem',
            acct_admin: 'Admin console',
            acct_logout: 'Sign out',
            acct_unknown: '(unknown)',
            role_student: 'Student',
            role_teacher: 'Teacher',
            role_admin: 'Administrator',
            prefs_title: 'Display',
            prefs_font: 'Text size',
            prefs_font_smaller: 'Smaller text',
            prefs_font_bigger: 'Larger text',
            prefs_font_reset: 'Reset to 100%',
            prefs_lang: 'Language',
            prefs_saved_local_only: 'Applied on this device, but not saved to your account. Try again later.',
        },
    };
})(window);
