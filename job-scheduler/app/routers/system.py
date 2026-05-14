# ==============================================================================
# ZH: 系統設定檔直接編輯功能已停用
# EN: Direct system file editing has been disabled
#
# ZH: 原因：允許管理員透過 API 以原始文字覆寫 .env / docker-compose.yml 存在
#     嚴重的安全風險（可覆蓋 JWT_SECRET_KEY 等關鍵憑證）。
# EN: Reason: Allowing admins to overwrite .env / docker-compose.yml via API
#     posed a critical security risk (e.g. overwriting JWT_SECRET_KEY).
#
# ZH: 後續計畫：改以獨立的輸入框對個別設定值進行受控修改，並加入型別驗證
#     與白名單限制，確保每個欄位僅接受合法範圍的資料。
# EN: Future plan: Replace with individual input-box fields for controlled edits,
#     with type validation and whitelisted keys to ensure only valid values
#     are accepted per field.
# ==============================================================================

from fastapi import APIRouter

router = APIRouter(prefix="/system", tags=["System Config Management"])

# ZH: 此 router 目前不對外暴露任何端點。
# EN: This router currently exposes no endpoints.
