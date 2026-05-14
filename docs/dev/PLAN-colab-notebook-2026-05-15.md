# Plan: Colab 風格 Notebook 運算介面

> 撰寫日期：2026-05-15
> 狀態：**已討論確認，待實作**

## Context

現有的「運算任務」頁面是一個極簡表單（任務名稱、資料集上傳、自動偵測 epochs/batch_size），
無程式碼編輯功能，且 GPU Worker 寫死 PyTorch 映像檔與 `python -u` 指令，無法支援
llama.cpp、vLLM 等不同工具。

目標：將運算頁面升級為類 Google Colab 的多格 Notebook 介面，讓使用者：
- 在瀏覽器內撰寫 Python 程式（多格、語法高亮）
- 選擇執行框架（PyTorch / TensorFlow / HuggingFace / llama.cpp / vLLM / 自訂，**單選**）
- 選擇執行模式（訓練、微調、推論、資料前處理）
- 選擇 GPU 伺服器（手動或自動排程）
- 上傳 / 選擇訓練資料集
- 即時串流執行輸出（SSE 已有）
- Notebook 內容自動儲存（持久化）

**現有表單**：保留但暫不接上系統（作為備案）。

---

## 技術決策

### 多格 Notebook 執行模型

採用「**偽 Notebook**」方案（非真 Jupyter Kernel）：
- UI 呈現多個獨立程式格（像 Colab）
- 使用者點「Run All」時，所有 code/shell cell 依序合併為一支腳本提交
- 提交為單一 Job，透過現有 GPU Worker 在 Docker 容器中執行
- 不需要持久化 Kernel，基礎設施不變

**格子間變數共享限制**：

| 情境 | 真 Colab | 偽 Notebook（本方案） |
|------|----------|-----------------------|
| Run All（全部一起跑） | ✅ | ✅ 完全相同 |
| 只跑第 N 格（用前格變數） | ✅ | ❌ 不支援 |
| 從第 N 格開始跑 | ✅ | 🔜 後續可加 |

對訓練/微調場景影響極小（幾乎都是寫完整腳本再全跑）。
真 Jupyter Kernel 需要每人一個常駐 server，成本過高，列為未來版本。

### 框架選擇 — 單選

每個 Job 在單一 Docker 容器執行，基底 Image 只能有一個（**單選**）。
使用者若需要額外套件，可在程式格內自行執行 `!pip install xxx`。

### 語言支援 — Python + Shell Cell

支援三種格子類型：

| 格子類型 | 執行方式 | 用途 |
|----------|----------|------|
| `code`   | `python -u compiled.py` | Python 程式（預設） |
| `shell`  | `bash -c "..."` | 編譯 C++/CUDA、安裝套件、任意 shell 指令 |
| `markdown` | 僅前端渲染，不執行 | 說明文字 |

Shell Cell 範例：
```bash
nvcc train.cu -o train_gpu && ./train_gpu
pip install deepspeed
g++ -O2 preprocess.cpp -o preprocess && ./preprocess
```

Monaco Editor 對 Python / C++ / CUDA / Shell 皆有語法高亮，自動依格子類型切換語言模式。

### 程式碼持久化

採用：每位使用者一份 Notebook 記錄（資料庫），前端 auto-save（debounce 2s）。

### Monaco Editor

透過 CDN 載入（無需 build step），支援語法高亮與自動補全。

---

## 框架 → Docker Image 對照表

| 框架 | Docker Image |
|------|-------------|
| PyTorch (預設) | `pytorch/pytorch:2.7.0-cuda12.8-cudnn9-runtime` |
| TensorFlow | `tensorflow/tensorflow:2.15.0-gpu` |
| HuggingFace Transformers | `huggingface/transformers-pytorch-gpu:latest` |
| llama.cpp | `ghcr.io/ggerganov/llama.cpp:full-cuda` |
| vLLM | `vllm/vllm-openai:latest` |
| 自訂 | 使用者自行輸入 image 名稱 |

---

## 執行模式 → 預設 Starter Template

| 框架 | 模式 | 預設程式格內容 |
|------|------|--------------|
| PyTorch | 訓練 | 標準訓練迴圈範本 |
| PyTorch | 微調 | LoRA 微調範本 |
| PyTorch | 推論 | 載入模型 + 推論範本 |
| llama.cpp | 推論 | `!./llama-cli -m /workspace/...` |
| vLLM | 推論 | vLLM API Server 啟動範本 |
| 通用 | 資料前處理 | CSV/JSONL 清洗範本 |

---

## 需修改 / 新增的檔案

### 1. `job-scheduler/app/models.py`

新增 `Notebook` 表：
```python
class Notebook(Base):
    __tablename__ = "notebooks"
    id          = Column(String, primary_key=True, default=generate_uuid)
    user_id     = Column(String, ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True)
    cells       = Column(Text)     # JSON: [{id, type:"code"|"shell"|"markdown", content}]
    environment = Column(Text)     # JSON: {framework, mode, preferred_node, docker_image}
    updated_at  = Column(DateTime, ...)
```

新增欄位至 `TrainingJob`：
```python
docker_image = Column(String, nullable=True)   # 覆寫 DEFAULT_IMAGE
inline_code  = Column(Text,   nullable=True)   # 合併後的完整執行腳本
entry_args   = Column(Text,   nullable=True)   # JSON 陣列（llama.cpp 等非 Python 用）
```

### 2. `job-scheduler/app/schemas.py`

```python
# 新增
class NotebookCell(BaseModel):
    id: str
    type: str       # "code" | "shell" | "markdown"
    content: str

class NotebookSave(BaseModel):
    cells: List[NotebookCell]
    environment: Dict[str, Any]

class NotebookResponse(BaseModel):
    cells: List[NotebookCell]
    environment: Dict[str, Any]
    updated_at: Optional[datetime]

# 更新 JobCreate（新增欄位）
docker_image:    Optional[str]       = None
inline_code:     Optional[str]       = None   # 合併的 shell script
entry_args:      Optional[List[str]] = None
preferred_node:  Optional[str]       = None   # "auto" 或特定 node_id
```

### 3. `job-scheduler/app/crud.py`

新增函式：
- `get_notebook(db, user_id)` → `Notebook | None`
- `save_notebook(db, user_id, cells_json, env_json)` → `Notebook` (upsert)

修改函式：
- `create_job()` — 儲存 `docker_image`, `inline_code`
- `get_pending_jobs()` — 若 job 有 `preferred_node`，優先回傳給對應 node

### 4. 新增 `job-scheduler/app/routers/notebooks.py`

```
GET  /api/v1/notebooks/mine   → 載入使用者 Notebook（JWT）
PUT  /api/v1/notebooks/mine   → 儲存 / 更新 Notebook（JWT）
GET  /api/v1/worker/nodes     → 列出線上 GPU 節點供前端選擇（JWT）
```

`/worker/nodes` 從 `WorkerHeartbeat` 表查詢 `last_seen > now - 60s`。

### 5. `job-scheduler/app/routers/worker.py`

- `/take` 回傳增加 `docker_image`, `inline_code`, `entry_args` 欄位
- 支援 `preferred_node`：若 job.preferred_node 非空且與 req.node_id 不符則跳過

### 6. `job-scheduler/app/main.py`

掛載新 Router：
```python
app.include_router(notebooks_router, prefix="/api/v1/notebooks")
```

### 7. `gpu-worker/worker.py`

`execute_job()` 修改邏輯：
```python
image = job.get("docker_image") or DEFAULT_IMAGE
inline_code = job.get("inline_code")

if inline_code:
    # inline_code 為前端 compileNotebook() 產出的完整 shell script
    # code cell → python 區塊，shell cell → bash 區塊，合併為 run.sh
    code_dir = f"/tmp/{job_id}"
    os.makedirs(code_dir, exist_ok=True)
    with open(f"{code_dir}/run.sh", "w") as f:
        f.write(inline_code)
    entry = ["bash", "-eu", "/job_code/run.sh"]
    cmd = [
        "docker", "run", "--rm",
        "--gpus", f"device={gpu_id}",
        "-v", f"{STORAGE_MOUNT_PATH}:/workspace",
        "-v", f"{code_dir}:/job_code",
        image, *entry
    ]
else:
    # 現有邏輯（script_path）
    entry = job.get("entry_args") or ["python", "-u", script]
    cmd = ["docker", "run", "--rm", "--gpus", ..., image, *entry]

# 結束後清理暫存
shutil.rmtree(code_dir, ignore_errors=True)
```

新增 `parse_progress()` 規則（llama.cpp 格式）：
```python
# [  1/ 10]
match = re.search(r'\[\s*(\d+)\s*/\s*(\d+)\s*\]', log_line)
```

### 8. `web-ui/index.html`

在 Compute 頁面新增 Notebook 子頁籤（High / Mid-Low / **Notebook**）：

```html
<!-- Monaco Editor CDN -->
<script src="https://cdn.jsdelivr.net/npm/monaco-editor@0.44.0/min/vs/loader.js"></script>

<!-- Notebook 面板結構 -->
<div id="notebook-panel">
  <div class="notebook-toolbar">
    <select id="nb-framework">PyTorch / TF / HuggingFace / llama.cpp / vLLM / 自訂</select>
    <select id="nb-mode">訓練 / 微調 / 推論 / 資料前處理</select>
    <select id="nb-gpu">自動 / gpu-node-01 / ...</select>
    <button id="nb-run-all">▶ Run All</button>
    <button id="nb-stop">■ Stop</button>
    <span id="nb-save-status">已儲存</span>
  </div>
  <div class="notebook-dataset-bar">...</div>
  <div id="nb-cells-container"><!-- 動態產生 .nb-cell --></div>
  <button id="nb-add-cell">+ 新增格子</button>
  <div id="nb-output-panel">
    <div id="nb-output-log"></div>
    <div id="nb-progress-bar"></div>
  </div>
</div>
```

### 9. `web-ui/app.js`

新增函式群：

| 函式 | 用途 |
|------|------|
| `initNotebook()` | 頁面載入時從 API 讀取 Notebook，建立 Monaco 格子 |
| `addCell(type)` | 新增 code / shell / markdown 格子 |
| `deleteCell(id)` | 刪除格子 |
| `moveCell(id, dir)` | 上移 / 下移格子 |
| `compileNotebook()` | 合併所有格子為完整 shell script（code → python 區塊，shell → bash 區塊） |
| `runNotebook()` | compileNotebook → POST /api/v1/jobs → 開始 SSE |
| `saveNotebook()` | PUT /api/v1/notebooks/mine（debounce 2s） |
| `loadWorkerNodes()` | GET /api/v1/worker/nodes → 填充 GPU 下拉選單 |
| `applyFrameworkTemplate()` | 框架/模式改變時替換 starter 程式格 |
| `startOutputStream(job_id)` | 連接 SSE，更新輸出面板 |

### 10. `web-ui/styles.css`

新增 Notebook 相關樣式：
- `.notebook-toolbar` — 工具列橫排佈局
- `.nb-cell` — 格子容器（border-left accent + 控制按鈕）
- `.nb-cell-code` / `.nb-cell-shell` — Monaco editor 容器
- `.nb-cell-markdown` — Markdown 顯示區
- `.nb-output-panel` — 輸出面板（深色背景，monospace 字型）
- `.nb-progress-bar` — 進度條

---

## 實作順序

```
Step 1  models.py                 新增 Notebook 表 + TrainingJob 3 個欄位
Step 2  schemas.py                NotebookCell / NotebookSave / NotebookResponse + 更新 JobCreate
Step 3  crud.py                   get_notebook / save_notebook + 更新 create_job / get_pending_jobs
Step 4  routers/notebooks.py      新建 (GET/PUT mine + GET /worker/nodes)
Step 5  main.py                   掛載新 router
Step 6  routers/worker.py         /take 補傳欄位 + preferred_node 邏輯
Step 7  gpu-worker/worker.py      inline_code + docker_image + entry_args + parse_progress
Step 8  web-ui/index.html         Notebook tab HTML 骨架
Step 9  web-ui/app.js             Notebook JS 函式群 + Monaco 初始化
Step 10 web-ui/styles.css         Notebook 樣式
```

---

## i18n 補充

所有新 UI 字串須同時加入 `web-ui/app.js` 的 `zh` / `en` 翻譯字典（遵循現有 `t()` 模式）。

---

## 驗證方式

1. **Notebook 儲存**：寫一格 `print("hello")`，重新整理頁面，確認格子仍在
2. **PyTorch Job**：選 PyTorch + 訓練，Run All，確認 Worker 執行 pytorch image
3. **llama.cpp Job**：選 llama.cpp + 推論，確認 Worker 使用正確 image + entry_args
4. **Shell Cell**：新增 shell cell 執行 `echo "cuda test"`，確認輸出正確
5. **preferred_node**：選特定 GPU 節點，確認 Worker /take 只有對應節點領到任務
6. **SSE 輸出**：執行中輸出面板即時更新，任務結束後 SSE 斷線
7. **policy 規則**：學生帳號受 max_concurrent_jobs 限制，管理員不受限
8. **現有表單**：High / Mid-Low 頁籤仍可正常切換（備案保留）
