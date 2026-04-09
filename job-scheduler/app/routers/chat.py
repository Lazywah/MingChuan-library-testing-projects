"""
==============================================================================
Router: 聊天代理路由 (Chat Proxy Router)
==============================================================================
ZH: 用途：處理 AI 聊天請求，扮演代理人 (Proxy) 角色將訊息轉發至 Portkey 或 Ollama
EN: Purpose: Handle AI chat requests, acting as a proxy to forward to Portkey or Ollama

ZH: 功能：
    1. 支援串流輸出 (Streaming Response)
    2. 自動存儲對話紀錄至資料庫 (ChatHistory)
    3. 整合 Token 配額扣除 (即將實作)
EN: Features:
    1. Support streaming response
    2. Auto-save chat history to database
    3. Integrated Token quota deduction (WIP)
==============================================================================
"""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
import httpx
import json
import logging
from datetime import datetime

from .. import crud, schemas, models
from ..auth import get_current_user
from ..database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(tags=["AI 助手 AI Assistant"])

# ZH: 內部服務端點 | EN: Internal service endpoints
PORTKEY_URL = "http://ai-platform-portkey:8000/v1/chat/completions"

@router.post("/completions")
async def chat_completions(
    request: schemas.ChatRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    ZH: AI 聊天及串流代理端點 (方案 B：模擬回音模式)
    EN: AI Chat and Streaming Proxy Endpoint (Option B: Mock Echo Mode)
    """
    
    # ZH: 檢查 Token 額度 | EN: Check token quota upfront
    usage = crud.get_token_usage(db, current_user.id)
    if usage and usage.tokens_used >= usage.tokens_limit:
        async def quota_exceeded():
            yield f"data: {json.dumps({'error': 'Token quota exceeded'}, ensure_ascii=False)}\n\n"
        return StreamingResponse(quota_exceeded(), media_type="text/event-stream")

    async def stream_generator():
        import asyncio
        combined_response = []
        last_message = request.messages[-1].content if request.messages else "沒有訊息"
        
        # ZH: 方案 B：模擬回音模式 | EN: Option B: Mock Echo Mode
        mock_response_text = f"這是模擬 AI 的回應 (Echo Mode)。您剛才說了：\n「{last_message}」\n\n(系統提示：由於目前為 MVP 開發階段，此為模擬訊息。串流對話功能與 Token 實際扣減皆已運作。)"
        
        try:
            # ZH: 模擬串流延遲 | EN: Simulate streaming delay
            chunk_size = 3
            for i in range(0, len(mock_response_text), chunk_size):
                chunk = mock_response_text[i:i+chunk_size]
                combined_response.append(chunk)
                data = {"choices": [{"delta": {"content": chunk}}]}
                yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
                await asyncio.sleep(0.05)
                
            yield "data: [DONE]\n\n"

            # ZH: 結束後存儲紀錄與扣減 Token | EN: Save history and deduct token
            full_text = "".join(combined_response)
            if full_text:
                crud.create_chat_history(db, models.ChatHistory(
                    user_id=current_user.id, session_id="default", role="user", content=last_message
                ))
                crud.create_chat_history(db, models.ChatHistory(
                    user_id=current_user.id, session_id="default", role="assistant", content=full_text
                ))
                
                # 計算 Token: 粗估中英文字數 / 3
                prompt_text = "".join([m.content for m in request.messages])
                estimated_tokens = (len(prompt_text) // 3) + (len(full_text) // 3)
                if estimated_tokens < 1: estimated_tokens = 1
                
                # 扣除額度
                try:
                    crud.increment_token_usage(db, current_user.id, estimated_tokens)
                except HTTPException:
                    pass # 超額時會丟出 429，由於在 generator 中，我們就捕捉忽略
                    
                db.commit()

        except Exception as e:
            logger.error(f"Streaming error: {str(e)}")
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(stream_generator(), media_type="text/event-stream")


@router.get("/history", response_model=list[schemas.ChatMessage])
def get_chat_history(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    ZH: 取得當前使用者的歷史對話
    EN: Get current user's chat history
    """
    histories = db.query(models.ChatHistory).filter(models.ChatHistory.user_id == current_user.id).order_by(models.ChatHistory.created_at.asc()).all()
    return histories
