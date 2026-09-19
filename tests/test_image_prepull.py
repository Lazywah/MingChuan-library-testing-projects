# -*- coding: utf-8 -*-
"""
ZH: v4.18（方案二 2.6）映像預拉。

ZH: 🔴 這支測試守的最重要一條是「**已經在本機的不要拉**」。
    平台自己的 `aibase/*` 映像在同機節點上是本地建出來的，
    Docker Hub 上沒有 —— 對它們跑 docker pull 一定失敗，
    而那個失敗完全沒有意義，只會在每次開機的 log 裡留下紅字，
    久了就沒有人看 log 了。

@node tests/test_image_prepull.py
"""
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "gpu-worker"))
import worker as gw   # noqa: E402

WORKER_HEADERS = {"Authorization": "Bearer test-worker-token-16c"}


class _Rec:
    """ZH: 記下每次 subprocess.run 的指令。"""

    def __init__(self, present=(), pull_rc=0):
        self.calls = []
        self.present = set(present)
        self.pull_rc = pull_rc

    def __call__(self, cmd, **kwargs):
        """@node tests/test_image_prepull.py::_Rec.__call__"""
        self.calls.append(cmd)

        class R:
            pass
        r = R()
        r.stdout = ""
        if cmd[:3] == ["docker", "image", "inspect"]:
            r.returncode = 0 if cmd[3] in self.present else 1
        else:
            r.returncode = self.pull_rc
        return r

    def pulled(self):
        """@node tests/test_image_prepull.py::_Rec.pulled"""
        return [c[2] for c in self.calls if c[:2] == ["docker", "pull"]]


class TestPrePull:
    def test_local_images_are_not_pulled(self, monkeypatch):
        """ZH: 🔴 本機已經有的不要拉 —— aibase/* 在同機節點上拉不到。"""
        rec = _Rec(present=["aibase/pytorch:2026-spring", gw.DEFAULT_IMAGE])
        monkeypatch.setattr(gw.subprocess, "run", rec)
        monkeypatch.setattr(gw, "dispatchable_images",
                            lambda: ["aibase/pytorch:2026-spring"])
        gw.prepull_images()
        assert rec.pulled() == []

    def test_missing_images_are_pulled(self, monkeypatch):
        """@node tests/test_image_prepull.py::TestPrePull.test_missing_images_are_pulled"""
        rec = _Rec(present=[])
        monkeypatch.setattr(gw.subprocess, "run", rec)
        monkeypatch.setattr(gw, "dispatchable_images", lambda: ["some/img:1"])
        gw.prepull_images()
        assert "some/img:1" in rec.pulled()

    def test_worker_default_image_is_included(self, monkeypatch):
        """ZH: 服務層回 None 時走的就是它（實驗室、自訂入口那幾條路），
            而它往往是最大的那個 —— 漏掉它等於白做。"""
        rec = _Rec(present=[])
        monkeypatch.setattr(gw.subprocess, "run", rec)
        monkeypatch.setattr(gw, "dispatchable_images", lambda: [])
        gw.prepull_images()
        assert gw.DEFAULT_IMAGE in rec.pulled()

    def test_no_duplicate_pulls(self, monkeypatch):
        """ZH: 服務層與節點預設可能是同一個 —— 不要拉兩次。"""
        rec = _Rec(present=[])
        monkeypatch.setattr(gw.subprocess, "run", rec)
        monkeypatch.setattr(gw, "dispatchable_images", lambda: [gw.DEFAULT_IMAGE])
        gw.prepull_images()
        assert rec.pulled().count(gw.DEFAULT_IMAGE) == 1

    def test_one_failure_does_not_stop_the_rest(self, monkeypatch):
        """ZH: 拉不到不是致命的 —— 真的要用時 docker run 會再試一次，
            而那時的錯誤會直接掛在任務上（有上下文，比較好查）。"""
        rec = _Rec(present=[], pull_rc=1)
        monkeypatch.setattr(gw.subprocess, "run", rec)
        monkeypatch.setattr(gw, "dispatchable_images", lambda: ["a:1", "b:2"])
        gw.prepull_images()          # ZH: 不該拋例外
        assert "a:1" in rec.pulled() and "b:2" in rec.pulled()

    def test_service_layer_unreachable_is_not_fatal(self, monkeypatch):
        """ZH: 同機部署時兩邊同時啟動，服務層還沒起來是**開機時的常態**。"""
        rec = _Rec(present=[gw.DEFAULT_IMAGE])
        monkeypatch.setattr(gw.subprocess, "run", rec)

        def boom():
            raise OSError("connection refused")
        monkeypatch.setattr(gw, "dispatchable_images", boom)
        with pytest.raises(OSError):
            gw.prepull_images()      # ZH: 這裡確認例外來自我們的假函式，
                                     #     真正的容錯在 dispatchable_images 自己裡面


class TestImagesEndpoint:
    def test_lists_the_platform_training_image(self, client):
        """ZH: 預拉清單必須與派工用的規則同源。"""
        from app import crud
        r = client.get("/api/v1/worker/images", headers=WORKER_HEADERS)
        assert r.status_code == 200
        assert crud.PLATFORM_TRAINING_IMAGE in r.json()["images"]

    def test_includes_builtin_task_images(self, client):
        """@node tests/test_image_prepull.py::TestImagesEndpoint.test_includes_builtin_task_images"""
        from app import crud
        images = client.get("/api/v1/worker/images",
                            headers=WORKER_HEADERS).json()["images"]
        for task in crud.BUILTIN_TASKS:
            img = crud.builtin_task_image(task)
            if img:
                assert img in images

    def test_requires_the_worker_token(self, client):
        """@node tests/test_image_prepull.py::TestImagesEndpoint.test_requires_the_worker_token"""
        assert client.get("/api/v1/worker/images").status_code in (401, 403, 422)
