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
        if (open) { reset(body); } else { place(btn, body); }
    });

    // ZH: 捲動時把泡泡收起來。fixed 定位的東西**不會跟著內容捲** ——
    //     不收的話它會停在原地，指著一個已經捲走的欄位。
    // ZH: capture + passive：表格自己的橫向捲動也要收得到（那個事件不會冒泡到
    //     document），而 passive 讓它不影響捲動的流暢度。
    document.addEventListener('scroll', function () {
        if (document.querySelector('.tip__btn[aria-expanded="true"]')) closeAll(null);
    }, { capture: true, passive: true });

    /* ZH: 🔴 泡泡用 `position: fixed`，不是 `absolute`。
     *
     * ZH: absolute 會被**任何一個有 overflow 的祖先切掉**。實際踩到：
     *     數據頁的表格包在 `.adm-tablewrap`（overflow-x: auto）裡，
     *     表頭上的泡泡只露出表格高度以內的那一小截。
     *     這與 `<dialog>` 用 top layer 的理由是同一件事。
     *
     * ZH: fixed 的座標是視窗座標，所以要自己算 —— 從按鈕的位置推。
     * ZH: ⚠ fixed 仍然會被 `transform` / `filter` / `contain` 的祖先困住
     *     （那些會建立新的 containing block）。目前的表格祖先沒有那些，
     *     真的遇到的話症狀是「泡泡跑到奇怪的地方」，不是被切掉。
     *
     * ZH: 每次打開都先歸零再量 —— 不歸零的話上一次的座標會被算進這一次的量測。
     */
    function reset(body) {
        body.style.position = '';
        body.style.left = '';
        body.style.top = '';
        body.style.transform = '';
    }

    function place(btn, body) {
        reset(body);
        body.style.position = 'fixed';
        body.style.left = '0px';
        body.style.top = '0px';

        var pad = 8;
        // ZH: 🔴 與按鈕的間隙要**比陰影長**。泡泡的陰影是 `0 4px 12px`，
        //     往下大約延伸 16px —— 間隙只留 4px 的話，往上翻時那層灰
        //     會落在表頭文字上，看起來像被蓋到（實際回報過）。
        //     ⚠ 改 .tip__body 的 box-shadow 時要一起看這個值：
        //     間隙必須 > offsetY + blur，否則陰影會壓在下面那一列上。
        var gap = 20;
        var vw = document.documentElement.clientWidth;
        var vh = document.documentElement.clientHeight;
        var r = btn.getBoundingClientRect();
        var b = body.getBoundingClientRect();

        // ZH: 預設貼在按鈕左緣下方；超出右緣就往左推，推過頭就靠左貼齊。
        var left = r.left;
        if (left + b.width > vw - pad) left = vw - pad - b.width;
        if (left < pad) left = pad;

        // ZH: 🔴 **優先往上**（擁有者裁定 2026-08-30）。
        //     往下長會蓋住 icon 底下的東西 —— 在表格裡那正是使用者
        //     正要讀的資料列。往上蓋的是已經看過的區域，代價小得多。
        // ZH: 上面放不下才往下。兩邊都放不下時往下 —— 從畫面底部被切掉
        //     還捲得到，從頂端被切掉則是連捲都捲不出來。
        var top = r.top - b.height - gap;
        if (top < pad) {
            top = r.bottom + gap;
        }

        body.style.left = Math.round(left) + 'px';
        body.style.top = Math.round(top) + 'px';
    }

})();
