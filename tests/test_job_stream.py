# -*- coding: utf-8 -*-
"""
ZH: v4.19 —— SSE 串流（GET /jobs/{id}/stream）。

ZH: ① 日誌被砍頭（crud.append_job_log 的 1 MB 上限）之後，舊游標指到的位置不存在了。
      修之前：長度變短 → `len > last_log_len` 不成立 → 什麼都不送；等日誌再長回舊長度，
      送出的是**錯位的片段**。要的是整份重送並標 reset。游標推進抽成 `_log_delta`，
      在這裡直接測；串流本身只做一次煙霧（歷史 → 終態 → 結束）。
    ② 沒變化時不讀整列（「SSE 讀取成本」）—— 探針是實作細節，靠 code review。

@node tests/test_job_stream.py
"""
import json

import pytest

from conftest import make_user, auth_headers
from app.routers.jobs import _log_delta


class TestLogCursor:
    def test_appends_send_only_the_tail(self):
        assert _log_delta("abcdef", 3) == ("def", False, 6)

    def test_no_change_sends_nothing(self):
        assert _log_delta("abc", 3) == ("", False, 3)

    def test_none_is_empty(self):
        assert _log_delta(None, 0) == ("", False, 0)

    def test_trimmed_log_is_resent_whole_with_reset(self):
        """ZH: 🔴 長度變短 ＝ 被砍頭：整份重送、標 reset、游標歸到新長度。"""
        assert _log_delta("tail-only", 500) == ("tail-only", True, 9)

    def test_after_reset_cursor_continues_from_new_length(self):
        _, _, cur = _log_delta("tail-only", 500)
        assert _log_delta("tail-only+more", cur) == ("+more", False, 14)


@pytest.fixture
def user_headers(client, db):
    make_user(db)
    return auth_headers(client)


def test_stream_sends_history_then_ends_on_terminal_state(client, db, user_headers):
    """ZH: 第一筆是全部歷史；任務已是終態時，再送一筆更新就結束（不會掛著）。"""
    from app import crud
    r = client.post("/api/v1/jobs", headers=user_headers,
                    json={"job_name": "s", "model_name": "resnet18", "config": {"epochs": 1}})
    assert r.status_code == 201, r.text
    job_id = r.json()["job_id"]
    crud.append_job_log(db, job_id, "line1")
    crud.update_job_status(db, job_id, "completed")

    events = []
    with client.stream("GET", f"/api/v1/jobs/{job_id}/stream", headers=user_headers) as resp:
        assert resp.status_code == 200
        for line in resp.iter_lines():
            line = line.decode() if isinstance(line, bytes) else line
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))
    assert "line1" in events[0]["logs"]
    assert events[-1]["status"] == "completed"
    assert events[-1].get("reset") is False
