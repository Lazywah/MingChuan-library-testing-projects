# -*- coding: utf-8 -*-
"""
ZH: v3.6 —— 程式實驗室（Notebook）模式的任務只能在「與服務層同機」的 GPU 節點上跑。

ZH: 要防的是什麼：`inline_code` 的腳本讀使用者的 `home_<uid>` Docker volume，
    而 Docker volume 是**本機**的。派給別台機器上的 worker 時，
    `docker run -v home_<uid>:/home/coder` 會在**那台**自動建立一個**空的**同名 volume。
    不報錯、不警告、訓練跑完、結果沒有意義。這裡把它變成明確的失敗。

ZH: 每一條「應該被擋」的測試都配一條**陰性對照**（把同機旗標打開，同一張單就過），
    否則「擋住了」與「這個測試根本沒送出任何東西」在結果上長得一樣。
"""
import pytest

from conftest import make_user, auth_headers

WORKER_AUTH = {"Authorization": "Bearer test-worker-token-16c"}


# ──────────────────────────────────────────────────────────────────────────
# ZH: 工具
# ──────────────────────────────────────────────────────────────────────────

def _heartbeat(client, node_id="gpu-node-01", shares=None, pool="batch"):
    """ZH: 送一次心跳。shares=None 代表**完全不帶這個欄位**（模擬舊版 worker）。"""
    body = {"node_id": node_id, "available_gpus": ["0"], "pool_type": pool}
    if shares is not None:
        body["shares_service_storage"] = shares
    r = client.post("/api/v1/worker/heartbeat", json=body, headers=WORKER_AUTH)
    assert r.status_code == 200, r.text
    return r


def _take(client, node_id="gpu-node-01", shares=None, pool="batch"):
    body = {"node_id": node_id, "available_gpus": ["0"], "pool_type": pool}
    if shares is not None:
        body["shares_service_storage"] = shares
    r = client.post("/api/v1/worker/take", json=body, headers=WORKER_AUTH)
    assert r.status_code == 200, r.text
    return r.json()["job"]


def _submit(client, headers, inline=True, name="t"):
    body = {"job_name": name, "model_name": "resnet18", "config": {"epochs": 1}}
    if inline:
        body["inline_code"] = "echo hello"
    return client.post("/api/v1/jobs", json=body, headers=headers)


@pytest.fixture
def user_headers(client, db):
    make_user(db)
    return auth_headers(client)


# ──────────────────────────────────────────────────────────────────────────
# ZH: 一、送單就擋（不然任務會永遠 pending —— 「排隊中」是另一種沉默失敗）
# ──────────────────────────────────────────────────────────────────────────

def test_lab_job_rejected_when_no_colocated_node(client, db, user_headers):
    """ZH: 線上只有不同機的節點 → 實驗室任務直接 503，而不是收下來排隊。"""
    _heartbeat(client, shares=False)
    r = _submit(client, user_headers)
    assert r.status_code == 503, r.text


def test_lab_job_accepted_when_colocated_node_online(client, db, user_headers):
    """ZH: 陰性對照 —— 同一張單，節點宣告同機就會被收下。

    ZH: 沒有這條的話，上一條測試在「送單根本壞掉」時也會綠。
    """
    _heartbeat(client, shares=True)
    r = _submit(client, user_headers)
    assert r.status_code == 201, r.text


def test_non_lab_job_unaffected_by_colocation(client, db, user_headers):
    """ZH: 沒有 inline_code 的一般任務不受影響 —— 閘門不可以擴大到全部任務。"""
    _heartbeat(client, shares=False)
    r = _submit(client, user_headers, inline=False)
    assert r.status_code == 201, r.text


def test_lab_job_rejected_when_no_node_at_all(client, db, user_headers):
    """ZH: 完全沒有節點在線時也擋 —— 空叢集不該讓它排到天荒地老。"""
    r = _submit(client, user_headers)
    assert r.status_code == 503, r.text


def test_rejected_lab_job_does_not_consume_quota(client, db, user_headers):
    """ZH: 被擋下的單不該扣 Token。檢查點刻意放在扣額之前。"""
    from app import crud
    _heartbeat(client, shares=False)
    before = crud.get_token_usage(db, user_id=make_user_id(db))
    used_before = before.tokens_used if before else 0
    assert _submit(client, user_headers).status_code == 503
    db.expire_all()
    after = crud.get_token_usage(db, user_id=make_user_id(db))
    used_after = after.tokens_used if after else 0
    assert used_after == used_before


def make_user_id(db):
    from app import models
    return db.query(models.User).filter(models.User.username == "testuser").first().id


# ──────────────────────────────────────────────────────────────────────────
# ZH: 二、派工閘門（送單當下有同機節點，但來領的是別台）
# ──────────────────────────────────────────────────────────────────────────

def test_remote_node_does_not_claim_lab_job(client, db, user_headers):
    """ZH: 單子收下了（有同機節點在線），但來領的節點宣告不同機 → 不給它。"""
    _heartbeat(client, node_id="local", shares=True)
    assert _submit(client, user_headers).status_code == 201

    assert _take(client, node_id="remote", shares=False) is None


def test_colocated_node_does_claim_lab_job(client, db, user_headers):
    """ZH: 陰性對照 —— 同一張單，換同機節點來領就領得到。"""
    _heartbeat(client, node_id="local", shares=True)
    assert _submit(client, user_headers).status_code == 201

    job = _take(client, node_id="local", shares=True)
    assert job is not None
    assert job["inline_code"] == "echo hello"


def test_legacy_worker_without_the_field_is_treated_as_remote(client, db, user_headers):
    """ZH: 舊版 worker 完全不送這個欄位 → 當成不同機（安全的一邊），不給它實驗室任務。

    ZH: 這是「缺值 ≠ 預設值」的另一面：這裡缺值**必須**落在保守的那一邊。
    """
    _heartbeat(client, node_id="local", shares=True)
    assert _submit(client, user_headers).status_code == 201

    assert _take(client, node_id="legacy", shares=None) is None


def test_remote_node_still_claims_normal_jobs(client, db, user_headers):
    """ZH: 不同機的節點照常領一般任務 —— 閘門只針對實驗室任務。"""
    _heartbeat(client, node_id="local", shares=True)
    assert _submit(client, user_headers, inline=False).status_code == 201

    job = _take(client, node_id="remote", shares=False)
    assert job is not None


# ──────────────────────────────────────────────────────────────────────────
# ZH: 三、掛載：不同機時不可以掛那個空 volume
# ──────────────────────────────────────────────────────────────────────────

def test_home_volume_only_mounted_when_colocated(client, db, user_headers):
    """ZH: 一般任務派給不同機節點時，回傳的 volume_mounts 不含 home_<uid>。

    ZH: 掛一個空 volume 比缺少掛載更難查——腳本會以為「資料夾就是空的」。
    """
    _heartbeat(client, node_id="local", shares=True)
    assert _submit(client, user_headers, inline=False).status_code == 201

    job = _take(client, node_id="remote", shares=False)
    names = [m["name"] for m in (job.get("volume_mounts") or [])]
    assert not any(n.startswith("home_") for n in names), names


def test_home_volume_mounted_when_colocated(client, db, user_headers):
    """ZH: 陰性對照 —— 同機時 home_<uid> 有掛上去，**而且是對的那一個名字**。

    ZH: 🔴 這條原本只斷言 `startswith("home_")` —— 對的名字與錯的名字都會過，
        於是下面那個缺陷在它眼皮底下活了下來。斷言改成完整比對。
    """
    import sys, pathlib
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "job-scheduler"))
    from app.services import lab_manager
    from app import models

    _heartbeat(client, node_id="local", shares=True)
    assert _submit(client, user_headers, inline=False).status_code == 201

    uid = db.query(models.User).filter_by(username="testuser").first().id
    job = _take(client, node_id="local", shares=True)
    names = [m["name"] for m in (job.get("volume_mounts") or [])]
    assert lab_manager.volume_name_for(uid) in names, (names, uid)


def test_mounted_home_volume_is_the_one_the_lab_actually_uses(client, db, user_headers):
    """ZH: 🔴 派工掛的 volume **必須就是實驗室真正在用的那一個**。

    ZH: 真實發生過的缺陷。`routers/worker.py` 自己寫了 `f"home_{user_id}"`，
        而 lab_manager 是 `home_<uid 的連字號換成底線>`：

            lab_manager  → home_dfea61fa_0d76_4390_af93_4c9df5606d6f
            worker       → home_dfea61fa-0d76-4390-af93-4c9df5606d6f

        兩個是**不同的 volume**，docker 遇到不存在的名字會**自動建一個空的**。
        不報錯、資料不在、訓練跑完、結果沒有意義 —— 正是同機閘門要防的那種沉默失敗，
        只是這次原因不是跨機而是名字對不上。

        查證方式（volume 標籤 + 內容量）：
            lab_manager 建的帶 `aibase.purpose=home`，399 MB / 3718 檔（真資料）
            自動建出來的沒有標籤，              84 KB / 7 檔（映像檔預設內容）
        當時有一位真實使用者兩種都有。

    ZH: 斷言寫成「等於 lab_manager 的輸出」而不是寫死字串 ——
        以後改命名規則時兩邊會一起動，這條測試不會變成過時的複製品。
    """
    import sys, pathlib
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "job-scheduler"))
    from app.services import lab_manager
    from app import models

    _heartbeat(client, node_id="local", shares=True)
    assert _submit(client, user_headers, inline=False).status_code == 201

    uid = db.query(models.User).filter_by(username="testuser").first().id
    job = _take(client, node_id="local", shares=True)

    home = [m for m in (job.get("volume_mounts") or []) if m["name"].startswith("home_")]
    assert len(home) == 1, job.get("volume_mounts")
    assert home[0]["name"] == lab_manager.volume_name_for(uid)
    # ZH: 明確擋掉那個錯的寫法（uid 是 UUID，一定含連字號）
    assert home[0]["name"] != f"home_{uid}", "又寫回連字號版了"
    assert "-" not in home[0]["name"][len("home_"):], home[0]["name"]


# ──────────────────────────────────────────────────────────────────────────
# ZH: 四、心跳把宣告寫進 DB（不是只在單次 take 裡有效）
# ──────────────────────────────────────────────────────────────────────────

def test_heartbeat_persists_the_flag(client, db):
    from app import models
    _heartbeat(client, node_id="n1", shares=True)
    n = db.query(models.WorkerHeartbeat).filter_by(node_id="n1").first()
    assert n.shares_storage == 1


def test_heartbeat_overwrites_the_flag_on_downgrade(client, db):
    """ZH: 每次心跳都覆寫，**不保留舊值**。

    ZH: 刻意如此：一台原本同機、後來被搬到別台又降回舊版 worker 的節點，
        若「沒說就沿用」會繼續自稱同機——那正是這整件事要防的情況。
    """
    from app import models
    _heartbeat(client, node_id="n1", shares=True)
    _heartbeat(client, node_id="n1", shares=None)      # 舊版 worker，不帶欄位
    db.expire_all()
    n = db.query(models.WorkerHeartbeat).filter_by(node_id="n1").first()
    assert n.shares_storage == 0
