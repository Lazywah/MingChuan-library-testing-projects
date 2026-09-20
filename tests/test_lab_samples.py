# -*- coding: utf-8 -*-
"""
ZH: v4.19 —— 「學習程式碼」可選範例（貓狗／表格／文字）。

ZH: 三層：
      1. sample_tar：打出來的 tar 放對地方（projects/<檔>）、是 coder 的（uid 1000）、
         貓狗回 None（映像裡本來就有）、不認得的種類要炸。
      2. seed_sample：呼叫 put_archive 到 /home/coder；放不進去**不影響開實驗室**。
      3. /lab/start：sample 會傳到 start_session；不認得的 sample 當場 400。
    範例腳本本身在 GPU 實跑過（2026-09-20，表格 ~88%、文字 100%）。

@node tests/test_lab_samples.py
"""
import io
import pathlib
import sys
import tarfile

import pytest

from conftest import make_user, auth_headers

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "job-scheduler"))
from app.services import lab_manager as lm   # noqa: E402

REPO = pathlib.Path(__file__).resolve().parent.parent


@pytest.fixture
def samples_dir(monkeypatch):
    """ZH: 指到 repo 裡的正本（容器裡跑時 /app/lab_samples 也在，但這樣兩邊都能測）。"""
    d = REPO / "job-scheduler" / "lab_samples"
    monkeypatch.setattr(lm, "LAB_SAMPLES_DIR", d)
    return d


def _members(data: bytes):
    with tarfile.open(fileobj=io.BytesIO(data)) as tf:
        return {m.name: m for m in tf.getmembers()}


# ── 1. sample_tar ────────────────────────────────────────────────────────

def test_tabular_tar_has_script_csv_and_projects_dir(samples_dir):
    m = _members(lm.sample_tar("tabular"))
    assert "projects" in m and m["projects"].isdir()
    assert "projects/sample_tabular.py" in m
    assert "projects/students.csv" in m


def test_text_tar_has_script_and_csv(samples_dir):
    m = _members(lm.sample_tar("text"))
    assert {"projects/sample_text.py", "projects/reviews.csv"} <= set(m)


def test_files_belong_to_coder(samples_dir):
    """ZH: 🔴 uid 不是 1000 的話檔案在 VS Code 裡是唯讀的 —— 學生改不了 EPOCHS。"""
    for m in _members(lm.sample_tar("tabular")).values():
        assert (m.uid, m.gid) == (1000, 1000), m.name


def test_cats_dogs_needs_no_tar(samples_dir):
    """ZH: 貓狗烤在 code-server 映像裡，entrypoint 自己放 —— 這裡不重複放 10 MB。"""
    assert lm.sample_tar("cats_dogs") is None


def test_unknown_kind_raises(samples_dir):
    with pytest.raises(ValueError):
        lm.sample_tar("speech")


def test_every_kind_has_a_python_file_that_mentions_run_on_gpu(samples_dir):
    """ZH: 範例的第一句就是「怎麼跑」—— 沒寫的話學生開了檔案不知道下一步。"""
    for kind, sub in lm.LAB_SAMPLE_KINDS.items():
        if sub is None:
            continue
        py = list((samples_dir / sub).glob("*.py"))
        assert py, kind
        assert "Run on GPU" in py[0].read_text(encoding="utf-8"), py[0]


# ── 2. seed_sample ───────────────────────────────────────────────────────

class _FakeContainer:
    name = "cs-test"

    def __init__(self, fail=False):
        self.calls = []
        self.fail = fail

    def put_archive(self, path, data):
        if self.fail:
            raise RuntimeError("boom")
        self.calls.append((path, data))
        return True


def test_seed_puts_archive_into_home(samples_dir):
    c = _FakeContainer()
    assert lm.seed_sample(c, "text") is True
    assert c.calls and c.calls[0][0] == lm.LAB_HOME
    assert "projects/sample_text.py" in _members(c.calls[0][1])


def test_seed_none_and_cats_dogs_do_nothing(samples_dir):
    c = _FakeContainer()
    assert lm.seed_sample(c, None) is False
    assert lm.seed_sample(c, "cats_dogs") is False
    assert c.calls == []


def test_seed_failure_does_not_raise(samples_dir):
    """ZH: 範例放不進去不該讓實驗室開不起來 —— 容器已經起來了。"""
    assert lm.seed_sample(_FakeContainer(fail=True), "tabular") is False


# ── 3. /lab/start ────────────────────────────────────────────────────────

@pytest.fixture
def user_headers(client, db):
    make_user(db)
    return auth_headers(client)


@pytest.fixture
def captured_start(monkeypatch):
    seen = {}

    def fake_start_session(db, user_id, base_image=None, session=lm.DEFAULT_SESSION,
                           want_gpu=False, sample=None):
        seen.update(sample=sample, session=session, want_gpu=want_gpu)
        return {"url": "/code/x/", "password": "p", "container_name": "cs-x", "started_at": "now"}
    monkeypatch.setattr(lm, "start_session", fake_start_session)
    monkeypatch.setattr(lm, "_stop_other_running", lambda db, uid, keep=None: None)
    return seen


def test_start_passes_the_sample_through(client, db, user_headers, captured_start):
    r = client.post("/api/v1/lab/start", json={"sample": "tabular"}, headers=user_headers)
    assert r.status_code == 200, r.text
    assert captured_start["sample"] == "tabular"


def test_start_without_sample_is_none(client, db, user_headers, captured_start):
    """ZH: 既有前端（lab.html）不帶 sample —— 行為與以前逐字相同。"""
    assert client.post("/api/v1/lab/start", json={}, headers=user_headers).status_code == 200
    assert captured_start["sample"] is None


def test_start_rejects_unknown_sample(client, db, user_headers, captured_start):
    """ZH: 選了「文字」卻開出貓狗是最難查的失敗 —— 不認得就當場拒絕。"""
    r = client.post("/api/v1/lab/start", json={"sample": "speech"}, headers=user_headers)
    assert r.status_code == 400, r.text
    assert "speech" in r.text
    assert "sample" not in captured_start
