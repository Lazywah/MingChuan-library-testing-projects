from fastapi import APIRouter, Depends, File, UploadFile, HTTPException
from typing import Dict, Any
import os
import uuid
import shutil
import pathlib
import re

from .. import models
from ..auth import get_current_user
from ..rate_limit import limiter
from fastapi import Request

router = APIRouter(tags=["Datasets"])

DATASET_DIR = "/data/datasets"

# H-4: ZH: 允許的副檔名白名單，拒絕可執行檔與腳本
# EN: Allowed extension whitelist — rejects executables and scripts
ALLOWED_EXTENSIONS = {
    ".csv", ".jsonl", ".json", ".txt",
    ".zip", ".tar", ".gz", ".bz2",
    ".pt", ".pth", ".ckpt", ".safetensors",
}

# H-5: ZH: 每位使用者最大儲存空間 2 GB | EN: Max 2 GB per user
MAX_USER_STORAGE_BYTES = 2 * 1024 ** 3


@router.post("/upload")
@limiter.limit("10/hour")  # M-9: ZH: 防止暴力上傳 | EN: Prevent upload flooding
async def upload_dataset(
    request: Request,
    file: UploadFile = File(...),
    current_user: models.User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    ZH: 上傳資料集，並自動推薦訓練參數
    EN: Upload dataset and auto-suggest training config

    @node job-scheduler/app/routers/datasets.py::upload_dataset
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    # H-4: ZH: 檢查副檔名白名單 | EN: Check extension whitelist
    ext = pathlib.Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"ZH: 不允許的檔案類型 '{ext}'，允許類型: {', '.join(sorted(ALLOWED_EXTENSIONS))} | "
                   f"EN: File type '{ext}' not allowed. Permitted: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
        )

    # 確保資料夾存在
    user_dataset_dir = os.path.join(DATASET_DIR, str(current_user.id))
    os.makedirs(user_dataset_dir, exist_ok=True)

    # H-5: ZH: 檢查個人儲存配額 | EN: Check per-user storage quota
    user_dir_path = pathlib.Path(user_dataset_dir)
    used_bytes = sum(f.stat().st_size for f in user_dir_path.rglob("*") if f.is_file())
    # Use content-length header as an estimate if available (file.size may be None for chunked uploads)
    incoming_size = file.size or 0
    if used_bytes + incoming_size > MAX_USER_STORAGE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"ZH: 個人儲存配額已超出（上限 2 GB） | EN: Storage quota exceeded (max 2 GB per user)"
        )

    # C-5: ZH: 使用 pathlib.Path(...).name 防止路徑穿越攻擊
    # EN: Strip directory components via pathlib to prevent path traversal
    safe_base = pathlib.Path(file.filename).name
    # ZH: v3.6 —— 存檔名只留「安全字元」。
    #     為什麼：`JobCreate.dataset_path` 有字元白名單（防命令注入），
    #     而這裡回傳的路徑會被原封不動拿去送單。原本把使用者的檔名直接接進路徑，
    #     於是 **中文檔名會上傳成功（201）、送單失敗（422）** ——
    #     而中文檔名對這裡的使用者是常態，等於整條路走不通。
    #     修在這一側：存到磁碟的名字**不需要**是使用者的名字（前面已經有 uuid 了）。
    #     不去放寬那條白名單——它擋的是注入。
    #     順帶把空白、引號、括號等等一起處理掉，那些會踩到同一條線。
    # EN: v3.6 — sanitise the stored name to the same charset JobCreate.dataset_path
    #     accepts. A CJK filename used to upload fine (201) and then fail to submit (422).
    #     ⚠ 只清**主檔名**，副檔名另外接回去——連副檔名一起清再 strip("._-")
    #       會把那個點也吃掉，`我的圖片.zip` 變成 `zip`（實測踩過）。
    #       ext 已經過白名單，本來就是安全的。
    stem = re.sub(r"[^A-Za-z0-9._-]", "_", pathlib.Path(safe_base).stem).strip("._-")
    safe_base = f"{stem or 'dataset'}{ext}"
    uuid4_prefix = uuid.uuid4().hex[:8]
    safe_filename = f"{uuid4_prefix}_{safe_base}"
    file_path = os.path.join(user_dataset_dir, safe_filename)

    # C-5: ZH: 二次確認解析路徑在允許目錄內 | EN: Double-check resolved path stays inside allowed dir
    resolved = os.path.realpath(file_path)
    allowed_root = os.path.realpath(user_dataset_dir)
    if not resolved.startswith(allowed_root + os.sep) and resolved != allowed_root:
        raise HTTPException(status_code=400, detail="Invalid filename")

    # 儲存檔案
    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {str(e)}")

    # 自動解析邏輯 (簡易版)
    suggested_config = {
        "epochs": 10,
        "batch_size": 8,
        "learning_rate": 0.001
    }

    try:
        # 如果是文字資料集，簡單計算行數
        if file.filename.endswith(".jsonl") or file.filename.endswith(".csv"):
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                lines = sum(1 for _ in f)
                
            if lines > 50000:
                suggested_config["epochs"] = 3
                suggested_config["batch_size"] = 32
            elif lines > 10000:
                suggested_config["epochs"] = 5
                suggested_config["batch_size"] = 16
            else:
                suggested_config["epochs"] = 10
                suggested_config["batch_size"] = 8
                
        # 若是壓縮檔，則依據檔案大小推測
        elif file.filename.endswith(".zip"):
            size_mb = os.path.getsize(file_path) / (1024 * 1024)
            if size_mb > 500:
                suggested_config["epochs"] = 5
                suggested_config["batch_size"] = 32
            elif size_mb > 100:
                suggested_config["epochs"] = 10
                suggested_config["batch_size"] = 16

    except Exception as e:
        print(f"Warning: Dataset analysis failed: {e}")

    return {
        "message": "Upload successful",
        "dataset_path": file_path,
        "suggested_config": suggested_config
    }
