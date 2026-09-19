# -*- coding: utf-8 -*-
"""
ZH: v4.16（方案二 2.3）伺服端的日誌附加：多行一包、超長截斷。

ZH: 為什麼要有上限：`logs` 是一個 TEXT 欄位，每次附加都整段重寫。
    實測（2026-09-20）逐行 4000 行要 4.53 秒、批次每 50 行只要 0.11 秒 ——
    批次把曲線壓平了，但一支跑歪的程式可以印幾百萬行，
    那時連批次都救不了（70 MB 的欄位每次附加都要重寫一次）。

ZH: 🔴 截斷要砍**前面**：出事的原因通常在最後幾行（traceback、CUDA OOM），
    開頭那些是環境資訊，重跑一次就有。

@node tests/test_job_log_cap.py
"""
import pytest

from app import crud, models
from conftest import make_user

NL = chr(10)


def _job(db, job_id="log-cap"):
    """@node tests/test_job_log_cap.py::_job"""
    user = db.query(models.User).first() or make_user(db)
    job = models.TrainingJob(id=job_id, user_id=user.id, job_name="t",
                             model_name="m", status="running", priority=0)
    db.add(job)
    db.commit()
    return job


class TestBatchAppend:
    def test_multiline_chunk_is_one_write(self, db):
        """ZH: worker 送上來的是一整包多行 —— 要原樣接上去。"""
        job = _job(db)
        crud.append_job_log(db, job.id, NL.join(["a", "b", "c"]))
        db.refresh(job)
        assert job.logs.splitlines() == ["a", "b", "c"]

    def test_appends_accumulate(self, db):
        """@node tests/test_job_log_cap.py::TestBatchAppend.test_appends_accumulate"""
        job = _job(db)
        crud.append_job_log(db, job.id, "first")
        crud.append_job_log(db, job.id, NL.join(["second", "third"]))
        db.refresh(job)
        assert job.logs.splitlines() == ["first", "second", "third"]

    def test_unknown_job_returns_none(self, db):
        """@node tests/test_job_log_cap.py::TestBatchAppend.test_unknown_job_returns_none"""
        assert crud.append_job_log(db, "no-such-job", "x") is None


class TestCap:
    def test_long_logs_are_capped(self, db):
        """ZH: 超過上限之後不能繼續無限長大。"""
        job = _job(db, "log-cap-long")
        chunk = "x" * 100_000
        for _ in range(15):          # ZH: 1.5 MB > JOB_LOG_MAX_CHARS
            crud.append_job_log(db, job.id, chunk)
        db.refresh(job)
        assert len(job.logs) <= crud.JOB_LOG_MAX_CHARS

    def test_the_tail_survives(self, db):
        """ZH: 🔴 砍前面不砍後面 —— 最後那幾行是失敗原因。"""
        job = _job(db, "log-cap-tail")
        crud.append_job_log(db, job.id, "A" * crud.JOB_LOG_MAX_CHARS)
        crud.append_job_log(db, job.id, "RuntimeError: CUDA out of memory")
        db.refresh(job)
        assert job.logs.rstrip().endswith("RuntimeError: CUDA out of memory")

    def test_truncation_is_announced(self, db):
        """ZH: 截斷要讓人看得出來 —— 不然使用者會以為訓練從中間開始。"""
        job = _job(db, "log-cap-mark")
        crud.append_job_log(db, job.id, "B" * (crud.JOB_LOG_MAX_CHARS + 10))
        db.refresh(job)
        assert "截斷" in job.logs or "truncated" in job.logs

    def test_short_logs_are_untouched(self, db):
        """ZH: 沒超過的不要動它 —— 截斷標記出現在一般任務上會讓人困惑。"""
        job = _job(db, "log-cap-short")
        crud.append_job_log(db, job.id, "hello")
        db.refresh(job)
        assert job.logs.strip() == "hello"
        assert "截斷" not in job.logs
