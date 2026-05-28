# 07 — 開發指南 | Development

給後端 / 前端開發者。包含模組擴展、i18n、開發方法學。

---

## 1. 程式碼結構

完整檔案樹見 [`02-architecture.md`](02-architecture.md) §5。核心：

```
job-scheduler/app/
├── main.py              # FastAPI 入口，redirect_slashes=False
├── config.py            # Pydantic Settings + .env + OIDC_ENABLED flag
├── database.py          # SQLAlchemy + WAL + 自動 ALTER 遷移
├── models.py            # ORM (User / TrainingJob / LabSession / UserSecret …)
├── schemas.py           # Pydantic 請求/回應驗證
├── crud.py              # 純 DB 操作（router 呼叫此處）
├── auth.py              # JWT (Bearer header + ai_hud_token cookie)
├── scheduler.py         # 背景排程（timeout / lab idle / storage）
├── sso_client.py        # Mock / CAS / OIDC client，皆繼承 BaseSSOClient
├── sso_policy.yaml      # 切換 provider + mock users
├── scheduler_policy.yaml # GPU 節點池 + lab 配額
├── routers/             # 各 API 群組
└── services/            # lab_manager / secrets_service / quota_service / email_service
```

---

## 2. 模組依賴順序（寫新模組請照這順序）

```
config.py  ─→  database.py  ─→  models.py + schemas.py  ─→  crud.py
                                                              ↓
                                                            auth.py
                                                              ↓
                                                routers/* + services/*
                                                              ↓
                                                          main.py (include_router)
```

---

## 3. 新增 API 端點（4 步）

### Step 1 — `schemas.py` 加請求/回應 model
```python
class MyFeatureCreate(BaseModel):
    name: str
    value: int

class MyFeatureResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
```

### Step 2 — `crud.py` 加 DB 操作
```python
def create_my_feature(db: Session, user_id: str, data: schemas.MyFeatureCreate) -> models.MyFeature:
    obj = models.MyFeature(user_id=user_id, **data.model_dump())
    db.add(obj); db.commit(); db.refresh(obj)
    return obj
```

### Step 3 — `routers/<name>.py` 加 router
```python
from fastapi import APIRouter, Depends
from ..auth import get_current_user

router = APIRouter(tags=["My Feature"])

@router.post("", response_model=schemas.MyFeatureResponse)
def create(payload: schemas.MyFeatureCreate,
           current_user: models.User = Depends(get_current_user),
           db: Session = Depends(get_db)):
    return crud.create_my_feature(db, current_user.id, payload)
```

### Step 4 — `main.py` `include_router`
```python
from .routers import myfeature
app.include_router(myfeature.router, prefix="/api/v1/myfeature")
```

> `redirect_slashes=False`：route 寫 `@router.post("")` 對應路徑 `/api/v1/myfeature`（無斜線）。前端 fetch 也用無斜線。nginx 已有 regex 同時匹配兩種形態（見 `infrastructure/nginx.conf`），新加的 prefix 也照樣做。

---

## 4. 新增資料庫表

1. `models.py` 加 ORM class（繼承 `Base`）
2. `database.py` 的 `init_db()` 內加 `ALTER TABLE` migration（如果只是加欄位到既有表）
3. 重啟服務 — `Base.metadata.create_all(bind=engine)` 自動建新表，既有欄位用 ALTER 加

範例（既有表加欄位）：
```python
try: conn.execute(text("ALTER TABLE users ADD COLUMN auth_source VARCHAR DEFAULT 'local'"))
except Exception: pass
```

---

## 5. i18n 雙語

前端 `web-ui/app.js` 自研 i18n 引擎，4 步：

### 加翻譯
`TRANSLATIONS` 物件下 `zh` + `en` 都加 key：
```js
const TRANSLATIONS = {
    zh: { my_label: "我的標籤", ... },
    en: { my_label: "My Label", ... },
};
```

### HTML 標記
| 屬性 | 用途 |
|---|---|
| `data-i18n="key"` | 文字內容（用 `textContent` 寫入，**HTML 標籤會被當文字**）|
| `data-i18n-placeholder="key"` | input placeholder |
| `data-i18n-aria="key"` | aria-label |
| `data-i18n-title="key"` | title (tooltip) |

```html
<button data-i18n="btn_submit">Submit</button>
<input data-i18n-placeholder="placeholder_name" placeholder="Name">
```

> ⚠️ 圖示 + 文字組合時，把 `data-i18n` 放在內層 `<span>`，否則 icon 會被翻譯文字蓋掉：
> ```html
> <button><ion-icon name="save-outline"></ion-icon><span data-i18n="btn_save">儲存</span></button>
> ```

### 切換語言
sidebar 底部 🌐 icon、或設定頁的「語言」開關，都觸發 `applyLanguage(lang)`。會掃所有 `data-i18n*` 元素更新。

---

## 6. 新增 LLM Provider

1. `portkey/config.yaml` 加 provider 區塊
2. `.env` 加對應 API key（`ANTHROPIC_API_KEY` / `OPENAI_API_KEY` …）
3. `docker compose -f docker-compose.ai-models.yml restart portkey`

---

## 7. 新增 SSO Provider

1. 在 `sso_client.py` 寫 `XxxSSOClient(BaseSSOClient)`，實作：
   - `get_login_url() -> str`
   - `validate_ticket(ticket) -> dict`（回 `{username, email, role, external_id, auth_source}`）
2. `get_sso_client()` 工廠加 `provider == "xxx"` 分支
3. `sso_policy.yaml` 加 `xxx:` 區塊

不必改 `routers/sso.py` 與前端 — 都已抽象。

---

## 8. 本地開發（不用 Docker）

```bash
cd job-scheduler
python -m venv .venv
source .venv/bin/activate         # Win: .venv\Scripts\activate
pip install -r requirements.txt

# 必要環境變數
export JWT_SECRET_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')"
export WORKER_API_TOKEN="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')"
export SECRETS_MASTER_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')"
export DATABASE_PATH="$(pwd)/../data/ai_platform.db"

uvicorn app.main:app --reload --port 8002
```

前端不需要 build；直接打開 `web-ui/index.html`（或用 nginx 服務）。

---

## 9. 開發方法學（精華）

完整版見 `docs/archive/AUDIT-2026-05-14.md` 或舊 `docs/dev/DEV-METHODOLOGY.md`。核心 7 階段：

```
0. 理解 → 1. 探索 → 2. 設計 → 3. 規劃 → 4. 執行 → 5. 清理 → 6. 交付
 拆痛點   掃結構    逼決策    切階段    寫+驗證   刪舊+文件  commit+部署
```

**核心心法**：開發 = 把「不確定」逐步轉換成「確定」的過程。寫程式碼是最後才發生的事。

### 階段 0 — 理解
- 抄一遍使用者的話（避免腦補）
- 拆「症狀 vs 病因」
- 列 N 個獨立痛點

### 階段 1 — 探索
- 小改：直接 Grep + Read
- 大改：派 Explore agent
- **不准在這階段改任何檔案**

### 階段 2 — 設計
- 進入 Plan Mode（強制慢下來）
- 用 `AskUserQuestion` 一次問 1-3 題
- 寫 Plan 檔（Context / 決策 / 預估 / 驗收 / 不做什麼）

### 階段 3 — 規劃
- 拆 3-5 個 Phase
- 每 Phase 能獨立驗證
- 用 TodoWrite 追進度

### 階段 4 — 執行
- 每改一段就跑廉價驗證（`node --check` / `python -c` / `nginx -t`）
- 卡住 > 30 min → 拆小 todo 或回 Plan

### 階段 5 — 清理
- 舊 router / schema / CRUD / CSS / i18n 全清乾淨
- 文件同步更新
- v2.x roadmap 寫「不做什麼」

### 階段 6 — 交付
- commit log 清楚（為什麼 > 做了什麼）
- `/health` 通過、容器 healthy
- 至少 1 個 happy-path 手動驗證

### 5 個反 Pattern（看到就停）

| Anti-pattern | 修正 |
|---|---|
| 跳過階段 0-2 直接寫 code | 進 Plan Mode 先列問題 |
| 一個 Phase 改 20+ 檔 | 拆成多 Phase，每個 5-10 檔 |
| 舊 code 用 `/* */` 註解掉「之後再刪」 | 直接刪，git 有歷史 |
| 「未來會用、先預留欄位」 | v2.x 真要做時自己 ALTER；現在用 Protocol + 文件預留擴充點 |
| commit 訊息只寫「做了什麼」不寫「為什麼」 | 標題寫**意圖**，bullet 寫改了什麼有意義的東西 |

---

## 10. 程式碼慣例

### 雙語註解
```python
# ZH: 中文說明 | EN: English description
```

### 模組頭部 docstring（必有）
```python
"""
==============================================================================
Module N: 模組名稱 (English Title)
==============================================================================
ZH: 用途、流程、模組化設計說明
EN: Same as above in English
==============================================================================
"""
```

### Commit message
```
<新增|修正|優化|重構>: <意圖標題 ≤70 字>

- <改動 1 與其原因>
- <改動 2>
- <改動 3>
```

範例：
```
修正: nginx + FastAPI trailing-slash 互打 307 連鎖

- nginx.conf: 9 個 location 改 regex 同時匹配有/無斜線
- main.py: FastAPI 加 redirect_slashes=False
- 結果：scheduler 不再噴 307，前端 fetchJobs 不再每 5s 噴錯
```

---

## 11. 廉價驗證指令速查

| 動作 | 指令 |
|---|---|
| JS 語法 | `node --check web-ui/app.js` |
| TS 語法 | `npx tsc --noEmit` |
| Python import | `python -c "from app.routers import xxx; print('ok')"` |
| nginx 設定 | `docker compose exec nginx nginx -t` |
| compose YAML | `docker compose config` |
| API 健康 | `curl http://localhost/health` |
| FastAPI route 樹 | `curl http://localhost:8002/openapi.json \| jq '.paths \| keys'` |

每改一段就跑一次。讓問題在改完 30 秒內就被發現，比 30 分鐘後 debug 快。

---

## 下一步

- [`05-api-reference.md`](05-api-reference.md) — API 完整參考
- [`08-status-and-roadmap.md`](08-status-and-roadmap.md) — 已知議題與 v2.2 計畫
- [`archive/PLAN-v2.0-lab.md`](archive/PLAN-v2.0-lab.md) / [`archive/PLAN-v2.1-sso-oidc.md`](archive/PLAN-v2.1-sso-oidc.md) — 歷史 plan 範本
