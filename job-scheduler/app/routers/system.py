from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
import os
from ..auth import get_current_user
from .. import models

router = APIRouter(prefix="/system", tags=["System Config Management"])

# 允許管理的系統設定檔路徑 (對應到 Container 內掛載的路徑)
ALLOWED_FILES = {
    ".env": "/app/.env",
    "docker-compose.yml": "/app/docker-compose.yml",
    "scheduler_policy.yaml": "/app/app/scheduler_policy.yaml",
    "sso_policy.yaml": "/app/app/sso_policy.yaml"
}

class FileContent(BaseModel):
    content: str

def verify_admin(current_user: models.User):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Forbidden: Admins only")

@router.get("/files")
async def list_files(current_user: models.User = Depends(get_current_user)):
    """
    列出系統允許修改的設定檔清單
    """
    verify_admin(current_user)
    return {
        "files": list(ALLOWED_FILES.keys())
    }

@router.get("/files/{filename}")
async def read_file(filename: str, current_user: models.User = Depends(get_current_user)):
    """
    讀取設定檔內容
    """
    verify_admin(current_user)
    if filename not in ALLOWED_FILES:
        raise HTTPException(status_code=403, detail="File not allowed or not found")
        
    filepath = ALLOWED_FILES[filename]
    
    if not os.path.exists(filepath):
        # 為了相容性，若檔案不存在，回傳空內容而非報錯
        return {"content": ""}
        
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
        return {"content": content}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/files/{filename}")
async def write_file(filename: str, payload: FileContent, current_user: models.User = Depends(get_current_user)):
    """
    更新設定檔內容
    """
    verify_admin(current_user)
    if filename not in ALLOWED_FILES:
        raise HTTPException(status_code=403, detail="File not allowed or not found")
        
    filepath = ALLOWED_FILES[filename]
    
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(payload.content)
        return {"message": f"Successfully updated {filename}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
