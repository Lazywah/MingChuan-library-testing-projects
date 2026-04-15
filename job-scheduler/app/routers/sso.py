import os
from fastapi import APIRouter, Depends, Query, Request, HTTPException, Form
from fastapi.responses import RedirectResponse, HTMLResponse
from sqlalchemy.orm import Session
from ..database import get_db
from ..crud import get_user_by_username, create_sso_user
from ..auth import create_access_token
from ..config import SSO_POLICY
from ..sso_client import get_sso_client

router = APIRouter()

# 初始化 SSO Client
mock_mode = SSO_POLICY.get("mock_mode", True)
sso_client = get_sso_client(mock_mode=mock_mode, config=SSO_POLICY)

@router.get("/login", summary="SSO 登入導向")
def sso_login():
    """導向至指定的 SSO 登入頁面 (CAS 或 Mock)"""
    url = sso_client.get_login_url()
    return RedirectResponse(url=url)

@router.get("/callback", summary="SSO 登入回呼網址")
def sso_callback(ticket: str = Query(..., description="CAS Server 或 Mock 傳回的 ticket"), db: Session = Depends(get_db)):
    """處理 SSO 驗證結果並產生系統的 JWT Token"""
    try:
        # 向 SSO Client 驗證 Ticket 以取得使用者資訊
        user_info = sso_client.validate_ticket(ticket)
        username = user_info.get("username")
        email = user_info.get("email")
        role = user_info.get("role", "student")

        if not username:
            raise HTTPException(status_code=400, detail="SSO 回傳的資訊不包含 username")

        # 確認此 SSO 使用者是否已存在於系統中
        user = get_user_by_username(db, username)
        if not user:
            # 首次登入，自動建立帳號並給予預設 Token 額度
            user = create_sso_user(db, username=username, email=email, role=role)

        # 產生 JWT Token 供前端使用
        access_token = create_access_token(
            data={"sub": user.username, "role": user.role}
        )

        # 導回前端並帶上 Token (前端 app.js 需解析 URL Token 並存入 localStorage)
        redirect_url = f"/?sso_token={access_token}"
        return RedirectResponse(url=redirect_url)

    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/mock-login", response_class=HTMLResponse, summary="模擬 SSO 登入畫面")
def mock_sso_login_page():
    """如果處於 Mock 模式，這會提供一個簡單的 HTML 表單，代表外部 SSO 的輸入畫面"""
    if not mock_mode:
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
    """收到模擬表單的 Ticket 後，將其透過 Callback 路由直接導回系統"""
    if not mock_mode:
        raise HTTPException(status_code=404, detail="Mock SSO is disabled")
    return RedirectResponse(url=f"/api/v1/sso/callback?ticket={ticket}", status_code=303)
