# 08 — 現況與計畫 | Status & Roadmap

| 章節 | 用途 |
|---|---|
| §1 完成的衝刺 | v2.0 / v2.1 主要里程碑 |
| §2 已知議題 | 仍未解決、不影響主流程的事項 |
| §3 v2.2 Roadmap | 排程中的下一輪 |
| §4 長期願景 | 還沒排期的想法 |

> ⚠ **維護這份文件的方式：查 `git log`，不要照記憶寫。**
> 2026-08-30 更新時發現 §2 有一半的議題**早就不成立了**
> （Hub 的 Coming Soon 已隨 V0 下線、`app.js` 從 1000+ 行變成 156 行），
> 而它們在文件上還掛著。過期的待辦比沒有待辦更糟 —— 會讓人去修不存在的東西。

---

## 1. 完成的衝刺

### 2026-05 第一衝刺 — MVP
- Chat 串流 proxy 到 Portkey、`session_id` 由請求帶或自動生成
- Scheduler 每 5 分鐘超時清理
- slowapi rate limit、`hmac.compare_digest` 防時序攻擊
- 全面改 `datetime.now(timezone.utc)`（棄用 `utcnow()`）
- Worker race condition fix：atomic SQL UPDATE + rowcount 檢查
- 50 個測試（22 CRUD + 28 API）通過

### 2026-05 第二衝刺 — 品質提升
- `GET /users` 從 N+1 改 outerjoin 單查詢
- `require_admin` 進 FastAPI DI 鏈
- Pydantic v2 全面改 `ConfigDict`
- 補 SQLAlchemy ForeignKey（CASCADE / SET NULL）
- `WorkerHeartbeat` 表 + `POST /worker/heartbeat` 端點
- 72 個測試通過、評分 77.4 → 87.6

### 2026-05 第三衝刺 — v1 Colab 風格 Notebook
- Monaco Editor 整合（後被 v2.0 Lab 取代）
- GPU Worker 支援任意 docker_image / inline_code / entry_args
- Notebook 進度解析格式（HF / llama.cpp）

### 2026-05 第四衝刺 — v2.0 Lab 上線
- code-server (VS Code in Browser) 取代 v1 偽 Notebook
- per-user volume (`home_<user_id>`)、共享 `shared_models` (read-only)
- 7 個學期鎖定 base image (PyTorch / TF / HF / llama.cpp / vLLM / dev-tools / code-server)
- AES-256-GCM `user_secrets` + 提交 Job 自動注入
- `quota_grants` 提權審計 + `user_storage_state` 4 階段生命週期
- `admin_actions` audit log + `/admin/audit` 端點
- VS Code Extension `aibase-runner`：右鍵 Run on GPU → SSE 串流回 Output Panel
- v1 Notebook 完整下線（DROP TABLE + 移除所有 router / schema / CRUD / CSS / i18n）

### 2026-05 第五衝刺 — v2.1 SSO OIDC
- `OIDCSSOClient` 繼承 `BaseSSOClient`，手寫 httpx + python-jose
- `auth_source` (local/sso_mock/sso_cas/sso_oidc) + `external_id` (Microsoft oid)
- SSO 使用者本機改密碼擋下（schema + UI 雙層）
- 識別優先序：external_id → email → username + `get_user_by_external_id`
- `upgrade_to_sso` 自動把 local 升級為 sso_oidc（含 admin provision 過的）
- PENDING fail-safe：`client_id="PENDING"` 自動降級 mock + warning
- Admin 完全分離 port 8888；Mock SSO 不曝光於 UI

### 2026-05 第六衝刺 — Notebook 測試後續修正
測試過程修了 9 個 bug：
- Lab IIFE 用錯 localStorage key（`jwt` → `ai_hud_token`）
- Lab / Secrets `_t()` 找不到翻譯（`window.translations` → 檔內 `TRANSLATIONS`）
- i18n 字串含 `<strong>` 顯示為純文字
- Lab `existing` session 查詢漏 `stopped` 狀態 → UNIQUE 撞 INSERT
- `scheduler_policy.yaml` `default_image` 應為 code-server（不是 pytorch）
- Lab `/start` `base_image` 是 query param 應為 body
- code-server Dockerfile：Node 18 → 20、root rm cleanup、CRLF → LF、`--auth none`
- nginx `/code/<uid>/` 需 URI rewrite 去前綴
- nginx + FastAPI trailing-slash 互打 307 連鎖 → regex location + `redirect_slashes=False`
- Cookie 改 HttpOnly + logout `delete_cookie`

---

### 2026-06 ~ 08 — v2.2 ~ v3.9（196 個 commit）

> 這一段太長，只列**改變了平台形狀**的事。逐項請查 `git log`。

**整合**
- **MYAI 廠商整合** —— 唯讀同步、email 綁定、交易日誌、Token 餘額、
  低點數提醒、模型對應表、每月自動補點、**自動開通**（官方批次註冊 xlsx）
- **SSO OIDC** —— 確認 MCU 是**自建 OIDC**（`auth.mcu.edu.tw`）不是 Entra；
  discovery 驅動、`username_claim="sub"`。go-live 只差非程式的三項
- **小基（RAG 助手）** —— 客服模式 + 程式家教模式；嵌入模型換 `bge-m3`、
  對話模型換 `llama3`（前者在繁中的鑑別差距只有 +0.066，排序接近隨機）

**Lab / GPU**
- Lab 支援**多份存檔**、**互動式 GPU**（獨佔鎖）、最長借用時間與三段預警、
  每日額度執行、磁碟配額每日量測
- **GPU 節點管理** —— 可排程時段、開關、池別覆蓋、撞名偵測
- 排隊時顯示位置與等待原因（只在真的在排隊時）

**介面**
- 三個 UI 版本改名 **V0 / V0.5 / V1**，根路徑導向 V1
- 導覽列改成「首頁 + 三個分類下拉」，**MYAI 獨立成頁**（`myai.html`），
  `provision.html` 併入後移除
- 顯示設定（字級 / 語言 / 色系）**跟帳號走**
- 說明小字收成**資訊 icon**（tooltip 抽成兩端共用的 `tip.js`）

**管理端**
- 系統設定頁（7 個營運旋鈕，runtime 生效）、組織對照表可編輯與匯出匯入
- 問題回報（主旨、類別、彈窗、已回覆唯讀）
- 公告：**中英雙版**、附件、內文網址自動變連結
- **各系院單位的使用統計** —— 兩種比例（佔比 / 滲透率）

**維運**
- `.env.example` 單一真相 + `setup_env --check` 漂移稽核
- `deploy_check.py` 開機前健檢
- 一整組機械檢查：i18n、JS 語法、共用檔一致、nginx 路由、時區、
  未翻譯中文、重複定義、錯誤訊息中文、載入的 `<script>`

---

## 2. 已知議題（2026-08-30 逐項查證過）

### 🔴 上線前一定要處理

| 項目 | 現況 | 為什麼要緊 |
|---|---|---|
| `myai_provision_email` = 0 | 不寄開通通知 | 學生不知道自己開通了 |
| `myai_initial_credit` = 0 | 不轉初始點數 | 學生進去是 0 點 |
| 告警信收件人**空的** | 完全不寄 | 系統出事沒有人知道 |
| 退信回收 IMAP **未設定** | 沒在跑 | 寄失敗的信會永遠停在「已交付」 |
| 廠商轉點端 **500** | 所有路徑都失敗 | 自動開通給點做不到（**廠商端問題**，錯誤報告已備妥） |

### 🟡 中優先

| 議題 | 影響 | 修法 |
|---|---|---|
| 44 個行政單位缺英文名 | 管理端英文模式下那一欄只能維持中文 | 官網上沒有，要問人 |
| SSO 尚未 go-live | 只能用本機帳號 | 缺**非程式**三項：正式主機名、TLS+nginx:443、redirect_uri 回報 IT |
| 台北 30 台 GPU 節點未連接 | 只有桃園一台 5090 | 真正的瓶頸是**映像頻寬**（單張 20G×30 台），台北需前哨 registry cache |
| GPU 狀態頁尚未實作 | 使用者看不到「現在忙不忙」 | 資料齊了（`/jobs/pool-availability` 等），只差介面 |
| 聊天模組整合測試單薄 | 覆蓋缺口 | 需 mock Portkey 或 httpx MockTransport |

### 🟢 低優先 — 技術債

| 議題 | 說明 |
|---|---|
| 無 Alembic migration | 現況靠 `create_all` + `database.py` 的手動 `ALTER TABLE`。⚠ **新增欄位到既有的表一定要加那一行**，漏了會在上線的資料庫上炸 |
| 「帶 token 下載」有三份實作 | `jobs.js` / `analytics.js` / `platform.js` 各一份；`Chrome.download()` 是第四份的收斂點，但那三份沒動（改了驗不了比留著更危險） |
| `batch_update_tokens` 迴圈 N+1 | 批次操作慢。改 bulk UPDATE |
| CAS SSO 只有框架 | **不再需要** —— MCU 是自建 OIDC。留著的 `sso_cas` 分支是死路 |
| 手機版頂部列佔 22% 畫面 | 固定之後折成三行（375px 時高 175px）。已試過 `nowrap`，量出來更糟 |

---

## 3. 下一輪的候選

> 沒有排期。依「**做了會改變什麼**」排序，不是依難度。

### 使用者看得到的

| 事 | 為什麼 |
|---|---|
| **GPU 狀態頁** | 「任務沒動」時目前無處可查。資料都有，只差介面 |
| **未登入看得到公告** | 最需要看公告的時刻正是**登入不了**的時候。要先決定放哪一頁 |
| 手機版頂部列 | 三選一：維持現狀 / 手機不固定 / 收合式選單 |

### 平台體質

| 事 | 為什麼 |
|---|---|
| **Lab 容器網路隔離** | 見下方。威脅低但真實 |
| Alembic | 手動 `ALTER TABLE` 已經踩過一次「漏了就炸」 |
| 收斂「帶 token 下載」 | 同一條規則四份實作 |

### Lab 容器網路隔離（原 v2.2 主項目，仍未做）

**問題**：所有 lab 容器掛同一個 `ai-platform-net`，學生 A 可從自己容器內連到
學生 B 的 code-server。

**威脅模型**：教學平台、低威脅 —— 要求攻擊者知道對方 UUID 且刻意為之。

**建議解法**：per-user docker network（新檔 `services/network_manager.py`，
`lab_manager` 啟停時建立／清理）。

> ⚠ Docker bridge driver 預設限 30 個網路 —— 同時開超過 30 個實驗室需要
> swarm overlay。以目前一台 5090 的規模不會遇到，台北接上之後要重新評估。

### 其他候選

- **Lab secrets 注入稽核** —— 誰何時讀取了 secrets（目前注入後即明文）
- **SSO 身分 → role 自動對應** —— 由 IdP 提供教職員身分欄位
- **id_token jwks 簽章驗證** —— 目前未驗 RSA 簽章（信任 token endpoint 走 HTTPS）

---

## 4. 長期願景（未排期）

- 台北 30 台 GPU 節點併入排程（**先解映像頻寬**，不是先解連線）
- 跨校區的作業佇列與優先序
- 文件庫累積到足以當教材

---

## 5. 這份文件怎麼維護

1. **查 `git log`，不要照記憶寫。**
2. 每一項議題寫的時候**去程式碼確認它還在**。2026-08-30 這次就刪掉了
   四項早就不存在的（Hub Coming Soon、`app.js` 過長、系統設定輸入框、
   CAS 未實作）。
3. 「刻意不做」的事**不要寫進議題** —— 那些在
   [12-功能說明.md](12-功能說明.md) §3。混在一起會讓人去「修」一個決定。
