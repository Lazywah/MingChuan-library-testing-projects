# -*- coding: utf-8 -*-
"""
ZH: v4.16（方案二 2.3）日誌批次化。

ZH: 這支測試守的是三件事，每一件都對應一個實際會發生的壞結果：
      1. `put()` 永不阻塞 —— 阻塞的話會把 stdout 管線塞滿，
         **訓練程式自己卡在 print 上**（這就是改這一段的理由）
      2. 佇列有上限 —— 沒有的話一支每秒印上萬行的程式會把 worker 記憶體吃光
      3. 丟掉的行要**說出來** —— 默默吞掉會讓人以為訓練真的沒有輸出

ZH: 伺服端那半（一包只重寫一次欄位 + 上限截斷）在 test_job_log_cap.py。

@node tests/test_log_pump.py
"""
import pathlib
import sys
import threading
import time

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "gpu-worker"))
import worker as gw   # noqa: E402


@pytest.fixture
def sent(monkeypatch):
    """ZH: 攔下 report_update，把送出去的 payload 收起來。"""
    out = []
    lock = threading.Lock()

    def fake(job_id, payload, **kwargs):
        """@node tests/test_log_pump.py::sent.fake"""
        with lock:
            out.append(payload)

    monkeypatch.setattr(gw, "report_update", fake)
    return out


def _lines_of(payloads):
    """@node tests/test_log_pump.py::_lines_of"""
    text = []
    for p in payloads:
        if p.get("log"):
            text.extend(p["log"].split(chr(10)))
    return text


class TestBatching:
    def test_many_lines_become_few_requests(self, sent):
        """ZH: 批次的**全部意義**：往返次數要遠少於行數。"""
        pump = gw.LogPump("job-batch")
        for i in range(200):
            pump.put("line %d" % i)
        pump.close()

        assert len(_lines_of(sent)) == 200
        # ZH: 200 行至少要壓成 10 次以內（LOG_BATCH_LINES 預設 50）。
        assert len(sent) <= 10, "送了 %d 次，批次沒有生效" % len(sent)

    def test_order_is_preserved(self, sent):
        """ZH: 日誌亂序比慢更糟 —— 讀的人會以為是程式邏輯錯了。"""
        pump = gw.LogPump("job-order")
        for i in range(120):
            pump.put("L%d" % i)
        pump.close()
        assert _lines_of(sent)[:5] == ["L0", "L1", "L2", "L3", "L4"]

    def test_close_flushes_the_tail(self, sent):
        """ZH: 🔴 最後那幾行往往正是失敗原因 —— close 一定要把它們送完。"""
        pump = gw.LogPump("job-tail")
        pump.put("Traceback (most recent call last):")
        pump.put("RuntimeError: CUDA out of memory")
        pump.close()
        assert "RuntimeError: CUDA out of memory" in _lines_of(sent)

    def test_progress_rides_along(self, sent):
        """ZH: 進度不必自己一次往返。"""
        pump = gw.LogPump("job-prog")
        pump.put("Epoch 1/10")
        pump.set_progress(10.0)
        pump.close()
        assert any(p.get("progress") == 10.0 for p in sent)


class TestBackpressure:
    def test_put_never_blocks(self, sent, monkeypatch):
        """ZH: 🔴 就算送出去那一端完全卡死，put() 也必須立刻回來 ——
            這正是原本「網路慢 → 訓練變慢」的成因。"""
        monkeypatch.setattr(gw, "report_update",
                            lambda *a, **k: time.sleep(30))  # ZH: 假裝網路卡死
        pump = gw.LogPump("job-block")
        t0 = time.time()
        for i in range(gw.LOG_QUEUE_MAX + 500):
            pump.put("x %d" % i)
        elapsed = time.time() - t0
        pump._done.set()          # ZH: 不要等那個卡死的 flush
        assert elapsed < 5, "put() 阻塞了 %.1f 秒" % elapsed

    def test_queue_is_bounded(self, sent):
        """ZH: 上限要真的有效 —— 沒有的話記憶體會跟著輸出量長。"""
        pump = gw.LogPump("job-bound")
        pump._done.set()          # ZH: 先停掉背景送出，讓佇列只進不出
        time.sleep(0.05)
        for i in range(gw.LOG_QUEUE_MAX + 1000):
            pump.put("y %d" % i)
        assert pump._q.qsize() <= gw.LOG_QUEUE_MAX

    def test_dropped_lines_are_reported(self, sent):
        """ZH: 丟掉的行要說出來 —— 默默吞掉會讓人以為訓練沒有輸出。"""
        pump = gw.LogPump("job-drop")
        pump._done.set()
        time.sleep(0.05)
        for i in range(gw.LOG_QUEUE_MAX + 200):
            pump.put("z %d" % i)
        pump._done.clear()
        pump._flush()
        joined = chr(10).join(p.get("log", "") for p in sent)
        assert "略過" in joined or "skipped" in joined

    def test_newest_lines_survive(self, sent):
        """ZH: 滿了要丟**最舊的** —— 出事的原因在最後幾行。"""
        pump = gw.LogPump("job-newest")
        pump._done.set()
        time.sleep(0.05)
        for i in range(gw.LOG_QUEUE_MAX + 300):
            pump.put("n%d" % i)
        last = "n%d" % (gw.LOG_QUEUE_MAX + 299)
        drained = []
        while not pump._q.empty():
            drained.append(pump._q.get_nowait())
        assert last in drained
        assert "n0" not in drained
