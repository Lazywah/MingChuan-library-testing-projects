/* ==========================================================================
 * visits.js — 網站到訪人次（v4.24）
 *
 * ZH: 首頁與登入頁底下那三個數字：本日 / 本月 / 累計（擁有者需求 2026-09-23）。
 *
 * ZH: 🔴 算的是**人次**，不是人數 —— 同一位訪客**當天**只算一次，隔天再來
 *     會再算一次（去重在後端，見 services/visit_counter.py 的檔頭）。
 *     介面上的字也要寫「人次」：寫成「人數」的話，一個每天來的人會讓
 *     數字每天 +1，而看的人會以為那是新的人。
 *
 * ZH: 🔴 **為什麼是獨立的一支，不寫在 chrome.js 裡**：
 *       · 登入頁**不載 chrome.js**（它刻意沒有頂部列的那一套），
 *         而登入頁正是未登入訪客真正會看到的那一頁 —— 首頁沒登入會被導走。
 *       · chrome.js 是**與管理端共用的正本**，放進去等於把管理端的瀏覽
 *         也算進「網站到訪」。
 *
 * ZH: ⚠ 這一段的任何失敗都不可以影響頁面 —— 它只是一個數字。
 *     localStorage 在無痕模式會丟例外，一律 try 包住；送不出去就算了。
 * ========================================================================== */
(function () {
    'use strict';

    var API = '/api/v1';
    var ID_KEY = 'ai_hud_visitor';        // ZH: 隨機訪客 id（localStorage）
    var SENT_KEY = 'ai_hud_visit_sent';   // ZH: 這個工作階段送過的日期（sessionStorage）

    /* ZH: 為什麼要在前端放一個 id：校園是 NAT，幾百個人共用一個對外 IP，
     *     後端只靠 IP 去重的話整棟樓會被算成一個人。
     * ZH: 這個 id 是**隨機的**，不含任何身分資訊，而且後端不原樣存 ——
     *     它存的是把日期揉進去的雜湊，跨天對不起來。
     */
    function visitorId() {
        try {
            var v = localStorage.getItem(ID_KEY);
            if (!v) {
                v = (window.crypto && window.crypto.randomUUID)
                    ? window.crypto.randomUUID().replace(/-/g, '').slice(0, 16)
                    // ZH: crypto 不在（舊瀏覽器／非安全來源）就退回亂數。
                    //     這不是安全機制，重點只是夠分散。
                    : (Date.now().toString(36) + Math.random().toString(36).slice(2, 10));
                localStorage.setItem(ID_KEY, v);
            }
            return v;
        } catch (e) {
            return '';                    // ZH: 存不了就不帶 —— 後端會退回 IP+UA
        }
    }

    function render(d) {
        var box = document.querySelector('[data-visits]');
        if (!box || !d) return;
        [['today', d.today], ['month', d.month], ['total', d.total]].forEach(function (p) {
            var el = box.querySelector('[data-visits-' + p[0] + ']');
            // ZH: 千分位 —— 五位數以上不分節的話一眼看不出是幾萬。
            if (el) el.textContent = Number(p[1] || 0).toLocaleString();
        });
        box.hidden = false;               // ZH: 有數字才顯示（見 index.html 的說明）
    }

    async function run() {
        var today = new Date().toISOString().slice(0, 10);
        var sent = '';
        try { sent = sessionStorage.getItem(SENT_KEY) || ''; } catch (e) { }

        try {
            // ZH: 這個工作階段已經送過 → 只讀不寫。換頁不該讓數字長大。
            if (sent === today) {
                var g = await fetch(API + '/system/visits');
                if (g.ok) render(await g.json());
                return;
            }
            var r = await fetch(API + '/system/visit', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ visitor_id: visitorId() }),
            });
            if (!r.ok) return;
            try { sessionStorage.setItem(SENT_KEY, today); } catch (e) { }
            render(await r.json());
        } catch (e) {
            // ZH: 只是一個數字，壞了就安靜地不顯示 —— 不要在頁面上留錯誤訊息。
        }
    }

    // ZH: 立刻跑，不等 load —— 它不碰版面（只填一個預設 hidden 的區塊）。
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', run);
    } else {
        run();
    }

    // ZH: 對外只留一支 refresh —— 之後若要在別處手動更新數字用得上。
    window.Visits = { refresh: run };
}());
