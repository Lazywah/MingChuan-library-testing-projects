"""
==============================================================================
SSO Router — Mock / CAS / OIDC 三種 provider 的 HTTP 端點
SSO Router — HTTP endpoints for Mock / CAS / OIDC providers
==============================================================================
ZH: 端點清單（v2.1 完整版）：
    GET  /api/v1/sso/login                  既有，依當下 provider 跳轉（mock/cas/oidc fallback to mock）
    GET  /api/v1/sso/callback               既有，CAS / mock 的 ticket 回呼
    GET  /api/v1/sso/mock-login             既有，mock SSO 的 HTML 登入頁
    POST /api/v1/sso/mock-submit            既有，mock 表單送出

    GET  /api/v1/sso/oidc/login             v2.1 新增，跳轉至 Microsoft 授權頁
    GET  /api/v1/sso/oidc/callback          v2.1 新增，OIDC code → token → user
    GET  /api/v1/sso/providers              v2.1 新增，前端用來決定按鈕顯示
    GET  /api/v1/sso/password-change-info   v2.1 新增，告訴前端密碼變更 UI 該怎麼顯示

EN: Endpoints (v2.1 full):
    legacy: /login, /callback, /mock-login, /mock-submit
    v2.1:   /oidc/login, /oidc/callback, /providers, /password-change-info
==============================================================================
"""
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Query, HTTPException, Form, Request
from fastapi.responses import RedirectResponse, HTMLResponse
from sqlalchemy.orm import Session

from ..database import get_db
from ..crud import (
    get_user_by_username,
    get_user_by_email,
    get_user_by_external_id,
    create_sso_user,
    upgrade_to_sso,
)
from ..auth import create_access_token
from ..config import SSO_POLICY, OIDC_ENABLED
from ..sso_client import get_sso_client, build_oidc_client_if_enabled

logger = logging.getLogger(__name__)
router = APIRouter()

# ==============================================================================
# Client singletons（啟動時建立一次，避免每次請求都重建）
# ==============================================================================
# 主 SSO client（給 /login + /callback 用，依 mock_mode + provider 決定）
mock_mode = SSO_POLICY.get("mock_mode", True)
sso_client = get_sso_client(mock_mode=mock_mode, config=SSO_POLICY)

# v2.1 OIDC 專屬 client（給 /oidc/login + /oidc/callback 用）
# 若 OIDC 設定不完整則為 None，相關端點會回 503
oidc_client = build_oidc_client_if_enabled(SSO_POLICY)


# ==============================================================================
# 共用：建立 / 升級 user 並簽 JWT 後 302 回前端
# ==============================================================================
def _finalize_sso_login(db: Session, user_info: dict, request: Request = None) -> RedirectResponse:
    """
    ZH: 共用流程（mock / cas / oidc 三條路徑都會走這裡）
        1. 依 external_id → email → username 順序找既有使用者
        2. 找不到就 create_sso_user；找到 local 帳號就 upgrade_to_sso
        3. 簽 JWT，302 回前端帶 ?sso_token=
    """
    username = user_info.get("username")
    if not username:
        raise HTTPException(status_code=400, detail="SSO 回傳的資訊不包含 username")

    auth_source = user_info.get("auth_source", "sso_mock")
    external_id = user_info.get("external_id")

    # 識別優先序：external_id (oid) → email → username
    user = None
    if external_id:
        user = get_user_by_external_id(db, external_id)
    if user is None and user_info.get("email"):
        user = get_user_by_email(db, user_info["email"])
    if user is None:
        user = get_user_by_username(db, username)

    if user is None:
        # 首次登入：建新 SSO 帳號
        user = create_sso_user(
            db,
            username=username,
            email=user_info.get("email") or f"{username}@unknown",
            role=user_info.get("role", "student"),
            auth_source=auth_source,
            external_id=external_id,
        )
        logger.info(f"SSO 首次登入，建立帳號 username={username} auth_source={auth_source}")
    elif user.auth_source == "local":
        # 既有 local 帳號首次走 SSO → 升級為 SSO（含寫入 external_id）
        logger.warning(
            f"local 帳號 {username} 首次走 {auth_source} 登入，自動升級。"
            f" 既有 hashed_password 保留但無法再變更（update_user 會拒絕）。"
        )
        upgrade_to_sso(db, user, auth_source=auth_source, external_id=external_id)

    # v2.1 修補：SSO 登入也要寫 last_login_* + last_activity（本機 /login 有寫但 SSO 之前漏寫）
    try:
        now = datetime.now(timezone.utc)
        user.last_login_time = now
        user.last_activity = now
        user.login_count = (user.login_count or 0) + 1
        if request and request.client:
            user.last_login_ip = request.client.host
        db.commit()
    except Exception as e:
        logger.error(f"SSO 登入時更新 last_login_* 失敗: {e}")
        db.rollback()

    # 簽 JWT 並 302 回前端
    # v2.1 bug fix: 之前 redirect 到 "/" 會跑到 Open WebUI（nginx 把 / 代理給 open-webui），
    # 改為 "/train/" 才會回到本平台的 web-ui SPA，由 setupSSOLogin IIFE 抓 ?sso_token= 進 dashboard
    access_token = create_access_token(data={"sub": user.username, "role": user.role})
    response = RedirectResponse(url=f"/train/?sso_token={access_token}")
    # v2.1: 同步設 cookie，讓瀏覽器直接導航 /code/ 時也帶得到 token (auth_request 用)
    # SPA 透過 URL ?sso_token= 自行存 localStorage 給 fetch 用，cookie 純粹給瀏覽器
    # 自動帶到 /code/ 走 nginx auth_request；兩個 storage 用途不同。
    response.set_cookie(
        key="ai_hud_token",
        value=access_token,
        max_age=7200,           # 2 小時，與 JWT 預設一致
        httponly=True,           # v2.1: SPA 不需要讀 cookie (走 URL 拿 token)，防 XSS 偷
        samesite="lax",
        path="/",
    )
    return response


# ==============================================================================
# 既有端點：/login + /callback（v1 邏輯保留，僅微調呼叫 _finalize_sso_login）
# ==============================================================================
@router.get("/login", summary="SSO 登入導向（依 provider 配置）")
def sso_login():
    """導向至當下 provider 的登入頁面（CAS / Mock / OIDC fallback to mock）"""
    url = sso_client.get_login_url()
    return RedirectResponse(url=url)


@router.get("/callback", summary="SSO 登入回呼網址（CAS / Mock）")
def sso_callback(
    request: Request,
    ticket: str = Query(..., description="CAS Server 或 Mock 傳回的 ticket"),
    db: Session = Depends(get_db),
):
    """處理 SSO 驗證結果並產生系統的 JWT Token"""
    try:
        user_info = sso_client.validate_ticket(ticket)
        return _finalize_sso_login(db, user_info, request=request)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))
    except Exception as e:
        logger.exception("SSO callback failed")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/mock-login", response_class=HTMLResponse, summary="模擬 SSO 登入畫面")
def mock_sso_login_page():
    """Mock 模式下的內建登入 HTML 表單（dev 環境用，UI 不曝光此入口）"""
    if not mock_mode and SSO_POLICY.get("provider") != "mock":
        raise HTTPException(status_code=404, detail="Mock SSO is disabled")

    users = SSO_POLICY.get("mock", {}).get("users", [])
    options = "".join(
        f'<option value="{u.get("student_id")}">{u.get("name")} ({u.get("student_id")})</option>'
        for u in users
    )
    html_content = f"""
    <html>
        <head>
            <title>Mock SSO Login</title>
            <style>
                body {{ font-family: Arial; padding: 50px; background: #f0f4f8; }}
                .container {{ max-width: 400px; margin: 0 auto; background: white; padding: 20px; border-radius: 8px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }}
                h2 {{ text-align: center; color: #333; }}
                select, button {{ width: 100%; padding: 10px; margin-top: 15px; font-size: 16px; }}
                button {{ background: #4f46e5; color: white; border: none; cursor: pointer; border-radius: 4px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <h2>Mock SSO 驗證伺服器</h2>
                <form action="/api/v1/sso/mock-submit" method="post">
                    <label>請選擇登入身分：</label>
                    <select name="ticket">
                        {options}
                    </select>
                    <button type="submit">確認登入</button>
                </form>
            </div>
        </body>
    </html>
    """
    return html_content


@router.post("/mock-submit", summary="處理模擬登入表單的送出")
def mock_sso_submit(ticket: str = Form(...)):
    if not mock_mode and SSO_POLICY.get("provider") != "mock":
        raise HTTPException(status_code=404, detail="Mock SSO is disabled")
    return RedirectResponse(url=f"/api/v1/sso/callback?ticket={ticket}", status_code=303)


# ==============================================================================
# v2.1 新增：OIDC 端點
# ==============================================================================
@router.get("/oidc/login", summary="v2.1 OIDC 登入（跳轉 Microsoft）")
def oidc_login():
    """
    ZH: 跳轉至 Microsoft Entra ID 授權頁。state 由 client 內部簽好寫進 URL。
    EN: Redirect to Microsoft Entra ID. State signed inside client.
    """
    if not OIDC_ENABLED or oidc_client is None:
        raise HTTPException(
            status_code=503,
            detail="OIDC is not configured. Please contact system administrator.",
        )
    url = oidc_client.get_login_url()
    return RedirectResponse(url=url)


@router.get("/oidc/callback", summary="v2.1 OIDC callback (Microsoft 回呼)")
def oidc_callback(
    request: Request,
    code: str = Query(..., description="Microsoft 回傳的 authorization code"),
    state: str = Query(..., description="登入時簽好的 state，用於防 CSRF"),
    db: Session = Depends(get_db),
):
    """
    ZH: OIDC callback 流程（v1.1 完整版）
        1. 驗證 state（防 CSRF + replay）
        2. 用 code 換 id_token（OIDCSSOClient.validate_ticket）
        3. 共用 _finalize_sso_login 建 user + 簽 JWT
    """
    if not OIDC_ENABLED or oidc_client is None:
        raise HTTPException(status_code=503, detail="OIDC is not configured")

    if not oidc_client.verify_state(state):
        logger.warning(f"OIDC callback state invalid (state={state[:20]}...)")
        raise HTTPException(status_code=400, detail="Invalid or expired state")

    try:
        user_info = oidc_client.validate_ticket(code)
        return _finalize_sso_login(db, user_info, request=request)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))
    except Exception:
        logger.exception("OIDC callback failed")
        raise HTTPException(status_code=500, detail="OIDC login failed")


@router.get("/providers", summary="v2.1 列出當下啟用的 SSO providers")
def list_providers():
    """
    ZH: 給前端登入頁用 — 決定要顯示哪些 SSO 按鈕。
        Mock SSO 永遠不在此列表（user UI 不曝光）。
    EN: For the user UI login page to decide which buttons to show.
        Mock SSO is intentionally never listed here (it's dev-only via direct URL).
    """
    providers: list[str] = []
    if OIDC_ENABLED and oidc_client is not None:
        providers.append("oidc")
    # cas 未來啟用時也加入此處
    return {"providers": providers}


@router.get("/password-change-info", summary="v2.1 告訴前端密碼變更 UI 該怎麼顯示")
def password_change_info():
    """
    ZH: 前端設定頁讀取此端點來決定要顯示「密碼輸入框」還是「IdP 連結」。
        本端點不需要認證（用 auth_source 對應 IdP 連結，不洩漏使用者資訊）。
    EN: Frontend Settings page reads this to render password-change UI.
    """
    oidc_cfg = SSO_POLICY.get("oidc", {})
    return {
        "providers": {
            "local": {
                "change_supported": True,
                "change_url": None,  # 用本機 PUT /api/v1/auth/me
            },
            "sso_mock": {
                "change_supported": False,
                "change_url": None,  # mock 帳號的密碼是隨機產生，無法變更
                "message": "Mock SSO 帳號無密碼可變更",
            },
            "sso_cas": {
                "change_supported": False,
                "change_url": None,  # 看學校 CAS 的密碼變更頁
                "message": "請至學校 CAS 系統變更密碼",
            },
            "sso_oidc": {
                "change_supported": False,
                "change_url": oidc_cfg.get(
                    "password_change_url",
                    "https://account.activedirectory.windowsazure.com/ChangePassword.aspx",
                ),
                "reset_url": oidc_cfg.get(
                    "password_reset_url",
                    "https://passwordreset.microsoftonline.com/",
                ),
                "message": "您使用學校 Microsoft 帳號登入，密碼由學校統一管理",
            },
        },
    }
