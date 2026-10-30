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

    // ══════════════════════════════════════════════════════════════════
    // ZH: v4.42 排序與分頁（擁有者 2026-10-30：20 人一頁、依數字大小、admin 最後）
    // ══════════════════════════════════════════════════════════════════
    // ZH: 帳號名幾乎都是學號／員編。用字串排的話 "9600885" 會排在 "12361114"
    //     後面（'9' > '1'），看起來像亂的 —— 所以**數字當數字比**。
    // ZH: 不是數字的（admin 這種）一律排最後，彼此再照字母 —— 擁有者只點名 admin，
    //     但用「不是數字就排後面」這個判準，日後多一個 root/service 也不會跑到中間。
    var LIST_PER_PAGE = 20;
    var LIST_PAGE = 0;

    function userSortKey(u) {
        var name = String(u.username || '');
        // ZH: ⚠ parseInt("12a") 會給 12 —— 要**整串都是數字**才算數字帳號。
        return /^\d+$/.test(name) ? { num: true, v: Number(name) } : { num: false, v: name.toLowerCase() };
    }

    function sortUsers(rows) {
        return rows.slice().sort(function (a, b) {
            var ka = userSortKey(a), kb = userSortKey(b);
            if (ka.num !== kb.num) return ka.num ? -1 : 1;   // ZH: 數字的在前
            if (ka.v === kb.v) return 0;
            return ka.v < kb.v ? -1 : 1;
        });
    }

    // ZH: v4.45 分頁器改用共用的 AdminPager（admin-chrome.js）——
    //     原本這裡、補齊預覽、回收預覽、reports.js 各抄一份 `.tu-pager`，只差 id 前綴。
    //     id 前綴維持 pp（按鈕仍是 #pp-prev / #pp-next）。
    // ZH: ⚠ LIST_PAGE 是**從 0 算**的（slice 用），AdminPager 要的是畫面上的頁碼（從 1 算）——
    //     進出時各換算一次，不要把兩種混在同一個變數裡。
    function listPagerOpts(total, focus) {
        return {
            id: 'pp', page: LIST_PAGE + 1, perPage: LIST_PER_PAGE, total: total, focus: focus,
            onGo: function (p, which) { LIST_PAGE = p - 1; renderList(which); },
        };
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

    // ZH: `focus`（'prev' / 'next'）只有分頁器換頁時會給 —— 重畫後把焦點放回同一顆
    //     （到頭變灰就放另一顆），用鍵盤的人不必從頁首重新 Tab。其他呼叫端不給。
    function renderList(focus) {
        var q = $('q').value.trim().toLowerCase();
        var rows = sortUsers(ALL.filter(function (u) { return matches(u, q); }));
        // ZH: 刪了人、或搜尋縮短清單時，目前這一頁可能已經不存在 —— 退到最後一頁。
        var pages = Math.max(1, Math.ceil(rows.length / LIST_PER_PAGE));
        if (LIST_PAGE > pages - 1) LIST_PAGE = pages - 1;
        var slice = rows.slice(LIST_PAGE * LIST_PER_PAGE, (LIST_PAGE + 1) * LIST_PER_PAGE);

        $('count').textContent = q
            ? T('pp_count_filtered', '{n} / {t} 人')
                .replace('{n}', rows.length).replace('{t}', ALL.length)
            : T('pp_count', '{n} 人').replace('{n}', ALL.length);

        if (!rows.length) {
            $('list').innerHTML = '<p class="footnote">' + esc(T('pp_none', '找不到符合的人。')) + '</p>';
            return;
        }

        // ZH: v4.11 拿掉「學系」欄（擁有者裁定 2026-09-11）——
        //     組織改在點開的詳情裡看（見 orgLine）。清單這一條是用來
        //     **找人**的，欄位越少越好找；而學系對職員一律是空的，
        //     那一欄有一半的列是「—」。
        // ZH: v4.45 第二欄（Email）是 grow 欄（admin.css 的「表格欄寬」）：Email 是唯一長短差很多的欄，
        //     讓它吃掉剩下的寬度，其他欄只佔內容需要的寬度 —— 不再每欄平均拉開。
        var head = [
            ['pp_c_user', '帳號'], ['', 'Email', 'grow'],
            ['pp_c_role', '角色'], ['pp_c_state', '狀態'], ['pp_c_source', '來源'],
            ['pp_c_seen', '最後登入'],
        ];

        var pg = listPagerOpts(rows.length, focus);
        $('list').innerHTML =
            '<div class="adm-tablewrap"><table class="adm-table"><thead><tr>'
            + head.map(function (h) {
                return '<th' + (h[2] ? ' class="' + h[2] + '"' : '') + '>' + esc(T(h[0], h[1])) + '</th>';
            }).join('')
            + '</tr></thead><tbody>'
            + slice.map(function (u) {
                return '<tr class="is-clickable' + (CURRENT && CURRENT.id === u.id ? ' is-picked' : '')
                    + '" data-id="' + esc(u.id) + '" tabindex="0">'
                    + '<td>' + esc(u.username) + '</td>'
                    + '<td class="grow">' + esc(shownEmail(u)) + '</td>'
                    + '<td>' + esc(T('role_' + u.role, u.role)) + '</td>'
                    + '<td>' + stateCell(u) + '</td>'
                    + '<td>' + esc(u.auth_source || '—') + '</td>'
                    + '<td>' + esc(u.last_login_time ? TW.when(u.last_login_time) : '—') + '</td>'
                    + '</tr>';
            }).join('')
            + '</tbody></table></div>'
            + AdminPager.html(pg);
        AdminPager.wire(pg);

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
                    ' min="' + twDay(0) + '"')
            + '<p class="footnote">' + esc(T('tmp_expires_hint',
                '選到哪一天，帳號就用到那天結束（台灣時間）。')) + '</p>'
            // ZH: v4.20 永久有效（擁有者 2026-09-21）—— 勾了就不設到期日，
            //     與一般帳號同形。用途仍然必填：永久的帳號更需要有人說得出它為什麼在。
            // ZH: v4.45 拿掉 inline 的 margin —— 間距交給容器（.adm-inline 本身的上外距、
            //     admin.css 的 footnote 規則），各處自帶外距正是間距忽大忽小的來源。
            + '<label class="adm-inline">'
            +   '<input type="checkbox" id="t-forever"> '
            +   '<span>' + esc(T('tmp_forever', '永久有效（不設到期日，與一般帳號一樣）')) + '</span>'
            + '</label>'
            + field('t-email', T('tmp_email', 'Email（可留空，平台不會寄信）'), '', 'email')
            // ZH: v4.20 密碼可以自己指定（擁有者 2026-09-21）——「長官短暫使用」那種場合
            //     可以口頭交代一組好記的，不必抄一串亂碼。留空就照舊隨機。
            + field('t-pw', T('tmp_pw_set', '密碼（留空＝自動產生）'), '')
            + '<p class="footnote">' + esc(T('tmp_pw_hint',
                '要自己指定的話 8~20 個字元（MYAI 廠商的規則）。同一組密碼平台與 MYAI 都能用。')) + '</p>'
            // ZH: v4.20 MYAI 開通。**預設不勾** —— 會在廠商端真的建一個帳號，
            //     那不是可以隨手做的事（帳號刪不掉、點數也跟著走）。
            + '<label class="adm-inline">'
            +   '<input type="checkbox" id="t-myai"> '
            +   '<span>' + esc(T('tmp_myai', '同時開通 MYAI 帳號（需要填 Email；密碼與上面同一組）')) + '</span>'
            + '</label>'
            + '<p class="footnote">' + esc(T('tmp_myai_hint',
                '不勾的話這個帳號進得了平台，但沒有 MYAI 額度 —— 密碼登入的帳號不會自動開通。')) + '</p>'
            // ZH: v4.45 對話框頁腳一律靠右、確認鍵在最右邊（計畫第 3 節「對話框」）：
            //     ［取消］［下一步］［確認］。原本這一頁有的是確認在前、有的是取消在前。
            + '<div class="adm-inline rmod__foot rmod__foot--end">'
            + '<button class="btn btn--minor" type="button" id="t-cancel">'
            + esc(T('tmp_cancel', '取消')) + '</button>'
            + '<button class="btn btn--primary" type="button" id="t-go">'
            + esc(T('tmp_create', '建立')) + '</button>'
            + '</div>'
            + '<div class="inline-error" id="t-msg" hidden></div>';

        dlg.showModal();
        $('t-cancel').addEventListener('click', function () { dlg.close(); });
        $('t-go').addEventListener('click', createTemp);
        // ZH: 勾了永久就把日期欄灰掉 —— 兩個都填是矛盾的輸入，
        //     後端會擋（422），但在這裡就讓它按不到比較好。
        $('t-forever').addEventListener('change', function () {
            var d = $('t-expires');
            d.disabled = this.checked;
            d.style.opacity = this.checked ? '.5' : '';
        });
        $('t-user').focus();
    }

    async function createTemp() {
        var forever = $('t-forever') && $('t-forever').checked;
        var body = {
            username: $('t-user').value.trim(),
            purpose: $('t-why').value.trim(),
        };
        // ZH: 永久就**完全不送** expires_on（送空字串會被當成填了但格式錯）。
        // ZH: 送日期字串本身，**不在前端換算成天數**。
        //     換算會因為時區與一天中的時刻而差一天，而且差了不會報錯。
        if (forever) body.never_expires = true;
        else body.expires_on = $('t-expires').value;
        var em = $('t-email').value.trim();
        if (em) body.email = em;
        var pw = $('t-pw') ? $('t-pw').value.trim() : '';
        if (pw) body.password = pw;
        if ($('t-myai') && $('t-myai').checked) body.provision_myai = true;

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

    // ZH: v4.20 MYAI 開通結果的一句話。狀態來自 myai_sync.provision_user。
    function myaiText(m) {
        var s = m && m.status;
        if (s === 'created') return T('tmp_myai_created', '已開通（密碼與上面同一組）');
        if (s === 'linked_only') return T('tmp_myai_linked',
            '廠商端本來就有這個信箱的帳號，已綁定 —— ⚠ MYAI 的密碼不是上面這一組');
        if (s === 'bound') return T('tmp_myai_bound', '這個人本來就綁好了');
        if (s === 'disabled') return T('tmp_myai_disabled',
            '沒有開通：平台設定的「MYAI 首次登入自動建號」是關的');
        if (s === 'failed') return T('tmp_myai_failed', '開通失敗') + '（' + esc(m.error || '') + '）';
        return T('tmp_myai_skipped', '沒有開通') + '（' + esc((m && m.reason) || s || '') + '）';
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
            // ZH: v4.20 永久帳號沒有到期日 —— 明寫「永久有效」，不要留一格空白
            //     （空白看起來像資料沒讀到，管理者會以為建錯了）。
            + '<div class="kv"><span class="kv__k">' + esc(T('tmp_expires', '到期')) + '</span>'
            + '<span class="kv__v">' + esc(out.expires_at
                ? TW.dateTime(out.expires_at)
                : T('tmp_forever_value', '永久有效（不會到期）')) + '</span></div>'
            // ZH: v4.20 MYAI 開通結果 —— 成功與否都要講，而且要講**密碼是不是同一組**。
            //     linked_only 是最容易誤會的：帳號綁上了，但那是廠商端本來就有的帳號，
            //     密碼不是我們給的這一組，照著交出去對方會登不進 MYAI。
            + (out.myai ? '<div class="kv"><span class="kv__k">MYAI</span>'
                + '<span class="kv__v">' + esc(myaiText(out.myai)) + '</span></div>' : '')
            + '<div class="adm-inline rmod__foot rmod__foot--end">'
            + '<button class="btn btn--minor" type="button" id="t-close">'
            + esc(T('tmp_close', '知道了')) + '</button>'
            + '<button class="btn btn--primary" type="button" id="t-copy">'
            + esc(T('tmp_copy', '複製帳號與密碼')) + '</button>'
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
        if (!u.expires_at) {
            // ZH: v4.42 永久的臨時帳號**不再標**（擁有者 2026-10-30）：
            //     只有真的有到期日的才顯示到期資訊。v4.20 加這顆標籤的理由是
            //     「不標就跟一般帳號長得一樣」，但永久帳號本來就等同一般帳號，
            //     而用途仍然查得到（詳細面板的臨時帳號卡片）。
            return out;
        }

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



    // ZH: 臨時帳號的延期。放在詳細面板裡而不是清單上 ——
    //     延期是「決定一件事」不是「掃一眼」，需要先看到用途與現在的到期日。
    //
    // ZH: 🔴 這個功能存在的理由很具體：使用者送了訓練、帳號在跑完之前到期。
    //     （任務本身照樣跑完 —— 派工不檢查帳號狀態 —— 但他登不進來拿結果。）
    function tempCard(u) {
        // ZH: v4.42 改成永久之後 expires_at 是 null —— Date.parse(null) 是 NaN，
        //     NaN <= now 為 false，所以不會誤標「已到期」；寫出來是因為下面還要用它。
        var forever = !u.expires_at;
        var gone = !forever && Date.parse(u.expires_at) <= Date.now();
        return '<section class="adm-card adm-card--temp pp-blk">'
            + blkHead(T('tmp_ext_title', '臨時帳號'))
            + '<div class="kv"><span class="kv__k">' + esc(T('tmp_ext_purpose', '用途')) + '</span>'
            + '<span class="kv__v">' + esc(u.temp_purpose || '—') + '</span></div>'
            + '<div class="kv"><span class="kv__k">' + esc(T('tmp_ext_until', '到期')) + '</span>'
            + '<span class="kv__v">'
            + esc(forever ? T('tmp_ext_never', '不到期（永久有效）') : TW.dateTime(u.expires_at))
            + (gone ? '　<span class="adm-pill adm-pill--expired">'
                + esc(T('tmp_expired', '已到期')) + '</span>' : '')
            + '</span></div>'
            + '<div class="adm-inline">'
            + '<input class="field__input" id="x-expires" type="date"'
            + ' min="' + twDay(0) + '"'
            + ' aria-label="' + esc(T('tmp_ext_until_new', '新的到期日')) + '">'
            + '<button class="btn btn--minor" type="button" id="x-go">'
            + esc(T('tmp_ext_go', '延期')) + '</button>'
            + '</div>'
            // ZH: v4.42 延期也可以改成永久（擁有者 2026-10-30）——
            //     以前只能選日期，想讓一個臨時帳號轉正只好設一個很遠的日子，
            //     而那種帳號到期時沒有人記得它為什麼在。
            // ZH: v4.45 pp-check：整個 label 可點，給到 44px 高（admin.css「小控制項的可點範圍」）。
            + '<label class="adm-inline pp-check">'
            +   '<input type="checkbox" id="x-forever"> '
            +   '<span>' + esc(T('tmp_ext_forever', '改成永久有效（不設到期日）')) + '</span>'
            + '</label>'
            + '<div class="inline-error" id="x-msg" hidden></div>'
            + '</section>';
    }


    // ZH: v4.42 延期的日期欄**留空**（擁有者 2026-10-30）。
    //     以前預填目前的到期日（過期就拉到今天），但那看起來像「已經幫你選好了」——
    //     按下去才發現延到今天就結束。留空＝一定要自己挑一天，誤會不了。
    //     目前的到期日就在上面那一行（「到期 …」），要參考看得到。


    function wireExtend(u) {
        // ZH: 勾了永久就不該再挑日期（後端兩個都給會 422）——把日期欄鎖起來並清空。
        $('x-forever').addEventListener('change', function () {
            var on = $('x-forever').checked;
            $('x-expires').disabled = on;
            if (on) $('x-expires').value = '';
        });
        $('x-go').addEventListener('click', function () {
            var forever = $('x-forever').checked;
            var expiresOn = forever ? '' : $('x-expires').value;
            if (!forever && !expiresOn) {
                say('x-msg', T('tmp_ext_need', '請選一個到期日，或勾「改成永久有效」。'));
                return;
            }
            say('x-msg', '');
            // ZH: v4.10b 延長＝把一個可能已經到期關掉的帳號重新打開
            //     （後端會把 is_active 設回 1）—— 算對帳號的操作，要確認。
            targetConfirm(T('tmp_ext_title', '確認延長'),
                          forever ? T('tmp_ext_forever_warn',
                              '這個帳號將**不再到期**，與一般帳號一樣。') : null,
                          u.username,
                          async function (name) { await sendExtend(u, expiresOn, name, forever); });
        });
    }

    async function sendExtend(u, expiresOn, name, forever) {
        {
            try {
                var out = await api('/admin/users/' + encodeURIComponent(u.id) + '/extend', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(forever
                        ? { never_expires: true, confirm_username: name }
                        : { expires_on: expiresOn, confirm_username: name }),
                });
                // ZH: 後端會順手把 is_active 設回 1（排程可能已經停用它），
                //     所以本地的兩個欄位都要跟著更新，否則清單還顯示舊狀態。
                u.expires_at = out.expires_at;
                u.is_active = 1;
                renderList();
                renderDetail();
                // ZH: 改成永久時 expires_at 是 null —— 丟給 TW.dateTime 會變成空白，
                //     看起來像「延到了，但不知道延到哪天」。兩種結果分開講。
                flash('x-msg', out.expires_at
                    ? T('tmp_ext_done', '已延到 {d}').replace('{d}', TW.dateTime(out.expires_at))
                    : T('tmp_ext_done_forever', '已改成永久有效（不再到期）。'));
            } catch (e) {
                // ZH: 丟回 targetConfirm 顯示在彈窗裡（彈窗不關，不用重打）。
                throw new Error(T('tmp_ext_fail', '延期失敗（{w}）').replace('{w}', e.message));
            }
        }
    }


    // ── 基本資料：唯讀 → 編輯 → 儲存前確認 ───────────────────────────────
    //
    // ZH: 預設唯讀。按「編輯」直接進編輯；**只在儲存前**確認一次
    //     （v4.3b 擁有者裁定 2026-09-03：原本進編輯還要先驗一次，兩道太煩——
    //     真正要擋的是「誤存」，看與改欄位本身不需要門）。
    // ZH: v4.10b 確認的內容從「管理者密碼」改成「打出目標帳號」——
    //     SSO 管理者沒有密碼可以輸入（見 targetConfirm）。
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
    // ZH: v4.11 這個人的組織，一行講完（擁有者需求 2026-09-11）。
    //
    // ZH: 顯示哪些**照身分走**，與初次設定問的那一欄一致
    //     （crud.ONBOARDING_FIELDS）：學生／老師看學系，職員／管理員看單位。
    //     兩邊都有值就都顯示 —— 老師同時掛學系與行政單位是真實情況
    //     （實測 8000036 兩邊都有），硬挑一個會把另一個藏起來。
    //
    // ZH: 學院是**推**出來的（後端由 department 外連 org_departments），
    //     不是使用者身上的欄位；所以改對照表這裡就立刻跟著變。
    //
    // ZH: 空的就回空字串，由呼叫端決定要不要顯示那一行 ——
    //     不要回「—」，那會讓沒有組織的人多出一行沒有內容的字。
    function orgLine(u) {
        var parts = [];
        var col = orgName(u.college, u.college_en);
        var dep = orgName(u.department, u.department_en);
        if (col) parts.push(col);
        if (dep) parts.push(dep);
        // ZH: 單位刻意不做英文（org_units 的英文名只有一半，
        //     做了會讓同一行一半中文一半英文 —— 與「數據」那頁同一個判斷）。
        if (u.unit) parts.push(u.unit);
        var line = parts.join(' / ');
        var camp = (u.campuses || []).join('、');
        if (camp) line = line ? (line + '（' + camp + '）') : camp;
        return line;
    }

    // ══════════════════════════════════════════════════════════════════
    // ZH: v4.45 個人對話框照**使用頻率**重排（版面整理計畫第 4 節「帳號」）：
    //       名片（含正在生效的授權／加碼藥丸）
    //       → 外部 AI（加點、回收點數在前；編輯綁定、解除綁定收進「更多▾」，解除排最底、紅字）
    //       → 基本資料 → 臨時帳號（有才出現）
    //       → 「較少用」收合區：開放一次修改、磁碟額外授與、程式實驗室、UUID
    // ZH: 原本是六張同樣份量的卡排成兩欄，一打開 15–21 個控制項，
    //     最醒目的 primary 卻是一年用幾次的「開放一次修改」。
    // ZH: 版面從 .adm-cols 的卡片格改成**單欄一疊**，區塊之間只靠細線分段（.pp-stack）——
    //     兩欄的卡高度參差、底邊對不齊，那正是「亂」的一部分。
    //     區塊仍掛 .adm-card：勾選框等既有樣式掛在它底下（.adm-card .field--check…），
    //     外框則由 .rmod--person .pp-blk 拿掉。
    // ══════════════════════════════════════════════════════════════════

    // ZH: 區塊標題列：與頁面上的區塊同一套 .adm-head（左＝標題、右＝動作），用 h3。
    //     `doHtml` 是呼叫端組好的按鈕字串（裡面的文字呼叫端自己 esc）。
    function blkHead(title, doHtml) {
        return '<div class="adm-head"><div class="adm-head__what">'
            + '<h3 class="adm-head__title">' + esc(title) + '</h3></div>'
            + (doHtml ? '<div class="adm-head__do">' + doHtml + '</div>' : '')
            + '</div>';
    }

    // ZH: 名片上「正在生效」的藥丸 —— 授權與加碼收進「較少用」之後，
    //     **收起來不等於看不到它生效了**：狀態留在名片上，表單才收起來。
    //     兩格各自由 loadUnlock / loadQuota 填（非同步，誰先回來誰先畫）。
    var LIVE = { unl: 0, q: 0 };
    var RARE = null;              // ZH: 「較少用」收合區的控制物件（AdminFold.wire 回傳）

    // ZH: 🔴 `slot` 要由呼叫端在 **await 之前**就抓好（元素，不是 id）。
    //     載入是非同步的：資料回來時對話框可能已經換人或重畫過，
    //     這時再用 id 去找，會把上一個人的狀態寫到下一個人的名片上。
    //     抓好的元素若已經不在畫面上（isConnected 為 false），就代表這筆結果過期了，直接丟掉。
    function setLive(slot, kind, n, html) {
        if (!slot || !slot.isConnected) return;
        LIVE[kind] = n;
        slot.innerHTML = n ? html : '';
        slot.hidden = !n;
        // ZH: 收合區標題上的數字＝生效中的項目數。0 就不顯示（空字串會讓藥丸藏起來）。
        var total = LIVE.unl + LIVE.q;
        if (RARE) {
            RARE.setCount(total ? T('dz_pp_rare_live', '{n} 項生效中').replace('{n}', total) : '');
        }
    }

    function pcardHtml(u) {
        // ZH: v4.45「已停用」改用 adm-pill--disabled（--warn-soft 的警示色）—— 與清單那一格同一個顏色。
        //     原本這裡掛的是 adm-pill--temp（--accent-soft，淺黃），跟「臨時帳號」那顆一模一樣，
        //     於是停用的帳號在對話框裡看起來像臨時帳號。
        var pills = '<span class="adm-pill">' + esc(T('role_' + u.role, u.role)) + '</span>'
            + (u.is_admin ? '<span class="adm-pill">'
                + esc(T('pp_c_is_admin', '管理權限')) + '</span>' : '')
            + (u.expires_at ? '<span class="adm-pill adm-pill--temp">'
                + esc(T('pp_pill_temp', '臨時帳號')) + '</span>' : '')
            + (!u.is_active ? '<span class="adm-pill adm-pill--disabled">'
                + esc(T('pf_org_off', '停用')) + '</span>' : '')
            // ZH: 兩個空槽，等 loadUnlock / loadQuota 回來再填（見 setLive）。
            + '<span id="pc-live-unl" hidden></span><span id="pc-live-q" hidden></span>';
        // ZH: v4.11 組織從 meta 那一行**搬出來自成一行** —— 它現在可能很長
        //     （學院／學系／單位＋校區），跟來源、最後登入擠在一起會讀不出來。
        var meta = [];
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
            + '<div class="pcard__line">' + esc(T('pp_org', '組織')) + '：'
            + esc(orgLine(u) || T('pp_org_none', '—（未設定）')) + '</div>'
            + '<div class="pcard__line">' + esc(meta.join(' · ')) + '</div>'
            // ZH: v4.45 UUID 搬進「較少用」收合區 —— 排查問題時才需要它。
            + '</div>'
            // ZH: v4.4b 停用/刪除搬到名片右側（擁有者裁定 2026-09-03）——
            //     確認在按下去之後用小彈窗問（v4.10 起是打出目標帳號，
            //     見 targetConfirm），所以這裡只是兩顆入口鈕。
            // ZH: v4.45 刪除帳號**留在原位**（擁有者待決事項 4 的 A 案），
            //     改成紅字的輕量按鈕：位置不變、仍要打帳號確認，只是不再跟停用一樣重。
            + '<div class="pcard__acts">'
            + '<button class="btn btn--minor" type="button" id="toggle-active">'
            + esc(u.is_active ? T('pp_disable', '停用帳號') : T('pp_enable', '啟用帳號')) + '</button>'
            + '<button class="btn--quiet btn--danger" type="button" id="del">'
            + esc(T('pp_delete', '刪除帳號')) + '</button>'
            + '</div></div>';
    }

    function basicCard(u) {
        // ZH: v4.45 「編輯」放進標題列右半（與頁面上的區塊同一個位置）；
        //     進入編輯時不另寫一句說明，改由 renderDetail 掛「編輯中」標示（AdminEditMark）。
        var open = '<section class="adm-card pp-blk" id="basic-box">';

        if (!EDIT_BASIC) {
            // ZH: v4.4 身分資訊都在上面的名片頭 —— 這張卡只剩「編輯」入口，
            //     重複列一次只會讓彈窗更長。
            return open
                + blkHead(T('pp_basic', '基本資料'),
                    '<button class="btn btn--minor" type="button" id="b-edit">'
                    + esc(T('pp_edit', '編輯')) + '</button>')
                + '<p class="footnote">' + esc(T('pp_ro_hint2',
                    'Email、角色、學系、密碼與管理權限都在這裡改。')) + '</p>'
                + '<div class="inline-error" id="save-msg" hidden></div>'
                + '</section>';
        }

        return open + blkHead(T('pp_basic', '基本資料'))
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
            // ZH: v4.10b 確認改在按「儲存」後用小彈窗問（打出目標帳號，
            //     見 targetConfirm），表單裡不擺確認欄。
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
    // ZH: v4.10 破壞性操作的確認彈窗（擁有者裁定 2026-09-11）。
    //
    // ZH: 前身是「再輸入一次管理者密碼」（v4.4b）。那個設計假設每個管理者
    //     都有一組自己知道的密碼 —— 但學校用 SSO，SSO 帳號的密碼是建號時
    //     隨機產生、明文當場丟掉的，**在世界上已經不存在**。
    //     2026-09-11 盤點：四個管理者裡三個是 SSO 帳號，他們永遠通不過。
    //
    // ZH: 改成「把要操作的那個帳號打出來」。這是**防手殘不是防攻擊** ——
    //     帳號不是秘密。它擋的是「點錯一列」，而那正是刪錯人的實際成因。
    //
    // ZH: 🔴 打的是**目標**帳號，不是自己的員編：自己的員編每次都一樣，
    //     第三次就變肌肉記憶等於沒有；打目標才擋得住「我以為我點的是別人」，
    //     而且後端驗得了（見 admin._require_target_confirm）。
    //
    // ZH: `run(value)` 負責動作，丟錯就顯示在彈窗裡、彈窗不關；成功才關。
    // ══════════════════════════════════════════════════════════════════
    // ZH: `label` 可選 —— 批次操作確認的是**操作者自己**，欄位得這樣寫，
    //     否則畫面會叫他去打一個不存在的「目標帳號」。
    function targetConfirm(title, hint, expect, run, label) {
        var dlg = $('pw-dialog');
        dlg.innerHTML =
            '<h2 class="rmod__title">' + esc(title) + '</h2>'
            + (hint ? '<p class="footnote">' + esc(hint) + '</p>' : '')
            + '<p class="footnote">'
            + esc(T('pp_confirm_type', '請輸入「{n}」以確認。').replace('{n}', expect))
            + '</p>'
            + field('pwc-in', label || T('pp_confirm_label', '帳號'), '', 'text')
            // ZH: v4.45 頁腳靠右、確認在最右邊（理由見 openTempForm）。
            + '<div class="adm-inline rmod__foot rmod__foot--end">'
            + '<button class="btn btn--minor" type="button" id="pwc-cancel">'
            + esc(T('tmp_cancel', '取消')) + '</button>'
            + '<button class="btn btn--primary" type="button" id="pwc-go">'
            + esc(T('pp_pwc_go', '確認')) + '</button>'
            + '</div>'
            + '<div class="inline-error" id="pwc-msg" hidden></div>';
        dlg.showModal();
        $('pwc-in').focus();
        $('pwc-cancel').addEventListener('click', function () { dlg.close(); });
        async function go() {
            var pw = $('pwc-in').value;
            // ZH: 前端先比一次只是省一趟往返 —— **後端才是判準**
            //     （前端擋得掉的東西，用 curl 一樣送得出來）。
            // ZH: 🔴 `expect` 是空的時候**不要在前端比**：那代表我們還不知道
            //     該打什麼（例如 /auth/me 還沒回來），此時本地比對只會
            //     把使用者鎖在一個永遠打不對的欄位裡。交給後端講原因。
            if (expect && pw.trim().toLowerCase() !== String(expect).trim().toLowerCase()) {
                say('pwc-msg', T('pp_confirm_bad', '打的帳號跟要操作的不一樣。'));
                return;
            }
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
        // ZH: 按 Enter = 確認 —— 打完還要移滑鼠去按鈕很煩。
        $('pwc-in').addEventListener('keydown', function (ev) {
            if (ev.key === 'Enter') { ev.preventDefault(); go(); }
        });
    }

    // ZH: v4.10 `verifyPassword()` 已移除 —— 它唯一的用途是把管理者輸入的
    //     密碼送去 `/admin/verify`，而確認方式已改成「打出目標帳號」
    //     （見 targetConfirm）。後端 `/admin/verify` 端點仍在，
    //     但前端已經沒有任何地方呼叫它。

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

            // ZH: v4.45 單欄一疊、照使用頻率（見 blkHead 上面那段）。
            + '<div class="pp-stack">'

            // ZH: 外部 AI 的綁定與消耗。放在這裡而不是「數據」那一頁 ——
            //     那一頁是看趨勢的，要查某一個人就該在人這一頁查完。
            // ZH: v4.4d 左半是綁定資訊、右半是消耗統計（extRo 的 .ext-cols）。
            // ZH: v4.45 排到第一個 —— 加點／回收點數是這個對話框最常做的事。
            + '<section class="adm-card pp-blk" id="ext-box">'
            + blkHead(T('pp_ext', '外部 AI（MYAI）'))
            + '<span class="skeleton skeleton--line"></span></section>'

            + basicCard(u)

            // ZH: 只有臨時帳號才出現這張卡。一般帳號看到一個「延期」欄位
            //     只會困惑（他沒有到期日可以延）。
            + (u.expires_at ? tempCard(u) : '')

            // ZH: v4.45 很少用的三樣收進「較少用」（擁有者已接受的做法：CSV 匯入就是這樣收的）。
            //     內容照樣一打開對話框就載入 —— 名片上的「生效中」藥丸要靠它們的資料，
            //     而且 API 呼叫與原本一模一樣，只是表單先收著。
            // ZH: 用 AdminFold.html()：每次換人／進出編輯都會整段重畫，
            //     它會照記住的開合狀態畫，使用者剛點開的不會被收回去。
            + AdminFold.html({
                id: 'pp-rare', key: 'dz_pp_rare', zh: '較少用', tag: 'h3', cls: 'pp-rare',
                body:
                    // ZH: v4.4c 一次性解鎖（擁有者裁定 2026-09-03）；v4.45 排在收合區第一個。
                    '<section class="adm-card pp-blk" id="unlock-box">'
                    + blkHead(T('pp_unlock', '修改個人資料的授權'))
                    + '<span class="skeleton skeleton--line"></span></section>'

                    // 額度 / 實驗室（非同步填）
                    + '<section class="adm-card pp-blk" id="quota-box">'
                    + blkHead(T('pp_quota', '磁碟配額'))
                    + '<span class="skeleton skeleton--line"></span></section>'

                    + '<section class="adm-card pp-blk" id="lab-box">'
                    + blkHead(T('pp_lab', '程式實驗室'))
                    + '<span class="skeleton skeleton--line"></span></section>'

                    // ZH: UUID：排查問題（看日誌、對資料庫）時才用得到，放最後。
                    + '<section class="adm-card pp-blk">'
                    + '<div class="kv"><span class="kv__k">UUID</span>'
                    + '<span class="kv__v mono">' + esc(u.id) + '</span></div></section>',
            })
            + '</div>';

        // ZH: 換一個人（或重畫）就從 0 算起 —— 上一個人的「生效中」不能留在這個人身上。
        LIVE = { unl: 0, q: 0 };
        RARE = AdminFold.wire($('detail').querySelector('[data-fold="pp-rare"]'));
        // ZH: 編輯中的標示（色條＋「編輯中」藥丸）取代原本「目前是唯讀」那類句子：
        //     唯讀是平常狀態，只標出例外。
        if (EDIT_BASIC) AdminEditMark('basic-box', true);

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
            // ZH: v4.10b 儲存一律要確認（擁有者裁定 2026-09-11）。
            //
            // ZH: 我一度把確認整個拿掉，理由是「改錯了再改回來就好」。
            //     那句話對信箱／學系／身分成立，但這張表單同時能改
            //     **管理權限**與**密碼** —— 那兩個「改回來」救不了：
            //     權限給出去的期間他做過的事、密碼給出去之後誰用過，
            //     都不會因為改回來而消失。
            //
            // ZH: 為什麼一律問而不是只在那兩欄變動時問：確認出現的時機
            //     可預測，管理者才不會在「這次怎麼沒問」的時候鬆懈。
            //     欄位值在 run 裡才讀 —— 小彈窗不動編輯表單，值都還在。
            targetConfirm(T('pp_confirm_save', '確認儲存'), null, u.username,
                          async function (name) {
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
            // ZH: 一律帶上 —— 後端在 is_admin／password 有變動時會驗（見 admin.py）。
            patch.confirm_username = name;

            try {
                await api('/admin/users/' + encodeURIComponent(u.id), {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(patch),
                });
            } catch (e) {
                // ZH: 丟給 targetConfirm 顯示在小彈窗裡（彈窗不關，不用重打）。
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
        // ZH: v4.10 停用／刪除都走「打出目標帳號」的確認（見 targetConfirm）。
        $('toggle-active').addEventListener('click', function () {
            targetConfirm(u.is_active ? T('pp_disable', '停用帳號') : T('pp_enable', '啟用帳號'),
                null, u.username,
                async function (name) {
                    await api('/admin/users/' + encodeURIComponent(u.id), {
                        method: 'PUT',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ is_active: u.is_active ? 0 : 1,
                                               confirm_username: name }),
                    });
                    u.is_active = u.is_active ? 0 : 1;
                    renderList();
                    renderDetail();
                });
        });

        $('del').addEventListener('click', function () {
            // ZH: 刪除的確認句直接放在彈窗裡（原本的原生 confirm 併進來了）。
            targetConfirm(T('pp_delete', '刪除帳號'),
                T('pp_delete_confirm', '要刪除「{n}」嗎？').replace('{n}', u.username),
                u.username,
                async function (name) {
                    await api('/admin/users/' + encodeURIComponent(u.id) + '/delete', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ confirm_username: name }),
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
        // ZH: v4.4d 左右分欄（擁有者裁定 2026-09-03）：卡佔滿整列後，
        //     左＝綁定資訊、右＝消耗統計，並排一眼看完。
        // ZH: 左欄也給小標 —— 右欄有「用了多少」而左欄沒有的話，
        //     兩欄的列從不同高度開始，分隔線對不齊，看起來就是亂。
        // ZH: v4.45 兩欄的小標改成 .pp-sub（小一號的灰字）—— 區塊標題已經是 h3，
        //     同一塊裡再放兩個同樣份量的標題，就分不出哪一層是哪一層。
        var left = '<div class="pp-sub">'
            + esc(T('pp_ext_binding', '綁定資訊')) + '</div>'
            + kv(T('pp_ext_vendor', '廠商帳號'), b.myai_email || '—')
            + kv(T('pp_ext_sn', '序號'), b.myai_vendor_sn || '—');

        // ZH: 點數只有對得上同步快取時才有值。對不上就明講「同步不到」——
        //     顯示「—」會被當成「他沒有點數」，那是完全不同的一件事。
        left += kv(T('pp_ext_points', '點數'),
                   b.synced ? num(b.points) : T('pp_ext_nosync', '同步不到這個帳號'));
        // ZH: ⚠ 唯讀這行也要翻譯。只在下拉裡翻的話，看的時候是 "active"、
        //     一按編輯變成「正常」—— 同一個值兩種樣子。
        left += kv(T('pp_ext_status', '狀態'),
                   b.status ? T('st_' + b.status, b.status) : '—');

        var right = '<div class="pp-sub">'
            + esc(T('pp_ext_used', '用了多少（全部期間）')) + '</div>';
        if (c && c.summary && c.summary.tx_count) {
            var s2 = c.summary, p = c.peer || {};
            right += kv(T('pp_ext_consumed', '總消耗'), num(s2.consumed) + ' ' + T('an_points', '點'))
                + kv(T('pp_ext_uses', 'AI 使用次數'), num(s2.uses))
                + kv(T('pp_ext_logins', '登入次數'), num(s2.logins))
                // ZH: 一個人的數字單看沒有意義 —— 給同期間的全體人均當基準，
                //     才知道「1000 點」是多還是少。
                + kv(T('pp_ext_peer', '全體人均'),
                     p.avg_consumed != null ? num(p.avg_consumed) + ' ' + T('an_points', '點') : '—');
        } else {
            right += '<p class="footnote">' + esc(c
                ? T('pp_ext_notx', '交易日誌裡還沒有這個人的紀錄。')
                : T('pp_ext_nosync', '同步不到這個帳號')) + '</p>';
        }
        return '<div class="ext-cols"><div>' + left + '</div><div>' + right + '</div></div>';
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
        var title = blkHead(T('pp_ext', '外部 AI（MYAI）'));
        var b = null, c = null;
        // ZH: 這個 <section> 在重讀之間是同一個元素（只換 innerHTML），
        //     「編輯中」的色條掛在它身上 —— 每一條出口都要明確設一次，不然取消編輯後色條還在。
        AdminEditMark(box, false);
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

        // ZH: v4.45 標題列右半只留最常用的兩顆：加點、回收點數。
        //     「編輯綁定」與「解除綁定」收進「更多▾」—— 解除是破壞性的，原本跟加點並排一樣重；
        //     AdminMenu 會把 danger 項排到最底下、紅字、上面一條線。
        //     選單項保留原本的 id（e-edit / e-unbind），下面綁事件的地方不用改。
        // ZH: 編輯中時標題列不放按鈕：儲存／取消在表單底下，旁邊再擺加點會讓人以為能一起存。
        var acts = EXT_EDIT ? '' :
            '<button class="btn btn--minor" type="button" id="e-grant">'
            + esc(T('pp_ext_grant', '加點')) + '</button>'
            // ZH: v4.43 回收（擁有者 2026-10-30）。緊鄰加點 —— 它們是同一件事的兩個方向。
            + '<button class="btn btn--minor" type="button" id="e-reclaim">'
            + esc(T('pp_ext_reclaim', '回收點數')) + '</button>'
            + AdminMenu.html({ id: 'e-more', items: [
                { id: 'e-edit', key: 'dz_pp_ext_edit', zh: '編輯綁定' },
                { id: 'e-unbind', key: 'pp_ext_unbind', zh: '解除綁定', danger: true },
            ] });

        box.innerHTML = blkHead(T('pp_ext', '外部 AI（MYAI）'), acts)
            + (EXT_EDIT ? extForm(b) : extRo(b, c))
            + (EXT_EDIT
                ? '<div class="ds__actions">'
                    + '<button class="btn btn--primary" type="button" id="e-save">'
                    + esc(T('pp_save', '儲存')) + '</button>'
                    + '<button class="btn btn--minor" type="button" id="e-cancel">'
                    + esc(T('pp_cancel', '取消變更')) + '</button>'
                    + '</div>'
                : '')
            + '<div id="e-grant-box" hidden></div>'
            + '<div id="e-reclaim-box" hidden></div>'
            + '<div class="inline-error" id="e-msg" hidden></div>';
        AdminEditMark(box, EXT_EDIT);

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
            $('e-reclaim').addEventListener('click', function () { toggleReclaim(u, b); });
            AdminMenu.wire('e-more');
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
        closeReclaim();               // ZH: 與回收互斥 —— 一次只開一張，方向不會看錯。
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

    // ══════════════════════════════════════════════════════════════════
    // ZH: v4.43 回收點數（擁有者 2026-10-30）
    // ══════════════════════════════════════════════════════════════════
    // ZH: 🔴 **方向與加點相反，而且更難救。** 加多了可以收回來；收錯了只能再發，
    //     而發回去的是新的點，他用掉的歷史對不回來。所以：
    //       · 預設是「全部收回」（最常見：課上完了、人走了），要收一部分才打數字
    //       · 確認框一律寫出**會從幾點變成幾點**
    function closeReclaim() {
        var box = $('e-reclaim-box');
        if (!box) return;
        box.hidden = true;
        box.innerHTML = '';
        say('e-msg', '');
    }

    function toggleReclaim(u, b) {
        var box = $('e-reclaim-box');
        if (!box.hidden) { closeReclaim(); return; }
        closeGrant();                 // ZH: 兩張表單不要同時開著 —— 送錯方向的機會。
        box.innerHTML =
            '<p class="footnote">' + esc(T('pp_rec_why',
                '把這個人的點數收回平台的廠商管理帳號。送出後收不回來，要還只能重新加點。'))
            + '</p>'
            + '<label class="adm-inline">'
            +   '<input type="checkbox" id="e-rec-all" checked> '
            +   '<span>' + esc(T('pp_rec_all', '全部收回')) + '</span>'
            + '</label>'
            + field('e-rec-pts', T('pp_rec_pts', '要收回的點數'), '', 'number',
                    ' min="1" step="1" inputmode="numeric" disabled')
            + field('e-rec-why', T('pp_grant_reason', '原因（會寫進紀錄）'), '')
            + '<div class="ds__actions">'
            + '<button class="btn btn--primary" type="button" id="e-rec-go">'
            + esc(T('pp_rec_go', '送出回收')) + '</button>'
            + '<button class="btn btn--minor" type="button" id="e-rec-cancel">'
            + esc(T('pp_grant_cancel', '取消')) + '</button></div>';
        box.hidden = false;
        // ZH: 勾了全部就把數字欄鎖起來，並**填入他目前有多少**（擁有者 2026-10-30）——
        //     空著的格子看不出「全部」是多少。讀不到就不填數字，改寫說明。
        function syncAll() {
            var all = $('e-rec-all').checked;
            var inp = $('e-rec-pts');
            var have = currentPoints(b);
            inp.disabled = all;
            inp.value = (all && have !== null) ? String(have) : '';
            inp.placeholder = (all && have === null)
                ? T('pp_rec_pts_unknown', '讀不到目前點數，送出時以廠商為準') : '';
            if (!all) inp.focus();
        }
        $('e-rec-all').addEventListener('change', syncAll);
        syncAll();
        $('e-rec-go').addEventListener('click', function () { doReclaim(u, b); });
        $('e-rec-cancel').addEventListener('click', closeReclaim);
    }

    // ZH: 目前點數。拿來把確認框寫成「從 X 變成 Y」——
    //     只講「要收 500 點」的話，看的人算不出收完剩多少。
    // ZH: 🔴 來源是綁定物件的 `b.points`，而且**要 b.synced 才算數** ——
    //     同步不到那個廠商帳號時 points 是過期的（畫面上那一格也是寫
    //     「同步不到這個帳號」而不是數字）。拿過期的數字去算「收完剩多少」
    //     會寫出一個看起來很篤定、實際上是錯的句子。
    function currentPoints(b) {
        return (b && b.synced && typeof b.points === 'number') ? b.points : null;
    }

    async function doReclaim(u, b) {
        var all = $('e-rec-all').checked;
        var pts = parseInt($('e-rec-pts').value, 10);
        if (!all && (!isFinite(pts) || pts <= 0)) {
            say('e-msg', T('pp_rec_need', '請填一個大於 0 的點數，或勾「全部收回」。'));
            return;
        }
        var have = currentPoints(b);
        var why = $('e-rec-why').value.trim();
        var take = all ? have : pts;
        // ZH: 🔴 數字留在說明裡 —— 與加點同一個理由，那是擋得住手滑的唯一地方。
        //     讀不到目前點數時（廠商查詢失敗）就不要編一個數字出來，講得保守一點。
        var hint = (take === null || have === null)
            ? T('pp_rec_confirm_unknown', '要把 {n} 的點數{w}收回嗎？送出後收不回來。')
                .replace('{n}', b.myai_email || u.username)
                .replace('{w}', all ? T('pp_rec_all_word', '全部') : (' ' + num(pts) + ' 點'))
            : T('pp_rec_confirm', '要從 {n} 收回 {p} 點嗎？收完會從 {a} 點變成 {z} 點，送出後收不回來。')
                .replace('{n}', b.myai_email || u.username)
                .replace('{p}', num(take)).replace('{a}', num(have))
                .replace('{z}', num(Math.max(0, have - take)));
        targetConfirm(T('pp_rec_title', '確認回收點數'), hint, u.username,
            async function (name) { await sendReclaim(u, all, pts, why, name); });
    }

    async function sendReclaim(u, all, pts, why, name) {
        var btn = $('e-rec-go');
        btn.disabled = true;            // ZH: 防連點 —— 這一支不冪等
        try {
            var r = await api('/admin/users/' + encodeURIComponent(u.id) + '/myai/reclaim', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(all
                    ? { all_points: true, reason: why, confirm_username: name }
                    : { points: pts, reason: why, confirm_username: name }),
            });
            closeReclaim();
            if (r.status === 'unknown') {
                // ZH: 送出後廠商沒回報成功 —— 點數**可能已經扣了**。
                //     這一則要留在畫面上，不能用會消失的提示（同加點）。
                say('e-msg', T('pp_rec_unknown',
                    '送出了，但廠商沒有回報成功。點數可能已經扣了 —— '
                    + '請到廠商後台對帳，不要再送一次。'));
            } else {
                say('e-msg', '');
                loadExtAi(u);          // ZH: 重讀，讓點數欄顯示新的值
            }
        } catch (e) {
            btn.disabled = false;
            throw new Error(String(e.message || e));
        } finally {
            btn.disabled = false;
        }
    }

    async function doGrant(u, b) {
        var pts = parseInt($('e-grant-pts').value, 10);
        if (!isFinite(pts) || pts <= 0) {
            say('e-msg', T('pp_grant_need', '請填一個大於 0 的點數。'));
            return;
        }
        var why = $('e-grant-why').value.trim();
        // ZH: v4.10b 改走 targetConfirm（原本是原生 confirm）。
        // ZH: 🔴 **數字一定要留在說明裡** —— 那是唯一擋得住「多打一個 0」
        //     的地方。換彈窗時很容易只搬動作、把這句話丟掉。
        targetConfirm(T('pp_grant_title', '確認加點'),
            T('pp_grant_confirm',
                '要給 {n} 加 {p} 點嗎？點數從平台的管理帳號轉出，送出後收不回來。')
                .replace('{n}', b.myai_email || u.username).replace('{p}', num(pts)),
            u.username,
            async function (name) { await sendGrant(u, pts, why, name); });
    }

    async function sendGrant(u, pts, why, name) {
        var btn = $('e-grant-go');
        btn.disabled = true;            // ZH: 防連點 —— 這一支不冪等
        try {
            var r = await api('/admin/users/' + encodeURIComponent(u.id) + '/myai/grant', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ points: pts, reason: why,
                                       confirm_username: name }),
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
            btn.disabled = false;
            // ZH: 丟回 targetConfirm 顯示在彈窗裡 —— 彈窗不關，不用重打。
            throw new Error(String(e.message || e));
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
        var liveSlot = $('pc-live-unl');      // ZH: await 之前抓（見 setLive）
        try {
            var d = await api('/admin/users/' + encodeURIComponent(u.id) + '/profile-unlock');
            var a = d.active;
            // ZH: v4.45 生效中就掛到名片上（收合區收著也看得到）。
            //     用 pp-pill-live（外框、不填色）而不是 adm-pill--ok：後者與「臨時帳號」同一個
            //     --accent-soft 底色，並排在名片上會讀成同一類標籤（見 admin.css 的 .pp-pill-live）。
            setLive(liveSlot, 'unl', a ? 1 : 0,
                    '<span class="adm-pill pp-pill-live">'
                    + esc(T('dz_pp_live_unl', '開放修改中')) + '</span>');
            box.innerHTML =
                blkHead(T('pp_unlock', '修改個人資料的授權'))
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
                      + '<button class="btn--quiet" type="button" id="unl-cancel">'
                      + esc(T('pp_unl_cancel', '收回')) + '</button></div>'
                    : '<p class="footnote">' + esc(T('pp_unl_locked', '目前鎖定中。')) + '</p>')
                + (d.last_used
                    ? '<p class="footnote">'
                      + esc(T('pp_unl_last', '上次修改：{d}').replace('{d}', TW.date(d.last_used.used_at)))
                      + '</p>'
                    : '')
                // ZH: v4.45 核可表單（連同整個 #unlock-box）收進「較少用」的 fold（計畫第 4 節）——
                //     原本常駐，理由是「看到申請時人已經在這一頁上了，再多一次展開只是多一步」；
                //     但它一年幾次，常駐的代價是每次打開對話框都多一整塊。fold 收著時，
                //     名片上的「開放修改中」標籤（上面的 setLive）照樣顯示目前的狀態。
                // ZH: v4.4c 範圍**依身分自動決定**（擁有者裁定 2026-09-03）：
                //     不再逐項勾選 —— 老師/學生＝校區＋學系、職員＝校區＋單位、
                //     訪客＝僅校區，一次全給。逐項挑的需求從沒出現過，
                //     挑錯反而會讓對方改到一半發現差一項、再跑一次申請。
                // ZH: v4.45 拿掉第二個小標（原本寫一次「開放一次修改」當小標、
                //     按鈕又寫一次，還帶 inline 的 margin）；按鈕從 primary 降成 minor ——
                //     它是一年幾次、有人來申請才做的事，不該是整個對話框最醒目的按鈕。
                + '<p class="footnote">'
                + esc(T('pp_unl_scope', '會開放：{f}（依他的身分決定）').replace('{f}',
                    unlockFieldsFor(u).map(function (f) {
                        var lab = UNLOCK_LABELS[f] || [f, f];
                        return T(lab[0], lab[1]);
                    }).join('、'))) + '</p>'
                + field('unl-reason', T('pp_unl_reason', '原因（會寫進稽核）'), '')
                + '<div class="ds__actions">'
                + '<button class="btn btn--minor" type="button" id="unl-go">'
                + esc(T('pp_unl_do', '開放一次修改')) + '</button></div>'
                + '<div class="inline-error" id="unl-msg" hidden></div>';

            var go = $('unl-go');
            if (go) go.addEventListener('click', function () { grantUnlock(u); });
            var cancel = $('unl-cancel');
            // ZH: 「收回」＝把還沒用掉的那筆標成已用掉。不刪紀錄 —— 稽核要看得出開過。
            if (cancel) cancel.addEventListener('click', function () { grantUnlock(u, true); });
        } catch (e) {
            box.innerHTML = blkHead(T('pp_unlock', '修改個人資料的授權'))
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

    // ZH: v4.10b 核可要確認（等於放行那個人改自己的組織資料）。
    // ZH: v4.45 **收回也要確認**（版面整理計畫第 4 節，擁有者核可）。v4.10b 當時的理由是
    //     「收錯了再核可一次就好」—— 但收回之後對方正在填的那一次就作廢了，
    //     而且這顆鈕現在跟磁碟加碼的「收回」在同一個收合區裡，兩個意思不同的「收回」
    //     沒有一道確認就很容易點錯。確認方式與其他操作相同（打出目標帳號）。
    // ZH: 🔴 只是前端多一道門 —— 送出的 API 與原本**完全相同**（revoke 端點不收
    //     confirm_username，這裡也不送），後端的行為沒有任何改變。
    async function grantUnlock(u, revoke) {
        if (revoke) {
            targetConfirm(T('dz_pp_unl_rv_title', '確認收回修改授權'),
                          T('dz_pp_unl_rv_hint', '收回之後 {n} 就不能再改，要改得重新開放一次。')
                              .replace('{n}', u.username),
                          u.username,
                          async function () { await sendUnlock(u, true, null); });
            return;
        }
        targetConfirm(T('unl_confirm_title', '確認開放修改'), null, u.username,
                      async function (name) { await sendUnlock(u, false, name); });
    }

    async function sendUnlock(u, revoke, name) {
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
                                           reason: ($('unl-reason') || {}).value || '',
                                           confirm_username: name }),
                });
            }
            loadUnlock(u);          // ZH: 重讀 —— 狀態由後端決定,不要在前端自己推
        } catch (e) {
            if (msg) { msg.textContent = e.message; msg.hidden = false; }
            // ZH: 兩條都是從確認彈窗來的（v4.45 起收回也是）——
            //     丟回去讓彈窗顯示、彈窗不關，不用重打。
            throw e;
        }
    }

    async function loadQuota(u) {
        var box = $('quota-box');
        var liveSlot = $('pc-live-q');        // ZH: await 之前抓（見 setLive）
        try {
            var q = await api('/admin/quota/' + encodeURIComponent(u.id));
            var live = (q.grants || []).filter(function (g) { return !g.revoked_at; });
            // ZH: v4.45 有加碼就掛到名片上（收合區收著也看得到）。寫**總共加了幾 GB**，
            //     不是「有加碼」—— 數字才回答得了「他現在到底有多少」。
            var extra = live.reduce(function (s, g) { return s + (Number(g.extra_quota_gb) || 0); }, 0);
            setLive(liveSlot, 'q', live.length,
                    '<span class="adm-pill pp-pill-live">'
                    + esc(T('dz_pp_live_q', '磁碟 +{g} GB').replace('{g}', extra)) + '</span>');
            box.innerHTML =
                blkHead(T('pp_quota', '磁碟配額'))
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

                // ZH: v4.45 小標從「與區塊標題同樣份量、帶 inline margin 的 div」改成 .pp-sub。
                + '<div class="pp-sub">' + esc(T('pp_q_grants', '額外授與')) + '</div>'
                + (live.length
                    ? live.map(function (g) {
                        return '<div class="adm-alert">'
                            + '<span>+' + esc(g.extra_quota_gb) + ' GB　'
                            + '<span class="footnote">' + esc(g.reason || '')
                            + (g.expires_at ? '　→ ' + esc(TW.date(g.expires_at)) : '') + '</span></span>'
                            + '<button class="btn--quiet" type="button" data-revoke="' + esc(g.id) + '"'
                            + ' data-gb="' + esc(g.extra_quota_gb) + '">'
                            + esc(T('pp_q_revoke', '收回')) + '</button></div>';
                    }).join('')
                    : '<p class="footnote">' + esc(T('pp_q_none', '沒有額外授與。')) + '</p>')

                // ZH: v4.45 三個欄位各自帶**看得見的標籤**，寬度照內容分級（GB 數字、原因文字、日期）。
                //     原本是三個只有 placeholder 的框擠在 428px 的卡片裡，換成兩三行，
                //     而日期框完全看不出是「到期日」還是「起始日」—— 填錯的後果是額度提早消失。
                //     欄位 id（g-gb / g-why / g-exp）不變。
                + '<div class="adm-inline pp-qrow">'
                + '<label class="field pp-qrow__gb">'
                + '<span class="field__label">' + esc(T('pp_q_add_gb', '要加幾 GB')) + '</span>'
                + '<input class="field__input" id="g-gb" type="number" min="1" placeholder="GB"></label>'
                + '<label class="field pp-qrow__why">'
                + '<span class="field__label">' + esc(T('pp_q_reason', '原因（必填）')) + '</span>'
                + '<input class="field__input" id="g-why" type="text"></label>'
                + '<label class="field pp-qrow__exp">'
                + '<span class="field__label">' + esc(T('pp_q_expires', '到期日（可留空）')) + '</span>'
                + '<input class="field__input" id="g-exp" type="date"></label>'
                + '<button class="btn btn--minor" type="button" id="g-add">'
                + esc(T('pp_q_add', '加額度')) + '</button>'
                + '</div>'
                + '<div class="inline-error" id="q-msg" hidden></div>';

            // ZH: v4.45 收回加碼要確認（計畫第 4 節「兩種收回補上確認步驟」）。
            //     確認句寫出**收回幾 GB**（數字留在確認框裡，與加點、回收同一條理由）。
            //     送出的 API 與原本完全相同（DELETE，不帶任何確認欄位）；
            //     失敗時丟回確認彈窗顯示，彈窗不關。
            box.querySelectorAll('[data-revoke]').forEach(function (b) {
                b.addEventListener('click', function () {
                    targetConfirm(T('dz_pp_q_rv_title', '確認收回磁碟加碼'),
                        T('dz_pp_q_rv_hint', '要收回 {n} 的 +{g} GB 額外授與嗎？實際可用的配額會跟著變小。')
                            .replace('{n}', u.username).replace('{g}', b.dataset.gb || '?'),
                        u.username,
                        async function () {
                            await api('/admin/quota/grant/' + encodeURIComponent(b.dataset.revoke),
                                      { method: 'DELETE' });
                            loadQuota(u);
                        });
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
            box.innerHTML = blkHead(T('pp_quota', '磁碟配額'))
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
            box.innerHTML = blkHead(T('pp_lab', '程式實驗室'))
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
                            // ZH: v4.45 列內動作用輕量按鈕、紅字（強制關閉會丟掉他沒存的東西）。
                            + '<button class="btn--quiet btn--danger" type="button" data-stop="'
                            + esc(s.session_name || '') + '">'
                            + esc(T('pp_lab_stop', '強制關閉')) + '</button></div>';
                    }).join('')
                    : '<p class="footnote">' + esc(T('pp_lab_none', '目前沒有執行中的實驗室。')) + '</p>');
            // ZH: v4.45 拿掉原本的 #lab-msg —— 強制關閉的錯誤改在確認彈窗裡顯示（見下面），
            //     這一塊已經沒有人寫，留著只是一個永遠空著的元素。

            box.querySelectorAll('[data-stop]').forEach(function (btn) {
                // ZH: v4.45 確認從原生 confirm() 改成 targetConfirm（打出目標帳號）——
                //     這頁其他會影響到人的操作都是這一套，只有這裡是一顆按 Enter 就過的原生框。
                //     原本那句「要強制關閉 X 的實驗室嗎？」留在確認框的說明裡。
                // ZH: 送出的 API 與原本完全相同；失敗時丟回確認彈窗顯示（彈窗不關，不用重打）。
                btn.addEventListener('click', function () {
                    targetConfirm(T('dz_pp_lab_title', '確認強制關閉實驗室'),
                        T('pp_lab_confirm', '要強制關閉「{n}」的實驗室嗎？').replace('{n}', u.username),
                        u.username,
                        async function () {
                            // ZH: 明確指名要關哪一份。留空時後端會關「正在跑的那一份」，
                            //     但既然畫面上就是按著某一列，指名比較不會有意外。
                            var q = btn.dataset.stop ? '?session=' + encodeURIComponent(btn.dataset.stop) : '';
                            await api('/admin/lab/sessions/' + encodeURIComponent(u.id) + '/force-stop' + q,
                                      { method: 'POST' });
                            loadLab(u);
                        });
                });
            });
        } catch (e) {
            box.innerHTML = blkHead(T('pp_lab', '程式實驗室'))
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
        fd.append('dry_run', dryRun ? 'true' : 'false');
        // ZH: v4.20 整批開通 MYAI（與單筆同契約：兩平台同一組密碼）。
        if ($('ti-myai') && $('ti-myai').checked) fd.append('provision_myai', 'true');
        return fd;
    }

    // ZH: 範例檔下載。端點要 Authorization，不能用 <a href>（同組織匯出的理由）。
    async function downloadTemplate(fmt) {
        try {
            // ZH: v4.24 收斂到 AdminDownload（唯一真相，見 admin-chrome.js）
            await AdminDownload('/admin/users/temporary/import-template?fmt=' + fmt,
                                'temp-accounts-template.' + fmt);
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
                '每行一個帳號，欄位用逗號分開：帳號名稱,信箱,密碼,身分,到期日。'
                + '信箱可空（不寄信）；密碼可空（系統產生，建立後顯示一次）；'
                + '身分可空（預設學生），可用：學生/老師/職員/訪客；'
                + '到期日填日期（YYYY-MM-DD）或「永久」，不能空白。')) + '</p>'
            + field('ti-why', T('tmp_purpose', '用途（必填）'), '')
            // ZH: v4.20 —— 勾了的話**每一列都要有 Email**，否則預覽就會擋下來
            //     （後端驗，理由：沒 Email 會在廠商端留下救不回密碼的垃圾帳號）。
            + '<label class="adm-inline">'
            +   '<input type="checkbox" id="ti-myai"> '
            +   '<span>' + esc(T('tmpi_myai', '同時開通 MYAI 帳號（每一列都要有 Email；密碼與該列同一組）')) + '</span>'
            + '</label>'
            // ZH: v4.44 到期日搬進檔案的第 5 欄（擁有者 2026-10-30），每一列自己的 ——
            //     這裡原本的「到期日」與「整批永久有效」都拿掉了。永久要在檔案裡明寫「永久」，
            //     空白會在預覽被擋下（後端 _parse_row_expiry）。
            // ZH: v4.44 範例兩種格式收成一個下拉（擁有者 2026-10-30，與頁首工具列同一個做法），
            //     跟「選擇檔案」排在同一列：先拿範例、再選檔案，是同一件事的前後兩步。
            //     選單往**左**對齊（adm-dd--left）—— 按鈕在對話框左緣，往右對齊會被切掉。
            + '<div class="adm-inline">'
            + '<div class="account adm-dd adm-dd--left">'
            +   '<button class="btn btn--minor" type="button" id="ti-tpl"'
            +   ' aria-haspopup="menu" aria-expanded="false" aria-controls="ti-tpl-menu">'
            +   esc(T('tmpi_tpl', '下載範例'))
            +   ' <span class="account__caret" aria-hidden="true">▾</span></button>'
            +   '<div class="account__menu" role="menu" hidden id="ti-tpl-menu">'
            +     '<button type="button" role="menuitem" id="ti-tpl-xlsx">'
            +     esc(T('tmpi_tpl_xlsx', 'Excel（.xlsx）')) + '</button>'
            +     '<button type="button" role="menuitem" id="ti-tpl-csv">'
            +     esc(T('tmpi_tpl_csv', 'CSV（.csv）')) + '</button>'
            +   '</div>'
            + '</div>'
            + '<input type="file" id="ti-file" accept=".csv,.xlsx" hidden>'
            + '<button class="btn btn--minor" type="button" id="ti-pick">'
            + esc(T('tmpi_pick', '選擇檔案（CSV / Excel）')) + '</button>'
            + '<span class="footnote" id="ti-fname">' + esc(T('tmpi_nofile', '尚未選擇')) + '</span>'
            + '</div>'
            // ZH: v4.45 頁腳順序：［取消］［預覽］［確認建立］—— 確認在最右邊（見 openTempForm）。
            + '<div class="adm-inline rmod__foot rmod__foot--end">'
            + '<button class="btn btn--minor" type="button" id="ti-cancel">'
            + esc(T('tmp_cancel', '取消')) + '</button>'
            + '<button class="btn btn--minor" type="button" id="ti-preview">'
            + esc(T('tmpi_preview', '預覽')) + '</button>'
            + '<button class="btn btn--primary" type="button" id="ti-apply" hidden>'
            + esc(T('tmpi_apply', '確認建立')) + '</button>'
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
        AdminDropdown($('ti-tpl'), $('ti-tpl-menu'));
        $('ti-pick').addEventListener('click', function () { $('ti-file').click(); });
        $('ti-file').addEventListener('change', function () {
            TI_FILE = ($('ti-file').files || [])[0] || null;
            $('ti-fname').textContent = TI_FILE ? TI_FILE.name : T('tmpi_nofile', '尚未選擇');
            $('ti-apply').hidden = true;
            $('ti-result').innerHTML = '';
        });
        // ZH: 內容一改，上一份預覽就不算數（同手動補齊：看 A 的預覽送出 B 很危險）。
        // ZH: 🔴 勾選也要作廢預覽 —— 預覽過的是「不開通」那一版，
        //     勾完直接按建立的話，看到的與送出的是兩件事（後端的驗證規則也不同）。
        ['ti-why', 'ti-myai'].forEach(function (id) {
            if (!$(id)) return;
            $(id).addEventListener($(id).type === 'checkbox' ? 'change' : 'input', function () {
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
            + '<th>' + esc(T('tmpi_exp_col', '到期日')) + '</th>'
            + '<th>' + esc(T('tmpi_check', '檢查')) + '</th>'
            + '</tr></thead><tbody>'
            + r.rows.map(function (x) {
                return '<tr><td>' + esc(x.username || '—') + '</td>'
                    + '<td>' + esc(roleName[x.role] || '—') + '</td>'
                    + '<td>' + esc(x.will_generate_pw
                        ? T('tmpi_pw_gen', '系統產生') : T('tmpi_pw_given', '檔案提供')) + '</td>'
                    // ZH: v4.44 每一列建到哪天。永久要看得出來 —— 這是送出前最後一眼。
                    + '<td>' + (x.expires_on ? esc(x.expires_on)
                        : x.never_expires ? '<strong>' + esc(T('tmpi_forever_cell', '永久')) + '</strong>'
                        : '—') + '</td>'
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
        // ZH: v4.20 —— 這一批有沒有做 MYAI 開通（決定表格要不要多一欄）。
        var anyMyai = r.created.some(function (x) { return x.myai; });
        // ZH: 🔴 自己填了密碼的那幾列不在 `gen` 裡（密碼不回顯），但它們**也開通了**。
        //     開通結果對那幾列同樣重要（尤其 linked_only），所以另外列一段。
        var otherMyai = anyMyai ? r.created.filter(function (x) { return !x.password && x.myai; }) : [];
        var dlg = _tempDlg(gen.length > 0);
        dlg.innerHTML =
            '<form method="dialog" class="rmod__x">'
            +   '<button class="btn btn--minor" type="submit" aria-label="'
            +   esc(T('pf_close', '關閉')) + '">✕</button></form>'
            + '<h2 class="rmod__title">' + esc(T('tmpi_done', '匯入完成')) + '</h2>'
            + '<p class="footnote">' + esc(T('tmpi_done_sum', '共建立 {n} 個臨時帳號。')
                .replace('{n}', num(r.total))
                // ZH: 🔴 永久的有幾個要寫出來 —— 永久是不可逆的決定
                //     （到期日可以延，永久卻要一個一個手動改回去）。
                //     v4.44 起到期日是每一列自己的，所以講「其中幾個」而不是一個日期。
                + (r.never_expires_count
                    ? ' ' + T('tmpi_done_forever_n', '其中 {n} 個永久有效（不會到期）。')
                        .replace('{n}', num(r.never_expires_count))
                    : '')) + '</p>'
            + (gen.length
                ? '<div class="adm-alert adm-alert--error"><span>'
                  + esc(T('tmpi_pw_once',
                      '🔴 下面這些密碼是系統產生的，只會顯示這一次。現在就抄下來——關掉之後就看不到了。'))
                  + '</span></div>'
                  + '<div class="adm-tablewrap"><table class="adm-table"><thead><tr>'
                  + '<th>' + esc(T('pp_c_user', '帳號')) + '</th>'
                  + '<th>' + esc(T('tmp_pw', '密碼')) + '</th>'
                  // ZH: v4.20 有開通才多這一欄 —— 沒開通時多一欄空白只是雜訊。
                  + (anyMyai ? '<th>MYAI</th>' : '')
                  + '</tr></thead><tbody>'
                  + gen.map(function (x) {
                      return '<tr><td class="mono">' + esc(x.username) + '</td>'
                          + '<td class="mono">' + esc(x.password) + '</td>'
                          + (anyMyai ? '<td>' + esc(myaiText(x.myai)) + '</td>' : '')
                          + '</tr>';
                  }).join('')
                  + '</tbody></table></div>'
                : '')
            + (otherMyai.length
                ? '<p class="footnote">' + esc(T('tmpi_myai_others',
                    '你自己填了密碼的那幾列（密碼不回顯）的 MYAI 結果：')) + '</p>'
                  + '<div class="adm-tablewrap"><table class="adm-table"><thead><tr>'
                  + '<th>' + esc(T('pp_c_user', '帳號')) + '</th><th>MYAI</th>'
                  + '</tr></thead><tbody>'
                  + otherMyai.map(function (x) {
                      return '<tr><td class="mono">' + esc(x.username) + '</td>'
                          + '<td>' + esc(myaiText(x.myai)) + '</td></tr>';
                  }).join('')
                  + '</tbody></table></div>'
                : '')
            + '<div class="adm-inline rmod__foot rmod__foot--end">'
            + '<button class="btn btn--minor" type="button" id="ti-close">'
            + esc(T('tmp_close', '知道了')) + '</button>'
            + (gen.length
                ? '<button class="btn btn--primary" type="button" id="ti-copy">'
                  + esc(T('tmpi_copy', '複製全部帳密')) + '</button>'
                : '')
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
    // ══════════════════════════════════════════════════════════════════
    // ZH: v4.6 Alma 身分回填（擁有者需求 2026-09-07）。
    //     排程每 alma_sync_interval_hours 自己跑一次；這顆是「現在就跑」。
    //     兩段式：先乾跑列出會動到誰，按確認才寫 —— 它改的是**身分**，
    //     跟手動補齊點數同一個等級的操作。
    // ZH: 後端只補空值、不覆蓋人工設定（判準在 alma_service.backfill_users，
    //     排程與這裡共用同一支，不會漂開）。
    // ══════════════════════════════════════════════════════════════════
    var ALMA_LIMIT = 200;      // ZH: 一次檢查幾個人（後端上限 500）

    function almaBox(inner, foot) {
        return '<form method="dialog" class="rmod__x">'
            + '<button class="btn btn--minor" type="submit" aria-label="'
            + esc(T('pf_close', '關閉')) + '">✕</button></form>'
            + '<h2 class="rmod__title">' + esc(T('alma_title', 'Alma 身分回填')) + '</h2>'
            + inner
            // ZH: v4.45 頁腳靠右；呼叫端把確認鍵放在最後（最右邊），見 openAlma。
            + '<div class="adm-inline rmod__foot rmod__foot--end">' + foot + '</div>'
            + '<div class="inline-error" id="alma-msg" hidden></div>';
    }

    function almaTable(details) {
        if (!details.length) {
            return '<p class="footnote">'
                + esc(T('alma_none', '沒有需要補的欄位——大家的資料都齊了。')) + '</p>';
        }
        return '<div class="adm-tablewrap"><table class="adm-table"><thead><tr>'
            + '<th>' + esc(T('pp_c_user', '帳號')) + '</th>'
            + '<th>' + esc(T('alma_changes', '會補上')) + '</th>'
            + '</tr></thead><tbody>'
            + details.map(function (d) {
                return '<tr><td>' + esc(d.username) + '</td><td>'
                    + esc((d.changes || []).join('、')) + '</td></tr>';
            }).join('')
            + '</tbody></table></div>';
    }

    async function openAlma() {
        var dlg = $('alma-dialog');
        dlg.innerHTML = almaBox(
            '<p class="footnote">' + esc(T('alma_loading', '正在跟 Alma 對資料…')) + '</p>', '');
        dlg.showModal();
        var r;
        try {
            r = await api('/admin/alma/backfill?dry_run=true&limit=' + ALMA_LIMIT,
                          { method: 'POST' });
        } catch (e) {
            dlg.innerHTML = almaBox('<p class="footnote">' + esc(e.message) + '</p>',
                '<button class="btn btn--minor" type="button" id="alma-close">'
                + esc(T('tmp_close', '知道了')) + '</button>');
            $('alma-close').addEventListener('click', function () { dlg.close(); });
            return;
        }
        dlg.innerHTML = almaBox(
            '<p class="footnote">'
            + esc(T('alma_why', '只補空著的欄位（校區／學系／單位／常用信箱），'
                    + '以及當初用信箱猜出來的角色。人工設定過或本人確認過的一律不動，'
                    + '主信箱永遠不動。')) + '</p>'
            + '<p class="footnote">'
            + esc(T('alma_checked', '檢查了 {n} 人，{c} 人有欄位可以補。')
                .replace('{n}', num(r.checked)).replace('{c}', num(r.changed))) + '</p>'
            + almaTable(r.details || []),
            '<button class="btn btn--minor" type="button" id="alma-close">'
            + esc(r.changed ? T('tmp_cancel', '取消') : T('tmp_close', '知道了')) + '</button>'
            + (r.changed
                ? '<button class="btn btn--primary" type="button" id="alma-go">'
                  + esc(T('alma_apply', '確認回填')) + '</button>'
                : ''));
        $('alma-close').addEventListener('click', function () { dlg.close(); });
        if (r.changed) {
            $('alma-go').addEventListener('click', function () { applyAlma(dlg); });
        }
    }

    async function applyAlma(dlg) {
        $('alma-go').disabled = true;          // ZH: 防連點
        try {
            var r = await api('/admin/alma/backfill?dry_run=false&limit=' + ALMA_LIMIT,
                              { method: 'POST' });
            dlg.innerHTML = almaBox(
                '<p class="footnote">'
                + esc(T('alma_done', '完成：{c} 人的資料補齊了（檢查 {n} 人）。')
                    .replace('{c}', num(r.changed)).replace('{n}', num(r.checked))) + '</p>'
                + almaTable(r.details || []),
                '<button class="btn btn--minor" type="button" id="alma-close">'
                + esc(T('tmp_close', '知道了')) + '</button>');
            $('alma-close').addEventListener('click', function () { dlg.close(); });
            ALL = await loadAll();             // ZH: 清單要跟著換（角色/學系可能變了）
            renderList();
        } catch (e) {
            say('alma-msg', e.message);
            $('alma-go').disabled = false;
        }
    }

    $('import-temp').addEventListener('click', openTempImport);
    $('alma-sync').addEventListener('click', openAlma);

    // ── 帳號匯出（v4.12）────────────────────────────────────────────────
    //
    // ZH: 端點要 Authorization，所以**不能用 <a href> 直接下載**
    //     （那樣帶不上 token，會拿到一個 401 的檔案）——
    //     fetch → blob → 臨時 <a download>，與數據頁、組織對照表同一個做法。
    //
    // ZH: `scope=all`：匯出全部帳號。上面那個搜尋框是**前端**的，
    //     而端點只認 auth_source 這一種篩選 —— 接成「跟著畫面」會是假的
    //     （使用者以為匯出的是他看到的那幾筆）。欄位用端點的預設值。
    //
    // ZH: 成功不另外給訊息 —— 檔案下載本身就是回饋。失敗**一定要講**：
    //     下載沒發生時畫面上完全沒有痕跡，使用者只會以為自己沒按到。
    async function exportUsers(fmt, btn, label) {
        var lab = label || btn;       // ZH: 下拉按鈕裡還有 ▾，只換文字那一段
        var old = lab.textContent;
        btn.disabled = true;
        lab.textContent = T('pp_exporting', '匯出中…');
        try {
            // ZH: v4.24 收斂到 AdminDownload（唯一真相，見 admin-chrome.js）
            await AdminDownload('/admin/users/export?scope=all&fmt=' + fmt,
                                'users-export.' + fmt);
        } catch (e) {
            alert(T('pp_export_fail', '匯出失敗（{w}）').replace('{w}', e.message));
        } finally {
            btn.disabled = false;
            lab.textContent = old;
        }
    }
    // ZH: v4.44 匯出收進下拉後，「匯出中…」寫在**下拉按鈕**上 ——
    //     選單項一點就收起來了，寫在它身上沒有人看得到。
    $('ux-xlsx').addEventListener('click', function () { exportUsers('xlsx', $('ux-btn'), $('ux-label')); });
    $('ux-csv').addEventListener('click', function () { exportUsers('csv', $('ux-btn'), $('ux-label')); });
    AdminDropdown($('tmp-btn'), $('tmp-btn-menu'));
    AdminDropdown($('ux-btn'), $('ux-btn-menu'));

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

    // ZH: `focus` = { key, which }：只有某張子表的分頁器換頁時才給（見 blockTable）。
    function renderBatch(focus) {
        if (!BX) return;
        var m = BX.myai, un = BX.un, pv = BX.prov;
        BX_PAGERS = [];

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
        // ZH: v4.45 Email 是 grow 欄：吃掉剩下的寬度，其他欄只佔內容需要的寬度。
        var C_MAIL = ['', 'Email', 'grow'];
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
                'pp_bx_un_myai_why', '廠商那邊有這些帳號，但平台上沒有人對應。多半是老師，或用了與平台不同的信箱。廠商自己的管理帳號請按「不列入計算」，統計就不會被它灌水。',
                [C_ACC, C_MAIL, C_TAG, ['pp_bx_c_points', '點數', 'num'],
                 ['pp_bx_c_stat', '統計']],
                (un.unmatched_myai || []).map(function (r) {
                    return [{ t: r.name || r.vendor_sn }, { t: r.email || '—' },
                            { t: r.excluded
                                ? T('pp_bx_excluded', '不列入計算')
                                : (r.has_platform_user ? T('pp_bx_hasuser', '找得到同 email 的使用者') : ''),
                              pill: true },
                            { t: num(r.points), cls: 'num' },
                            // ZH: 切換鈕。vendor_sn 進 data 屬性要 esc —— 它是後端來的值。
                            // ZH: v4.45 列內動作改用輕量按鈕（最多 20 列，每列一顆外框鈕太吵）；
                            //     點擊範圍照樣 44px。
                            { html: '<button class="btn--quiet" type="button"'
                                + ' data-excl="' + esc(r.vendor_sn) + '"'
                                + ' data-on="' + (r.excluded ? '1' : '0') + '">'
                                + esc(r.excluded ? T('pp_bx_incl_do', '列入計算')
                                                 : T('pp_bx_excl_do', '不列入計算'))
                                + '</button>' }];
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

        // ZH: 分頁器要等標記進了 DOM 才接得上。剛換頁的那一張把焦點放回同一顆鈕。
        BX_PAGERS.forEach(function (o) {
            if (focus && focus.key === o.key) o.focus = focus.which;
            AdminPager.wire(o);
        });
    }

    // ZH: 每一塊：標題（含筆數）+ 一句說明 + 表格。**空的就整塊不畫** ——
    //     五個「沒有」疊在一起會把真正有東西的那一塊淹掉。
    //
    // ZH: 🔴 用表格不用清單。原本是 flex 的 space-between，於是名字在最左、
    //     點數在最右，中間空了 1138px（實測）—— 要把一列讀完得橫掃整個螢幕。
    //     表格的欄位會對齊，而且**有欄位標題**告訴你右邊那個數字是什麼。
    // ZH: v4.45 超過 20 筆改成**分頁**（AdminPager），取代原本的「還有 N 筆。」——
    //     那句話是死路：知道還有 37 筆，卻沒有任何辦法看到它們。
    //     每張子表各記自己的頁碼（以標題 key 為鍵）；#bx-body 每次整段重畫，
    //     頁碼不能放在 DOM 上，所以放在這裡。重讀資料（同步、配對、切換列入計算）後
    //     列數可能變少，畫的時候會把頁碼夾回範圍內。
    // ZH: 分頁器的 id 前綴是 'bx-' + key（按鈕是 #bx-<key>-prev / -next），五張表不會撞 id。
    var BX_PER_PAGE = 20;
    var BX_PAGE = {};
    var BX_PAGERS = [];           // ZH: 這一輪畫出來的分頁器，renderBatch 畫完再一起接上
    // ZH: 「要處理」的兩張（對不上的）數量用警示色；其他三張是名單，用中性灰 ——
    //     全部上色等於沒有一個被凸顯。
    var BX_WARN = { pp_bx_un_users: true, pp_bx_un_myai: true };

    function blockTable(key, zh, whyKey, whyZh, cols, rows) {
        if (!rows.length) return '';
        var pages = Math.max(1, Math.ceil(rows.length / BX_PER_PAGE));
        var page = Math.min(Math.max(1, BX_PAGE[key] || 1), pages);
        BX_PAGE[key] = page;
        var shown = rows.slice((page - 1) * BX_PER_PAGE, page * BX_PER_PAGE);
        var pg = {
            id: 'bx-' + key, key: key, page: page, pages: pages, total: rows.length,
            onGo: function (p, which) { BX_PAGE[key] = p; renderBatch({ key: key, which: which }); },
        };
        BX_PAGERS.push(pg);
        // ZH: v4.45 子表標題改用共用的 .adm-head（h3），數量藥丸放在標題**裡面**、緊貼著字。
        return '<section class="adm-block">'
            + '<div class="adm-head"><div class="adm-head__what">'
            + '<h3 class="adm-head__title">' + esc(T(key, zh))
            // ZH: 筆數緊跟著標題。原本靠 space-between 推到最右邊，
            //     離標題 1246px —— 那個數字是在講誰，完全看不出來。
            + ' <span class="adm-head__count' + (BX_WARN[key] ? ' adm-head__count--warn' : '') + '">'
            + esc(num(rows.length)) + '</span>'
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
            + '</div></div>'
            + '<div class="adm-tablewrap adm-tablewrap--narrow">'
            + '<table class="adm-table"><thead><tr>'
            + cols.map(function (c) {
                return '<th' + (c[2] ? ' class="' + esc(c[2]) + '"' : '') + '>'
                    + esc(T(c[0], c[1])) + '</th>';
            }).join('')
            + '</tr></thead><tbody>'
            + shown.map(function (r) {
                return '<tr>' + r.map(function (cell, ci) {
                    // ZH: v4.5 `html` 型儲存格 —— 放按鈕用。**只給這支自己組的
                    //     字串**，不接任何後端資料（後端來的值一律走 esc）。
                    if (cell.html != null) {
                        return '<td' + (cell.cls ? ' class="' + esc(cell.cls) + '"' : '')
                            + '>' + cell.html + '</td>';
                    }
                    if (cell.pill) {
                        return '<td>' + (cell.t
                            ? '<span class="adm-pill adm-pill--temp">' + esc(cell.t) + '</span>'
                            : '<span class="footnote">—</span>') + '</td>';
                    }
                    // ZH: v4.45 一般文字格沒指定 class 時沿用欄位的 class（例如 Email 欄的 grow），
                    //     表頭與內容才會是同一種欄寬規則。
                    var cls = cell.cls || (cols[ci] && cols[ci][2]) || '';
                    return '<td' + (cls ? ' class="' + esc(cls) + '"' : '') + '>'
                        + esc(cell.t) + '</td>';
                }).join('') + '</tr>';
            }).join('')
            + '</tbody></table></div>'
            // ZH: 只有一頁時 AdminPager 只寫「共 N 筆」—— 但標題旁已經有數量藥丸，
            //     再寫一次是重複，所以一頁的表不畫分頁器。
            + (pages > 1 ? AdminPager.html(pg) : '')
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

    // ZH: v4.5 「不列入計算」切換。用委派 —— #bx-body 每次都整個重畫，
    //     直接綁在按鈕上的話，重畫一次就要記得重綁（漏一次＝按了沒反應）。
    document.addEventListener('click', async function (ev) {
        var btn = ev.target.closest && ev.target.closest('[data-excl]');
        if (!btn) return;
        var on = btn.dataset.on === '1';
        btn.disabled = true;
        try {
            await api('/external-ai/admin/myai-accounts/'
                      + encodeURIComponent(btn.dataset.excl) + '/exclude', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ excluded: !on }),
            });
            await loadBatch();     // ZH: 重讀 —— 讓標記與筆數一起更新
        } catch (e) {
            say('bx-msg', e.message);
            btn.disabled = false;
        }
    });

    var typing = null;
    $('q').addEventListener('input', function () {
        // ZH: 節流 —— 幾千人的清單每敲一個字就重畫會頓。
        clearTimeout(typing);
        // ZH: 換關鍵字就回第一頁 —— 不然在第 5 頁搜尋會看到一片空白。
        LIST_PAGE = 0;
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
        // ZH: v4.10b 預覽算出來的「幾個人、合計幾點」——送出前的確認要把
        //     這兩個數字講出來。理由同單人加點：數字寫進確認訊息是唯一
        //     擋得住「多打一個 0」的地方。
        var TU_LAST = { count: 0, points: 0 };
        var TU_PAGE_SIZE = 10;     // ZH: 預覽名單 10 人一頁（擁有者裁定 2026-09-03）
        // ZH: v4.41 這次不補的信箱（擁有者 2026-10-13）。🔴 預覽與送出都帶它 ——
        //     送出時後端會重新算名單，只在預覽帶的話，被移除的人會在送出那一刻被算回來。
        var TU_EXCLUDE = [];
        var TU_ROWS = null;        // ZH: 最近一次預覽（只拿來搜尋、畫畫面，不當送出的依據）

        function btns() {
            $('tu-apply').hidden = !PREVIEWED;
            $('tu-cancel').hidden = !PREVIEWED;
            // ZH: v4.45 確認鍵直接寫出人數與點數（計畫第 4 節）——「確認補齊」四個字
            //     擋不住「多打一個 0」，「確認補齊 87 人，共 4,350 點」擋得住。
            //     數字是預覽那一刻後端算的（TU_LAST）；送出時後端會再算一次，
            //     確認框也會再寫一次（見 apply）。按鈕沒有預覽時是藏著的，所以不必給無數字的版本。
            $('tu-apply').textContent = T('dz_pp_tu_apply_n', '確認補齊 {n} 人，共 {p} 點')
                .replace('{n}', num(TU_LAST.count)).replace('{p}', num(TU_LAST.points));
            // ZH: 有預覽在畫面上時，再按一次是拿**現在的**餘額重算 ——
            //     字樣跟著改（預覽→重算），不然看起來像同一件事按兩次。
            $('tu-preview').textContent = PREVIEWED
                ? T('pf_topup_recalc', '重算') : T('pf_topup_preview', '預覽');
            // ZH: 刻意**不**把輸入框鎖起來 —— 鎖了的話下面那個 input 監聽器
            //     永遠不會觸發（打不了字就沒有 input 事件），等於死碼。
            //     改成「改了數字就讓預覽失效」，同樣防得住「看 A 的預覽、送出 B」。
        }

        // ZH: `keepExclude`：改了點數只是讓預覽失效，「這次不補誰」是另一件事，留著；
        //     按「取消預覽」或送出完成才全部清掉。
        function reset(keepExclude) {
            PREVIEWED = null;
            TU_ROWS = null;
            if (keepExclude !== true) TU_EXCLUDE = [];
            $('tu-result').innerHTML = '';
            $('tu-tools').hidden = true;
            $('tu-search').value = '';
            say('tu-msg', '');
            btns();
        }

        // ZH: 已移除的人：一行列出，各帶「復原」。只列後端回報「本來會補、被排除」的人。
        function renderRemoved(excluded) {
            var box = $('tu-removed');
            if (!excluded || !excluded.length) { box.hidden = true; box.innerHTML = ''; return; }
            box.innerHTML = '<span class="footnote">'
                + esc(T('pf_topup_removed', '這次不補：')) + '</span>'
                + excluded.map(function (e) {
                    return '<span class="tu-chip">' + esc(e)
                        + ' <button class="btn btn--minor" type="button" data-undo="' + esc(e) + '"'
                        + ' aria-label="' + esc(T('pf_topup_undo_aria', '把 {e} 加回名單').replace('{e}', e)) + '">'
                        + esc(T('pf_topup_undo', '復原')) + '</button></span>';
                }).join('');
            box.hidden = false;
            box.querySelectorAll('[data-undo]').forEach(function (b) {
                b.addEventListener('click', function () {
                    var who = b.dataset.undo.toLowerCase();
                    TU_EXCLUDE = TU_EXCLUDE.filter(function (x) { return x !== who; });
                    preview();
                });
            });
        }

        function filtered(r) {
            var q = ($('tu-search').value || '').trim().toLowerCase();
            return q ? r.rows.filter(function (x) { return (x.email || '').toLowerCase().indexOf(q) >= 0; })
                     : r.rows;
        }

        function target() {
            var v = parseInt($('tu-target').value, 10);
            return (isFinite(v) && v > 0) ? v : null;
        }

        function renderPreview(r) {
            TU_ROWS = r;
            renderRemoved(r.excluded);
            // ZH: 名單被移除到空也要留著工具列 —— 不然「復原」的鈕會跟著消失。
            $('tu-tools').hidden = !(r.count || (r.excluded && r.excluded.length));
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
        // ZH: `focus`（'prev' / 'next'）只在分頁器換頁時給，重畫後焦點回到同一顆鈕。
        function renderPreviewPage(r, page, focus) {
            var list = filtered(r);
            if (!list.length) {
                $('tu-result').innerHTML = '<p class="footnote">'
                    + esc(T('pf_topup_nomatch', '沒有符合的帳號。')) + '</p>';
                return;
            }
            var pages = Math.max(1, Math.ceil(list.length / TU_PAGE_SIZE));
            page = Math.min(Math.max(1, page), pages);
            var slice = list.slice((page - 1) * TU_PAGE_SIZE, page * TU_PAGE_SIZE);
            // ZH: v4.45 分頁器改用共用的 AdminPager（id 前綴 tu，按鈕仍是 #tu-prev / #tu-next），
            //     並一直顯示總筆數（篩選後的筆數 —— 那是這張表現在有幾列）。
            var pg = { id: 'tu', page: page, pages: pages, total: list.length, focus: focus,
                       onGo: function (p, which) { renderPreviewPage(r, p, which); } };
            // ZH: .adm-tablewrap 是必要的（橫向捲動）—— 自己組光溜溜的 <table>，
            //     窄畫面會把整頁撐寬。與本頁其他表格同一套。
            // ZH: v4.45 帳號欄是 grow 欄；「移除」改成列內的輕量按鈕。
            $('tu-result').innerHTML =
                '<div class="adm-tablewrap"><table class="adm-table"><thead><tr>'
                + '<th class="grow">' + esc(T('pf_topup_who', '帳號')) + '</th>'
                + '<th class="num">' + esc(T('pf_topup_add', '要補')) + '</th>'
                + '<th><span class="sr-only">' + esc(T('pf_topup_act', '操作')) + '</span></th>'
                + '</tr></thead><tbody>'
                + slice.map(function (x) {
                    return '<tr><td class="grow">' + esc(x.email) + '</td>'
                         + '<td class="num">' + num(x.points) + '</td>'
                         + '<td class="tu-act"><button class="btn--quiet" type="button"'
                         + ' data-rm="' + esc(x.email) + '"'
                         + ' aria-label="' + esc(T('pf_topup_rm_aria', '這次不補給 {e}').replace('{e}', x.email)) + '">'
                         + esc(T('pf_topup_remove', '移除')) + '</button></td></tr>';
                }).join('')
                + '</tbody></table></div>'
                + AdminPager.html(pg);
            AdminPager.wire(pg);
            // ZH: 移除 = 加進排除名單 → **請後端重算**（不是前端自己扣）：
            //     合計點數與確認框裡的數字都要是後端算的那一份。
            $('tu-result').querySelectorAll('[data-rm]').forEach(function (b) {
                b.addEventListener('click', function () {
                    var who = b.dataset.rm.toLowerCase();
                    if (TU_EXCLUDE.indexOf(who) < 0) TU_EXCLUDE.push(who);
                    preview();
                });
            });
        }

        async function preview() {
            var t = target();
            if (!t) { say('tu-msg', T('pf_topup_need', '請填一個大於 0 的點數。')); return; }
            say('tu-msg', '');
            try {
                var r = await api('/admin/myai/topup', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ target: t, dry_run: true, exclude: TU_EXCLUDE }),
                });
                PREVIEWED = t;
                TU_LAST = { count: r.count || 0, points: r.points || 0 };
                renderPreview(r);
                // ZH: 沒有人要補時不給「確認」鈕 —— 按了也是空操作，
                //     但會讓人以為真的做了什麼。
                if (!r.count) { PREVIEWED = null; }
                btns();
            } catch (e) {
                say('tu-msg', String(e.message || e));
            }
        }

        function apply() {
            var t = target();
            if (!t) return;
            // ZH: v4.10b 送出前要打出**自己的**帳號（擁有者裁定 2026-09-11）。
            //     批次補齊沒有單一目標可以打，所以確認的是操作者本人。
            // ZH: 🔴 人數與點數要留在說明裡 —— 那是唯一擋得住「多打一個 0」
            //     的地方（同單人加點）。
            targetConfirm(T('pf_topup_title', '確認補齊點數'),
                T('pf_topup_confirm',
                    '要把 {n} 個帳號補到 {t} 點嗎？合計 {p} 點，'
                    + '從平台的管理帳號轉出，送出後收不回來。')
                    .replace('{n}', num(TU_LAST.count))
                    .replace('{t}', num(t))
                    .replace('{p}', num(TU_LAST.points))
                    // ZH: 有排除的話確認框要講出來 —— 不講的話，人數比上次少他也看不出為什麼。
                    + (TU_EXCLUDE.length
                        ? T('pf_topup_confirm_ex', '（已排除 {m} 個帳號）').replace('{m}', num(TU_EXCLUDE.length))
                        : ''),
                ((window.AdminMe && window.AdminMe()) || {}).username || '',
                async function (name) { await sendTopup(t, name); },
                T('pf_topup_self', '你自己的帳號'));
        }

        async function sendTopup(t, name) {
            $('tu-apply').disabled = true;      // ZH: 防連點
            try {
                var r = await api('/admin/myai/topup', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ target: t, dry_run: false,
                                           confirm_username: name, exclude: TU_EXCLUDE }),
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
                $('tu-apply').disabled = false;
                // ZH: 丟回 targetConfirm 顯示在彈窗裡（彈窗不關，不用重打）。
                throw new Error(String(e.message || e));
            } finally {
                $('tu-apply').disabled = false;
            }
        }

        $('tu-preview').addEventListener('click', preview);
        $('tu-apply').addEventListener('click', apply);
        $('tu-cancel').addEventListener('click', function () { reset(); });
        // ZH: 改了數字就讓預覽失效 —— 否則會發生「看著 A 的預覽、送出 B」。
        //     排除名單留著（那是「補給誰」，跟「補到多少」無關）。
        $('tu-target').addEventListener('input', function () {
            if (PREVIEWED) reset(true);
        });
        // ZH: 搜尋只篩**顯示**，不影響送出（送出的名單永遠是後端算的，扣掉排除的人）。
        $('tu-search').addEventListener('input', function () {
            if (TU_ROWS && TU_ROWS.count) renderPreviewPage(TU_ROWS, 1);
        });
        // ZH: v4.45 確認鍵的字是這裡組的（含數字、不掛 data-i18n），切換語言時要自己重寫一次。
        document.addEventListener('prefs:langchanged', btns);
        btns();
    })();

    // ══════════════════════════════════════════════════════════════════
    // ZH: v4.43 批次回收點數（擁有者 2026-10-30）
    // ══════════════════════════════════════════════════════════════════
    // ZH: 與上面的「手動補齊」**同一個形狀**，方向相反：兩段式、可搜尋、可移除、
    //     送出要打自己的帳號。差別只在三件事，而那三件都是因為它扣的是使用者的點數：
    //       · 預覽的措詞是「會收回」不是「會補」
    //       · 收到的水位允許 0（全部收光是合理的指令），補齊則要求 > 0
    //       · 確認框講「從他們的帳號收回」
    // ZH: 🔴 排除名單**預覽與送出都要帶** —— 送出時後端重算名單（同補齊那一條）。
    (function () {
        var PREVIEWED = null;
        var RC_LAST = { count: 0, points: 0 };
        var RC_EXCLUDE = [];
        var RC_ROWS = null;
        var RC_PAGE_SIZE = 10;

        function btns() {
            $('rc-apply').hidden = !PREVIEWED;
            $('rc-cancel').hidden = !PREVIEWED;
            // ZH: v4.45 確認鍵寫出人數與點數（理由同補齊的 btns）。
            $('rc-apply').textContent = T('dz_pp_rc_apply_n', '確認回收 {n} 人，共 {p} 點')
                .replace('{n}', num(RC_LAST.count)).replace('{p}', num(RC_LAST.points));
            $('rc-preview').textContent = PREVIEWED
                ? T('pf_topup_recalc', '重算') : T('pf_topup_preview', '預覽');
        }

        function reset(keepExclude) {
            PREVIEWED = null;
            RC_ROWS = null;
            if (keepExclude !== true) RC_EXCLUDE = [];
            $('rc-result').innerHTML = '';
            $('rc-tools').hidden = true;
            $('rc-search').value = '';
            say('rc-msg', '');
            btns();
        }

        // ZH: 收到的水位允許 0（把所有人收光是合理的指令）——
        //     所以這裡的判準是「有沒有填」，不是「大不大於 0」。
        function target() {
            var raw = $('rc-target').value.trim();
            if (raw === '') return null;
            var v = parseInt(raw, 10);
            return (isFinite(v) && v >= 0) ? v : null;
        }

        function renderRemoved(excluded) {
            var box = $('rc-removed');
            if (!excluded || !excluded.length) { box.hidden = true; box.innerHTML = ''; return; }
            box.innerHTML = '<span class="footnote">'
                + esc(T('pf_rec_removed', '這次不收：')) + '</span>'
                + excluded.map(function (e) {
                    return '<span class="tu-chip">' + esc(e)
                        + ' <button class="btn btn--minor" type="button" data-undo="' + esc(e) + '"'
                        + ' aria-label="' + esc(T('pf_topup_undo_aria', '把 {e} 加回名單').replace('{e}', e)) + '">'
                        + esc(T('pf_topup_undo', '復原')) + '</button></span>';
                }).join('');
            box.hidden = false;
            box.querySelectorAll('[data-undo]').forEach(function (b) {
                b.addEventListener('click', function () {
                    var who = b.dataset.undo.toLowerCase();
                    RC_EXCLUDE = RC_EXCLUDE.filter(function (x) { return x !== who; });
                    preview();
                });
            });
        }

        function filtered(r) {
            var q = ($('rc-search').value || '').trim().toLowerCase();
            return q ? r.rows.filter(function (x) { return (x.email || '').toLowerCase().indexOf(q) >= 0; })
                     : r.rows;
        }

        function renderPreview(r) {
            RC_ROWS = r;
            renderRemoved(r.excluded);
            $('rc-tools').hidden = !(r.count || (r.excluded && r.excluded.length));
            if (!r.count) {
                $('rc-result').innerHTML = '<p class="footnote">'
                    + esc(T('pf_rec_nobody', '沒有人高於這個點數，不需要收。')) + '</p>';
                return;
            }
            renderPage(r, 1);
            note('rc-msg', T('pf_rec_sum', '{n} 個帳號，合計收回 {p} 點。按「確認回收」才會送出。')
                .replace('{n}', num(r.count)).replace('{p}', num(r.points)));
        }

        // ZH: `focus` 同補齊的 renderPreviewPage。
        function renderPage(r, page, focus) {
            var list = filtered(r);
            if (!list.length) {
                $('rc-result').innerHTML = '<p class="footnote">'
                    + esc(T('pf_topup_nomatch', '沒有符合的帳號。')) + '</p>';
                return;
            }
            var pages = Math.max(1, Math.ceil(list.length / RC_PAGE_SIZE));
            page = Math.min(Math.max(1, page), pages);
            var slice = list.slice((page - 1) * RC_PAGE_SIZE, page * RC_PAGE_SIZE);
            // ZH: v4.45 共用分頁器（id 前綴 rc，按鈕仍是 #rc-prev / #rc-next）；表格同補齊。
            var pg = { id: 'rc', page: page, pages: pages, total: list.length, focus: focus,
                       onGo: function (p, which) { renderPage(r, p, which); } };
            $('rc-result').innerHTML =
                '<div class="adm-tablewrap"><table class="adm-table"><thead><tr>'
                + '<th class="grow">' + esc(T('pf_topup_who', '帳號')) + '</th>'
                + '<th class="num">' + esc(T('pf_rec_take', '要收回')) + '</th>'
                + '<th><span class="sr-only">' + esc(T('pf_topup_act', '操作')) + '</span></th>'
                + '</tr></thead><tbody>'
                + slice.map(function (x) {
                    return '<tr><td class="grow">' + esc(x.email) + '</td>'
                         + '<td class="num">' + num(x.points) + '</td>'
                         + '<td class="tu-act"><button class="btn--quiet" type="button"'
                         + ' data-rm="' + esc(x.email) + '"'
                         + ' aria-label="' + esc(T('pf_rec_rm_aria', '這次不收 {e}').replace('{e}', x.email)) + '">'
                         + esc(T('pf_topup_remove', '移除')) + '</button></td></tr>';
                }).join('')
                + '</tbody></table></div>'
                + AdminPager.html(pg);
            AdminPager.wire(pg);
            $('rc-result').querySelectorAll('[data-rm]').forEach(function (b) {
                b.addEventListener('click', function () {
                    var who = b.dataset.rm.toLowerCase();
                    if (RC_EXCLUDE.indexOf(who) < 0) RC_EXCLUDE.push(who);
                    preview();
                });
            });
        }

        async function preview() {
            var t = target();
            if (t === null) { say('rc-msg', T('pf_rec_need', '請填一個 0 或更大的點數。')); return; }
            say('rc-msg', '');
            try {
                var r = await api('/admin/myai/reclaim', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ target: t, dry_run: true, exclude: RC_EXCLUDE }),
                });
                PREVIEWED = t;
                RC_LAST = { count: r.count || 0, points: r.points || 0 };
                renderPreview(r);
                if (!r.count) { PREVIEWED = null; }
                btns();
            } catch (e) {
                say('rc-msg', String(e.message || e));
            }
        }

        function apply() {
            var t = target();
            if (t === null) return;
            targetConfirm(T('pf_rec_title', '確認回收點數'),
                T('pf_rec_confirm',
                    '要把 {n} 個帳號收到 {t} 點嗎？合計從他們的帳號收回 {p} 點，送出後收不回來。')
                    .replace('{n}', num(RC_LAST.count))
                    .replace('{t}', num(t))
                    .replace('{p}', num(RC_LAST.points))
                    + (RC_EXCLUDE.length
                        ? T('pf_topup_confirm_ex', '（已排除 {m} 個帳號）').replace('{m}', num(RC_EXCLUDE.length))
                        : ''),
                ((window.AdminMe && window.AdminMe()) || {}).username || '',
                async function (name) { await send(t, name); },
                T('pf_topup_self', '你自己的帳號'));
        }

        async function send(t, name) {
            $('rc-apply').disabled = true;
            try {
                var r = await api('/admin/myai/reclaim', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ target: t, dry_run: false,
                                           confirm_username: name, exclude: RC_EXCLUDE }),
                });
                reset();
                if (r.status === 'unknown') {
                    // ZH: 點數**可能已經扣了** —— 這一則不能用會消失的提示。
                    say('rc-msg', T('pf_rec_unknown',
                        '送出了，但廠商沒有回報成功。點數可能已經扣了 —— '
                        + '請到廠商後台對帳，不要再按一次。'));
                } else {
                    flash('rc-msg', T('pf_rec_done', '回收完成：{n} 個帳號、合計 {p} 點。')
                        .replace('{n}', num(r.count)).replace('{p}', num(r.points)), 8000);
                }
            } catch (e) {
                $('rc-apply').disabled = false;
                throw new Error(String(e.message || e));
            } finally {
                $('rc-apply').disabled = false;
            }
        }

        $('rc-preview').addEventListener('click', preview);
        $('rc-apply').addEventListener('click', apply);
        $('rc-cancel').addEventListener('click', function () { reset(); });
        $('rc-target').addEventListener('input', function () { if (PREVIEWED) reset(true); });
        $('rc-search').addEventListener('input', function () {
            if (RC_ROWS && RC_ROWS.count) renderPage(RC_ROWS, 1);
        });
        document.addEventListener('prefs:langchanged', btns);
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
