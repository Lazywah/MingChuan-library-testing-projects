/* ==========================================================================
 * tour.js — 首次登入的引導導覽（v4.26）
 *
 * ZH: 首頁改版之後六個入口從卡片移到頂部列下拉 —— 入口還在，但不再是
 *     「打開首頁就看得到」。所以新使用者需要有人帶一遍（擁有者需求 2026-09-23）。
 *
 * ZH: 🔴 **跨頁**：首頁 → MYAI →（訓練 → 實驗室）→ 回首頁。
 *     所以有兩種狀態，而且**刻意存在不同的地方**：
 *       · 「看過了」→ 帳號（`users.ui_dismissed` 的 `tour` key，由 prefs.js 管）
 *         換一台裝置也記得，這是使用者的偏好。
 *       · 「走到第幾步」→ sessionStorage
 *         那是一次性的進度。寫進帳號的話，「我昨天走到一半」會在另一台
 *         電腦上莫名其妙接著跑。
 *
 * ZH: 🔴 **開始之前一定要等初次設定結束。** 那個彈窗（chrome.js 的
 *     `maybeShowOnboarding`）也綁在首次登入，z-index 1000、蓋滿整頁，
 *     而且 `html:has(.onb){overflow:hidden}` 會鎖住捲動。兩個遮罩疊在一起
 *     會變成一團。做法見 `waitForOnboarding()`。
 *
 * ZH: ⚠ 沒有「跳過」鈕（擁有者裁定：步數不多，就讓大家看一遍），
 *     但**一定有 ×，Esc 也能關**。理由不是禮貌，是**逃生**：
 *     版面改版後選擇器失效、或哪一步算錯座標時，沒有出口等於把人鎖在首頁。
 *     同理，`stepsFor()` 會把「目標不存在」的步驟先濾掉 —— 導覽要走得完，
 *     不是卡住。
 *
 * ZH: ⚠ 換頁只在使用者按「下一步」時發生，不自動導航。
 * ========================================================================== */
(function (global) {
    'use strict';

    var SEEN_KEY = 'tour';                    // ZH: ui_dismissed 裡的 key
    var PROGRESS_KEY = 'ai_hud_tour_step';    // ZH: sessionStorage 的進度

    /* ZH: 步驟表。`page` 是這一步要在哪一頁演，`target` 是要圈住誰
     *     （null = 置中的卡片，不圈任何東西）。
     * ZH: `gpu: true` 的步驟在 GPU 功能暫停時會被濾掉（見 stepsFor）——
     *     那兩頁那時會被 chrome.js 擋成「這項功能暫停使用」，
     *     帶人過去只會看到一片空白。
     * ZH: ⚠ 文案用 `T('key', '中文')` 的形狀寫，check_i18n 才看得到
     *     （它認「key 後面接含中文的字串」）。key 少一邊翻譯就會 FAIL。
     */
    var STEPS = [
        { id: 'hello',  page: 'index.html', target: null,
          t: ['tour_hello_t', '歡迎使用 AI 基地'],
          d: ['tour_hello_d', '大約 30 秒，帶你看一遍這裡有什麼、東西放在哪。'] },
        { id: 'lines',  page: 'index.html', target: '.lines',
          t: ['tour_lines_t', '三條路，由淺入深'],
          d: ['tour_lines_d', '不知道從哪開始就從 1 開始：先用現成的 AI 工具，再跑一次訓練，最後自己寫程式。'] },
        { id: 'myai',   page: 'myai.html',  target: '#balance-card',
          t: ['tour_myai_t', '1 · 付費版 AI 工具'],
          d: ['tour_myai_d', '聊天與文書都在這裡。上面那個數字是你的額度，用完會自動補。'] },
        { id: 'train',  page: 'gpu.html',   target: '.primary-card', gpu: true,
          t: ['tour_train_t', '2 · 體驗現有模型訓練'],
          d: ['tour_train_d', '選一個範例按下去就開始，約 20 分鐘。不用準備自己的資料。'] },
        { id: 'lab',    page: 'lab.html',   target: '.primary-card', gpu: true,
          t: ['tour_lab_t', '3 · 程式實驗室'],
          d: ['tour_lab_d', '瀏覽器裡的 VS Code，可以寫自己的程式並送去 GPU 訓練。'] },
        { id: 'nav',    page: 'index.html', target: '.topnav',
          t: ['tour_nav_t', '其他入口都在這裡'],
          d: ['tour_nav_d', '訓練進度、資料集、使用量、文件庫、GPU 忙不忙、問題回報 —— 都在上面這排選單裡。'] },
        { id: 'bot',    page: 'index.html', target: '#aibot-fab',
          t: ['tour_bot_t', '不會用就問小基'],
          d: ['tour_bot_d', '右下角這顆隨時都在。想再看一次這個導覽，右上角帳號選單裡有。'] },
    ];

    // ── 純函式（tests/tour.test.js 測的就是這一段）────────────────────
    //
    // ZH: 🔴 這幾支刻意不碰 DOM、不碰 storage —— 跨頁狀態機是這個功能最容易
    //     錯的地方，而它在瀏覽器裡很難重現（要真的登入、真的換頁）。
    //     把判斷抽成純函式，node 就測得動（前例：tests/tz.test.js）。

    /* ZH: 這次要走哪幾步。
     *   gpuOn=false → 濾掉 GPU 的兩站
     *   has(sel)    → 回傳「這個選擇器現在找不找得到」，找不到的步驟也濾掉
     * ZH: ⚠ `has` 只對**目前這一頁**的步驟有意義（別頁的元素當然找不到），
     *     所以只對 `page === here` 的步驟問。
     */
    function stepsFor(opts) {
        var o = opts || {};
        var here = o.here || '';
        var has = o.has || function () { return true; };
        return STEPS.filter(function (s) {
            if (s.gpu && !o.gpuOn) return false;
            if (s.target && s.page === here && !has(s.target)) return false;
            return true;
        });
    }

    /* ZH: 從 index 往後找下一個「演得出來」的步驟。回 -1 代表沒有了（該結束）。
     * ZH: ⚠ 回傳的是**索引**不是步驟 —— 呼叫端要把它寫進進度，
     *     而進度存的就是索引。
     */
    function nextIndex(steps, from) {
        var i = (typeof from === 'number' ? from : -1) + 1;
        return i < steps.length ? i : -1;
    }

    function prevIndex(steps, from) {
        var i = (typeof from === 'number' ? from : 0) - 1;
        return i >= 0 ? i : 0;
    }

    /* ZH: 現在這一頁的檔名（跨頁時用來判斷要不要導航）。
     * ZH: 根路徑（`/V1/`）當成 index.html —— nginx 的 index 指令會給那一頁，
     *     而路徑上看不出來。
     */
    function pageName(path) {
        var last = String(path || '').split('/').pop();
        return last === '' ? 'index.html' : last;
    }

    global.Tour = {
        STEPS: STEPS,
        stepsFor: stepsFor,
        nextIndex: nextIndex,
        prevIndex: prevIndex,
        pageName: pageName,
        SEEN_KEY: SEEN_KEY,
        PROGRESS_KEY: PROGRESS_KEY,
    };

    // ZH: 在 node 裡（測試）就到此為止 —— 下面全是 DOM。
    if (typeof document === 'undefined') return;

    // ── 以下是瀏覽器端 ────────────────────────────────────────────────
    var steps = [];
    var cur = -1;
    var box = null;       // 說明卡
    var ring = null;      // 高亮框
    var veil = null;      // 遮罩

    function T(key, fallback) {
        try { return (global.T ? global.T(key, fallback) : fallback); }
        catch (e) { return fallback; }
    }

    function esc(v) {
        return String(v == null ? '' : v).replace(/[&<>"']/g, function (c) {
            return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
        });
    }

    function readProgress() {
        try {
            var v = sessionStorage.getItem(PROGRESS_KEY);
            return v === null ? null : parseInt(v, 10);
        } catch (e) { return null; }      // ZH: 無痕模式會丟例外
    }

    function writeProgress(i) {
        try {
            if (i === null) sessionStorage.removeItem(PROGRESS_KEY);
            else sessionStorage.setItem(PROGRESS_KEY, String(i));
        } catch (e) { /* ZH: 記不住只是換頁後導覽不會續走，不是錯誤 */ }
    }

    // ── 畫面 ──────────────────────────────────────────────────────────

    function teardown() {
        [veil, ring, box].forEach(function (el) { if (el) el.remove(); });
        veil = ring = box = null;
        document.removeEventListener('keydown', onKey);
        global.removeEventListener('resize', reposition);
        global.removeEventListener('scroll', reposition, true);
        document.documentElement.classList.remove('tour-open');
    }

    /* ZH: 結束導覽。`seen` 為真才記進帳號。
     * ZH: ⚠ 按 × 也算看過 —— 不然他每次重新整理都會再被攔一次，
     *     而那正是他剛剛用 × 表達不想要的事。
     */
    function finish(seen) {
        teardown();
        writeProgress(null);
        cur = -1;
        if (seen && global.Prefs && global.Prefs.dismiss) {
            try { global.Prefs.dismiss(SEEN_KEY); } catch (e) { /* 存不了下次再問 */ }
        }
    }

    function onKey(ev) {
        if (ev.key === 'Escape') { ev.preventDefault(); finish(true); }
        else if (ev.key === 'ArrowRight') { ev.preventDefault(); go(1); }
        else if (ev.key === 'ArrowLeft') { ev.preventDefault(); go(-1); }
    }

    /* ZH: 把高亮框與說明卡放到目標旁邊。
     * ZH: ⚠ 用 `position: fixed` + `getBoundingClientRect()`（視窗座標）——
     *     所以捲動與 resize 都要重算，而不是算一次就好。
     */
    function reposition() {
        if (!box) return;
        var s = steps[cur];
        var el = s && s.target ? document.querySelector(s.target) : null;

        if (!el) {
            // ZH: 沒有目標（歡迎那一步）或目標不見了 → 置中，不畫框，
            //     這時由遮罩負責變暗（見 web.css 的 .tour__veil--dim）。
            if (ring) ring.hidden = true;
            if (veil) veil.classList.add('tour__veil--dim');
            box.style.left = '50%';
            box.style.top = '50%';
            box.style.transform = 'translate(-50%, -50%)';
            return;
        }

        var r = el.getBoundingClientRect();
        var pad = 6;
        ring.hidden = false;
        // ZH: 有框了 → 暗由框的外擴陰影負責，遮罩退回透明（否則兩層疊起來）。
        if (veil) veil.classList.remove('tour__veil--dim');
        ring.style.left = (r.left - pad) + 'px';
        ring.style.top = (r.top - pad) + 'px';
        ring.style.width = (r.width + pad * 2) + 'px';
        ring.style.height = (r.height + pad * 2) + 'px';

        // ZH: 說明卡放在目標下面；下面放不下就放上面。
        //     ⚠ 用 `box.offsetHeight` 量自己 —— 文案長度會變，寫死高度遲早會撞。
        var bh = box.offsetHeight || 160;
        var below = r.bottom + 12;
        var top = (below + bh < global.innerHeight) ? below : Math.max(12, r.top - bh - 12);
        var left = Math.min(Math.max(12, r.left), Math.max(12, global.innerWidth - box.offsetWidth - 12));
        box.style.transform = 'none';
        box.style.left = left + 'px';
        box.style.top = top + 'px';
    }

    function render() {
        var s = steps[cur];
        if (!s) { finish(true); return; }

        if (!veil) {
            veil = document.createElement('div');
            veil.className = 'tour__veil';
            document.body.appendChild(veil);

            ring = document.createElement('div');
            ring.className = 'tour__ring';
            document.body.appendChild(ring);

            box = document.createElement('div');
            box.className = 'tour__box';
            box.setAttribute('role', 'dialog');
            box.setAttribute('aria-modal', 'true');
            box.setAttribute('aria-labelledby', 'tour-t');
            document.body.appendChild(box);

            document.addEventListener('keydown', onKey);
            global.addEventListener('resize', reposition);
            // ZH: 捲動要用 capture —— 捲的可能是內層容器，不是 window。
            global.addEventListener('scroll', reposition, true);
            document.documentElement.classList.add('tour-open');
        }

        var last = cur === steps.length - 1;
        box.innerHTML =
            '<button class="tour__x" type="button" id="tour-x" aria-label="'
            + esc(T('tour_close', '關閉導覽')) + '">×</button>'
            + '<p class="tour__n">' + esc(T('tour_step_n', '第 {i} 步，共 {n} 步')
                .replace('{i}', cur + 1).replace('{n}', steps.length)) + '</p>'
            + '<h2 class="tour__t" id="tour-t">' + esc(T(s.t[0], s.t[1])) + '</h2>'
            + '<p class="tour__d">' + esc(T(s.d[0], s.d[1])) + '</p>'
            + (last && !hasGpuSteps()
                ? '<p class="tour__note">' + esc(T('tour_gpu_off',
                    '（訓練與程式實驗室目前暫停開放，開放後再回來看那兩站。）')) + '</p>'
                : '')
            + '<div class="tour__btns">'
            + (cur > 0 ? '<button class="btn btn--ghost" type="button" id="tour-prev">'
                + esc(T('tour_prev', '上一步')) + '</button>' : '')
            + '<button class="btn btn--primary" type="button" id="tour-next">'
            + esc(last ? T('tour_done', '開始使用') : T('tour_next', '下一步')) + '</button>'
            + '</div>';

        box.querySelector('#tour-x').addEventListener('click', function () { finish(true); });
        box.querySelector('#tour-next').addEventListener('click', function () { go(1); });
        var prev = box.querySelector('#tour-prev');
        if (prev) prev.addEventListener('click', function () { go(-1); });

        // ZH: 把目標捲進畫面再定位 —— 目標在畫面外時框會畫在看不見的地方。
        var el = s.target ? document.querySelector(s.target) : null;
        if (el && el.scrollIntoView) {
            try { el.scrollIntoView({ block: 'center', behavior: 'auto' }); } catch (e) { }
        }
        reposition();
        box.querySelector('#tour-next').focus();
    }

    function hasGpuSteps() {
        return steps.some(function (s) { return s.gpu; });
    }

    /* ZH: 往前／往後一步。跨頁的步驟就導過去（進度已經寫進 sessionStorage，
     *     新頁面載入後 `start()` 會接著演）。
     */
    function go(dir) {
        var i = dir > 0 ? nextIndex(steps, cur) : prevIndex(steps, cur);
        if (i < 0) { finish(true); return; }
        cur = i;
        writeProgress(cur);
        var s = steps[cur];
        if (s.page !== pageName(location.pathname)) {
            teardown();                 // ZH: 先收乾淨再跳，不然遮罩會閃一下
            location.href = s.page;
            return;
        }
        render();
    }

    // ── 啟動 ──────────────────────────────────────────────────────────

    /* ZH: 等初次設定的彈窗消失（見檔頭）。沒有彈窗就立刻回來。
     * ZH: ⚠ 用 MutationObserver 而不是輪詢：那個彈窗可能停留好幾分鐘
     *     （使用者在填信箱），輪詢整段期間都在燒 CPU。
     */
    function waitForOnboarding(cb) {
        if (!document.querySelector('.onb')) { cb(); return; }
        var ob = new MutationObserver(function () {
            if (!document.querySelector('.onb')) { ob.disconnect(); cb(); }
        });
        ob.observe(document.body, { childList: true, subtree: true });
    }

    async function gpuEnabled() {
        // ZH: 讀不到設定時**當成開著** —— 與 chrome.js 的 applyGpuGate 同一個判斷
        //     （暫時性的政策，不該因為一次讀取失敗就把功能講成關閉）。
        try {
            if (!global.Chrome || !global.Chrome.publicSettings) return true;
            var st = await global.Chrome.publicSettings();
            return String(st.gpu_features_enabled) !== '0';
        } catch (e) { return true; }
    }

    /* ZH: 開始（或續走）。`force` 是「再看一次」用的 —— 忽略「看過了」。 */
    async function start(force) {
        if (!force && global.Prefs && global.Prefs.isDismissed
            && global.Prefs.isDismissed(SEEN_KEY)) return;

        var here = pageName(location.pathname);
        var gpuOn = await gpuEnabled();
        steps = stepsFor({
            here: here,
            gpuOn: gpuOn,
            has: function (sel) { return !!document.querySelector(sel); },
        });
        if (!steps.length) return;

        var saved = force ? null : readProgress();
        if (saved !== null && saved >= 0 && saved < steps.length) {
            cur = saved;
        } else {
            cur = 0;
            writeProgress(0);
        }

        // ZH: 這一步不屬於這一頁時，兩種情況要分開處理 ——
        if (steps[cur].page !== here) {
            // ZH: 🔴 **他自己按了「再看一次導覽」**（force）：那顆鈕在每一頁的
            //     帳號選單裡，而導覽從首頁開始。不帶他過去的話，
            //     在別頁按下去會**完全沒反應** —— 實測踩到過。
            if (force) location.href = steps[cur].page;
            // ZH: 續走（非 force）則不要把人抓回去 —— 他可能是自己走開的。
            //     進度留著，他回到那一頁就會接上。
            return;
        }

        waitForOnboarding(render);
    }

    global.Tour.start = start;
    global.Tour.restart = function () { writeProgress(null); start(true); };

    /* ZH: chrome.js 拿到 /auth/me 之後會發 `chrome:ready`。
     * ZH: 🔴 一定要等它，不能只等 DOMContentLoaded：
     *       · 「看過了」在 `me.ui_dismissed` 裡，那是 /auth/me 才有的
     *       · 初次設定的彈窗也是那時候才決定要不要跳
     *     早跑的後果是「每次登入都又被導覽一次」，而且與初次設定疊在一起。
     * ZH: ⚠ 登入頁不載 chrome.js，所以那一頁永遠等不到這個事件 —— 那是對的，
     *     未登入的人不需要導覽。
     */
    document.addEventListener('chrome:ready', function (ev) {
        var me = ev && ev.detail ? ev.detail.me : null;
        if (!me) return;               // ZH: 沒登入就不導
        start(false);
    });
}(window));
