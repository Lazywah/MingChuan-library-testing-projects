/* ==========================================================================
 * tip.js — 資訊 icon + 說明泡泡（共用檔）
 *
 * ZH: ⚠ **這是共用檔**：web-ui-V1 是正本，admin-ui-V1 逐位元組相同。
 *     只改正本，然後跑 `python scripts/check_shared_ui_files.py --fix`。
 *
 * ZH: v3.9 原本住在 web-ui-V1/chrome.js 裡。搬出來的理由：管理端也要用，
 *     而管理端載的是 admin-chrome.js —— 複製一份過去就是同一條規則的
 *     兩份實作，改一邊忘另一邊時**不會有任何錯誤訊息**，
 *     只是有些頁面的 icon 點了沒反應。
 * ========================================================================== */
/* ==========================================================================
 * ZH: 資訊 icon + 說明泡泡（v3.9）
 *
 * ZH: 目的：把「看一次就夠」的補充說明從畫面上收起來，只留真正要決策的字。
 *     小字太多的頁面，讀者會**整片跳過** —— 包含其中真正重要的那一句。
 *
 * ZH: 🔴 為什麼是 <button> + 點擊切換，而不是 CSS 的 :hover：
 *       · 手機沒有 hover。純 hover 的 tooltip 在觸控裝置上等於那段字不存在。
 *       · 鍵盤使用者 Tab 不到 <span>，螢幕閱讀器也不會唸。
 *       · WCAG 1.4.13 要求「可關閉、可停留、不會自己消失」——
 *         hover 版三條都做不到。
 *
 * ZH: 說明文字**留在 DOM 裡**（hidden + aria-describedby），不是塞在
 *     title 屬性或 JS 變數裡 —— 那樣螢幕閱讀器與 Ctrl+F 都找不到它。
 *
 * ZH: 用法：
 *     <span class="tip">
 *       <button type="button" class="tip__btn" aria-expanded="false"
 *               aria-controls="tip-x" aria-label="說明">i</button>
 *       <span class="tip__body" id="tip-x" role="tooltip" hidden>…</span>
 *     </span>
 * ========================================================================== */
(function () {
    'use strict';

    function closeAll(except) {
        document.querySelectorAll('.tip__btn[aria-expanded="true"]').forEach(function (b) {
            if (b === except) return;
            b.setAttribute('aria-expanded', 'false');
            var body = document.getElementById(b.getAttribute('aria-controls'));
            if (body) body.hidden = true;
        });
    }

    // ZH: 委派在 document 上 —— 泡泡可能是頁面 JS 後來才建的（例如存檔清單）。
    //     逐一綁定的話，後來建的那些點了不會有反應，而且沒有錯誤訊息。
    document.addEventListener('click', function (ev) {
        var btn = ev.target.closest ? ev.target.closest('.tip__btn') : null;
        if (!btn) { closeAll(null); return; }   // ZH: 點別處就全部收起來
        ev.preventDefault();
        var body = document.getElementById(btn.getAttribute('aria-controls'));
        if (!body) return;
        var open = btn.getAttribute('aria-expanded') === 'true';
        closeAll(btn);
        btn.setAttribute('aria-expanded', open ? 'false' : 'true');
        body.hidden = open;
        if (!open) fit(body);
    });

    /* ZH: 泡泡預設從 icon 往右長。icon 靠近視窗右緣時會**被切掉**，
     *     而且會撐出一條橫向捲軸 —— 實測在置中的卡片標題上就會發生。
     * ZH: 用 JS 量了再推，不用 CSS 的 `.tip--right` 手動指定：
     *     那要每個使用點自己判斷「我會不會靠右」，而那件事取決於視窗寬度，
     *     寫死在 class 上一定會有猜錯的時候。
     * ZH: 每次打開都先歸零再量 —— 不歸零的話上一次的位移會被算進這一次。
     */
    function fit(body) {
        body.style.transform = '';
        var pad = 8;
        var r = body.getBoundingClientRect();
        var over = r.right - (document.documentElement.clientWidth - pad);
        if (over > 0) body.style.transform = 'translateX(' + (-Math.ceil(over)) + 'px)';
        // ZH: 推完可能反而戳出左邊（視窗比泡泡還窄）—— 那就靠左貼齊。
        r = body.getBoundingClientRect();
        if (r.left < pad) body.style.transform = 'translateX(' + Math.ceil(pad - r.left) + 'px)';
    }

    // ZH: Esc 關閉並把焦點還給按鈕 —— 不還的話鍵盤使用者會不知道自己在哪。
    document.addEventListener('keydown', function (ev) {
        if (ev.key !== 'Escape') return;
        var open = document.querySelector('.tip__btn[aria-expanded="true"]');
        if (!open) return;
        closeAll(null);
        open.focus();
    });
})();
