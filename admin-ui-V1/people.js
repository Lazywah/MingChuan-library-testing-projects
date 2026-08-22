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
                    + '<td>' + esc(u.department || '—') + '</td>'
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
    function openTempForm() {
        var box = $('temp-box');
        box.hidden = false;
        box.innerHTML =
            '<div class="adm-card__title">' + esc(T('tmp_title', '建立臨時帳號')) + '</div>'
            + '<p class="footnote">' + esc(T('tmp_why',
                '給校外人士、長官視察或其他例外用途。到期會自動停用，帳號與紀錄都留著。')) + '</p>'
            + field('t-user', T('tmp_user', '帳號名稱'), '')
            + field('t-why', T('tmp_purpose', '用途（必填）'), '')
            + '<p class="footnote">' + esc(T('tmp_purpose_hint',
                '例如「教育部訪視 2026-09-03」。半年後看到一個沒有用途的帳號，沒有人敢刪它。')) + '</p>'
            + field('t-days', T('tmp_days', '有效天數'), '1', 'number')
            + '<p class="footnote">' + esc(T('tmp_days_hint', '1–90 天')) + '</p>'
            + field('t-email', T('tmp_email', 'Email（可留空，平台不會寄信）'), '', 'email')
            + '<div class="ds__actions">'
            + '<button class="btn btn--primary" type="button" id="t-go">'
            + esc(T('tmp_create', '建立')) + '</button>'
            + '<button class="btn btn--minor" type="button" id="t-cancel">'
            + esc(T('tmp_cancel', '取消')) + '</button>'
            + '</div>'
            + '<div class="inline-error" id="t-msg" hidden></div>';

        $('t-cancel').addEventListener('click', function () { box.hidden = true; });
        $('t-go').addEventListener('click', createTemp);
        $('t-user').focus();
    }

    async function createTemp() {
        var body = {
            username: $('t-user').value.trim(),
            purpose: $('t-why').value.trim(),
            days: parseInt($('t-days').value, 10) || 1,
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
        var box = $('temp-box');
        box.innerHTML =
            '<div class="adm-card__title">' + esc(T('tmp_done', '帳號建好了')) + '</div>'
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
            + '<div class="ds__actions">'
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
        $('t-close').addEventListener('click', function () { box.hidden = true; });
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

    function field(id, label, value, type) {
        return '<label class="field">'
            + '<span class="field__label" for="' + id + '">' + esc(label) + '</span>'
            + '<input class="field__input" id="' + id + '" type="' + (type || 'text') + '"'
            + ' value="' + esc(value == null ? '' : value) + '">'
            + '</label>';
    }


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
            + '<input class="field__input" id="x-days" type="number" min="1" max="90" value="7"'
            + ' aria-label="' + esc(T('tmp_ext_days', '再延幾天')) + '">'
            + '<button class="btn btn--minor" type="button" id="x-go">'
            + esc(T('tmp_ext_go', '延期')) + '</button>'
            + '</div>'
            + '<div class="inline-error" id="x-msg" hidden></div>'
            + '</section>';
    }


    function wireExtend(u) {
        $('x-go').addEventListener('click', async function () {
            var days = parseInt($('x-days').value, 10);
            try {
                var out = await api('/admin/users/' + encodeURIComponent(u.id) + '/extend', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ days: days }),
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


    // ── 基本資料：唯讀 → 解鎖 → 編輯 ────────────────────────────────────────
    //
    // ZH: 預設唯讀。按「編輯」要先輸入一次密碼，按「儲存」再輸入一次。
    //
    // ZH: 🔴 **這兩道確認擋的是誤觸與離開座位時被人動到，不是安全機制。**
    //     後端的 `PUT /admin/users/{id}` 本身不要求密碼（改它會弄壞舊版管理介面），
    //     所以拿到 token 的人仍然可以直接打 API。
    //     但密碼是真的向後端驗的（`POST /admin/verify`，它不發 token、
    //     也不會污染登入紀錄），不是畫面上比對一下而已。
    var EDIT_BASIC = false;

    function roText(u) {
        return '<div class="kv"><span class="kv__k">Email</span>'
            + '<span class="kv__v">' + esc(shownEmail(u)) + '</span></div>'
            + '<div class="kv"><span class="kv__k">' + esc(T('pp_c_dept', '學系')) + '</span>'
            + '<span class="kv__v">' + esc(u.department || '—') + '</span></div>'
            + '<div class="kv"><span class="kv__k">' + esc(T('pp_c_role', '角色')) + '</span>'
            + '<span class="kv__v">' + esc(T('role_' + u.role, u.role)) + '</span></div>';
    }

    function basicCard(u) {
        var head = '<section class="adm-card">'
            + '<div class="adm-card__title">' + esc(T('pp_basic', '基本資料')) + '</div>';

        if (!EDIT_BASIC) {
            return head
                + roText(u)
                + '<p class="footnote">' + esc(T('pp_ro_hint', '唯讀。要修改請按「編輯」。')) + '</p>'
                + '<div class="ds__actions">'
                + '<button class="btn btn--minor" type="button" id="b-edit">'
                + esc(T('pp_edit', '編輯')) + '</button>'
                + '</div>'
                // ZH: 解鎖用的密碼欄位。預設收著 —— 平常看資料的人不需要看到它。
                + '<div id="b-unlock" hidden>'
                + '<p class="footnote">' + esc(T('pp_unlock_why',
                    '確認是本人在操作，避免誤改或離開座位時被人動到。')) + '</p>'
                + field('b-pw', T('pp_unlock_title', '請再輸入一次你的密碼'), '', 'password')
                + '<div class="ds__actions">'
                + '<button class="btn btn--primary" type="button" id="b-unlock-go">'
                + esc(T('pp_unlock_go', '確認')) + '</button>'
                + '<button class="btn btn--minor" type="button" id="b-unlock-cancel">'
                + esc(T('pp_cancel', '取消變更')) + '</button>'
                + '</div>'
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
            + ['student', 'teacher', 'admin'].map(function (r) {
                return '<option value="' + r + '"' + (u.role === r ? ' selected' : '') + '>'
                    + esc(T('role_' + r, r)) + '</option>';
            }).join('')
            + '</select></label>'
            + field('f-pw', T('pp_new_pw', '新密碼'), '', 'password')
            + '<p class="footnote">' + esc(T('pp_pw_hint', '留空就不改密碼')) + '</p>'
            // ZH: 儲存前的第二次確認。與解鎖那次是**分開的兩個欄位**——
            //     共用一個的話，第一次輸入的密碼會一直留在 DOM 裡。
            + field('f-confirm', T('pp_confirm_save', '儲存前請再輸入一次密碼'), '', 'password')
            + '<div class="ds__actions">'
            + '<button class="btn btn--primary" type="button" id="save">'
            + esc(T('pp_save', '儲存')) + '</button>'
            + '<button class="btn btn--minor" type="button" id="b-cancel">'
            + esc(T('pp_cancel', '取消變更')) + '</button>'
            + '</div>'
            + '<div class="inline-error" id="save-msg" hidden></div>'
            + '</section>';
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

    function renderDetail() {
        var box = $('detail');
        if (!CURRENT) {
            box.innerHTML = '<p class="footnote">' + esc(T('pp_pick', '點一列看這個人的詳細資料。')) + '</p>';
            return;
        }
        var u = CURRENT;
        box.innerHTML =
            '<div class="adm-sec__head"><h2>'
            + esc(T('pp_detail', '{name} 的資料').replace('{name}', u.username)) + '</h2>'
            + '<span class="footnote mono">' + esc(u.id) + '</span></div>'

            + '<div class="adm-cols">'
            + basicCard(u)

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
            + '</div>'

            // 危險操作
            + '<section class="adm-card adm-card--danger">'
            + '<div class="adm-card__title">' + esc(T('pp_danger', '需要再確認的操作')) + '</div>'
            + '<p class="footnote">' + esc(T('pp_danger_why', '這幾項會影響使用者，所以要再輸入一次你的密碼。')) + '</p>'
            + field('f-adminpw', T('pp_admin_pw', '你的管理員密碼'), '', 'password')
            + '<div class="ds__actions">'
            + '<button class="btn btn--minor" type="button" id="toggle-active">'
            + esc(u.is_active ? T('pp_disable', '停用帳號') : T('pp_enable', '啟用帳號')) + '</button>'
            + '<button class="btn btn--minor" type="button" id="del">'
            + esc(T('pp_delete', '刪除帳號')) + '</button>'
            + '</div>'
            + '<div class="inline-error" id="danger-msg" hidden></div>'
            + '</section>';

        wireDetail(u);
        if (u.expires_at) wireExtend(u);
        loadQuota(u);
        loadLab(u);
        loadExtAi(u);
    }

    function say(id, text) {
        var el = $(id);
        el.textContent = text;
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
        // ── 唯讀時：只有「編輯」與解鎖表單 ──────────────────────────────
        if (!EDIT_BASIC) {
            $('b-edit').addEventListener('click', function () {
                $('b-unlock').hidden = false;
                $('b-edit').disabled = true;
                $('b-pw').focus();
            });
            $('b-unlock-cancel').addEventListener('click', function () {
                $('b-unlock').hidden = true;
                $('b-edit').disabled = false;
                $('b-pw').value = '';          // ZH: 密碼不留在 DOM 裡
                say('save-msg', '');
            });
            $('b-unlock-go').addEventListener('click', async function () {
                var pw = $('b-pw').value;
                if (!pw) { say('save-msg', T('pp_need_pw', '請先輸入你的管理員密碼。')); return; }
                if (!await verifyPassword(pw)) {
                    say('save-msg', T('pp_unlock_bad', '密碼不對。'));
                    return;
                }
                // ZH: 驗過就把它清掉。**不要留著等儲存時再用** ——
                //     那等於把密碼放在記憶體裡直到他關掉頁面，
                //     而且使用者的期待是「儲存時會再問一次」（他明講的）。
                $('b-pw').value = '';
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

        $('save').addEventListener('click', async function () {
            // ZH: 儲存前的第二次確認（使用者明確要求）。
            var pw2 = $('f-confirm').value;
            if (!pw2) { say('save-msg', T('pp_need_pw', '請先輸入你的管理員密碼。')); return; }
            if (!await verifyPassword(pw2)) {
                say('save-msg', T('pp_unlock_bad', '密碼不對。'));
                return;
            }
            $('f-confirm').value = '';

            var patch = {
                email: $('f-email').value.trim() || null,
                department: $('f-dept').value.trim() || null,
                role: $('f-role').value,
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
                Object.assign(u, { email: patch.email, department: patch.department, role: patch.role });
                $('f-pw').value = '';
                EDIT_BASIC = false;            // ZH: 存完收回唯讀
                renderList();
                renderDetail();
                flash('save-msg', T('pp_saved', '已儲存'));
            } catch (e) {
                say('save-msg', T('pp_save_fail', '存不起來（{w}）').replace('{w}', e.message));
            }
        });

        wireCommon(u);
    }

    // ZH: 兩種模式都有的部分（危險操作那一區不受唯讀／編輯影響）。
    function wireCommon(u) {
        $('toggle-active').addEventListener('click', async function () {
            try {
                await api('/admin/users/' + encodeURIComponent(u.id), {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ is_active: u.is_active ? 0 : 1 }),
                });
                u.is_active = u.is_active ? 0 : 1;
                renderList();
                renderDetail();
            } catch (e) {
                say('danger-msg', e.message);
            }
        });

        $('del').addEventListener('click', async function () {
            var pw = $('f-adminpw').value;
            if (!pw) { say('danger-msg', T('pp_need_pw', '請先輸入你的管理員密碼。')); return; }
            if (!confirm(T('pp_delete_confirm', '要刪除「{n}」嗎？').replace('{n}', u.username))) return;
            try {
                await api('/admin/users/' + encodeURIComponent(u.id) + '/delete', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ admin_password: pw }),
                });
                ALL = ALL.filter(function (x) { return x.id !== u.id; });
                CURRENT = null;
                renderList();
                renderDetail();
            } catch (e) {
                say('danger-msg', e.message);
            }
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
                    + '<button class="btn btn--minor" type="button" id="e-unbind">'
                    + esc(T('pp_ext_unbind', '解除綁定')) + '</button>')
            + '</div>'
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
    $('new-temp').addEventListener('click', openTempForm);

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
                'pp_bx_staff_why', '只是提示，不會自動改角色——網域不等於身分，改權限要人決定。',
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
            + '<h3 class="adm-block__title">' + esc(T(key, zh)) + '</h3>'
            // ZH: 筆數緊跟著標題。原本靠 space-between 推到最右邊，
            //     離標題 1246px —— 那個數字是在講誰，完全看不出來。
            + '<span class="adm-block__n">' + esc(rows.length) + '</span>'
            + '<span class="topbar__spacer"></span>'
            + '</div>'
            + '<p class="footnote">' + esc(T(whyKey, whyZh)) + '</p>'
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

    document.addEventListener('prefs:langchanged', function () {
        renderList();
        renderDetail();
        renderBatch();
    });
})();
