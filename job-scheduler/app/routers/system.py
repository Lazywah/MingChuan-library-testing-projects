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

import ipaddress

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .. import crud, models
from ..auth import get_current_user
from ..database import get_db
from ..rate_limit import limiter
from ..services import visit_counter

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


@router.get("/org-options", summary="組織對照清單（學院/學系、行政單位、校區）")
def get_org_options(
    db: Session = Depends(get_db),
    _user: models.User = Depends(get_current_user),
):
    """
    ZH: 下拉選單要用的三份清單。**要求登入**，理由同上面那支。

    ZH: 為什麼由後端給而不是前端寫死：系所會異動（2023→2025 之間銘傳併過兩個學院）。
        前端自己維護一份的話，改了對照表前端還是舊的，而且沒有任何提示。

    @node job-scheduler/app/routers/system.py::get_org_options
    """
    return crud.org_options(db)


@router.post("/onboarding", summary="送出初次登入設定（校區 + 學系／行政單位）")
def submit_onboarding(
    payload: dict = Body(..., description='{"campuses": ["台北"], "org_value": "資訊工程學系"}'),
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """
    ZH: 使用者自己送出初次設定。

    ZH: ⚠️ **v3.8 這段改了**：本來寫「允許重送」,而單次解鎖做完之後就不是了 ——
        第一次免鎖,之後要改必須有管理者核可的一次性解鎖（見 crud.complete_onboarding）。
        沒有解鎖時回 400 並告訴使用者去用「問題回報」申請。

    ZH: 網路不穩導致的重試會拿到那個 400 —— 代價可以接受,因為第一次送出時
        onboarded_at 還是 NULL,重試仍然會成功;只有**已經存檔成功過**的重試會被擋,
        而那本來就不該再改。

    @node job-scheduler/app/routers/system.py::submit_onboarding
    """
    # ZH: v4.3 常用信箱：初次設定順手設定（可留空）。它**不在**鎖定契約裡
    #     （隨時可用 PUT /auth/me 改），所以驗完直接寫、不看解鎖。
    ce = payload.get("contact_email")
    if ce is not None:
        ce = str(ce).strip()
        if ce:
            import re as _re
            if not _re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", ce):
                raise HTTPException(status_code=400, detail="常用信箱格式不對")
        user.contact_email = ce or None

    try:
        u = crud.complete_onboarding(db, user,
                                     payload.get("campuses") or [],
                                     payload.get("org_value"),
                                     role=payload.get("role"))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"onboarded_at": u.onboarded_at, "campuses": crud.campuses_of(db, u.id),
            "department": u.department, "unit": u.unit}


# ==============================================================================
# ZH: 網站到訪計數（v4.24）| EN: site visit counter
# ==============================================================================
# ZH: 🔴 **這兩支刻意不要求登入。** 它們回答的是「有多少人來過這個網站」——
#     把它們關在登入後面就只剩下「有多少人登入過」，那是另一個問題
#     （而且管理端的使用統計已經在回答了）。
#
# ZH: 回傳的是**人次**（同一位訪客當天只算一次），不是人數。
#     去重與隱私的做法見 services/visit_counter.py 的檔頭：不存 IP，
#     存的是把日期揉進去的雜湊，跨天對不起來。
# ==============================================================================

@router.post("/visit", summary="記一次到訪（公開）")
@limiter.limit("600/hour")
def record_site_visit(
    request: Request,
    payload: dict = Body(default={}),
    db: Session = Depends(get_db),
):
    """
    ZH: 前端每個瀏覽器工作階段打一次。回傳目前的三個數字。

    ZH: ⚠ 速率限制放得很鬆（600/hour）是因為**校園是 NAT** ——
        幾百個人共用一個對外 IP，限太緊會把整棟樓一起擋掉。
        它擋的是「有人寫迴圈灌數字」，不是正常流量。

    ZH: 🔴 訪客 IP 只從**我們自己的 nginx** 給的 `X-Real-IP` 取，而且
        只在來源是內網位址時才信。8002 是對外開著的，直接打那個埠的人
        可以自己帶一個假的 X-Real-IP —— 不檢查來源的話，那個標頭
        等於讓人任意指定身分。

    @node job-scheduler/app/routers/system.py::record_site_visit
    """
    stats = visit_counter.record_visit(
        db,
        visitor_id=str((payload or {}).get("visitor_id") or "")[:64] or None,
        ip=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return stats


@router.get("/visits", summary="到訪人次：本日／當月／歷史（公開）")
def get_site_visits(db: Session = Depends(get_db)):
    """
    ZH: 只讀，不會累加 —— 重新整理頁面不該讓數字自己長大。

    @node job-scheduler/app/routers/system.py::get_site_visits
    """
    return visit_counter.get_stats(db)


def _client_ip(request: Request) -> str | None:
    """
    ZH: 取訪客 IP（只用來算雜湊，不落地）。

    ZH: 判準：直連來源是內網（我們的 nginx 容器）才信 `X-Real-IP`；
        否則用直連來源本身。⚠ 反過來寫的話（先信標頭）等於把計數的
        去重鍵交給客戶端決定。

    @node job-scheduler/app/routers/system.py::_client_ip
    """
    direct = request.client.host if request.client else None
    if direct and _is_private(direct):
        fwd = request.headers.get("x-real-ip") or ""
        fwd = fwd.split(",")[0].strip()
        if fwd:
            return fwd
    return direct


def _is_private(ip: str) -> bool:
    """ZH: 內網位址嗎？（判不出來就當成不是 —— 往保守的方向倒）

    @node job-scheduler/app/routers/system.py::_is_private
    """
    try:
        return ipaddress.ip_address(ip).is_private
    except ValueError:
        return False
