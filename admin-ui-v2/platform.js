/* ==========================================================================
 * platform.js — 平台設定（調完就走）
 *
 * ZH: 三塊都是「設定完就離開」的東西，與總覽（每天看）和人（接到求助才開）
 *     的使用時機不同：
 *       營運設定  GET/PUT /admin/system-settings
 *       模型      GET/POST /admin/models、PUT/DELETE /admin/models/{id}
 *       GPU 節點  GET /admin/gpu-nodes、PUT /admin/gpu-nodes/{id}
 *
 * ZH: 🔴 外部 AI（MYAI）**沒有放進來**。它有 18 個端點，而且大部分是
 *     營運動作（同步、匯入、未配對處理）不是設定 ——
 *     全塞進來會重演這次要解決的「一頁又長又雜」。另外處理。
 *
 * ZH: 營運設定是**資料驅動**的：後端每個旋鈕都回 label/type/value/default/
 *     min/max/overridden，所以這裡不寫死欄位清單。加旋鈕時前端不用改。
 * ========================================================================== */
(function () {
    'use strict';

    var API = '/api/v1';
    var DAYS = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'];

    function $(id) { return document.getElementById(id); }

    function token() {
        return sessionStorage.getItem('ai_hud_token') || localStorage.getItem('ai_hud_token');
    }

    function esc(s) {
        return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
            return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
        });
    }

    function detailText(body) {
        var d = body && body.detail;
        if (!d) return '';
        if (typeof d === 'string') return zhOnly(d);
        if (Array.isArray(d)) {
            return d.map(function (x) {
                return (x.loc ? x.loc[x.loc.length - 1] + '：' : '')
                    + zhOnly(String(x.msg || '').replace(/^Value error,\s*/, ''));
            }).join('；');
        }
        return String(d);
    }

    function zhOnly(text) {
        var parts = String(text).split(' | ');
        var lang = (window.Prefs && Prefs.get().ui_lang) || 'zh';
        var want = parts.filter(function (p) {
            return p.indexOf(lang === 'en' ? 'EN:' : 'ZH:') === 0;
        })[0];
        return (want || parts[0] || '').replace(/^(ZH|EN):\s*/, '');
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

    function say(id, text) {
        var el = $(id);
        if (!el) return;
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


    // ── 營運設定 ──────────────────────────────────────────────────────────
    // ZH: 預設**唯讀**，按「編輯設定」才變成可填的欄位。
    //
    // ZH: 兩個理由：15 個輸入框常駐會把這一區撐得很長，而真正要改的時候
    //     一年也沒幾次；而且常駐的輸入框會招來誤觸 ——
    //     捲頁時滑鼠滾輪停在數字欄位上，值就被改掉了，
    //     而且**完全沒有痕跡**（除非他剛好按了儲存）。
    var SETTINGS = [];
    var EDITING = false;

    async function loadSettings() {
        try {
            SETTINGS = (await api('/admin/system-settings')).settings || [];
        } catch (e) {
            $('settings').innerHTML = '<p class="footnote">'
                + esc(T('ov_fail_part', '這一段暫時讀不到（{w}）').replace('{w}', e.message)) + '</p>';
            return;
        }
        renderSettings();
    }

    function settingValueLabel(s) {
        // ZH: 唯讀時下拉要顯示**看得懂的名字**，不是模型 id。
        if (s.type === 'choice') {
            var pick = (s.choices || []).filter(function (c) {
                return String(c.value) === String(s.value);
            })[0];
            return pick ? pick.label : String(s.value);
        }
        return String(s.value);
    }

    function renderSettings() {
        paintSettingsButtons();

        if (!EDITING) {
            // ZH: 唯讀 —— 一列兩欄（名稱 / 值），比可編輯時緊很多。
            $('settings').innerHTML = SETTINGS.map(function (s) {
                return '<div class="adm-setting adm-setting--ro">'
                    + '<span class="adm-setting__label">' + esc(s.label)
                    + (s.overridden ? ' <span class="adm-pill adm-pill--temp">'
                        + esc(T('pf_overridden', '已覆寫')) + '</span>' : '')
                    + '</span>'
                    + '<span class="adm-setting__ro">' + esc(settingValueLabel(s)) + '</span>'
                    + '</div>';
            }).join('');
            wireExternalWarning();
            return;
        }

        $('settings').innerHTML = SETTINGS.map(function (s) {
            var range = (s.min != null && s.max != null)
                ? T('pf_range', '{min}–{max}').replace('{min}', s.min).replace('{max}', s.max)
                : '';
            return '<div class="adm-setting">'
                + '<label class="adm-setting__label" for="s-' + esc(s.key) + '">'
                + esc(s.label)
                // ZH: `overridden` 是後端給的 —— 標出來，管理者才分得出
                //     「這是我改過的」與「這是 .env 的預設」。
                + (s.overridden ? ' <span class="adm-pill adm-pill--temp">'
                    + esc(T('pf_overridden', '已覆寫')) + '</span>' : '')
                + '</label>'
                // ZH: 下拉型的旋鈕（目前只有小基的模型）。選項由後端給 ——
                //     前端不維護一份模型清單，不然管理者新增模型之後這裡還是舊的。
                // ZH: 🔴 **只有「已覆寫」的才填值**，其餘留空、用 placeholder 顯示預設。
                //
                // ZH: 原本一律填入生效值，結果按一次「儲存設定」就把**全部 15 個旋鈕
                //     都變成明確覆寫**（實測 11 → 15），連沒碰過的也是 ——
                //     之後改 .env 對它們就再也沒有作用，而且沒有任何提示。
                //
                // ZH: 空白＝跟著預設走，正好是後端的契約（值留空＝清除覆寫）。
                //     所以「回到預設」只要把欄位清空就好，不需要另外記狀態。
                + (s.type === 'choice'
                    ? '<select class="field__input" id="s-' + esc(s.key) + '">'
                        // ZH: 下拉沒辦法「留空」，所以給一個明確的「用預設」選項。
                        + '<option value=""' + (s.overridden ? '' : ' selected') + '>'
                        + esc(T('pf_use_default', '（用預設）')) + '</option>'
                        + (s.choices || []).map(function (c) {
                            return '<option value="' + esc(c.value) + '"'
                                + (s.overridden && String(c.value) === String(s.value)
                                    ? ' selected' : '') + '>'
                                + esc(c.label) + '</option>';
                        }).join('')
                        + '</select>'
                    : '<input class="field__input" id="s-' + esc(s.key) + '"'
                        + ' type="' + (s.type === 'int' || s.type === 'float' ? 'number' : 'text') + '"'
                        + (s.type === 'float' ? ' step="0.01"' : '')
                        + (s.min != null ? ' min="' + esc(s.min) + '"' : '')
                        + (s.max != null ? ' max="' + esc(s.max) + '"' : '')
                        + ' placeholder="' + esc(s.default) + '"'
                        + ' value="' + esc(s.overridden ? s.value : '') + '">')
                + '<span class="adm-setting__hint footnote">'
                + esc(T('pf_default', '預設 {v}').replace('{v}', s.default))
                + (range ? '　' + esc(range) : '')
                + '</span>'
                + '<button class="btn btn--minor" type="button" data-reset="' + esc(s.key) + '"'
                + (s.overridden ? '' : ' disabled') + '>'
                + esc(T('pf_reset', '回到預設')) + '</button>'
                + '</div>';
        }).join('');

        wireExternalWarning();

        $('settings').querySelectorAll('[data-reset]').forEach(function (b) {
            b.addEventListener('click', function () {
                // ZH: 🔴 **只清空欄位，不存檔。**
                //     原本是按下去就立刻送出並跳回唯讀 —— 你正在改好幾個欄位，
                //     其中一個按了「回到預設」就把全部一起存掉並踢出編輯模式。
                //
                // ZH: 空白就是「跟著預設走」（後端契約），所以清空即可；
                //     真正生效是在按「儲存設定」的時候，與其他欄位一起。
                var el = $('s-' + b.dataset.reset);
                if (el) { el.value = ''; el.focus(); }
                b.disabled = true;          // 已經是預設了，再按沒有意義
            });
        });
    }

    // ZH: 選了校外供應商就把代價講出來 —— 這是政策決定，不只是換個下拉值。
    //
    // ZH: ⚠ **唯讀時也要顯示**。這條提示講的是「平台現在把使用者的問題送到哪裡」——
    //     那件事在你沒有在編輯的時候同樣成立，而且正是你最需要看到它的時候。
    //     （只在編輯時顯示的話，它就變成一句沒有人會再看到的話。）
    function wireExternalWarning() {
        var row = SETTINGS.filter(function (x) { return x.key === 'rag_chat_model'; })[0];
        if (!row) { $('ext-warn').hidden = true; return; }

        var paint = function (value) {
            var pick = (row.choices || []).filter(function (c) {
                return String(c.value) === String(value);
            })[0];
            $('ext-warn').hidden = !(pick && pick.provider && pick.provider !== 'ollama');
        };

        var sel = $('s-rag_chat_model');
        if (sel) {
            sel.addEventListener('change', function () { paint(sel.value); });
            paint(sel.value);
        } else {
            paint(row.value);          // 唯讀模式：看目前生效的值
        }
    }

    function paintSettingsButtons() {
        $('s-edit').hidden = EDITING;
        $('s-save').hidden = !EDITING;
        $('s-cancel').hidden = !EDITING;
        $('s-ro-hint').hidden = EDITING;
        // ZH: 「空白＝跟著預設」這條規則要講出來 ——
        //     不講的話，看到一排空欄位的人第一個反應是「資料沒載到」。
        $('s-edit-hint').hidden = !EDITING;
    }

    async function saveSettings(single) {
        var payload = {};
        if (single) {
            payload[single.key] = single.value;
        } else {
            SETTINGS.forEach(function (s) {
                var el = $('s-' + s.key);
                if (el) payload[s.key] = el.value;
            });
        }
        try {
            await api('/admin/system-settings', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });
            flash('s-msg', T('pf_saved', '已儲存'));
            EDITING = false;               // ZH: 存完就收起來，回到唯讀
            await loadSettings();          // ZH: 重讀 —— 後端會夾限，畫面要顯示真正存進去的值
        } catch (e) {
            say('s-msg', T('pf_save_fail', '存不起來（{w}）').replace('{w}', e.message));
        }
    }

    // ── 模型 ──────────────────────────────────────────────────────────────
    async function loadModels() {
        var list;
        try {
            list = await api('/admin/models');
        } catch (e) {
            $('models').innerHTML = '<p class="footnote">'
                + esc(T('ov_fail_part', '這一段暫時讀不到（{w}）').replace('{w}', e.message)) + '</p>';
            return;
        }
        if (!list.length) {
            $('models').innerHTML = '<p class="footnote">'
                + esc(T('pf_m_none', '還沒有任何模型。')) + '</p>';
            return;
        }
        var head = [
            ['pf_m_name', '名稱'], ['pf_m_type', '類型'], ['pf_m_provider', '供應者'],
            ['pf_m_id', '模型 ID'], ['pf_m_public', '公開'], ['pf_m_desc', '說明'],
        ];
        $('models').innerHTML =
            '<div class="adm-tablewrap"><table class="adm-table"><thead><tr>'
            + head.map(function (h) { return '<th>' + esc(T(h[0], h[1])) + '</th>'; }).join('')
            + '<th></th></tr></thead><tbody>'
            + list.map(function (m) {
                return '<tr>'
                    + '<td>' + esc(m.name) + '</td>'
                    + '<td>' + esc(m.model_type || '—') + '</td>'
                    + '<td>' + esc(m.api_provider || '—') + '</td>'
                    + '<td class="mono">' + esc(m.api_model_id || '—') + '</td>'
                    + '<td>' + esc(m.is_public ? T('pf_yes', '是') : T('pf_no', '否')) + '</td>'
                    + '<td>' + esc(m.description || '—') + '</td>'
                    + '<td>'
                    + '<button class="btn btn--minor" type="button" data-edit-model="'
                    + esc(m.id) + '">' + esc(T('pf_m_edit', '編輯')) + '</button> '
                    + '<button class="btn btn--minor" type="button" data-del-model="'
                    + esc(m.id) + '" data-name="' + esc(m.name) + '">'
                    + esc(T('pf_m_del', '刪除')) + '</button></td>'
                    + '</tr>';
            }).join('')
            + '</tbody></table></div>'
            + '<div class="inline-error" id="m-msg" hidden></div>';

        $('models').querySelectorAll('[data-edit-model]').forEach(function (b) {
            b.addEventListener('click', function () {
                var m = list.filter(function (x) { return String(x.id) === b.dataset.editModel; })[0];
                if (m) openModelForm(m);
            });
        });

        $('models').querySelectorAll('[data-del-model]').forEach(function (b) {
            b.addEventListener('click', async function () {
                if (!confirm(T('pf_m_del_confirm', '要刪掉「{n}」嗎？')
                    .replace('{n}', b.dataset.name))) return;
                try {
                    await api('/admin/models/' + encodeURIComponent(b.dataset.delModel),
                              { method: 'DELETE' });
                    loadModels();
                } catch (e) { say('m-msg', e.message); }
            });
        });
    }


    // ZH: 新增／編輯共用同一個表單。
    //
    // ZH: 原本這一區只能看與刪 —— 少了新增與編輯，要改一個模型得**先刪再建**，
    //     那會把它的 id 換掉（其他地方若引用了那個 id 就會斷）。
    //     `m` 為 null = 新增，否則是編輯。
    function openModelForm(m) {
        var box = $('model-form');
        box.hidden = false;
        box.innerHTML =
            '<div class="adm-card__title">'
            + esc(m ? T('pf_m_edit', '編輯') : T('pf_m_add', '新增模型')) + '</div>'
            + fieldRow('m-name', T('pf_m_name', '名稱'), m ? m.name : '')
            + fieldRow('m-provider', T('pf_m_provider', '供應者'), m ? (m.api_provider || '') : '')
            + fieldRow('m-mid', T('pf_m_id', '模型 ID'), m ? (m.api_model_id || '') : '')
            + fieldRow('m-endpoint', T('pf_m_endpoint', 'API 位址'), m ? (m.api_endpoint || '') : '')
            + fieldRow('m-desc', T('pf_m_desc', '說明'), m ? (m.description || '') : '')
            + '<label class="field"><span class="field__label">'
            + esc(T('pf_m_public', '公開')) + '</span>'
            + '<input type="checkbox" id="m-public"'
            + (m && m.is_public ? ' checked' : '') + '></label>'
            + '<div class="ds__actions">'
            + '<button class="btn btn--primary" type="button" id="m-go">'
            + esc(m ? T('pp_save', '儲存') : T('tmp_create', '建立')) + '</button>'
            + '<button class="btn btn--minor" type="button" id="m-cancel">'
            + esc(T('tmp_cancel', '取消')) + '</button>'
            + '</div>'
            + '<div class="inline-error" id="m-form-msg" hidden></div>';

        $('m-cancel').addEventListener('click', function () { box.hidden = true; });
        $('m-go').addEventListener('click', async function () {
            var body = {
                name: $('m-name').value.trim(),
                api_provider: $('m-provider').value.trim() || null,
                api_model_id: $('m-mid').value.trim() || null,
                api_endpoint: $('m-endpoint').value.trim() || null,
                description: $('m-desc').value.trim() || null,
                is_public: $('m-public').checked,
            };
            try {
                await api(m ? '/admin/models/' + encodeURIComponent(m.id) : '/admin/models', {
                    method: m ? 'PUT' : 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(body),
                });
                box.hidden = true;
                loadModels();
            } catch (e) {
                say('m-form-msg', e.message);
            }
        });
        $('m-name').focus();
    }

    // ── GPU 節點 ──────────────────────────────────────────────────────────
    // ZH: schedule 的契約（見 app/gpu_schedule.py 檔頭）有**三種狀態**，
    //     而且其中兩種容易混淆：
    //       null / 空字串   → 全天可排
    //       明確的空 dict {} → **永不**可排（與上面語意相反）
    //       {"mon": [["18:00","23:00"]], …} → 依時段
    //     所以介面做成三選一，不讓使用者自己去猜「清空」是什麼意思。
    function schedMode(raw) {
        if (raw == null || raw === '') return 'all';
        var obj = typeof raw === 'string' ? JSON.parse(raw) : raw;
        var any = DAYS.some(function (d) { return (obj[d] || []).length; });
        return any ? 'win' : 'never';
    }

    function schedToText(raw, day) {
        if (raw == null || raw === '') return '';
        var obj = typeof raw === 'string' ? JSON.parse(raw) : raw;
        return (obj[day] || []).map(function (seg) { return seg[0] + '-' + seg[1]; }).join(', ');
    }

    // ZH: 把「18:00-23:00, 08:00-12:00」轉回契約要的 [["18:00","23:00"], …]。
    //     格式不對就丟錯 —— **不要默默忽略**，那會讓管理者以為存好了。
    function textToSegs(text) {
        var out = [];
        String(text || '').split(',').forEach(function (part) {
            var t = part.trim();
            if (!t) return;
            var m = t.match(/^(\d{1,2}:\d{2})\s*-\s*(\d{1,2}:\d{2})$/);
            if (!m) throw new Error(t);
            out.push([m[1], m[2]]);
        });
        return out;
    }

    // ZH: 🔴 **下拉選一台、只畫那一台。**
    //
    // ZH: 原本是每台機器一張卡（後來改成可收合）。兩種都不對，理由是同一個：
    //     總覽已經是「一眼看完所有節點狀態」的地方，這裡再列一次是重複的 ——
    //     而重複的資訊會讓人不確定該信哪一邊，也讓這一頁隨機器數變長。
    //
    // ZH: 這一頁的工作是「調某一台」，所以入口就該是「選一台」。
    //     不管有幾台機器，這一區永遠只有一張卡。
    var NODES = [];

    async function loadNodes(keepId) {
        try {
            NODES = (await api('/admin/gpu-nodes')).nodes || [];
        } catch (e) {
            $('nodes').innerHTML = '<p class="footnote">'
                + esc(T('ov_fail_part', '這一段暫時讀不到（{w}）').replace('{w}', e.message)) + '</p>';
            $('node-card').hidden = true;
            $('n-count').textContent = '';
            return;
        }
        if (!NODES.length) {
            $('nodes').innerHTML = '<p class="footnote">'
                + esc(T('pf_n_none', '沒有任何節點回報過心跳。')) + '</p>';
            $('node-card').hidden = true;
            $('n-count').textContent = '';
            return;
        }
        $('nodes').innerHTML = '';        // ZH: 清掉骨架／錯誤訊息
        $('node-card').hidden = false;
        $('n-count').textContent = T('pf_n_count', '{n} 台機器').replace('{n}', NODES.length);

        // ZH: 存檔後要停在同一台，不要跳回第一台 ——
        //     連續調同一台的兩個設定是很常見的動作。
        var fromHash = hashNodeId();
        var want = keepId || fromHash || NODES[0].node_id;
        renderNodePicker(want);
        renderNodeForm(want);

    }

    function hashNodeId() {
        // ZH: 從總覽的 GPU 卡片連過來：platform.html#node-<id>
        var h = decodeURIComponent((location.hash || '').replace(/^#node-/, '').replace(/^#/, ''));
        return h && NODES.some(function (n) { return n.node_id === h; }) ? h : '';
    }

    function renderNodePicker(current) {
        $('node-pick').innerHTML = NODES.map(function (n) {
            // ZH: 只放名字。狀態／池別／張數**刻意不放** ——
            //     那些總覽已經有了，在這裡重複只會讓人不確定該信哪一邊。
            return '<option value="' + esc(n.node_id) + '"'
                + (n.node_id === current ? ' selected' : '') + '>'
                + esc(n.display_name ? n.display_name + '（' + n.node_id + '）' : n.node_id)
                + '</option>';
        }).join('');
    }

    // ZH: 只重畫 #node-body —— 卡片外殼與下拉留在原地，換節點時焦點不會掉。
    function renderNodeForm(nodeId) {
        var n = NODES.filter(function (x) { return x.node_id === nodeId; })[0];
        if (!n) { $('node-body').innerHTML = ''; return; }
        var mode = schedMode(n.schedule);

        $('node-body').innerHTML = ''

            // ZH: 撞名**留在這裡**（不是重複的狀態）—— 它是設定問題，
            //     而且要在這一頁修（改其中一台的 NODE_ID）。
            + (n.ip_conflict ? '<div class="adm-alert adm-alert--error"><span>'
                + esc(T('pf_n_conflict', '🔴 這個 NODE_ID 有兩台機器在用。')) + '</span></div>' : '')

            + '<div class="adm-cols">'
            + '<div>'
            + fieldRow('n-name', T('pf_n_name', '顯示名稱'), n.display_name || '')
            + fieldRow('n-note', T('pf_n_note', '備註'), n.note || '')
            + '<label class="field"><span class="field__label">'
            + esc(T('pf_n_enabled', '啟用')) + '</span>'
            + '<input type="checkbox" id="n-on"' + (n.enabled ? ' checked' : '') + '>'
            + '</label>'
            + '<label class="field"><span class="field__label" for="n-pool">'
            + esc(T('pf_n_pool', '池別覆寫')) + '</span>'
            + '<select class="field__input" id="n-pool">'
            + ['', 'batch', 'interactive'].map(function (p) {
                return '<option value="' + p + '"' + (n.pool_override === p ? ' selected' : '') + '>'
                    + esc(p || T('pf_n_pool_auto', '（跟著節點回報）')) + '</option>';
            }).join('')
            + '</select></label>'
            + fieldRow('n-buf', T('pf_n_buffer', '收工緩衝（分）'),
                       n.dispatch_buffer_min == null ? '' : n.dispatch_buffer_min, 'number')
            + '<p class="footnote">' + esc(T('pf_n_buffer_hint',
                '時段結束前這麼多分鐘就不再派新任務，讓正在跑的有時間收尾。')) + '</p>'
            + '</div>'

            + '<div>'
            + '<label class="field"><span class="field__label" for="n-mode">'
            + esc(T('pf_n_mode', '開放方式')) + '</span>'
            + '<select class="field__input" id="n-mode">'
            + [['all', T('pf_n_mode_all', '全天可用')],
               ['win', T('pf_n_mode_win', '依時段')],
               ['never', T('pf_n_mode_never', '永不可用')]].map(function (o) {
                return '<option value="' + o[0] + '"' + (mode === o[0] ? ' selected' : '') + '>'
                    + esc(o[1]) + '</option>';
            }).join('')
            + '</select></label>'
            + '<div class="adm-days" id="n-days"' + (mode === 'win' ? '' : ' hidden') + '>'
            + DAYS.map(function (d) {
                return '<label class="adm-day">'
                    + '<span>' + esc(T('d_' + d, d)) + '</span>'
                    + '<input class="field__input" id="n-' + d
                    + '" type="text" value="' + esc(schedToText(n.schedule, d)) + '">'
                    + '</label>';
            }).join('')
            + '<p class="footnote">' + esc(T('pf_n_sched_hint',
                '每一天可以填多段，用逗號分開，例如「18:00-23:00, 08:00-12:00」。空白＝那天不開放。')) + '</p>'
            + '<p class="footnote">' + esc(T('pf_n_overnight',
                '結束時間比開始早＝跨夜，例如 22:00-02:00。')) + '</p>'
            + '</div>'
            + '</div>'
            + '</div>'

            + '<div class="ds__actions">'
            + '<button class="btn btn--primary" type="button" id="n-save">'
            + esc(T('pf_n_save', '儲存這個節點')) + '</button>'
            + '</div>'
            + '<div class="inline-error" id="n-msg" hidden></div>';

        // ZH: 切「依時段」才顯示七天的輸入 —— 選「全天」時那七格是誤導。
        $('n-mode').addEventListener('change', function (ev) {
            $('n-days').hidden = (ev.target.value !== 'win');
        });
        $('n-save').addEventListener('click', function () { saveNode(n); });
    }

    function fieldRow(id, label, value, type) {
        return '<label class="field">'
            + '<span class="field__label" for="' + id + '">' + esc(label) + '</span>'
            + '<input class="field__input" id="' + id + '" type="' + (type || 'text') + '"'
            + ' value="' + esc(value) + '"></label>';
    }

    async function saveNode(n) {
        var mode = $('n-mode').value;
        var schedule;

        if (mode === 'all') {
            schedule = null;                    // ZH: null = 全天可排
        } else if (mode === 'never') {
            schedule = {};                      // ZH: 空 dict = 永不（與 null 相反，見上方註解）
        } else {
            schedule = {};
            try {
                DAYS.forEach(function (d) {
                    var segs = textToSegs($('n-' + d).value);
                    if (segs.length) schedule[d] = segs;
                });
            } catch (bad) {
                say('n-msg', T('pf_n_sched_bad', '時段格式看不懂：{w}').replace('{w}', bad.message));
                return;
            }
            // ZH: 選了「依時段」卻一段都沒填 —— 那在契約上等於「永不」。
            //     這很可能不是他的本意，所以擋下來問清楚，不要默默關掉一台機器。
            if (!Object.keys(schedule).length) {
                say('n-msg', T('pf_n_mode_never', '永不可用') + '？');
                return;
            }
        }

        var buf = $('n-buf').value.trim();
        var payload = {
            display_name: $('n-name').value.trim(),
            note: $('n-note').value.trim(),
            enabled: $('n-on').checked,
            pool_override: $('n-pool').value || null,
            schedule: schedule,
        };
        if (buf !== '') payload.dispatch_buffer_min = parseInt(buf, 10);

        try {
            await api('/admin/gpu-nodes/' + encodeURIComponent(n.node_id), {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });
            // ZH: 重讀 —— 後端會回算 state 與 next_change。
            //     ⚠ 帶著 node_id 重讀，**停在同一台**：跳回第一台的話，
            //       連續調同一台的兩個設定會變成每次都要重選。
            await loadNodes(n.node_id);
            flash('n-msg', T('pf_saved', '已儲存'));
        } catch (e) {
            say('n-msg', e.message);
        }
    }

    // ── 啟動 ──────────────────────────────────────────────────────────────
    $('s-edit').addEventListener('click', function () {
        EDITING = true;
        say('s-msg', '');
        renderSettings();
    });
    $('s-cancel').addEventListener('click', function () {
        // ZH: 取消要**丟掉改動**。從 SETTINGS 重畫即可 ——
        //     那份資料是上次從後端讀回來的，沒有被編輯過。
        EDITING = false;
        say('s-msg', '');
        renderSettings();
    });
    $('s-save').addEventListener('click', function () { saveSettings(null); });
    // ZH: 一定要包一層 —— 直接傳 openModelForm 的話，
    //     addEventListener 會把 **Event 物件**當成 `m`，於是永遠走「編輯」那條路。
    $('m-add').addEventListener('click', function () { openModelForm(null); });

    // ZH: 換一台就重畫那張卡。不重讀後端 —— NODES 是剛拿的，
    //     再打一次 API 只會讓切換變慢。
    $('node-pick').addEventListener('change', function (ev) {
        renderNodeForm(ev.target.value);
    });

    // ZH: 🔴 從總覽的 GPU 卡片連過來時要**捲到 GPU 節點那一區**。
    //     只把下拉選好而不捲的話，你會停在頁面最上方的「營運設定」，
    //     完全看不出剛才那個連結做了什麼 —— 連結等於只做了一半。
    //
    // ZH: ⚠ 時序：三段是平行載入的。在 loadNodes 裡捲的話，
    //     營運設定的 15 列可能**之後**才畫在它上方，把版面撐開 ——
    //     捲是捲了，但停在錯的位置。所以要等三段都就位。
    //
    // ZH: ⚠ 只在**第一次**捲。語言切換也會重跑 loadAll，
    //     每次都把人拉到 GPU 節點會很煩。
    var scrolled = false;

    function scrollToHash() {
        if (scrolled) return;
        // ZH: ⚠ 這行原本寫成 `!(...).indexOf('#node-') === 0` ——
        //     運算優先序讓它**永遠是 false**，於是直接打開這一頁也會被拉到 GPU 節點。
        //     （用 node 實際跑過三種 hash 才確認的，不是看出來的。）
        if ((location.hash || '').indexOf('#node-') !== 0) return;
        var el = $('h-nodes');
        if (!el) return;
        scrolled = true;
        // ZH: 等一次 rAF 讓版面確定就位再量位置。
        requestAnimationFrame(function () { el.scrollIntoView({ block: 'start' }); });
    }

    async function loadAll() {
        await Promise.all([loadSettings(), loadModels(), loadNodes()]);
        scrollToHash();
    }

    loadAll();
    document.addEventListener('prefs:langchanged', loadAll);
})();
