/* ==========================================================================
 * prefs.js — 介面偏好（字級 / 語言）的套用與保存
 *
 * ZH: **設定跟帳號走，不跟裝置走**（擁有者裁定 2026-08-20）：
 *     換一台機器登入，字級與語言要跟著在。真相在 `users.ui_font_scale / ui_lang`，
 *     由 `GET /auth/me` 回、`PATCH /auth/me/preferences` 存。
 *
 * ⚠ **localStorage 是快取，不是真相。**
 *     只靠後端的話，頁面會先用預設值（100% / 中文）畫一次，等 /auth/me 回來再跳一下——
 *     字級尤其明顯，整頁會抖。所以流程是：
 *         載入 → 立刻用快取套用（同步，第一次繪製前）
 *         /auth/me 回來 → 與快取對帳，不同才重套並更新快取
 *     使用者改設定時：立刻套用 + 寫快取 → 送 PATCH（失敗只提示，不回滾畫面）。
 *
 * ⚠ **這支必須載入在 login.html 上。** 登入頁也要吃語言與字級——
 *     不然使用者設了英文，登入頁還是中文，而那是他每次進站看到的第一個畫面。
 *     （chrome.js 相反：登入頁**不**該有帳號選單。兩者的載入範圍刻意不同。）
 *
 * ⚠ **字級只放大文字，不放大間距。** v2 的 --space-* 與 --tap-min 是 px，
 *     只有字體走 rem。150% 時要確認固定高度的元件（topbar 56px 等）不爆版。
 * ========================================================================== */
(function (global) {
    'use strict';

    var API = '/api/v1';
    var KEY_SCALE = 'ai_hud_font_scale';
    var KEY_LANG = 'ai_hud_lang';
    var MIN = 80, MAX = 150;              // ZH: 與後端 schemas.FONT_SCALE_MIN/MAX 一致
    var LANGS = ['zh', 'en'];

    var state = { ui_font_scale: 100, ui_lang: 'zh' };

    function clampScale(v) {
        var n = parseInt(v, 10);
        if (isNaN(n)) return 100;
        return Math.min(MAX, Math.max(MIN, n));
    }
    function okLang(v) { return LANGS.indexOf(v) >= 0 ? v : 'zh'; }

    function authHeaders() {
        var t = sessionStorage.getItem('ai_hud_token') || localStorage.getItem('ai_hud_token');
        return t ? { Authorization: 'Bearer ' + t } : {};
    }

    // ── 套用 ──────────────────────────────────────────────────────────
    // ZH: 用**百分比**，相對「瀏覽器預設字級」。v2 的字級全是 rem，所以整體跟著縮放。
    //
    // ⚠ **這是刻意的：使用者自己的瀏覽器字級設定要被尊重**（擁有者裁定 2026-08-20：
    //   「有個別人確實需要」）。把瀏覽器預設調大的人，多半是真的需要——
    //   用 px 蓋掉它等於默默取消他的無障礙設定。
    //
    //   代價是「100%」在不同機器解出的絕對值可能不同（瀏覽器預設 20px 的人，
    //   100% 就是 20px）。這是**知情的取捨**：跟著帳號走的是「相對於你習慣的大小
    //   放大幾成」，不是「幾個像素」——對使用者而言那反而是對的語意。
    //
    //   ⚠ 因此 styles.css 的 root 必須是 `font-size: 100%` 而**不能釘 px**：
    //   inline 百分比是相對瀏覽器預設算的（實測：CSS 釘 20px 時 inline 150% 仍得 24px），
    //   CSS 釘 px 只會讓 JS 跑起來前先畫錯一次，關掉 JS 更是永遠被壓住。
    function applyScale(p) {
        document.documentElement.style.fontSize = clampScale(p) + '%';
    }

    function applyLang(lang) {
        document.documentElement.lang = lang === 'en' ? 'en' : 'zh-Hant';
        var dict = (global.I18N && global.I18N[lang]) || null;
        if (!dict) return;                 // ZH: 沒有字典就維持原文，不要清空畫面
        document.querySelectorAll('[data-i18n]').forEach(function (el) {
            var v = dict[el.getAttribute('data-i18n')];
            if (v) el.textContent = v;
        });
        document.querySelectorAll('[data-i18n-placeholder]').forEach(function (el) {
            var v = dict[el.getAttribute('data-i18n-placeholder')];
            if (v) el.placeholder = v;
        });
        document.querySelectorAll('[data-i18n-aria]').forEach(function (el) {
            var v = dict[el.getAttribute('data-i18n-aria')];
            if (v) el.setAttribute('aria-label', v);
        });
    }

    function apply() {
        applyScale(state.ui_font_scale);
        applyLang(state.ui_lang);
        // ZH: 讓後加進 DOM 的東西（chrome.js 的選單）也能重新套用。
        document.dispatchEvent(new CustomEvent('prefs:applied', { detail: getState() }));
    }

    function getState() { return { ui_font_scale: state.ui_font_scale, ui_lang: state.ui_lang }; }

    // ── 快取（第一次繪製前就要套用，所以是同步的）────────────────────
    function loadCache() {
        state.ui_font_scale = clampScale(localStorage.getItem(KEY_SCALE) || 100);
        state.ui_lang = okLang(localStorage.getItem(KEY_LANG) || 'zh');
    }
    function saveCache() {
        localStorage.setItem(KEY_SCALE, String(state.ui_font_scale));
        localStorage.setItem(KEY_LANG, state.ui_lang);
    }

    // ── 與帳號對帳 ────────────────────────────────────────────────────
    // ZH: 由 chrome.js 呼叫（它本來就會打 /auth/me，不要再打第二次）。
    //     登入頁沒有 chrome.js，就只用快取——那裡也還沒有帳號可對。
    function syncFrom(me) {
        if (!me) return;
        var s = clampScale(me.ui_font_scale == null ? 100 : me.ui_font_scale);
        var l = okLang(me.ui_lang || 'zh');
        if (s === state.ui_font_scale && l === state.ui_lang) return;   // 相同就不重畫
        state.ui_font_scale = s;
        state.ui_lang = l;
        saveCache();
        apply();
    }

    // ── 使用者改設定 ──────────────────────────────────────────────────
    // ZH: 先套用再送出。送失敗**不回滾畫面**——他看到的就是他選的；
    //     回滾會讓人以為自己按錯了。改為回傳 false 讓呼叫端提示「這台機器上有效，
    //     但沒存回帳號」。
    async function set(patch) {
        if (patch.ui_font_scale != null) state.ui_font_scale = clampScale(patch.ui_font_scale);
        if (patch.ui_lang != null) state.ui_lang = okLang(patch.ui_lang);
        saveCache();
        apply();
        try {
            var r = await fetch(API + '/auth/me/preferences', {
                method: 'PATCH',
                headers: Object.assign({ 'Content-Type': 'application/json' }, authHeaders()),
                body: JSON.stringify(getState()),
            });
            return r.ok;
        } catch (e) {
            return false;
        }
    }

    loadCache();
    // ZH: 立刻套用，不等 DOMContentLoaded —— 等的話會先看到未縮放的一瞬間。
    applyScale(state.ui_font_scale);
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', apply);
    } else {
        apply();
    }

    global.Prefs = {
        MIN: MIN, MAX: MAX, LANGS: LANGS,
        get: getState, set: set, syncFrom: syncFrom, apply: apply,
        t: function (key, fallback) {
            var dict = (global.I18N && global.I18N[state.ui_lang]) || null;
            return (dict && dict[key]) || fallback;
        },
    };
})(window);
