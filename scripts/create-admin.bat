@echo off
chcp 65001 >nul
setlocal
REM ============================================================================
REM  建立 / 重設「管理員帳號」 (Windows .bat)
REM  用途：全新部署後，平台沒有任何 admin，用本腳本建立第一個管理員帳號。
REM       已存在同名帳號時 → 改成 admin 角色並重設密碼（upsert）。
REM  前提：核心 stack 已啟動（docker compose up -d，容器 ai-platform-scheduler 在跑）。
REM  注意：密碼直接寫在下方，請保管好本檔，登入後立即於平台改密碼。
REM ============================================================================

REM ===== 可自行修改 =====================================================
set "ADMIN_USER=admin"
set "ADMIN_EMAIL=admin@mcu.local"
set "ADMIN_PW=admin"
set "CONTAINER=ai-platform-scheduler"
REM   ↑ 密碼建議避開 cmd 特殊字元 ! %% ^ ^& ^< ^> ^|（用 - _ @ . 等即可）
REM =====================================================================

echo.
echo [create-admin] 檢查容器 %CONTAINER% 是否在執行 ...
docker ps --format "{{.Names}}" | findstr /x "%CONTAINER%" >nul
if errorlevel 1 (
  echo [錯誤] 容器 "%CONTAINER%" 沒在執行。
  echo        請先在專案根目錄啟動核心服務： docker compose up -d
  echo.
  if /i not "%~1"=="auto" pause
  exit /b 1
)

echo [create-admin] 建立 / 重設管理員「%ADMIN_USER%」 ...
echo        ^(過程若出現 bcrypt "__about__" 警告屬版本相容訊息，可忽略；看到下方「[完成]」即成功^)
docker exec -e ADMIN_USER=%ADMIN_USER% -e ADMIN_EMAIL=%ADMIN_EMAIL% -e ADMIN_PW=%ADMIN_PW% %CONTAINER% python -c "import os; from app.database import SessionLocal; from app import models as m, crud as c; from app.config import settings as s; db=SessionLocal(); U=os.environ['ADMIN_USER']; P=os.environ['ADMIN_PW']; E=os.environ.get('ADMIN_EMAIL','admin@local'); u=c.get_user_by_username(db,U) or m.User(username=U,email=E,role='admin',is_active=1); new=(u.id is None); u.hashed_password=c.get_password_hash(P); u.role='admin'; u.is_active=1; db.add(u); db.commit(); db.refresh(u); (db.query(m.TokenUsage).filter(m.TokenUsage.user_id==u.id).first() or (db.add(m.TokenUsage(user_id=u.id,tokens_used=0,tokens_limit=s.DEFAULT_MONTHLY_TOKEN_LIMIT,reset_date=c._calculate_next_reset_date())), db.commit())); print('CREATED' if new else 'UPDATED', 'admin:', U)"

if errorlevel 1 (
  echo.
  echo [錯誤] 建立失敗，請看上面的 Python 錯誤訊息。
  echo        常見原因：scheduler 尚未就緒（稍候重試）、或 .env 機密未設定導致容器起不來。
  echo.
  if /i not "%~1"=="auto" pause
  exit /b 1
)

echo.
echo ============================================================
echo  [完成] 管理員帳號已就緒
echo     帳號 (username): %ADMIN_USER%
echo     密碼 (password): %ADMIN_PW%
echo     管理員入口      : http://localhost:8888/
echo  ^>^> 請登入後「立即」於平台修改密碼，並妥善保管本檔。
echo ============================================================
echo.
endlocal
if /i not "%~1"=="auto" pause
