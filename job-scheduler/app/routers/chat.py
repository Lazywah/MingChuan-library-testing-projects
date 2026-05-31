"""
==============================================================================
Router: 聊天代理路由 (Chat Proxy Router)
==============================================================================
ZH: 用途：處理 AI 聊天請求，代理轉發至 Portkey LLM Gateway
EN: Purpose: Handle AI chat requests, proxying to Portkey LLM Gateway

ZH: 功能：
    1. 串流 SSE 代理至 Portkey (支援 Anthropic / OpenAI / Google / Ollama)
    2. 自動存儲對話紀錄 (含正確的 session_id)
    3. Token 配額扣除 (優先使用上游回傳的實際用量)
    4. Portkey 不可達時回傳明確錯誤訊息
EN: Features:
    1. SSE proxy to Portkey (supports Anthropic/OpenAI/Google/Ollama)
    2. Auto-save chat history (with correct session_id)
    3. Token quota deduction (uses upstream actual usage if available)
    4. Returns clear error when Portkey is unreachable
==============================================================================
"""

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import update as _sa_update
import httpx
import json
import logging
import uuid

from .. import crud, schemas, models
from ..auth import get_current_user
from ..database import get_db
from ..config import settings
from ..services import agent_dispatcher, document_generator

logger = logging.getLogger(__name__)

router = APIRouter(tags=["AI 助手 AI Assistant"])

# ZH: 模型名稱前綴 → Portkey Provider 對應表
# EN: Model name prefix → Portkey provider mapping
_PROVIDER_MAP = {
    "claude": "anthropic",
    "gpt": "openai",
    "o1": "openai",
    "o3": "openai",
    "gemini": "google",
    "llama": "ollama",
    "mistral": "ollama",
    "qwen": "ollama",
}

def _get_portkey_headers(model_id: str) -> dict:
    """ZH: 依模型名稱決定 Portkey provider | EN: Determine Portkey provider from model name"""
    model_lower = model_id.lower()
    headers = {"Content-Type": "application/json"}
    for prefix, provider in _PROVIDER_MAP.items():
        if prefix in model_lower:
            headers["x-portkey-provider"] = provider
            break
    return headers


@router.post("/completions")
async def chat_completions(
    request: schemas.ChatRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """ZH: AI 聊天串流代理 | EN: AI Chat SSE proxy"""

    # ZH: 配額前置檢查 | EN: Upfront quota check
    usage = crud.get_token_usage(db, current_user.id)
    if usage and usage.tokens_used >= usage.tokens_limit:
        async def quota_exceeded():
            yield f"data: {json.dumps({'error': 'Token quota exceeded'}, ensure_ascii=False)}\n\n"
        return StreamingResponse(quota_exceeded(), media_type="text/event-stream")

    # ZH: v2.3 P1 — 專項生成 agent（文書簡報等）走獨立 dispatch 流程，
    #     不影響既有純 chat 行為（tool_type 為空/"chat" 時走下方原邏輯）
    # EN: v2.3 P1 — specialized generation agents use an isolated dispatch path;
    #     existing plain chat behaviour is untouched (empty/"chat" → original below)
    if agent_dispatcher.is_dispatch_tool(request.tool_type):
        return StreamingResponse(
            _dispatch_stream_generator(request, current_user.id, db),
            media_type="text/event-stream",
        )

    # ZH: 使用請求傳入的 session_id；若未傳入則產生新 UUID
    # EN: Use session_id from request; generate new UUID if not provided
    session_id = (request.session_id or "").strip() or str(uuid.uuid4())
    last_message = request.messages[-1].content if request.messages else ""

    portkey_payload = {
        "model": request.model_id,
        "messages": [{"role": m.role, "content": m.content} for m in request.messages],
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    portkey_headers = _get_portkey_headers(request.model_id)

    async def stream_generator():
        combined_response: list[str] = []
        total_tokens = 0

        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(connect=5.0, read=120.0, write=10.0, pool=5.0)) as client:
                async with client.stream(
                    "POST",
                    settings.PORTKEY_URL,
                    json=portkey_payload,
                    headers=portkey_headers,
                ) as upstream:
                    if upstream.status_code != 200:
                        body = await upstream.aread()
                        err_msg = body.decode("utf-8", errors="replace")[:200]
                        logger.error(f"Portkey returned {upstream.status_code}: {err_msg}")
                        yield f"data: {json.dumps({'error': f'AI service error ({upstream.status_code})'})}\n\n"
                        return

                    async for line in upstream.aiter_lines():
                        if not line:
                            continue
                        if not line.startswith("data: "):
                            continue

                        data_str = line[6:]
                        if data_str == "[DONE]":
                            yield "data: [DONE]\n\n"
                            break

                        try:
                            chunk = json.loads(data_str)
                            # ZH: 提取內容片段 | EN: Extract content delta
                            delta = chunk.get("choices", [{}])[0].get("delta", {})
                            if content := delta.get("content"):
                                combined_response.append(content)
                            # ZH: 提取實際 Token 用量 | EN: Extract actual token usage
                            if chunk_usage := chunk.get("usage"):
                                total_tokens = chunk_usage.get("total_tokens", 0)
                        except (json.JSONDecodeError, IndexError, KeyError):
                            pass

                        yield f"{line}\n\n"

        except httpx.ConnectError:
            logger.error(f"Cannot connect to Portkey at {settings.PORTKEY_URL}. Is docker-compose.ai-models.yml running?")
            yield (
                f"data: {json.dumps({'error': 'AI 服務尚未啟動，請聯絡管理員 | AI service not available. Run: docker compose -f docker-compose.ai-models.yml up -d'}, ensure_ascii=False)}\n\n"
            )
            return
        except httpx.TimeoutException:
            logger.error("Portkey request timed out")
            yield f"data: {json.dumps({'error': 'AI service timed out, please try again'})}\n\n"
            return
        except Exception as e:
            logger.error(f"Streaming error: {e}", exc_info=True)
            yield f"data: {json.dumps({'error': 'Internal streaming error'})}\n\n"
            return

        # ZH: 儲存對話紀錄並扣減 Token | EN: Save history and deduct tokens
        full_text = "".join(combined_response)
        if not full_text:
            return
        try:
            # ZH: 優先使用上游回傳的精確用量，備用字數/3 粗估
            # EN: Prefer upstream actual usage; fallback to char/3 estimate
            prompt_text = "".join(m.content for m in request.messages)
            estimated = total_tokens or max(1, (len(prompt_text) + len(full_text)) // 3)

            # H-8: ZH: 先算 estimated 再寫入，讓 assistant 行帶上本次往返真實 Token 消耗
            # EN: Compute estimated first so the assistant row carries actual round-trip cost
            db.add(models.ChatHistory(
                user_id=current_user.id, session_id=session_id,
                role="user", content=last_message,
                tool_type=request.tool_type or "chat",
                tokens_used=0,          # ZH: prompt 成本計入下方 assistant 行 | EN: prompt cost counted in assistant row
            ))
            db.add(models.ChatHistory(
                user_id=current_user.id, session_id=session_id,
                role="assistant", content=full_text,
                tool_type=request.tool_type or "chat",
                tokens_used=estimated,  # H-8: ZH: 本次完整往返的 Token 消耗 | EN: total round-trip token cost
            ))

            # ZH: 以 SQL UPDATE 直接做加法，避免 read-modify-write 競爭條件
            # EN: Use SQL UPDATE for arithmetic to avoid read-modify-write race
            db.execute(
                _sa_update(models.TokenUsage)
                .where(models.TokenUsage.user_id == current_user.id)
                .values(tokens_used=models.TokenUsage.tokens_used + estimated)
                .execution_options(synchronize_session=False)
            )
            db.execute(
                _sa_update(models.User)
                .where(models.User.id == current_user.id)
                .values(lifetime_tokens_used=models.User.lifetime_tokens_used + estimated)
                .execution_options(synchronize_session=False)
            )
            db.commit()
        except Exception as e:
            logger.error(f"Failed to save chat history: {e}", exc_info=True)
            db.rollback()

    return StreamingResponse(stream_generator(), media_type="text/event-stream")


# ==============================================================================
# ZH: v2.3 P1 — 專項生成 agent dispatch 串流（文書簡報）
# EN: v2.3 P1 — specialized generation agent dispatch stream (presentation)
# ==============================================================================

def _sse(payload: dict) -> str:
    """ZH: 包成單行 SSE data 事件 | EN: Wrap into one SSE data line"""
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _content_event(text: str) -> str:
    """ZH: 仿 OpenAI delta 格式，讓前端既有 parser 直接吃 | EN: OpenAI-style delta"""
    return _sse({"choices": [{"delta": {"content": text}}]})


def _extract_spec_json(block: str) -> str:
    """ZH: 容錯地把標記區塊內的 JSON 取出（去掉可能的 ``` 圍欄）
       EN: Tolerantly extract JSON from the marker block (strip code fences)"""
    s = block.strip()
    if s.startswith("```"):
        # 去掉第一行 ```/```json 與結尾 ```
        s = s.split("\n", 1)[1] if "\n" in s else s
        if s.rstrip().endswith("```"):
            s = s.rstrip()[:-3]
    return s.strip()


async def _dispatch_stream_generator(
    request: schemas.ChatRequest,
    user_id: str,
    db: Session,
):
    """
    ZH: 專項 agent 串流：注入 system prompt → 串流 → 偵測生成契約 →
        擷取 spec → document_generator 渲染 → 回傳生成結果事件。
        對使用者隱藏原始 JSON（偵測到 START 標記後停止外送內容）。
    EN: Specialized agent stream: inject system prompt → stream → detect the
        generation contract → extract spec → render → emit result event.
        Raw JSON is hidden from the user (stop forwarding once START is seen).
    """
    cfg = agent_dispatcher.get_agent_config(request.tool_type)
    start_marker = cfg["spec_start"]
    end_marker = cfg["spec_end"]
    system_prompt = cfg["system_prompt"]

    session_id = (request.session_id or "").strip() or str(uuid.uuid4())
    last_message = request.messages[-1].content if request.messages else ""

    # ZH: system prompt 置頂；其餘維持使用者對話 | EN: prepend system prompt
    out_messages = [{"role": "system", "content": system_prompt}]
    out_messages += [{"role": m.role, "content": m.content} for m in request.messages]

    portkey_payload = {
        "model": request.model_id,
        "messages": out_messages,
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    portkey_headers = _get_portkey_headers(request.model_id)

    full = ""              # ZH: AI 完整輸出（含標記）| EN: full AI output (with markers)
    emitted = 0            # ZH: 已外送字元數 | EN: chars already forwarded
    spec_mode = False      # ZH: 已進入 spec 區塊 | EN: inside spec block
    start_idx = -1
    total_tokens = 0
    hold = len(start_marker)

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(connect=5.0, read=120.0, write=10.0, pool=5.0)) as client:
            async with client.stream(
                "POST", settings.PORTKEY_URL, json=portkey_payload, headers=portkey_headers,
            ) as upstream:
                if upstream.status_code != 200:
                    body = await upstream.aread()
                    err_msg = body.decode("utf-8", errors="replace")[:200]
                    logger.error(f"Portkey returned {upstream.status_code}: {err_msg}")
                    yield _sse({"error": f"AI service error ({upstream.status_code})"})
                    return

                async for line in upstream.aiter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    data_str = line[6:]
                    if data_str == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data_str)
                        delta = chunk.get("choices", [{}])[0].get("delta", {})
                        content = delta.get("content")
                        if chunk_usage := chunk.get("usage"):
                            total_tokens = chunk_usage.get("total_tokens", 0)
                    except (json.JSONDecodeError, IndexError, KeyError):
                        continue
                    if not content:
                        continue

                    full += content
                    if not spec_mode:
                        idx = full.find(start_marker)
                        if idx != -1:
                            # ZH: 標記出現 → 外送標記前的人類文字，之後全部隱藏
                            if idx > emitted:
                                yield _content_event(full[emitted:idx])
                                emitted = idx
                            spec_mode = True
                            start_idx = idx
                        else:
                            # ZH: 保留尾端 hold 字元，避免把跨 chunk 的標記切一半送出
                            safe = max(emitted, len(full) - hold)
                            if safe > emitted:
                                yield _content_event(full[emitted:safe])
                                emitted = safe
                    # spec_mode → 不外送
    except httpx.ConnectError:
        logger.error(f"Cannot connect to Portkey at {settings.PORTKEY_URL}")
        yield _sse({"error": "AI 服務尚未啟動，請聯絡管理員 | AI service not available."})
        return
    except httpx.TimeoutException:
        logger.error("Portkey request timed out (dispatch)")
        yield _sse({"error": "AI service timed out, please try again"})
        return
    except Exception as e:
        logger.error(f"Dispatch streaming error: {e}", exc_info=True)
        yield _sse({"error": "Internal streaming error"})
        return

    # ZH: 收尾 — 決定 assistant 存檔內容、必要時觸發生成
    # EN: Finalize — decide saved assistant text, trigger generation if needed
    if not spec_mode:
        if len(full) > emitted:
            yield _content_event(full[emitted:])
        assistant_text = full
    else:
        # ZH: 擷取 START..END 間 JSON | EN: extract JSON between START..END
        json_start = start_idx + len(start_marker)
        end_pos = full.find(end_marker, json_start)
        raw_block = full[json_start:end_pos] if end_pos != -1 else full[json_start:]
        assistant_text = full[:start_idx].strip() or "好的，正在為你生成簡報。"

        result = None
        try:
            spec = json.loads(_extract_spec_json(raw_block))
            result = document_generator.generate_presentation(spec, user_id)
        except json.JSONDecodeError as e:
            logger.warning("Presentation spec JSON parse failed: %s", e)
            result = {"ok": False, "error": "AI 產生的簡報結構無法解析，請再說一次「請生成」。"
                                            " | Could not parse the generated spec; please reconfirm."}

        yield _sse({"pptx_generated": result})

    yield "data: [DONE]\n\n"

    # ZH: 存對話紀錄 + 扣 token（與 /completions 同邏輯）
    # EN: Save history + deduct tokens (same logic as /completions)
    if not assistant_text:
        return
    try:
        prompt_text = "".join(m.content for m in request.messages)
        estimated = total_tokens or max(1, (len(prompt_text) + len(full)) // 3)
        db.add(models.ChatHistory(
            user_id=user_id, session_id=session_id,
            role="user", content=last_message,
            tool_type=request.tool_type or "presentation", tokens_used=0,
        ))
        db.add(models.ChatHistory(
            user_id=user_id, session_id=session_id,
            role="assistant", content=assistant_text,
            tool_type=request.tool_type or "presentation", tokens_used=estimated,
        ))
        db.execute(
            _sa_update(models.TokenUsage)
            .where(models.TokenUsage.user_id == user_id)
            .values(tokens_used=models.TokenUsage.tokens_used + estimated)
            .execution_options(synchronize_session=False)
        )
        db.execute(
            _sa_update(models.User)
            .where(models.User.id == user_id)
            .values(lifetime_tokens_used=models.User.lifetime_tokens_used + estimated)
            .execution_options(synchronize_session=False)
        )
        db.commit()
    except Exception as e:
        logger.error(f"Failed to save dispatch chat history: {e}", exc_info=True)
        db.rollback()


@router.get("/history")
def get_chat_history(
    session_id: str = None,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """ZH: 取得當前使用者的歷史對話 | EN: Get current user's chat history"""
    query = db.query(models.ChatHistory).filter(
        models.ChatHistory.user_id == current_user.id
    )
    if session_id:
        query = query.filter(models.ChatHistory.session_id == session_id)
    histories = query.order_by(models.ChatHistory.created_at.asc()).all()
    return [{"role": h.role, "content": h.content} for h in histories]


@router.get("/sessions")
def get_chat_sessions(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """ZH: 取得使用者的所有對話 session 清單 | EN: List all chat sessions for current user"""
    from sqlalchemy import distinct
    sessions = (
        db.query(models.ChatHistory.session_id)
        .filter(models.ChatHistory.user_id == current_user.id)
        .distinct()
        .all()
    )
    return [s[0] for s in sessions]
