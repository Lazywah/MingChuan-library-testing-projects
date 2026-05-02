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

HEADERS = {"Authorization": f"Bearer {API_TOKEN}"}

# ZH: 預設使用的訓練 Image | EN: Default training image
DEFAULT_IMAGE = "pytorch/pytorch:2.6.0-cuda12.4-cudnn9-runtime"

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

def report_update(job_id, payload):
    url = f"{SERVICE_LAYER_URL}/api/v1/worker/jobs/{job_id}/update"
    try:
        requests.post(url, json=payload, headers=HEADERS, timeout=5)
    except Exception as e:
        logger.error(f"Failed to report update for job {job_id}: {e}")

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
        "--gpus", f'"device={gpu_id}"',
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
    logger.info(f"Worker node {NODE_ID} started. Polling {SERVICE_LAYER_URL}...")
    while True:
        available_gpus = get_available_gpus()
        
        if available_gpus:
            try:
                # ZH: 嘗試領取任務 | EN: Try to take a job
                response = requests.post(
                    f"{SERVICE_LAYER_URL}/api/v1/worker/take",
                    json={"node_id": NODE_ID, "available_gpus": available_gpus},
                    headers=HEADERS,
                    timeout=5
                )
                
                if response.status_code == 200:
                    data = response.json()
                    job = data.get("job")
                    if job:
                        logger.info(f"Acquired job: {job.get('job_id')}")
                        # ZH: 放入獨立的 Thread 執行，避免阻塞 Polling
                        # EN: Execute in a separate thread to avoid blocking polling
                        # Note: In a real multi-GPU setup, we might limit threads to len(available_gpus)
                        t = threading.Thread(target=execute_job, args=(job,))
                        t.daemon = True
                        t.start()
            except Exception as e:
                logger.debug(f"Polling failed: {e}")
                
        time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    poll_loop()
