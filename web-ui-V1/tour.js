/* ==========================================================================
 * tour.js — 首次登入的引導導覽（v4.27）
 *
 * ZH: 首頁改版之後六個入口從卡片移到頂部列下拉 —— 入口還在，但不再是
 *     「打開首頁就看得到」。所以新使用者需要有人帶一遍（擁有者需求 2026-09-23）。
 *
 * ZH: 🔴 **像遊戲引導：導覽自己不換頁，換頁一律由使用者點**（v4.27 改版）。
 *     v4.26 是「按下一步，程式幫你跳過去」。擁有者要的是反過來 ——
 *     圈起來的那張卡**真的點得到**，他點下去才過去。
 *     差別不只是手感：自己點過一次的人記得住路，被載過去的人不會。
 *
 * ZH: 🔴 所以遮罩**不是一整片**，是目標四周的四塊（上右下左）。
 *     一整片的話中間那塊看得到卻點不到 ——
 *     而「看得到、點不到」正是這種引導最常見的壞掉方式。
 *
 * ZH: 兩種狀態，刻意存在不同的地方：
 *       · 「看過了」→ 帳號（`users.ui_dismissed` 的 `tour` key，由 prefs.js 管）
 *       · 「走到第幾步」→ sessionStorage（一次性的進度，不該跟著帳號跨裝置）
 *
 * ZH: 🔴 **開始之前一定要等初次設定結束**（chrome.js 的 `maybeShowOnboarding`，
 *     z-index 1000、會鎖住整頁捲動）。做法見 `waitForOnboarding()`。
 *
 * ZH: ⚠ **不顯示「第幾步／共幾步」**（擁有者裁定 2026-09-23）——
 *     步數會因為有沒有公告、GPU 開不開而變動，寫出來只會讓人覺得
 *     「怎麼跟剛才看到的不一樣」。
 *
 * ZH: ⚠ 沒有「跳過」鈕，但**一定有 ×，Esc 也能關**。理由是逃生：
 *     選擇器失效或座標算錯時，沒有出口等於把人鎖在畫面上。
 *     同理 `stepsFor()` 會先濾掉「目標不存在」的步驟。
 * ========================================================================== */
(function (global) {
    'use strict';

    var SEEN_KEY = 'tour';                    // ZH: ui_dismissed 裡的 key
    var PROGRESS_KEY = 'ai_hud_tour_step';    // ZH: sessionStorage 的進度

    /* ZH: 步驟表。
     *   page   這一步在哪一頁演
     *   target 圈住誰（null = 置中的卡片，不圈任何東西）
     *   click  true = **要使用者自己點那個元素**才前進（那一步不給前進鈕）
     *   gpu    true = GPU 功能暫停時整步略過（那兩頁那時會被擋成空白）
     *
     * ZH: 🔴 **換頁只會發生在 `click: true` 的步驟之後** —— 這是這份表的不變式。
     *     程式自己不跳頁，所以破壞它的症狀是「導覽停在上一頁不動」，
     *     而且不會報錯。`badTransitions()` 把它變成測得到的東西。
     *
     * ZH: ⚠ 文案用 `T('key', '中文')` 的形狀寫，check_i18n 才看得到。
     */
    var STEPS = [
        { id: 'hello', page: 'index.html', target: null,
          t: ['tour_hello_t', '歡迎使用 AI 基地'],
          d: ['tour_hello_d',
              '這裡是銘傳大學圖書館的 AI 平台：可以直接用現成的 AI 工具，也可以自己訓練模型。'
              + '接下來帶你認一遍環境，大約一分鐘。隨時可以按右上角的 × 離開。'] },

        { id: 'news', page: 'index.html', target: '#news',
          t: ['tour_news_t', '公告在最上面'],
          d: ['tour_news_d',
              '維護時間、功能暫停、新功能上線都會公告在這裡，最新的排在最前面。'
              + '哪天某個功能點不下去，先看這一區通常就知道原因。'] },

        { id: 'lines', page: 'index.html', target: '.lines',
          t: ['tour_lines_t', '三條路，由淺入深'],
          d: ['tour_lines_d',
              '1 是直接用別人訓練好的 AI；2 是用我們準備好的範例資料跑一次完整訓練；'
              + '3 是自己寫程式。編號是建議的順序，不是限制 —— 想從哪一條開始都可以。'] },

        { id: 'ai', page: 'index.html', target: '[data-tour="ai"]', click: true,
          t: ['tour_ai_t', '先從第一條開始'],
          d: ['tour_ai_d',
              '這條通往 MYAI：可以聊天、改作文、整理報告，不需要任何程式基礎。'
              + '點一下這張卡片，我們過去看看。'] },

        { id: 'balance', page: 'myai.html', target: '#balance-card',
          t: ['tour_balance_t', '這是你的額度'],
          d: ['tour_balance_d',
              '使用 MYAI 會消耗點數，這個數字就是你現在剩下的額度，每個月會自動補回來。'
              + '用完了不會跟你收錢，只是要等下個月 —— 所以放心用。'] },

        { id: 'home', page: 'myai.html', target: '.topnav a[href="index.html"]', click: true,
          t: ['tour_home_t', '左上角隨時回得去'],
          d: ['tour_home_d',
              '不管走到哪一頁，點頂部列的「首頁」或左上角的站名都會回到首頁。'
              + '點一下「首頁」，我們回去看剩下的部分。'] },

        { id: 'train', page: 'index.html', target: '[data-tour="train"]', gpu: true,
          t: ['tour_train_t', '第二條：跑一次真的訓練'],
          d: ['tour_train_d',
              '不用準備自己的資料，也不用寫程式：選一個現成的範例（例如分辨貓和狗），'
              + '按下去就會排進 GPU 佇列，大約 20 分鐘跑完，過程中看得到進度。'] },

        { id: 'lab', page: 'index.html', target: '[data-tour="lab"]', gpu: true,
          t: ['tour_lab_t', '第三條：自己寫程式'],
          d: ['tour_lab_d',
              '瀏覽器裡就有一套 VS Code，檔案會留在你自己的空間裡。'
              + '寫好的程式可以直接送去 GPU 訓練，不必自己準備環境。'] },

        { id: 'nav', page: 'index.html', target: '.topnav',
          t: ['tour_nav_t', '其他東西都在這排選單'],
          d: ['tour_nav_d',
              '首頁只放三條主線，其餘都收在這裡：看訓練進度、管理資料集、查使用量、'
              + '看別人做過什麼、GPU 現在忙不忙，以及問題回報。點開任一個分類都看得到。'] },

        { id: 'bot', page: 'index.html', target: '#aibot-fab',
          t: ['tour_bot_t', '卡住就問小基'],
          d: ['tour_bot_d',
              '右下角這顆是站內助手，問它「怎麼開始訓練」「額度怎麼算」都可以。'
              + '它讀的是這個平台自己的說明文件，不是網路上的泛泛答案。'] },

        { id: 'done', page: 'index.html', target: null,
          t: ['tour_done_t', '就這些，開始用吧'],
          d: ['tour_done_d',
              '想再看一次這個導覽，右上角帳號選單裡有「再看一次導覽」。'
              + '遇到平台本身的問題，用「問題回報」告訴我們，管理者看得到。'] },
    ];

    // ── 純函式（tests/tour.test.js 測的就是這一段）────────────────────
    //
    // ZH: 🔴 這幾支刻意不碰 DOM、不碰 storage —— 跨頁狀態機是這個功能最容易
    //     錯的地方，而它在瀏覽器裡很難重現（要真的登入、真的換頁）。

    /* ZH: 這次要走哪幾步。兩段：先濾掉不該出現的，再丟掉**到不了**的。
     *
     * ZH: 第一段（濾）：
     *   gpuOn=false → 濾掉 GPU 的步驟
     *   has(sel)    → 「這個選擇器現在找不找得到」，找不到的步驟也濾掉
     *   ⚠ `has` 只對**目前這一頁**的步驟有意義（別頁的元素當然找不到）。
     *
     * ZH: 🔴 第二段（到得了嗎）：導覽自己不換頁，**每一次換頁都靠一個
     *     click 步驟當橋**。第一段可能剛好把那座橋濾掉（例如有人改了
     *     `data-tour` 的值，於是「點我去 MYAI」那一步消失）——
     *     這時對岸那幾步就到不了了。留著的話症狀是
     *     **在首頁演 MYAI 的說明**：不報錯、不卡住，只是講錯地方。
     *     所以橋斷了就把對岸整段丟掉，導覽縮短但每一句話都還對得上畫面。
     *
     * ZH: ⚠ 這也是 `badTransitions()` 為什麼對真實輸入永遠該回空陣列 ——
     *     那支是斷言，這一段是實作。2026-09-23 就是測試先抓到的。
     */
    function stepsFor(opts) {
        var o = opts || {};
        var here = o.here || '';
        var has = o.has || function () { return true; };

        var kept = STEPS.filter(function (s) {
            if (s.gpu && !o.gpuOn) return false;
            if (s.target && s.page === here && !has(s.target)) return false;
            return true;
        });

        var out = [];
        // ZH: 🔴 從**導覽的起點**算可達性，不是從使用者現在這一頁算。
        //     用 `here` 當起點的話，在 MYAI 頁重算時前面那幾個首頁步驟
        //     會被當成「到不了」而砍掉 —— 於是同一份導覽在不同頁長度不同。
        var reachable = STEPS.length ? STEPS[0].page : here;
        kept.forEach(function (s) {
            if (s.page === reachable) { out.push(s); return; }
            // ZH: 不同頁 —— 只有上一個留下來的步驟是 click（那座橋還在）才過得去。
            var prev = out[out.length - 1];
            if (prev && prev.click) { out.push(s); reachable = s.page; }
        });
        return out;
    }

    /* ZH: 🔴 **進度存的是步驟 id，不是「第幾個」。**
     *
     * ZH: 為什麼：`stepsFor` 的結果**長短會變** —— `has` 只檢查目前這一頁的
     *     目標，所以「沒有公告的人」在首頁少一步，換到 MYAI 頁重算時那一步
     *     又回來了。存索引的話，跨頁之後同一個數字指到的是**別的步驟**
     *     （實測會變成在 MYAI 頁重播「點一下這張卡片」）。
     *     id 沒有這個問題。⚠ v4.26 存的是索引，這是那一版的真 bug。
     *
     * ZH: 找不到那個 id 時（例如那一步這一頁剛好被濾掉）：往後找**第一個
     *     排在它之後、而且在這一頁**的步驟。都沒有就回 -1（這一頁不演，
     *     進度留著，他回到對的頁面就接得上）。
     */
    function resumeIndex(steps, savedId, here) {
        if (!savedId) return -1;
        var i, j;
        var masterPos = -1;
        for (i = 0; i < STEPS.length; i++) {
            if (STEPS[i].id === savedId) { masterPos = i; break; }
        }
        if (masterPos < 0) return -1;      // ZH: 不認得的 id（步驟表改過）→ 不要亂接

        // ZH: 🔴 一律找「**這一頁**、而且排在進度之後（含進度本身）」的第一步。
        //
        // ZH: 原本是「先找完全相同的 id，找不到才往後找」。那個寫法在
        //     **進度指到別頁**時會回傳那個別頁的索引，呼叫端接著發現
        //     `page !== here` 就什麼都不演 —— 畫面上是一片空白。
        //     會走到那裡的情境不只一種（使用者自己打網址、上一頁、
        //     或是點到導覽沒預期的連結），而每一種的結果都一樣難解釋。
        //     改成「往後追到這一頁的第一步」= 使用者晃到哪裡，導覽就追到哪裡。
        for (i = 0; i < steps.length; i++) {
            if (steps[i].page !== here) continue;
            var pos = -1;
            for (j = 0; j < STEPS.length; j++) {
                if (STEPS[j].id === steps[i].id) { pos = j; break; }
            }
            if (pos >= masterPos) return i;
        }
        return -1;
    }

    function nextIndex(steps, from) {
        var i = (typeof from === 'number' ? from : -1) + 1;
        return i < steps.length ? i : -1;
    }

    function prevIndex(steps, from) {
        var i = (typeof from === 'number' ? from : 0) - 1;
        return i >= 0 ? i : 0;
    }

    /* ZH: 現在這一頁的檔名。根路徑（`/V1/`）當成 index.html ——
     *     nginx 的 index 指令會給那一頁，而網址上看不出來。
     */
    function pageName(path) {
        var last = String(path || '').split('/').pop();
        return last === '' ? 'index.html' : last;
    }

    /* ZH: 🔴 不變式檢查：**換頁只能發生在 click 步驟之後**。
     *     導覽自己不跳頁（擁有者裁定 v4.27），所以若某一步與下一步不同頁、
     *     而它又不是 click 步驟，導覽就會停在那裡不動 —— 而且不會報錯。
     *     回傳有問題的步驟 id（空陣列＝沒問題）。
     */
    function badTransitions(steps) {
        var bad = [];
        for (var i = 0; i < steps.length - 1; i++) {
            if (steps[i].page !== steps[i + 1].page && !steps[i].click) {
                bad.push(steps[i].id);
            }
        }
        return bad;
    }

    global.Tour = {
        STEPS: STEPS,
        stepsFor: stepsFor,
        nextIndex: nextIndex,
        prevIndex: prevIndex,
        pageName: pageName,
        badTransitions: badTransitions,
        resumeIndex: resumeIndex,
        SEEN_KEY: SEEN_KEY,
        PROGRESS_KEY: PROGRESS_KEY,
    };

    // ZH: 在 node 裡（測試）就到此為止 —— 下面全是 DOM。
    if (typeof document === 'undefined') return;

    // ── 以下是瀏覽器端 ────────────────────────────────────────────────
    var steps = [];
    var cur = -1;
    var box = null;          // 說明卡
    var ring = null;         // 高亮框（只是一圈邊，不負責變暗）
    var panels = [];         // 目標四周的遮罩（上右下左）—— 中間留給使用者點
    var armed = null;        // 這一步掛在目標上的點擊監聽（要記得拆）

    /* ZH: 🔴 **「找得到」不等於「看得見」。**
     *
     * ZH: `document.querySelector()` 對 `display:none` 的元素照樣回傳節點，
     *     所以只判斷 null 的話，這三個目標會在看不見的時候被當成還在：
     *       · `#news` —— 沒有公告時整塊帶著 `hidden` 留在 DOM 裡
     *       · `.topnav` —— 手機版收進 ☰，面板展開前是隱藏的
     *       · `#aibot-fab` —— 小基側欄展開時 FAB 是 `display:none`
     *     症狀不是「略過那一步」，是**把高亮框畫成左上角一個 12×12 的小方塊**
     *     （隱藏元素的 getBoundingClientRect 全是 0），說明卡飄在旁邊。
     *     不報錯、不卡住，看起來就像導覽壞了。2026-09-23 擁有者回報後查到。
     *
     * ZH: 判準用 `getClientRects().length` —— 它同時涵蓋 `display:none`、
     *     祖先被隱藏、以及尺寸為 0 三種情況。`offsetParent` 對 `position:fixed`
     *     會誤判（那正好是頂部列與 FAB 的定位方式）。
     */
    function visible(el) {
        return !!(el && el.getClientRects && el.getClientRects().length);
    }

    function T(key, fallback) {
        try { return (global.T ? global.T(key, fallback) : fallback); }
        catch (e) { return fallback; }
    }

    function esc(v) {
        return String(v == null ? '' : v).replace(/[&<>"']/g, function (c) {
            return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
        });
    }

    // ZH: 存的是**步驟 id**（見 resumeIndex 的說明）。
    function readProgress() {
        try {
            return sessionStorage.getItem(PROGRESS_KEY) || null;
        } catch (e) { return null; }      // ZH: 無痕模式會丟例外
    }

    function writeProgress(id) {
        try {
            if (!id) sessionStorage.removeItem(PROGRESS_KEY);
            else sessionStorage.setItem(PROGRESS_KEY, String(id));
        } catch (e) { /* ZH: 記不住只是換頁後不會續走，不是錯誤 */ }
    }

    // ZH: 小幫手 —— 呼叫端關心的是「現在停在哪一步」，不是索引。
    function saveCurrent(i) {
        writeProgress(i >= 0 && steps[i] ? steps[i].id : null);
    }

    // ── 畫面 ──────────────────────────────────────────────────────────

    function disarm() {
        if (armed) {
            armed.el.removeEventListener('click', armed.fn, true);
            armed = null;
        }
    }

    function teardown() {
        disarm();
        panels.forEach(function (p) { p.remove(); });
        panels = [];
        [ring, box].forEach(function (el) { if (el) el.remove(); });
        ring = box = null;
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
    }

    function ensureChrome() {
        if (box) return;
        // ZH: 四塊遮罩（上右下左）。中間留空 = 目標真的點得到。
        for (var i = 0; i < 4; i++) {
            var p = document.createElement('div');
            p.className = 'tour__panel';
            document.body.appendChild(p);
            panels.push(p);
        }
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

    /* ZH: 把四塊遮罩排成「中間有一個洞」。`r` 為 null 時第一塊蓋滿整頁。 */
    function setPanels(r) {
        var W = global.innerWidth, H = global.innerHeight;
        var boxes = r
            ? [
                { left: 0, top: 0, width: W, height: Math.max(0, r.top) },
                { left: Math.max(0, r.right), top: Math.max(0, r.top),
                  width: Math.max(0, W - r.right), height: Math.max(0, r.height) },
                { left: 0, top: Math.max(0, r.bottom),
                  width: W, height: Math.max(0, H - r.bottom) },
                { left: 0, top: Math.max(0, r.top),
                  width: Math.max(0, r.left), height: Math.max(0, r.height) },
            ]
            : [{ left: 0, top: 0, width: W, height: H },
               { left: 0, top: 0, width: 0, height: 0 },
               { left: 0, top: 0, width: 0, height: 0 },
               { left: 0, top: 0, width: 0, height: 0 }];

        panels.forEach(function (p, i) {
            var b = boxes[i];
            p.style.left = b.left + 'px';
            p.style.top = b.top + 'px';
            p.style.width = b.width + 'px';
            p.style.height = b.height + 'px';
        });
    }

    /* ZH: 把高亮框、四塊遮罩與說明卡放到目標旁邊。
     * ZH: ⚠ `position: fixed` + `getBoundingClientRect()`（視窗座標），
     *     所以捲動與 resize 都要重算。
     */
    function reposition() {
        if (!box) return;
        var s = steps[cur];
        var el = s && s.target ? document.querySelector(s.target) : null;
        // ZH: ⚠ 演到一半才不見的情況（例如他中途把小基側欄打開，FAB 就沒了）：
        //     當成「這一步沒有目標」＝置中顯示說明，不要畫一個 0×0 的框。
        if (!visible(el)) el = null;

        if (!el) {
            ring.hidden = true;
            setPanels(null);
            box.style.left = '50%';
            box.style.top = '50%';
            box.style.transform = 'translate(-50%, -50%)';
            return;
        }

        var r = el.getBoundingClientRect();
        var pad = 6;
        ring.hidden = false;
        ring.style.left = (r.left - pad) + 'px';
        ring.style.top = (r.top - pad) + 'px';
        ring.style.width = (r.width + pad * 2) + 'px';
        ring.style.height = (r.height + pad * 2) + 'px';
        setPanels(r);

        // ZH: 說明卡放目標下面；下面放不下就放上面。
        //     ⚠ 用 `offsetHeight` 量自己 —— 文案長度會變，寫死高度遲早會撞。
        var bh = box.offsetHeight || 180;
        var below = r.bottom + 14;
        var top = (below + bh < global.innerHeight) ? below : Math.max(12, r.top - bh - 14);
        var left = Math.min(Math.max(12, r.left),
                            Math.max(12, global.innerWidth - box.offsetWidth - 12));
        box.style.transform = 'none';
        box.style.left = left + 'px';
        box.style.top = top + 'px';
    }

    /* ZH: 這一步要使用者自己點目標 —— 把監聽掛上去。
     *
     * ZH: 🔴 用 **capture 階段**：目標多半是 `<a>`，冒泡階段可能來不及
     *     （瀏覽器已經開始導覽）。capture 保證我們先寫進度再讓它跳。
     * ZH: ⚠ **絕對不要 preventDefault** —— 整個設計就是「讓他真的點過去」。
     * ZH: ⚠ 換頁之後這一頁的 JS 就沒了，所以進度一定要在這裡寫完。
     */
    function arm(el) {
        disarm();
        var fn = function () {
            var i = nextIndex(steps, cur);
            saveCurrent(i);
            teardown();
            if (i < 0) { finish(true); return; }
            // ZH: 目標若不會換頁（同一頁的東西），就地演下一步。
            //     真的換頁時這段來不及跑完也沒關係 —— 進度已經寫下去了。
            if (steps[i].page === pageName(location.pathname)) {
                cur = i;
                setTimeout(render, 50);
            }
        };
        el.addEventListener('click', fn, true);
        armed = { el: el, fn: fn };
    }

    function render() {
        var s = steps[cur];
        if (!s) { finish(true); return; }

        ensureChrome();
        disarm();

        var el = s.target ? document.querySelector(s.target) : null;
        if (!visible(el)) el = null;      // ZH: 同上 —— 看不見就當成沒有
        var last = cur === steps.length - 1;
        // ZH: 上一步只在**同一頁**才給 —— 導覽自己不換頁，往回也一樣。
        var canBack = cur > 0 && steps[cur - 1].page === s.page;

        box.innerHTML =
            '<button class="tour__x" type="button" id="tour-x" aria-label="'
            + esc(T('tour_close', '關閉導覽')) + '">×</button>'
            + '<h2 class="tour__t" id="tour-t">' + esc(T(s.t[0], s.t[1])) + '</h2>'
            + '<p class="tour__d">' + esc(T(s.d[0], s.d[1])) + '</p>'
            + (last && !hasGpuSteps()
                ? '<p class="tour__note">' + esc(T('tour_gpu_off',
                    '（第二條與第三條目前暫停開放，開放之後再回來看那兩站。）')) + '</p>'
                : '')
            + '<div class="tour__btns">'
            + (canBack ? '<button class="btn btn--ghost" type="button" id="tour-prev">'
                + esc(T('tour_prev', '上一步')) + '</button>' : '')
            + (s.click && el
                // ZH: 🔴 要他自己點的那一步**不給前進鈕** —— 給了就沒有人會去點那張卡，
                //     而「自己點過一次」正是這個導覽想留下的東西。
                ? '<span class="tour__wait">'
                  + esc(T('tour_click_hint', '點一下圈起來的地方就會過去')) + '</span>'
                : '<button class="btn btn--primary" type="button" id="tour-next">'
                  + esc(last ? T('tour_finish', '開始使用') : T('tour_next', '繼續'))
                  + '</button>')
            + '</div>';

        box.querySelector('#tour-x').addEventListener('click', function () { finish(true); });
        var next = box.querySelector('#tour-next');
        if (next) next.addEventListener('click', function () { go(1); });
        var prev = box.querySelector('#tour-prev');
        if (prev) prev.addEventListener('click', function () { go(-1); });

        if (s.click && el) arm(el);

        // ZH: 把目標捲進畫面再定位 —— 目標在畫面外時框會畫在看不見的地方。
        if (el && el.scrollIntoView) {
            try { el.scrollIntoView({ block: 'center', behavior: 'auto' }); } catch (e) { }
        }
        reposition();
        if (next) next.focus();
    }

    function hasGpuSteps() {
        return steps.some(function (s) { return s.gpu; });
    }

    /* ZH: 前進／後退。
     * ZH: 🔴 **這支永遠不換頁**（v4.27）—— 換頁只由使用者點目標觸發（見 arm）。
     *     所以下一步一定與這一步同頁；不同頁的話就是步驟表寫錯了，
     *     `badTransitions()` 會在測試時抓到。
     */
    function go(dir) {
        var i = dir > 0 ? nextIndex(steps, cur) : prevIndex(steps, cur);
        if (i < 0) { finish(true); return; }
        cur = i;
        saveCurrent(cur);
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

    /* ZH: 開始（或續走）。`force` 是「再看一次」用的 —— 忽略「看過了」。
     *
     * ZH: 🔴 **「看過了」只擋「從頭開始」，不擋「續走」。**
     *     這兩件事本來混在一起，造成一個很難自己撞到的 bug：
     *       按「再看一次導覽」（force=true，過得了）→ 點卡片去 MYAI →
     *       新頁面載入後呼叫的是 `start(false)` → 撞上 isDismissed → 直接 return
     *       → **第二頁什麼都不畫**。
     *     也就是「看過一次的人再看一次時，跨頁之後就斷在那裡」。
     *     2026-09-24 擁有者回報「點下去之後轉 MYAI 分頁就沒東西了」查到的。
     *     判準：sessionStorage 裡有進度 = 正在走，那就繼續走完。
     */
    async function start(force) {
        var inProgress = !!readProgress();
        if (!force && !inProgress && global.Prefs && global.Prefs.isDismissed
            && global.Prefs.isDismissed(SEEN_KEY)) return;

        var here = pageName(location.pathname);
        var gpuOn = await gpuEnabled();
        steps = stepsFor({
            here: here,
            gpuOn: gpuOn,
            // ZH: ⚠ 要「看得見」才算有（見 visible 的說明）。
            has: function (sel) { return visible(document.querySelector(sel)); },
        });
        if (!steps.length) return;

        var saved = force ? null : readProgress();
        var at = resumeIndex(steps, saved, here);
        if (at >= 0) {
            cur = at;
        } else if (saved && !force) {
            // ZH: 有進度但這一頁接不上（他自己走去別頁了）——
            //     什麼都不做，進度留著，回到對的頁面就會接上。
            return;
        } else {
            cur = 0;
            saveCurrent(0);
        }

        if (steps[cur].page !== here) {
            // ZH: 走到這裡只剩一種情況：**他按了「再看一次導覽」但人不在首頁**
            //     （那顆鈕在每一頁的帳號選單裡，而導覽從首頁開始）。
            //     不帶他過去的話按下去會完全沒反應 —— 實測踩到過。
            //     ⚠ 這是唯一一次程式主動換頁，而且是他剛剛按下去要求的。
            // ZH: 續走的情況不會落到這裡：resumeIndex 只會回傳**這一頁**的步驟，
            //     接不上就回 -1（上面已經處理）。
            if (force) location.href = steps[cur].page;
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
     *     早跑的後果是「每次登入都又被導覽一次」。
     * ZH: ⚠ 登入頁不載 chrome.js，所以那一頁永遠等不到這個事件 —— 那是對的。
     */
    document.addEventListener('chrome:ready', function (ev) {
        var me = ev && ev.detail ? ev.detail.me : null;
        if (!me) return;               // ZH: 沒登入就不導
        start(false);
    });
}(window));
