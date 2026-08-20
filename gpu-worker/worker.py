import os
import time
import json
import logging
import subprocess
import requests
import re
import threading
import shutil
import hashlib
import pathlib
import tempfile
import zipfile

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# ZH: M3 修復 — 追蹤本機已派發但容器尚未起跑（util 仍 < 10%）的 GPU，
#     避免下一輪 poll 把同一張 GPU 又領一個任務塞進去（雙重派發）。
# EN: M3 fix — track GPUs dispatched but not yet under load so the next poll
#     won't re-grab them as idle and double-dispatch a job to the same card.
_busy_gpus_lock = threading.Lock()
_busy_gpus: set = set()


def _mark_gpu_busy(gpu_id: str) -> None:
    """@node gpu-worker/worker.py::_mark_gpu_busy"""
    with _busy_gpus_lock:
        _busy_gpus.add(str(gpu_id))


def _mark_gpu_free(gpu_id: str) -> None:
    """@node gpu-worker/worker.py::_mark_gpu_free"""
    with _busy_gpus_lock:
        _busy_gpus.discard(str(gpu_id))


def _busy_gpu_snapshot() -> set:
    """@node gpu-worker/worker.py::_busy_gpu_snapshot"""
    with _busy_gpus_lock:
        return set(_busy_gpus)

SERVICE_LAYER_URL = os.environ.get("SERVICE_LAYER_URL", "http://192.168.1.50:8002")
API_TOKEN = os.environ.get("API_TOKEN", "mcu-secret-token")
NODE_ID = os.environ.get("NODE_ID", "gpu-node-01")
# ZH: v3.0 此節點所屬池 batch(高階 GPU 伺服器) / interactive(本地·服務層 GPU)。
#     本機/目前部署維持預設 batch；日後在服務層 RTX 5090 起的 worker 設 POOL_TYPE=interactive，
#     「本地 GPU」任務便會自動改由它領取（不需改任何程式碼）。
# EN: v3.0 this node's pool. Keep default "batch" for now; a future service-layer
#     RTX 5090 worker sets POOL_TYPE=interactive and local-GPU jobs route to it — no code change.
POOL_TYPE = os.environ.get("POOL_TYPE", "batch")
# ZH: v3.6 這個節點是否與**服務層同一台機器**。
#     為什麼需要它：程式實驗室（Notebook）模式的任務靠 per-user 的 `home_<uid>`
#     Docker volume 取得使用者的檔案，而 Docker volume 是**本機**的。
#     這個 worker 跑在別台機器時，`docker run -v home_<uid>:…` 會在**這台**
#     自動建立一個**空的**同名 volume：不報錯、不警告、訓練出沒有意義的結果。
#     宣告 false（預設）時，服務層就不會把這類任務派過來。
#     ⚠ 用**明確宣告**而不是自動推測（比對 IP 之類）：架節點的人知道自己是不是同一台，
#       而猜錯成 true 會產生無聲的錯誤結果，猜錯成 false 只是拒絕派工——往安全的方向倒。
SHARES_SERVICE_STORAGE = os.environ.get("SHARES_SERVICE_STORAGE", "false").strip().lower() in ("1", "true", "yes", "on")
POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL", "5"))
STORAGE_MOUNT_PATH = os.environ.get("STORAGE_MOUNT_PATH", "C:\\storage")
# Heartbeat is sent every HEARTBEAT_INTERVAL polls (default: every 30 s = 6 polls × 5 s)
HEARTBEAT_INTERVAL = int(os.environ.get("HEARTBEAT_INTERVAL", "30"))
# ZH: GPU 視為「空閒」的使用率上限(%)。專用 GPU 節點維持預設 10；
#     單機/桌機(GPU 與 OS/瀏覽器/Ollama 共用)可調高(如 90)讓任務仍能派發。
# EN: Max GPU util(%) to consider "idle". Dedicated node: keep 10;
#     single-PC/desktop (GPU shared with OS/browser/Ollama): raise it (e.g. 90).
GPU_IDLE_UTIL_THRESHOLD = int(os.environ.get("GPU_IDLE_UTIL_THRESHOLD", "10"))

HEADERS = {"Authorization": f"Bearer {API_TOKEN}"}

# ZH: 預設使用的訓練 Image | EN: Default training image
# ZH: RTX 5090 (Blackwell sm_120) 需要 CUDA ≥ 12.8；PyTorch 2.7+ 才有官方 cu128 映像檔
# EN: RTX 5090 (Blackwell sm_120) requires CUDA ≥ 12.8; PyTorch 2.7+ has official cu128 images
DEFAULT_IMAGE = "pytorch/pytorch:2.7.0-cuda12.8-cudnn9-runtime"

# ==============================================================================
# ZH: v3.6 資料集下載與解壓 | EN: v3.6 Dataset download & extraction
# ==============================================================================
#
# ZH: ⚠ 這裡最容易踩的一個坑：**worker 容器裡的路徑，主機的 docker 看不到。**
#     `docker run -v A:B` 的 A 是由**主機** daemon 解析的（兄弟容器模式）。
#     所以解壓的目的地不能是 worker 容器內部隨便一個資料夾，必須是一個
#     「主機上真實存在、而且訓練容器也掛得到」的地方。
#
#     做法：worker 容器把主機的 STORAGE_MOUNT_PATH 掛在 HOST_STORAGE_MOUNT（預設
#     /hoststorage）。同一個主機目錄，訓練容器那邊掛成 /workspace。於是：
#
#         worker 寫  /hoststorage/datasets/<hash>/…
#         主機上是   <STORAGE_MOUNT_PATH>/datasets/<hash>/…
#         訓練容器讀 /workspace/datasets/<hash>/…
#
#     （本檔 inline_code 那段註解記錄過同一個坑：當初 run.sh 就是這樣消失的。）
# EN: The worker's in-container paths are invisible to the host docker daemon, which
#     resolves `-v`. Extract into shared host storage, mounted here and in the
#     training container at different paths.
HOST_STORAGE_MOUNT = os.environ.get("HOST_STORAGE_MOUNT", "/hoststorage")
# ZH: 訓練容器看到的同一個目錄（worker 不會用這個路徑開檔，只用來組 env）
TRAIN_WORKSPACE = "/workspace"

# ZH: 解壓上限。壓縮炸彈防線：一個 20 KB 的 zip 可以解出好幾 TB。
MAX_EXTRACT_BYTES   = int(os.environ.get("MAX_EXTRACT_BYTES", str(8 * 1024 ** 3)))
MAX_EXTRACT_MEMBERS = int(os.environ.get("MAX_EXTRACT_MEMBERS", "200000"))
# ZH: 下載上限，與服務層的每人 2 GB 配額同數量級
MAX_DOWNLOAD_BYTES  = int(os.environ.get("MAX_DOWNLOAD_BYTES", str(4 * 1024 ** 3)))

# ZH: 內建訓練腳本（隨映像一起帶進來），key 必須與服務層 crud.BUILTIN_TASKS 一致
BUILTIN_SCRIPT_DIR = pathlib.Path(__file__).resolve().parent / "builtin_scripts"


def _host_dir(*parts) -> pathlib.Path:
    """ZH: 組出 worker 這一側的共享儲存路徑，並確保目錄存在。

    @node gpu-worker/worker.py::_host_dir
    """
    d = pathlib.Path(HOST_STORAGE_MOUNT).joinpath(*parts)
    d.mkdir(parents=True, exist_ok=True)
    return d


def download_dataset(job_id: str) -> pathlib.Path:
    """ZH: 從服務層下載這張單的資料集壓縮檔，回傳暫存檔路徑。

    ZH: 串流寫檔——資料集可能好幾 GB，不整包讀進記憶體。

    @node gpu-worker/worker.py::download_dataset
    """
    url = f"{SERVICE_LAYER_URL}/api/v1/worker/datasets/{job_id}"
    tmp_dir = _host_dir("tmp")
    fd, tmp_path = tempfile.mkstemp(prefix=f"ds_{job_id[:8]}_", suffix=".zip", dir=str(tmp_dir))
    os.close(fd)
    tmp = pathlib.Path(tmp_path)

    total = 0
    try:
        with requests.get(url, headers=HEADERS, stream=True, timeout=(10, 600)) as r:
            r.raise_for_status()
            with open(tmp, "wb") as f:
                for chunk in r.iter_content(chunk_size=1024 * 1024):
                    if not chunk:
                        continue
                    total += len(chunk)
                    if total > MAX_DOWNLOAD_BYTES:
                        raise ValueError(
                            f"Dataset exceeds the "
                            f"{MAX_DOWNLOAD_BYTES // 1024 ** 3} GB download limit")
                    f.write(chunk)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
    logger.info("Downloaded dataset for job %s (%.1f MB)", job_id[:8], total / 1024 ** 2)
    return tmp


def file_sha256(path: pathlib.Path) -> str:
    """ZH: 檔案內容雜湊——拿來當快取鍵。

    ZH: 用**內容**而不是 job_id 或檔名：同一包資料重跑十次只解壓一次，
        而不同的資料就算檔名一樣也不會互相污染。

    @node gpu-worker/worker.py::file_sha256
    """
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _declared_size(infos) -> int:
    """ZH: zip 標頭宣告的解壓後總大小。

    ZH: 獨立成一支不只是為了好讀——測試要能把它「關掉」，才驗得到下面那道
        **實際寫入時**的關。兩道關共用同一個上限常數，不拆開的話第二道關
        在測試裡永遠碰不到（而現實中一個說謊的標頭就會碰到）。

    @node gpu-worker/worker.py::_declared_size
    """
    return sum(i.file_size for i in infos)


def safe_extract_zip(zip_path: pathlib.Path, dest: pathlib.Path) -> int:
    """ZH: 解壓 zip，拒絕會跑出 dest 之外的成員；回傳解出的檔案數。

    ZH: 要擋的三件事：
        1. **路徑穿越（zip slip）** —— 成員名字是 `../../etc/passwd` 或絕對路徑。
           不靠檢查字串裡有沒有 `..`（那擋不住各種編碼），而是把最終路徑
           歸一化後確認它**確實在 dest 底下**。
        2. **壓縮炸彈** —— 依 zip 標頭宣告的 file_size 累加，超過上限就中止。
           標頭是可以說謊的，所以實際寫入時**再數一次**。
        3. **成員數量爆炸** —— 幾百萬個小檔案本身就會癱瘓檔案系統。

    @node gpu-worker/worker.py::safe_extract_zip
    """
    dest.mkdir(parents=True, exist_ok=True)
    root = os.path.realpath(dest)
    written = 0
    count = 0

    with zipfile.ZipFile(zip_path) as zf:
        infos = zf.infolist()
        if len(infos) > MAX_EXTRACT_MEMBERS:
            raise ValueError(f"Archive has {len(infos)} members, over the "
                             f"{MAX_EXTRACT_MEMBERS} limit")
        declared = _declared_size(infos)
        if declared > MAX_EXTRACT_BYTES:
            raise ValueError(f"Archive expands to {declared / 1024 ** 3:.1f} GB, over the "
                             f"{MAX_EXTRACT_BYTES / 1024 ** 3:.0f} GB limit")

        for info in infos:
            name = info.filename
            # ZH: 絕對路徑與磁碟機代號直接拒絕（Windows 的 C:\ 也算）
            if name.startswith(("/", "\\")) or (len(name) > 1 and name[1] == ":"):
                raise ValueError(f"Refusing absolute path in archive: {name!r}")

            target = os.path.realpath(os.path.join(dest, name))
            if not (target == root or target.startswith(root + os.sep)):
                raise ValueError(f"Refusing path traversal in archive: {name!r}")

            if info.is_dir():
                os.makedirs(target, exist_ok=True)
                continue

            os.makedirs(os.path.dirname(target), exist_ok=True)
            with zf.open(info) as src, open(target, "wb") as dst:
                while True:
                    chunk = src.read(1024 * 1024)
                    if not chunk:
                        break
                    written += len(chunk)
                    # ZH: 標頭會說謊，所以實際寫了多少也要數。
                    if written > MAX_EXTRACT_BYTES:
                        raise ValueError("Archive expanded past the size limit while "
                                         "extracting (the header understated it)")
                    dst.write(chunk)
            count += 1

    return count


def prepare_dataset(job_id: str) -> str:
    """ZH: 下載 → 快取判斷 → 解壓，回傳**訓練容器看到的**資料夾路徑。

    ZH: 快取鍵是壓縮檔的內容雜湊。完成的目錄會放一個 `.ready` 記號檔——
        **沒有記號就不算完成**：解壓到一半斷掉留下的半套資料夾，下次不會被誤用。

    @node gpu-worker/worker.py::prepare_dataset
    """
    tmp = download_dataset(job_id)
    try:
        digest = file_sha256(tmp)[:16]
        cache = pathlib.Path(HOST_STORAGE_MOUNT) / "datasets" / digest
        ready = cache / ".ready"

        if ready.exists():
            logger.info("Dataset %s already extracted, reusing the cache", digest)
        else:
            if cache.exists():
                # ZH: 有目錄卻沒有記號 = 上次沒解完。整個丟掉重來，不要沿用半套的。
                logger.warning("Cache dir %s has no .ready marker - re-extracting", digest)
                shutil.rmtree(cache, ignore_errors=True)
            n = safe_extract_zip(tmp, cache)
            ready.write_text("ok", encoding="utf-8")
            logger.info("Extracted %d files to %s", n, cache)

        return f"{TRAIN_WORKSPACE}/datasets/{digest}"
    finally:
        tmp.unlink(missing_ok=True)


def materialize_builtin_script(task: str) -> str:
    """ZH: 把內建訓練腳本複製到共享儲存，回傳**訓練容器看到的**路徑。

    ZH: 為什麼每次都複製而不是只在第一次：腳本只有幾 KB，而「映像更新了但
        主機上還留著舊腳本」是那種完全看不出來的錯誤。每次覆蓋最省事也最不會錯。

    @node gpu-worker/worker.py::materialize_builtin_script
    """
    src = BUILTIN_SCRIPT_DIR / f"{task}.py"
    if not src.is_file():
        raise FileNotFoundError(
            f"Built-in script for task {task!r} is missing from this worker image "
            f"({src}). The service layer offers a task this worker cannot run.")
    dest_dir = _host_dir("scripts")
    shutil.copyfile(src, dest_dir / src.name)
    return f"{TRAIN_WORKSPACE}/scripts/{src.name}"

def get_available_gpus():
    """
    ZH: 透過 nvidia-smi 查詢空閒 GPU，並排除本機已派發但容器尚未起跑的 GPU
    EN: Query idle GPUs via nvidia-smi, excluding GPUs already dispatched locally

    @node gpu-worker/worker.py::get_available_gpus
    """
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=index,utilization.gpu", "--format=csv,noheader,nounits"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True
        )
        busy = _busy_gpu_snapshot()
        available = []
        for line in result.stdout.strip().split('\n'):
            if line:
                idx, util = line.split(',')
                idx = idx.strip()
                util = int(util.strip())
                if util < GPU_IDLE_UTIL_THRESHOLD and idx not in busy:
                    # ZH: 使用率低於門檻且未在本機 busy-set，才視為空閒
                    # EN: Idle only if util < threshold AND not in local busy-set
                    available.append(idx)
        return available
    except Exception as e:
        logger.error(f"Failed to query GPUs: {e}")
        return []

def get_gpu_utilization() -> float:
    """
    Return the average GPU utilization (%) across all GPUs.
    Returns 0.0 on failure.

    @node gpu-worker/worker.py::get_gpu_utilization
    """
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=utilization.gpu", "--format=csv,noheader,nounits"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True,
        )
        utils = [float(u.strip()) for u in result.stdout.strip().split("\n") if u.strip()]
        return round(sum(utils) / len(utils), 1) if utils else 0.0
    except Exception:
        return 0.0


def get_gpu_details() -> list:
    """
    ZH: 查詢每張 GPU 的 name/util/temp/memory，供 admin 叢集監控卡片顯示。
    EN: Per-GPU name/util/temp/memory for the admin cluster panel.

    @node gpu-worker/worker.py::get_gpu_details
    """
    try:
        result = subprocess.run(
            ["nvidia-smi",
             "--query-gpu=index,name,utilization.gpu,temperature.gpu,memory.used,memory.total",
             "--format=csv,noheader,nounits"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True,
        )
        gpus = []
        for line in result.stdout.strip().split("\n"):
            if not line.strip():
                continue
            parts = [p.strip() for p in line.split(",")]
            if len(parts) < 6:
                continue
            idx, name, util, temp, mem_used, mem_total = parts[:6]
            gpus.append({
                "gpu_id": idx,
                "name": name,
                "utilization": float(util) if util.replace('.', '', 1).isdigit() else 0,
                "temperature": float(temp) if temp.replace('.', '', 1).isdigit() else 0,
                "memory_used": int(float(mem_used)) if mem_used.replace('.', '', 1).isdigit() else 0,
                "memory_total": int(float(mem_total)) if mem_total.replace('.', '', 1).isdigit() else 0,
            })
        return gpus
    except Exception:
        return []


def send_heartbeat(available_gpus: list) -> None:
    """
    POST /api/v1/worker/heartbeat to keep the service layer informed of this
    node's availability and GPU utilisation.  Errors are logged but never fatal.

    @node gpu-worker/worker.py::send_heartbeat
    """
    try:
        gpu_util = get_gpu_utilization()
        payload = {
            "node_id": NODE_ID,
            "available_gpus": available_gpus,
            "gpu_utilization": gpu_util,
            "gpus_detail": get_gpu_details(),
            "pool_type": POOL_TYPE,
            "shares_service_storage": SHARES_SERVICE_STORAGE,   # ZH: v3.6 見檔頭說明
        }
        resp = requests.post(
            f"{SERVICE_LAYER_URL}/api/v1/worker/heartbeat",
            json=payload,
            headers=HEADERS,
            timeout=5,
        )
        if resp.status_code == 200:
            logger.debug("Heartbeat OK — node=%s gpus=%s util=%.1f%%", NODE_ID, available_gpus, gpu_util)
        else:
            logger.warning("Heartbeat returned HTTP %d: %s", resp.status_code, resp.text[:120])
    except Exception as e:
        logger.warning("Heartbeat failed (service unreachable?): %s", e)


def report_update(job_id, payload, *, retries: int = 3, backoff: float = 2.0) -> None:
    """
    ZH: 向服務層回報任務狀態，失敗時最多重試 retries 次（指數退避）。
    EN: Report job status to service layer; retries up to `retries` times with backoff on failure.

    @node gpu-worker/worker.py::report_update
    """
    url = f"{SERVICE_LAYER_URL}/api/v1/worker/jobs/{job_id}/update"
    for attempt in range(1, retries + 1):
        try:
            resp = requests.post(url, json=payload, headers=HEADERS, timeout=5)
            if resp.status_code < 500:
                # ZH: 2xx / 4xx 不重試（4xx 代表服務端已拒絕，重試無效）
                # EN: 2xx / 4xx — don't retry (4xx means server rejected, retrying won't help)
                return
            logger.warning(
                "report_update HTTP %d for job %s (attempt %d/%d)",
                resp.status_code, job_id, attempt, retries,
            )
        except Exception as e:
            logger.warning(
                "report_update failed for job %s (attempt %d/%d): %s",
                job_id, attempt, retries, e,
            )
        if attempt < retries:
            time.sleep(backoff * attempt)  # ZH: 線性退避 | EN: linear backoff
    logger.error("report_update gave up after %d attempts for job %s", retries, job_id)

def parse_progress(log_line):
    """
    ZH: 解析常見的進度格式
    EN: Parse common progress formats

    ZH: 支援格式：
        - "Epoch 2/10"           PyTorch 訓練
        - "Progress: 25%"        通用格式
        - "[  2/ 10]"            llama.cpp fine-tune / gguf 工具
        - "step 50/200"          HuggingFace Trainer
    EN: Supported formats:
        - "Epoch 2/10"           PyTorch training
        - "Progress: 25%"        Generic
        - "[  2/ 10]"            llama.cpp fine-tune / gguf tools
        - "step 50/200"          HuggingFace Trainer

    @node gpu-worker/worker.py::parse_progress
    """
    # ZH: PyTorch: Epoch 2/10 | EN: PyTorch
    match = re.search(r'Epoch (\d+)/(\d+)', log_line, re.IGNORECASE)
    if match:
        current, total = int(match.group(1)), int(match.group(2))
        return (current / total) * 100.0

    # ZH: HuggingFace Trainer: step 50/200 | EN: HuggingFace
    match = re.search(r'\bstep\s+(\d+)/(\d+)', log_line, re.IGNORECASE)
    if match:
        current, total = int(match.group(1)), int(match.group(2))
        return (current / total) * 100.0

    # ZH: llama.cpp fine-tune: [  2/ 10] | EN: llama.cpp
    match = re.search(r'\[\s*(\d+)\s*/\s*(\d+)\s*\]', log_line)
    if match:
        current, total = int(match.group(1)), int(match.group(2))
        return (current / total) * 100.0

    # ZH: 通用百分比: Progress: 25% | EN: Generic percentage
    match = re.search(r'Progress:?\s*(\d+(?:\.\d+)?)%', log_line, re.IGNORECASE)
    if match:
        return float(match.group(1))

    return None

# ZH: v3.6 —— 這些注入的環境變數**不是機密**，log 裡不要遮。
#     遮掉的代價是實際的：學生的任務失敗時，log 就是唯一的線索，
#     而 `DATASET_DIR=/w****/x` 等於沒說。
# EN: These injected env vars are not secrets; masking them would blind the only
#     diagnostic a student has when a job fails.
NON_SECRET_ENV = {"DATASET_DIR", "OUTPUT_DIR", "EPOCHS", "BATCH_SIZE",
                  "LEARNING_RATE", "VAL_SPLIT", "SEED"}


def _mask_secret(value: str) -> str:
    """ZH: 將 secret 在 log 中 mask 成 ab****yz | EN: Mask secret as ab****yz for logs

    @node gpu-worker/worker.py::_mask_secret
    """
    if not value or len(value) <= 6:
        return "***"
    return f"{value[:2]}****{value[-2:]}"


def execute_job(job):
    """@node gpu-worker/worker.py::execute_job"""
    job_id    = job.get("job_id")
    gpu_id    = job.get("gpu_id", "0")
    image     = job.get("docker_image") or DEFAULT_IMAGE
    inline_code = job.get("inline_code")
    entry_args  = job.get("entry_args")   # list[str] or None
    # ZH: v2.0 Lab — 由服務層注入的環境變數與額外掛載
    # EN: v2.0 Lab — env vars and extra mounts injected by service layer
    extra_env: dict     = job.get("extra_env") or {}
    volume_mounts: list = job.get("volume_mounts") or []
    # ZH: v3.6 上傳資料集訓練 | EN: v3.6 upload-a-dataset training
    has_dataset  = bool(job.get("has_dataset"))
    builtin_task = job.get("builtin_task")
    config: dict = job.get("config") or {}

    logger.info(f"Starting job {job_id} on GPU {gpu_id} | image={image}")
    if extra_env:
        masked = {k: _mask_secret(v) for k, v in extra_env.items()}
        logger.info(f"  injected env: {masked}")

    # ZH: M3 修復 — 立即將此 GPU 標記為 busy；docker pull / 容器初始化期間
    #     nvidia-smi 仍會回報 util < 10%，若不標記則下一次 poll 會把同張卡再派一個任務。
    # EN: M3 fix — mark this GPU busy immediately. While docker pulls / initializes,
    #     nvidia-smi still reports util < 10%, so without this flag the next poll
    #     would double-dispatch onto the same card.
    _mark_gpu_busy(gpu_id)

    # ZH: 通知服務層任務已開始 | EN: Notify service layer job started
    report_update(job_id, {"status": "running"})

    # ZH: 決定容器入口指令與額外 -v 掛載 | EN: Determine container entry and extra mounts
    extra_mounts: list[str] = []
    code_dir: str | None = None

    # ZH: v3.6 —— 先把資料集準備好（下載＋解壓到共享儲存）。
    #     這一段**在起容器之前**做完：解壓失敗就直接把任務標成 failed 並附上原因，
    #     不要讓訓練容器起來之後才發現資料夾是空的（那時使用者只會看到
    #     「訓練完成、正確率 0%」這種毫無線索的結果）。
    # EN: Prepare the dataset before launching the container so a failure surfaces
    #     as a failed job with a reason, not as a successful run on an empty folder.
    dataset_dir: str | None = None
    if has_dataset:
        try:
            report_update(job_id, {"log": "正在取得資料集… / Fetching the dataset…"})
            dataset_dir = prepare_dataset(job_id)
            report_update(job_id, {"log": f"資料集就緒 / Dataset ready at {dataset_dir}"})
        except Exception as e:
            logger.error("Job %s: could not prepare the dataset: %s", job_id, e)
            report_update(job_id, {
                "status": "failed",
                "error_message": f"ZH: 資料集準備失敗 | EN: Could not prepare the dataset: {e}",
            })
            # ZH: 這兩個提早 return 在下面那個 try/finally **之前**，
            #     所以要自己放掉 GPU 標記——不放的話這張卡會永遠被當成忙碌中。
            _mark_gpu_free(gpu_id)
            return

    if inline_code:
        # ZH: Notebook 模式 — 直接以 bash -c 執行已編譯的 shell script。
        #     不寫檔/掛載：兄弟容器模式下 worker 容器內的 /tmp 路徑主機 docker 看不到
        #     （-v 由主機 daemon 解析），會導致 /job_code/run.sh 找不到。改用 bash -c 跨平台可靠。
        # EN: Notebook mode — run the compiled script via `bash -c` directly. No file/mount:
        #     in the sibling-container pattern the worker's in-container /tmp is invisible to the
        #     host docker daemon (which resolves -v), so the mounted run.sh is missing. `bash -c`
        #     is cross-platform and avoids the shared-path problem entirely.
        entry = ["bash", "-euc", inline_code]
        logger.info("Notebook mode: running compiled script via bash -c")
    elif builtin_task:
        # ZH: v3.6 內建腳本模式 —— 使用者只上傳資料，程式由平台提供。
        # EN: v3.6 built-in script mode — the user uploads data; the platform supplies the code.
        try:
            script_in_container = materialize_builtin_script(builtin_task)
        except Exception as e:
            logger.error("Job %s: %s", job_id, e)
            report_update(job_id, {
                "status": "failed",
                "error_message": f"ZH: 這個節點沒有這支內建腳本 | EN: {e}",
            })
            # ZH: 這兩個提早 return 在下面那個 try/finally **之前**，
            #     所以要自己放掉 GPU 標記——不放的話這張卡會永遠被當成忙碌中。
            _mark_gpu_free(gpu_id)
            return
        entry = ["python", "-u", script_in_container]
        logger.info("Built-in mode: %s -> %s", builtin_task, script_in_container)
    elif entry_args:
        # ZH: 自訂入口（llama.cpp、vLLM 等非 Python 工具）
        # EN: Custom entry (llama.cpp, vLLM, and other non-Python tools)
        entry = entry_args
    else:
        # ZH: 傳統模式 — 執行 script_path 指向的 Python 腳本
        # EN: Legacy mode — run Python script at script_path
        script = job.get("script_path", "/workspace/train.py")
        entry = ["python", "-u", script]

    # ZH: v3.6 —— 資料集位置與訓練參數以環境變數交給腳本。
    #     用 env 而不是命令列參數：內建腳本與使用者自己的腳本用同一組約定，
    #     而且不必處理引號跳脫（路徑裡有空白時最容易在這裡出事）。
    # EN: v3.6 — pass dataset location and hyper-parameters via env, not argv.
    if dataset_dir:
        extra_env.setdefault("DATASET_DIR", dataset_dir)
    if builtin_task:
        extra_env.setdefault("OUTPUT_DIR", f"{TRAIN_WORKSPACE}/outputs/{job_id}")
        for key, env_name in (("epochs", "EPOCHS"),
                              ("batch_size", "BATCH_SIZE"),
                              ("learning_rate", "LEARNING_RATE")):
            if config.get(key) is not None:
                extra_env.setdefault(env_name, str(config[key]))

    # ZH: v2.0 — 額外環境變數 ( -e KEY=VAL )，secrets 不會被印到 log（已 mask 在上方）
    # EN: v2.0 — extra env flags ( -e KEY=VAL ); secrets are masked above before logging
    env_args: list = []
    for k, v in extra_env.items():
        env_args.extend(["-e", f"{k}={v}"])

    # ZH: v2.0 — 額外 volume mounts (per-user home + shared models)
    # EN: v2.0 — extra volume mounts (per-user home + shared models)
    lab_mount_args: list = []
    for mount in volume_mounts:
        name   = mount.get("name")
        target = mount.get("target")
        mode   = mount.get("mode", "rw")
        if name and target:
            lab_mount_args.extend(["-v", f"{name}:{target}:{mode}"])

    # ZH: 組裝 docker run 指令（兄弟容器模式）
    # EN: Build docker run command (sibling container pattern)
    cmd = [
        "docker", "run", "--rm",
        "--gpus", f"device={gpu_id}",
        "-v", f"{STORAGE_MOUNT_PATH}:/workspace",
        *extra_mounts,
        *lab_mount_args,
        *env_args,
        image,
        *entry
    ]

    # ZH: log 時把 -e KEY=value 對的 value 換成 mask，避免 secret 漏在 log
    # EN: When logging, replace -e KEY=value values with masks to keep secrets out of log
    safe_cmd = []
    skip_next = False
    for i, tok in enumerate(cmd):
        if skip_next:
            if "=" in tok:
                k, _, v = tok.partition("=")
                safe_cmd.append(f"{k}={v}" if k in NON_SECRET_ENV
                                else f"{k}={_mask_secret(v)}")
            else:
                safe_cmd.append(tok)
            skip_next = False
            continue
        safe_cmd.append(tok)
        if tok == "-e":
            skip_next = True
    logger.info(f"CMD: {' '.join(safe_cmd)}")

    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True
        )

        for line in process.stdout:
            line = line.strip()
            if not line:
                continue

            logger.info(f"[{job_id}] {line}")
            payload = {"log": line}

            prog = parse_progress(line)
            if prog is not None:
                payload["progress"] = prog

            report_update(job_id, payload)

        process.wait()

        if process.returncode == 0:
            logger.info(f"Job {job_id} completed successfully.")
            report_update(job_id, {
                "status":      "completed",
                "progress":    100.0,
                "output_path": f"/workspace/outputs/{job_id}/model.pt"
            })
        else:
            logger.error(f"Job {job_id} failed with exit code {process.returncode}.")
            report_update(job_id, {
                "status":        "failed",
                "error_message": f"Docker container exited with code {process.returncode}"
            })

    except Exception as e:
        logger.error(f"Failed to execute job {job_id}: {e}")
        report_update(job_id, {"status": "failed", "error_message": str(e)})

    finally:
        # ZH: 清理 Notebook 暫存目錄 | EN: Clean up notebook temp directory
        if code_dir and os.path.exists(code_dir):
            shutil.rmtree(code_dir, ignore_errors=True)
            logger.debug(f"Cleaned up temp dir: {code_dir}")
        # ZH: M3 修復 — 任務結束（成功 / 失敗 / 例外）一律釋放 GPU 標記
        # EN: M3 fix — always free the GPU flag when the job finishes, no matter how
        _mark_gpu_free(gpu_id)

def poll_loop():
    """@node gpu-worker/worker.py::poll_loop"""
    logger.info("Worker node %s started. Polling %s every %ds, heartbeat every %ds.",
                NODE_ID, SERVICE_LAYER_URL, POLL_INTERVAL, HEARTBEAT_INTERVAL)
    # ZH: v3.6 開機時把這個宣告印出來——設錯了要看得見，不要等到訓練結果不對才發現。
    logger.info("Co-located with the service layer (Code Lab volumes visible): %s%s",
                SHARES_SERVICE_STORAGE,
                "" if SHARES_SERVICE_STORAGE else
                "  -> this node will NOT be given Code Lab (notebook) jobs")

    last_heartbeat = 0.0  # Unix timestamp of last successful heartbeat send

    while True:
        available_gpus = get_available_gpus()

        # ── Heartbeat (time-based, independent of GPU availability) ──────────
        now = time.time()
        if now - last_heartbeat >= HEARTBEAT_INTERVAL:
            send_heartbeat(available_gpus)
            last_heartbeat = now

        # ── Job polling (only when a GPU is free) ─────────────────────────────
        if available_gpus:
            try:
                response = requests.post(
                    f"{SERVICE_LAYER_URL}/api/v1/worker/take",
                    json={"node_id": NODE_ID, "available_gpus": available_gpus,
                          "pool_type": POOL_TYPE,
                          "shares_service_storage": SHARES_SERVICE_STORAGE},
                    headers=HEADERS,
                    timeout=5,
                )

                if response.status_code == 200:
                    data = response.json()
                    job = data.get("job")
                    if job:
                        logger.info("Acquired job: %s", job.get("job_id"))
                        # Execute in a separate thread to avoid blocking the poll loop
                        t = threading.Thread(target=execute_job, args=(job,))
                        t.daemon = True
                        t.start()
            except Exception as e:
                logger.debug("Polling failed: %s", e)

        time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    poll_loop()
