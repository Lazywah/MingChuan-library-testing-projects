# 平台全功能稽核 — 2026-08-27 夜

> **這份文件是邊測邊寫的流水帳**，不是事後整理的報告。
> 順序＝我實際做的順序，包含走錯的路與被推翻的判斷 —— 那些通常比結論有用。
>
> **委託內容**（擁有者 2026-08-27 23:xx）：測目前平台上「所有」功能的可用性與可改進處；
> 影響小的問題直接依我的建議修，影響大的留給擁有者；期間所有測試、決策、修改都要記錄。
> 擁有者不在（到 2026-08-28 08:00），期間授權 commit。

---

## 0. 測試環境與自我約束

| 項目 | 內容 |
|---|---|
| 測試對象 | **正在跑的正式堆疊**（不是另開的測試環境） |
| 服務 | nginx（:80 使用者端 / :8888 管理端）、job-scheduler（:8002） |
| 未啟動 | registry、ollama、portkey、open-webui（image 都在本機，需要時啟動） |
| GPU worker | `gpu-node-01` 最後心跳 **2026-08-26 13:56** → 目前離線 |
| 既有資料 | 使用者 4 筆、訓練任務 0 筆 |

### 我給自己定的四條界線

1. **不讓任何信真的寄出去。**
   `smtp_server` 暫時覆寫為 `127.0.0.1:1`（沒有人在聽 → 連線立刻被拒 → `email_log` 記 `failed`）。
   **測完必須還原**（把兩個鍵設成空字串＝清除覆寫，退回 `.env`）。
   理由：這個專案已經誤寄過兩次（2026-08-15 約 35 封、08-21 又 9 封），
   而「測全部功能」必然要反覆建帳號與登入。
2. **測試帳號一律 `@example.com`** —— RFC 2606 保留網域，`send_email` 內部的閘門會擋，
   這是繞不過的第二道防線（第 1 條是外部防線，改壞了就破功）。
3. **破壞性操作只對我自己建的測試帳號做**，做完清乾淨。
   會動到既有 4 個帳號的事一律不碰，列進「需要擁有者決定」。
4. **不輸入密碼。** 這條不因為擁有者授權而改變。
   管理端用擁有者已登入的 session；使用者端請擁有者按一次登入。

### 已對正式環境做的變更（必須還原）

| 時間 | 變更 | 還原方式 | 狀態 |
|---|---|---|---|
| 08-27 夜 | `smtp_server` → `127.0.0.1`、`smtp_port` → `1` | 兩鍵設空字串（清除覆寫） | ⬜ 待還原 |

---

## 1. 功能清單（來源：`apm.features.json` 39 項 + 路由 128 個端點 + 前端 18 頁）

狀態欄的意思：
- ✅ 測過可用
- ⚠️ 可用但有問題（已記在下面）
- 🔴 不可用
- ⬜ 尚未測
- ⛔ 無法測（環境缺條件，非缺陷）

### 1.1 帳號與權限

| # | 功能 | 狀態 | 備註 |
|---|---|---|---|
| 1 | `auth` 登入與權限（JWT、admin DI 鏈） | ⬜ | |
| 2 | `sso` 單一登入（mock／OIDC） | ⬜ | |
| 3 | `admin-flag` role 與 is_admin 拆開 | ⬜ | |
| 4 | `role-from-email` 依信箱網域判角色 | ⬜ | |
| 5 | `onboarding-modal` 初次登入設定彈窗 | ⬜ | |
| 6 | `profile-unlock` 組織資料上鎖 + 一次性解鎖 | ⬜ | |
| 7 | `org-lookup` 組織對照（系→院、單位、校區） | ⬜ | |
| 8 | `delete-audit` 刪帳號留稽核 | ⬜ | |
| 9 | `quota` 配額與提權審計 | ⬜ | |

### 1.2 AI 功能

| # | 功能 | 狀態 | 備註 |
|---|---|---|---|
| 10 | `chat` AI 助手串流 proxy | ⬜ | 需要 portkey/ollama |
| 11 | `external-ai` 外部 AI 供應商接入 | ⬜ | |
| 12 | `myai-sync` MYAI 廠商同步 | ⬜ | 需連外 |
| 13 | `myai-balance-two-stage` 點數兩段提醒 | ⬜ | 今天剛做 |
| 14 | `rag` 小基知識庫 | ⬜ | 需要 ollama |
| 15 | `token-accounting` Token 記帳 | ⬜ | |

### 1.3 運算與儲存

| # | 功能 | 狀態 | 備註 |
|---|---|---|---|
| 16 | `jobs` GPU 訓練任務排程 | ⬜ | |
| 17 | `worker` GPU Worker 與心跳 | ⬜ | 節點離線 |
| 18 | `lab` 瀏覽器內 VS Code | ⬜ | |
| 19 | `datasets` 資料集與訓練管線 | ⬜ | |
| 20 | `models` 模型與產出物 | ⬜ | |
| 21 | `secrets` 使用者密鑰（AES-256-GCM） | ⬜ | |
| 22 | `storage-lifecycle` 儲存四階段生命週期 | ⬜ | 已知：多為標籤 |
| 23 | `agent-dispatch` Agent 派工 | ⬜ | |
| 24 | `vscode-ext` VS Code 擴充 | ⬜ | |

### 1.4 溝通與營運

| # | 功能 | 狀態 | 備註 |
|---|---|---|---|
| 25 | `email` 寄信與退信處理 | ⬜ | |
| 26 | `admin-alert-mail` 管理員告警信 To/CC | ⬜ | 今天剛做 |
| 27 | `lab-purge-reminder` Lab 銷毀提醒信 | ⬜ | |
| 28 | `announcements` 公告 | ⬜ | |
| 29 | `reports` 報表 | ⬜ | |
| 30 | 問題回報 | ⬜ | |
| 31 | `system-settings` 系統設定 | ⬜ | |
| 32 | `public-settings` 前台唯讀營運設定 | ⬜ | |
| 33 | `smtp-admin-config` SMTP 管理端可設 | ⬜ | |
| 34 | `analytics-grouping` 數據頁分組 | ⬜ | |
| 35 | `admin` 管理端 API | ⬜ | 47 個端點 |

### 1.5 介面與基礎設施

| # | 功能 | 狀態 | 備註 |
|---|---|---|---|
| 36 | `web-ui-v2` 使用者介面 V1（12 頁） | ⬜ | |
| 37 | `admin-ui-v1` 管理端介面 V1（6 頁） | ⬜ | |
| 38 | `web-ui-v1` / `web-ui-v1_5` 舊版仍在服務 | ⬜ | |
| 39 | `infra` 部署編排 | ⬜ | |

---

## 2. 測試流水帳

### T1 — 端點盤點（靜態）

從 `main.py` 的 `include_router` 前綴 + 各 router 的裝飾器推出完整端點表：
**132 個端點**，其中 GET 且無路徑參數的有 54 個（可直接掃）。

> ⚠️ 第一版腳本用 `@router.` 硬抓，得到 128 個且前綴全錯 ——
> 因為 `announcements.py` 與 `reports.py` 各有兩個 router 物件
> （`router` 與 `admin_router`）掛在不同前綴。改成先解析 `include_router`
> 再對應 router 物件名才正確。**盤點工具本身也會有 bug，數字要對得起來才算數。**

### T2 — 權限邊界（意外做成的，但這是有效測試）

第一輪廣掃時我只帶 cookie 沒帶 Authorization，結果 **27 個管理端端點全數 403**，
訊息是「這個功能只有管理員能用」。查下去才發現 cookie 認到的身分是
`Lazy`（role=student、is_admin=0）。

也就是說這一輪等於**用學生身分打了所有管理端端點，全部被正確擋下**：

| 類別 | 端點數 | 學生身分的結果 |
|---|---|---|
| `/api/v1/admin/*` | 15 | 403 ✅ |
| `/api/v1/external-ai/admin/*` | 11 | 403 ✅ |
| `/api/v1/admin/reports/summary` | 1 | 403 ✅ |

**✅ 通過。** 沒有任何管理端端點漏擋。

### T3 — 🔴 cookie 不分 port，兩個介面共用同一份登入身分

追 T2 的原因時發現的**真正問題**（見 §3 問題 1）。

驗證：
- `job-scheduler/app/routers/auth.py:190` 登入時 `response.set_cookie("ai_hud_token", ..., path="/")`
  —— **沒有指定 domain/port**（cookie 規格本來就不分 port）。
- `job-scheduler/app/auth.py:62` `_extract_token()` 會退回讀 `request.cookies.get("ai_hud_token")`。
- 實測：擁有者在使用者端（:80）登入 `Lazy` 之後，管理端（:8888）的 cookie 身分**同時**變成
  `Lazy`，管理端 API 開始回 403。

管理介面前端存的 `admin_hud_token` 是 **2026-08-21 就過期**的殘留（我解 JWT 的 `exp` 確認），
所以管理端實際上一直是靠 cookie 在認 —— 那份 cookie 一被蓋掉，管理端就失去權限。

**這也是本次稽核的實際阻礙**：我的管理端 session 因此消失，
而重新登入需要輸入密碼（我不做）。管理端的**即時**測試因此停在這裡，
改以測試套件與程式碼審查涵蓋（見 T5）。

### T4 — 使用者端 API 全掃（學生身分，24 個端點）

全部回 200 且資料合理，**沒有一個是壞的**。幾個值得記的：

| 端點 | 回應重點 |
|---|---|
| `/auth/usage` | `tokens_used=34000 / limit=5000000`（0.0068%）；重置日 2026-09-01 |
| `/system/public-settings` | 三個旋鈕都回得出來（重置日／逾時／封存天數）|
| `/system/org-options` | 校區 5、學系清單含學院對照 ✅ |
| `/external-ai/my-balance` | `points=2033236, threshold=30000, state="ok"` —— **今天新加的 `state` 欄位在正式環境正確** |
| `/external-ai/my-consumption` | `bound=true`，30 天內用了 689 點 / 1 次 |
| `/jobs/pool-availability` | 兩個池都 `available=false, next_open=null` ← 沒有節點在線，符合現況 |
| `/lab/status` | `stopped`，限制值讀得到（閒置 30 / 硬上限 90 / 每日 360 分） |
| `/assistant/status` | **`ready=true, chunks=40`** —— 小基的知識庫是活的 |

### T5 — 🔴 一個「不存在的 bug」與一個真的 bug（兩次假發現的紀錄）

**假發現 A**：`/api/v1/reports/mine` 回傳 `<!doctype html>` 而不是 JSON。
→ 直連 `:8002` 與經 nginx **都回 401 JSON**，路由完全正常。
→ 是**瀏覽器快取**：加 `cache: 'no-store'` 重打就得到正確的 `200 []`。

**假發現 B**：查快取時發現這個 origin 註冊了 **2 個 service worker**，
一度以為是 SW 攔截了 API。
→ 查 scope 才知道那是 **code-server（Lab）自己的** SW，範圍只在 `/code/<uid>/`，
而且 `navigator.serviceWorker.controller` 是 `null`（這一頁根本沒被 SW 控制）。

**真的問題**（假發現 A 追下去才是重點）：**API 回應完全沒有任何快取標頭**，
只有 `content-type`。這個專案已經被快取咬過三次（見記憶 `static-asset-cache-busting`），
而 API 這一層一直沒設防。

**已修**：在 `main.py` 加一層 middleware，`/api/` 開頭的回應一律
`Cache-Control: no-store`（含 401/403 —— 不加的話「你還沒登入」會被快取起來，
登入後照樣看到錯誤而且重新整理沒有用）。

放後端不放 nginx 的理由寫在程式碼註解裡：nginx 有 **13 個** `/api/v1/...` 的
location 區塊，逐一加 `add_header` 就是 13 個會漏的地方，
而這個專案已經漏掛過兩次 location（一次 405、一次 502）。

驗證（含陽性對照）：

| 路徑 | Cache-Control |
|---|---|
| `/api/v1/system/public-settings` | `no-store` ✅ |
| `/api/v1/auth/me`（401） | `no-store` ✅ |
| `/health` | **無**（陽性對照：證明條件真的在判斷，不是全部都加） ✅ |
| `/V1/index.html` | `no-cache`（nginx 的，沒被動到） ✅ |

測試：`tests/test_api_no_store.py`（3 條，含陽性對照）。

### T6 — 使用者端 12 個頁面逐頁載入

| 頁面 | 結果 |
|---|---|
| `index.html` 首頁 | ✅ 公告 3 則、額度卡（2,033,236）、引導流程、全部入口都在 |
| `usage.html` 使用量 | ✅ 額度／有效期／三個數字／樣本不足的說明都正確 |
| `lab.html` 實驗室 | ✅ 狀態「未啟動」、存檔清單、封存 30 天說明 |
| `jobs.html` 我的訓練 | ✅ 空狀態正確 |
| `datasets.html` 資料集 | ✅ 容量 1 KB / 2.0 GB、空狀態正確 |
| `train.html` 交給平台訓練 | ✅ 上傳區、輪數、逾時 120 分（來自 public-settings） |
| `gpu.html` 入門 | ✅ 正確顯示「目前無可用算力／等待機器上線」（節點確實離線） |
| `news.html` 公告 | ✅ 3 則，含置頂 |
| `report.html` 問題回報 | 🔴 → ✅ **原本壞的，已修**（見下） |
| `docs.html` / `provision.html` / `login.html` | ⬜ 稍後 |

### T7 — 🔴 問題回報頁「暫時讀不到歷史回報」→ 已修（根因是 T5 的快取）

這是 T5 那個快取問題的**使用者可見症狀**，而且它偽裝得很好：
畫面說「暫時讀不到」，看起來像後端掛了，但後端完全正常。

證據（同一個 URL，同一個瀏覽器，差別只在有沒有繞過快取）：

| | status | content-type | Cache-Control | 內容 |
|---|---|---|---|---|
| 沿用快取 | 200 | text/html | （無） | `<!doctype html>…` |
| `cache:'reload'` | 200 | application/json | `no-store` | `[]` |

**它當初怎麼被存進去的**：nginx 若少掛某條 `/api/v1/...` 的 location，
GET 會落到 catch-all（Open WebUI），拿到它的 SPA 首頁 —— **200 而且可快取**。
之後 nginx 補好了，瀏覽器仍然繼續給那份舊 HTML。
`nginx.conf` 裡原本的註解寫「漏掛的症狀是 405」，那只講了 POST 那一半；
**GET 的後果更久，而且會留在使用者的瀏覽器裡**。

**修法（兩層）**：
1. 後端 middleware：`/api/` 一律 `no-store`（防未來）。
2. `chrome.js` / `admin-chrome.js` 包一層 `window.fetch`：同源 `/api/` 請求自動帶
   `cache: 'no-store'`（讓**已經中招**的瀏覽器下次開頁面就恢復）。
   包 fetch 而不是逐一改，是因為使用者端有 34 個 fetch 散在 15 個檔案。

**驗證**：重新載入問題回報頁 → 錯誤消失，正確顯示「你還沒有送出過回報。」

### T8 — 問題回報端對端

| 步驟 | 結果 |
|---|---|
| POST `/reports`（欄位 `body`） | ✅ 201，狀態 `open` |
| GET `/reports/mine` | ✅ 讀得到剛送出的那筆 |
| 空白內容 `"   "` | ✅ 422（`_body_not_blank` validator 有效） |
| 欄位名寫錯（`message`） | ✅ 422（不是安靜接受） |

> ⚠️ **我在正式資料庫留下了一筆測試回報**（id=1，開頭「[稽核測試 2026-08-27 由 Claude 送出]」）。
> 管理端可以直接標成已解決或忽略。這是測試這條流程唯一的方法。

### T9 — 順手修的小東西

- 問題回報的診斷資訊寫「介面版本：**v2**」，但 UI 早在 `1cf0b3b`（2026-08-22）
  就改名成 V1。看回報的人會對著一個不存在的版本查問題。已改成 `V1`。
  （全站掃過，沒有其他使用者可見的 `v2` 殘留。）

---

## 3. 發現的問題

### 問題 1 — 🔴 在使用者端登入會讓管理端安靜地失去權限（反之亦然）

**症狀**：同一台主機上先登入管理端、再到使用者端登入（或反過來），
先前那個介面的身分會被**無聲地換掉**。管理端不會提示「你已被登出」，
只會開始出現「這一段暫時讀不到」之類的錯誤 —— 看起來像後端壞了。

**成因**：兩個介面用**同一個 cookie 名稱** `ai_hud_token`、同一個 host、`path=/`。
**cookie 規格不區分 port**，所以 :80 與 :8888 共用一份。

**為什麼現在沒出大事**：權限檢查看的是解出來的使用者，`require_admin` 正確擋下學生（T2 驗過），
所以**不是提權漏洞**，是「安靜地降權」。

**但它有一個更難察覺的方向**：管理員在自己的機器上開學生視角看看畫面，
回頭管理端就變成那個學生的身分了。若之後有任何端點改成優先信任 cookie，
這就會從「降權」變成「身分混淆」。

**建議修法**（我**沒有動**，因為會影響所有現存 session，屬於影響大的變更）：
1. **最小改動**：管理端登入改用不同的 cookie 名稱（例如 `ai_hud_admin_token`），
   `_extract_token` 依請求進來的 port／路徑決定讀哪一個。
2. **更正確**：管理端走不同的 hostname（例如 `admin.<domain>`），
   cookie 自然隔離 —— 這與 go-live 要處理的正式主機名剛好可以一起做。
3. 兩者都要順手處理：`admin_hud_token` 這個 localStorage 殘留已經過期 6 天卻還留著，
   前端應該在偵測到過期時清掉，而不是留著讓人以為那是有效憑證（我就被誤導了一次）。

---

## 4. 需要擁有者決定的事

| # | 事項 | 為什麼要你決定 |
|---|---|---|
| 1 | cookie 隔離的修法（換 cookie 名 vs 換 hostname） | 會讓**所有現存 session 失效**，且方案 2 與 go-live 的正式主機名綁在一起 |
