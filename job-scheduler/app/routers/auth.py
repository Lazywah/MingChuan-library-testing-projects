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
from datetime import datetime, timezone

import hmac as _hmac

from .. import crud, schemas, models
from ..auth import authenticate_user, create_access_token, get_current_user, require_role
from ..database import get_db
from ..services import email_service
from ..rate_limit import limiter

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
@limiter.limit("5/minute")  # C-1: ZH: 防止暴力大量建號 | EN: Prevent mass account creation
async def register(request: Request, user: schemas.UserCreate, db: Session = Depends(get_db)):
    """
    ZH: 註冊新使用者
    EN: Register a new user

    ZH: 限制：username 和 email 必須唯一；角色限定 student
    EN: Constraints: username and email must be unique; role forced to student
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
@limiter.limit("10/minute")
async def login(
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
            # H-3: ZH: 使用 hmac.compare_digest 防計時攻擊 | EN: Use constant-time compare to prevent timing attacks
            if sso_id == form_data.username and _hmac.compare_digest(sso_pwd, form_data.password):
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

    # ZH: 記錄上線狀態與次數 | EN: Record online status and login count
    try:
        user.last_login_time = datetime.now(timezone.utc)
        user.last_login_ip = request.client.host if request.client else "Unknown"
        user.online_status = 1
        user.login_count += 1
        db.commit()
    except Exception as e:
        logger.error(f"Failed to update login status: {e}")

    # ZH: 寫入實體登入紀錄檔 (排除測試帳號) | EN: Write to physical login log (exclude test accounts)
    if not getattr(user, 'is_test_account', 0):
        try:
            from ..config import settings
            import os
            
            log_dir = os.path.dirname(settings.DATABASE_PATH)
            if not os.path.exists(log_dir):
                os.makedirs(log_dir, exist_ok=True)
                
            log_path = os.path.join(log_dir, "login.log")
            timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
            ip_addr = request.client.host if request.client else "Unknown"
            
            with open(log_path, "a", encoding="utf-8") as f:
                # H-2: ZH: 不記錄 Email，避免個資洩漏 | EN: Omit email to avoid PII exposure
                f.write(f"[{timestamp}] User '{user.username}' (Role: {user.role}) logged in from IP: {ip_addr}\n")
        except Exception as e:
            logger.error(f"Failed to write login log: {e}")

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
@limiter.limit("3/hour")  # C-2: ZH: 防郵件炸彈 | EN: Prevent email-bombing via reset requests
async def forgot_password(
    request: Request,
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
    from ..config import settings as _settings

    # 產生 8 碼英數混合密碼
    alphabet = string.ascii_letters + string.digits
    temp_password = ''.join(secrets.choice(alphabet) for i in range(8))

    # 更新密碼
    user.hashed_password = passlib.hash.bcrypt.hash(temp_password)
    db.commit()

    # C-11: ZH: 有設定 SMTP 則寄信，否則將臨時密碼回傳 (避免密碼消失無法取得)
    # EN: Send email when SMTP is configured; otherwise return temp password in response
    email_sent = bool(_settings.SMTP_SERVER)
    if email_sent:
        background_tasks.add_task(
            email_service.send_temp_password,
            user.email,
            user.username,
            temp_password,
            False
        )

    logger.info(f"ZH: 忘記密碼重設成功: {user.username} | EN: Password reset successful: {user.username}")
    return {
        "message": "Password reset successful",
        "temp_password": None if email_sent else temp_password,
        "email_sent": email_sent,
    }


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
# ZH: 用途：供 Job Scheduler 或 Portkey Token Tracking 呼叫（限 admin 角色）
# EN: Purpose: Called by Job Scheduler or Portkey (admin role required)
# ==============================================================================
@router.post("/usage/increment")
def increment_token_usage(
    request: schemas.TokenIncrementRequest,
    # C-3: ZH: 限制為 admin 角色，防止一般使用者自行操控 Token 計數
    # EN: Restrict to admin role — prevents students from self-manipulating counters
    current_user: models.User = Depends(require_role("admin")),
    db: Session = Depends(get_db)
):
    """
    ZH: 扣減指定使用者 Token 配額（原子 UPDATE），超額回傳 429
    EN: Atomically deduct token quota; returns 429 if limit exceeded

    ZH: C2 修復：扣減目標為 request.user_id（先前誤扣 current_user/admin 自己）
    EN: C2 fix: deducts from request.user_id (previously deducted from current_user/admin)
    """
    # ZH: 驗證目標使用者存在 | EN: Verify target user exists
    target_user = crud.get_user_by_id(db, user_id=request.user_id)
    if not target_user:
        raise HTTPException(status_code=404, detail="Target user not found")

    # C-3: ZH: 改用原子扣減，防止超額後仍計入 | EN: Atomic deduct — never over-credits then checks
    success = crud.try_deduct_tokens(db, user_id=request.user_id, tokens=request.tokens)
    if not success:
        usage = crud.get_token_usage(db, user_id=request.user_id)
        remaining = (usage.tokens_limit - usage.tokens_used) if usage else 0
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"ZH: Token 配額不足。剩餘: {remaining}, 需要: {request.tokens} | "
                   f"EN: Insufficient quota. Remaining: {remaining}, Required: {request.tokens}"
        )
    usage = crud.get_token_usage(db, user_id=request.user_id)
    return {
        "status": "success",
        "user_id": request.user_id,
        "tokens_used": usage.tokens_used if usage else 0,
    }
