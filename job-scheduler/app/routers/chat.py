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
    ZH: AI 聊天及串流代理端點
    EN: AI Chat and Streaming Proxy Endpoint
    """
    
    # ZH: 準備轉發給下層服務的資料 | EN: Prepare data for downstream service
    # ZH: 注意：此處我們可以根據 model_id 調整 Portkey 的 Headers (例如切換 Provider)
    # EN: Note: We can adjust Portkey headers based on model_id here
    headers = {
        "x-portkey-provider": "openai", # ZH: 預設使用 OpenAI 格式代理 | EN: Default OpenAI format
        "Content-Type": "application/json"
    }
    
    # ZH: 實例映射 (簡化版) | EN: Simplified mapping
    payload = {
        "model": request.model_id,
        "messages": [{"role": m.role, "content": m.content} for m in request.messages],
        "stream": request.stream
    }

    async def stream_generator():
        combined_response = []
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                async with client.stream("POST", PORTKEY_URL, json=payload, headers=headers) as response:
                    if response.status_code != 200:
                        error_detail = await response.aread()
                        logger.error(f"LLM Provider error: {error_detail}")
                        yield f"data: {json.dumps({'error': 'Upstream Error'})}\n\n"
                        return

                    async for line in response.aiter_lines():
                        if not line:
                            continue
                        
                        # ZH: 轉發串流內容 | EN: Forward stream content
                        yield f"{line}\n\n"
                        
                        # ZH: 解析內容以供稍後存入資料庫 | EN: Parse content for DB storage
                        if line.startswith("data: "):
                            content = line[6:].strip()
                            if content == "[DONE]":
                                break
                            try:
                                data = json.loads(content)
                                delta = data['choices'][0]['delta'].get('content', '')
                                combined_response.append(delta)
                            except:
                                pass

            # ZH: 結束後異步存儲紀錄 | EN: Async save history after finishing
            # ZH: 注意：生產環境建議建立真正的 session_id 追蹤
            full_text = "".join(combined_response)
            if full_text:
                # 儲存使用者問題 (最後一筆)
                crud.create_chat_history(db, models.ChatHistory(
                    user_id=current_user.id,
                    session_id="default",
                    role="user",
                    content=request.messages[-1].content
                ))
                # 儲存 AI 回覆
                crud.create_chat_history(db, models.ChatHistory(
                    user_id=current_user.id,
                    session_id="default",
                    role="assistant",
                    content=full_text
                ))
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
