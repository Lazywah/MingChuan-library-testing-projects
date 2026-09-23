/* ==========================================================================
 * tests/tour.test.js — 引導導覽的跨頁狀態機（v4.26）
 *
 * ZH: 為什麼是 node 測試而不是靠人工點：跨頁狀態機**在瀏覽器裡很難重現**
 *     （要真的登入、真的換頁、真的等 /auth/me），而它正是這個功能最容易錯
 *     的部分 —— 步驟濾掉幾個、索引就全部位移。
 *
 * ZH: 形狀照 `tests/tz.test.js`：純 node、零相依、手寫斷言。
 *     這個 repo 沒有 JS 測試框架，那一支是既有前例。
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
const NONE = function (sel) { return false; };

console.log('tour.js —— 步驟過濾');

// ── GPU 閘門 ────────────────────────────────────────────────────────
{
    const on = Tour.stepsFor({ here: 'index.html', gpuOn: true, has: ALL });
    const off = Tour.stepsFor({ here: 'index.html', gpuOn: false, has: ALL });
    eq(on.length, 7, 'GPU 開著：七步');
    eq(off.length, 5, 'GPU 暫停：五步');
    eq(off.some((s) => s.id === 'train' || s.id === 'lab'), false,
        'GPU 暫停時訓練與實驗室**不在**步驟裡（那兩頁會被擋成空白）');
    eq(off.map((s) => s.id), ['hello', 'lines', 'myai', 'nav', 'bot'],
        'GPU 暫停時剩下的順序');
}

// ── 目標不存在就略過（逃生設計的一半）──────────────────────────────
{
    // ZH: 🔴 這條守的是「版面改版之後導覽還走得完」。
    //     沒有它的話，某一步圈不到東西就會卡在那裡 ——
    //     而使用者只會以為平台壞了。
    const missing = Tour.stepsFor({ here: 'index.html', gpuOn: true, has: NONE });
    eq(missing.map((s) => s.id), ['hello', 'myai', 'train', 'lab'],
        '首頁上找不到目標的步驟被濾掉，別頁的不受影響');

    // ZH: ⚠ `has` 只能回答「**這一頁**有沒有這個元素」。別頁的元素現在當然
    //     找不到，所以不能拿它去濾別頁的步驟 —— 否則跨頁導覽會只剩第一頁那幾步。
    const onMyai = Tour.stepsFor({ here: 'myai.html', gpuOn: true, has: NONE });
    eq(onMyai.some((s) => s.id === 'lines'), true,
        '在 MYAI 頁時，首頁的步驟不會因為「這裡找不到」而被砍掉');
    eq(onMyai.some((s) => s.id === 'myai'), false,
        '在 MYAI 頁時，這一頁自己找不到的目標才會被砍掉');
}

console.log('tour.js —— 前進與後退');

{
    const steps = Tour.stepsFor({ here: 'index.html', gpuOn: false, has: ALL }); // 5 步
    eq(Tour.nextIndex(steps, -1), 0, '還沒開始 → 第 0 步');
    eq(Tour.nextIndex(steps, 0), 1, '0 → 1');
    eq(Tour.nextIndex(steps, 3), 4, '3 → 4（最後一步）');
    eq(Tour.nextIndex(steps, 4), -1, '最後一步再按下一步 → -1（結束）');
    eq(Tour.prevIndex(steps, 0), 0, '第 0 步按上一步 → 留在 0，不會變成 -1');
    eq(Tour.prevIndex(steps, 2), 1, '2 → 1');
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
    eq(Tour.STEPS.every((s) => /^[a-z_]+$/.test(s.t[0]) && /^[a-z_]+$/.test(s.d[0])), true,
        'i18n key 的形狀（check_i18n 只認得字面值）');
}

console.log(failed ? `\n[FAIL] ${failed} 條沒過` : '\n[OK] 全部通過');
process.exit(failed ? 1 : 0);
