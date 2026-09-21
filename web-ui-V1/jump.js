/* ==========================================================================
 * jump.js — 離站前的確認說明（v4.21）
 *
 * ZH: 用在「按下去就會離開這個網站」的動作上：前往 MYAI（廠商的站）、
 *     用學校帳號登入（學校的 IdP）。擁有者需求 2026-09-21。
 *
 * ZH: 為什麼值得擋一下：這兩個動作按下去之後，畫面上出現的是**別人的網站**。
 *     不先講的話有兩種人會卡住 ——
 *       · 以為自己按錯了、跑到別的地方（尤其學校的登入頁長得完全不一樣）
 *       · 到了對方的登入頁才想起「我的帳號密碼是什麼」，得切回來翻
 *     所以這個彈窗的價值**不是警告，是把他待會需要的東西先給他**。
 *
 * ZH: 🔴 打斷要有代價意識 —— 每次都擋會讓最常用的動作多一次點擊。判準：
 *       有東西要給他看（例如還沒改過的初始密碼）→ **一定**顯示，忽略「不再提醒」
 *       只是例行說明                              → 顯示一次，勾了就不再出現
 *     兩種都給「不要再提醒」的話，第一種會被自己關掉，而那正是最需要看到的一次。
 *
 * ZH: ⚠ localStorage 在無痕模式／關掉網站資料時會丟例外，一律用 try 包住。
 *     讀不到就當成「沒看過」—— 多顯示一次彈窗是可以接受的失敗方式。
 *
 * ZH: 版面重用初次設定那一套 `.onb` / `.onb__box`（styles.css），
 *     不另外做一份 —— 兩個對話框長得不一樣只會讓人以為是兩種東西。
 * ========================================================================== */
(function (global) {
    'use strict';

    var LS_PREFIX = 'ai_hud_jump_';

    function t(key, fallback) {
        try {
            return (global.T ? global.T(key, fallback) : fallback);
        } catch (e) {
            return fallback;
        }
    }

    function esc(s) {
        return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
            return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
        });
    }

    function dismissed(key) {
        if (!key) return false;
        try {
            return localStorage.getItem(LS_PREFIX + key) === '1';
        } catch (e) {
            return false;               // ZH: 讀不到就當沒看過（見檔頭）
        }
    }

    function remember(key) {
        if (!key) return;
        try {
            localStorage.setItem(LS_PREFIX + key, '1');
        } catch (e) { /* ZH: 記不起來只是下次會再問一次，不是錯誤 */ }
    }

    /* ZH: 顯示確認彈窗。
     *
     * opts:
     *   title      標題（字串）
     *   lines      說明，一個元素一段（陣列）
     *   kv         要先交給他的資料 [[標籤, 值, 可複製?], …]
     *   goLabel    主要按鈕的字
     *   onGo       按下主要按鈕時做的事
     *   rememberKey 有值才出現「不要再提醒」；勾了之後**下次直接執行 onGo**
     *   force      true = 忽略「不再提醒」一定顯示（有重要資訊時用）
     */
    function confirmJump(opts) {
        var o = opts || {};
        // ZH: 已經說過不用再提醒，而且這次沒有非看不可的東西 → 直接走，不打斷。
        if (!o.force && dismissed(o.rememberKey)) {
            if (o.onGo) o.onGo();
            return;
        }

        var box = document.createElement('div');
        box.className = 'onb';
        box.setAttribute('role', 'dialog');
        box.setAttribute('aria-modal', 'true');

        var kvHtml = (o.kv || []).map(function (row, i) {
            return '<div class="kv"><span class="kv__k">' + esc(row[0]) + '</span>'
                + '<span class="kv__v' + (row[2] ? ' kv__v--pw' : '') + '" id="jump-kv-' + i + '">'
                + esc(row[1]) + '</span>'
                + (row[2]
                    ? '<button class="btn btn--minor kv__act" type="button" data-copy="' + i + '">'
                      + esc(t('jump_copy', '複製')) + '</button>'
                    : '')
                + '</div>';
        }).join('');

        box.innerHTML =
            '<div class="onb__box">'
            + '<h2 class="onb__title">' + esc(o.title || '') + '</h2>'
            + (o.lines || []).map(function (line) {
                return '<p class="onb__sub">' + esc(line) + '</p>';
            }).join('')
            + (kvHtml ? '<div class="onb__review">' + kvHtml + '</div>' : '')
            + (o.rememberKey && !o.force
                ? '<label class="onb__sub" style="display:flex;gap:.5rem;align-items:center">'
                  + '<input type="checkbox" id="jump-skip">'
                  + '<span>' + esc(t('jump_skip', '知道了，下次不用再提醒')) + '</span></label>'
                : '')
            + '<button class="btn btn--primary btn--block" type="button" id="jump-go">'
            + esc(o.goLabel || t('jump_go', '繼續')) + '</button>'
            + '<button class="btn btn--ghost btn--block" type="button" id="jump-cancel">'
            + esc(t('jump_cancel', '先不要')) + '</button>'
            + '<span class="inline-error" id="jump-msg" hidden></span>'
            + '</div>';

        document.body.appendChild(box);

        function close() {
            document.removeEventListener('keydown', onKey);
            box.remove();
        }
        function onKey(ev) {
            // ZH: Esc 等於「先不要」—— 只能用滑鼠關的對話框對鍵盤使用者是陷阱。
            if (ev.key === 'Escape') { ev.preventDefault(); close(); }
        }
        document.addEventListener('keydown', onKey);

        box.querySelector('#jump-cancel').addEventListener('click', close);

        // ZH: 複製鈕 —— 帳號與密碼是他待會要打的東西，讓他用複製的比用抄的可靠。
        Array.prototype.forEach.call(box.querySelectorAll('[data-copy]'), function (btn) {
            btn.addEventListener('click', async function () {
                var el = box.querySelector('#jump-kv-' + btn.dataset.copy);
                var msg = box.querySelector('#jump-msg');
                try {
                    await navigator.clipboard.writeText(el.textContent);
                    msg.textContent = t('jump_copied', '已複製');
                } catch (e) {
                    // ZH: 非 https 或使用者拒絕時 clipboard 會失敗 —— 講出來，
                    //     不要讓他以為複製成功然後貼出空白。
                    msg.textContent = t('jump_copy_fail', '複製被擋，請手動選取。');
                }
                msg.hidden = false;
            });
        });

        box.querySelector('#jump-go').addEventListener('click', function () {
            var skip = box.querySelector('#jump-skip');
            if (skip && skip.checked) remember(o.rememberKey);
            close();
            // ZH: 🔴 先關再跳。順序反過來的話，跳轉被瀏覽器擋下時（新分頁）
            //     遮罩會留在畫面上，看起來像整頁卡住。
            if (o.onGo) o.onGo();
        });

        // ZH: 焦點落在主要按鈕 —— Enter 直接繼續，不必先 Tab 過去。
        //     手機不自動聚焦輸入框那條規則在這裡不適用（這裡沒有輸入框）。
        box.querySelector('#jump-go').focus();
    }

    global.Jump = { confirm: confirmJump, dismissed: dismissed };
}(window));
