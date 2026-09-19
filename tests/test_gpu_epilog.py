# -*- coding: utf-8 -*-
"""
ZH: v4.15（方案二 2.5）GPU epilog —— 任務結束後檢查那張卡還健康嗎。

ZH: 這支測試的重點是**兩級判準不要互相汙染**：
      · 問不到那張卡 → 隔離（沒有第二種解釋）
      · VRAM 比開跑前高 → 只警告（這台的卡與 Ollama / Code Lab 共用，
        把用量變高當成洩漏會一直誤報，而會誤報的檢查等於沒有）
    誤判的代價是不對稱的：漏判只是多用一張可疑的卡；
    誤判是把一台好機器從叢集裡拿掉，而且沒有人會發現它被拿掉了。

@node tests/test_gpu_epilog.py
"""
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "gpu-worker"))
import worker as gw   # noqa: E402


@pytest.fixture(autouse=True)
def _clean_quarantine():
    """ZH: 隔離狀態是模組層的集合 —— 每支測試前後都要清乾淨，
        否則前一支測試隔離的卡會讓後一支莫名其妙地失敗。"""
    gw._quarantined_gpus.clear()
    yield
    gw._quarantined_gpus.clear()


class _FakeRun:
    """ZH: 假的 subprocess.run 結果。"""

    def __init__(self, returncode=0, stdout=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = ""


# ==============================================================================
# ZH: 查詢
# ==============================================================================
class TestGpuMemoryUsed:
    def test_reads_the_number(self, monkeypatch):
        """@node tests/test_gpu_epilog.py::TestGpuMemoryUsed.test_reads_the_number"""
        monkeypatch.setattr(gw.subprocess, "run",
                            lambda *a, **k: _FakeRun(0, "1234\n"))
        assert gw.gpu_memory_used("0") == 1234

    def test_non_zero_exit_is_none(self, monkeypatch):
        """ZH: 🔴 問不到要回 None，**不是 0** —— 回 0 的話 epilog 會把
            一張壞掉的卡當成「很乾淨」。"""
        monkeypatch.setattr(gw.subprocess, "run",
                            lambda *a, **k: _FakeRun(1, ""))
        assert gw.gpu_memory_used("0") is None

    def test_not_a_number_is_none(self, monkeypatch):
        """ZH: 某些驅動/虛擬化組合會回 [N/A]（get_available_gpus 也處理過同一件事）。"""
        monkeypatch.setattr(gw.subprocess, "run",
                            lambda *a, **k: _FakeRun(0, "[N/A]\n"))
        assert gw.gpu_memory_used("0") is None

    def test_exception_is_none(self, monkeypatch):
        """@node tests/test_gpu_epilog.py::TestGpuMemoryUsed.test_exception_is_none"""
        def boom(*a, **k):
            raise OSError("nvidia-smi missing")
        monkeypatch.setattr(gw.subprocess, "run", boom)
        assert gw.gpu_memory_used("0") is None


# ==============================================================================
# ZH: epilog 的兩級判準
# ==============================================================================
class TestEpilogLevels:
    def test_unqueryable_gpu_is_quarantined(self, monkeypatch):
        """ZH: 硬失敗 —— 這是唯一會讓節點停用一張卡的情況。"""
        monkeypatch.setattr(gw, "gpu_memory_used", lambda gpu: None)
        monkeypatch.setattr(gw, "report_update", lambda *a, **k: None)
        gw.gpu_epilog("0", 500, "job-123456")
        assert "0" in gw.quarantined_snapshot()

    def test_leak_only_warns(self, monkeypatch):
        """ZH: 🔴 VRAM 變高**不隔離**。共用卡上 Ollama 隨時可能載入模型，
            隔離會把一台好機器拿掉。"""
        monkeypatch.setattr(gw, "gpu_memory_used",
                            lambda gpu: 500 + gw.GPU_LEAK_WARN_MB + 1)
        gw.gpu_epilog("0", 500, "job-123456")
        assert gw.quarantined_snapshot() == []

    def test_clean_run_changes_nothing(self, monkeypatch):
        """@node tests/test_gpu_epilog.py::TestEpilogLevels.test_clean_run_changes_nothing"""
        monkeypatch.setattr(gw, "gpu_memory_used", lambda gpu: 500)
        gw.gpu_epilog("0", 500, "job-123456")
        assert gw.quarantined_snapshot() == []

    def test_no_baseline_still_does_the_health_check(self, monkeypatch):
        """ZH: 開跑前就問不到（mem_before=None）時，仍然要做健康檢查 ——
            那時候更可疑，不是更不可疑。"""
        monkeypatch.setattr(gw, "gpu_memory_used", lambda gpu: None)
        monkeypatch.setattr(gw, "report_update", lambda *a, **k: None)
        gw.gpu_epilog("1", None, "job-abcdef")
        assert "1" in gw.quarantined_snapshot()

    def test_no_baseline_and_healthy_card_is_left_alone(self, monkeypatch):
        """ZH: 沒有基準線就無從判斷洩漏 —— 不能因此就當成壞掉。"""
        monkeypatch.setattr(gw, "gpu_memory_used", lambda gpu: 900)
        gw.gpu_epilog("0", None, "job-abcdef")
        assert gw.quarantined_snapshot() == []


# ==============================================================================
# ZH: 隔離之後不再領工作
# ==============================================================================
class TestQuarantineAffectsDispatch:
    def test_quarantined_card_is_not_offered(self, monkeypatch):
        """ZH: 隔離要真的有效果 —— 只記在集合裡但照樣回報可用，等於沒做。"""
        monkeypatch.setattr(gw.subprocess, "run",
                            lambda *a, **k: _FakeRun(0, "0, 1\n1, 1\n"))
        monkeypatch.setattr(gw, "_busy_gpu_snapshot", lambda: set())
        assert gw.get_available_gpus() == ["0", "1"]

        gw._quarantine_gpu("0", "test")
        assert gw.get_available_gpus() == ["1"]

    def test_quarantine_is_idempotent(self, monkeypatch):
        """ZH: 每張單結束都會再檢查一次 —— 同一張壞卡不該每次都再喊一遍。"""
        gw._quarantine_gpu("0", "first")
        gw._quarantine_gpu("0", "second")
        assert gw.quarantined_snapshot() == ["0"]
