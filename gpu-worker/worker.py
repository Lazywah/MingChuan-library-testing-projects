import os
import time
import json
import logging
import subprocess
import requests
import re
import threading
import shutil

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# ZH: M3 修復 — 追蹤本機已派發但容器尚未起跑（util 仍 < 10%）的 GPU，
#     避免下一輪 poll 把同一張 GPU 又領一個任務塞進去（雙重派發）。
# EN: M3 fix — track GPUs dispatched but not yet under load so the next poll
#     won't re-grab them as idle and double-dispatch a job to the same card.
_busy_gpus_lock = threading.Lock()
_busy_gpus: set = set()


def _mark_gpu_busy(gpu_id: str) -> None:
    with _busy_gpus_lock:
        _busy_gpus.add(str(gpu_id))


def _mark_gpu_free(gpu_id: str) -> None:
    with _busy_gpus_lock:
        _busy_gpus.discard(str(gpu_id))


def _busy_gpu_snapshot() -> set:
    with _busy_gpus_lock:
        return set(_busy_gpus)

SERVICE_LAYER_URL = os.environ.get("SERVICE_LAYER_URL", "http://192.168.1.50:8002")
API_TOKEN = os.environ.get("API_TOKEN", "mcu-secret-token")
NODE_ID = os.environ.get("NODE_ID", "gpu-node-01")
POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL", "5"))
STORAGE_MOUNT_PATH = os.environ.get("STORAGE_MOUNT_PATH", "C:\\storage")
# Heartbeat is sent every HEARTBEAT_INTERVAL polls (default: every 30 s = 6 polls × 5 s)
HEARTBEAT_INTERVAL = int(os.environ.get("HEARTBEAT_INTERVAL", "30"))

HEADERS = {"Authorization": f"Bearer {API_TOKEN}"}

# ZH: 預設使用的訓練 Image | EN: Default training image
# ZH: RTX 5090 (Blackwell sm_120) 需要 CUDA ≥ 12.8；PyTorch 2.7+ 才有官方 cu128 映像檔
# EN: RTX 5090 (Blackwell sm_120) requires CUDA ≥ 12.8; PyTorch 2.7+ has official cu128 images
DEFAULT_IMAGE = "pytorch/pytorch:2.7.0-cuda12.8-cudnn9-runtime"

def get_available_gpus():
    """
    ZH: 透過 nvidia-smi 查詢空閒 GPU，並排除本機已派發但容器尚未起跑的 GPU
    EN: Query idle GPUs via nvidia-smi, excluding GPUs already dispatched locally
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
                if util < 10 and idx not in busy:
                    # ZH: 使用率低於 10% 且未在本機 busy-set，才視為空閒
                    # EN: Idle only if util < 10% AND not in local busy-set
                    available.append(idx)
        return available
    except Exception as e:
        logger.error(f"Failed to query GPUs: {e}")
        return []

def get_gpu_utilization() -> float:
    """
    Return the average GPU utilization (%) across all GPUs.
    Returns 0.0 on failure.
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


def send_heartbeat(available_gpus: list) -> None:
    """
    POST /api/v1/worker/heartbeat to keep the service layer informed of this
    node's availability and GPU utilisation.  Errors are logged but never fatal.
    """
    try:
        gpu_util = get_gpu_utilization()
        payload = {
            "node_id": NODE_ID,
            "available_gpus": available_gpus,
            "gpu_utilization": gpu_util,
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

def execute_job(job):
    job_id    = job.get("job_id")
    gpu_id    = job.get("gpu_id", "0")
    image     = job.get("docker_image") or DEFAULT_IMAGE
    inline_code = job.get("inline_code")
    entry_args  = job.get("entry_args")   # list[str] or None

    logger.info(f"Starting job {job_id} on GPU {gpu_id} | image={image}")

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

    if inline_code:
        # ZH: Notebook 模式 — 將 compileNotebook() 產出的 shell script 寫入暫存目錄
        # EN: Notebook mode — write compiled shell script to temp dir and mount it
        code_dir = f"/tmp/job_{job_id}"
        os.makedirs(code_dir, exist_ok=True)
        script_file = os.path.join(code_dir, "run.sh")
        with open(script_file, "w", encoding="utf-8") as f:
            f.write(inline_code)
        os.chmod(script_file, 0o755)
        extra_mounts = ["-v", f"{code_dir}:/job_code"]
        entry = ["bash", "-eu", "/job_code/run.sh"]
        logger.info(f"Notebook mode: script written to {script_file}")
    elif entry_args:
        # ZH: 自訂入口（llama.cpp、vLLM 等非 Python 工具）
        # EN: Custom entry (llama.cpp, vLLM, and other non-Python tools)
        entry = entry_args
    else:
        # ZH: 傳統模式 — 執行 script_path 指向的 Python 腳本
        # EN: Legacy mode — run Python script at script_path
        script = job.get("script_path", "/workspace/train.py")
        entry = ["python", "-u", script]

    # ZH: 組裝 docker run 指令（兄弟容器模式）
    # EN: Build docker run command (sibling container pattern)
    cmd = [
        "docker", "run", "--rm",
        "--gpus", f"device={gpu_id}",
        "-v", f"{STORAGE_MOUNT_PATH}:/workspace",
        *extra_mounts,
        image,
        *entry
    ]

    logger.info(f"CMD: {' '.join(cmd)}")

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
    logger.info("Worker node %s started. Polling %s every %ds, heartbeat every %ds.",
                NODE_ID, SERVICE_LAYER_URL, POLL_INTERVAL, HEARTBEAT_INTERVAL)

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
                    json={"node_id": NODE_ID, "available_gpus": available_gpus},
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
