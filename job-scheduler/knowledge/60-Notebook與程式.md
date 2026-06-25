# 在 Notebook / Lab 裡寫程式

AI Base Lab 是瀏覽器內的完整 VS Code（code-server），可寫 Python、跑終端機、編輯 Jupyter Notebook，並把程式送到 GPU 執行。本頁整理寫程式時最常遇到的問題。

## 程式家教小基（在這裡幫你看程式）

平台的「小基」助手有兩種模式，右下角浮動泡泡可切換：

- **客服**：回答平台操作問題（公開，不需登入）。
- **程式家教**：陪你看程式碼、解釋錯誤、引導修正（**需登入**）。

開啟程式家教的兩個入口：

1. 右下角泡泡 →上方切到「**程式家教**」。
2. 在「Compute Tasks → Notebook」頁，按「**問程式家教**」按鈕。

程式家教可以**讀你自己 Lab 裡的檔**：在泡泡按「📎 附加 Lab 檔案」→ 選一個檔 → 再問問題（例如「幫我看這段為什麼會錯」）。前提是你的 Lab 正在執行中；附檔只會讀你自己的容器，不會看到別人的檔案，也不會儲存你的對話。

## 安裝套件

- 用 `pip install --user <套件>`，會裝到 `~/.local/`，**重開 Lab 後仍保留**。
- 不要用 `sudo pip`；容器內沒有 root 權限需求，`--user` 即可。
- 想固定環境，可在專案放 `requirements.txt`，用 `pip install --user -r requirements.txt`。

## 送到 GPU 執行

1. 在 code-server 寫好訓練程式。
2. 右鍵選「**AI Base: Run on GPU**」。
3. 程式被送到 GPU 節點執行，輸出會**串流回 VS Code 的 Output 面板**。
4. GPU 為共用資源：若目前有人在用，任務會排隊；單機環境下 Ollama 與訓練無法同時佔用 GPU。

## 常見錯誤與排解

- **`ModuleNotFoundError`**：套件沒裝或裝錯環境。用 `pip install --user` 重裝，並確認用的是同一個 Python。
- **`CUDA out of memory`**：模型/批次太大。調小 `batch_size`、用較小模型，或改用 CPU 環境先驗證邏輯。
- **`Permission denied` 寫檔**：請寫在 `/home/coder`（你的家目錄）底下，不要寫系統路徑。
- **改完檔案沒生效**：確認存檔，必要時重啟 kernel / 重跑 cell。
- **Lab 開啟後一片空白或 503**：容器剛啟動需幾秒，稍候重整即可。

## 檔案保存

- 你的檔案存在個人 volume（容器內 `/home/coder`），**閒置自動關閉不會刪檔**，下次開 Lab 仍在。
- 個人磁碟預設配額 10 GB，需要更多請聯絡管理員。
