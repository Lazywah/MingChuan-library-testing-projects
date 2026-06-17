# AI Base Lab（瀏覽器內的 VS Code）

AI Base Lab 讓你在瀏覽器裡使用完整的 VS Code 環境（含終端機、檔案總管、Notebook 編輯），並可把程式碼送到 GPU 執行。入口在「Compute Tasks」分頁的「Notebook」子分頁，或首頁的「AI Base Lab」快速連結。

## 如何開啟 Lab

1. 進入「Compute Tasks」→「Notebook」子分頁。
2. 在「選擇 Image」下拉選單挑一個環境：
   - 🟢 **新手推薦（CPU）**：Code Editor（純編輯，最快啟動）、Dev Tools（Python / C++ / Java 通用）。
   - 🔵 **深度學習（CUDA GPU）**：PyTorch、TensorFlow。
   - 🟣 **LLM 微調與推論**：HuggingFace、llama.cpp、vLLM。
3. 按「**開啟 Notebook**」。第一次開啟約需 5–10 秒建立容器。

## 重要使用規則

- **閒置自動關閉**：閒置 30 分鐘後 session 會自動關閉，但你的檔案會永久保留在個人 volume。
- **送 GPU 訓練**：在 code-server 內寫完程式碼，右鍵選「AI Base: Run on GPU」即可送到 GPU，輸出會串流回 VS Code 的 Output 面板。
- **共用模型快取**：放在 `/opt/models`（唯讀）。
- **安裝自己的套件**：用 `pip install --user`，會裝到 `~/.local/` 並永久保留。
- **停止 Session**：用完可按「停止 Session」釋放資源。

## 個人磁碟配額

每位使用者有個人磁碟配額（預設 10 GB）。需要更多空間時，請聯絡管理員申請提升配額。
