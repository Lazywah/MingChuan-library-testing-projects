"""
==============================================================================
Module 6: JWT 認證核心 (JWT Authentication Core)
==============================================================================
ZH: 用途：處理 JWT Token 的建立、驗證、解碼，以及使用者身份識別
EN: Purpose: Handle JWT token creation, verification, decoding, and user identity

ZH: 流程：
    登入成功 → create_access_token() → 回傳 JWT
    後續請求 → get_current_user() → 解碼 JWT → 回傳使用者物件
    權限檢查 → require_role() → 驗證角色是否匹配
EN: Flow:
    Login success → create_access_token() → return JWT
    Subsequent requests → get_current_user() → decode JWT → return user object
    Permission check → require_role() → verify role matches

ZH: 模組化設計：
    - 此模組只負責「認證」，不處理路由 (路由在 routers/auth.py)
    - 可替換為 OAuth2、LDAP 等其他認證方式，只需修改此檔案
    - get_current_user 透過 FastAPI Depends 注入到任何需要認證的路由
EN: Modular design:
    - This module only handles "authentication", not routing (routing in routers/auth.py)
    - Can be swapped to OAuth2, LDAP etc, only modify this file
    - get_current_user injected via FastAPI Depends to any authenticated route
==============================================================================
"""

from datetime import datetime, timedelta, timezone
from jose import JWTError, jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from . import crud, models, schemas
from .database import get_db
from .config import settings

import logging

logger = logging.getLogger(__name__)

# ==============================================================================
# ZH: OAuth2 Token URL 配置 | EN: OAuth2 Token URL configuration
# ZH: tokenUrl 要與 routers/auth.py 中的 login 路徑一致
# EN: tokenUrl must match the login path in routers/auth.py
# ==============================================================================
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


def _extract_token(request: Request, bearer_token: str | None) -> str | None:
    """
    ZH: v2.1 — 同時支援 Authorization: Bearer header 與 ai_hud_token cookie
    EN: v2.1 — accept JWT from either Authorization header or ai_hud_token cookie

    Cookie 路徑用於瀏覽器直接導航的場景 (例：window.open('/code/...'))，
    這類請求 fetch API 才能塞 header，直接 navigate 無法。

    @node job-scheduler/app/auth.py::_extract_token
    """
    if bearer_token:
        return bearer_token
    return request.cookies.get(cookie_name_for(request))


# ==============================================================================
# ZH: v3.8 —— 兩端的 cookie 分開
# ==============================================================================
USER_COOKIE = "ai_hud_token"
ADMIN_COOKIE = "ai_hud_admin_token"


def cookie_name_for(request: Request) -> str:
    """
    ZH: 這個請求該用哪一個 cookie 名稱。

    ZH: 🔴 為什麼要分開：cookie 規格**不區分 port**。
        使用者端（:80）與管理端（:8888）是同一個 host，
        共用一個 `ai_hud_token` 的話，**後登入的那一邊會覆蓋先登入的**。
        2026-08-27 稽核實測：在使用者端登入之後，管理端的 cookie 身分
        也跟著變成那個學生，管理端 API 開始回 403。

    ZH: 目前兩個 UI 都送 `Authorization: Bearer`，所以介面本身沒事；
        真正吃到影響的是**依賴 cookie 的路徑** —— 現在是 nginx 對
        Lab `/code/` 的 `auth_request`，未來任何新的導航式端點也會。
        而且 Bearer 過期時 `_extract_token` 會退回讀 cookie，
        那時身分就會變成「另一邊最後登入的人」。

    ZH: 怎麼知道請求來自哪一端：**由 nginx 明講**（`X-AIBase-Surface: admin`）。
        不能用 Host 判斷 —— nginx 傳的 `$host` **不含 port**，
        兩個 server 區塊看起來一模一樣。
        沒有這個表頭時一律當使用者端：直連 :8002 的（worker、健檢）
        本來就走 Bearer，不受影響。

    @node job-scheduler/app/auth.py::cookie_name_for
    """
    return (ADMIN_COOKIE
            if (request.headers.get("X-AIBase-Surface", "").strip().lower() == "admin")
            else USER_COOKIE)


def authenticate_user(db: Session, username: str, password: str):
    """
    ZH: 驗證使用者帳號密碼
    EN: Authenticate user credentials

    Returns:
        ZH: 成功回傳 User 物件，失敗回傳 None
        EN: User object on success, None on failure

    @node job-scheduler/app/auth.py::authenticate_user
    """
    user = crud.get_user_by_username(db, username)
    if not user:
        return None
    if not crud.verify_password(password, user.hashed_password):
        return None
    if not user.is_active:
        return None
    # ZH: 臨時帳號到期 —— 與停用給**同一個結果**（登不進來），
    #     但理由不同，所以分開判斷；日後要改成不同訊息時才有地方改。
    if is_expired(user):
        return None
    return user


def is_expired(user) -> bool:
    """ZH: 臨時帳號是否已經過期。

    ZH: 🔴 到期**不能只靠每日排程**。排程一天跑一次，中間最多有一整天的空窗——
        「到期日是昨天」的帳號今天照樣登得進來。所以登入與每次帶 token 的請求
        都要即時判斷。排程的角色是把 is_active 也設成 0，讓管理端看得出來。

    ZH: 沒有 expires_at = 永久帳號，不受影響。

    @node job-scheduler/app/auth.py::is_expired
    """
    exp = getattr(user, "expires_at", None)
    if exp is None:
        return False
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) >= exp


def create_access_token(data: dict, expires_delta: timedelta = None) -> str:
    """
    ZH: 建立 JWT Access Token
    EN: Create JWT access token

    Args:
        data: ZH: 要編碼的資料 (通常含 sub=username, role) | EN: Data to encode
        expires_delta: ZH: 自訂過期時間 | EN: Custom expiration time

    @node job-scheduler/app/auth.py::create_access_token
    """
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return encoded_jwt


async def get_current_user(
    request: Request,
    token: str | None = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> models.User:
    """
    ZH: 從 JWT Token 取得當前使用者 (FastAPI 依賴注入)
    EN: Get current user from JWT token (FastAPI dependency injection)

    ZH: 用法：在路由參數中加入 current_user = Depends(get_current_user)
    EN: Usage: add current_user = Depends(get_current_user) to route params

    v2.1: 同時支援 Authorization: Bearer (fetch/SPA 用) 與 ai_hud_token cookie
    (瀏覽器直接導航如 window.open('/code/...') 走這條路)

    @node job-scheduler/app/auth.py::get_current_user
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="ZH: 無法驗證憑證 | EN: Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    token = _extract_token(request, token)
    if not token:
        raise credentials_exception
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = crud.get_user_by_username(db, username=username)
    if user is None:
        raise credentials_exception
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="ZH: 帳號已停用 | EN: Account is disabled"
        )
    # ZH: 🔴 已經發出去的 token 也要擋。只在登入時檢查的話，
    #     到期前登入的人可以繼續用到 token 自己過期為止（預設 120 分鐘）。
    if is_expired(user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="ZH: 臨時帳號已到期 | EN: Temporary account has expired"
        )

    # v2.1 在線狀態修正：每次 API 呼叫節流更新 last_activity（避免每 request 都寫 DB）
    # 規則：last_activity 為 None 或距離現在 > 1 分鐘才寫入
    try:
        from datetime import datetime, timezone, timedelta
        now = datetime.now(timezone.utc)
        last = user.last_activity
        if last is not None and last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        if last is None or (now - last) > timedelta(minutes=1):
            user.last_activity = now
            db.commit()
    except Exception:
        db.rollback()  # 更新失敗不影響本次請求

    return user


def require_admin(current_user: models.User = Depends(get_current_user)) -> models.User:
    """
    ZH: 管理權限檢查 —— **看 `is_admin` 旗標，不看 `role`**（v3.8 起）。

    ZH: 拆開的理由：`role` 是「你是誰」（學生／教師／職員／訪客）,
        `is_admin` 是「你能做什麼」。合成一個欄位時,一個學生兼系統管理員
        只能二選一 —— 選 admin 的話他在「依身分」統計裡會被算成管理員。

    ZH: 這裡讀的是**資料庫**的值不是 JWT 的 claim,所以取消權限**立刻生效**,
        不需要等舊 token 過期。

    ZH: 🔴 這是全站唯一的管理權限判定點。要加新的管理端功能就 Depends 它,
        不要自己寫 `if user.role == "admin"` —— 那種散在各處的判定
        正是 v3.8 之前要改一次得找四個地方的原因。

    @node job-scheduler/app/auth.py::require_admin
    """
    if not getattr(current_user, "is_admin", 0):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="ZH: 這個功能只有管理員能用 | EN: Forbidden: Admins only",
        )
    return current_user


def require_role(*allowed_roles: str):
    """
    ZH: 角色權限檢查裝飾器 (積木式可組合)
    EN: Role-based permission check decorator (composable building block)

    ZH: 用法：
        @router.get("/admin-only")
        def admin_page(user = Depends(require_role("admin"))):
            ...

        @router.get("/teacher-or-admin")
        def teacher_page(user = Depends(require_role("teacher", "admin"))):
            ...
    EN: Usage: see above

    @node job-scheduler/app/auth.py::require_role
    """
    async def role_checker(current_user: models.User = Depends(get_current_user)):
        """@node job-scheduler/app/auth.py::require_role.<nested@170>.role_checker"""
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"ZH: 權限不足，需要角色: {', '.join(allowed_roles)} | "
                       f"EN: Insufficient permissions, required role: {', '.join(allowed_roles)}"
            )
        return current_user
    return role_checker
