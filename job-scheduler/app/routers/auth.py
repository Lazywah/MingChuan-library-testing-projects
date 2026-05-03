"""
==============================================================================
Router: 認證路由群組 (Authentication Routes)
==============================================================================
ZH: 用途：處理使用者註冊、登入、資訊查詢、Token 額度管理的 HTTP 端點
EN: Purpose: Handle HTTP endpoints for registration, login, user info, token quota

ZH: 端點清單：
    POST /api/v1/auth/register        → 使用者註冊
    POST /api/v1/auth/login           → 使用者登入 (回傳 JWT)
    GET  /api/v1/auth/me              → 取得當前使用者資訊
    GET  /api/v1/auth/usage           → 查詢 Token 用量
    POST /api/v1/auth/usage/increment → 增加 Token 使用量

ZH: 模組化設計：
    - 此 Router 可獨立加入/移除，不影響 Jobs Router
    - 掛載方式：app.include_router(auth_router, prefix="/api/v1/auth")
    - 移除方式：註解掉 main.py 中的 include_router 即可
EN: Modular design:
    - This Router can be added/removed independently, won't affect Jobs Router
    - Mount: app.include_router(auth_router, prefix="/api/v1/auth")
    - Remove: comment out include_router in main.py
==============================================================================
"""

from fastapi import APIRouter, Depends, HTTPException, status, Request, BackgroundTasks
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from datetime import datetime

from .. import crud, schemas, models
from ..auth import authenticate_user, create_access_token, get_current_user
from ..database import get_db
from ..services import email_service

import logging

logger = logging.getLogger(__name__)

# ==============================================================================
# ZH: 建立 Router 實例 | EN: Create Router instance
# ZH: tags 用於 Swagger UI 分類 | EN: tags for Swagger UI categorization
# ==============================================================================
router = APIRouter(tags=["認證 Authentication"])


# ==============================================================================
# ZH: POST /register - 使用者註冊
# EN: POST /register - User registration
# ZH: 流程：驗證資料 → 檢查重複 → 雜湊密碼 → 建立使用者 + Token 額度
# EN: Flow: Validate data → check duplicate → hash password → create user + quota
# ==============================================================================
@router.post("/register", response_model=schemas.UserResponse, status_code=status.HTTP_201_CREATED)
def register(user: schemas.UserCreate, db: Session = Depends(get_db)):
    """
    ZH: 註冊新使用者
    EN: Register a new user

    ZH: 限制：username 和 email 必須唯一
    EN: Constraints: username and email must be unique
    """
    # ZH: 檢查使用者名稱是否已存在 | EN: Check if username exists
    if crud.get_user_by_username(db, username=user.username):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="ZH: 使用者名稱已被註冊 | EN: Username already registered"
        )

    # ZH: 檢查郵件是否已存在 | EN: Check if email exists
    if crud.get_user_by_email(db, email=user.email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="ZH: 電子郵件已被註冊 | EN: Email already registered"
        )

    db_user = crud.create_user(db=db, user=user)
    logger.info(f"ZH: 新使用者註冊成功: {user.username} | EN: New user registered: {user.username}")
    return db_user


# ==============================================================================
# ZH: POST /login - 使用者登入
# EN: POST /login - User login
# ZH: 流程：接收帳密 → 驗證 → 簽發 JWT Token
# EN: Flow: Receive credentials → verify → issue JWT token
# ==============================================================================
@router.post("/login", response_model=schemas.Token)
def login(
    request: Request,
    background_tasks: BackgroundTasks,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    """
    ZH: 使用者登入，回傳 JWT access token
    EN: User login, returns JWT access token

    ZH: 使用 OAuth2 表單格式 (username + password)
    EN: Uses OAuth2 form format (username + password)
    """
    user = authenticate_user(db, form_data.username, form_data.password)
    
    # ZH: 嘗試 SSO 快速驗證 (依據 Mock 配置匹配密碼，若未設密碼預設與學號同) | EN: Try seamless SSO auth
    if not user:
        from ..config import SSO_POLICY
        mock_users = SSO_POLICY.get("mock", {}).get("users", [])
        for sso_user in mock_users:
            sso_id = sso_user.get("student_id")
            sso_pwd = sso_user.get("password", sso_id)
            if sso_id == form_data.username and sso_pwd == form_data.password:
                # 符合列表，擷取或建立此使用者
                user = crud.get_user_by_username(db, username=form_data.username)
                if not user:
                    user = crud.create_sso_user(
                        db,
                        username=sso_id,
                        email=sso_user.get("email"),
                        role=sso_user.get("role", "student")
                    )
                logger.info(f"ZH: SSO 使用者登入成功: {user.username} | EN: SSO User logged in: {user.username}")
                break

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="ZH: 帳號或密碼錯誤 | EN: Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # ZH: 記錄上線狀態 | EN: Record online status
    try:
        user.last_login_time = datetime.utcnow()
        user.last_login_ip = request.client.host if request.client else "Unknown"
        user.online_status = 1
        db.commit()
    except Exception as e:
        logger.error(f"Failed to update login status: {e}")

    # ZH: 發送登入通知 | EN: Send login alert
    if user.email:
        background_tasks.add_task(
            email_service.send_login_alert,
            user.email,
            user.username,
            request.client.host if request.client else "Unknown"
        )

    access_token = create_access_token(
        data={"sub": user.username, "role": user.role}
    )
    logger.info(f"ZH: 使用者登入成功: {user.username} | EN: User logged in: {user.username}")
    return {"access_token": access_token, "token_type": "bearer"}


@router.post("/forgot-password")
def forgot_password(
    payload: schemas.AuthForgotPassword,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """ZH: 忘記密碼 - 產生隨機臨時密碼 | EN: Forgot password - Generate random temp password"""
    user = crud.get_user_by_username(db, payload.username)
    if not user or user.email != payload.email:
        # ZH: 安全考量，無論是否找到，都回傳模糊訊息或直接回報錯誤
        # EN: Security consideration, return vague message or standard error
        raise HTTPException(status_code=400, detail="Invalid username or email")
        
    import secrets
    import string
    import passlib.hash
    
    # 產生 8 碼英數混合密碼
    alphabet = string.ascii_letters + string.digits
    temp_password = ''.join(secrets.choice(alphabet) for i in range(8))
    
    # 更新密碼
    user.hashed_password = passlib.hash.bcrypt.hash(temp_password)
    db.commit()
    
    # ZH: 發送臨時密碼郵件 | EN: Send temp password email
    background_tasks.add_task(
        email_service.send_temp_password,
        user.email,
        user.username,
        temp_password,
        False
    )
    
    logger.info(f"ZH: 忘記密碼重設成功: {user.username} | EN: Password reset successful: {user.username}")
    return {"message": "Password reset successful, temporary password sent to email"}


# ==============================================================================
# ZH: POST /logout - 登出並更新狀態
# EN: POST /logout - Logout and update status
# ==============================================================================
@router.post("/logout")
def logout(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """ZH: 登出 - 將在線狀態設為離線 | EN: Logout - Set online status to offline"""
    try:
        current_user.online_status = 0
        db.commit()
    except Exception as e:
        logger.error(f"Failed to update logout status: {e}")
    return {"message": "Logged out successfully"}

# ==============================================================================
# ZH: GET /me - 取得當前使用者資訊
# EN: GET /me - Get current user info
# ==============================================================================
@router.get("/me", response_model=schemas.UserResponse)
def read_users_me(current_user: models.User = Depends(get_current_user)):
    """
    ZH: 取得已登入使用者的個人資訊
    EN: Get logged-in user's profile info
    """
    return current_user

# ==============================================================================
# ZH: PUT /me - 更新當前使用者資訊
# EN: PUT /me - Update current user info
# ==============================================================================
@router.put("/me", response_model=schemas.UserResponse)
def update_users_me(
    update_data: schemas.UserUpdate,
    background_tasks: BackgroundTasks,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    ZH: 更新已登入使用者的個人資訊 (修改信箱、密碼)
    EN: Update logged-in user's profile info (email, password)
    """
    password_changed = update_data.password is not None and update_data.password != ""
    updated_user = crud.update_user(db, current_user, update_data)
    
    if password_changed and updated_user.email:
        background_tasks.add_task(
            email_service.send_password_change_alert,
            updated_user.email,
            updated_user.username
        )
        
    return updated_user
# ==============================================================================
# ZH: GET /usage - 查詢 Token 用量
# EN: GET /usage - Query token usage
# ZH: 流程：取得使用者 ID → 查詢 token_usage 表 → 計算百分比 → 回傳
# EN: Flow: Get user ID → query token_usage → calculate percentage → return
# ==============================================================================
@router.get("/usage", response_model=schemas.TokenUsageResponse)
def get_token_usage(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    ZH: 查詢當前使用者的 Token 用量與配額
    EN: Query current user's token usage and quota
    """
    usage = crud.get_token_usage(db, user_id=current_user.id)
    if not usage:
        usage = crud.create_token_usage(db, user_id=current_user.id)

    return {
        "user_id": usage.user_id,
        "tokens_used": usage.tokens_used,
        "tokens_limit": usage.tokens_limit,
        "usage_percentage": (usage.tokens_used / usage.tokens_limit) if usage.tokens_limit > 0 else 0,
        "reset_date": usage.reset_date
    }


# ==============================================================================
# ZH: POST /usage/increment - 增加 Token 使用量
# EN: POST /usage/increment - Increment token usage
# ZH: 用途：供 Job Scheduler 或 Portkey Token Tracking 呼叫
# EN: Purpose: Called by Job Scheduler or Portkey Token Tracking
# ==============================================================================
@router.post("/usage/increment")
def increment_token_usage(
    request: schemas.TokenIncrementRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    ZH: 增加使用者 Token 使用量，超過上限回傳 429
    EN: Increment user token usage, returns 429 if limit exceeded
    """
    usage = crud.increment_token_usage(db, user_id=current_user.id, tokens=request.tokens)

    if usage.tokens_used > usage.tokens_limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"ZH: Token 配額已超出。已用: {usage.tokens_used}, 上限: {usage.tokens_limit} | "
                   f"EN: Token quota exceeded. Used: {usage.tokens_used}, Limit: {usage.tokens_limit}"
        )

    return {"status": "success", "tokens_used": usage.tokens_used}
