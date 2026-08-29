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
    // ZH: null = 還不知道（fetch 沒回來）。**只有 true 才解除隱藏** —— fail closed。
    let state = null;

    /* ZH: 把已知的決定套到 root（預設整份文件）底下的槽位。
     *
     * ZH: 🔴 為什麼要暴露成 window.DocsEntry：導覽列的文件庫項目是
     *     chrome.js 動態建的，**比這支的第一次掃描還晚**。原本的寫法在載入時
     *     就把 slots 抓定了，那個項目永遠不會被解除隱藏 —— 而且不會報錯，
     *     只是「文件庫入口在導覽列上永遠不出現」。
     * ZH: ⚠ 規則本身仍然只有這一份實作。呼叫端只是說「我又多了槽位」，
     *     不重新判斷要不要顯示。
     */
    function apply(root) {
        if (state !== true) return;
        (root || document).querySelectorAll('[data-docs-entry]')
            .forEach((el) => { el.hidden = false; });
    }
    window.DocsEntry = { apply };

    // ZH: 檢視用：?docs=on 強制顯示入口，免得為了看樣子去改內容檔。
    const forced = new URLSearchParams(location.search).get('docs');
    if (forced === 'on') { state = true; apply(); return; }
    if (forced === 'off') { state = false; return; }

    // ZH: cache: 'no-cache' —— 這個檔沒有 ?v= 版號（它是資料不是資產）。
    fetch('docs-content.json', { cache: 'no-cache' })
        .then((r) => (r.ok ? r.json() : null))
        .then((d) => {
            const n = d && Array.isArray(d.items) ? d.items.length : 0;
            state = n > 0;
            apply();
        })
        .catch(() => { state = false; /* fail closed：維持隱藏 */ });
})();
