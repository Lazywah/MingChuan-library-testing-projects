/* ==========================================================================
 * 文件庫入口的條件式顯示（規格 V3 修正）
 *
 * ZH: 規則是「**文件庫入口在有內容前不出現**」——連到空頁比沒有連結更糟。
 *
 *     這條規則只寫在這一個檔案裡。要顯示入口的頁面只要放一個
 *     `<a href="docs.html" data-docs-entry hidden>…</a>`，其餘交給這支。
 *
 *     為什麼不各頁自己 fetch 一次：那會變成同一條規則的兩份實作，
 *     而日後放了內容還要「記得」回頭改兩個檔案。**靠記得的規則不是約束。**
 *
 * ⚠ 取不到清單時**不顯示**入口（fail closed）。寧可少一個入口，
 *   也不要給出一個可能連到空頁的連結——那正是這條規則要防的事。
 * ========================================================================== */
(function docsEntry() {
    const slots = document.querySelectorAll('[data-docs-entry]');
    if (!slots.length) return;

    // ZH: 檢視用：?docs=on 強制顯示入口，免得為了看樣子去改內容檔。
    const forced = new URLSearchParams(location.search).get('docs');
    if (forced === 'on') { slots.forEach((el) => { el.hidden = false; }); return; }
    if (forced === 'off') return;

    // ZH: cache: 'no-cache' —— 這個檔沒有 ?v= 版號（它是資料不是資產）。
    fetch('docs-content.json', { cache: 'no-cache' })
        .then((r) => (r.ok ? r.json() : null))
        .then((d) => {
            const n = d && Array.isArray(d.items) ? d.items.length : 0;
            if (n > 0) slots.forEach((el) => { el.hidden = false; });
        })
        .catch(() => { /* fail closed：維持隱藏 */ });
})();
