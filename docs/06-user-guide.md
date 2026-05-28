# 06 — 使用者操作手冊 | User Guide

> 給學生、老師看的介面操作說明。Admin 看 [`04-operations.md`](04-operations.md)。

---

## 1. 角色與權限

| 角色 | 訓練任務 | AI 助手 | Admin 介面 |
|---|---|---|---|
| **student** | 僅自己 | ✅ | ❌ |
| **teacher** | 全系統（唯讀）| ✅ | ❌ |
| **admin** | 全系統（含取消、改優先級）| ✅ | ✅ port 8888 |

帳號由管理員配發；Token 月度配額所有角色共用同一機制（admin 可個別調整）。

---

## 2. 登入

### 方式 1 — 學校 SSO（正式環境）

1. 開瀏覽器到 `http://<服務層 URL>/train/`
2. 點 **「使用學校帳號登入」**
3. 跳轉到學校登入頁（Microsoft Entra / CAS）→ 輸入學校帳密 → MFA
4. 自動回到平台，已登入

### 方式 2 — Mock SSO（教學環境 / 開發）

直接打 `http://<URL>/api/v1/sso/login` → 下拉選測試帳號（如 T1090001）→ 進入。

### 方式 3 — 本機帳號（管理員）

`http://<URL>:8888/` → 輸入 admin username + password。

### 首次登入

會看到「Welcome to AI Base!」教學面板（介紹三大板塊）。勾「不再顯示」可關閉；想再看可到 設定 → 教學手冊 → 開啟教學。

---

## 3. 運算任務（Compute Tasks）

主介面三個子分頁：

### Notebook 分頁（v2.0 Lab，**推薦**）

VS Code in Browser，完整 IDE 體驗。

**啟動**：
1. 從「選擇 Image」下拉選一個（預設 `Code Editor` = 純編輯環境；想要 PyTorch 訓練選 `PyTorch (CUDA 12.8)` 等）
2. 點 **「開啟 Notebook」** → 5-10 秒跳到 VS Code 分頁

**裡面可以做的事**：

| 功能 | 操作 |
|---|---|
| 寫程式 | `.py` / `.ipynb` / `.cpp` / `.sh` 任意檔案，語法高亮 + 自動補全 |
| 終端機 | Ctrl+\` 開 bash（`pip install --user xxx` 一定要加 `--user`，否則重啟掉光）|
| 檔案總管 | 左側 Explorer 看 `/home/coder/`，可拖曳上傳 / 下載 |
| Notebook | 內建 Jupyter，逐格執行 |
| Git | 預裝 `git` + `gh` CLI |
| **AI Base: Run on GPU** | 右鍵 Python 檔 / Notebook cell → 送 GPU 訓練，輸出串到 VS Code Output Panel |
| **AI Base: Pick GPU Node** | Command Palette (Shift+Cmd+P) 選特定 GPU 節點 |
| **AI Base: Pick Framework Image** | 切換 Run on GPU 用的 image |

**檔案保留規則**：

| 位置 | 跨次保留？ |
|---|---|
| Base image（系統工具 / 預裝 Python 套件）| ✅ 學期內 image 鎖定 |
| `/home/coder/`（你的工作目錄、`~/.local/`、`~/.cache/huggingface`）| ✅ 永久（per-user volume）|
| `/opt/models/`（共享模型快取，唯讀）| ✅ 所有使用者共用 |

**自動關閉**：
- Idle 30 分鐘自動停容器（檔案不會丟）
- 每日累計使用 360 分鐘上限（超過要等明天或請 admin 加額）

### High Compute / Mid-Low Compute 分頁（快速表單）

直接填表單派發任務、不開 VS Code：

| 欄位 | 說明 |
|---|---|
| 任務名稱 | 自訂 |
| 資料集 | 上傳 `.csv` / `.jsonl` / `.zip`，系統自動推薦 epochs / batch_size |
| 派發任務 | 送出 |

任務送出後到右側「佇列」看進度條 + 即時 log。

---

## 4. AI 助手（Hub）

進入 AI 大廳 → 4 個分類：**AI 模型 / 文書寫作 / 影音創作 / 生活翻譯**。

| 功能 | 說明 |
|---|---|
| 串流回應 | 模型邊想邊回，不用等完整文字 |
| 多對話 | 左側「+ 新對話」開獨立 thread；點歷史可切換 |
| 帳號隔離 | 不同登入只看自己的對話歷史 |
| 切換分類 | 對話視窗上方「🔙 返回大廳」 |

---

## 5. 系統設定（Settings）

| 區塊 | 用途 |
|---|---|
| **Token Resources** | 圓環進度條：已用 / 總配額 / 重置日 |
| **個人資料** | 唯讀（姓名、email、學系、認證來源、登入紀錄、Token 用量）|
| **變更密碼** | 依登入來源分流：本機帳號顯示舊密碼+新密碼表單；SSO 帳號顯示「請至 Microsoft / CAS 改密碼」連結 |
| **Secrets 管理** | API key 倉庫（HF_TOKEN / WANDB_API_KEY / OPENAI_API_KEY 等）|
| **外觀** | 深色 / 淺色主題（也可在 sidebar 底部快速切）|
| **語言** | 中文 / English 即時切（也可在 sidebar 底部）|
| **教學手冊** | 重開首次登入導覽 |
| **登出** | 清 token + cookie |

### Secrets 用法

API key 需要存放怎麼辦？**不要寫死在程式裡**。

1. 設定 → Secrets 管理 → 新增
2. 填入 `Name`（如 `OPENAI_API_KEY`，需符合 ENV var 格式）+ `Value`
3. 提交 GPU 任務或啟動 Lab 時，**系統自動注入到容器環境變數**
4. 程式碼裡：`os.environ["OPENAI_API_KEY"]` 就拿得到

**安全保證**：value 用 AES-256-GCM 加密存 DB、管理員也讀不到（只能看到 masked）。只能更新或刪除。

---

## 6. 老師專屬功能

`role=teacher` 登入後，介面與學生 95% 相同，差別：

- **運算任務**頁面看得到**全系統**的任務（非僅自己）
- 任務卡片顯示提交者帳號，便於課堂掌握進度
- **無法取消**他人任務（admin 才能）

其餘（AI 助手、設定、Token 配額）完全相同。

---

## 7. 管理員功能

`role=admin` 帳號可進 `http://<URL>:8888/`。

詳見 [`04-operations.md`](04-operations.md)。摘要：使用者管理（3-tab 分頁、Provision、Reset）、模型管理、全域任務（強制取消、調優先級）、設定檔線上編輯、數據分析、Audit log。

---

## 8. FAQ

### AI 回到一半變紅色錯誤？
通常是配額用完或 LLM gateway 短暫斷線。系統會保留已生成的文字；可重發訊息，或設定頁查 Token 餘額。

### 切換中英文？
設定 → 語言（或 sidebar 底部 🌐 icon）。即時生效。

### 看 Token 配額？
設定 → 第一個區塊「Token Resources」。

### Notebook 卡在 "Stopped" 但點不動？
- 重整一次頁面
- 看是不是每日 360 min 用完（找 admin 重置）
- 看 Image 下拉是不是選了沒 build 的（請 admin 確認）

### Notebook 內 pip install 套件下次不見了？
記得加 `--user`：`pip install --user transformers`。這樣會裝到 `~/.local/`，跨 session 保留。否則裝到 image 內，容器停掉就沒了。

### 跑 GPU 但找不到 CUDA？
- 確認 Notebook image 選的是 PyTorch / TensorFlow / etc（不是純 Code Editor）
- 啟動的 Lab 容器本身是 CPU 編輯環境，CUDA 在 Run on GPU 派出去的訓練容器才有
- 訓練容器內：`import torch; torch.cuda.is_available()` 應為 `True`

### 忘記密碼？
- 本機帳號：登入頁點「忘記密碼」→ 系統寄信
- 學校 SSO：到學校 IT 密碼重設頁（設定 → 變更密碼 區有連結）
