/* ==========================================================================
 * [畫面: 體驗現有模型訓練] — 使用者在這裡要完成：選一種範例、選一種開始的方式。
 *
 * ZH: v4.36（擁有者 2026-10-02，接管者回饋 2026-09-30）改成「種類 × 方式」：
 *       種類：貓狗圖片／學生及格表格／餐廳評論文字（決定標題與說明）
 *       方式：先體驗看看／用自己的資料／用自己的程式（三張卡 → train.html?task=&mode=）
 *     以前的「學習程式碼」主按鈕會在這裡直接開實驗室，所以這支要查算力、查實驗室配額；
 *     那顆按鈕拿掉之後這些都不需要了 —— 排隊與算力由訓練頁自己顯示。
 * ========================================================================== */
const $ = (id) => document.getElementById(id);

// ── 範例種類（v4.19）─────────────────────────────────────────────────
// ZH: 選哪一種決定畫面上四段文案，以及三張方式卡帶過去的內建任務。
//     用 T() 一個個寫是為了 check_i18n 抓得到 key。
const KINDS = {
    cats_dogs: {
        task: 'image_classification',
        h1:   () => T('gpu_h1', '做出一個能分辨貓和狗的模型'),
        sub1: () => T('gpu_sub1', '用學校的 GPU，訓練通常不到一分鐘。'),
        s1d:  () => T('gpu_s1d', '每個類別一個資料夾。用範例的話這步跳過。'),
        s3d:  () => T('gpu_s3d', '正確率、以及模型判斷錯的那幾張圖。'),
        keys: { h1: 'gpu_h1', sub1: 'gpu_sub1', s1d: 'gpu_s1d', s3d: 'gpu_s3d' },
    },
    tabular: {
        task: 'tabular_classification',
        h1:   () => T('gpu_h1_tab', '做出一個能預測學生會不會及格的模型'),
        sub1: () => T('gpu_sub1_tab', '用一份表格（CSV），幾秒鐘就訓練完。'),
        s1d:  () => T('gpu_s1d_tab', '一份 CSV：一列一筆、一欄一個特徵、其中一欄是答案。用範例的話這步跳過。'),
        s3d:  () => T('gpu_s3d_tab', '正確率、以及模型猜錯的那幾筆。'),
        keys: { h1: 'gpu_h1_tab', sub1: 'gpu_sub1_tab', s1d: 'gpu_s1d_tab', s3d: 'gpu_s3d_tab' },
    },
    text: {
        task: 'text_classification',
        h1:   () => T('gpu_h1_text', '做出一個能分辨評論是正面還是負面的模型'),
        sub1: () => T('gpu_sub1_text', '用一份句子＋答案的表格（CSV），幾秒鐘就訓練完。'),
        s1d:  () => T('gpu_s1d_text', '一份 CSV，兩欄：句子與答案。用範例的話這步跳過。'),
        s3d:  () => T('gpu_s3d_text', '正確率、模型猜錯的那幾句，還可以拿自己寫的句子試。'),
        keys: { h1: 'gpu_h1_text', sub1: 'gpu_sub1_text', s1d: 'gpu_s1d_text', s3d: 'gpu_s3d_text' },
    },
};
let kind = 'cats_dogs';

// ZH: 同時改 data-i18n 與文字：prefs.js 換語言時是重掃 data-i18n，只改文字會跳回貓狗。
function setKind(k) {
    if (!KINDS[k]) return;
    kind = k;
    const c = KINDS[k];
    $('kind-seg').querySelectorAll('button').forEach((b) =>
        b.setAttribute('aria-pressed', String(b.dataset.kind === k)));
    [['gpu-title', 'h1'], ['gpu-sub1', 'sub1'], ['gpu-s1d', 's1d'], ['gpu-s3d', 's3d']]
        .forEach(([id, key]) => {
            const el = $(id);
            if (!el) return;
            el.setAttribute('data-i18n', c.keys[key]);
            el.textContent = c[key]();
        });
    // ZH: 三張方式卡都帶著這一種過去 —— 他在這裡選了表格，過去不該又是圖片。
    document.querySelectorAll('.modes a[data-mode]').forEach((a) => {
        a.href = `train.html?task=${encodeURIComponent(c.task)}&mode=${a.dataset.mode}`;
    });
}
$('kind-seg').addEventListener('click', (e) => {
    const b = e.target.closest('button[data-kind]');
    if (b) setKind(b.dataset.kind);
});
setKind(kind);
