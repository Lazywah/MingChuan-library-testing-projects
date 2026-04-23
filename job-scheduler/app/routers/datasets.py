from fastapi import APIRouter, Depends, File, UploadFile, HTTPException
from typing import Dict, Any
import os
import uuid
import shutil

from .. import models
from ..auth import get_current_user

router = APIRouter(tags=["Datasets"])

DATASET_DIR = "/data/datasets"

@router.post("/upload")
async def upload_dataset(
    file: UploadFile = File(...),
    current_user: models.User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    ZH: 上傳資料集，並自動推薦訓練參數
    EN: Upload dataset and auto-suggest training config
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    # 確保資料夾存在
    user_dataset_dir = os.path.join(DATASET_DIR, str(current_user.id))
    os.makedirs(user_dataset_dir, exist_ok=True)

    # 產生唯一的檔名以避免覆蓋
    safe_filename = f"{uuid.uuid4().hex[:8]}_{file.filename}"
    file_path = os.path.join(user_dataset_dir, safe_filename)

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
