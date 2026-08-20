/* ==========================================================================
 * tz.js 的行為測試 —— 純 node，無任何相依套件。
 *
 *     node tests/tz.test.js
 *
 * ZH: 由 scripts/check_timezone.py 帶跑（也可單獨執行）。
 *     web-ui-v2/tz.js 是**正本**，其餘四個 UI 的副本由該腳本比對雜湊。
 *
 * ⚠ ZH: 為什麼有「指定時區」那一組測試 ——
 *     開發機本來就在 +08:00，於是「釘死 Asia/Taipei」與「跟著系統跑」
 *     會產生**完全相同的輸出**。實測過：把 timeZone 選項整個拿掉，
 *     原本那組測試照樣全綠；而 Windows 的 node **不吃 TZ 環境變數**
 *     （Intl.DateTimeFormat().resolvedOptions().timeZone 恆為 Asia/Taipei），
 *     所以「換時區重跑」也驗不到。
 *     解法是讓 parts() 收一個時區參數，直接驗「它有沒有照給的時區算」。
 *     少了那一組，這整支測試對「時區被拿掉」是瞎的。
 * ========================================================================== */
'use strict';

global.window = global;
require('../web-ui-v2/tz.js');   // ZH: web-ui-v2 是正本，其餘四份由 check_timezone.py 比對
const TW = global.TW;

let failed = 0;
function eq(label, got, want) {
    const ok = JSON.stringify(got) === JSON.stringify(want);
    if (!ok) failed++;
    console.log(`${ok ? 'OK  ' : 'FAIL'}  ${label}` +
                (ok ? '' : `\n        got  ${JSON.stringify(got)}\n        want ${JSON.stringify(want)}`));
}

// ── 後端真的會送出的字串形狀 ────────────────────────────────────────────
// naive（絕大多數端點）與帶 +00:00（IssueReportResponse）兩種都要吃。
eq('naive 微秒 → 台北',   TW.full('2026-08-20T01:42:38.152605'),       '2026-08-20 09:42:38');
eq('帶 +00:00 → 台北',    TW.full('2026-08-20T01:42:38.152605+00:00'), '2026-08-20 09:42:38');
eq('帶 Z → 台北',         TW.full('2026-08-20T01:42:38Z'),             '2026-08-20 09:42:38');
eq('已是 +08:00 不再推',   TW.full('2026-08-20T09:42:38+08:00'),        '2026-08-20 09:42:38');

// ── 跨日 ────────────────────────────────────────────────────────────────
eq('UTC 20:00 → 台北隔天', TW.date('2026-08-19T20:00:00'),  '2026-08-20');
eq('UTC 16:00 → 台北午夜', TW.time('2026-08-19T16:00:00'),  '00:00');

// ── 各種輸出格式 ────────────────────────────────────────────────────────
eq('dateTime',  TW.dateTime('2026-08-20T01:42:38.152605'), '2026-08-20 09:42');
eq('monthDay',  TW.monthDay('2026-08-20T01:42:38'),        '08/20');
eq('date 斜線', TW.date('2026-08-20T01:42:38', '/'),       '2026/08/20');

// ── 壞輸入不得亂猜 ──────────────────────────────────────────────────────
eq('null',        TW.date(null),           '');
eq('空字串',       TW.date(''),             '');
eq('亂字串',       TW.date('not-a-date'),   '');
eq('parse 亂字串', TW.parse('not-a-date'),  null);

// ── Date 物件與 epoch ───────────────────────────────────────────────────
eq('Date 物件', TW.full(new Date(Date.UTC(2026, 7, 20, 1, 42, 38))), '2026-08-20 09:42:38');
eq('epoch ms',  TW.full(Date.UTC(2026, 7, 20, 1, 42, 38)),           '2026-08-20 09:42:38');

// ── 相對時間 ────────────────────────────────────────────────────────────
eq('未來時間不得為負', TW.relative(new Date(Date.now() + 60000)), '0 秒前');

// ── ⭐ 這一組才驗得到「時區有沒有被真的套用」（見檔頭）──────────────────
(function zoneIsActuallyApplied() {
    const iso = '2026-08-20T01:42:38Z';   // 同一個瞬間
    const tp = TW.parts(iso);                          // 預設 = Asia/Taipei
    const ny = TW.parts(iso, 'America/New_York');
    const utc = TW.parts(iso, 'UTC');

    eq('預設時區＝台北',   [tp.year, tp.month, tp.day, tp.hour], ['2026', '08', '20', '09']);
    eq('指定 New_York',   [ny.year, ny.month, ny.day, ny.hour], ['2026', '08', '19', '21']);
    eq('指定 UTC',        [utc.year, utc.month, utc.day, utc.hour], ['2026', '08', '20', '01']);

    // ZH: 反向守門 —— 三個時區必須互不相同。若 Intl 忽略了 timeZone 選項，
    //     三者會變成同一個值而上面三支仍可能各自「看起來合理」。
    const key = (p) => p.year + p.month + p.day + p.hour;
    eq('三個時區必須互不相同', new Set([key(tp), key(ny), key(utc)]).size, 3);

    eq('宣告的時區常數', TW.TZ, 'Asia/Taipei');
})();

console.log(failed ? `\n🔴 ${failed} 項失敗` : '\n全部通過');
process.exit(failed ? 1 : 0);
