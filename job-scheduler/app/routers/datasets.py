from fastapi import APIRouter, Depends, File, UploadFile, HTTPException
from sqlalchemy.orm import Session
from typing import Dict, Any
import os
import uuid
import shutil
import pathlib
import re

from .. import models, crud
from ..auth import get_current_user
from ..database import get_db
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
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
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
    # ZH: 清理之前先留一份原始檔名——那是列表裡要顯示給人看的東西。
    #     只砍長度與控制字元，不動中文。
    safe_base_original = re.sub(r"[\x00-\x1f\x7f]", "", safe_base)[:200] or "dataset.zip"
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

    # ZH: v3.6 —— 建一筆紀錄。沒有紀錄就沒有列表、沒有刪除，
    #     而且**原始檔名會遺失**（存檔名已經清成 ASCII，「我的圖片.zip」在磁碟上
    #     是 0fad32ff_dataset.zip，列表裡沒得顯示）。
    ds = crud.create_dataset(db, user_id=current_user.id, original_name=safe_base_original,
                             stored_name=safe_filename,
                             size_bytes=os.path.getsize(file_path))

    return {
        "message": "Upload successful",
        # ZH: **這才是之後該用的東西**。dataset_path 保留是為了 v1/v1.5，
        #     但那是客戶端傳回來的字串，伺服器無從判斷所有權（見 submit_job 的檢查）。
        "dataset_id": ds.id,
        "dataset_path": file_path,
        "suggested_config": suggested_config
    }


# ==============================================================================
# ZH: v3.6 資料集管理 | EN: v3.6 Dataset management
# ==============================================================================
# ZH: 為什麼這幾個端點是必要的而不只是方便：每人 2 GB 配額，而在這之前
#     **沒有任何刪除的方法**——使用者一旦傳滿就永遠卡住（上傳 413，而他什麼都做不了）。


@router.get("")
def list_my_datasets(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    ZH: 列出自己上傳過的資料集。

    ZH: 一併回配額用量——「你用了多少、還剩多少」跟列表放在一起才有意義，
        分兩個請求拿的話畫面上一定會出現「兩邊數字對不起來」的一瞬間。

    @node job-scheduler/app/routers/datasets.py::list_my_datasets
    """
    rows = crud.list_datasets(db, current_user.id)
    used = sum(r.size_bytes or 0 for r in rows)
    return {
        "datasets": [
            {
                "id": r.id,
                "name": r.original_name,
                "size_bytes": r.size_bytes,
                "created_at": r.created_at,
                # ZH: 還在跑的單擋著不能刪——前端據此把刪除鈕變灰並說明原因
                "in_use_by_jobs": crud.dataset_active_jobs(db, r.id),
            }
            for r in rows
        ],
        "used_bytes": used,
        "quota_bytes": MAX_USER_STORAGE_BYTES,
    }


@router.delete("/{dataset_id}")
def delete_my_dataset(
    dataset_id: str,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    ZH: 刪掉自己的一份資料集。

    ZH: ⚠ 還有任務在排隊或執行中就**不給刪**。刪掉的話那張單會在領工之後才失敗，
        而使用者根本不會把兩件事聯想在一起（他只會看到「訓練莫名其妙失敗了」）。

    @node job-scheduler/app/routers/datasets.py::delete_my_dataset
    """
    ds = crud.get_dataset(db, dataset_id)
    # ZH: 找不到與不是自己的**回同一個 404** —— 回 403 等於告訴對方「這個 id 存在」。
    if not ds or ds.user_id != current_user.id:
        raise HTTPException(status_code=404,
                            detail="ZH: 找不到這份資料集 | EN: Dataset not found")

    n = crud.dataset_active_jobs(db, dataset_id)
    if n:
        raise HTTPException(
            status_code=409,
            detail=f"ZH: 還有 {n} 個任務正在用這份資料，跑完之後才能刪 | "
                   f"EN: {n} job(s) are still using this dataset; delete it after they finish")

    crud.delete_dataset(db, ds, lambda d: _remove_dataset_file(d))
    return {"status": "deleted", "id": dataset_id}


def _remove_dataset_file(ds) -> None:
    """ZH: 刪掉磁碟上的檔案。找不到不算錯（可能已經被手動清掉）。

    @node job-scheduler/app/routers/datasets.py::_remove_dataset_file
    """
    try:
        os.remove(crud.dataset_file_path(DATASET_DIR, ds))
    except OSError:
        pass
