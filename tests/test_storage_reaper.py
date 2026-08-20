# -*- coding: utf-8 -*-
"""
ZH: v3.6 —— GPU 主機共享儲存的回收。

ZH: 這支測試的重點**不是「有沒有刪掉」，是「有沒有刪錯」**。
    刪不掉的後果是磁碟慢慢滿（看得見、可補救）；
    刪錯的後果是把正在訓練的資料抽掉（訓練炸掉，而且完全查不出原因）。
    所以每一條「該刪」都配一條「絕對不能刪」。

ZH: 判準刻意做成**沒有狀態**的（見 worker.py 的說明）：
    touch 記號檔 + 天為單位的 TTL + 最近 N 小時內碰過的一律不刪。
    不做「使用中登記表」——那種簿記會在某條 early return 上漏掉。
"""
import os
import pathlib
import sys
import time

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "gpu-worker"))
import worker as gw   # noqa: E402

DAY = 86400
HOUR = 3600


# ──────────────────────────────────────────────────────────────────────────
# ZH: 工具
# ──────────────────────────────────────────────────────────────────────────

@pytest.fixture
def store(tmp_path, monkeypatch):
    """ZH: 一個假的共享儲存根目錄，並把回收器的旋鈕設成可預測的值。"""
    monkeypatch.setattr(gw, "HOST_STORAGE_MOUNT", str(tmp_path))
    monkeypatch.setattr(gw, "REAP_ENABLED", True)
    monkeypatch.setattr(gw, "DATASET_TTL_DAYS", 14.0)
    monkeypatch.setattr(gw, "OUTPUT_TTL_DAYS", 30.0)
    monkeypatch.setattr(gw, "REAP_MIN_AGE_HOURS", 24.0)
    monkeypatch.setattr(gw, "DATASET_CACHE_MAX_GB", 100.0)
    return tmp_path


def make_dataset(store, name, *, age_days, ready=True, size=1024):
    """ZH: 造一個資料集快取目錄，並把「最後使用時間」設成 age_days 天前。"""
    d = store / "datasets" / name
    (d / "cats").mkdir(parents=True)
    (d / "cats" / "a.jpg").write_bytes(b"x" * size)
    when = time.time() - age_days * DAY
    if ready:
        m = d / ".ready"
        m.write_text("ok", encoding="utf-8")
        os.utime(m, (when, when))
    os.utime(d, (when, when))
    return d


def make_output(store, job_id, *, age_days, size=1024):
    d = store / "outputs" / job_id
    d.mkdir(parents=True)
    (d / "model.pt").write_bytes(b"x" * size)
    when = time.time() - age_days * DAY
    os.utime(d, (when, when))
    return d


def make_tmp(store, name, *, age_days):
    d = store / "tmp"
    d.mkdir(parents=True, exist_ok=True)
    f = d / name
    f.write_bytes(b"x" * 1024)
    when = time.time() - age_days * DAY
    os.utime(f, (when, when))
    return f


# ──────────────────────────────────────────────────────────────────────────
# ZH: 一、資料集快取的 TTL
# ──────────────────────────────────────────────────────────────────────────

def test_old_dataset_is_reaped(store):
    d = make_dataset(store, "old", age_days=20)
    gw.reap_host_storage()
    assert not d.exists()


def test_recent_dataset_is_kept(store):
    """ZH: 陰性對照 —— 還在 TTL 內的不能刪。"""
    d = make_dataset(store, "fresh", age_days=3)
    gw.reap_host_storage()
    assert d.exists()


def test_dataset_used_today_is_never_reaped_even_if_the_dir_is_old(store):
    """ZH: 🔴 這條是整個設計的關鍵。

    ZH: 一包**天天在用**的資料，目錄本身是很久以前建的。
        如果判準看的是「目錄建立時間」，它會被當成 20 天沒用過而刪掉——
        而那正是最常用的那一包。判準必須看 `.ready` 的 mtime（＝最後一次被用到），
        而快取命中時 prepare_dataset 會去 touch 它。
    """
    d = make_dataset(store, "hot", age_days=60)
    (d / ".ready").touch()                       # 剛剛才用過
    gw.reap_host_storage()
    assert d.exists(), "天天在用的資料集被當成過期刪掉了"


def test_prepare_dataset_touches_the_marker_on_cache_hit(store, monkeypatch, tmp_path):
    """ZH: 上一條成立的前提：快取命中時**真的**會 touch。

    ZH: 沒有這條的話，上一條測試只證明了「我手動 touch 之後不會被刪」，
        不代表現場真的會 touch —— 那是兩件事。
    """
    d = make_dataset(store, "abc0123456789abc", age_days=60)
    old_mtime = (d / ".ready").stat().st_mtime

    # ZH: 讓 prepare_dataset 拿到一個 hash 剛好等於這個目錄名的假下載檔
    fake = tmp_path / "dl.zip"
    fake.write_bytes(b"whatever")
    monkeypatch.setattr(gw, "download_dataset", lambda job_id: fake)
    monkeypatch.setattr(gw, "file_sha256", lambda p: "abc0123456789abc" + "0" * 48)

    got = gw.prepare_dataset("job-1")
    assert got.endswith("abc0123456789abc")
    assert (d / ".ready").stat().st_mtime > old_mtime, "快取命中卻沒有更新最後使用時間"


def test_half_extracted_dir_without_marker_is_reaped_when_old(store):
    """ZH: 沒有 .ready ＝ 上次沒解完的殘骸。夠舊就該清掉。"""
    d = make_dataset(store, "broken", age_days=20, ready=False)
    gw.reap_host_storage()
    assert not d.exists()


def test_half_extracted_dir_being_written_right_now_is_kept(store):
    """ZH: 🔴 沒有 .ready 的目錄**也可能是此刻正在解壓的那一個**。

    ZH: 所以安全底線（REAP_MIN_AGE_HOURS）對它同樣適用——
        不能因為「沒有記號」就當成殘骸馬上刪。
    """
    d = make_dataset(store, "extracting-now", age_days=0, ready=False)
    gw.reap_host_storage()
    assert d.exists(), "正在解壓的目錄被刪了"


# ──────────────────────────────────────────────────────────────────────────
# ZH: 二、安全底線 —— 不論怎麼算，太新的一律不刪
# ──────────────────────────────────────────────────────────────────────────

def test_min_age_beats_ttl(store, monkeypatch):
    """ZH: 就算把 TTL 設成 0（＝全部過期），底線內的還是不能刪。

    ZH: 這是「設定被調錯」時的最後一道防線。有人把 DATASET_TTL_DAYS 設成 0
        不該讓正在跑的訓練當場失去資料。
    """
    monkeypatch.setattr(gw, "DATASET_TTL_DAYS", 0.0)
    fresh = make_dataset(store, "fresh", age_days=0)
    old = make_dataset(store, "old", age_days=5)
    gw.reap_host_storage()
    assert fresh.exists(), "TTL=0 時連剛剛在用的都被刪了"
    assert not old.exists()


def test_min_age_beats_the_size_cap(store, monkeypatch):
    """ZH: 容量爆了也不能刪剛剛在用的那一包 —— 底線優先於容量。"""
    monkeypatch.setattr(gw, "DATASET_CACHE_MAX_GB", 0.0)     # 一律超標
    fresh = make_dataset(store, "fresh", age_days=0, size=4096)
    old = make_dataset(store, "old", age_days=5, size=4096)
    gw.reap_host_storage()
    assert fresh.exists(), "容量淘汰刪到了剛剛在用的資料"
    assert not old.exists()


# ──────────────────────────────────────────────────────────────────────────
# ZH: 三、容量上限（LRU）
# ──────────────────────────────────────────────────────────────────────────

def test_size_cap_evicts_oldest_first(store, monkeypatch):
    """ZH: 超過上限時最舊的先走，較新的留著。"""
    monkeypatch.setattr(gw, "DATASET_TTL_DAYS", 999.0)       # TTL 不會動它們
    # ZH: 上限刻意設成「放得下一份、放不下兩份」。
    #     設成比一份還小的話，把兩份都刪掉才是正確行為——那就測不出「順序」了。
    monkeypatch.setattr(gw, "DATASET_CACHE_MAX_GB", 6000 / 1024 ** 3)
    oldest = make_dataset(store, "d1", age_days=10, size=4096)
    newer = make_dataset(store, "d2", age_days=2, size=4096)
    gw.reap_host_storage()
    assert not oldest.exists()
    assert newer.exists(), "容量淘汰不是從最舊的開始"


def test_size_cap_does_nothing_when_under(store, monkeypatch):
    """ZH: 陰性對照 —— 沒超標就一個都不能動。"""
    monkeypatch.setattr(gw, "DATASET_TTL_DAYS", 999.0)
    a = make_dataset(store, "d1", age_days=10)
    b = make_dataset(store, "d2", age_days=2)
    gw.reap_host_storage()
    assert a.exists() and b.exists()


# ──────────────────────────────────────────────────────────────────────────
# ZH: 四、訓練產出與暫存檔
# ──────────────────────────────────────────────────────────────────────────

def test_old_output_is_reaped(store):
    d = make_output(store, "job-old", age_days=40)
    gw.reap_host_storage()
    assert not d.exists()


def test_recent_output_is_kept(store):
    """ZH: 陰性對照。產出這一版還不能從畫面下載，保留期刻意長。"""
    d = make_output(store, "job-new", age_days=10)
    gw.reap_host_storage()
    assert d.exists()


def test_stale_temp_file_is_reaped(store):
    f = make_tmp(store, "ds_abc.zip", age_days=3)
    gw.reap_host_storage()
    assert not f.exists()


def test_temp_file_being_downloaded_right_now_is_kept(store):
    """ZH: 🔴 正在下載的暫存檔不能刪——刪掉會讓那張任務憑空失敗。"""
    f = make_tmp(store, "ds_now.zip", age_days=0)
    gw.reap_host_storage()
    assert f.exists()


# ──────────────────────────────────────────────────────────────────────────
# ZH: 五、不可以把 worker 拖垮
# ──────────────────────────────────────────────────────────────────────────

def test_disabled_switch_does_nothing(store, monkeypatch):
    monkeypatch.setattr(gw, "REAP_ENABLED", False)
    d = make_dataset(store, "old", age_days=999)
    gw.reap_host_storage()
    assert d.exists()


def test_missing_root_is_not_an_error(tmp_path, monkeypatch):
    """ZH: 共享儲存還沒建立時（第一次開機）不該炸。"""
    monkeypatch.setattr(gw, "HOST_STORAGE_MOUNT", str(tmp_path / "nope"))
    monkeypatch.setattr(gw, "REAP_ENABLED", True)
    assert gw.reap_host_storage()["datasets_removed"] == 0


def test_reap_safely_swallows_exceptions(monkeypatch):
    """ZH: 回收失敗**絕對不能**拖垮輪詢迴圈。

    ZH: 「worker 不再領工」比「磁碟滿了」更難查——前者沒有任何症狀，
        使用者只會看到任務永遠排隊。
    """
    def boom():
        raise RuntimeError("disk on fire")
    monkeypatch.setattr(gw, "reap_host_storage", boom)
    gw.reap_safely()          # ZH: 不拋例外就是通過
