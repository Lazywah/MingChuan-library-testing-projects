# -*- coding: utf-8 -*-
"""端對端實測：真的 HTTP 往返 —— 上傳 zip → 送單 → 領工 → 下載 → 解壓 → 快取。

    用法：python tests/dataset_pipeline_e2e.py

ZH: **手動執行**，不是 pytest 的一部分（檔名刻意不叫 test_*）——它會起一個
    真的 uvicorn，跑起來要幾秒，不適合每次全套都跑。

ZH: 為什麼不靠單元測試就好：單元測試裡的「下載」是 TestClient，
    走不到 `requests` 那條路（串流、逾時、raise_for_status、暫存檔清理）。
    而 worker 在現場走的正是那一條。

ZH: 用**獨立的暫存 DB**，不碰 data/ai_platform.db
    （從主機端一般開啟那個檔會讓容器再也開不了它）。
"""
import io
import os
import sys as _sys
try:
    _sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
import pathlib
import socket
import subprocess
import sys
import tempfile
import time
import zipfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
WORK = pathlib.Path(tempfile.mkdtemp(prefix="e2e_ds_"))
DATASETS = WORK / "datasets"          # 服務層的資料集根目錄
HOSTSTORE = WORK / "hoststorage"      # worker 這一側的共享儲存
DATASETS.mkdir(); HOSTSTORE.mkdir()

TOKEN = "e2e-worker-token-abcdef123456"


def free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close()
    return p


PORT = free_port()
BASE = f"http://127.0.0.1:{PORT}"

env = dict(os.environ)
env.update({
    "DATABASE_PATH":     str(WORK / "e2e.db"),
    "WORKER_API_TOKEN":  TOKEN,
    "JWT_SECRET_KEY":    "e" * 40,
    "SECRET_KEY":        "e" * 40,
    "BOOTSTRAP_ADMIN_PASSWORD": "E2ePass!23456",
    "BOOTSTRAP_ADMIN_EMAIL":    "admin@example.com",
    "DATASET_DIR":       str(DATASETS),
    "PYTHONPATH":        str(ROOT / "job-scheduler"),
    "PYTHONIOENCODING":  "utf-8",
})

print(f"暫存工作區：{WORK}")
print(f"啟動服務於 {BASE} …")
proc = subprocess.Popen(
    [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1",
     "--port", str(PORT), "--log-level", "warning"],
    cwd=str(ROOT / "job-scheduler"), env=env,
    stdout=io.open(WORK / "server.log", "w", encoding="utf-8", errors="replace"),
    stderr=subprocess.STDOUT)

import requests   # noqa: E402

try:
    # ── 等服務起來
    for _ in range(60):
        if proc.poll() is not None:
            print("服務啟動失敗：")
            print(proc.stdout.read()[-3000:])
            sys.exit(1)
        try:
            requests.get(f"{BASE}/health", timeout=1)
            break
        except Exception:
            time.sleep(0.5)
    else:
        print(f"服務沒有起來，log: {WORK / 'server.log'}")
        proc.terminate()
        sys.exit(1)
    print("  服務就緒")

    # ── 註冊 + 登入
    u = {"username": "e2euser", "email": "e2e@example.com",
         "password": "E2ePass!23456", "role": "student"}
    r = requests.post(f"{BASE}/api/v1/auth/register", json=u, timeout=10)
    print(f"  註冊 {r.status_code}")
    r = requests.post(f"{BASE}/api/v1/auth/login",
                      data={"username": u["username"], "password": u["password"]}, timeout=10)
    r.raise_for_status()
    auth = {"Authorization": f"Bearer {r.json()['access_token']}"}
    print("  登入 OK")

    # ── 造一包「每類一個資料夾」的真 zip（多包一層，測自動下鑽）
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for cls in ("cats", "dogs"):
            for i in range(3):
                zf.writestr(f"my_pets/{cls}/{i}.jpg", b"\xff\xd8\xff" + bytes(200))
    payload = buf.getvalue()
    print(f"  資料集 zip：{len(payload)} bytes、6 個檔、包了一層 my_pets/")

    # ── 上傳（走真的 multipart）
    r = requests.post(f"{BASE}/api/v1/datasets/upload", headers=auth,
                      files={"file": ("pets.zip", payload, "application/zip")}, timeout=30)
    r.raise_for_status()
    up = r.json()
    print(f"  上傳 OK → {up['dataset_path']}")
    assert pathlib.Path(up["dataset_path"]).is_file(), "上傳的檔案不在磁碟上"

    # ── 送單
    r = requests.post(f"{BASE}/api/v1/jobs", headers=auth, timeout=10, json={
        "job_name": "e2e", "model_name": "resnet18",
        "dataset_path": up["dataset_path"],
        "config": {"epochs": 2, "batch_size": 4},
    })
    print(f"  送單 {r.status_code} {r.text[:200]}")
    r.raise_for_status()
    job_id = r.json()["job_id"]

    # ── 心跳 + 領工（模擬 worker）
    wh = {"Authorization": f"Bearer {TOKEN}"}
    requests.post(f"{BASE}/api/v1/worker/heartbeat", headers=wh, timeout=10, json={
        "node_id": "e2e-node", "available_gpus": ["0"], "pool_type": "batch",
        "shares_service_storage": True}).raise_for_status()
    r = requests.post(f"{BASE}/api/v1/worker/take", headers=wh, timeout=10, json={
        "node_id": "e2e-node", "available_gpus": ["0"], "pool_type": "batch",
        "shares_service_storage": True})
    r.raise_for_status()
    job = r.json()["job"]
    assert job, "沒領到任務"
    print(f"  領工 OK → has_dataset={job['has_dataset']} "
          f"filename={job['dataset_filename']} builtin={job['builtin_task']}")
    assert job["has_dataset"] is True
    assert job["builtin_task"] == "image_classification"
    assert "dataset_path" not in job

    # ── 真的用 worker 的程式碼下載 + 解壓
    sys.path.insert(0, str(ROOT / "gpu-worker"))
    os.environ["HOST_STORAGE_MOUNT"] = str(HOSTSTORE)
    import worker as gw
    gw.SERVICE_LAYER_URL = BASE
    gw.HEADERS = wh
    gw.HOST_STORAGE_MOUNT = str(HOSTSTORE)

    t0 = time.time()
    ds_dir = gw.prepare_dataset(job_id)
    print(f"  prepare_dataset → {ds_dir}  ({time.time()-t0:.2f}s)")

    digest = ds_dir.rsplit("/", 1)[-1]
    on_disk = HOSTSTORE / "datasets" / digest
    files = sorted(p.relative_to(on_disk).as_posix()
                   for p in on_disk.rglob("*") if p.is_file())
    print(f"  解壓後實際檔案：{files}")
    assert len([f for f in files if f.endswith('.jpg')]) == 6, files
    assert ".ready" in files

    # ── 快取：再跑一次不該重新解壓
    mtime_before = (on_disk / "my_pets" / "cats" / "0.jpg").stat().st_mtime
    t0 = time.time()
    ds_dir2 = gw.prepare_dataset(job_id)
    dt = time.time() - t0
    mtime_after = (on_disk / "my_pets" / "cats" / "0.jpg").stat().st_mtime
    assert ds_dir2 == ds_dir, (ds_dir, ds_dir2)
    assert mtime_before == mtime_after, "檔案被重寫了＝快取沒生效"
    print(f"  快取命中：路徑相同、檔案未被重寫（{dt:.2f}s）")

    # ── 陽性對照：拿掉 .ready 之後**應該**要重解，證明上面那把尺量得出差別
    import time as _t
    _t.sleep(0.05)
    (on_disk / ".ready").unlink()
    gw.prepare_dataset(job_id)
    mtime_redo = (on_disk / "my_pets" / "cats" / "0.jpg").stat().st_mtime
    assert mtime_redo != mtime_after, ("拿掉 .ready 卻沒重解 —— 上面的快取判定量不出差別，"
                                       "那條綠燈是假的")
    assert (on_disk / ".ready").exists(), "重解之後沒有補回 .ready"
    print("  陽性對照：拿掉 .ready 後確實重新解壓（尺是有效的）")

    # ── 暫存檔有沒有清乾淨
    leftovers = list((HOSTSTORE / "tmp").glob("*"))
    print(f"  暫存目錄殘留：{leftovers}")
    assert not leftovers, leftovers

    # ── 內建腳本落地
    script = gw.materialize_builtin_script("image_classification")
    landed = HOSTSTORE / "scripts" / "image_classification.py"
    print(f"  腳本落地 → {script}（實體 {landed.stat().st_size} bytes）")
    assert landed.is_file()

    # ── 訓練腳本的自動下鑽：對真的解壓結果跑一次
    sys.path.insert(0, str(ROOT / "gpu-worker" / "builtin_scripts"))
    import importlib.util
    spec = importlib.util.spec_from_file_location("ic", landed)
    ic = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ic)
    try:
        root_found = ic.find_data_root(str(on_disk))
        rel = pathlib.Path(root_found).relative_to(on_disk).as_posix()
        print(f"  find_data_root → {rel}（應為 my_pets）")
        assert rel == "my_pets", rel
    except ImportError as e:
        print(f"  （find_data_root 需要 torchvision，本機沒有，略過：{e}）")

    print("\n✅ 端對端通過：上傳 → 送單 → 領工 → 下載 → 解壓 → 快取 → 腳本落地")

finally:
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
    print(f"（暫存工作區保留於 {WORK}）")
