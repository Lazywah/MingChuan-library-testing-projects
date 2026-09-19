# -*- coding: utf-8 -*-
"""
ZH: v4.19 —— 貓狗之外的內建訓練種類（表格分類、文字分類）。

ZH: 三層各測各的：
      1. **登錄表與腳本檔一致** —— crud.BUILTIN_TASKS 多寫一種而 gpu-worker 沒有那支
         腳本，症狀是派工成功、worker 起來就 FileNotFoundError；反過來則是腳本永遠沒人跑到。
      2. **服務層** —— 指名新種類送單、派工帶對的 builtin_task 與映像、狀態查詢回 task。
      3. **腳本的純函式** —— 找 CSV、挑答案欄、one-hot、斷詞。這些不需要 torch，
         在服務層容器裡就能測；真的訓練那段用 GPU 實跑驗（2026-09-20 兩支都跑過）。

@node tests/test_builtin_tasks.py
"""
import csv
import importlib.util
import pathlib
import sys

import pytest

from conftest import make_user, auth_headers

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "gpu-worker" / "builtin_scripts"
WORKER_AUTH = {"Authorization": "Bearer test-worker-token-16c"}


def _load(name):
    """ZH: 把內建腳本當模組載入（它們不是套件；torch 只在 main() 裡才 import）。"""
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _heartbeat(client):
    r = client.post("/api/v1/worker/heartbeat",
                    json={"node_id": "n1", "available_gpus": ["0"],
                          "pool_type": "batch", "shares_service_storage": True},
                    headers=WORKER_AUTH)
    assert r.status_code == 200, r.text


def _take(client):
    r = client.post("/api/v1/worker/take",
                    json={"node_id": "n1", "available_gpus": ["0"],
                          "pool_type": "batch", "shares_service_storage": True},
                    headers=WORKER_AUTH)
    assert r.status_code == 200, r.text
    return r.json()["job"]


def _upload_csv_zip(client, headers, rows, name="data.zip", member="data.csv"):
    import io
    import zipfile
    buf = io.StringIO()
    csv.writer(buf, lineterminator="\n").writerows(rows)
    z = io.BytesIO()
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr(member, buf.getvalue())
    r = client.post("/api/v1/datasets/upload", headers=headers,
                    files={"file": (name, z.getvalue(), "application/zip")})
    assert r.status_code == 200, r.text
    return r.json()["dataset_path"]


@pytest.fixture
def user_headers(client, db):
    make_user(db)
    return auth_headers(client)


@pytest.fixture(autouse=True)
def _dataset_root(tmp_path, monkeypatch):
    """ZH: 上傳落到暫存目錄，不碰真的 data/datasets。"""
    from app.routers import datasets as ds
    monkeypatch.setattr(ds, "DATASET_ROOT", tmp_path / "datasets", raising=False)


# ──────────────────────────────────────────────────────────────────────────
# ZH: 一、登錄表 ↔ 腳本檔
# ──────────────────────────────────────────────────────────────────────────

def test_every_registered_task_has_a_script():
    """ZH: 🔴 登錄了卻沒有腳本 → worker 起來就 FileNotFoundError，而使用者只看到「失敗」。"""
    from app import crud
    for task in crud.BUILTIN_TASKS:
        assert (SCRIPTS / f"{task}.py").is_file(), f"缺 gpu-worker/builtin_scripts/{task}.py"


def test_every_script_is_registered():
    """ZH: 反方向 —— 寫了腳本卻沒登錄，永遠沒人跑得到。"""
    from app import crud
    for p in SCRIPTS.glob("*.py"):
        assert p.stem in crud.BUILTIN_TASKS, f"{p.name} 沒有登錄在 crud.BUILTIN_TASKS"


def test_new_tasks_are_registered_with_an_image():
    from app import crud
    for task in ("tabular_classification", "text_classification"):
        assert task in crud.BUILTIN_TASKS
        assert crud.builtin_task_image(task), task


def test_every_script_speaks_the_worker_protocol():
    """ZH: worker 靠三個字面量認腳本的輸出：`@@METRIC `、`Epoch i/n`、`[錯誤]`。
        少一個，那一種任務就沒有指標／進度條／錯誤訊息，而且沒有任何地方會報錯。"""
    for p in SCRIPTS.glob("*.py"):
        s = p.read_text(encoding="utf-8")
        assert '"@@METRIC "' in s, p.name
        assert 'print(f"Epoch {epoch}/{EPOCHS}"' in s, p.name
        assert "[錯誤]" in s, p.name


# ──────────────────────────────────────────────────────────────────────────
# ZH: 二、服務層
# ──────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("task", ["tabular_classification", "text_classification"])
def test_submit_take_and_status_for_new_task(client, db, user_headers, task):
    from app import crud
    _heartbeat(client)
    path = _upload_csv_zip(client, user_headers, [["text", "label"], ["a", "x"], ["b", "y"]])
    r = client.post("/api/v1/jobs", headers=user_headers,
                    json={"job_name": "t", "model_name": "resnet18", "dataset_path": path,
                          "config": {"epochs": 3, "task": task}})
    assert r.status_code == 201, r.text
    job_id = r.json()["job_id"]

    # ZH: 派工帶對的腳本與映像
    job = _take(client)
    assert job["builtin_task"] == task
    assert job["docker_image"] == crud.builtin_task_image(task)

    # ZH: 狀態查詢回 task —— 前端靠它決定失敗時「常見原因」講哪一種
    got = client.get(f"/api/v1/jobs/{job_id}", headers=user_headers).json()
    assert got["task"] == task


def test_status_task_is_none_for_own_script(client, db, user_headers):
    """ZH: 自帶程式的單不是內建任務 —— task 是 None，前端就不會亂講「類別太少」。"""
    _heartbeat(client)
    path = _upload_csv_zip(client, user_headers, [["text", "label"], ["a", "x"]])
    r = client.post("/api/v1/jobs", headers=user_headers,
                    json={"job_name": "t", "model_name": "resnet18", "dataset_path": path,
                          "script_source": "print('hi')", "config": {"epochs": 1}})
    assert r.status_code == 201, r.text
    got = client.get(f"/api/v1/jobs/{r.json()['job_id']}", headers=user_headers).json()
    assert got["task"] is None


def test_images_endpoint_covers_new_tasks(client):
    from app import crud
    images = client.get("/api/v1/worker/images", headers=WORKER_AUTH).json()["images"]
    for task in ("tabular_classification", "text_classification"):
        assert crud.builtin_task_image(task) in images


# ──────────────────────────────────────────────────────────────────────────
# ZH: 三、表格分類腳本的純函式
# ──────────────────────────────────────────────────────────────────────────

class TestTabular:
    @pytest.fixture(autouse=True)
    def _mod(self):
        self.m = _load("tabular_classification")

    def _write_csv(self, tmp_path, rows, name="d.csv", encoding="utf-8"):
        p = tmp_path / name
        with open(p, "w", encoding=encoding, newline="") as f:
            csv.writer(f).writerows(rows)
        return p

    def test_find_csv_picks_the_largest_and_skips_macosx(self, tmp_path):
        (tmp_path / "__MACOSX").mkdir()
        (tmp_path / "__MACOSX" / "._d.csv").write_text("junk" * 100)
        self._write_csv(tmp_path, [["a", "b"]], "small.csv")
        big = self._write_csv(tmp_path, [["a", "b"]] * 50, "big.csv")
        assert self.m.find_csv(str(tmp_path)) == str(big)

    def test_find_csv_fails_loudly_when_missing(self, tmp_path):
        (tmp_path / "readme.txt").write_text("no csv here")
        with pytest.raises(SystemExit):
            self.m.find_csv(str(tmp_path))

    def test_read_rows_accepts_cp950(self, tmp_path):
        """ZH: 台灣的 Excel 存出來的 CSV 常是 cp950 —— 不能只認 UTF-8。"""
        p = self._write_csv(tmp_path, [["科系", "label"], ["資工", "pass"]], encoding="cp950")
        header, body = self.m.read_rows(str(p))
        assert header == ["科系", "label"]
        assert body == [["資工", "pass"]]

    def test_read_rows_strips_bom(self, tmp_path):
        p = self._write_csv(tmp_path, [["x", "label"], ["1", "a"]], encoding="utf-8-sig")
        header, _ = self.m.read_rows(str(p))
        assert header[0] == "x"     # ZH: 不是 '﻿x'

    def test_label_column_by_name_then_last(self):
        assert self.m.pick_label_column(["a", "Label", "b"]) == 1
        assert self.m.pick_label_column(["a", "b", "c"]) == 2
        assert self.m.pick_label_column(["a", "答案", "b"]) == 1

    def test_label_column_from_env(self, monkeypatch):
        monkeypatch.setattr(self.m, "LABEL_COLUMN", "b")
        assert self.m.pick_label_column(["a", "b", "c"]) == 1
        monkeypatch.setattr(self.m, "LABEL_COLUMN", "nope")
        with pytest.raises(SystemExit):
            self.m.pick_label_column(["a", "b"])

    def test_build_features_onehots_text_and_drops_ids(self):
        header = ["id", "hours", "dept", "label"]
        body = [["u1", "3", "資工", "pass"], ["u2", "1", "企管", "fail"], ["u3", "", "資工", "pass"]]
        X, names, y, skipped = self.m.build_features(header, body, 3)
        assert names == ["hours", "dept=企管", "dept=資工"]
        assert skipped == ["id"]              # ZH: 每列都不同 → 不能學，丟掉並說出來
        assert y == ["pass", "fail", "pass"]
        assert X[0] == [3.0, 0.0, 1.0]
        assert X[1] == [1.0, 1.0, 0.0]
        assert X[2][0] != X[2][0]             # ZH: 缺值先留 NaN，由 main() 用中位數補


# ──────────────────────────────────────────────────────────────────────────
# ZH: 四、文字分類腳本的純函式
# ──────────────────────────────────────────────────────────────────────────

class TestText:
    @pytest.fixture(autouse=True)
    def _mod(self):
        self.m = _load("text_classification")

    def test_tokenize_chinese_per_char_english_per_word(self):
        assert self.m.tokenize("這家店 is Great!") == ["這", "家", "店", "is", "great"]

    def test_tokenize_drops_punctuation_and_space(self):
        assert self.m.tokenize("，。！ ") == []

    def test_pick_columns_by_name(self):
        assert self.m.pick_columns(["label", "text"]) == (1, 0)
        assert self.m.pick_columns(["句子", "答案"]) == (0, 1)

    def test_pick_columns_falls_back_to_first_non_label(self):
        # ZH: 沒有認得的名字 → 答案是最後一欄，文字是第一個不是答案的欄
        assert self.m.pick_columns(["comment", "score"]) == (0, 1)

    def test_pick_columns_needs_two(self):
        with pytest.raises(SystemExit):
            self.m.pick_columns(["only"])


# ──────────────────────────────────────────────────────────────────────────
# ZH: 五、範例資料檔
# ──────────────────────────────────────────────────────────────────────────

def test_sample_zips_exist_and_match_their_task():
    """ZH: 前端的「用平台準備好的範例」抓的是 samples/<task>.zip —— 檔名就是契約。"""
    import zipfile
    samples = ROOT / "web-ui-V1" / "samples"
    for task in ("tabular_classification", "text_classification"):
        p = samples / f"{task}.zip"
        assert p.is_file(), p
        with zipfile.ZipFile(p) as zf:
            names = zf.namelist()
            assert len(names) == 1 and names[0].endswith(".csv"), names
            rows = zf.read(names[0]).decode("utf-8-sig").splitlines()
            assert rows[0].endswith(",label"), rows[0]
            assert len(rows) > 100
