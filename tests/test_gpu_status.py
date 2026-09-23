# -*- coding: utf-8 -*-
"""
ZH: GPU 狀態頁的資料（v4.24）—— 「現在每張卡在做什麼」。

ZH: 🔴 這一族最重要的一條：**不可以洩漏是誰在用**。
    別人的卡只能說「訓練任務／程式實驗室」，自己的才帶名稱。
    判斷「要等還是改天」用不到對方是誰，知道了只會變成互相催促。

ZH: 其他守的：
      · 離線節點的卡片要標得出來（呼叫端靠 online 決定畫不畫 ——
        把最後一次心跳的「空閒」當成現況會騙人）
      · 實驗室佔的卡只算在**與服務層同機**的節點上（台北 30 台上線之後，
        不分節點的話每一台都會顯示同一張卡被實驗室佔著）
      · 訓練任務**不給** until（它沒有硬性期限，編一個出來比不說更糟）
      · 佇列只給數量與自己的位置

@node tests/test_gpu_status.py
"""
import json
from datetime import datetime, timedelta, timezone

import pytest

from app import crud, models
from conftest import make_user, auth_headers

GPUS = json.dumps([{"gpu_id": "0", "name": "NVIDIA GeForce RTX 5090",
                    "utilization": 3.0, "memory_used": 1024, "memory_total": 32607}])


def _node(db, node_id="gpu-node-01", *, online=True, co_located=1, enabled=1):
    """ZH: 一台有心跳的節點（預設在線、與服務層同機）。

    @node tests/test_gpu_status.py::_node
    """
    seen = datetime.now(timezone.utc) if online else datetime.now(timezone.utc) - timedelta(hours=2)
    db.add(models.WorkerHeartbeat(node_id=node_id, available_gpus='["0"]',
                                  gpus_detail=GPUS, last_seen=seen,
                                  is_online=1 if online else 0,
                                  pool_type="batch", shares_storage=co_located))
    db.add(models.GpuNode(node_id=node_id, display_name="測試節點", enabled=enabled))
    db.commit()


def _running_job(db, user, node_id="gpu-node-01", gpu=0, name="我的訓練"):
    """@node tests/test_gpu_status.py::_running_job"""
    j = models.TrainingJob(user_id=user.id, job_name=name, model_name="m",
                           status="running", gpu_server=node_id, gpu_id=gpu,
                           started_at=datetime.now(timezone.utc))
    db.add(j)
    db.commit()
    return j


def _lab_with_gpu(db, user, gpu=0):
    """@node tests/test_gpu_status.py::_lab_with_gpu"""
    row = models.LabSession(user_id=user.id, session_name="default",
                            volume_name="v", base_image="i", status="running",
                            gpu_index=gpu, started_at=datetime.now(timezone.utc))
    db.add(row)
    db.commit()
    return row


@pytest.fixture
def me(db):
    return make_user(db, username="gs1", email="gs1@example.com", role="student")


@pytest.fixture
def other(db):
    return make_user(db, username="gs2", email="gs2@example.com", role="student")


def _gpu0(d, node_id="gpu-node-01"):
    """@node tests/test_gpu_status.py::_gpu0"""
    node = next(n for n in d["nodes"] if n["node_id"] == node_id)
    return node, node["gpus"][0]


# ── 不洩漏是誰 ──────────────────────────────────────────────────────────
class TestItNeverSaysWho:
    def test_someone_elses_job_has_no_name(self, db, me, other):
        _node(db)
        _running_job(db, other, name="別人的祕密專案")
        d = crud.gpu_status(db, user_id=me.id)
        _, g = _gpu0(d)
        assert g["state"] == "job"
        assert g["mine"] is False
        assert g["label"] is None
        assert "祕密" not in json.dumps(d, ensure_ascii=False)

    def test_my_own_job_is_labelled(self, db, me):
        """ZH: **陽性對照** —— 自己的任務要認得出來，否則使用者看不出
           那張卡是不是自己佔著的。"""
        _node(db)
        _running_job(db, me, name="我的訓練")
        d = crud.gpu_status(db, user_id=me.id)
        _, g = _gpu0(d)
        assert g["mine"] is True and g["label"] == "我的訓練"

    def test_anonymous_caller_gets_no_labels(self, db, other):
        """ZH: 沒有 user_id（例如內部呼叫）時，一律當成「不是我的」。"""
        _node(db)
        _running_job(db, other, name="別人的")
        d = crud.gpu_status(db, user_id=None)
        _, g = _gpu0(d)
        assert g["mine"] is False and g["label"] is None

    def test_someone_elses_lab_has_no_name(self, db, me, other):
        _node(db)
        _lab_with_gpu(db, other)
        d = crud.gpu_status(db, user_id=me.id)
        _, g = _gpu0(d)
        assert g["state"] == "lab" and g["mine"] is False and g["label"] is None


# ── 狀態判斷 ────────────────────────────────────────────────────────────
class TestWhatTheCardIsDoing:
    def test_idle_when_nothing_is_running(self, db, me):
        _node(db)
        _, g = _gpu0(crud.gpu_status(db, user_id=me.id))
        assert g["state"] == "idle" and g["since"] is None and g["until"] is None

    def test_a_job_does_not_get_a_fake_deadline(self, db, me):
        """
        ZH: 🔴 批次訓練**沒有**硬性到期時間。給一個假的 until 的話，
            畫面會寫「預計 X 釋放」，而那個時間到了卡還在跑 ——
            使用者會以為平台壞了。
        """
        _node(db)
        _running_job(db, me)
        _, g = _gpu0(crud.gpu_status(db, user_id=me.id))
        assert g["state"] == "job"
        assert g["since"] is not None, "訓練至少要說得出從幾點開始"
        assert g["until"] is None

    def test_a_lab_reports_its_deadline(self, db, me):
        """ZH: 互動借用**有**最長時間（lab_gpu_max_minutes），那個要講。"""
        crud.set_settings(db, {"lab_gpu_max_minutes": 120})
        _node(db)
        _lab_with_gpu(db, me)
        _, g = _gpu0(crud.gpu_status(db, user_id=me.id))
        assert g["state"] == "lab" and g["until"] is not None

    def test_lab_wins_over_a_stale_running_job(self, db, me, other):
        """ZH: 互動借用是獨佔鎖 —— 同一張卡上還掛著 running 的任務列
           多半是沒收乾淨的舊資料，以實驗室為準。"""
        _node(db)
        _running_job(db, other)
        _lab_with_gpu(db, me)
        _, g = _gpu0(crud.gpu_status(db, user_id=me.id))
        assert g["state"] == "lab" and g["mine"] is True


# ── 節點 ────────────────────────────────────────────────────────────────
class TestNodes:
    def test_offline_node_is_marked_offline(self, db, me):
        """ZH: 🔴 離線節點回的是**最後一次看到的樣子**。
           呼叫端要靠 online 決定畫不畫，所以這個旗標一定要對。"""
        _node(db, online=False)
        d = crud.gpu_status(db, user_id=me.id)
        assert d["nodes"][0]["online"] is False

    def test_a_lab_does_not_occupy_a_remote_node(self, db, me):
        """
        ZH: 🔴 實驗室容器是**服務層**開的，它借的卡必然在那一台。
            不分節點的話，台北 30 台上線之後每一台都會顯示
            同一張卡被實驗室佔著 —— 而那三十個「忙碌」全是假的。
        """
        _node(db, node_id="taipei-01", co_located=0)
        _lab_with_gpu(db, me)
        d = crud.gpu_status(db, user_id=me.id)
        node = next(n for n in d["nodes"] if n["node_id"] == "taipei-01")
        assert node["gpus"][0]["state"] == "idle"

    def test_disabled_node_is_reported(self, db, me):
        _node(db, enabled=0)
        assert crud.gpu_status(db, user_id=me.id)["nodes"][0]["enabled"] is False


# ── 佇列 ────────────────────────────────────────────────────────────────
class TestQueue:
    def _pending(self, db, user, name):
        """@node tests/test_gpu_status.py::TestQueue._pending"""
        j = models.TrainingJob(user_id=user.id, job_name=name, model_name="m",
                               status="pending")
        db.add(j)
        db.commit()
        return j

    def test_counts_everyone_but_lists_only_mine(self, db, me, other):
        """ZH: 數量是大家的（他要知道前面有多少人），清單只有自己的。"""
        _node(db)
        self._pending(db, other, "別人的任務")
        self._pending(db, me, "我的任務")
        d = crud.gpu_status(db, user_id=me.id)
        assert d["queue"]["pending"] == 2
        assert [x["job_name"] for x in d["queue"]["mine"]] == ["我的任務"]

    def test_my_position_is_included(self, db, me):
        _node(db)
        j = self._pending(db, me, "我的任務")
        d = crud.gpu_status(db, user_id=me.id)
        assert d["queue"]["mine"][0]["position"] == crud.get_queue_position(db, j.id)


# ── 端點 ────────────────────────────────────────────────────────────────
class TestEndpoint:
    def test_requires_login(self, client, db):
        assert client.get("/api/v1/jobs/gpu-status").status_code in (401, 403)

    def test_is_not_swallowed_by_the_job_id_route(self, client, db, me):
        """
        ZH: 🔴 `/jobs/{job_id}` 會把 "gpu-status" 當成一個任務 id ——
            宣告順序反了的話這裡會回 404，而且錯誤訊息是「找不到任務」，
            沒有人會聯想到是路由順序。pool-availability 當初就踩過。
        """
        _node(db)
        h = auth_headers(client, "gs1", "password123")
        r = client.get("/api/v1/jobs/gpu-status", headers=h)
        assert r.status_code == 200, r.text
        assert set(r.json()) == {"pools", "nodes", "queue", "as_of"}
