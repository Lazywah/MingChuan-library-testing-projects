# -*- coding: utf-8 -*-
"""
ZH: v4.36 「上傳一張圖片試試看」—— POST /jobs/{id}/try（服務層 CPU 推論，擁有者選 (a)）。

ZH: 這一族守三件事，第一件最重要：
      1. 🔴 **只對內建程式訓練的圖片模型開放**。自帶程式的 model.pt 是使用者自己的程式寫的，
         服務層去載入它＝讓他在伺服器上執行任意程式 —— 所以那種單在**載入之前**就要被擋下，
         而且載入一律 weights_only（格式不對就拒絕）。
      2. 不能把服務層拖垮：同時名額、依使用者的頻率限制、圖片大小上限。
      3. 回應分得開（403／404／409／410／400／429／503），前端照實講。

ZH: 模型用真的 ResNet-18 結構、隨機權重、32px —— 判斷結果沒有意義，
    但「載得進來、跑得出每一類的機率」是真的。

@node tests/test_try_model.py
"""
import io
import json

import pytest

from conftest import auth_headers, make_user

# ZH: 直接 import，**不用 importorskip**：torch 是 requirements.txt 宣告的依賴，
#     缺了就是部署壞了，該紅不該跳過（跳過的測試會被當成「已驗證」）。
import torch  # noqa: E402


def _png(size=(48, 40), color=(200, 120, 30)):
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def artifacts(tmp_path, monkeypatch):
    from app.routers import worker as wr
    monkeypatch.setattr(wr, "ARTIFACT_ROOT", str(tmp_path / "artifacts"))
    return tmp_path / "artifacts"


def _save_model(path, classes=("cats", "dogs"), arch="resnet18"):
    from torch import nn
    from torchvision import models
    m = models.resnet18(weights=None)
    m.fc = nn.Linear(m.fc.in_features, len(classes))
    path.parent.mkdir(parents=True, exist_ok=True)
    torch.save({"state_dict": m.state_dict(), "classes": list(classes),
                "img_size": 32, "arch": arch}, str(path))


def _job(db, user, artifacts, task="image_classification", script=None, status="completed",
         with_file=True, arch="resnet18"):
    from app import models
    j = models.TrainingJob(job_name="t", model_name="resnet18", status=status, user_id=user.id,
                           dataset_path="/data/datasets/x/y.zip",
                           config=json.dumps({"task": task}), script_source=script,
                           artifact_bytes=123)
    db.add(j)
    db.commit()
    if with_file:
        _save_model(artifacts / j.id / "model.pt", arch=arch)
    return j.id


@pytest.fixture
def owner(client, db):
    u = make_user(db, username="tryer", email="tryer@example.com")
    return u, auth_headers(client, "tryer")


@pytest.fixture(autouse=True)
def fresh_limits(monkeypatch):
    from app.routers import jobs as jr
    monkeypatch.setattr(jr, "_try_hits", {})


def _post(client, h, jid, data=None, name="me.png"):
    return client.post(f"/api/v1/jobs/{jid}/try", headers=h,
                       files={"file": (name, data if data is not None else _png(), "image/png")})


# ── 1. 正常 ─────────────────────────────────────────────────────────

def test_returns_a_label_and_every_class_score(client, db, owner, artifacts):
    u, h = owner
    jid = _job(db, u, artifacts)
    r = _post(client, h, jid)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["label"] in ("cats", "dogs")
    labels = [s["label"] for s in body["scores"]]
    assert sorted(labels) == ["cats", "dogs"], "每一類都要有分數，不能只給最高的"
    ps = [s["p"] for s in body["scores"]]
    assert ps == sorted(ps, reverse=True)
    assert abs(sum(ps) - 1) < 0.01
    assert body["confidence"] == ps[0]


# ── 2. 🔴 自帶程式的模型連載入都不能 ───────────────────────────────

def test_own_script_job_is_refused_before_loading(client, db, owner, artifacts, monkeypatch):
    from app.services import inference
    def boom(path):
        raise AssertionError("自帶程式的模型檔被載入了")
    monkeypatch.setattr(inference, "_load_model", boom)
    u, h = owner
    jid = _job(db, u, artifacts, script="print('hi')")
    assert _post(client, h, jid).status_code == 409


def test_tabular_model_is_refused(client, db, owner, artifacts):
    u, h = owner
    jid = _job(db, u, artifacts, task="tabular_classification")
    assert _post(client, h, jid).status_code == 409


def test_unknown_checkpoint_format_is_rejected(client, db, owner, artifacts):
    """ZH: 內建格式以外的東西（arch 不是 resnet18）不硬載。"""
    u, h = owner
    jid = _job(db, u, artifacts, arch="mystery")
    assert _post(client, h, jid).status_code == 400


def test_loading_is_weights_only(monkeypatch, tmp_path):
    """ZH: 🔴 拿掉 weights_only 的話這條會紅 —— 那是擋夾帶程式碼的最後一道。"""
    from app.services import inference
    seen = {}
    real = torch.load
    def spy(*a, **k):
        seen.update(k)
        return real(*a, **k)
    monkeypatch.setattr(torch, "load", spy)
    p = tmp_path / "m.pt"
    _save_model(p)
    inference._cache.clear()
    inference._load_model(str(p))
    assert seen.get("weights_only") is True


# ── 3. 權限與狀態 ───────────────────────────────────────────────────

def test_another_student_cannot_try(client, db, owner, artifacts):
    u, _ = owner
    jid = _job(db, u, artifacts)
    make_user(db, username="other2", email="other2@example.com")
    assert _post(client, auth_headers(client, "other2"), jid).status_code == 403


def test_unfinished_job_is_404(client, db, owner, artifacts):
    u, h = owner
    jid = _job(db, u, artifacts, status="running")
    assert _post(client, h, jid).status_code == 404


def test_missing_model_file_is_410(client, db, owner, artifacts):
    u, h = owner
    jid = _job(db, u, artifacts, with_file=False)
    assert _post(client, h, jid).status_code == 410


# ── 4. 輸入與保護 ───────────────────────────────────────────────────

def test_not_an_image_is_400(client, db, owner, artifacts):
    u, h = owner
    jid = _job(db, u, artifacts)
    assert _post(client, h, jid, data=b"definitely not an image", name="x.png").status_code == 400


def test_too_large_is_400(client, db, owner, artifacts, monkeypatch):
    from app.services import inference
    monkeypatch.setattr(inference, "MAX_IMAGE_BYTES", 100)
    u, h = owner
    jid = _job(db, u, artifacts)
    assert _post(client, h, jid).status_code == 400


def test_busy_is_503(client, db, owner, artifacts, monkeypatch):
    from app.services import inference

    class Full:
        def acquire(self, blocking=True):
            return False

        def release(self):
            raise AssertionError("沒拿到名額卻放回去了")

    monkeypatch.setattr(inference, "_slots", Full())
    u, h = owner
    jid = _job(db, u, artifacts)
    assert _post(client, h, jid).status_code == 503


def test_rate_limit_is_per_user(client, db, owner, artifacts, monkeypatch):
    """ZH: 依使用者，不依 IP —— 平台在 Docker 後面，所有人的來源 IP 都一樣。"""
    from app.routers import jobs as jr
    monkeypatch.setattr(jr, "_TRY_MAX_PER_WINDOW", 1)
    u, h = owner
    jid = _job(db, u, artifacts)
    assert _post(client, h, jid).status_code == 200
    assert _post(client, h, jid).status_code == 429
    # ZH: 另一個人不受影響
    make_user(db, username="teach9", email="teach9@example.com", role="teacher")
    assert _post(client, auth_headers(client, "teach9"), jid).status_code == 200
