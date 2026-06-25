"""
==============================================================================
Router: 客服／導覽助手路由 (Support / Guide Assistant Router) — v2.6
==============================================================================
ZH: 用途：右下角浮動「客服小基」的後端。以 RAG（檢索平台 FAQ/說明）+ 本地 Ollama
    生成回覆，引導使用者操作平台、回答常見問題。

    設計取捨：
    - /ask 為「公開」端點（不強制登入、不扣 Token）。理由：客服泡泡在登入頁也要能用，
      新生才能問「怎麼登入」。以 slowapi 限流防濫用。
    - 直接打 Ollama（不經 Portkey），降低相依與失敗點；Ollama 不可達時回明確錯誤。

EN: Purpose: Backend for the bottom-right floating "support assistant". Uses RAG
    (retrieve platform FAQ/docs) + local Ollama to generate replies that guide
    users and answer common questions.

    Trade-offs:
    - /ask is PUBLIC (no login required, no token charge): the bubble must work
      on the login page so new students can ask "how do I log in". Rate-limited
      via slowapi to prevent abuse.
    - Talks to Ollama directly (not Portkey) to reduce coupling/failure points;
      returns a clear error when Ollama is unreachable.
==============================================================================
"""

import json
import logging

import httpx
from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import models
from ..auth import get_current_user
from ..config import settings
from ..database import get_db
from ..rate_limit import limiter
from ..services import rag_service, lab_manager

logger = logging.getLogger(__name__)

router = APIRouter(tags=["客服助手 Support Assistant"])


# ==============================================================================
# ZH: 請求/回應模型 | EN: Request/response schemas
# ==============================================================================

class AssistantMessage(BaseModel):
    role: str
    content: str


class AssistantAskRequest(BaseModel):
    # ZH: 完整對話（最後一則為本次提問）；或只帶 query | EN: full convo (last = question), or just query
    messages: list[AssistantMessage] = Field(default_factory=list)
    query: str | None = None
    session_id: str | None = None
    # ZH: v2.6 模式：guide=平台客服(公開)；code=程式家教(需登入，可附 Lab 檔)
    # EN: v2.6 mode: guide=public support; code=code-tutor (login required, optional lab file)
    mode: str = "guide"
    file_path: str | None = None


def _sse(payload: dict) -> str:
    """ZH: 包成單行 SSE | EN: one SSE data line（與 chat.py 同格式，前端可共用 parser）"""
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _delta(text: str) -> str:
    """ZH: 仿 OpenAI delta，沿用前端既有解析 | EN: OpenAI-style delta for the existing parser"""
    return _sse({"choices": [{"delta": {"content": text}}]})


# ==============================================================================
# ZH: 核心：RAG 問答串流 | EN: Core: RAG Q&A stream
# ==============================================================================

@router.post("/ask")
@limiter.limit("30/minute")
async def ask(
    request: Request,                       # ZH: slowapi 限流需要 | EN: required by slowapi
    body: AssistantAskRequest,
    db: Session = Depends(get_db),
):
    """ZH: 客服問答 SSE 串流 | EN: Support Q&A SSE stream"""

    history = [{"role": m.role, "content": m.content} for m in body.messages]
    # ZH: 取最後一則 user 訊息當檢索 query | EN: last user message is the retrieval query
    query = (body.query or "").strip()
    if not query:
        for m in reversed(history):
            if m["role"] == "user":
                query = m["content"].strip()
                break
    # ZH: 檢索用 query 不重複進歷史 | EN: don't duplicate the query into history
    if history and history[-1]["role"] == "user":
        history = history[:-1]

    async def gen():
        if not query:
            if body.mode == "code":
                yield _delta("嗨，我是程式家教小基 👨‍🏫 你可以貼上程式碼、或附上 Lab 裡的檔，我陪你一起看。")
            else:
                yield _delta("你好，我是平台客服小基 🙂 有什麼平台操作上的問題嗎？")
            yield "data: [DONE]\n\n"
            return

        # ZH: 檢索（兩種模式都用 KB 接地操作類問題）| EN: retrieve (both modes use KB)
        try:
            ranked = await rag_service.retrieve(db, query)
        except Exception as e:  # noqa: BLE001 - 檢索失敗不應讓整個請求 500
            logger.error("RAG retrieve failed: %s", e, exc_info=True)
            ranked = []

        if body.mode == "code":
            # ZH: 程式家教需登入（guide 維持公開）| EN: code-tutor requires login
            # ZH: 自行從 Authorization header 取 bearer（手動呼叫繞過 oauth2_scheme，
            #     _extract_token 只認注入值或 cookie，故 header 要自己拆）
            from fastapi import HTTPException
            _auth = request.headers.get("Authorization", "")
            _bearer = _auth[7:].strip() if _auth[:7].lower() == "bearer " else None
            try:
                user = await get_current_user(request, _bearer, db)
            except HTTPException:
                yield _sse({"error": "程式家教需要先登入才能使用喔，請先登入。"})
                yield "data: [DONE]\n\n"
                return

            # ZH: 讀使用者「手動挑選」的檔；失敗則提示後改一般性回答
            file_excerpt = None
            if body.file_path:
                res = lab_manager.read_user_file(user.id, body.file_path)
                if res.get("ok"):
                    file_excerpt = res
                else:
                    reason_msg = {
                        "lab_not_started": "（讀不到附檔：你的 Lab 尚未啟動，請先到 Notebook 開啟 Lab）",
                        "lab_not_running": "（讀不到附檔：你的 Lab 容器不在執行中，請先啟動）",
                        "not_found": "（讀不到附檔：找不到這個檔案）",
                        "path_forbidden": "（附檔路徑不被允許）",
                    }.get(res.get("reason"), "（讀不到附檔，先就你的問題一般性回答）")
                    yield _delta(reason_msg + "\n\n")

            messages = rag_service.build_code_messages(query, ranked, file_excerpt, history)
        else:
            messages = rag_service.build_messages(query, ranked, history)

        ollama_url = f"{settings.OLLAMA_BASE_URL.rstrip('/')}/v1/chat/completions"
        payload = {"model": settings.RAG_CHAT_MODEL, "messages": messages, "stream": True}

        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(connect=5.0, read=120.0, write=10.0, pool=5.0)
            ) as client:
                async with client.stream("POST", ollama_url, json=payload) as upstream:
                    if upstream.status_code != 200:
                        body_txt = (await upstream.aread()).decode("utf-8", errors="replace")[:200]
                        logger.error("Ollama chat returned %s: %s", upstream.status_code, body_txt)
                        yield _sse({"error": "AI 服務暫時無法使用，請稍後再試或聯絡管理員。"})
                        return

                    async for line in upstream.aiter_lines():
                        if not line or not line.startswith("data: "):
                            continue
                        data_str = line[6:]
                        if data_str == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data_str)
                            content = chunk.get("choices", [{}])[0].get("delta", {}).get("content")
                        except (json.JSONDecodeError, IndexError, KeyError):
                            continue
                        if content:
                            yield _delta(content)
        except httpx.ConnectError:
            logger.error("Cannot connect to Ollama at %s", settings.OLLAMA_BASE_URL)
            yield _sse({"error": "AI 服務尚未啟動，請聯絡管理員。| AI service not available."})
            return
        except httpx.TimeoutException:
            logger.error("Ollama chat timed out")
            yield _sse({"error": "回應逾時，請再試一次。"})
            return
        except Exception as e:  # noqa: BLE001
            logger.error("Assistant stream error: %s", e, exc_info=True)
            yield _sse({"error": "發生內部錯誤，請稍後再試。"})
            return

        # ZH: 附上引用來源（前端可選擇顯示）| EN: attach sources (frontend may show)
        if ranked:
            sources = sorted({r["chunk"].source for r in ranked})
            yield _sse({"sources": sources})
        yield "data: [DONE]\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")


# ==============================================================================
# ZH: 狀態查詢（公開）| EN: Status (public)
# ==============================================================================

@router.get("/status")
def status(db: Session = Depends(get_db)):
    """ZH: 回傳知識庫片段數與模型設定 | EN: KB chunk count + model config"""
    count = db.query(models.KnowledgeChunk).count()
    return {
        "ready": count > 0,
        "chunks": count,
        "embed_model": settings.RAG_EMBED_MODEL,
        "chat_model": settings.RAG_CHAT_MODEL,
    }


# ==============================================================================
# ZH: v2.6 程式家教 — 列出使用者自己的 Lab 檔（給前端附檔挑選器，需登入）
# EN: v2.6 code-tutor — list the user's OWN lab files (file picker, login required)
# ==============================================================================

@router.get("/lab-files")
def lab_files(current_user: models.User = Depends(get_current_user)):
    """ZH: 回傳使用者 cs-<uid> 容器內 /home/coder 下可挑選的檔（相對路徑）。
       EN: List selectable files under /home/coder in the user's own container."""
    return lab_manager.list_user_files(current_user.id)


# ==============================================================================
# ZH: 重建知識庫（admin）| EN: Reindex knowledge base (admin)
# ==============================================================================

@router.post("/reindex")
async def reindex(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """ZH: 重新讀取 knowledge/*.md 並重建向量（僅 admin）| EN: Rebuild KB from knowledge/*.md (admin only)"""
    if current_user.role != "admin":
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Forbidden: Admins only")
    result = await rag_service.ingest_knowledge_base(db, force=True)
    return result
