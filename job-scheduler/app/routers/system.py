# ==============================================================================
# ZH: 系統設定 —— 前台唯讀端點
# EN: System settings — read-only endpoint for the user-facing site
#
# ZH: 這支 router 原本是「用 API 直接覆寫 .env / docker-compose.yml」，已停用：
#     那等於讓管理員從網頁蓋掉 JWT_SECRET_KEY。停用當時寫下的後續計畫是
#     「改以個別欄位受控修改 + 型別驗證 + 白名單」——
#     **寫入側**已經由 v3.1 的營運旋鈕實作（admin.py 的 /system-settings，
#     存 SystemConfig、型別檢查、範圍夾限）。
#
# ZH: v3.8 補上**讀取側**：前台在此之前完全沒有任何管道讀到營運設定，
#     於是「額度什麼時候重置」「任務跑多久會被砍」只存在管理端的畫面上，
#     使用者只能來問。這支端點就是那條管道，而且只開白名單。
# EN: v3.8 adds the read side: a whitelisted, read-only view of operational
#     settings so the user-facing pages can state the values instead of guessing.
# ==============================================================================

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import crud, models
from ..auth import get_current_user
from ..database import get_db

# ZH: 前綴由 main.py 的 include_router 給 —— 其他 16 支 router 都是這樣，
#     只有這支原本自帶 prefix="/system"。兩種寫法混用時，
#     「這條路徑到底長什麼樣」要看兩個檔案才拼得出來。
router = APIRouter(tags=["System Config Management"])


@router.get("/public-settings", summary="前台可見的營運設定（唯讀白名單）")
def get_public_settings(
    db: Session = Depends(get_db),
    _user: models.User = Depends(get_current_user),
):
    """
    ZH: 回傳 `{key: 生效值}`，只含 `SYSTEM_SETTINGS` 裡標了 `public` 的旋鈕。

    ZH: **要求登入**。這些值本身不是機密，但前台會用到它們的頁面
        （使用量／訓練／實驗室）本來就都在登入後，
        開成匿名等於平白多一個對外面孔，換不到任何東西。

    ZH: 白名單在 crud.get_public_settings 裡，不在這裡 ——
        新增旗標的人改的是設定表那一份，不必記得回來改 router。

    @node job-scheduler/app/routers/system.py::get_public_settings
    """
    return {"settings": crud.get_public_settings(db)}
