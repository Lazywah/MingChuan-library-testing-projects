/* ==========================================================================
 * tz.js — 全站時間一律以「台灣時間」顯示
 *
 * ZH: 這支解決兩個獨立的問題，兩個都不會報錯、都只是把時間顯示錯：
 *
 *   問題 1：**後端送來的時間字串沒有時區標記。**
 *       DB 存的是 UTC（後端 99 處都用 datetime.now(timezone.utc)），
 *       但 SQLite 取回來是 naive datetime，序列化長這樣：
 *           "2026-08-20T01:42:38.152605"      ← 沒有 Z、沒有 +08:00
 *       瀏覽器的 new Date(...) 會把這種字串當成**本地時間**，
 *       於是 +08:00 的使用者看到的時間**早了 8 小時**。
 *       實測抓到過：09:42 送出的回報顯示成 01:42。
 *
 *   問題 2：**即使解析對了，getHours() 等方法給的是「瀏覽器所在時區」。**
 *       擁有者裁定：一律釘死 **Asia/Taipei**，不跟著瀏覽器跑。
 *       理由是人在國外時，管理者與學生要看到同一個鐘，
 *       也才和 GPU 時段（gpu_schedule.py 已用 UTC+8）與圖書館開放時間一致。
 *
 * ⚠ **一個例外，不要套這支：`myai_transactions.occurred_at`。**
 *   那一欄存的是**廠商當地時間**（已經是台灣時間的 naive 值），不是 UTC。
 *   拿這裡的函式去處理它會再推 8 小時 —— 現在的原字串顯示才是對的。
 *   同一張表的 `synced_at` 則是 UTC，要用這支。
 *
 * ⚠ **這個檔在五個 UI 目錄各有一份，內容必須逐位元組相同。**
 *   由 scripts/check_timezone.py 機械檢查（已接進 deploy_check.py）——
 *   「記得同步五份」不是約束，可檢查才是。
 * ========================================================================== */
(function (global) {
    'use strict';

    var TW_TZ = 'Asia/Taipei';

    // ZH: 有沒有時區標記。要看的是**時間部分**之後有沒有 Z / +hh:mm / -hh:mm——
    //     日期裡的 "2026-08-20" 本身就有兩個減號，整串找 '-' 會全部誤判為有時區。
    function hasZone(s) {
        return /(?:Z|[+-]\d{2}:?\d{2})$/.test(s.trim());
    }

    /**
     * ZH: 解析成 Date。沒有時區標記 → 視為 UTC。
     * @returns {Date|null} 解析不出來回 null（呼叫端自己決定顯示什麼，不要猜）
     */
    function parse(v) {
        if (v == null || v === '') return null;
        if (v instanceof Date) return isNaN(v.getTime()) ? null : v;
        if (typeof v === 'number') {
            var dn = new Date(v);
            return isNaN(dn.getTime()) ? null : dn;
        }
        var s = String(v).trim();
        if (!s) return null;
        var d = new Date(hasZone(s) ? s : s + 'Z');
        return isNaN(d.getTime()) ? null : d;
    }

    // ZH: 用 Intl 取「台北時區的年月日時分秒」。
    //     不用 getHours() —— 那是瀏覽器所在時區，正是問題 2。
    //
    // ZH: 第二個參數 tz 是**為了讓「有沒有真的釘死時區」測得到**而開的接縫。
    //     沒有它的話，在一台本來就位於 +08:00 的機器上，「釘死台北」與
    //     「跟著系統跑」會產生完全相同的輸出 —— 測試永遠綠，卻什麼都沒驗到。
    //     （實測過：把 timeZone 選項拿掉，原本那組測試照樣全過。
    //       Windows 的 node 不吃 TZ 環境變數，換時區重跑也驗不到。）
    //     正式程式碼一律不傳第二個參數。
    var _fmts = {};
    function parts(v, tz) {
        var d = parse(v);
        if (!d) return null;
        var zone = tz || TW_TZ;
        if (!_fmts[zone]) {
            _fmts[zone] = new Intl.DateTimeFormat('en-CA', {
                timeZone: zone, hour12: false,
                year: 'numeric', month: '2-digit', day: '2-digit',
                hour: '2-digit', minute: '2-digit', second: '2-digit',
            });
        }
        var o = {};
        _fmts[zone].formatToParts(d).forEach(function (p) { o[p.type] = p.value; });
        // ZH: hour12:false 在部分瀏覽器把午夜給成 "24"，正規化回 "00"。
        if (o.hour === '24') o.hour = '00';
        return o;
    }

    function twDate(v, sep) {                       // 2026-08-20
        var p = parts(v);
        if (!p) return '';
        return [p.year, p.month, p.day].join(sep == null ? '-' : sep);
    }

    function twDateTime(v) {                        // 2026-08-20 09:42
        var p = parts(v);
        return p ? p.year + '-' + p.month + '-' + p.day + ' ' + p.hour + ':' + p.minute : '';
    }

    function twFull(v) {                            // 2026-08-20 09:42:38
        var p = parts(v);
        return p ? twDateTime(v) + ':' + p.second : '';
    }

    function twTime(v) {                            // 09:42
        var p = parts(v);
        return p ? p.hour + ':' + p.minute : '';
    }

    function twMonthDay(v) {                        // 08/20
        var p = parts(v);
        return p ? p.month + '/' + p.day : '';
    }

    // ZH: 「今天」也必須用台北的今天算，否則跨日那幾小時會判錯。
    function twIsToday(v) {
        var a = twDate(v), b = twDate(new Date());
        return !!a && a === b;
    }

    /** ZH: 今天 09:42 / 08/20 09:42 —— GPU 下次開放那類「近期時間」用。 */
    function twWhen(v) {
        var p = parts(v);
        if (!p) return '';
        return (twIsToday(v) ? '今天' : (Number(p.month) + '/' + Number(p.day)))
             + ' ' + p.hour + ':' + p.minute;
    }

    /** ZH: 相對時間。未來時間回 '剛剛'——時鐘些微不同步不該顯示成「-3 分鐘前」。 */
    function twRelative(v) {
        var d = parse(v);
        if (!d) return '';
        var s = (Date.now() - d.getTime()) / 1000;
        if (s < 0) s = 0;
        if (s < 60) return Math.floor(s) + ' 秒前';
        if (s < 3600) return Math.floor(s / 60) + ' 分鐘前';
        if (s < 86400) return Math.floor(s / 3600) + ' 小時前';
        if (s < 2592000) return Math.floor(s / 86400) + ' 天前';
        return twDate(v);
    }

    global.TW = {
        TZ: TW_TZ,
        parse: parse,
        parts: parts,
        date: twDate,
        dateTime: twDateTime,
        full: twFull,
        time: twTime,
        monthDay: twMonthDay,
        isToday: twIsToday,
        when: twWhen,
        relative: twRelative,
    };
})(window);
