/* ==========================================================================
 * [畫面: 開通確認] — 使用者在這裡要完成：拿到初始密碼、去 MYAI 改掉、回報改好了
 *
 * ZH: 後端契約（GET /external-ai/my-provision）有**三種**狀態，首頁原本只當成兩種：
 *       provisioned=false                     → 還沒有 MYAI 帳號 → **沒有密碼可看**
 *       provisioned=true + initial_password    → 保留期內未確認 → 這個畫面的正常路徑
 *       provisioned=true + initial_password=null → 已確認或逾期 → 沒東西可看
 *     首頁先前在第一種狀態就顯示「確認我的初始密碼」，點進來會是空的。已一併修正。
 *
 * 隱私：身分一律由 JWT 推導，後端不吃任何身分參數，查不到別人的。
 *       ack 會**立即銷毀**伺服器上的暫存密碼，不等保留期到——所以文案要講明不可逆。
 * ========================================================================== */
const API = '/api/v1';
const FORCED = new URLSearchParams(location.search).get('state');
const $ = (id) => document.getElementById(id);

// ZH: 色系切換已集中到 prefs.js（跟帳號走）。
//     原本九個頁面各寫一份，**只有 app.js 那份會存與還原**——
//     於是「有些頁面換了顏色，其他頁面還沒變」。同一條規則不要有第二份實作。

function authHeaders() {
    // ZH: ⚠ 鍵名必須與 v1／v1.5／其他 v2 畫面一致（'ai_hud_token'）。
    const t = sessionStorage.getItem('ai_hud_token') || localStorage.getItem('ai_hud_token');
    return t ? { Authorization: 'Bearer ' + t } : {};
}

// ZH: stuck=true 時順便把「回報給我們」那一行打開。
//     預設 false —— 「已確認／逾期」不是故障，給回報入口只會製造無效工單。
function paintMsg(text, cls, stuck) {
    var box = $('stuck');
    if (box) box.hidden = !stuck;
    $('msg').textContent = text;
    $('msg').className = cls;
    $('msg').hidden = false;
    $('card').hidden = true;
    $('how').hidden = true;
}

// ZH: 錯誤（紅框）—— 這一頁只有「讀不到開通狀態」算錯誤。
function showMsg(text, stuck) { paintMsg(text, 'inline-error', stuck); }

// ZH: 正常狀態與成功 —— **不是紅的**。
//     🔴 這一頁四種訊息裡有三種不是錯誤（還在開通中、已確認／逾期、已清除密碼），
//     之前全部用錯誤樣式顯示。「你的帳號還在開通中」配紅底紅字，
//     讀起來像是開通失敗了。
//
// ZH: ⚠ stuck 與顏色是**兩件不同的事**，不要合併：「還在開通中」不是錯誤
//     （所以中性底），但使用者在這裡確實沒有下一步可走（所以要給回報入口）。
function showNote(text, stuck) { paintMsg(text, 'inline-note', stuck); }

// ── 載入 ─────────────────────────────────────────────────────────────
async function load() {
    if (FORCED === 'loading') return;

    let d;
    try {
        if (FORCED) {
            d = mock(FORCED);
        } else {
            const r = await fetch(`${API}/external-ai/my-provision`,
                                  { headers: { Accept: 'application/json', ...authHeaders() } });
            if (!r.ok) throw new Error(`HTTP ${r.status}`);
            d = await r.json();
        }
    } catch (e) {
        return showMsg(T('prov_state_fail', '暫時取不到開通狀態') + `（${e.message || e}）。`
                       + T('prov_retry', '可以重新整理再試一次。'), true);
    }

    if (!d.provisioned) {
        // ZH: 首頁的「問 AI」在未開通時會把人帶到這裡（擁有者裁定 2026-08-24）。
        //     所以這一支不只是「沒密碼可看」，而是他**本來想問 AI 卻問不了**。
        return showNote(T('prov_pending', '你的 MYAI 帳號還在開通中，目前還沒有初始密碼。')
            + T('prov_after', '開通完成後回到首頁就會看到提示。'), true);
    }
    if (!d.initial_password) {
        // ZH: 這兩種原因在後端是同一個結果（密碼為 null），前端**不要猜**是哪一種。
        return showNote(T('prov_none', '目前沒有可顯示的初始密碼——你已經確認過，或是保留期已過。')
            + T('prov_forgot', '若忘記密碼，請在 MYAI 平台用忘記密碼功能重設。'));
    }

    $('acct').textContent = d.email || '—';
    $('pw').textContent = d.initial_password;
    $('intro').textContent = d.retention_days
        ? T('prov_window', '這組密碼只在開通後 {d} 天內看得到。').replace('{d}', d.retention_days)
          + T('prov_change_soon', '請盡快到 MYAI 登入並改成自己的密碼。')
        : T('prov_change_soon', '請盡快到 MYAI 登入並改成自己的密碼。');
    $('card').hidden = false;
    $('how').hidden = false;
}

// ── 複製 ─────────────────────────────────────────────────────────────
$('copy').addEventListener('click', async () => {
    const pw = $('pw').textContent;
    try {
        await navigator.clipboard.writeText(pw);
        $('note').textContent = T('prov_copied', '已複製到剪貼簿。');
        $('note').hidden = false;
    } catch {
        // ZH: 剪貼簿在非 https 或權限被拒時不可用。不要靜默失敗——
        //     密碼已設 user-select:all，直接告訴使用者可以手動選取。
        $('note').textContent = T('prov_copy_manual', '這個瀏覽器不允許自動複製，請直接選取上面那一行。');
        $('note').hidden = false;
    }
});

// ── 主要動作：我已改好（不可逆）────────────────────────────────────────
$('ack').addEventListener('click', async () => {
    const btn = $('ack');
    btn.disabled = true;
    btn.textContent = T('prov_working', '處理中…');
    try {
        if (FORCED) {
            // 檢視模式不打後端，但流程走完整條，才看得到成功後的樣子
        } else {
            const r = await fetch(`${API}/external-ai/my-provision/ack`,
                                  { method: 'POST', headers: authHeaders() });
            if (!r.ok) throw new Error(`HTTP ${r.status}`);
        }
        showNote(T('prov_cleared', '已清除暫存的初始密碼。之後這裡不會再顯示它。'));
    } catch (e) {
        btn.disabled = false;
        btn.textContent = T('prov_ack', '我已經改好密碼了');
        $('note').textContent = T('prov_clear_fail', '清除失敗') + `（${e.message || e}）。`
            + T('prov_clear_fail2', '可以再試一次；不影響你在 MYAI 已經改好的密碼。');
        $('note').hidden = false;
    }
});

$('go-myai').addEventListener('click', (ev) => {
    ev.preventDefault();
    // ZH: 與首頁同一條路徑（先登出頁再轉登入頁），這裡只需要開登入頁：
    //     使用者手上就是初始密碼，本來就要登入一次。
    window.open('https://www.myai168.com/mcu/ai/user/login', '_blank', 'noopener');
});

// ── 假資料：供狀態檢視 ────────────────────────────────────────────────
function mock(kind) {
    if (kind === 'error') throw new Error('強制錯誤狀態');
    if (kind === 'unprovisioned') return { provisioned: false };
    if (kind === 'acked') return { provisioned: true, email: 'a1234567@mail.mcu.edu.tw',
                                   initial_password: null, acknowledged: true, retention_days: 30 };
    return { provisioned: true, email: 'a1234567@mail.mcu.edu.tw',
             initial_password: 'Mcu-2026-x7Kq', acknowledged: false, retention_days: 30 };
}

// ── 啟動 ─────────────────────────────────────────────────────────────
function requireLogin() {
    const t = sessionStorage.getItem('ai_hud_token') || localStorage.getItem('ai_hud_token');
    if (t || FORCED) return true;
    location.replace('login.html');
    return false;
}
if (requireLogin()) load();


// ── 語言切換時重繪 ───────────────────────────────────────────────────
// ZH: prefs.js 的字典掃描只換得掉 `data-i18n` 元素；本頁 JS 產生的內容要自己重跑。
//     只在語言**改變**時觸發（不是每次套用），所以不會在載入時多跑一次。
document.addEventListener('prefs:langchanged', () => { load(); });
