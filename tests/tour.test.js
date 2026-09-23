/* ==========================================================================
 * tests/tour.test.js — 引導導覽的跨頁狀態機（v4.28）
 *
 * ZH: 為什麼是 node 測試而不是靠人工點：跨頁狀態機**在瀏覽器裡很難重現**
 *     （要真的登入、真的換頁、真的等 /auth/me），而它正是這個功能最容易錯
 *     的部分 —— 步驟濾掉幾個、索引就全部位移。
 *
 * ZH: 形狀照 `tests/tz.test.js`：純 node、零相依、手寫斷言。
 *     這個 repo 沒有 JS 測試框架，那一支是既有前例。
 *
 * ZH: 🔴 v4.27 最重要的一條在 `TestPageChangesOnlyAfterAClick`：
 *     導覽**自己不換頁**（擁有者裁定：像遊戲引導，讓使用者自己點）。
 *     所以步驟表若在「不是 click 的那一步」換頁，導覽會**停在上一頁不動**
 *     —— 沒有錯誤訊息、沒有 console 紅字，只是不會前進。
 *     那種壞法在瀏覽器裡要走到那一步才看得到，用測試釘住便宜得多。
 *
 * ZH: ⚠ 只測 tour.js 裡**不碰 DOM** 的那一段（tour.js 在 `document` 不存在時
 *     會提早 return）。畫面的部分由瀏覽器實測負責。
 *
 * 用法：node tests/tour.test.js
 * ========================================================================== */
'use strict';

const path = require('path');

// ZH: tour.js 是 `(function (global) { … }(window))`，所以先造一個 window。
global.window = global;
require(path.join(__dirname, '..', 'web-ui-V1', 'tour.js'));
const Tour = global.Tour;

let failed = 0;
function eq(actual, expected, what) {
    const a = JSON.stringify(actual);
    const e = JSON.stringify(expected);
    if (a === e) { console.log('  ok   ' + what); return; }
    failed++;
    console.log('  FAIL ' + what + '\n       得到 ' + a + '\n       預期 ' + e);
}

const ALL = function (sel) { return true; };
// ZH: v4.28b 起有兩道閘門：GPU 與文件庫。兩個都開＝完整的那一圈。
const BOTH_ON = { gpuOn: true, docsOn: true };
const NONE = function (sel) { return false; };

console.log('tour.js —— 步驟過濾');

// ── GPU 閘門 ────────────────────────────────────────────────────────
{
    const on = Tour.stepsFor({ here: 'index.html', ...BOTH_ON, has: ALL });
    const off = Tour.stepsFor({ here: 'index.html', gpuOn: false, docsOn: true, has: ALL });
    // ZH: ⚠ 不寫死總數 —— 步驟會增減，而「剛好幾步」不是要守的性質。
    //     要守的是**少了哪幾步**，以及少完之後還接得起來。
    eq(off.some((s) => s.id === 'train' || s.id === 'lab'), false,
        'GPU 暫停時訓練與實驗室**不在**步驟裡（那兩頁會被擋成空白）');
    eq(on.length - off.length, on.filter((s) => s.gpu).length,
        '少掉的正好是掛了 gpu 旗標的那些，沒有誤傷別的步驟');

    // ZH: 🔴 v4.28 訓練進度整站也吃 GPU 閘門 —— 理由不是那一頁會空白，
    //     而是 chrome.js 的 applyGpuGate 會**把選單裡那一項的 href 拿掉**，
    //     於是「點我去訓練進度」圈得到卻點不過去。
    //     ⚠ 閘門不擋 admin，所以這個壞法只有學生遇得到（實測踩到過）。
    eq(off.some((s) => s.page === 'jobs.html'), false,
        'GPU 暫停時整個訓練進度那一站都不出現（選單裡那一項會變成點不動）');
    eq(on.some((s) => s.page === 'jobs.html'), true,
        '（對照）GPU 開著時它在');

    // ZH: 🔴 這一條才是那個迴圈的重點：拿掉整段之後**前後還接得起來**。
    //     做法是讓那一段從首頁出發、回到首頁 —— 兩端同頁，中間整段可拆。
    eq(Tour.badTransitions(off), [], '整段拿掉之後沒有走不過去的換頁');
    eq(off.some((s) => s.page === 'usage.html') && off.some((s) => s.page === 'report.html'),
        true, '而且後面兩站還在（沒有被連坐砍掉）');
}

// ── 目標不存在就略過（逃生設計的一半）──────────────────────────────
{
    // ZH: 🔴 這條守的是「版面改版之後導覽還走得完」。
    //     沒有它的話，某一步圈不到東西就會卡在那裡 ——
    //     而使用者只會以為平台壞了。
    const missing = Tour.stepsFor({ here: 'index.html', gpuOn: true, has: NONE });
    eq(missing.every((s) => s.page !== 'index.html' || !s.target), true,
        '首頁上找不到目標的步驟被濾掉（沒有目標的那幾步留著）');

    // ZH: 🔴 v4.27：首頁的目標全不見 = 「點我去 MYAI」那座橋也沒了，
    //     所以對岸（MYAI）那幾步**也要一起砍掉**。留著的話會在首頁
    //     演 MYAI 的說明 —— 不報錯、不卡住，只是講錯地方。
    eq(missing.some((s) => s.page === 'myai.html'), false,
        '橋斷了就把對岸整段砍掉（不會在首頁演別頁的說明）');

    // ZH: ⚠ `has` 只能回答「**這一頁**有沒有這個元素」。別頁的元素現在當然
    //     找不到，所以不能拿它去濾別頁的步驟。
    const onMyai = Tour.stepsFor({ here: 'myai.html', gpuOn: true, has: NONE });
    eq(onMyai.some((s) => s.id === 'lines'), true,
        '在 MYAI 頁時，首頁的步驟不會因為「這裡找不到」而被砍掉');
    eq(onMyai.some((s) => s.id === 'balance'), false,
        '在 MYAI 頁時，這一頁自己找不到的目標才會被砍掉');
}

console.log('tour.js —— 前進與後退');

{
    const steps = Tour.stepsFor({ here: 'index.html', gpuOn: false, has: ALL });
    const last = steps.length - 1;
    eq(Tour.nextIndex(steps, -1), 0, '還沒開始 → 第 0 步');
    eq(Tour.nextIndex(steps, 0), 1, '0 → 1');
    eq(Tour.nextIndex(steps, last - 1), last, '倒數第二 → 最後一步');
    eq(Tour.nextIndex(steps, last), -1, '最後一步再按下一步 → -1（結束）');
    eq(Tour.prevIndex(steps, 0), 0, '第 0 步按上一步 → 留在 0，不會變成 -1');
    eq(Tour.prevIndex(steps, 2), 1, '2 → 1');
}

console.log('tour.js —— 換頁只能由使用者點（v4.27 的不變式）');

// ── TestPageChangesOnlyAfterAClick ──────────────────────────────────
{
    // ZH: 🔴 導覽自己不跳頁。所以每一次「這一步與下一步不同頁」，
    //     前一步都必須是 click:true（由使用者點那個連結過去）。
    //     不然導覽會停在上一頁不動，而且完全不報錯。
    const both = Tour.stepsFor({ here: 'index.html', gpuOn: true, has: ALL });
    const gpuOff = Tour.stepsFor({ here: 'index.html', gpuOn: false, has: ALL });
    eq(Tour.badTransitions(both), [], 'GPU 開著時沒有「走不過去」的換頁');
    eq(Tour.badTransitions(gpuOff), [], 'GPU 暫停時也沒有（少了兩步之後接縫會變）');

    // ZH: ⚠ 連目標都找不到的極端情況（例如首頁大改版）也不能卡住。
    const nothing = Tour.stepsFor({ here: 'index.html', gpuOn: false, has: NONE });
    eq(Tour.badTransitions(nothing), [], '首頁的目標全都找不到時也不會卡住');

    // ZH: **陰性對照** —— 這支要真的抓得到問題，不是永遠回空陣列。
    const broken = [
        { id: 'a', page: 'index.html', click: false },
        { id: 'b', page: 'myai.html' },
    ];
    eq(Tour.badTransitions(broken), ['a'],
        '不是 click 卻要換頁 → 抓得出來（陰性對照）');

    const fixed = [
        { id: 'a', page: 'index.html', click: true },
        { id: 'b', page: 'myai.html' },
    ];
    eq(Tour.badTransitions(fixed), [], '改成 click 之後就通過');
}

// ── 要使用者點的那幾步，目標必須是連結 ───────────────────────────────
{
    // ZH: ⚠ click 步驟的目標若不是 `<a>`（例如圈到一個 div），
    //     使用者點下去不會換頁，導覽卻已經把進度推到下一頁的步驟 ——
    //     結果是「按了沒反應」。選擇器裡看得出來的部分先在這裡守住。
    const clicky = Tour.STEPS.filter((s) => s.click);
    eq(clicky.length > 0, true, '確實有「請你自己點」的步驟');
    eq(clicky.every((s) => !!s.target), true, 'click 步驟一定要有目標');
}

console.log('tour.js —— 進度用 id，不用索引');

// ── TestProgressSurvivesPageChanges ────────────────────────────────
{
    // ZH: 🔴 `stepsFor` 的結果**長短會變**（`has` 只檢查目前這一頁的目標），
    //     所以「第幾個」在跨頁之後會指到別的步驟。
    //     v4.26 存的就是索引 —— 實際的症狀是：沒有公告的人走到 MYAI 頁時，
    //     會看到「點一下這張卡片」重播一次。
    const onIndexNoNews = Tour.stepsFor({
        here: 'index.html', gpuOn: true, has: (sel) => sel !== '#news' });
    const onMyai = Tour.stepsFor({ here: 'myai.html', gpuOn: true, has: ALL });
    eq(onIndexNoNews.length !== onMyai.length, true,
        '前提：同一份導覽在兩頁算出來的長度真的會不一樣');

    // ZH: 使用者在首頁點掉「去 MYAI」那一步之後，存的是 id 'balance'。
    //     到了 MYAI 頁（清單多了 news 那一步）仍然要停在 balance。
    const at = Tour.resumeIndex(onMyai, 'balance', 'myai.html');
    eq(onMyai[at].id, 'balance', '跨頁之後接回**同一個**步驟');

    // ZH: 若換成索引：在首頁那份清單裡 balance 是第幾個？
    let idxInIndexList = onIndexNoNews.findIndex((s) => s.id === 'balance');
    eq(onMyai[idxInIndexList].id !== 'balance', true,
        '（對照）用索引的話會指到別的步驟 —— 這就是 v4.26 的 bug');
}

// ── 進度指到別頁、或指到被濾掉的步驟 ────────────────────────────────
{
    const steps = Tour.stepsFor({ here: 'index.html', gpuOn: true, has: ALL });

    // ZH: 🔴 2026-09-24 擁有者回報「點下去之後轉 MYAI 分頁就沒東西了」。
    //     成因之一：resumeIndex 原本會回傳**別頁**那一步的索引，
    //     呼叫端一看 page 不同就什麼都不演 —— 畫面一片空白。
    //     現在一律往後追到**這一頁**的第一步：他晃到哪，導覽就追到哪。
    const onIndex = Tour.resumeIndex(steps, 'balance', 'index.html');
    eq(steps[onIndex].page, 'index.html', '進度在別頁時 → 追到這一頁的步驟');
    eq(steps[onIndex].id, 'train', '而且是排在進度**之後**的那一步，不是從頭來');

    // ZH: 真的在這一頁時當然就接那一步本身。
    const onMyai = Tour.resumeIndex(steps, 'balance', 'myai.html');
    eq(steps[onMyai].id, 'balance', '進度就在這一頁 → 接回同一步');

    // ZH: 這一步被濾掉時（沒有公告），往後找排在它之後、而且在這一頁的。
    const noNews = Tour.stepsFor({
        here: 'index.html', gpuOn: true, has: (sel) => sel !== '#news' });
    const after = Tour.resumeIndex(noNews, 'news', 'index.html');
    eq(noNews[after].id, 'lines', '被濾掉的步驟 → 接到它後面那一步');

    // ZH: 這一頁完全沒有可接的步驟（例如他自己走去 jobs.html）→ 不要亂演。
    eq(Tour.resumeIndex(steps, 'done', 'jobs.html'), -1,
        '這一頁沒有任何步驟 → -1（什麼都不演，不是亂接一個）');

    eq(Tour.resumeIndex(steps, 'no-such-step', 'index.html'), -1,
        '完全不認得的 id → -1（不要亂接）');
    eq(Tour.resumeIndex(steps, null, 'index.html'), -1, '沒有進度 → -1');

    // ZH: ⚠ 另一個成因是 `start()` 裡的「看過了」把**續走**也擋掉了
    //     （按「再看一次」→ 跨頁 → 第二頁 isDismissed 直接 return）。
    //     那一段要 sessionStorage 與 Prefs，測不到；判準寫在 start() 的註解裡，
    //     驗收靠瀏覽器實測那一條（清單見 docs 的驗收步驟）。
}

console.log('tour.js —— 整圈走得完（v4.28）');

// ══════════════════════════════════════════════════════════════════════
// ZH: 擁有者 2026-09-24：「完全帶一遍訓練進度、使用量、問題回報」。
//     那三頁不是用講的，是真的帶過去 —— 而每一次換頁都要靠使用者點
//     選單裡的連結。這一族守的就是那條鏈子不會斷。
// ══════════════════════════════════════════════════════════════════════

// ZH: 桌面：☰ 是 display:none，導覽列與下拉看得到。
const DESKTOP = (sel) => (/topbar__burger/.test(sel) ? /topnav|navmenu/.test(sel) : true);
// ZH: 手機：反過來 —— 只看得到 ☰，導覽列收在裡面。
const MOBILE = (sel) => (/topbar__burger/.test(sel) ? true : !/topnav|navmenu/.test(sel));

const TOUR_PAGES = ['index.html', 'myai.html', 'jobs.html', 'usage.html',
                    'docs.html', 'report.html'];

{
    const all = Tour.stepsFor({ here: 'index.html', ...BOTH_ON, has: ALL });
    const pages = [...new Set(all.map((s) => s.page))].sort();
    eq(pages, [...TOUR_PAGES].sort(), '兩道閘門都開時，導覽會走過這六頁');
}

// ── TestTheDocsStopIsItsOwnGate ────────────────────────────────────
{
    // ZH: 🔴 「看別人做過什麼」的入口**在有內容之前不出現**
    //     （docs-entry.js，fail closed）。所以那一站要能整段拿掉。
    //     ⚠ 判斷不能用「看得見嗎」—— 它躺在還沒點開的下拉裡，
    //     那個答案永遠是否，於是不管有沒有內容都會被砍。
    const withDocs = Tour.stepsFor({ here: 'index.html', ...BOTH_ON, has: ALL });
    const without = Tour.stepsFor({ here: 'index.html', gpuOn: true, docsOn: false, has: ALL });
    eq(without.some((s) => s.page === 'docs.html'), false,
        '沒有內容時整站不出現（入口那時根本不在導覽列上）');
    eq(withDocs.some((s) => s.page === 'docs.html'), true, '（對照）有內容時它在');
    eq(withDocs.length - without.length, withDocs.filter((s) => s.docs).length,
        '少掉的正好是掛了 docs 旗標的那些');
    eq(Tour.badTransitions(without), [], '整段拿掉之後沒有走不過去的換頁');
    eq(without.some((s) => s.page === 'report.html'), true,
        '而且後面那一站還在（沒有被連坐砍掉）');

    // ZH: 兩道閘門同時關 —— 少掉兩整段，前後還是要接得起來。
    const none = Tour.stepsFor({ here: 'index.html', gpuOn: false, docsOn: false, has: ALL });
    eq(Tour.badTransitions(none), [], '兩道閘門都關著時也接得起來');
    eq(none.some((s) => s.page === 'usage.html') && none.some((s) => s.page === 'report.html'),
        true, '而且沒被擋的那兩站都還在');
}

// ── TestTheChainSurvivesOnBothLayouts ──────────────────────────────
{
    // ZH: 🔴 這一條抓的是一個**只在桌面發生**的壞法。
    //     probe 用的是選擇器清單（「☰ 或 這個分類鈕」），而
    //     `document.querySelector` 回傳**文件順序**的第一個 —— ☰ 排在
    //     導覽列前面。所以若判斷只看第一個，桌面上永遠問到那顆隱藏的 ☰，
    //     整段選單導覽會在開場就被砍掉：導覽只走到一半就自己結束，不報錯。
    [['桌面', DESKTOP], ['手機', MOBILE]].forEach(([what, has]) => {
        TOUR_PAGES.forEach((here) => {
            const steps = Tour.stepsFor({ here: here, ...BOTH_ON, has: has });
            const pages = new Set(steps.map((s) => s.page));
            eq(TOUR_PAGES.every((p) => pages.has(p)), true,
                what + '在 ' + here + ' 重算時，六頁都還在鏈子上');
            eq(Tour.badTransitions(steps), [],
                what + '在 ' + here + ' 重算時沒有走不過去的換頁');
        });
    });
}

// ── TestMenuLinksAreProbedByTheirOpener ────────────────────────────
{
    // ZH: 🔴 下拉裡的連結在開場時是 display:none（選單還沒點開）。
    //     拿它自己去問「現在看得到嗎」，答案永遠是否 —— 所以那種步驟
    //     一定要有 probe（問的是「能點開它的那顆鈕還在嗎」）。
    const inMenu = Tour.STEPS.filter((s) => s.target && /navmenu__menu/.test(s.target));
    eq(inMenu.length > 0, true, '前提：真的有「藏在下拉裡」的目標');
    eq(inMenu.every((s) => !!s.probe), true,
        '下拉裡的目標一定要有 probe（否則開場就被砍，整段跟著消失）');

    // ZH: 陰性對照 —— probe 真的有作用：目標看不見、但 probe 看得見時要留著。
    const hidMenuItems = Tour.stepsFor({
        here: 'index.html', ...BOTH_ON,
        has: (sel) => !/navmenu__menu/.test(sel) });
    eq(hidMenuItems.some((s) => s.id === 'go_jobs'), true,
        '目標藏在還沒點開的選單裡，步驟仍然留著（這就是 probe 的用途）');

    // ZH: 反過來 —— 連 probe 都不見了（有人把整排導覽拆了）就該砍掉，
    //     而且對岸那幾頁要跟著砍（橋斷了）。
    const noNav = Tour.stepsFor({
        here: 'index.html', ...BOTH_ON,
        has: (sel) => !/topnav|navmenu|topbar__burger/.test(sel) });
    eq(noNav.some((s) => s.page === 'jobs.html'), false,
        '連 probe 都找不到時，後面那幾頁整段砍掉（不會在首頁演別頁的說明）');
    eq(Tour.badTransitions(noNav), [], '砍完之後也不會卡住');
}

console.log('tour.js —— 頁面判斷');

{
    eq(Tour.pageName('/V1/index.html'), 'index.html', '一般路徑');
    eq(Tour.pageName('/V1/myai.html'), 'myai.html', '別頁');
    // ZH: 🔴 根路徑要當成首頁 —— nginx 的 index 指令會送出 index.html，
    //     但網址上看不出來。判錯的話，從 `/V1/` 進來的人會被一直導去
    //     `index.html`（同一頁），變成無窮迴圈。
    eq(Tour.pageName('/V1/'), 'index.html', '根路徑 = 首頁');
    eq(Tour.pageName(''), 'index.html', '空字串也當首頁');
}

console.log('tour.js —— 契約');

{
    eq(Tour.SEEN_KEY, 'tour', '「看過了」用的 ui_dismissed key');
    // ZH: ⚠ ui_dismissed 的後端驗證只收 [a-z0-9_,-]（schemas.py 的 _sane_dismissed）。
    //     key 寫成大寫或帶空白的話，PATCH 會回 422 而前端**完全不會察覺**
    //     （prefs.js 的 dismiss 是靜默失敗的）—— 症狀是「每次登入都被導覽一次」。
    eq(/^[a-z0-9_-]+$/.test(Tour.SEEN_KEY), true,
        'key 的格式必須通得過後端驗證（否則靜默失敗，每次登入都會再導一次）');
    eq(Tour.STEPS.every((s) => s.t && s.d && s.page), true,
        '每一步都要有頁面、標題、說明');
    // ZH: 擁有者要求「說明多一點」—— 一句話的步驟就失去意義了。
    eq(Tour.STEPS.every((s) => s.d[1].length >= 30), true,
        '每一步的說明都要夠長（擁有者要求說明寫詳細）');
    eq(Tour.STEPS.every((s) => /^[a-z_]+$/.test(s.t[0]) && /^[a-z_]+$/.test(s.d[0])), true,
        'i18n key 的形狀（check_i18n 只認得字面值）');
}

console.log(failed ? `\n[FAIL] ${failed} 條沒過` : '\n[OK] 全部通過');
process.exit(failed ? 1 : 0);
