# -*- coding: utf-8 -*-
"""
ZH: v4.19 —— 訓練容器寫得進 worker 建的目錄。

ZH: 🔴 2026-09-20 實跑抓到的：worker 是 root，建出來的 outputs/<job>/ 與 .torch/
    是 0755；平台映像 aibase/pytorch:2026-spring 以 coder（uid 1000）跑，
    於是 `torch.save` 直接 Permission denied —— **內建訓練 100% 失敗**，
    而錯誤訊息長得像網路問題。這裡守的是「worker 建的可寫目錄要 777」。
    真正的驗證是 GPU 實跑（同日三種任務都跑完並回傳 model.pt）。

@node tests/test_job_output_permissions.py
"""
import os
import pathlib
import stat
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "gpu-worker"))
import worker as gw   # noqa: E402


@pytest.fixture
def storage(tmp_path, monkeypatch):
    monkeypatch.setattr(gw, "HOST_STORAGE_MOUNT", str(tmp_path))
    return tmp_path


@pytest.mark.skipif(os.name == "nt", reason="Windows 沒有 POSIX 權限位元")
def test_writable_dirs_are_world_writable(storage):
    d = gw._host_dir("outputs", "job-1", writable_by_anyone=True)
    assert d.is_dir()
    assert stat.S_IMODE(d.stat().st_mode) == 0o777


@pytest.mark.skipif(os.name == "nt", reason="Windows 沒有 POSIX 權限位元")
def test_plain_dirs_keep_the_default_mode(storage):
    """ZH: 陰性對照 —— 唯讀掛載那些（scripts / jobscripts / datasets）不該被開 777。"""
    d = gw._host_dir("scripts")
    assert d.is_dir()
    assert stat.S_IMODE(d.stat().st_mode) != 0o777


def test_host_dir_is_idempotent(storage):
    a = gw._host_dir("outputs", "job-2", writable_by_anyone=True)
    b = gw._host_dir("outputs", "job-2", writable_by_anyone=True)
    assert a == b and a.is_dir()


def test_exception_line_regex():
    """ZH: 沒有 [錯誤] 行時，錯誤訊息要帶 traceback 的最後一行；但一般的 key: value 不算。"""
    yes = ["RuntimeError: File /workspace/output/model.pt cannot be opened",
           "torch.cuda.OutOfMemoryError: CUDA out of memory",
           "KeyboardInterrupt:",
           "SystemExit: 1"]
    no = ["loss: 0.31", "Epoch 1/3", "GPU: NVIDIA", "資料筆數 / Rows: 320", "Error: not python style"]
    for s in yes:
        assert gw._EXCEPTION_LINE.match(s), s
    for s in no:
        assert not gw._EXCEPTION_LINE.match(s), s
