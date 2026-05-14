import os
import time
import json
import logging
import subprocess
import requests
import re
import threading

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

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
    ZH: 透過 nvidia-smi 查詢空閒 GPU
    EN: Query idle GPUs via nvidia-smi
    """
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=index,utilization.gpu", "--format=csv,noheader,nounits"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True
        )
        available = []
        for line in result.stdout.strip().split('\n'):
            if line:
                idx, util = line.split(',')
                idx = idx.strip()
                util = int(util.strip())
                if util < 10:  # ZH: 使用率低於 10% 視為空閒 | EN: Util < 10% is idle
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
    ZH: 解析常見的進度格式，例如 "Epoch 2/10" 或 "Progress: 25%"
    EN: Parse common progress formats
    """
    match = re.search(r'Epoch (\d+)/(\d+)', log_line)
    if match:
        current, total = int(match.group(1)), int(match.group(2))
        return (current / total) * 100.0
    
    match = re.search(r'Progress:? (\d+(?:\.\d+)?)%', log_line)
    if match:
        return float(match.group(1))
    
    return None

def execute_job(job):
    job_id = job.get("job_id")
    script = job.get("script_path", "/workspace/train.py")
    gpu_id = job.get("gpu_id", "0")
    
    logger.info(f"Starting job {job_id} on GPU {gpu_id} executing {script}")
    
    # ZH: 通知主機任務已開始 | EN: Notify master job started
    report_update(job_id, {"status": "running"})

    # ZH: 準備 docker run 指令 | EN: Prepare docker run command
    # ZH: 注意！這裡啟動的是兄弟容器 (Sibling container)
    cmd = [
        "docker", "run", "--rm",
        "--gpus", f"device={gpu_id}",
        "-v", f"{STORAGE_MOUNT_PATH}:/workspace",
        DEFAULT_IMAGE,
        "python", "-u", script
    ]
    
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
            # ZH: 假設產出在 /workspace/outputs/job_id/ | EN: Assume output in /workspace/outputs/job_id/
            report_update(job_id, {
                "status": "completed", 
                "progress": 100.0,
                "output_path": f"/workspace/outputs/{job_id}/model.pt"
            })
        else:
            logger.error(f"Job {job_id} failed with exit code {process.returncode}.")
            report_update(job_id, {
                "status": "failed",
                "error_message": f"Docker container exited with code {process.returncode}"
            })
            
    except Exception as e:
        logger.error(f"Failed to execute job {job_id}: {e}")
        report_update(job_id, {"status": "failed", "error_message": str(e)})

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
