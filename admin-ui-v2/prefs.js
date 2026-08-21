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
    var KEY_THEME = 'ai_hud_theme';
    var MIN = 80, MAX = 150;              // ZH: 與後端 schemas.FONT_SCALE_MIN/MAX 一致
    var LANGS = ['zh', 'en'];
    var THEMES = ['yellow', 'blue'];

    var state = { ui_font_scale: 100, ui_lang: 'zh', ui_theme: 'yellow' };

    function clampScale(v) {
        var n = parseInt(v, 10);
        if (isNaN(n)) return 100;
        return Math.min(MAX, Math.max(MIN, n));
    }
    function okLang(v) { return LANGS.indexOf(v) >= 0 ? v : 'zh'; }
    function okTheme(v) { return THEMES.indexOf(v) >= 0 ? v : 'yellow'; }

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

    // ZH: 上一次真的套用過的語言。用來判斷「這次是不是**改變**」。
    var _lastLang = null;

    // ZH: 色系。原本九個頁面各寫一份切換處理，**只有 app.js 那份會存/還原**，
    //     其餘八頁改了就忘——症狀正是「有些頁面換了顏色，其他頁面還沒變」。
    //     與 tz.js、topbar 同一類：同一條規則寫了 N 份，只有一份是完整的。
    function applyTheme(name) {
        var t = okTheme(name);
        document.documentElement.dataset.theme = t;
        document.querySelectorAll('[data-set-theme]').forEach(function (b) {
            b.setAttribute('aria-pressed', String(b.dataset.setTheme === t));
        });
    }

    function apply() {
        applyScale(state.ui_font_scale);
        applyTheme(state.ui_theme);
        applyLang(state.ui_lang);
        // ZH: 讓後加進 DOM 的東西（chrome.js 的選單）也能重新套用。
        document.dispatchEvent(new CustomEvent('prefs:applied', { detail: getState() }));

        // ⚠ ZH: **字典掃描只換得掉 `data-i18n` 元素。**
        //   各頁 JS 產生的內容（「查看全部 2 則」「使用量明細」這種組合字串）
        //   沒有那個屬性，就地切換語言時會留在原本的語言——
        //   實測在部署上抓到：切成英文後首頁仍有兩處中文。
        //   所以語言**改變**時另發一個事件，讓各頁重跑自己的 render。
        //   為什麼不共用 prefs:applied：頁面 JS 早於 DOMContentLoaded 執行，
        //   會接到「初次套用」那一發而白跑一次載入。
        if (_lastLang !== null && _lastLang !== state.ui_lang) {
            document.dispatchEvent(new CustomEvent('prefs:langchanged', { detail: getState() }));
        }
        _lastLang = state.ui_lang;
    }

    function getState() {
        return { ui_font_scale: state.ui_font_scale, ui_lang: state.ui_lang, ui_theme: state.ui_theme };
    }

    // ── 快取（第一次繪製前就要套用，所以是同步的）────────────────────
    function loadCache() {
        state.ui_font_scale = clampScale(localStorage.getItem(KEY_SCALE) || 100);
        state.ui_lang = okLang(localStorage.getItem(KEY_LANG) || 'zh');
        // ZH: 'v2-theme' 是舊鍵（只有 app.js 用過）。讀得到就沿用，使用者不會突然被重設。
        state.ui_theme = okTheme(localStorage.getItem(KEY_THEME)
                                 || localStorage.getItem('v2-theme') || 'yellow');
    }
    function saveCache() {
        localStorage.setItem(KEY_SCALE, String(state.ui_font_scale));
        localStorage.setItem(KEY_LANG, state.ui_lang);
        localStorage.setItem(KEY_THEME, state.ui_theme);
    }

    // ── 與帳號對帳 ────────────────────────────────────────────────────
    // ZH: 由 chrome.js 呼叫（它本來就會打 /auth/me，不要再打第二次）。
    //     登入頁沒有 chrome.js，就只用快取——那裡也還沒有帳號可對。
    //
    // ⚠⚠ **「後端沒有這個欄位」不等於「後端說要用預設值」。**
    //   原本寫成 `okLang(me.ui_lang || 'zh')`，於是後端沒回這個欄位時
    //   會被解讀成「帳號設定是中文」，**把使用者剛選的英文蓋掉**。
    //
    //   實測（部署中的 Docker 後端就是這個情況——它的映像早於這個功能）：
    //     選了英文 → 畫面變英文 ✅
    //     /auth/me 回來（沒有 ui_lang 欄位）→ **一秒後整頁跳回中文** 🔴
    //   使用者看到的症狀是「很多地方沒有英文」＋「設定不持久化」，
    //   而那是**同一個原因**。
    //
    //   缺值必須是 no-op：欄位不在就維持目前的值，不要當成預設值。
    //   （與 archgraph 規格 §26.3「缺值不得以哨兵值表示」同一件事。）
    function syncFrom(me) {
        if (!me) return;
        var s = (me.ui_font_scale == null) ? state.ui_font_scale : clampScale(me.ui_font_scale);
        var l = (me.ui_lang == null) ? state.ui_lang : okLang(me.ui_lang);
        var th = (me.ui_theme == null) ? state.ui_theme : okTheme(me.ui_theme);
        if (s === state.ui_font_scale && l === state.ui_lang && th === state.ui_theme) return;
        state.ui_font_scale = s;
        state.ui_lang = l;
        state.ui_theme = th;
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
        if (patch.ui_theme != null) state.ui_theme = okTheme(patch.ui_theme);
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
    // ZH: 立刻套用，不等 DOMContentLoaded —— 等的話會先看到未縮放／舊色系的一瞬間。
    applyScale(state.ui_font_scale);
    document.documentElement.dataset.theme = state.ui_theme;

    // ZH: 色系鈕的處理也集中在這裡（九頁各寫一份就是這次的 bug）。
    //     用委派而不是逐一綁定：chrome.js 之後才建的按鈕也接得到。
    document.addEventListener('click', function (ev) {
        var b = ev.target && ev.target.closest && ev.target.closest('[data-set-theme]');
        if (b) set({ ui_theme: b.dataset.setTheme });
    });
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', apply);
    } else {
        apply();
    }

    // ZH: 全域捷徑。各頁 JS 產生的文案用 `T('key', '中文原文')`——
    //     第二個參數是 fallback，字典缺 key 時維持中文而不是變空白。
    global.T = function (key, fallback) {
        var dict = (global.I18N && global.I18N[state.ui_lang]) || null;
        return (dict && dict[key]) || fallback;
    };

    global.Prefs = {
        MIN: MIN, MAX: MAX, LANGS: LANGS, THEMES: THEMES,
        get: getState, set: set, syncFrom: syncFrom, apply: apply,
        t: function (key, fallback) {
            var dict = (global.I18N && global.I18N[state.ui_lang]) || null;
            return (dict && dict[key]) || fallback;
        },
    };
})(window);
