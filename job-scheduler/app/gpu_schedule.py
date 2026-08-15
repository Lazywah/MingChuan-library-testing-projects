"""
==============================================================================
GPU 節點週時段引擎 (v3.2) | GPU node weekly-schedule engine
==============================================================================
ZH: 純函式模組 — 解析/驗證 gpu_nodes.schedule 的 JSON、判斷「現在可不可排」、
    算「下一次開/關時間」。無 DB、無 I/O，方便單元測試。

    Schedule JSON 格式（存於 gpu_nodes.schedule，NULL/空字串 = 全天可排）：
      {"mon": [["18:00","23:00"]], "sat": [["00:00","23:59"]], "sun": [["18:00","08:00"]]}
      - 鍵：mon/tue/wed/thu/fri/sat/sun，缺鍵＝該日無時段
      - 每段 [開始"HH:MM", 結束"HH:MM"]；結束 <= 開始 = 跨夜（延伸到隔天）
      - 明確給了 dict 但全空 ＝「永不開放」（與 NULL 的「全天開放」語意相反，勿混用）

    ⚠️ 時區：容器時鐘是 UTC，但管理者填的是台北時間。本模組一律以固定 UTC+8
    評估（台灣無日光節約時間，固定偏移安全且零相依——python:3.11-slim 不保證有 tzdata）。
EN: Pure functions — parse/validate the weekly schedule JSON, test "open now",
    and compute the next open/close transition. Evaluated in fixed UTC+8
    (Taiwan has no DST; avoids tzdata dependency in slim images).
==============================================================================
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone

# ZH: 台北固定時區（無 DST）| EN: fixed Taipei offset (no DST)
TZ_TAIPEI = timezone(timedelta(hours=8), name="Asia/Taipei")

WEEK_MINUTES = 7 * 24 * 60          # 10080
_DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
_TIME_RE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")
MAX_SEGMENTS_PER_DAY = 6


def _hm_to_min(s: str) -> int:
    """@node job-scheduler/app/gpu_schedule.py::_hm_to_min"""
    m = _TIME_RE.match(s.strip())
    if not m:
        raise ValueError(f"時間格式須為 HH:MM（收到 {s!r}）")
    return int(m.group(1)) * 60 + int(m.group(2))


def parse_schedule(raw) -> list[tuple[int, int]] | None:
    """
    ZH: 解析 schedule（JSON 字串或 dict）→ [(週分鐘起點, 持續分鐘), ...]。
        回傳 None = 全天可排（raw 為 None/空字串）。格式錯誤丟 ValueError。
        跨夜段（結束<=開始）視為延伸到隔天，持續 = 到隔天結束時刻。
    EN: Parse to [(start_minute_of_week, duration_minutes), ...]; None = always open.
        Overnight segments (end <= start) extend into the next day.

    @node job-scheduler/app/gpu_schedule.py::parse_schedule
    """
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return None
    obj = json.loads(raw) if isinstance(raw, str) else raw
    if not isinstance(obj, dict):
        raise ValueError("schedule 必須是物件（各 weekday 對時段列表）")
    unknown = set(obj.keys()) - set(_DAYS)
    if unknown:
        raise ValueError(f"不明的星期鍵：{sorted(unknown)}（限 {'/'.join(_DAYS)}）")

    windows: list[tuple[int, int]] = []
    for day_idx, day in enumerate(_DAYS):
        segs = obj.get(day) or []
        if not isinstance(segs, list):
            raise ValueError(f"{day} 的時段必須是列表")
        if len(segs) > MAX_SEGMENTS_PER_DAY:
            raise ValueError(f"{day} 時段過多（上限 {MAX_SEGMENTS_PER_DAY} 段）")
        for seg in segs:
            if (not isinstance(seg, (list, tuple))) or len(seg) != 2:
                raise ValueError(f"{day} 的每段須為 [開始,結束]（收到 {seg!r}）")
            start_hm = _hm_to_min(str(seg[0]))
            end_hm = _hm_to_min(str(seg[1]))
            if start_hm == end_hm:
                raise ValueError(f"{day} 時段開始與結束相同（{seg[0]}），請刪除該段或改用整日時段")
            start = day_idx * 1440 + start_hm
            # ZH: 跨夜：18:00→08:00 = 840 分鐘延到隔天 | EN: overnight wraps to next day
            duration = (end_hm - start_hm) if end_hm > start_hm else (1440 - start_hm + end_hm)
            windows.append((start, duration))
    return windows


def _minute_of_week(at: datetime) -> int:
    """@node job-scheduler/app/gpu_schedule.py::_minute_of_week"""
    at = at.astimezone(TZ_TAIPEI)
    return at.weekday() * 1440 + at.hour * 60 + at.minute


def _open_at(windows: list[tuple[int, int]], minute: int, buffer_min: int = 0) -> bool:
    """該週分鐘是否落在任一時段內（buffer 縮短各段結尾）

    @node job-scheduler/app/gpu_schedule.py::_open_at
    """
    for start, dur in windows:
        if (minute - start) % WEEK_MINUTES < max(0, dur - buffer_min):
            return True
    return False


def is_open(windows: list[tuple[int, int]] | None, at: datetime | None = None,
            buffer_min: int = 0) -> bool:
    """
    ZH: 此刻（台北時間）是否可排程。windows=None → 永遠可；空列表 → 永不可。
        buffer_min 供派工閘門用（時段結束前 N 分鐘視為關閉）；顯示用請傳 0。
    EN: Whether schedulable now. None → always; [] → never. buffer_min shrinks
        each window's tail (dispatch gate); pass 0 for display.

    @node job-scheduler/app/gpu_schedule.py::is_open
    """
    if windows is None:
        return True
    if not windows:
        return False
    at = at or datetime.now(TZ_TAIPEI)
    return _open_at(windows, _minute_of_week(at), buffer_min)


def next_transition(windows: list[tuple[int, int]] | None,
                    at: datetime | None = None) -> tuple[bool, datetime | None]:
    """
    ZH: 回 (現在是否開放, 下一次狀態切換的時間)。全開/全關（永不切換）→ (state, None)。
        用逐分鐘掃描（上限一週 10080 步）：簡單、對重疊/跨夜時段絕對正確；
        本函式只給 admin 狀態欄呼叫，效能無虞。
    EN: (open_now, next state-change datetime). Minute-walk (≤10080 steps) — simple
        and provably correct across overlapping/overnight windows; admin-panel only.

    @node job-scheduler/app/gpu_schedule.py::next_transition
    """
    if windows is None:
        return True, None
    if not windows:
        return False, None
    at = (at or datetime.now(TZ_TAIPEI)).astimezone(TZ_TAIPEI)
    m = _minute_of_week(at)
    now_state = _open_at(windows, m)
    base = at.replace(second=0, microsecond=0)
    for step in range(1, WEEK_MINUTES + 1):
        if _open_at(windows, (m + step) % WEEK_MINUTES) != now_state:
            return now_state, base + timedelta(minutes=step)
    return now_state, None   # 時段覆蓋全週（或理論上的全空）→ 永不切換
