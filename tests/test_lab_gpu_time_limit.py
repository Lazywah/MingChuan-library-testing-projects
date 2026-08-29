"""
ZH: Lab GPU 最長借用時間（v3.9）。

ZH: 桃園目前只有一張卡，而程式實驗室會**獨佔**它 —— 一個人開著不關，
    整個校區就沒有人能訓練。這條限制是資源分配，不是使用時長政策。

ZH: 🔴 因此它**不分角色**，與 scheduler_policy 的 `hard_limit_min` 是兩回事：
    那個 teacher/admin 是 None（無上限）。少了這個區別，
    管理員一開實驗室就等於把卡永久鎖住 —— 而且完全看不出來。
"""
import sys
import os
from datetime import datetime, timezone, timedelta

import pytest
from conftest import make_user

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "job-scheduler"))

from app import crud, models  # noqa: E402
from app.services import lab_manager as L  # noqa: E402


def _session(db, user, *, gpu, minutes_ago, name="default"):
    row = models.LabSession(
        user_id=user.id, session_name=name, status="running",
        volume_name="home_" + user.username, base_image="img",
        gpu_index=gpu,
        started_at=datetime.now(timezone.utc) - timedelta(minutes=minutes_ago),
        last_activity=datetime.now(timezone.utc))
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@pytest.fixture
def stop_calls(monkeypatch):
    """ZH: 攔下 stop_session —— 這組測試不碰 Docker。"""
    calls = []
    monkeypatch.setattr(L, "stop_session",
                        lambda db, uid, reason=None, session=None: calls.append((uid, reason, session)))
    # ZH: reconcile 會去問 Docker，這裡一律當成「沒有異常」。
    monkeypatch.setattr(L, "reconcile_session", lambda db, s: False)
    return calls


# ══════════════════════════════════════════════════════════════════════════
# ZH: 一、到期就收回
# ══════════════════════════════════════════════════════════════════════════

def test_gpu_session_is_stopped_after_the_limit(db, stop_calls):
    u = make_user(db, username="g1", email="g1@example.com")
    crud.set_system_config(db, "lab_gpu_max_minutes", "120")
    _session(db, u, gpu=0, minutes_ago=121)
    L.scan_and_evict(db)
    assert [c[1] for c in stop_calls] == ["gpu_time_limit"]


def test_gpu_session_within_the_limit_is_left_alone(db, stop_calls):
    """ZH: 陽性對照 —— 沒到期不能踢。只測「會踢」的話，永遠踢也會過。"""
    u = make_user(db, username="g2", email="g2@example.com")
    crud.set_system_config(db, "lab_gpu_max_minutes", "120")
    _session(db, u, gpu=0, minutes_ago=60)
    L.scan_and_evict(db)
    assert stop_calls == []


def test_cpu_session_is_not_affected(db, stop_calls):
    """
    ZH: 沒借 GPU 的實驗室不受這條限制 —— 它沒有佔用稀缺資源。
        （它仍受角色的 hard_limit_min 管，那是另一回事。）
    """
    u = make_user(db, username="g3", email="g3@example.com")
    crud.set_system_config(db, "lab_gpu_max_minutes", "120")
    crud.set_system_config(db, "lab_gpu_max_minutes", "120")
    _session(db, u, gpu=None, minutes_ago=600)
    L.scan_and_evict(db)
    assert [c for c in stop_calls if c[1] == "gpu_time_limit"] == []


def test_zero_means_no_limit(db, stop_calls):
    u = make_user(db, username="g4", email="g4@example.com")
    crud.set_system_config(db, "lab_gpu_max_minutes", "0")
    _session(db, u, gpu=0, minutes_ago=9999)
    L.scan_and_evict(db)
    assert [c for c in stop_calls if c[1] == "gpu_time_limit"] == []


def test_admin_is_not_exempt(db, stop_calls):
    """
    ZH: 🔴 這條的重點。角色的 hard_limit_min 對 admin 是 None（無上限），
        但 GPU 是**稀缺資源**：管理員佔著不放，別人一樣訓練不了。
        沒有這一條的話，最容易長期佔卡的正好是最不會被踢的那個人。
    """
    a = make_user(db, username="g5", email="g5@example.com", role="admin")
    crud.set_system_config(db, "lab_gpu_max_minutes", "120")
    _session(db, a, gpu=0, minutes_ago=200)
    L.scan_and_evict(db)
    assert [c[1] for c in stop_calls] == ["gpu_time_limit"]


def test_the_right_save_is_stopped(db, stop_calls):
    """
    ZH: 一定要指名存檔。不帶的話會關掉 default，而超時的那一份繼續佔著卡 ——
        日誌還會說已經關了（既有註解在 scan_and_evict 裡記過這個坑）。
    """
    u = make_user(db, username="g6", email="g6@example.com")
    crud.set_system_config(db, "lab_gpu_max_minutes", "120")
    _session(db, u, gpu=0, minutes_ago=200, name="我的實驗")
    L.scan_and_evict(db)
    assert stop_calls[0][2] == "我的實驗"


# ══════════════════════════════════════════════════════════════════════════
# ZH: 二、到期時刻（畫面與容器內提示共用同一個計算）
# ══════════════════════════════════════════════════════════════════════════

def test_deadline_is_start_plus_limit(db):
    u = make_user(db, username="g7", email="g7@example.com")
    crud.set_system_config(db, "lab_gpu_max_minutes", "120")
    row = _session(db, u, gpu=0, minutes_ago=30)
    d = L.gpu_deadline(db, row)
    started = row.started_at.replace(tzinfo=timezone.utc)
    assert d == started + timedelta(minutes=120)


def test_no_deadline_for_cpu_or_unlimited(db):
    u = make_user(db, username="g8", email="g8@example.com")
    crud.set_system_config(db, "lab_gpu_max_minutes", "120")
    assert L.gpu_deadline(db, _session(db, u, gpu=None, minutes_ago=1)) is None

    u2 = make_user(db, username="g9", email="g9@example.com")
    crud.set_system_config(db, "lab_gpu_max_minutes", "0")
    assert L.gpu_deadline(db, _session(db, u2, gpu=0, minutes_ago=1)) is None


def test_unreadable_setting_means_no_limit_not_instant_eviction(db, monkeypatch, stop_calls):
    """
    ZH: 🔴 設定讀不到時**寧可不踢人**。
        回一個小數字或 0 當「立刻到期」的話，一次設定故障會把全校的
        GPU 實驗室同時關掉 —— 那比「暫時沒有上限」嚴重得多。
    """
    u = make_user(db, username="g10", email="g10@example.com")
    def boom(*a, **k):
        raise RuntimeError("設定讀不到")
    monkeypatch.setattr(crud, "get_setting", boom)
    _session(db, u, gpu=0, minutes_ago=9999)
    L.scan_and_evict(db)
    assert [c for c in stop_calls if c[1] == "gpu_time_limit"] == []
