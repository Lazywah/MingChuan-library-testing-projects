# -*- coding: utf-8 -*-
"""
ZH: 程式實驗室的 per-user 網路（v4.24，原 v2.2 主項目）。

ZH: 🔴 來歷：所有 lab 容器原本共用 `ai-platform-net`，於是學生 A 可以從自己的
    容器連到學生 B 的 code-server（`curl http://cs-<對方 uuid>:8080`）。
    威脅不高（要知道對方的 uuid 且刻意為之），但它是真的。

ZH: 這一族守的三件事：
      1. **預設是關的** —— 開啟會改變容器的網路拓撲，要能分批驗證
      2. 開啟時每個人拿到**自己的**網路（兩個人不會共用）
      3. 🔴 平台容器要被連進去，而且服務層要帶 alias `job-scheduler` ——
         少了它，實驗室開得起來但 Run on GPU 與心跳全部失敗，
         而且只在隔離開啟後才發生（最難聯想的那種）

ZH: ⚠ 這裡**不碰真的 Docker**（測試機不一定有）。用假的 client 驗
    「我們下了哪些指令」；真的連通性由 docs/08 的人工驗證步驟負責。

@node tests/test_lab_network_isolation.py
"""
import pytest
from docker.errors import APIError, NotFound

from app import crud
from app.services import network_manager as nm


class _FakeNet:
    def __init__(self, name, containers=None):
        self.name = name
        self.attrs = {"Containers": {str(i): {"Name": n}
                                     for i, n in enumerate(containers or [])}}
        self.connected = []
        self.disconnected = []
        self.removed = False

    def reload(self):
        """@node tests/test_lab_network_isolation.py::_FakeNet.reload"""

    def connect(self, name, aliases=None):
        """@node tests/test_lab_network_isolation.py::_FakeNet.connect"""
        self.connected.append((name, tuple(aliases or ())))
        self.attrs["Containers"][name] = {"Name": name}

    def disconnect(self, name, force=False):
        """@node tests/test_lab_network_isolation.py::_FakeNet.disconnect"""
        self.disconnected.append(name)

    def remove(self):
        """@node tests/test_lab_network_isolation.py::_FakeNet.remove"""
        self.removed = True


class _FakeNetworks:
    def __init__(self, existing=None, create_error=None):
        self.nets = dict(existing or {})
        self.created = []
        self.create_error = create_error

    def get(self, name):
        """@node tests/test_lab_network_isolation.py::_FakeNetworks.get"""
        if name not in self.nets:
            raise NotFound(name)
        return self.nets[name]

    def create(self, name, driver=None, labels=None):
        """@node tests/test_lab_network_isolation.py::_FakeNetworks.create"""
        if self.create_error:
            raise self.create_error
        self.created.append((name, driver, labels))
        self.nets[name] = _FakeNet(name)
        return self.nets[name]


class _FakeClient:
    def __init__(self, networks):
        self.networks = networks


# ── 名字 ────────────────────────────────────────────────────────────────
def test_each_user_gets_a_different_network_name():
    a = nm.network_name("11111111-2222-3333-4444-555555555555")
    b = nm.network_name("99999999-8888-7777-6666-555555555555")
    assert a != b
    assert a.startswith(nm.NET_PREFIX)


# ── 建立與連線 ──────────────────────────────────────────────────────────
class TestEnsureNetwork:
    def test_creates_the_network_once(self):
        nets = _FakeNetworks()
        c = _FakeClient(nets)
        name = nm.ensure_network(c, "u1")
        again = nm.ensure_network(c, "u1")
        assert name == again
        assert len(nets.created) == 1, "同一個人被建了兩次網路"

    def test_the_scheduler_is_connected_with_its_compose_alias(self):
        """
        ZH: 🔴 compose 的服務名只在 compose 建的網路上有效。手動 connect 進來時
            預設只有容器名（ai-platform-scheduler）解得到，而容器裡的 extension
            打的是 `http://job-scheduler:8000`。少了這個 alias 的症狀是
            「實驗室開得起來、但送訓練與心跳全部失敗」。
        """
        nets = _FakeNetworks()
        c = _FakeClient(nets)
        nm.ensure_network(c, "u1")
        net = nets.nets[nm.network_name("u1")]
        by_name = dict((n, a) for n, a in net.connected)
        assert "ai-platform-nginx" in by_name, "nginx 沒連進去 → /code/ 會 502"
        assert "job-scheduler" in by_name["ai-platform-scheduler"]

    def test_already_connected_peers_are_not_reconnected(self):
        existing = _FakeNet(nm.network_name("u1"),
                            containers=["ai-platform-nginx", "ai-platform-scheduler"])
        c = _FakeClient(_FakeNetworks({existing.name: existing}))
        nm.ensure_network(c, "u1")
        assert existing.connected == []

    def test_a_missing_peer_does_not_break_starting_a_lab(self):
        """ZH: 連不上要記 error，但不可以讓實驗室開不起來 ——
           「少一層隔離」比「今天不能寫程式」輕。"""
        net = _FakeNet(nm.network_name("u1"))

        def _boom(name, aliases=None):
            """@node tests/test_lab_network_isolation.py::TestEnsureNetwork.<nested>._boom"""
            raise NotFound(name)

        net.connect = _boom
        c = _FakeClient(_FakeNetworks({net.name: net}))
        assert nm.ensure_network(c, "u1") == net.name      # 不該拋

    def test_address_pool_exhaustion_says_what_it_means(self):
        """
        ZH: 🔴 Docker 的原文是 "could not find an available IP address pool"，
            看起來像 Docker 壞了；實際上是「同時開著的實驗室太多」。
            兩者的處理完全不同，所以要翻譯成人話。
        """
        err = APIError("could not find an available IP address pool")
        c = _FakeClient(_FakeNetworks(create_error=err))
        with pytest.raises(RuntimeError) as e:
            nm.ensure_network(c, "u1")
        assert "位址池" in str(e.value) and "實驗室" in str(e.value)


# ── 收網路 ──────────────────────────────────────────────────────────────
class TestRemoveNetwork:
    def test_removes_when_only_platform_peers_remain(self):
        net = _FakeNet(nm.network_name("u1"),
                       containers=["ai-platform-nginx", "ai-platform-scheduler"])
        c = _FakeClient(_FakeNetworks({net.name: net}))
        assert nm.remove_network(c, "u1") is True
        assert net.removed is True
        assert set(net.disconnected) == {"ai-platform-nginx", "ai-platform-scheduler"}

    def test_keeps_the_network_while_another_lab_is_open(self):
        """ZH: 🔴 多份存檔的人可能還開著另一份 —— 收掉的話那一份會斷線。"""
        net = _FakeNet(nm.network_name("u1"),
                       containers=["ai-platform-nginx", "cs-u1-project"])
        c = _FakeClient(_FakeNetworks({net.name: net}))
        assert nm.remove_network(c, "u1") is False
        assert net.removed is False

    def test_missing_network_is_not_an_error(self):
        c = _FakeClient(_FakeNetworks())
        assert nm.remove_network(c, "u1") is False


# ── 閘門 ────────────────────────────────────────────────────────────────
class TestTheSwitch:
    def test_it_is_off_by_default(self, db):
        """
        ZH: 🔴 預設關 —— 這會改變容器的網路拓撲，而已經開著的實驗室不受影響
            （只影響之後啟動的）。要能分批驗證，不能一翻就全站生效。
        """
        assert str(crud.get_setting(db, "lab_network_isolation")) == "0"

    def test_it_is_a_zero_or_one_knob(self, db):
        crud.set_settings(db, {"lab_network_isolation": 1})
        assert str(crud.get_setting(db, "lab_network_isolation")) == "1"
        crud.set_settings(db, {"lab_network_isolation": 0})
        assert str(crud.get_setting(db, "lab_network_isolation")) == "0"
