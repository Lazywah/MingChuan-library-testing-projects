"""
ZH: 聊天模組整合測試 (使用 httpx MockTransport，不需要真實 Portkey / AI API)
EN: Chat module integration tests using httpx MockTransport — no real Portkey/AI API needed

ZH: 覆蓋場景：
    - POST /chat/completions 正常 SSE 串流
    - Token 配額超限時回傳錯誤 SSE
    - Portkey 連線失敗時回傳友善錯誤
    - GET /chat/history 取得歷史
    - GET /chat/sessions 取得 session 清單
    - 使用者只能看到自己的歷史
EN: Covered scenarios:
    - POST /chat/completions normal SSE stream
    - Token quota exceeded returns error SSE
    - Portkey unreachable returns friendly error
    - GET /chat/history retrieves history
    - GET /chat/sessions lists sessions
    - Users can only see their own history
"""
import pytest
import json
from unittest.mock import patch, AsyncMock, MagicMock
from conftest import make_user, auth_headers


# ══════════════════════════════════════════════════════════════════
# ZH: 輔助函式 | EN: Helper utilities
# ══════════════════════════════════════════════════════════════════

def _make_sse_lines(*contents, include_usage: bool = True) -> list[str]:
    """
    ZH: 產生符合 OpenAI SSE 格式的假回應行
    EN: Generate fake OpenAI-compatible SSE response lines
    """
    lines = []
    for content in contents:
        chunk = {
            "choices": [{"delta": {"content": content}}],
        }
        lines.append(f"data: {json.dumps(chunk)}")
    if include_usage:
        usage_chunk = {"usage": {"total_tokens": 42}, "choices": [{"delta": {}}]}
        lines.append(f"data: {json.dumps(usage_chunk)}")
    lines.append("data: [DONE]")
    return lines


def _setup_user_with_quota(db, username="chatuser", quota=5_000_000):
    """ZH: 建立測試使用者並設定 Token 配額 | EN: Create test user with token quota"""
    from app import crud, models
    user = make_user(db, username=username, email=f"{username}@example.com")
    usage = db.query(models.TokenUsage).filter(models.TokenUsage.user_id == user.id).first()
    if usage:
        usage.tokens_limit = quota
        usage.tokens_used = 0
    db.commit()
    return user


def _post_chat(client, headers, model_id="claude-opus-4", messages=None, session_id=None):
    """ZH: 呼叫 POST /api/v1/chat/completions | EN: Call POST /api/v1/chat/completions"""
    payload = {
        "model_id": model_id,
        "messages": messages or [{"role": "user", "content": "Hello"}],
    }
    if session_id:
        payload["session_id"] = session_id
    return client.post("/api/v1/chat/completions", json=payload, headers=headers)


# ══════════════════════════════════════════════════════════════════
# ZH: 正常 SSE 串流測試
# EN: Normal SSE streaming tests
# ══════════════════════════════════════════════════════════════════

class TestChatCompletionsStream:
    def test_stream_returns_200_and_sse_content(self, client, db):
        """ZH: 正常流程：回傳 200 且含 SSE 內容 | EN: Happy path: 200 with SSE content"""
        _setup_user_with_quota(db)
        headers = auth_headers(client, "chatuser")

        sse_lines = _make_sse_lines("Hello", " world")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.aiter_lines = AsyncMock(return_value=iter(sse_lines))

        async def fake_stream(*args, **kwargs):
            class FakeCtx:
                status_code = 200
                async def __aenter__(self_inner):
                    return self_inner
                async def __aexit__(self_inner, *a):
                    pass
                async def aiter_lines(self_inner):
                    for line in sse_lines:
                        yield line
            return FakeCtx()

        with patch("app.routers.chat.httpx.AsyncClient") as mock_client_cls:
            mock_instance = MagicMock()
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=False)

            class FakeStreamCtx:
                status_code = 200
                async def __aenter__(self_inner):
                    return self_inner
                async def __aexit__(self_inner, *a):
                    pass
                async def aiter_lines(self_inner):
                    for line in sse_lines:
                        yield line
                async def aread(self_inner):
                    return b""

            mock_instance.stream = MagicMock(return_value=FakeStreamCtx())
            mock_client_cls.return_value = mock_instance

            resp = _post_chat(client, headers)

        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers.get("content-type", "")
        body = resp.text
        assert "data:" in body

    def test_stream_saves_chat_history(self, client, db):
        """ZH: 串流完成後應儲存 user + assistant 對話紀錄 | EN: History saved after stream"""
        from app import models as m
        _setup_user_with_quota(db)
        headers = auth_headers(client, "chatuser")
        sse_lines = _make_sse_lines("Hi there!")
        session = "test-session-001"

        with patch("app.routers.chat.httpx.AsyncClient") as mock_client_cls:
            mock_instance = MagicMock()
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=False)

            class FakeStreamCtx:
                status_code = 200
                async def __aenter__(self_inner):
                    return self_inner
                async def __aexit__(self_inner, *a):
                    pass
                async def aiter_lines(self_inner):
                    for line in sse_lines:
                        yield line
                async def aread(self_inner):
                    return b""

            mock_instance.stream = MagicMock(return_value=FakeStreamCtx())
            mock_client_cls.return_value = mock_instance

            _post_chat(client, headers, session_id=session)

        # ZH: 確認歷史已存入 DB | EN: Verify history persisted to DB
        db.expire_all()
        histories = db.query(m.ChatHistory).filter(m.ChatHistory.session_id == session).all()
        assert len(histories) == 2
        roles = {h.role for h in histories}
        assert roles == {"user", "assistant"}

    def test_stream_deducts_tokens(self, client, db):
        """ZH: 串流完成後應扣減 Token 用量 | EN: Tokens deducted after stream completes"""
        from app import models as m
        user = _setup_user_with_quota(db, username="tokenuser")
        headers = auth_headers(client, "tokenuser")
        sse_lines = _make_sse_lines("response text", include_usage=True)

        with patch("app.routers.chat.httpx.AsyncClient") as mock_client_cls:
            mock_instance = MagicMock()
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=False)

            class FakeStreamCtx:
                status_code = 200
                async def __aenter__(self_inner):
                    return self_inner
                async def __aexit__(self_inner, *a):
                    pass
                async def aiter_lines(self_inner):
                    for line in sse_lines:
                        yield line
                async def aread(self_inner):
                    return b""

            mock_instance.stream = MagicMock(return_value=FakeStreamCtx())
            mock_client_cls.return_value = mock_instance

            _post_chat(client, headers)

        db.expire_all()
        usage = db.query(m.TokenUsage).filter(m.TokenUsage.user_id == user.id).first()
        assert usage is not None
        assert usage.tokens_used > 0  # ZH: 有扣減即可 | EN: Any deduction is sufficient

    def test_unauthenticated_returns_401(self, client, db):
        """ZH: 未認證請求回傳 401 | EN: Unauthenticated request returns 401"""
        resp = _post_chat(client, {})
        assert resp.status_code == 401


# ══════════════════════════════════════════════════════════════════
# ZH: Token 配額超限
# EN: Token quota exceeded
# ══════════════════════════════════════════════════════════════════

class TestChatQuotaExceeded:
    def test_quota_exceeded_returns_error_sse(self, client, db):
        """ZH: Token 用量已達上限時，SSE 回傳 error 訊息 | EN: Error SSE when quota exceeded"""
        from app import models as m
        user = _setup_user_with_quota(db, username="quotauser", quota=100)
        # ZH: 將用量設為等於上限 | EN: Set usage equal to limit
        usage = db.query(m.TokenUsage).filter(m.TokenUsage.user_id == user.id).first()
        usage.tokens_used = 100
        db.commit()

        headers = auth_headers(client, "quotauser")
        resp = _post_chat(client, headers)

        assert resp.status_code == 200
        assert "Token quota exceeded" in resp.text


# ══════════════════════════════════════════════════════════════════
# ZH: Portkey 連線失敗
# EN: Portkey connection failure
# ══════════════════════════════════════════════════════════════════

class TestChatPortkeyUnavailable:
    def test_connect_error_returns_friendly_message(self, client, db):
        """ZH: Portkey 無法連線時，SSE 回傳友善錯誤 | EN: Friendly error when Portkey unreachable"""
        import httpx as _httpx
        _setup_user_with_quota(db, username="erruser")
        headers = auth_headers(client, "erruser")

        with patch("app.routers.chat.httpx.AsyncClient") as mock_client_cls:
            mock_instance = MagicMock()
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=False)

            class ErrorStreamCtx:
                async def __aenter__(self_inner):
                    raise _httpx.ConnectError("connection refused")
                async def __aexit__(self_inner, *a):
                    pass

            mock_instance.stream = MagicMock(return_value=ErrorStreamCtx())
            mock_client_cls.return_value = mock_instance

            resp = _post_chat(client, headers)

        assert resp.status_code == 200
        body = resp.text
        # ZH: 回傳訊息含服務未啟動提示 | EN: Response contains "not available" hint
        assert "AI" in body or "error" in body.lower()

    def test_timeout_returns_error_sse(self, client, db):
        """ZH: Portkey 逾時時，SSE 回傳 timeout 錯誤 | EN: Timeout error SSE when Portkey times out"""
        import httpx as _httpx
        _setup_user_with_quota(db, username="timeoutuser")
        headers = auth_headers(client, "timeoutuser")

        with patch("app.routers.chat.httpx.AsyncClient") as mock_client_cls:
            mock_instance = MagicMock()
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=False)

            class TimeoutStreamCtx:
                async def __aenter__(self_inner):
                    raise _httpx.TimeoutException("timed out")
                async def __aexit__(self_inner, *a):
                    pass

            mock_instance.stream = MagicMock(return_value=TimeoutStreamCtx())
            mock_client_cls.return_value = mock_instance

            resp = _post_chat(client, headers)

        assert resp.status_code == 200
        assert "timed out" in resp.text.lower() or "timeout" in resp.text.lower()


# ══════════════════════════════════════════════════════════════════
# ZH: GET /chat/history — 對話歷史
# EN: GET /chat/history — Chat history
# ══════════════════════════════════════════════════════════════════

class TestChatHistory:
    def _seed_history(self, db, user_id, session_id="sess-001", n=3):
        from app import models as m
        for i in range(n):
            db.add(m.ChatHistory(
                user_id=user_id,
                session_id=session_id,
                role="user" if i % 2 == 0 else "assistant",
                content=f"message {i}",
                tool_type="chat",
            ))
        db.commit()

    def test_history_returns_own_messages(self, client, db):
        """ZH: 使用者取得自己的歷史 | EN: User retrieves own history"""
        user = _setup_user_with_quota(db, username="histuser")
        self._seed_history(db, user.id, session_id="sess-abc", n=4)
        headers = auth_headers(client, "histuser")

        resp = client.get("/api/v1/chat/history?session_id=sess-abc", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 4
        assert all("role" in m and "content" in m for m in data)

    def test_history_without_session_returns_all(self, client, db):
        """ZH: 不指定 session_id 時回傳全部歷史 | EN: All history returned when no session_id filter"""
        user = _setup_user_with_quota(db, username="histuser2")
        self._seed_history(db, user.id, session_id="s1", n=2)
        self._seed_history(db, user.id, session_id="s2", n=3)
        headers = auth_headers(client, "histuser2")

        resp = client.get("/api/v1/chat/history", headers=headers)
        assert resp.status_code == 200
        assert len(resp.json()) == 5

    def test_cannot_see_other_users_history(self, client, db):
        """ZH: 使用者看不到其他人的對話 | EN: User cannot see other user's history"""
        user_a = _setup_user_with_quota(db, username="usera")
        user_b = _setup_user_with_quota(db, username="userb")
        self._seed_history(db, user_a.id, session_id="private-sess", n=5)

        headers_b = auth_headers(client, "userb")
        resp = client.get("/api/v1/chat/history?session_id=private-sess", headers=headers_b)
        assert resp.status_code == 200
        assert len(resp.json()) == 0  # ZH: 看不到 user_a 的對話 | EN: user_b sees nothing

    def test_history_unauthenticated_401(self, client):
        """ZH: 未認證回傳 401 | EN: Unauthenticated returns 401"""
        resp = client.get("/api/v1/chat/history")
        assert resp.status_code == 401


# ══════════════════════════════════════════════════════════════════
# ZH: GET /chat/sessions — Session 清單
# EN: GET /chat/sessions — Session list
# ══════════════════════════════════════════════════════════════════

class TestChatSessions:
    def _seed_sessions(self, db, user_id, session_ids: list):
        from app import models as m
        for sid in session_ids:
            db.add(m.ChatHistory(
                user_id=user_id, session_id=sid,
                role="user", content="hi", tool_type="chat",
            ))
        db.commit()

    def test_sessions_returns_distinct_ids(self, client, db):
        """ZH: 回傳不重複的 session_id 清單 | EN: Returns distinct session_id list"""
        user = _setup_user_with_quota(db, username="sessuser")
        self._seed_sessions(db, user.id, ["sess-1", "sess-1", "sess-2", "sess-3"])
        headers = auth_headers(client, "sessuser")

        resp = client.get("/api/v1/chat/sessions", headers=headers)
        assert resp.status_code == 200
        ids = resp.json()
        assert set(ids) == {"sess-1", "sess-2", "sess-3"}

    def test_sessions_empty_for_new_user(self, client, db):
        """ZH: 新使用者沒有任何 session | EN: New user has no sessions"""
        _setup_user_with_quota(db, username="newuser")
        headers = auth_headers(client, "newuser")

        resp = client.get("/api/v1/chat/sessions", headers=headers)
        assert resp.status_code == 200
        assert resp.json() == []

    def test_sessions_unauthenticated_401(self, client):
        """ZH: 未認證回傳 401 | EN: Unauthenticated returns 401"""
        resp = client.get("/api/v1/chat/sessions")
        assert resp.status_code == 401
