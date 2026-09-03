/* ==========================================================================
 * people.js — 人（處理某一個人）
 *
 * ZH: 這一頁的使用時機與總覽完全不同：總覽是「每天開機看一眼」，
 *     這裡是「有人來求助才打開」。所以入口是**搜尋**，不是瀏覽 ——
 *     你已經知道要找誰了。
 *
 * ZH: 一個人的所有東西集中在同一個地方：基本資料、額度、實驗室、危險操作。
 *     舊版把這些散在「帳號管理」與「Lab 管理」兩個分頁，
 *     處理一個人要跳來跳去、而且兩邊各自有一份搜尋。
 *
 * 🔴 使用者清單**沒有後端搜尋**（GET /admin/users 只有 skip/limit，上限 500）。
 *    所以搜尋是前端做的，而這帶來一個陷阱：只抓第一頁的話，
 *    **第 501 個人之後搜不到，而且畫面上不會有任何提示** ——
 *    你會得到「查無此人」而不是「我只看了前 500 個」。
 *    這裡改成**逐頁抓完**（抓到不足一頁為止），把那個天花板拿掉。
 *
 * ⚠ 破壞性操作（刪除帳號、凍結儲存）後端要求**再輸入一次管理員密碼**。
 *   那是後端的設計，不是這裡加的；介面照做，不把密碼存在任何地方。
 * ========================================================================== */
(function () {
    'use strict';

    var API = '/api/v1';
    var PAGE = 500;               // ZH: 後端 limit 的上限
    var MAX_PAGES = 40;           // ZH: 20000 人的保險絲；真的到這個量就該做後端搜尋了

    var ALL = [];                 // 全部使用者
    var CURRENT = null;           // 目前選中的人

    function $(id) { return document.getElementById(id); }

    /* ZH: 組織名稱的中英挑選（v3.9，擁有者裁定 2026-08-30）。
     *
     * ZH: 規則：**英文介面且有英文名才用英文，否則一律中文。**
     *     與公告的 pickLang、models 的 name_en 同一條規則。
     * ZH: 🔴 判斷用 truthy 不是 `!= null` —— 空字串也算沒有。
     *     後端已經把空的正規化成 None，但前端不假設後端一定做對：
     *     漏掉的話畫面上會出現**空白的學系欄**，而且不會有錯誤。
     * ZH: ⚠ 行政單位**沒有**英文名可挑（後端刻意不送 unit_en，只有 53/97）——
     *     那一欄一律中文，不是漏做。
     */
    function orgName(zh, en) {
        var isEn = (window.Prefs && window.Prefs.get().ui_lang) === 'en';
        return (isEn && en) || zh || '';
    }

    function token() {
        return sessionStorage.getItem('ai_hud_token') || localStorage.getItem('ai_hud_token');
    }

    // ZH: 大數字要有千分位 —— 12340 與 1234 在沒有分隔時一眼分不出來。
    function num(n) { return Number(n || 0).toLocaleString('en-US'); }

    function esc(s) {
        return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
            return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
        });
    }

    async function api(path, opts) {
        var o = opts || {};
        o.headers = Object.assign({ Authorization: 'Bearer ' + token() }, o.headers || {});
        var r = await fetch(API + path, o);
        if (r.status === 401) { location.replace('login.html'); throw new Error('401'); }
        if (!r.ok) {
            var body = await r.json().catch(function () { return {}; });
            throw new Error(detailText(body) || ('HTTP ' + r.status));
        }
        return r.status === 204 ? null : r.json();
    }

    // ZH: FastAPI 的 422 `detail` 是**陣列**，直接塞進畫面會變成 [object Object]。
    //     （使用者端踩過同一個坑。）
    function detailText(body) {
        var d = body && body.detail;
        if (!d) return '';
        if (typeof d === 'string') return zhOnly(d);
        if (Array.isArray(d)) {
            return d.map(function (x) {
                // ZH: 422 的每一條訊息也要拆中英 —— 只在字串那條路徑拆的話，
                //     欄位驗證的錯誤會把「ZH: … | EN: …」整句噴在畫面上。
                //     pydantic 還會在前面加 "Value error, "，一併去掉。
                return (x.loc ? x.loc[x.loc.length - 1] + '：' : '')
                    + zhOnly(String(x.msg || '').replace(/^Value error,\s*/, ''));
            }).join('；');
        }
        return String(d);
    }

    // ZH: 後端的訊息統一是「ZH: 中文 | EN: english」。畫面上只顯示目前語言那半。
    function zhOnly(text) {
        var parts = String(text).split(' | ');
        var lang = (window.Prefs && Prefs.get().ui_lang) || 'zh';
        var want = parts.filter(function (p) {
            return p.indexOf(lang === 'en' ? 'EN:' : 'ZH:') === 0;
        })[0];
        return (want || parts[0] || '').replace(/^(ZH|EN):\s*/, '');
    }

    // ── 載入全部使用者 ────────────────────────────────────────────────────
    async function loadAll() {
        var out = [], skip = 0, pages = 0;
        while (pages < MAX_PAGES) {
            var batch = await api('/admin/users?skip=' + skip + '&limit=' + PAGE);
            out = out.concat(batch);
            pages += 1;
            if (batch.length < PAGE) break;      // ZH: 不足一頁 = 已經是最後一頁
            skip += PAGE;
        }
        if (pages >= MAX_PAGES) {
            // ZH: 真的撞到保險絲時**要講出來**。默默截斷會讓搜尋結果看起來很正常，
            //     只是少了人 —— 那正是這整段要防的事。
            console.warn('使用者超過 ' + (MAX_PAGES * PAGE) + ' 人，清單已截斷');
        }
        return out;
    }

    // ── 列表 ──────────────────────────────────────────────────────────────
    function matches(u, q) {
        if (!q) return true;
        return [u.username, u.email, u.department, u.id, u.role]
            .some(function (v) { return v && String(v).toLowerCase().indexOf(q) >= 0; });
    }


    // ZH: 臨時帳號沒填 email 時，後端會合成一個 `.invalid` 的位址
    //     （`users.email` 是 NOT NULL + UNIQUE，一定要填點什麼；
    //       `.invalid` 是 RFC 2606 保留、永遠不會存在的網域）。
    //     那是**實作細節，不該給人看** —— 秀出來的話管理者會以為那是對方的信箱，
    //     然後試著寄信過去。
    function shownEmail(u) {
        var e = u.email || '';
        if (!e || /@invalid$/i.test(e)) return T('pp_no_email', '—（無信箱）');
        return e;
    }

    function renderList() {
        var q = $('q').value.trim().toLowerCase();
        var rows = ALL.filter(function (u) { return matches(u, q); });

        $('count').textContent = q
            ? T('pp_count_filtered', '{n} / {t} 人')
                .replace('{n}', rows.length).replace('{t}', ALL.length)
            : T('pp_count', '{n} 人').replace('{n}', ALL.length);

        if (!rows.length) {
            $('list').innerHTML = '<p class="footnote">' + esc(T('pp_none', '找不到符合的人。')) + '</p>';
            return;
        }

        var head = [
            ['pp_c_user', '帳號'], ['', 'Email'], ['pp_c_dept', '學系'],
            ['pp_c_role', '角色'], ['pp_c_state', '狀態'], ['pp_c_source', '來源'],
            ['pp_c_seen', '最後登入'],
        ];

        $('list').innerHTML =
            '<div class="adm-tablewrap"><table class="adm-table"><thead><tr>'
            + head.map(function (h) { return '<th>' + esc(T(h[0], h[1])) + '</th>'; }).join('')
            + '</tr></thead><tbody>'
            + rows.map(function (u) {
                return '<tr class="is-clickable' + (CURRENT && CURRENT.id === u.id ? ' is-picked' : '')
                    + '" data-id="' + esc(u.id) + '" tabindex="0">'
                    + '<td>' + esc(u.username) + '</td>'
                    + '<td>' + esc(shownEmail(u)) + '</td>'
                    + '<td>' + esc(orgName(u.department, u.department_en) || '—') + '</td>'
                    + '<td>' + esc(T('role_' + u.role, u.role)) + '</td>'
                    + '<td>' + stateCell(u) + '</td>'
                    + '<td>' + esc(u.auth_source || '—') + '</td>'
                    + '<td>' + esc(u.last_login_time ? TW.when(u.last_login_time) : '—') + '</td>'
                    + '</tr>';
            }).join('')
            + '</tbody></table></div>';

        $('list').querySelectorAll('tr[data-id]').forEach(function (tr) {
            tr.addEventListener('click', function () { pick(tr.dataset.id); });
            // ZH: 鍵盤也要能選 —— 整列可點卻只有滑鼠能用，等於把鍵盤使用者擋在外面。
            tr.addEventListener('keydown', function (ev) {
                if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); pick(tr.dataset.id); }
            });
        });
    }


    // ── 臨時帳號 ──────────────────────────────────────────────────────────
    // ZH: 給校外人士、長官視察、例外用途。
    //
    // ZH: 🔴 密碼**只會出現這一次** —— 這種帳號通常沒有信箱可寄，
    //     所以畫面必須把「現在就抄走」講得很明白。做不到這件事的話，
    //     管理者會關掉視窗然後回來問「密碼在哪」，而答案是沒有了。
    //
    // ZH: 2026-08-30 從頁內卡片改成 <dialog>（與公告 / 問題回報同一套）。
    //     表單階段 ESC 可關（沒填完就想放棄是正當操作）；
    //     **密碼階段攔掉 ESC**（_tempGuard 接 cancel 事件）——
    //     一次性密碼被手滑 ESC 收走的話，上面那段警告等於白寫。
    var _tempGuard = null;

    function _tempDlg(guardEsc) {
        var dlg = $('temp-dialog');
        if (_tempGuard) { dlg.removeEventListener('cancel', _tempGuard); _tempGuard = null; }
        if (guardEsc) {
            _tempGuard = function (ev) { ev.preventDefault(); };
            dlg.addEventListener('cancel', _tempGuard);
        }
        return dlg;
    }

    function openTempForm() {
        var dlg = _tempDlg(false);
        dlg.innerHTML =
            // ZH: 右上角的關閉。`method="dialog"` 讓它不必接事件就能關（同 reports.js）。
            '<form method="dialog" class="rmod__x">'
            +   '<button class="btn btn--minor" type="submit" aria-label="'
            +   esc(T('pf_close', '關閉')) + '">✕</button></form>'
            + '<h2 class="rmod__title">' + esc(T('tmp_title', '建立臨時帳號')) + '</h2>'
            + '<p class="footnote">' + esc(T('tmp_why',
                '給校外人士、長官視察或其他例外用途。到期會自動停用，帳號與紀錄都留著。')) + '</p>'
            + field('t-user', T('tmp_user', '帳號名稱'), '')
            + field('t-why', T('tmp_purpose', '用途（必填）'), '')
            + '<p class="footnote">' + esc(T('tmp_purpose_hint',
                '例如「教育部訪視 2026-09-03」。半年後看到一個沒有用途的帳號，沒有人敢刪它。')) + '</p>'
            + field('t-expires', T('tmp_expires_on', '到期日'), twDay(1), 'date',
                    ' min="' + twDay(0) + '" max="' + twDay(TEMP_MAX_DAYS) + '"')
            + '<p class="footnote">' + esc(T('tmp_expires_hint',
                '選到哪一天，帳號就用到那天結束（台灣時間）。最多 90 天。')) + '</p>'
            + field('t-email', T('tmp_email', 'Email（可留空，平台不會寄信）'), '', 'email')
            + '<div class="adm-inline rmod__foot">'
            + '<button class="btn btn--primary" type="button" id="t-go">'
            + esc(T('tmp_create', '建立')) + '</button>'
            + '<button class="btn btn--minor" type="button" id="t-cancel">'
            + esc(T('tmp_cancel', '取消')) + '</button>'
            + '</div>'
            + '<div class="inline-error" id="t-msg" hidden></div>';

        dlg.showModal();
        $('t-cancel').addEventListener('click', function () { dlg.close(); });
        $('t-go').addEventListener('click', createTemp);
        $('t-user').focus();
    }

    async function createTemp() {
        var body = {
            username: $('t-user').value.trim(),
            purpose: $('t-why').value.trim(),
            // ZH: 送日期字串本身，**不在前端換算成天數**。
            //     換算會因為時區與一天中的時刻而差一天，而且差了不會報錯。
            expires_on: $('t-expires').value,
        };
        var em = $('t-email').value.trim();
        if (em) body.email = em;

        try {
            var out = await api('/admin/users/temporary', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });
            showPassword(out);
            ALL = await loadAll();          // ZH: 讓新帳號立刻出現在清單裡
            renderList();
        } catch (e) {
            say('t-msg', T('tmp_fail', '建立失敗（{w}）').replace('{w}', e.message));
        }
    }

    function showPassword(out) {
        // ZH: 🔴 密碼階段：攔掉 ESC（見 _tempDlg）。只能按「知道了」或 ✕ 主動關。
        var dlg = _tempDlg(true);
        dlg.innerHTML =
            '<form method="dialog" class="rmod__x">'
            +   '<button class="btn btn--minor" type="submit" aria-label="'
            +   esc(T('pf_close', '關閉')) + '">✕</button></form>'
            + '<h2 class="rmod__title">' + esc(T('tmp_done', '帳號建好了')) + '</h2>'
            // ZH: 警告放在密碼**上面** —— 放下面的話，人已經在複製了才讀到。
            + '<div class="adm-alert adm-alert--error"><span>'
            + esc(T('tmp_pw_once',
                '🔴 這組密碼只會顯示這一次。現在就抄下來交給對方 —— 關掉之後就看不到了。'))
            + '</span></div>'
            + '<div class="kv"><span class="kv__k">' + esc(T('pp_c_user', '帳號')) + '</span>'
            + '<span class="kv__v mono">' + esc(out.username) + '</span></div>'
            + '<div class="kv"><span class="kv__k">' + esc(T('tmp_pw', '密碼')) + '</span>'
            + '<span class="kv__v mono" id="t-pw">' + esc(out.password) + '</span></div>'
            + '<div class="kv"><span class="kv__k">' + esc(T('tmp_expires', '到期')) + '</span>'
            + '<span class="kv__v">' + esc(TW.dateTime(out.expires_at)) + '</span></div>'
            + '<div class="adm-inline rmod__foot">'
            + '<button class="btn btn--primary" type="button" id="t-copy">'
            + esc(T('tmp_copy', '複製帳號與密碼')) + '</button>'
            + '<button class="btn btn--minor" type="button" id="t-close">'
            + esc(T('tmp_close', '知道了')) + '</button>'
            + '</div>'
            + '<div class="inline-error" id="t-msg" hidden></div>';

        $('t-copy').addEventListener('click', async function () {
            var text = out.username + ' / ' + out.password;
            try {
                await navigator.clipboard.writeText(text);
                flash('t-msg', T('tmp_copied', '已複製'));
            } catch (e) {
                // ZH: 剪貼簿被擋時**不要只說失敗** —— 幫他選起來，他自己按 Ctrl+C。
                //     （使用者端也是這樣處理的。）
                var r = document.createRange();
                r.selectNodeContents($('t-pw'));
                window.getSelection().removeAllRanges();
                window.getSelection().addRange(r);
                say('t-msg', T('copy_manual',
                    '這個瀏覽器不允許自動複製。已經幫你選起來了，按 Ctrl+C 複製。'));
            }
        });
        $('t-close').addEventListener('click', function () { dlg.close(); });
        // ZH: 正常路徑 dialog 已開（從表單階段換內容過來）；
        //     對開著的 dialog 再 showModal() 會丟 InvalidStateError，所以要判。
        if (!dlg.open) dlg.showModal();
    }


    // ZH: 臨時帳號在清單裡要**一眼看得出來**，而且看得到什麼時候失效。
    //     沒有這個標示的話，它與一般帳號長得一模一樣，
    //     於是就會被當成一般帳號留下來 —— 那是臨時帳號變成永久帳號的標準路徑。
    function stateCell(u) {
        var gone = u.expires_at && Date.parse(u.expires_at) <= Date.now();

        // ZH: 🔴 到期**蓋過**啟用，不要兩個一起顯示。
        //     每日掃描是凌晨 03:00 才把 is_active 設成 0，所以中間有一段時間
        //     資料上它還是「啟用」而人其實已經登不進來（登入路徑即時擋）。
        //     那段時間同時秀「啟用 · 已到期」是自相矛盾的；
        //     這一格要回答的是「他現在能不能用」，答案是不能。
        if (gone) {
            return '<span class="adm-pill adm-pill--expired" title="'
                + esc(u.temp_purpose || '') + '">'
                + esc(T('tmp_expired', '已到期')) + '</span>';
        }

        var out = '<span class="adm-pill adm-pill--' + (u.is_active ? 'ok' : 'disabled') + '">'
            + esc(u.is_active ? T('pp_active', '啟用') : T('pp_inactive', '已停用')) + '</span>';
        if (!u.expires_at) return out;

        // ZH: 還沒到期的臨時帳號 —— 標出**哪一天**失效，不是只標「臨時」。
        //     只寫「臨時」的話你還是得點進去才知道剩幾天。
        out += ' <span class="adm-pill adm-pill--temp" title="' + esc(u.temp_purpose || '') + '">'
            + esc(T('tmp_until', '到期 {d}').replace('{d}', TW.date(u.expires_at)))
            + '</span>';
        return out;
    }

    // ── 一個人的全部 ──────────────────────────────────────────────────────
    function pick(id) {
        // ZH: 換人時把外部 AI 卡的編輯狀態收掉 —— 不收的話，
        //     點下一個人會直接看到編輯中的表單，而且填的是別人的值。
        EXT_EDIT = false;
        // ZH: 換一個人就回到唯讀 —— 不然在 A 身上解鎖之後點到 B，
        //     B 的欄位是直接可以改的，而你並沒有為 B 確認過。
        EDIT_BASIC = false;
        CURRENT = ALL.filter(function (u) { return u.id === id; })[0] || null;
        renderList();
        renderDetail();
    }

    function field(id, label, value, type, attrs) {
        return '<label class="field">'
            + '<span class="field__label" for="' + id + '">' + esc(label) + '</span>'
            + '<input class="field__input" id="' + id + '" type="' + (type || 'text') + '"'
            + ' value="' + esc(value == null ? '' : value) + '"'
            + (attrs || '')
            + '>'
            + '</label>';
    }

    // ==================================================================
    // ZH: 台灣時間的日曆日（YYYY-MM-DD），給 <input type="date"> 用。
    //
    // ZH: 🔴 **不能用瀏覽器本地的今天**。這個平台的顯示時間釘死
    //     Asia/Taipei（tz.js），而到期判定也是台灣時間。管理者人在
    //     別的時區時，兩者會差一天 —— 而差一天的到期日沒有人看得出來。
    //
    // ZH: 台灣沒有夏令時間，所以「加 86400000 毫秒」在這裡精確等於加一天。
    // ==================================================================
    function twDay(offsetDays) {
        return TW.date(new Date(Date.now() + (offsetDays || 0) * 86400000));
    }

    var TEMP_MAX_DAYS = 90;   // ZH: 與後端 schemas.TEMP_ACCOUNT_MAX_DAYS 一致


    // ZH: 臨時帳號的延期。放在詳細面板裡而不是清單上 ——
    //     延期是「決定一件事」不是「掃一眼」，需要先看到用途與現在的到期日。
    //
    // ZH: 🔴 這個功能存在的理由很具體：使用者送了訓練、帳號在跑完之前到期。
    //     （任務本身照樣跑完 —— 派工不檢查帳號狀態 —— 但他登不進來拿結果。）
    function tempCard(u) {
        var gone = Date.parse(u.expires_at) <= Date.now();
        return '<section class="adm-card adm-card--temp">'
            + '<div class="adm-card__title">' + esc(T('tmp_ext_title', '臨時帳號')) + '</div>'
            + '<div class="kv"><span class="kv__k">' + esc(T('tmp_ext_purpose', '用途')) + '</span>'
            + '<span class="kv__v">' + esc(u.temp_purpose || '—') + '</span></div>'
            + '<div class="kv"><span class="kv__k">' + esc(T('tmp_ext_until', '到期')) + '</span>'
            + '<span class="kv__v">' + esc(TW.dateTime(u.expires_at))
            + (gone ? '　<span class="adm-pill adm-pill--expired">'
                + esc(T('tmp_expired', '已到期')) + '</span>' : '')
            + '</span></div>'
            + '<div class="adm-inline">'
            + '<input class="field__input" id="x-expires" type="date"'
            + ' min="' + twDay(0) + '" max="' + twDay(TEMP_MAX_DAYS) + '"'
            // ZH: 預填現在的到期日（已過期就拉到今天）——
            //     管理者看到的是「現在到哪天」，然後把它往後拉。
            + ' value="' + esc(extendDefault(u)) + '"'
            + ' aria-label="' + esc(T('tmp_ext_until_new', '新的到期日')) + '">'
            + '<button class="btn btn--minor" type="button" id="x-go">'
            + esc(T('tmp_ext_go', '延期')) + '</button>'
            + '</div>'
            + '<div class="inline-error" id="x-msg" hidden></div>'
            + '</section>';
    }


    // ZH: 延期欄位的預設值。字串比大小對 ISO 日期是正確的（等寬、大小端序）。
    function extendDefault(u) {
        var today = twDay(0);
        var cur = u.expires_at ? TW.date(u.expires_at) : '';
        return (!cur || cur < today) ? today : cur;
    }


    function wireExtend(u) {
        $('x-go').addEventListener('click', async function () {
            var expiresOn = $('x-expires').value;
            try {
                var out = await api('/admin/users/' + encodeURIComponent(u.id) + '/extend', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ expires_on: expiresOn }),
                });
                // ZH: 後端會順手把 is_active 設回 1（排程可能已經停用它），
                //     所以本地的兩個欄位都要跟著更新，否則清單還顯示舊狀態。
                u.expires_at = out.expires_at;
                u.is_active = 1;
                renderList();
                renderDetail();
                flash('x-msg', T('tmp_ext_done', '已延到 {d}')
                    .replace('{d}', TW.dateTime(out.expires_at)));
            } catch (e) {
                say('x-msg', T('tmp_ext_fail', '延期失敗（{w}）').replace('{w}', e.message));
            }
        });
    }


    // ── 基本資料：唯讀 → 編輯 → 儲存前確認密碼 ─────────────────────────────
    //
    // ZH: 預設唯讀。按「編輯」直接進編輯；**只在儲存前**確認一次密碼
    //     （v4.3b 擁有者裁定 2026-09-03：原本進編輯還要先驗一次，兩道太煩——
    //     真正要擋的是「誤存」，看與改欄位本身不需要門）。
    //
    // ZH: 🔴 **這道確認擋的是誤觸與離開座位時被人動到，不是安全機制。**
    //     後端的 `PUT /admin/users/{id}` 本身不要求密碼（改它會弄壞舊版管理介面），
    //     所以拿到 token 的人仍然可以直接打 API。
    //     但密碼是真的向後端驗的（`POST /admin/verify`，它不發 token、
    //     也不會污染登入紀錄），不是畫面上比對一下而已。
    var EDIT_BASIC = false;

    // ZH: v4.4 名片頭（擁有者裁定 2026-09-03）：身分資訊集中在彈窗最上面，
    //     長得像一張名片 —— 頭像圈＋名字＋標籤＋兩行信箱＋一行出處。
    //     基本資料卡因此**不再重複列身分**（原 roText 已併入這裡並刪除）。
    function pcardHtml(u) {
        var pills = '<span class="adm-pill">' + esc(T('role_' + u.role, u.role)) + '</span>'
            + (u.is_admin ? '<span class="adm-pill">'
                + esc(T('pp_c_is_admin', '管理權限')) + '</span>' : '')
            + (u.expires_at ? '<span class="adm-pill adm-pill--temp">'
                + esc(T('pp_pill_temp', '臨時帳號')) + '</span>' : '')
            + (!u.is_active ? '<span class="adm-pill adm-pill--temp">'
                + esc(T('pf_org_off', '停用')) + '</span>' : '');
        var org = orgName(u.department, u.department_en);
        var meta = [];
        if (org) meta.push(org);
        meta.push(u.auth_source || 'local');
        if (u.last_login_time) {
            meta.push(T('pp_c_seen', '最後登入') + ' ' + TW.when(u.last_login_time));
        }
        return '<div class="pcard">'
            + '<span class="pcard__avatar" aria-hidden="true">'
            + esc((u.username || '?').charAt(0).toUpperCase()) + '</span>'
            + '<div class="pcard__main">'
            + '<div class="pcard__name">' + esc(u.username) + pills + '</div>'
            + '<div class="pcard__line">' + esc(shownEmail(u)) + '</div>'
            + '<div class="pcard__line">' + esc(T('pp_contact', '常用信箱')) + '：'
            + esc(u.contact_email || T('pp_contact_none', '—（用學號信箱）')) + '</div>'
            + '<div class="pcard__line">' + esc(meta.join(' · ')) + '</div>'
            + '<div class="pcard__id mono">' + esc(u.id) + '</div>'
            + '</div>'
            // ZH: v4.4b 停用/刪除搬到名片右側（擁有者裁定 2026-09-03）——
            //     密碼確認在按下去之後用小彈窗問（pwConfirm），
            //     所以這裡只是兩顆入口鈕，不再擺密碼欄。
            + '<div class="pcard__acts">'
            + '<button class="btn btn--minor" type="button" id="toggle-active">'
            + esc(u.is_active ? T('pp_disable', '停用帳號') : T('pp_enable', '啟用帳號')) + '</button>'
            + '<button class="btn btn--minor pcard__del" type="button" id="del">'
            + esc(T('pp_delete', '刪除帳號')) + '</button>'
            + '</div></div>';
    }

    function basicCard(u) {
        var head = '<section class="adm-card">'
            + '<div class="adm-card__title">' + esc(T('pp_basic', '基本資料')) + '</div>';

        if (!EDIT_BASIC) {
            // ZH: v4.4 身分資訊都在上面的名片頭 —— 這張卡只剩「編輯」入口，
            //     重複列一次只會讓彈窗更長。
            return head
                + '<p class="footnote">' + esc(T('pp_ro_hint2',
                    'Email、角色、學系、密碼與管理權限都在這裡改。')) + '</p>'
                + '<div class="ds__actions">'
                + '<button class="btn btn--minor" type="button" id="b-edit">'
                + esc(T('pp_edit', '編輯')) + '</button>'
                + '</div>'
                + '<div class="inline-error" id="save-msg" hidden></div>'
                + '</section>';
        }

        return head
            + field('f-email', 'Email', u.email, 'email')
            + field('f-dept', T('pp_c_dept', '學系'), u.department)
            + '<label class="field"><span class="field__label" for="f-role">'
            + esc(T('pp_c_role', '角色')) + '</span>'
            + '<select class="field__input" id="f-role">'
            // ZH: 順序照實際人數：學生 > 教師 > 職員 > 管理員。
            //     職員是 v3.8 新增（擁有者裁定）—— 數據頁的「依身分」圓餅圖
            //     是直接照 users.role 聚合的，所以這裡加了它就會自己出現。
            + ['student', 'teacher', 'staff', 'guest', 'admin'].map(function (r) {
                return '<option value="' + r + '"' + (u.role === r ? ' selected' : '') + '>'
                    + esc(T('role_' + r, r)) + '</option>';
            }).join('')
            + '</select></label>'
            // ZH: v3.8 **管理權限與身分分開**。同一個人可以是「學生 + 管理權限」——
            //     合成一個欄位時他只能二選一,而選了管理員之後,
            //     數據頁的「依身分」就會把這個學生算成管理員。
            // ZH: `admin` 這個角色留在上面的下拉裡是為了既有資料（v3.8 之前建的）,
            //     新的設定請用身分 + 這個勾選框。
            + '<label class="field field--check">'
            + '<input type="checkbox" id="f-is-admin"' + (u.is_admin ? ' checked' : '') + '>'
            + '<span class="field--check__text">'
            + '<span class="field--check__title">'
            + esc(T('pp_c_is_admin', '管理權限')) + '</span>'
            + '<span class="field--check__hint">'
            + esc(T('pp_c_is_admin_hint', '可以進管理端。與角色無關 —— 學生也可以有。'))
            + '</span></span></label>'
            // ZH: v4.3b 「留空就不改密碼」改放 placeholder（擁有者裁定 2026-09-03）——
            //     提示跟欄位長在一起，開始打字就讓位，不佔一行。
            + field('f-pw', T('pp_new_pw', '新密碼'), '', 'password',
                    ' placeholder="' + esc(T('pp_pw_hint', '留空就不改密碼')) + '"')
            // ZH: v4.4b 密碼確認改在按「儲存」後用小彈窗問（pwConfirm），
            //     表單裡不再擺確認欄。
            + '<div class="ds__actions">'
            + '<button class="btn btn--primary" type="button" id="save">'
            + esc(T('pp_save', '儲存')) + '</button>'
            + '<button class="btn btn--minor" type="button" id="b-cancel">'
            + esc(T('pp_cancel', '取消變更')) + '</button>'
            + '</div>'
            + '<div class="inline-error" id="save-msg" hidden></div>'
            + '</section>';
    }

    // ══════════════════════════════════════════════════════════════════
    // ZH: v4.4b 管理員密碼確認彈窗（擁有者裁定 2026-09-03）：
    //     停用/刪除/儲存前確認共用。`run(pw)` 負責驗證與動作，
    //     丟錯就顯示在彈窗裡、彈窗不關；成功才關。
    //     密碼欄位活在這個彈窗裡，關掉就消失 —— 不殘留在詳情的 DOM。
    // ══════════════════════════════════════════════════════════════════
    function pwConfirm(title, hint, run) {
        var dlg = $('pw-dialog');
        dlg.innerHTML =
            '<h2 class="rmod__title">' + esc(title) + '</h2>'
            + (hint ? '<p class="footnote">' + esc(hint) + '</p>' : '')
            + field('pwc-in', T('pp_admin_pw', '你的管理員密碼'), '', 'password')
            + '<div class="adm-inline rmod__foot">'
            + '<button class="btn btn--primary" type="button" id="pwc-go">'
            + esc(T('pp_pwc_go', '確認')) + '</button>'
            + '<button class="btn btn--minor" type="button" id="pwc-cancel">'
            + esc(T('tmp_cancel', '取消')) + '</button>'
            + '</div>'
            + '<div class="inline-error" id="pwc-msg" hidden></div>';
        dlg.showModal();
        $('pwc-in').focus();
        $('pwc-cancel').addEventListener('click', function () { dlg.close(); });
        async function go() {
            var pw = $('pwc-in').value;
            if (!pw) { say('pwc-msg', T('pp_need_pw', '請先輸入你的管理員密碼。')); return; }
            $('pwc-go').disabled = true;
            try {
                await run(pw);
                dlg.close();
            } catch (e) {
                say('pwc-msg', e.message || String(e));
                $('pwc-go').disabled = false;
            }
        }
        $('pwc-go').addEventListener('click', go);
        // ZH: 密碼欄按 Enter = 確認 —— 打完還要移滑鼠去按鈕很煩。
        $('pwc-in').addEventListener('keydown', function (ev) {
            if (ev.key === 'Enter') { ev.preventDefault(); go(); }
        });
    }

    // ZH: 向後端驗證管理員密碼。用 /admin/verify —— 它專為此而存在，
    //     而且**不發 token、不更新 last_login**（用 /auth/login 驗的話，
    //     每次按編輯都會在稽核裡留下一次「登入」）。
    async function verifyPassword(pw) {
        try {
            await api('/admin/verify', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ admin_password: pw }),
            });
            return true;
        } catch (e) {
            return false;
        }
    }

    // ==================================================================
    // ZH: 檢視切換（平台 / MYAI）—— 與「平台設定」「數據」同一個元件。
    //
    // ZH: 它是**篩選**不是分頁：兩邊講的都是同一批帳號,
    //     只是「平台這邊的資料」與「廠商那邊的對應」。
    // ==================================================================
    var VIEWS = ['platform', 'myai'];

    function viewFromHash() {
        var h = (location.hash || '').replace('#', '');
        return VIEWS.indexOf(h) >= 0 ? h : 'platform';
    }

    var VIEW = viewFromHash();

    function applyView(next) {
        if (next) VIEW = next;
        // ZH: 🔴 **不要動 `hidden` 屬性。** 這一頁有元素自己在管 hidden
        //     （例如 #t-msg 這類訊息列）—— 檢視篩選去寫同一個屬性的話,
        //     會把別人的顯示狀態**強制蓋掉**（當年 #temp-box 還是頁內卡片時
        //     實測踩到過：切檢視把收著的空盒子強制打開）。
        //     用獨立的屬性,兩套顯示邏輯就不會互相覆蓋。
        //     （臨時帳號 2026-08-30 已改成 <dialog>,不在這條流程裡,但原則不變。）
        document.querySelectorAll('[data-view]').forEach(function (el) {
            var on = el.dataset.view === 'both' || el.dataset.view === VIEW;
            el.toggleAttribute('data-view-off', !on);
        });
        // ZH: 🔴 只在 hash 是空的或是我們自己的檢視名時才動它。
        //     無條件 replaceState 會洗掉別人放的 hash（平台設定那邊就踩過:
        //     `#node-<id>` 的深層連結被洗掉,從別處連過來就不會捲到那個節點）。
        var cur = (location.hash || '').replace('#', '');
        if (cur === '' || VIEWS.indexOf(cur) >= 0) {
            try {
                history.replaceState(null, '',
                    location.pathname + (VIEW === 'platform' ? '' : '#' + VIEW));
            } catch (e) { /* 某些情境不給改網址，不影響功能 */ }
        }
    }

    function wireViewSeg() {
        var seg = $('view-seg');
        if (!seg) return;
        var thumb = seg.querySelector('.adm-seg__thumb');
        var opts = [].slice.call(seg.querySelectorAll('[data-view-opt]'));

        function pick(i, focus) {
            if (i < 0 || i >= opts.length) return;
            thumb.style.transform = 'translateX(' + (i * 100) + '%)';
            opts.forEach(function (o, k) {
                var on = k === i;
                o.classList.toggle('is-current', on);
                o.setAttribute('aria-checked', on ? 'true' : 'false');
                o.setAttribute('tabindex', on ? '0' : '-1');
            });
            if (focus) opts[i].focus();
            applyView(opts[i].dataset.viewOpt);
        }

        opts.forEach(function (o, i) {
            o.addEventListener('click', function () { pick(i, false); });
        });
        // ZH: radiogroup 的慣例是左右鍵換選項（群組本身只佔一個 Tab 位）。
        seg.addEventListener('keydown', function (e) {
            var d = e.key === 'ArrowRight' ? 1 : e.key === 'ArrowLeft' ? -1 : 0;
            if (!d) return;
            e.preventDefault();
            pick((VIEWS.indexOf(VIEW) + d + opts.length) % opts.length, true);
        });

        // ZH: 網址帶 #myai 進來時,滑塊與選取狀態要跟著對 ——
        //     只設 VIEW 而不動 DOM 的話,內容是 MYAI 但滑塊停在「平台」。
        pick(VIEWS.indexOf(VIEW), false);

        // ZH: 🔴 **只改 hash 不會重新載入頁面**,模組頂層那行 `var VIEW = ...`
        //     只跑一次。沒有這個監聽,從別處連進來的 hash 變化不會反映在畫面上。
        window.addEventListener('hashchange', function () {
            var want = viewFromHash();
            if (want !== VIEW) pick(VIEWS.indexOf(want), false);
        });
    }

    function renderDetail() {
        var dlg = $('user-dialog');
        var box = $('detail');
        if (!CURRENT) {
            box.innerHTML = '';
            if (dlg.open) dlg.close();
            return;
        }
        var u = CURRENT;
        box.innerHTML =
            // ZH: v4.4 彈窗右上角 ✕。走**明確的 click 清理**而不是 method="dialog"——
            //     清 CURRENT/收反白不能押在 <dialog> 的 close 事件上
            //     （實測瀏覽器面板環境不發 close 事件；正式瀏覽器會發，
            //     但清理邏輯要在兩種環境都成立）。
            '<span class="rmod__x">'
            + '<button class="btn btn--minor" type="button" id="user-close" aria-label="'
            + esc(T('pp_close', '關閉')) + '">✕</button></span>'
            + pcardHtml(u)

            + '<div class="adm-cols">'
            + basicCard(u)

            // ZH: v4.4c 一次性解鎖移到第二順位（擁有者裁定 2026-09-03）——
            //     它跟「編輯基本資料」是同一類事（改這個人的資料），排在一起。
            + '<section class="adm-card" id="unlock-box">'
            + '<div class="adm-card__title">' + esc(T('pp_unlock', '修改個人資料的授權')) + '</div>'
            + '<span class="skeleton skeleton--line"></span></section>'

            // 額度 / 實驗室（非同步填）
            + '<section class="adm-card" id="quota-box">'
            + '<div class="adm-card__title">' + esc(T('pp_quota', '磁碟配額')) + '</div>'
            + '<span class="skeleton skeleton--line"></span></section>'

            + '<section class="adm-card" id="lab-box">'
            + '<div class="adm-card__title">' + esc(T('pp_lab', '程式實驗室')) + '</div>'
            + '<span class="skeleton skeleton--line"></span></section>'

            // ZH: 外部 AI 的綁定與消耗。放在這裡而不是「數據」那一頁 ——
            //     那一頁是看趨勢的，要查某一個人就該在人這一頁查完。
            + '<section class="adm-card" id="ext-box">'
            + '<div class="adm-card__title">' + esc(T('pp_ext', '外部 AI（MYAI）')) + '</div>'
            + '<span class="skeleton skeleton--line"></span></section>'
            // ZH: 只有臨時帳號才出現這張卡。一般帳號看到一個「延期」欄位
            //     只會困惑（他沒有到期日可以延）。
            + (u.expires_at ? tempCard(u) : '')
            + '</div>';

        $('user-close').addEventListener('click', closeUserDialog);
        wireDetail(u);
        if (u.expires_at) wireExtend(u);
        loadQuota(u);
        loadLab(u);
        loadUnlock(u);
        loadExtAi(u);
        if (!dlg.open) dlg.showModal();
    }

    // ZH: v4.4 關閉的唯一實作：✕、ESC（cancel）、close 事件三條路都走這裡。
    function closeUserDialog() {
        var dlg = $('user-dialog');
        CURRENT = null;
        $('detail').innerHTML = '';
        renderList();      // ZH: 清單的反白也要收掉,不然還亮著一列但人已經關掉了
        if (dlg.open) dlg.close();
    }

    function say(id, text) {
        var el = $(id);
        el.textContent = text;
        // ZH: 這個容器兩用 —— 預設回到錯誤樣式，成功訊息由 flash() 換過去。
        //     每次都重設，否則上一則成功訊息的中性底會留給下一則錯誤訊息。
        el.classList.remove('inline-note');
        el.classList.add('inline-error');
        el.hidden = !text;
    }

    // ZH: 只給**成功**訊息用的短暫提示（幾秒後自己消失）。
    //
    // ZH: 🔴 錯誤訊息**不要**用這個 —— 它還沒被解決，讀者需要時間看清楚，
    //     而且訊息消失之後畫面看起來就像什麼都沒發生過。
    //     成功則相反：確認完就沒有用了，留著只會變成雜訊
    //     （下次再按時你分不出那是新的還是上次留下的）。
    var _flashTimers = {};
    function flash(id, text, ms) {
        say(id, text);
        // ZH: 成功訊息不要用紅底 —— say() 剛把它設成錯誤樣式，這裡換掉。
        var okEl = $(id);
        if (okEl) {
            okEl.classList.remove('inline-error');
            okEl.classList.add('inline-note');
        }
        // ZH: 舊的計時器一定要取消。不取消的話，上一次的計時器會在幾秒後
        //     把**新的**訊息清掉——包含錯誤訊息。
        clearTimeout(_flashTimers[id]);
        _flashTimers[id] = setTimeout(function () {
            var el = $(id);
            // ZH: 只清掉自己那一則。中間若換成別的訊息（例如錯誤），就不要動它。
            if (el && el.textContent === text) say(id, '');
        }, ms || 3000);
    }


    function wireDetail(u) {
        // ── 唯讀時：按「編輯」直接進（密碼留到儲存前那一道）──────────────
        if (!EDIT_BASIC) {
            $('b-edit').addEventListener('click', function () {
                EDIT_BASIC = true;
                renderDetail();
            });
            wireCommon(u);
            return;
        }

        // ── 編輯時 ──────────────────────────────────────────────────────
        $('b-cancel').addEventListener('click', function () {
            // ZH: 丟掉改動 —— 從 CURRENT 重畫即可，那份沒有被編輯過。
            EDIT_BASIC = false;
            renderDetail();
        });

        $('save').addEventListener('click', function () {
            // ZH: 儲存前的密碼確認（唯一一道）——用小彈窗問（v4.4b）。
            //     欄位值在 run 裡才讀：小彈窗不動編輯表單，值都還在。
            pwConfirm(T('pp_confirm_save', '管理者密碼確認'), null, async function (pw2) {
            if (!await verifyPassword(pw2)) {
                throw new Error(T('pp_unlock_bad', '密碼不對。'));
            }

            var patch = {
                email: $('f-email').value.trim() || null,
                department: $('f-dept').value.trim() || null,
                role: $('f-role').value,
                // ZH: v3.8 管理權限。勾選框沒帶上的話,畫面勾了但存不進去 ——
                //     而且畫面重讀後會變回原狀,看起來像「存檔壞了」。
                is_admin: $('f-is-admin') && $('f-is-admin').checked ? 1 : 0,
            };
            // ZH: 密碼留空 = 不改。送空字串會**把密碼設成空的**。
            var pw = $('f-pw').value;
            if (pw) patch.password = pw;

            try {
                await api('/admin/users/' + encodeURIComponent(u.id), {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(patch),
                });
            } catch (e) {
                // ZH: 丟給 pwConfirm 顯示在小彈窗裡（彈窗不關，密碼不用重打）。
                throw new Error(T('pp_save_fail', '存不起來（{w}）').replace('{w}', e.message));
            }
            Object.assign(u, { email: patch.email, department: patch.department, role: patch.role });
            EDIT_BASIC = false;            // ZH: 存完收回唯讀
            renderList();
            renderDetail();
            flash('save-msg', T('pp_saved', '已儲存'));
            });
        });

        wireCommon(u);
    }

    // ZH: 兩種模式都有的部分（危險操作那一區不受唯讀／編輯影響）。
    function wireCommon(u) {
        // ZH: v4.4b 停用/刪除都走密碼小彈窗。
        //     ⚠ 舊版「停用」其實**沒驗密碼**（危險卡的欄位只有刪除在讀）——
        //     這次補齊：停用也要驗（/admin/verify），與卡上的承諾一致。
        $('toggle-active').addEventListener('click', function () {
            pwConfirm(u.is_active ? T('pp_disable', '停用帳號') : T('pp_enable', '啟用帳號'),
                null,
                async function (pw) {
                    if (!await verifyPassword(pw)) {
                        throw new Error(T('pp_unlock_bad', '密碼不對。'));
                    }
                    await api('/admin/users/' + encodeURIComponent(u.id), {
                        method: 'PUT',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ is_active: u.is_active ? 0 : 1 }),
                    });
                    u.is_active = u.is_active ? 0 : 1;
                    renderList();
                    renderDetail();
                });
        });

        $('del').addEventListener('click', function () {
            // ZH: 刪除的確認句直接放在彈窗裡（原本的原生 confirm 併進來了）。
            pwConfirm(T('pp_delete', '刪除帳號'),
                T('pp_delete_confirm', '要刪除「{n}」嗎？').replace('{n}', u.username),
                async function (pw) {
                    // ZH: 刪除端點自己收 admin_password 驗 —— 不用先打 /admin/verify。
                    await api('/admin/users/' + encodeURIComponent(u.id) + '/delete', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ admin_password: pw }),
                    });
                    ALL = ALL.filter(function (x) { return x.id !== u.id; });
                    closeUserDialog();
                });
        });
    }

    // ── 額度 ──────────────────────────────────────────────────────────────
    // ── 外部 AI（MYAI）綁定與消耗 ─────────────────────────────────────────
    //
    // ZH: 兩件事放同一張卡：這個人綁到哪個廠商帳號、以及他用掉多少。
    //     ⚠ 後端沒有「單一使用者的綁定」端點，只有整份清單 ——
    //       所以這裡抓全部再挑出這一個人。人數上千時要回頭補一個端點。
    var EXT_EDIT = false;

    function extRo(b, c) {
        var kv = function (k, v) {
            return '<div class="kv"><span class="kv__k">' + esc(k) + '</span>'
                + '<span class="kv__v">' + esc(v) + '</span></div>';
        };
        var out = kv(T('pp_ext_vendor', '廠商帳號'), b.myai_email || '—')
            + kv(T('pp_ext_sn', '序號'), b.myai_vendor_sn || '—');

        // ZH: 點數只有對得上同步快取時才有值。對不上就明講「同步不到」——
        //     顯示「—」會被當成「他沒有點數」，那是完全不同的一件事。
        out += kv(T('pp_ext_points', '點數'),
                  b.synced ? num(b.points) : T('pp_ext_nosync', '同步不到這個帳號'));
        // ZH: ⚠ 唯讀這行也要翻譯。只在下拉裡翻的話，看的時候是 "active"、
        //     一按編輯變成「正常」—— 同一個值兩種樣子。
        out += kv(T('pp_ext_status', '狀態'),
                  b.status ? T('st_' + b.status, b.status) : '—');

        if (c && c.summary && c.summary.tx_count) {
            var s2 = c.summary, p = c.peer || {};
            out += '<div class="adm-card__title" style="margin-top:1rem">'
                + esc(T('pp_ext_used', '用了多少（全部期間）')) + '</div>'
                + kv(T('pp_ext_consumed', '總消耗'), num(s2.consumed) + ' ' + T('an_points', '點'))
                + kv(T('pp_ext_uses', 'AI 使用次數'), num(s2.uses))
                + kv(T('pp_ext_logins', '登入次數'), num(s2.logins))
                // ZH: 一個人的數字單看沒有意義 —— 給同期間的全體人均當基準，
                //     才知道「1000 點」是多還是少。
                + kv(T('pp_ext_peer', '全體人均'),
                     p.avg_consumed != null ? num(p.avg_consumed) + ' ' + T('an_points', '點') : '—');
        } else if (c) {
            out += '<p class="footnote">' + esc(T('pp_ext_notx', '交易日誌裡還沒有這個人的紀錄。')) + '</p>';
        }
        return out;
    }

    function extForm(b) {
        return field('e-email', T('pp_ext_vendor', '廠商帳號'), (b && b.myai_email) || '')
            + '<label class="field"><span class="field__label" for="e-status">'
            + esc(T('pp_ext_status', '狀態')) + '</span>'
            + '<select class="field__input" id="e-status">'
            + ['active', 'disabled'].map(function (r) {
                return '<option value="' + r + '"'
                    + ((b && b.status) === r ? ' selected' : '') + '>'
                    + esc(T('st_' + r, r)) + '</option>';
            }).join('')
            + '</select></label>'
            + field('e-note', T('pp_ext_note', '備註'), (b && b.note) || '');
    }

    async function loadExtAi(u) {
        var box = $('ext-box');
        var title = '<div class="adm-card__title">' + esc(T('pp_ext', '外部 AI（MYAI）')) + '</div>';
        var b = null, c = null;
        try {
            var all = await api('/external-ai/admin/bindings');
            b = (all.bindings || []).filter(function (x) { return x.user_id === u.id; })[0] || null;
        } catch (e) {
            box.innerHTML = title + '<p class="footnote">'
                + esc(T('ov_fail_part', '這一段暫時讀不到（{w}）').replace('{w}', e.message)) + '</p>';
            return;
        }

        // ZH: 有綁定才查消耗 —— 查詢的鍵是廠商那邊的 email，沒綁就沒得查。
        if (b && b.myai_email) {
            try {
                c = await api('/external-ai/admin/user-consumption?days=0&q='
                              + encodeURIComponent(b.myai_email));
            } catch (e) { c = null; }
        }

        if (!b) {
            box.innerHTML = title
                + '<p class="footnote">' + esc(T('pp_ext_unbound', '還沒有綁定廠商帳號。')) + '</p>'
                + field('e-email', T('pp_ext_vendor', '廠商帳號'), u.email || '')
                + '<div class="ds__actions">'
                + '<button class="btn btn--minor" type="button" id="e-bind">'
                + esc(T('pp_ext_bind', '綁定')) + '</button></div>'
                + '<div class="inline-error" id="e-msg" hidden></div>';
            $('e-bind').addEventListener('click', function () { bindExt(u); });
            return;
        }

        box.innerHTML = title
            + (EXT_EDIT ? extForm(b) : extRo(b, c))
            + '<div class="ds__actions">'
            + (EXT_EDIT
                ? '<button class="btn btn--primary" type="button" id="e-save">'
                    + esc(T('pp_save', '儲存')) + '</button>'
                    + '<button class="btn btn--minor" type="button" id="e-cancel">'
                    + esc(T('pp_cancel', '取消變更')) + '</button>'
                : '<button class="btn btn--minor" type="button" id="e-edit">'
                    + esc(T('pp_edit', '編輯')) + '</button>'
                    + '<button class="btn btn--minor" type="button" id="e-grant">'
                    + esc(T('pp_ext_grant', '加點')) + '</button>'
                    + '<button class="btn btn--minor" type="button" id="e-unbind">'
                    + esc(T('pp_ext_unbind', '解除綁定')) + '</button>')
            + '</div>'
            + '<div id="e-grant-box" hidden></div>'
            + '<div class="inline-error" id="e-msg" hidden></div>';

        if (EXT_EDIT) {
            $('e-save').addEventListener('click', function () { saveExtAi(u, b); });
            $('e-cancel').addEventListener('click', function () {
                EXT_EDIT = false;
                loadExtAi(u);
            });
        } else {
            $('e-edit').addEventListener('click', function () {
                EXT_EDIT = true;
                loadExtAi(u);
            });
            $('e-unbind').addEventListener('click', function () { unbindExt(u, b); });
            $('e-grant').addEventListener('click', function () { toggleGrant(u, b); });
        }
    }

    // ZH: 個別加點（v3.9）
    //
    // ZH: 🔴 **這是「加 N」不是「補到 N」——按兩次就發兩次。**
    //     管理端的「手動補齊」重按是安全的（大家都在同一水位就沒有差額），
    //     這一支不是。所以送出前一定要 confirm()，而且訊息裡要**寫出數字**：
    //     「確定嗎」擋不住手滑，「要給 X 加 500 點嗎」才擋得住。
    function closeGrant() {
        var box = $('e-grant-box');
        if (!box) return;
        box.hidden = true;
        box.innerHTML = '';
        say('e-msg', '');      // ZH: 關掉表單也要清掉它留下的錯誤訊息
    }

    function toggleGrant(u, b) {
        var box = $('e-grant-box');
        if (!box.hidden) { closeGrant(); return; }
        box.innerHTML =
            '<p class="footnote">' + esc(T('pp_grant_why',
                '直接加給這個人，不是補到某個水位。點數從平台的廠商管理帳號轉出，不可逆。'))
            + '</p>'
            + field('e-grant-pts', T('pp_grant_pts', '要加的點數'), '', 'number',
                    ' min="1" step="1" inputmode="numeric"')
            + field('e-grant-why', T('pp_grant_reason', '原因（會寫進紀錄）'), '')
            + '<div class="ds__actions">'
            + '<button class="btn btn--primary" type="button" id="e-grant-go">'
            + esc(T('pp_grant_go', '送出加點')) + '</button>'
            + '<button class="btn btn--minor" type="button" id="e-grant-cancel">'
            + esc(T('pp_grant_cancel', '取消')) + '</button></div>';
        box.hidden = false;
        $('e-grant-go').addEventListener('click', function () { doGrant(u, b); });
        $('e-grant-cancel').addEventListener('click', closeGrant);
        $('e-grant-pts').focus();
    }

    async function doGrant(u, b) {
        var pts = parseInt($('e-grant-pts').value, 10);
        if (!isFinite(pts) || pts <= 0) {
            say('e-msg', T('pp_grant_need', '請填一個大於 0 的點數。'));
            return;
        }
        var why = $('e-grant-why').value.trim();
        // ZH: 數字寫進確認訊息 —— 這是唯一擋得住「多打一個 0」的地方。
        if (!confirm(T('pp_grant_confirm',
                '要給 {n} 加 {p} 點嗎？點數從平台的管理帳號轉出，送出後收不回來。')
                .replace('{n}', b.myai_email || u.username).replace('{p}', num(pts)))) return;

        var btn = $('e-grant-go');
        btn.disabled = true;            // ZH: 防連點 —— 這一支不冪等
        try {
            var r = await api('/admin/users/' + encodeURIComponent(u.id) + '/myai/grant', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ points: pts, reason: why }),
            });
            closeGrant();
            if (r.status === 'unknown') {
                // ZH: 送出後廠商沒回報成功 —— 點數可能已經轉出。
                //     這一則要留在畫面上（紅的），不能用會消失的提示：
                //     訊息一消失，「不要再按一次」也跟著消失了。
                say('e-msg', T('pp_grant_unknown',
                    '送出了，但廠商沒有回報成功。點數可能已經轉出 —— '
                    + '請到廠商後台對帳，不要再送一次。'));
            } else {
                say('e-msg', '');
                loadExtAi(u);          // ZH: 重讀，讓點數欄顯示新的值
            }
        } catch (e) {
            say('e-msg', String(e.message || e));
        } finally {
            btn.disabled = false;
        }
    }

    async function bindExt(u) {
        var email = $('e-email').value.trim();
        if (!email) { say('e-msg', T('pp_ext_need_email', '要填廠商那邊的帳號。')); return; }
        try {
            await api('/external-ai/admin/accounts', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    platform_username: u.username, vendor_username: email, status: 'active',
                }),
            });
            loadExtAi(u);
        } catch (e) { say('e-msg', e.message); }
    }

    async function saveExtAi(u, b) {
        try {
            await api('/external-ai/admin/accounts/' + encodeURIComponent(b.id), {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    vendor_username: $('e-email').value.trim(),
                    status: $('e-status').value,
                    note: $('e-note').value.trim(),
                }),
            });
            EXT_EDIT = false;
            loadExtAi(u);
        } catch (e) { say('e-msg', e.message); }
    }

    async function unbindExt(u, b) {
        // ZH: 明講解除之後會怎樣 —— 不講的話沒有人敢按，
        //     而且要說清楚**廠商那邊不受影響**（我們從來不寫廠商的資料）。
        if (!confirm(T('pp_ext_unbind_confirm',
                '要解除 {n} 的綁定嗎？只是拿掉平台這邊的對應，廠商那邊的帳號與點數不受影響。')
                .replace('{n}', b.myai_email || b.myai_vendor_sn || ''))) return;
        try {
            await api('/external-ai/admin/accounts/' + encodeURIComponent(b.id), { method: 'DELETE' });
            loadExtAi(u);
        } catch (e) { say('e-msg', e.message); }
    }

    // ZH: 一次性解鎖（v3.8）。校區／學系／行政單位在使用者初次設定之後就鎖住,
    //     要改得由管理者在這裡開放一次。「一次」＝**他成功存檔一次**,不是一段時間。
    var UNLOCK_LABELS = { campus: ['pp_unl_campus', '校區'],
                          department: ['pp_unl_dept', '學系'],
                          unit: ['pp_unl_unit', '行政單位'] };

    async function loadUnlock(u) {
        var box = $('unlock-box');
        try {
            var d = await api('/admin/users/' + encodeURIComponent(u.id) + '/profile-unlock');
            var a = d.active;
            box.innerHTML =
                '<div class="adm-card__title">' + esc(T('pp_unlock', '修改個人資料的授權')) + '</div>'
                + (a
                    // ZH: 已開放時把**範圍**列出來 —— 只說「已開放」的話,
                    //     管理者不知道他能改哪幾項,而範圍是核可時就決定好的。
                    ? '<div class="adm-alert"><span>'
                      + esc(T('pp_unl_open', '已開放（{f}）').replace('{f}',
                            (a.fields || []).map(function (f) {
                                return T(UNLOCK_LABELS[f] ? UNLOCK_LABELS[f][0] : f,
                                         UNLOCK_LABELS[f] ? UNLOCK_LABELS[f][1] : f);
                            }).join('、')))
                      + '　<span class="footnote">' + esc(TW.date(a.granted_at))
                      + (a.reason ? '　' + esc(a.reason) : '') + '</span></span>'
                      + '<button class="btn btn--minor" type="button" id="unl-cancel">'
                      + esc(T('pp_unl_cancel', '收回')) + '</button></div>'
                    : '<p class="footnote">' + esc(T('pp_unl_locked', '目前鎖定中。')) + '</p>')
                + (d.last_used
                    ? '<p class="footnote">'
                      + esc(T('pp_unl_last', '上次修改：{d}').replace('{d}', TW.date(d.last_used.used_at)))
                      + '</p>'
                    : '')
                // ZH: 核可表單常駐（不收進 fold）—— 使用者是用「問題回報」來申請的,
                //     管理者看到申請時人已經在這一頁上了,再多一次展開只是多一步。
                // ZH: v4.4c 範圍**依身分自動決定**（擁有者裁定 2026-09-03）：
                //     不再逐項勾選 —— 老師/學生＝校區＋學系、職員＝校區＋單位、
                //     訪客＝僅校區，一次全給。逐項挑的需求從沒出現過，
                //     挑錯反而會讓對方改到一半發現差一項、再跑一次申請。
                + '<div class="adm-card__title" style="margin-top:1rem">'
                + esc(T('pp_unl_grant', '開放一次修改')) + '</div>'
                + '<p class="footnote">'
                + esc(T('pp_unl_scope', '會開放：{f}（依他的身分決定）').replace('{f}',
                    unlockFieldsFor(u).map(function (f) {
                        var lab = UNLOCK_LABELS[f] || [f, f];
                        return T(lab[0], lab[1]);
                    }).join('、'))) + '</p>'
                + field('unl-reason', T('pp_unl_reason', '原因（會寫進稽核）'), '')
                + '<div class="ds__actions">'
                + '<button class="btn btn--primary" type="button" id="unl-go">'
                + esc(T('pp_unl_do', '開放一次修改')) + '</button></div>'
                + '<div class="inline-error" id="unl-msg" hidden></div>';

            var go = $('unl-go');
            if (go) go.addEventListener('click', function () { grantUnlock(u); });
            var cancel = $('unl-cancel');
            // ZH: 「收回」＝把還沒用掉的那筆標成已用掉。不刪紀錄 —— 稽核要看得出開過。
            if (cancel) cancel.addEventListener('click', function () { grantUnlock(u, true); });
        } catch (e) {
            box.innerHTML = '<div class="adm-card__title">'
                + esc(T('pp_unlock', '修改個人資料的授權')) + '</div>'
                + '<p class="footnote">' + esc(e.message) + '</p>';
        }
    }

    // ZH: v4.4c 這個身分能改哪些欄位（與初次設定的 ONBOARDING_FIELDS 同一套邏輯）：
    //     校區人人有；老師/學生＝學系、職員/admin＝行政單位、訪客沒有組織欄。
    function unlockFieldsFor(u) {
        var out = ['campus'];
        if (u.role === 'staff' || u.role === 'admin') out.push('unit');
        else if (u.role !== 'guest') out.push('department');
        return out;
    }

    async function grantUnlock(u, revoke) {
        var msg = $('unl-msg');
        var fields = revoke ? [] : unlockFieldsFor(u);
        try {
            if (revoke) {
                await api('/admin/users/' + encodeURIComponent(u.id) + '/profile-unlock/revoke',
                          { method: 'POST' });
            } else {
                await api('/admin/users/' + encodeURIComponent(u.id) + '/profile-unlock', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ fields: fields,
                                           reason: ($('unl-reason') || {}).value || '' }),
                });
            }
            loadUnlock(u);          // ZH: 重讀 —— 狀態由後端決定,不要在前端自己推
        } catch (e) {
            if (msg) { msg.textContent = e.message; msg.hidden = false; }
        }
    }

    async function loadQuota(u) {
        var box = $('quota-box');
        try {
            var q = await api('/admin/quota/' + encodeURIComponent(u.id));
            var live = (q.grants || []).filter(function (g) { return !g.revoked_at; });
            box.innerHTML =
                '<div class="adm-card__title">' + esc(T('pp_quota', '磁碟配額')) + '</div>'
                + '<div class="kv"><span class="kv__k">' + esc(T('pp_q_base', '基本')) + '</span>'
                + '<span class="kv__v">' + esc(q.base_quota_gb) + ' GB</span></div>'
                + '<div class="kv"><span class="kv__k">' + esc(T('pp_q_effective', '實際可用')) + '</span>'
                + '<span class="kv__v">' + esc(q.effective_quota_gb) + ' GB</span></div>'
                // ZH: v3.9 實際用量。**要與配額並排顯示** —— 只給配額的話，
                //     管理者無從判斷該不該加額度（那正是 v3.9 之前的狀況：
                //     `current_size_gb` 沒有人更新，永遠是 0）。
                // ZH: null = 從沒量到過（沒開過 Lab 或量測失敗），與「0」是兩件事。
                + '<div class="kv"><span class="kv__k">' + esc(T('pp_q_used', '已使用')) + '</span>'
                + '<span class="kv__v">'
                + (q.used_gb == null ? esc(T('pp_q_unknown', '尚未量測'))
                   : esc(q.used_gb) + ' GB'
                     + (q.effective_quota_gb && q.used_gb > q.effective_quota_gb
                        ? ' ' + esc(T('pp_q_over', '（超出配額）')) : ''))
                + '</span></div>'

                + '<div class="adm-card__title" style="margin-top:1rem">'
                + esc(T('pp_q_grants', '額外授與')) + '</div>'
                + (live.length
                    ? live.map(function (g) {
                        return '<div class="adm-alert">'
                            + '<span>+' + esc(g.extra_quota_gb) + ' GB　'
                            + '<span class="footnote">' + esc(g.reason || '')
                            + (g.expires_at ? '　→ ' + esc(TW.date(g.expires_at)) : '') + '</span></span>'
                            + '<button class="btn btn--minor" type="button" data-revoke="' + esc(g.id) + '">'
                            + esc(T('pp_q_revoke', '收回')) + '</button></div>';
                    }).join('')
                    : '<p class="footnote">' + esc(T('pp_q_none', '沒有額外授與。')) + '</p>')

                + '<div class="adm-inline">'
                // ZH: placeholder 不算可及的名稱 —— 一填字就消失了，
                //     而讀螢幕的人本來就聽不到它。要另外給 aria-label。
                + '<input class="field__input" id="g-gb" type="number" min="1" placeholder="GB"'
                + ' aria-label="' + esc(T('pp_q_add_gb', '要加幾 GB')) + '">'
                + '<input class="field__input" id="g-why" type="text" placeholder="'
                + esc(T('pp_q_reason', '原因（必填）')) + '"'
                + ' aria-label="' + esc(T('pp_q_reason', '原因（必填）')) + '">'
                // ZH: 日期欄位一定要有標示 —— 一個空的 date 框看不出是「到期日」
                //     還是「起始日」，而填錯的後果是額度提早消失。
                + '<input class="field__input" id="g-exp" type="date" title="'
                + esc(T('pp_q_expires', '到期日（可留空）')) + '" aria-label="'
                + esc(T('pp_q_expires', '到期日（可留空）')) + '">'
                + '<button class="btn btn--minor" type="button" id="g-add">'
                + esc(T('pp_q_add', '加額度')) + '</button>'
                + '</div>'
                + '<div class="inline-error" id="q-msg" hidden></div>';

            box.querySelectorAll('[data-revoke]').forEach(function (b) {
                b.addEventListener('click', async function () {
                    try {
                        await api('/admin/quota/grant/' + encodeURIComponent(b.dataset.revoke),
                                  { method: 'DELETE' });
                        loadQuota(u);
                    } catch (e) { say('q-msg', e.message); }
                });
            });

            $('g-add').addEventListener('click', async function () {
                var gb = parseInt($('g-gb').value, 10);
                var why = $('g-why').value.trim();
                if (!gb || !why) {
                    // ZH: 原因是必填 —— 半年後看到一筆沒有原因的加額，沒有人記得為什麼。
                    say('q-msg', T('pp_q_reason', '原因（必填）'));
                    return;
                }
                var body = { user_id: u.id, extra_quota_gb: gb, reason: why };
                if ($('g-exp').value) body.expires_at = $('g-exp').value;
                try {
                    await api('/admin/quota/grant', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(body),
                    });
                    loadQuota(u);
                } catch (e) { say('q-msg', e.message); }
            });
        } catch (e) {
            box.innerHTML = '<div class="adm-card__title">' + esc(T('pp_quota', '磁碟配額')) + '</div>'
                + '<p class="footnote">' + esc(T('ov_fail_part', '這一段暫時讀不到（{w}）')
                    .replace('{w}', e.message)) + '</p>';
        }
    }

    // ── 實驗室 ────────────────────────────────────────────────────────────
    async function loadLab(u) {
        var box = $('lab-box');
        try {
            var all = await api('/admin/lab/sessions');
            var list = (all.sessions || all || []).filter(function (s) {
                return s.user_id === u.id;
            });
            box.innerHTML = '<div class="adm-card__title">' + esc(T('pp_lab', '程式實驗室')) + '</div>'
                + (list.length
                    ? list.map(function (s) {
                        // ZH: 顯示**使用者取的名字**，容器名放在後面當佐證。
                        //     ⚠ 不要寫 `s.session_name || 'default'` —— 後端一度不回這個欄位，
                        //     那樣會讓每一份都顯示「default」，是個看起來很正常的錯誤答案。
                        //     現在後端會回了（force_stop 那次一起補的），但這個寫法的教訓留著。
                        return '<div class="adm-alert"><span>'
                            + esc(s.display_name || s.session_name || '—') + '　'
                            + '<span class="footnote mono">' + esc(s.container_name || '') + '</span>　'
                            + '<span class="adm-pill adm-pill--' + esc(s.status) + '">'
                            + esc(s.status) + '</span>'
                            + (s.started_at ? '　<span class="footnote">'
                                + esc(TW.when(s.started_at)) + '</span>' : '')
                            + '</span>'
                            // ZH: 用 data 屬性而不是 id —— 同一個 id 出現多次是無效的 HTML，
                            //     而且 `getElementById` 只拿得到第一顆：
                            //     第二份存檔的按鈕會**看得到但按不動**。
                            //     （目前一次只開一份，所以這是預防性的；但約束在別處，
                            //       這裡不該建立在「那邊不會改」之上。）
                            + '<button class="btn btn--minor" type="button" data-stop="'
                            + esc(s.session_name || '') + '">'
                            + esc(T('pp_lab_stop', '強制關閉')) + '</button></div>';
                    }).join('')
                    : '<p class="footnote">' + esc(T('pp_lab_none', '目前沒有執行中的實驗室。')) + '</p>')
                + '<div class="inline-error" id="lab-msg" hidden></div>';

            box.querySelectorAll('[data-stop]').forEach(function (btn) {
                btn.addEventListener('click', async function () {
                    if (!confirm(T('pp_lab_confirm', '要強制關閉「{n}」的實驗室嗎？')
                        .replace('{n}', u.username))) return;
                    try {
                        // ZH: 明確指名要關哪一份。留空時後端會關「正在跑的那一份」，
                        //     但既然畫面上就是按著某一列，指名比較不會有意外。
                        var q = btn.dataset.stop ? '?session=' + encodeURIComponent(btn.dataset.stop) : '';
                        await api('/admin/lab/sessions/' + encodeURIComponent(u.id) + '/force-stop' + q,
                                  { method: 'POST' });
                        loadLab(u);
                    } catch (e) { say('lab-msg', e.message); }
                });
            });
        } catch (e) {
            box.innerHTML = '<div class="adm-card__title">' + esc(T('pp_lab', '程式實驗室')) + '</div>'
                + '<p class="footnote">' + esc(T('ov_fail_part', '這一段暫時讀不到（{w}）')
                    .replace('{w}', e.message)) + '</p>';
        }
    }

    // ── 啟動 ──────────────────────────────────────────────────────────────
    // ══════════════════════════════════════════════════════════════════
    // ZH: v4.2 批次匯入臨時帳號（擁有者需求 2026-09-02）。
    //     每列：帳號名稱,信箱,密碼,身分（後三欄可留空）；用途與到期日整批共用。
    //     兩段式（預覽 → 確認建立），與手動補齊/組織匯入同一套慣例。
    //     後端全有或全無：任何一列有錯就整批不建（預覽先把錯抓出來）。
    // ══════════════════════════════════════════════════════════════════
    // ZH: v4.2b 改檔案匯入（擁有者修訂 2026-09-03）：CSV/XLSX 由**後端**解析
    //     （Big5/UTF-8、Excel 數值格式都在那邊處理），前端只負責把檔案送過去。
    var TI_FILE = null;          // ZH: 已選的檔案；改任何欄位就作廢預覽（防「看A送B」）

    function tempImportForm(dryRun) {
        var fd = new FormData();
        fd.append('file', TI_FILE);
        fd.append('purpose', $('ti-why').value.trim());
        fd.append('expires_on', $('ti-expires').value);
        fd.append('dry_run', dryRun ? 'true' : 'false');
        return fd;
    }

    // ZH: 範例檔下載。端點要 Authorization，不能用 <a href>（同組織匯出的理由）。
    async function downloadTemplate(fmt) {
        try {
            var res = await fetch(API + '/admin/users/temporary/import-template?fmt=' + fmt,
                                  { headers: { Authorization: 'Bearer ' + token() } });
            if (!res.ok) throw new Error('HTTP ' + res.status);
            var blob = await res.blob();
            var url = URL.createObjectURL(blob);
            var a = document.createElement('a');
            a.href = url;
            a.download = 'temp-accounts-template.' + fmt;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
        } catch (e) { say('ti-msg', e.message); }
    }

    function openTempImport() {
        var dlg = _tempDlg(false);
        dlg.innerHTML =
            '<form method="dialog" class="rmod__x">'
            +   '<button class="btn btn--minor" type="submit" aria-label="'
            +   esc(T('pf_close', '關閉')) + '">✕</button></form>'
            + '<h2 class="rmod__title">' + esc(T('tmpi_title', '匯入臨時帳號')) + '</h2>'
            + '<p class="footnote">' + esc(T('tmpi_fmt',
                '每行一個帳號，欄位用逗號分開：帳號名稱,信箱,密碼,身分。'
                + '信箱可空（不寄信）；密碼可空（系統產生，建立後顯示一次）；'
                + '身分可空（預設學生），可用：學生/老師/職員/訪客。')) + '</p>'
            + field('ti-why', T('tmp_purpose', '用途（必填）'), '')
            + field('ti-expires', T('tmp_expires_on', '到期日'), twDay(1), 'date',
                    ' min="' + twDay(0) + '" max="' + twDay(TEMP_MAX_DAYS) + '"')
            + '<div class="adm-inline">'
            + '<button class="btn btn--minor" type="button" id="ti-tpl-csv">'
            + esc(T('tmpi_tpl_csv', '下載範例 CSV')) + '</button>'
            + '<button class="btn btn--minor" type="button" id="ti-tpl-xlsx">'
            + esc(T('tmpi_tpl_xlsx', '下載範例 Excel')) + '</button>'
            + '</div>'
            + '<div class="adm-inline">'
            + '<input type="file" id="ti-file" accept=".csv,.xlsx" hidden>'
            + '<button class="btn btn--minor" type="button" id="ti-pick">'
            + esc(T('tmpi_pick', '選擇檔案（CSV / Excel）')) + '</button>'
            + '<span class="footnote" id="ti-fname">' + esc(T('tmpi_nofile', '尚未選擇')) + '</span>'
            + '</div>'
            + '<div class="adm-inline rmod__foot">'
            + '<button class="btn btn--minor" type="button" id="ti-preview">'
            + esc(T('tmpi_preview', '預覽')) + '</button>'
            + '<button class="btn btn--primary" type="button" id="ti-apply" hidden>'
            + esc(T('tmpi_apply', '確認建立')) + '</button>'
            + '<button class="btn btn--minor" type="button" id="ti-cancel">'
            + esc(T('tmp_cancel', '取消')) + '</button>'
            + '</div>'
            + '<div id="ti-result" aria-live="polite"></div>'
            + '<div class="inline-error" id="ti-msg" hidden></div>';

        dlg.showModal();
        TI_FILE = null;
        $('ti-cancel').addEventListener('click', function () { dlg.close(); });
        $('ti-preview').addEventListener('click', previewTempImport);
        $('ti-apply').addEventListener('click', applyTempImport);
        $('ti-tpl-csv').addEventListener('click', function () { downloadTemplate('csv'); });
        $('ti-tpl-xlsx').addEventListener('click', function () { downloadTemplate('xlsx'); });
        $('ti-pick').addEventListener('click', function () { $('ti-file').click(); });
        $('ti-file').addEventListener('change', function () {
            TI_FILE = ($('ti-file').files || [])[0] || null;
            $('ti-fname').textContent = TI_FILE ? TI_FILE.name : T('tmpi_nofile', '尚未選擇');
            $('ti-apply').hidden = true;
            $('ti-result').innerHTML = '';
        });
        // ZH: 內容一改，上一份預覽就不算數（同手動補齊：看 A 的預覽送出 B 很危險）。
        ['ti-why', 'ti-expires'].forEach(function (id) {
            $(id).addEventListener('input', function () {
                $('ti-apply').hidden = true;
                $('ti-result').innerHTML = '';
            });
        });
        $('ti-why').focus();
    }

    function renderTempPreview(r) {
        var roleName = { student: T('role_student', '學生'), teacher: T('role_teacher', '教師'),
                         staff: T('role_staff', '職員'), guest: T('role_guest', '訪客') };
        $('ti-result').innerHTML =
            '<div class="adm-tablewrap"><table class="adm-table"><thead><tr>'
            + '<th>' + esc(T('pp_c_user', '帳號')) + '</th>'
            + '<th>' + esc(T('pp_c_role', '角色')) + '</th>'
            + '<th>' + esc(T('tmpi_pw_col', '密碼')) + '</th>'
            + '<th>' + esc(T('tmpi_check', '檢查')) + '</th>'
            + '</tr></thead><tbody>'
            + r.rows.map(function (x) {
                return '<tr><td>' + esc(x.username || '—') + '</td>'
                    + '<td>' + esc(roleName[x.role] || '—') + '</td>'
                    + '<td>' + esc(x.will_generate_pw
                        ? T('tmpi_pw_gen', '系統產生') : T('tmpi_pw_given', '檔案提供')) + '</td>'
                    + '<td>' + (x.errors.length
                        ? '<span class="adm-pill adm-pill--temp">' + esc(x.errors.join('、')) + '</span>'
                        : '✓') + '</td></tr>';
            }).join('')
            + '</tbody></table></div>';
        if (r.ok) {
            note('ti-msg', T('tmpi_sum', '{n} 個帳號可建立。按「確認建立」才會送出。')
                .replace('{n}', num(r.total)));
        } else {
            say('ti-msg', T('tmpi_bad', '{e} 列有問題（見「檢查」欄）——整批都不會建立，改好再預覽一次。')
                .replace('{e}', num(r.error_rows)));
        }
        $('ti-apply').hidden = !r.ok;
    }

    async function previewTempImport() {
        if (!TI_FILE) { say('ti-msg', T('tmpi_empty', '先選擇檔案。')); return; }
        say('ti-msg', '');
        try {
            // ZH: FormData 不能自帶 Content-Type —— 瀏覽器要自己放 boundary。
            var r = await api('/admin/users/temporary/import', {
                method: 'POST',
                body: tempImportForm(true),
            });
            renderTempPreview(r);
        } catch (e) { say('ti-msg', e.message); }
    }

    async function applyTempImport() {
        $('ti-apply').disabled = true;      // ZH: 防連點
        try {
            var r = await api('/admin/users/temporary/import', {
                method: 'POST',
                body: tempImportForm(false),
            });
            showImportResult(r);
            ALL = await loadAll();
            renderList();
        } catch (e) {
            say('ti-msg', e.message);
            $('ti-apply').disabled = false;
        }
    }

    function showImportResult(r) {
        // ZH: 有系統產生的密碼 → 鎖 ESC（與單筆同一個「只顯示一次」契約）。
        var gen = r.created.filter(function (x) { return x.password; });
        var dlg = _tempDlg(gen.length > 0);
        dlg.innerHTML =
            '<form method="dialog" class="rmod__x">'
            +   '<button class="btn btn--minor" type="submit" aria-label="'
            +   esc(T('pf_close', '關閉')) + '">✕</button></form>'
            + '<h2 class="rmod__title">' + esc(T('tmpi_done', '匯入完成')) + '</h2>'
            + '<p class="footnote">' + esc(T('tmpi_done_sum', '共建立 {n} 個臨時帳號。')
                .replace('{n}', num(r.total))) + '</p>'
            + (gen.length
                ? '<div class="adm-alert adm-alert--error"><span>'
                  + esc(T('tmpi_pw_once',
                      '🔴 下面這些密碼是系統產生的，只會顯示這一次。現在就抄下來——關掉之後就看不到了。'))
                  + '</span></div>'
                  + '<div class="adm-tablewrap"><table class="adm-table"><thead><tr>'
                  + '<th>' + esc(T('pp_c_user', '帳號')) + '</th>'
                  + '<th>' + esc(T('tmp_pw', '密碼')) + '</th>'
                  + '</tr></thead><tbody>'
                  + gen.map(function (x) {
                      return '<tr><td class="mono">' + esc(x.username) + '</td>'
                          + '<td class="mono">' + esc(x.password) + '</td></tr>';
                  }).join('')
                  + '</tbody></table></div>'
                : '')
            + '<div class="adm-inline rmod__foot">'
            + (gen.length
                ? '<button class="btn btn--primary" type="button" id="ti-copy">'
                  + esc(T('tmpi_copy', '複製全部帳密')) + '</button>'
                : '')
            + '<button class="btn btn--minor" type="button" id="ti-close">'
            + esc(T('tmp_close', '知道了')) + '</button>'
            + '</div>'
            + '<div class="inline-error" id="ti-msg" hidden></div>';
        if (gen.length) {
            $('ti-copy').addEventListener('click', async function () {
                var text = gen.map(function (x) { return x.username + ' / ' + x.password; }).join('\n');
                try {
                    await navigator.clipboard.writeText(text);
                    flash('ti-msg', T('tmp_copied', '已複製'));
                } catch (e) { say('ti-msg', T('tmpi_copy_fail', '複製被擋，請手動選取。')); }
            });
        }
        $('ti-close').addEventListener('click', function () { dlg.close(); });
    }

    $('new-temp').addEventListener('click', openTempForm);
    $('import-temp').addEventListener('click', openTempImport);

    // ── 廠商帳號對應（維運）───────────────────────────────────────────────
    //
    // ZH: 四件事放同一區，因為它們是同一條動線：
    //       同步廠商帳號 → 自動配對 → 看還有誰對不上 → 看還有誰要開通
    //
    // ZH: 🔴 「同步」與「配對」是**兩件不同的事**，介面上不能混：
    //       同步  = headless 登入廠商網站把帳號與點數抓回來（讀廠商）
    //       配對  = 用 email 把廠商帳號對到平台使用者（只寫我們自己的表）
    //     兩者都不寫廠商的資料，這點要講出來 —— 不然沒有人敢按。
    var BX = null;

    async function loadBatch() {
        try {
            // ZH: 三份資料各自獨立，一起抓。任何一份失敗就整區顯示錯誤 ——
            //     這一區的數字要一起看才有意義，缺一份就會誤導。
            var out = await Promise.all([
                api('/external-ai/admin/myai-accounts'),
                api('/external-ai/admin/unmatched'),
                api('/external-ai/admin/provision-candidates'),
            ]);
            BX = { myai: out[0], un: out[1], prov: out[2] };
        } catch (e) {
            $('bx-body').innerHTML = '<p class="footnote">'
                + esc(T('ov_fail_part', '這一段暫時讀不到（{w}）').replace('{w}', e.message)) + '</p>';
            return;
        }
        renderBatch();
    }

    function renderBatch() {
        if (!BX) return;
        var m = BX.myai, un = BX.un, pv = BX.prov;

        // ZH: 同步時間一定要講 —— 一份三天前的帳號清單看起來跟今天的一模一樣。
        $('bx-sum').textContent = m.synced_at
            ? T('pp_bx_sum', '廠商帳號 {n} 筆，同步到 {t}')
                .replace('{n}', num(m.count)).replace('{t}', TW.dateTime(m.synced_at))
            : T('pp_bx_never', '還沒有同步過廠商帳號。');

        var total = (un.unmatched_users || []).length + (un.unmatched_myai || []).length
            + (pv.ready || []).length + (pv.no_email || []).length
            + (pv.staff_pending || []).length;

        var C_ACC = ['pp_bx_c_acc', '帳號'];
        // ZH: 中英一樣，不需要 key。（給了 key 反而會被 check_i18n 報成
        //     「沒有人用」—— 它的判準是 key 後面緊接一個**含中文**的 fallback。）
        var C_MAIL = ['', 'Email'];
        var C_TAG = ['pp_bx_c_tag', '狀況'];

        $('bx-body').innerHTML =
            blockTable('pp_bx_un_users', '平台使用者還沒綁定',
                'pp_bx_un_users_why', '這些人在平台上有帳號，但沒有對應到任何廠商帳號。標「找得到同 email」的按「自動配對」就會接上。',
                [C_ACC, C_MAIL, C_TAG],
                (un.unmatched_users || []).map(function (u) {
                    return [{ t: u.username }, { t: u.email || '—' },
                            { t: u.has_myai_match ? T('pp_bx_hasmatch', '找得到同 email') : '',
                              pill: true }];
                }))

            + blockTable('pp_bx_un_myai', '廠商帳號沒有對到人',
                'pp_bx_un_myai_why', '廠商那邊有這些帳號，但平台上沒有人對應。多半是老師，或用了與平台不同的信箱。',
                [C_ACC, C_MAIL, C_TAG, ['pp_bx_c_points', '點數', 'num']],
                (un.unmatched_myai || []).map(function (r) {
                    return [{ t: r.name || r.vendor_sn }, { t: r.email || '—' },
                            { t: r.has_platform_user ? T('pp_bx_hasuser', '找得到同 email 的使用者') : '',
                              pill: true },
                            { t: num(r.points), cls: 'num' }];
                }))

            // ZH: 待開通依**事實**分三類（有沒有信箱、網域屬不屬教職員），
            //     不做「這個信箱大概是真的」這種預測 —— 寄出去看退件才是事實。
            + blockTable('pp_bx_ready', '可以開通',
                'pp_bx_ready_why', '有信箱、還沒綁定廠商帳號的人。信箱真假不預判，寄出後看退件紀錄。',
                [C_ACC, C_MAIL, ['pp_bx_c_domain', '網域']],
                (pv.ready || []).map(function (r) {
                    return [{ t: r.username }, { t: r.email }, { t: r.label || r.domain || '—' }];
                }))

            + blockTable('pp_bx_noemail', '沒有信箱，無法開通',
                'pp_bx_noemail_why', '完全沒有信箱，沒辦法建廠商帳號，要人工補。',
                [C_ACC, C_MAIL],
                (pv.no_email || []).map(function (r) {
                    return [{ t: r.username }, { t: r.platform_email || '—' }];
                }))

            + blockTable('pp_bx_staff', '信箱看起來是教職員，角色還是學生',
                'pp_bx_staff_why', 'v3.8 起新帳號會依信箱網域自動判角色；這裡列的是 v3.8 之前建立、或被改回學生的帳號。',
                [C_ACC, C_MAIL, ['pp_bx_c_domain', '網域']],
                (pv.staff_pending || []).map(function (r) {
                    return [{ t: r.username }, { t: r.email || '—' }, { t: r.domain || '—' }];
                }))

            + (total === 0
                ? '<p class="footnote">' + esc(T('pp_bx_allgood', '兩邊都對上了，也沒有人在等開通。')) + '</p>'
                : '');
    }

    // ZH: 每一塊：標題（含筆數）+ 一句說明 + 表格。**空的就整塊不畫** ——
    //     五個「沒有」疊在一起會把真正有東西的那一塊淹掉。
    //
    // ZH: 🔴 用表格不用清單。原本是 flex 的 space-between，於是名字在最左、
    //     點數在最右，中間空了 1138px（實測）—— 要把一列讀完得橫掃整個螢幕。
    //     表格的欄位會對齊，而且**有欄位標題**告訴你右邊那個數字是什麼。
    var BX_MAX = 20;
    function blockTable(key, zh, whyKey, whyZh, cols, rows) {
        if (!rows.length) return '';
        var shown = rows.slice(0, BX_MAX);
        return '<section class="adm-block">'
            + '<div class="adm-block__head">'
            + '<h3 class="adm-block__title">' + esc(T(key, zh))
            // ZH: v3.9 說明收進標題旁的 icon（擁有者裁定 2026-08-30）——
            //     三張小表各掛一段兩行說明，加起來比表格本身還長。
            // ZH: ⚠ 泡泡的 id 用 key 推出來（'tip-' + key）。三張表共用這支，
            //     寫死一個 id 的話畫面上會出現三個相同 id，
            //     而 aria-controls 只會指到第一個 —— 後兩顆 icon 點了打不開自己那張。
            + '<span class="tip">'
            + '<button type="button" class="tip__btn" aria-expanded="false"'
            + ' aria-controls="tip-' + esc(key) + '"'
            + ' aria-label="' + esc(T('tip_more', '這是什麼')) + '">i</button>'
            + '<span class="tip__body" id="tip-' + esc(key) + '" role="tooltip" hidden>'
            + esc(T(whyKey, whyZh)) + '</span>'
            + '</span>'
            + '</h3>'
            // ZH: 筆數緊跟著標題。原本靠 space-between 推到最右邊，
            //     離標題 1246px —— 那個數字是在講誰，完全看不出來。
            + '<span class="adm-block__n">' + esc(rows.length) + '</span>'
            + '<span class="topbar__spacer"></span>'
            + '</div>'
            + '<div class="adm-tablewrap adm-tablewrap--narrow">'
            + '<table class="adm-table"><thead><tr>'
            + cols.map(function (c) {
                return '<th' + (c[2] ? ' class="' + esc(c[2]) + '"' : '') + '>'
                    + esc(T(c[0], c[1])) + '</th>';
            }).join('')
            + '</tr></thead><tbody>'
            + shown.map(function (r) {
                return '<tr>' + r.map(function (cell) {
                    if (cell.pill) {
                        return '<td>' + (cell.t
                            ? '<span class="adm-pill adm-pill--temp">' + esc(cell.t) + '</span>'
                            : '<span class="footnote">—</span>') + '</td>';
                    }
                    return '<td' + (cell.cls ? ' class="' + esc(cell.cls) + '"' : '') + '>'
                        + esc(cell.t) + '</td>';
                }).join('') + '</tr>';
            }).join('')
            + '</tbody></table></div>'
            + (rows.length > shown.length
                ? '<p class="footnote">' + esc(T('pp_bx_more', '還有 {n} 筆。')
                    .replace('{n}', rows.length - shown.length)) + '</p>'
                : '')
            + '</section>';
    }

    // ZH: 兩個動作都慢（同步是 headless 登入廠商）。按下去就停用並改字，
    //     不然使用者會以為沒反應而一直按。
    var BX_BUSY = false;
    async function runBatch(btnId, path, okKey, okZh, fmt) {
        if (BX_BUSY) return;
        BX_BUSY = true;
        var b = $(btnId), was = b.textContent;
        b.disabled = true;
        b.textContent = T('pp_bx_running', '執行中…');
        say('bx-msg', '');
        try {
            var r = await api(path, { method: 'POST' });
            flash('bx-msg', fmt(T(okKey, okZh), r), 8000);
            await loadBatch();
        } catch (e) {
            say('bx-msg', e.message);
        } finally {
            BX_BUSY = false;
            b.disabled = false;
            b.textContent = was;
        }
    }

    async function importCsv() {
        var text = $('bx-csv').value;
        if (!text.trim()) { say('bx-csv-msg', T('pp_bx_csv_empty', '先貼上內容。')); return; }
        try {
            var r = await api('/external-ai/admin/import', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ csv: text }),
            });
            // ZH: 逐行的錯誤要**全部列出來**，不要只說「有 N 行失敗」——
            //     使用者得知道是哪幾行才改得動。
            var msg = T('pp_bx_csv_done', '新增 {c}、更新 {u}、略過 {s}。')
                .replace('{c}', r.created).replace('{u}', r.updated).replace('{s}', r.skipped);
            if ((r.errors || []).length) {
                say('bx-csv-msg', msg + '　' + r.errors.join('；'));
            } else {
                flash('bx-csv-msg', msg, 8000);
                $('bx-csv').value = '';
            }
            await loadBatch();
        } catch (e) { say('bx-csv-msg', e.message); }
    }

    var typing = null;
    $('q').addEventListener('input', function () {
        // ZH: 節流 —— 幾千人的清單每敲一個字就重畫會頓。
        clearTimeout(typing);
        typing = setTimeout(renderList, 120);
    });

    // ZH: 訊息裡的欄位名是**照後端實際回傳**寫的，不要用 `a || b || 0` 猜 ——
    //     猜錯的話畫面永遠顯示 0，而且看起來像「真的沒抓到」。
    //       sync()       → {status, total, created, updated}
    //       auto_match() → {matched_created, backfilled}
    $('bx-sync').addEventListener('click', function () {
        runBatch('bx-sync', '/external-ai/admin/sync-myai',
                 'pp_bx_synced', '抓到 {t} 個廠商帳號（新增 {c}、更新 {u}）。',
                 function (t, r) {
                     return t.replace('{t}', num(r.total)).replace('{c}', num(r.created))
                            .replace('{u}', num(r.updated));
                 });
    });
    $('bx-match').addEventListener('click', function () {
        // ZH: 「回填序號」是指綁定早就在、只是缺廠商的穩定鍵。
        //     跟「新配對」分開講 —— 兩者的意義完全不同。
        runBatch('bx-match', '/external-ai/admin/auto-match',
                 'pp_bx_matched', '新配對 {c} 筆，回填序號 {b} 筆。',
                 function (t, r) {
                     return t.replace('{c}', num(r.matched_created))
                            .replace('{b}', num(r.backfilled));
                 });
    });
    $('bx-import').addEventListener('click', importCsv);

    // ZH: 中性（非錯誤）的常駐訊息 —— say() 預設紅底，這支換成一般底。
    //     與 platform.js 的同名函式一致；搬「手動補齊」過來時一起帶的。
    function note(id, text) {
        say(id, text);
        var el = $(id);
        if (el) {
            el.classList.remove('inline-error');
            el.classList.add('inline-note');
        }
    }

    // ══════════════════════════════════════════════════════════════════
    // ZH: 手動補齊點數（v3.9；v4.2 從「平台設定」搬來 —— 擁有者裁定
    //     2026-09-02：它是對帳號的維運動作，跟同步/配對同一類）。
    // ══════════════════════════════════════════════════════════════════
    // ZH: 兩段式：預覽 → 確認。不可逆的操作先讓人看一眼再送出。
    //
    // ZH: 🔴 預覽的名單**不留在前端當成送出的依據**。按「確認補齊」時後端會
    //     重新同步、重新算一次差額。中間有人用掉點數的話，補的是**當下**的差額。
    //     把預覽結果送回去當名單的話，補的會是一份已經過期的數字。
    (function () {
        var PREVIEWED = null;      // ZH: 只用來決定按鈕要不要亮，不當送出的資料
        var TU_PAGE_SIZE = 10;     // ZH: 預覽名單 10 人一頁（擁有者裁定 2026-09-03）

        function btns() {
            $('tu-apply').hidden = !PREVIEWED;
            $('tu-cancel').hidden = !PREVIEWED;
            // ZH: 有預覽在畫面上時，再按一次是拿**現在的**餘額重算 ——
            //     字樣跟著改（預覽→重算），不然看起來像同一件事按兩次。
            $('tu-preview').textContent = PREVIEWED
                ? T('pf_topup_recalc', '重算') : T('pf_topup_preview', '預覽');
            // ZH: 刻意**不**把輸入框鎖起來 —— 鎖了的話下面那個 input 監聽器
            //     永遠不會觸發（打不了字就沒有 input 事件），等於死碼。
            //     改成「改了數字就讓預覽失效」，同樣防得住「看 A 的預覽、送出 B」。
        }

        function reset() {
            PREVIEWED = null;
            $('tu-result').innerHTML = '';
            say('tu-msg', '');
            btns();
        }

        function target() {
            var v = parseInt($('tu-target').value, 10);
            return (isFinite(v) && v > 0) ? v : null;
        }

        function renderPreview(r) {
            if (!r.count) {
                $('tu-result').innerHTML = '<p class="footnote">'
                    + esc(T('pf_topup_nobody', '沒有人低於這個點數，不需要補。')) + '</p>';
                return;
            }
            renderPreviewPage(r, 1);
            note('tu-msg', T('pf_topup_sum', '{n} 個帳號，合計 {p} 點。按「確認補齊」才會送出。')
                .replace('{n}', num(r.count)).replace('{p}', num(r.points)));
        }

        // ZH: 10 人一頁（擁有者裁定 2026-09-03：整班補點時名單太長）。
        //     只是**顯示**分頁 —— 送出的仍是整批（後端本來就重新算，見上面 🔴）。
        function renderPreviewPage(r, page) {
            var pages = Math.max(1, Math.ceil(r.rows.length / TU_PAGE_SIZE));
            page = Math.min(Math.max(1, page), pages);
            var slice = r.rows.slice((page - 1) * TU_PAGE_SIZE, page * TU_PAGE_SIZE);
            // ZH: .adm-tablewrap 是必要的（橫向捲動）—— 自己組光溜溜的 <table>，
            //     窄畫面會把整頁撐寬。與本頁其他表格同一套。
            $('tu-result').innerHTML =
                '<div class="adm-tablewrap"><table class="adm-table"><thead><tr>'
                + '<th>' + esc(T('pf_topup_who', '帳號')) + '</th>'
                + '<th class="num">' + esc(T('pf_topup_add', '要補')) + '</th>'
                + '</tr></thead><tbody>'
                + slice.map(function (x) {
                    return '<tr><td>' + esc(x.email) + '</td>'
                         + '<td class="num">' + num(x.points) + '</td></tr>';
                }).join('')
                + '</tbody></table></div>'
                + (pages > 1
                    ? '<div class="adm-inline tu-pager">'
                      + '<button class="btn btn--minor" type="button" id="tu-prev"'
                      + (page <= 1 ? ' disabled' : '') + '>'
                      + esc(T('pf_pg_prev', '上一頁')) + '</button>'
                      + '<span class="footnote">'
                      + esc(T('pf_pg_of', '第 {a} / {b} 頁').replace('{a}', page).replace('{b}', pages))
                      + '</span>'
                      + '<button class="btn btn--minor" type="button" id="tu-next"'
                      + (page >= pages ? ' disabled' : '') + '>'
                      + esc(T('pf_pg_next', '下一頁')) + '</button>'
                      + '</div>'
                    : '');
            if (pages > 1) {
                $('tu-prev').addEventListener('click', function () { renderPreviewPage(r, page - 1); });
                $('tu-next').addEventListener('click', function () { renderPreviewPage(r, page + 1); });
            }
        }

        async function preview() {
            var t = target();
            if (!t) { say('tu-msg', T('pf_topup_need', '請填一個大於 0 的點數。')); return; }
            say('tu-msg', '');
            try {
                var r = await api('/admin/myai/topup', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ target: t, dry_run: true }),
                });
                PREVIEWED = t;
                renderPreview(r);
                // ZH: 沒有人要補時不給「確認」鈕 —— 按了也是空操作，
                //     但會讓人以為真的做了什麼。
                if (!r.count) { PREVIEWED = null; }
                btns();
            } catch (e) {
                say('tu-msg', String(e.message || e));
            }
        }

        async function apply() {
            var t = target();
            if (!t) return;
            $('tu-apply').disabled = true;      // ZH: 防連點
            try {
                var r = await api('/admin/myai/topup', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ target: t, dry_run: false }),
                });
                reset();
                if (r.status === 'unknown') {
                    // ZH: 送出後失敗 —— 點數**可能已經轉出**。這一則不能用會消失的
                    //     提示，讀者必須看到並去廠商後台對帳。
                    say('tu-msg', T('pf_topup_unknown',
                        '送出了，但廠商沒有回報成功。點數可能已經轉出 —— '
                        + '請到廠商後台對帳，不要再按一次。'));
                } else {
                    flash('tu-msg', T('pf_topup_done', '補齊完成：{n} 個帳號、合計 {p} 點。')
                        .replace('{n}', num(r.count)).replace('{p}', num(r.points)), 8000);
                }
            } catch (e) {
                say('tu-msg', String(e.message || e));
            } finally {
                $('tu-apply').disabled = false;
            }
        }

        $('tu-preview').addEventListener('click', preview);
        $('tu-apply').addEventListener('click', apply);
        $('tu-cancel').addEventListener('click', reset);
        // ZH: 改了數字就讓預覽失效 —— 否則會發生「看著 A 的預覽、送出 B」。
        $('tu-target').addEventListener('input', function () {
            if (PREVIEWED) reset();
        });
        btns();
    })();

    // ZH: 檢視滑條要在讀資料**之前**接好 —— 帶 #myai 進來時,
    //     滑塊與 hidden 狀態要在第一次畫面出現時就是對的,
    //     不然使用者會看到平台那一邊閃一下才切過去。
    wireViewSeg();

    loadBatch();

    (async function () {
        try {
            ALL = await loadAll();
            renderList();
            renderDetail();
        } catch (e) {
            $('list').innerHTML = '<p class="footnote">'
                + esc(T('pp_fail', '讀不到使用者清單（{w}）。').replace('{w}', e.message)) + '</p>';
        }
    })();

    // ZH: v4.4 ESC 關閉：攔下 cancel 走同一條清理路（cancel 是同步事件，可靠）。
    //     close 事件也掛一份當保險 —— 面板環境實測不發它，正式瀏覽器會，
    //     兩邊都掛、閒置的那份無害（closeUserDialog 冪等）。
    $('user-dialog').addEventListener('cancel', function (ev) {
        ev.preventDefault();
        closeUserDialog();
    });
    // ZH: v4.4b 點遮罩也關（擁有者裁定 2026-09-03）。點在 ::backdrop 上時
    //     事件的 target 是 <dialog> 本身、座標落在內容框**外** ——
    //     用座標判斷，免得點到彈窗內距（padding）也被當成遮罩。
    $('user-dialog').addEventListener('click', function (ev) {
        if (ev.target !== this) return;
        var r = this.getBoundingClientRect();
        if (ev.clientX < r.left || ev.clientX > r.right
            || ev.clientY < r.top || ev.clientY > r.bottom) {
            closeUserDialog();
        }
    });
    $('user-dialog').addEventListener('close', function () {
        if (CURRENT) closeUserDialog();
    });

    document.addEventListener('prefs:langchanged', function () {
        renderList();
        renderDetail();
        renderBatch();
    });
})();
