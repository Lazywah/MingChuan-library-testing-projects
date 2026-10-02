# -*- coding: utf-8 -*-
"""
ZH: 實驗室範例 —— v4.19 起有三種（貓狗／表格／文字），v4.36 起**每個存檔都放**。

ZH: v4.19 是「學習程式碼」按鈕選了哪一種才放哪一種；那顆按鈕在 2026-10-02 拿掉了，
    改成訓練結果下方的一段說明：「到程式實驗室的 projects 裡就有」。
    所以不管從哪裡開實驗室，範例都要在 —— 而且**不能覆蓋**學生改過的檔。

ZH: 四層：
      1. samples_tar：表格＋文字打進同一個 tar、放在暫存目錄、是 coder 的（uid 1000）。
         貓狗**不在這裡**（10 MB 圖片烤在映像裡，由 entrypoint 放）。
      2. 範例本身：每一支 .py 第一段都寫「怎麼跑」（Run on GPU）。
      3. seed_samples：put_archive 進暫存目錄 → 以 coder 執行 `cp -n`（不覆蓋）→ 寫記號；
         有記號就不再放；任何一步失敗都**不影響開實驗室**。
      4. /lab/start：不再收 sample；舊前端帶來的 sample 直接忽略，不是 400。
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
    """ZH: 指到範例的正本。

    ZH: 🔴 兩個環境的路徑不一樣，所以要挑：
          · 主機上跑 → repo 裡的 `job-scheduler/lab_samples/`
          · 容器裡跑 → 映像把它放在 `/app/lab_samples/`（`lm.LAB_SAMPLES_DIR` 的預設值），
            而 repo 的 `job-scheduler/` 那一層**不存在**
        原本寫死 repo 路徑，於是在容器裡（＝平常跑測試的地方）五條全紅，
        錯誤訊息還是 `tarfile.ReadError: empty file` —— 看起來像範例壞了，
        實際上是測試自己指錯地方（2026-09-23 抓到）。

    ZH: ⚠ 兩邊都找不到就**當場失敗**，不要 skip ——
        「範例檔不見了」正是這一族測試要抓的事，skip 掉等於沒測。
    """
    for d in (REPO / "job-scheduler" / "lab_samples", lm.LAB_SAMPLES_DIR):
        if d.is_dir() and any(d.iterdir()):
            monkeypatch.setattr(lm, "LAB_SAMPLES_DIR", d)
            return d
    raise AssertionError(
        "找不到 lab_samples 正本：repo 的 job-scheduler/lab_samples 與 "
        f"{lm.LAB_SAMPLES_DIR} 都沒有檔案")


def _members(data: bytes):
    with tarfile.open(fileobj=io.BytesIO(data)) as tf:
        return {m.name: m for m in tf.getmembers()}


STAGE = lm._SAMPLES_STAGE


# ── 1. samples_tar ───────────────────────────────────────────────────────

def test_tar_has_both_samples_in_the_stage_dir(samples_dir):
    m = _members(lm.samples_tar())
    assert STAGE in m and m[STAGE].isdir()
    assert {f"{STAGE}/sample_tabular.py", f"{STAGE}/students.csv",
            f"{STAGE}/sample_text.py", f"{STAGE}/reviews.csv"} <= set(m)


def test_tar_does_not_carry_cats_dogs(samples_dir):
    """ZH: 貓狗烤在 code-server 映像裡，entrypoint 自己放 —— 這裡不重複帶 10 MB。"""
    assert not any("cat" in n for n in _members(lm.samples_tar()))


def test_files_belong_to_coder(samples_dir):
    """ZH: 🔴 uid 不是 1000 的話檔案在 VS Code 裡是唯讀的 —— 學生改不了 EPOCHS。"""
    for m in _members(lm.samples_tar()).values():
        assert (m.uid, m.gid) == (1000, 1000), m.name


def test_no_files_means_no_tar(tmp_path, monkeypatch):
    monkeypatch.setattr(lm, "LAB_SAMPLES_DIR", tmp_path)
    assert lm.samples_tar() is None


# ── 2. 範例本身 ──────────────────────────────────────────────────────────

def test_every_sample_says_how_to_run_it(samples_dir):
    """ZH: 範例的第一段就是「怎麼跑」。訓練結果下方的說明也叫人按右鍵 Run on GPU ——
    實驗室本身沒有 torch，直接按 ▶ 會失敗，所以這句一定要在。"""
    for sub in lm.LAB_SAMPLE_DIRS:
        py = list((samples_dir / sub).glob("*.py"))
        assert py, sub
        assert "Run on GPU" in py[0].read_text(encoding="utf-8"), py[0]


# ── 3. seed_samples ──────────────────────────────────────────────────────

class _Res:
    def __init__(self, code):
        self.exit_code = code


class _FakeContainer:
    name = "cs-test"

    def __init__(self, fail_put=False, exit_code=0):
        self.puts, self.execs = [], []
        self.fail_put, self.exit_code = fail_put, exit_code

    def put_archive(self, path, data):
        if self.fail_put:
            raise RuntimeError("boom")
        self.puts.append((path, data))
        return True

    def exec_run(self, cmd, user=None, environment=None):
        self.execs.append({"cmd": cmd, "user": user, "env": environment})
        return _Res(self.exit_code)


def test_seed_stages_then_copies_without_overwriting(samples_dir):
    c = _FakeContainer()
    assert lm.seed_samples(c) is True
    assert c.puts and c.puts[0][0] == lm.LAB_HOME
    script = c.execs[0]["cmd"][-1]
    # ZH: 🔴 不覆蓋 —— 學生改了 EPOCHS，關掉再開不能被打回原樣
    assert "cp -n" in script
    # ZH: 放過就不再放（刪掉就是不要了）
    assert lm.SAMPLES_MARK in script and "touch" in script
    # ZH: 暫存目錄一律清掉，不留在學生的家目錄裡
    assert "rm -rf" in script and STAGE in script


def test_seed_runs_as_coder(samples_dir):
    """ZH: 以 root 跑的話記號檔是 root 的，學生刪不掉也改不了。"""
    c = _FakeContainer()
    lm.seed_samples(c)
    assert c.execs[0]["user"] == "coder"


def test_seed_failure_does_not_raise(samples_dir):
    """ZH: 範例放不進去不該讓實驗室開不起來 —— 容器已經起來了。"""
    assert lm.seed_samples(_FakeContainer(fail_put=True)) is False


def test_seed_script_error_is_reported_not_raised(samples_dir):
    assert lm.seed_samples(_FakeContainer(exit_code=1)) is False


def test_seed_script_really_skips_existing_files(samples_dir, tmp_path):
    """ZH: 不只看字串 —— 用真的 sh 跑一次那段腳本，確認改過的檔真的沒被蓋掉、記號真的擋得住第二次。"""
    import shutil
    import subprocess
    if not shutil.which("sh"):
        pytest.skip("沒有 sh")
    home = tmp_path
    (home / "projects").mkdir()
    (home / "projects" / "sample_text.py").write_text("EPOCHS = 99  # 學生改過的\n", encoding="utf-8")
    stage = home / STAGE
    stage.mkdir()
    for sub in lm.LAB_SAMPLE_DIRS:
        for f in (samples_dir / sub).iterdir():
            shutil.copy(f, stage / f.name)
    env = {"HOME": str(home), "PATH": "/usr/bin:/bin"}
    subprocess.run(["sh", "-c", lm._SEED_SH], env=env, check=True)
    assert (home / "projects" / "sample_text.py").read_text(encoding="utf-8").startswith("EPOCHS = 99")
    assert (home / "projects" / "sample_tabular.py").exists(), "缺的那份要補上"
    assert (home / "projects" / lm.SAMPLES_MARK).exists()
    assert not stage.exists(), "暫存目錄沒清掉"
    # ZH: 第二次：學生把表格範例刪掉了 → 有記號，不再補
    (home / "projects" / "sample_tabular.py").unlink()
    stage.mkdir()
    shutil.copy(samples_dir / "tabular" / "sample_tabular.py", stage / "sample_tabular.py")
    subprocess.run(["sh", "-c", lm._SEED_SH], env=env, check=True)
    assert not (home / "projects" / "sample_tabular.py").exists(), "刪掉的又被補回來了"


# ── 4. /lab/start ────────────────────────────────────────────────────────

@pytest.fixture
def user_headers(client, db):
    make_user(db)
    return auth_headers(client)


@pytest.fixture
def captured_start(monkeypatch):
    seen = {}

    def fake_start_session(db, user_id, base_image=None, session=lm.DEFAULT_SESSION,
                           want_gpu=False):
        seen.update(session=session, want_gpu=want_gpu)
        return {"url": "/code/x/", "password": "p", "container_name": "cs-x", "started_at": "now"}
    monkeypatch.setattr(lm, "start_session", fake_start_session)
    monkeypatch.setattr(lm, "_stop_other_running", lambda db, uid, keep=None: None)
    return seen


def test_start_ignores_a_legacy_sample_key(client, db, user_headers, captured_start):
    """ZH: 舊前端（快取裡的 gpu.js）還會帶 sample —— 忽略就好，不是 400。"""
    r = client.post("/api/v1/lab/start", json={"sample": "tabular"}, headers=user_headers)
    assert r.status_code == 200, r.text


def test_start_without_sample(client, db, user_headers, captured_start):
    assert client.post("/api/v1/lab/start", json={}, headers=user_headers).status_code == 200
    assert captured_start["want_gpu"] is False
