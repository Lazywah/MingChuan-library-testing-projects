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
    """
    if bearer_token:
        return bearer_token
    return request.cookies.get("ai_hud_token")


def authenticate_user(db: Session, username: str, password: str):
    """
    ZH: 驗證使用者帳號密碼
    EN: Authenticate user credentials

    Returns:
        ZH: 成功回傳 User 物件，失敗回傳 None
        EN: User object on success, None on failure
    """
    user = crud.get_user_by_username(db, username)
    if not user:
        return None
    if not crud.verify_password(password, user.hashed_password):
        return None
    if not user.is_active:
        return None
    return user


def create_access_token(data: dict, expires_delta: timedelta = None) -> str:
    """
    ZH: 建立 JWT Access Token
    EN: Create JWT access token

    Args:
        data: ZH: 要編碼的資料 (通常含 sub=username, role) | EN: Data to encode
        expires_delta: ZH: 自訂過期時間 | EN: Custom expiration time
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
    """
    async def role_checker(current_user: models.User = Depends(get_current_user)):
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"ZH: 權限不足，需要角色: {', '.join(allowed_roles)} | "
                       f"EN: Insufficient permissions, required role: {', '.join(allowed_roles)}"
            )
        return current_user
    return role_checker
