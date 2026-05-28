# 08 — 現況與計畫 | Status & Roadmap

| 章節 | 用途 |
|---|---|
| §1 完成的衝刺 | v2.0 / v2.1 主要里程碑 |
| §2 已知議題 | 仍未解決、不影響主流程的事項 |
| §3 v2.2 Roadmap | 排程中的下一輪 |
| §4 長期願景 | 還沒排期的想法 |

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

## 2. 已知議題（非阻擋）

### 🟡 中優先

| 議題 | 影響 | 修法 |
|---|---|---|
| 11 個 AI Hub 功能為 Coming Soon | 平台功能顯著不完整 | 各需不同後端（圖片生成 API、RAG 知識庫等） |
| `batch_update_tokens` 迴圈 N+1 | 批次操作慢 | 改 SQLAlchemy bulk UPDATE |
| 聊天模組無整合測試 | 覆蓋缺口 | 需 mock Portkey 或 httpx Mock Transport |

### 🟢 低優先 — 技術債

| 議題 | 影響 | 說明 |
|---|---|---|
| 真實 CAS SSO 未實作 | 只有 mock + OIDC | `sso_client.py` 有框架無 ticket 驗證 |
| `app.js` > 1000 行 | 前端維護難度高 | 未來拆 ES6 模組 |
| `crud.append_job_metric` bare except | 可能掩蓋錯誤 | 改 `logger.warning` |
| 無 Alembic migration | 結構變更需重啟 | 開發階段 `Base.metadata.create_all` 可接受；上線前導入 |
| 系統設定 — 輸入框管理 | 移除危險的「直接編輯 .env」後留下 placeholder | `routers/system.py` 已有空 router；前端 `admin-ui/index.html` 已有佔位卡 |

---

## 3. v2.2 Roadmap

> 完整文件：歷史 `docs/dev/v2.2-roadmap.md` 已合併到本檔。

### 主項目：Lab 容器網路隔離

**問題**：所有 lab 容器掛同 `ai-platform-net`，學生 A 可從自己容器內 `curl http://cs-<other_uid>:8080/` 繞過 nginx auth_request 讀別人工作目錄。

**威脅模型評估**：教學平台、低威脅。要求攻擊者 (a) 知道對方 UUID (b) 願意在自己容器內主動 curl 別人 — 明顯異常。

**解法選項**：

| 方案 | 複雜度 | 工時 | 評估 |
|---|---|---|---|
| A. nginx + shared secret header + socat sidecar | 中 | 4-6 hr | code-server 原生不支援 header-based auth，需 OAuth proxy sidecar |
| **B. per-user docker network**（推薦）| 中 | 4-6 hr | nginx 動態 join、code-server `--auth none` 仍可、不動其他元件 |
| C. Docker swarm overlay | 高 | 8-12 hr | 跨 host 部署才有意義 |

**B 方案實作藍圖**：
1. 新檔 `services/network_manager.py`：`create_user_network() / connect_nginx() / cleanup_orphan()`
2. `lab_manager.py` `lifecycle.start()`：`network="ai-platform-net"` → `f"lab-net-{user_id}"`
3. `stop_session()` 加 `network_manager.disconnect_and_cleanup(user_id)`
4. scheduler 啟動 hook：`cleanup_orphan_networks()`
5. **nginx 不用動**（DNS 仍解析 `cs-<uid>`，nginx 動態加入 user network 後仍可 proxy）

**風險點**：
- nginx 動態 join network → 立即 proxy 之間時序，可能需 retry
- Orphan 清理（容器死亡但 network 沒清）
- Docker bridge driver 預設限 30 個網路；user > 30 需 swarm overlay

**遷移風險**：低 — 不動 nginx config / 前端 / DB schema / API；全在 lab_manager + 新檔。

### 其他 v2.2 候選

- **Lab secrets 注入稽核**：誰何時讀取了 secrets（目前注入後即明文，container exec 可讀）
- **SSO group claim → role 自動對應**：Microsoft Entra 「教師」group → `role=teacher`（admin 仍需手動提權）
- **Single Logout (SLO)**：OIDC RP-initiated logout，登出時順便登出 Microsoft session
- **id_token jwks 簽章驗證**：目前未驗 RSA 簽章（信任 token endpoint 走 HTTPS）；v2.2 加 jwks + 公鑰 cache
- **CORS 正式環境設定**：上線前必須在 `.env` 填 `CORS_ORIGINS=https://domain.com,...`
- **批次操作 N+1 → bulk UPDATE**：admin batch tokens / batch reset
- **Notebook 進階**：單格執行（需常駐 Kernel）、Notebook 分享 URL、資料集預覽

---

## 4. 長期願景（未排期）

- **Slurm 整合**：大叢集 HPC 排程（目前 `gpu_client.py` 有抽象框架，~15% 進度）
- **NVIDIA DCGM**：GPU 硬體監控 → Prometheus + Grafana
- **JupyterHub 共存**：保留 v2.0 Lab 為主、JupyterHub 為次（針對既有使用者）
- **Group claim → role 自動化**：見 v2.2 候選
- **Storage 自動配額調整**：依使用者活躍度動態升降 disk_quota_gb
- **Notebook 智慧建議**：依資料集自動推薦 hyperparams（已有部分基於檔案掃描）
- **多語系擴充**：日文 / 韓文 / 越南文（既有 i18n 框架現成可加）

---

## 5. 建議的立即行動

按優先序：

### A. 啟動 Portkey + 填 API 金鑰
```bash
docker compose -f docker-compose.ai-models.yml up -d
# 編輯 docker-compose.ai-models.yml 的 portkey environment 區
# 填入 ANTHROPIC_API_KEY / OPENAI_API_KEY / GOOGLE_API_KEY
```

### B. 改 `batch_update_tokens` N+1（2 hr）
```python
# admin.py
db.query(models.TokenUsage)\
    .filter(models.TokenUsage.user_id.in_(payload.user_ids))\
    .update({models.TokenUsage.tokens_limit: payload.value}, synchronize_session=False)
```

### C. 導入 Alembic（1 天）
```bash
pip install alembic
alembic init migrations
alembic revision --autogenerate -m "initial schema"
```

### D. Lab 安全強化（v2.2 主項目，4-6 hr）
見 §3。

---

## 6. 完整變更歷史

詳細 commit-level 變更見：
- `git log --oneline` — 所有 commit
- [`archive/AUDIT-2026-05-14.md`](archive/AUDIT-2026-05-14.md) — 早期程式碼審查報告
- [`archive/PLAN-v2.0-lab.md`](archive/PLAN-v2.0-lab.md) — v2.0 Lab 詳細設計
- [`archive/PLAN-v2.1-sso-oidc.md`](archive/PLAN-v2.1-sso-oidc.md) — v2.1 SSO 詳細設計
- [`archive/v2.1-roadmap.md`](archive/v2.1-roadmap.md) — v2.1 預先計畫（已實作完成）
