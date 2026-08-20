# -*- coding: utf-8 -*-
"""
ZH: v3.6 —— 資料集管理（列表／刪除／重用）與所有權。

ZH: 為什麼這頁是必要的而不只是方便：每人 2 GB 配額，而**原本沒有任何刪除的方法**。
    使用者一旦傳滿就永遠卡住——上傳會 413，而他做不了任何事。

ZH: 順帶補一個所有權的洞（先寫測試證明它是紅的，再修）：
    `POST /jobs` 收下客戶端送來的 `dataset_path`，**完全沒有檢查那是不是他自己的**。
"""
import io
import pathlib
import zipfile

import pytest

from conftest import make_user, auth_headers

WORKER_AUTH = {"Authorization": "Bearer test-worker-token-16c"}


@pytest.fixture(autouse=True)
def dataset_dir(monkeypatch):
    """ZH: 把資料集根目錄指到一個 **POSIX 形狀**的暫存路徑。

    ZH: 不能用 pytest 的 tmp_path —— Windows 的暫存路徑帶冒號，
        而 `JobCreate.dataset_path` 的字元白名單會直接 422。
        那樣測出來的紅是「路徑格式不合」，不是「所有權沒檢查」——
        用錯誤的理由變紅的測試，等於沒有測到。
    """
    import shutil
    import uuid as _uuid
    from app.routers import datasets as ds
    from app.routers import worker as wr
    root = f"/tmp/ds_{_uuid.uuid4().hex[:8]}"
    monkeypatch.setattr(ds, "DATASET_DIR", root)
    monkeypatch.setattr(wr, "DATASET_ROOT", root)
    yield pathlib.Path(root)
    shutil.rmtree(root, ignore_errors=True)


def _zip(names=("cats/a.jpg", "dogs/b.jpg")):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for n in names:
            zf.writestr(n, "x" * 100)
    return buf.getvalue()


def _upload(client, headers, name="我的圖片.zip"):
    return client.post("/api/v1/datasets/upload", headers=headers,
                       files={"file": (name, _zip(), "application/zip")})


def _heartbeat(client):
    client.post("/api/v1/worker/heartbeat",
                json={"node_id": "n1", "available_gpus": ["0"], "pool_type": "batch",
                      "shares_service_storage": True}, headers=WORKER_AUTH)


@pytest.fixture
def user_headers(client, db):
    make_user(db)
    return auth_headers(client)


# ──────────────────────────────────────────────────────────────────────────
# ZH: 一、所有權 —— 別人的資料集不能拿來用
# ──────────────────────────────────────────────────────────────────────────

def test_cannot_submit_a_job_with_another_users_dataset(client, db):
    """ZH: 🔴 送單時 `dataset_path` 原本**完全沒有檢查是不是自己的**。

    ZH: 攻擊面不大（兩層 UUID 都不好猜），但路徑是會流出去的——上傳回應裡有，
        管理者之間轉貼也有。而且「沒有檢查」本身就是一個會被後續改動放大的洞。
    """
    make_user(db, username="alice", email="a@example.com")
    make_user(db, username="bob", email="b@example.com")
    alice, bob = auth_headers(client, "alice"), auth_headers(client, "bob")

    path = _upload(client, alice).json()["dataset_path"]

    _heartbeat(client)
    r = client.post("/api/v1/jobs", headers=bob,
                    json={"job_name": "steal", "model_name": "resnet18",
                          "dataset_path": path, "config": {"epochs": 1}})
    assert r.status_code == 403, f"別人的資料集被收下了：{r.status_code} {r.text[:200]}"


def test_can_submit_a_job_with_my_own_dataset(client, db, user_headers):
    """ZH: 陰性對照 —— 自己的照常可以用。

    ZH: 沒有這條的話，上一條在「送單整個壞掉」時也會綠。
    """
    path = _upload(client, user_headers).json()["dataset_path"]
    _heartbeat(client)
    r = client.post("/api/v1/jobs", headers=user_headers,
                    json={"job_name": "mine", "model_name": "resnet18",
                          "dataset_path": path, "config": {"epochs": 1}})
    assert r.status_code == 201, r.text


def test_a_made_up_path_is_refused(client, db, user_headers):
    """ZH: 憑空編一個路徑也不行（就算它長得像在自己的目錄底下）。"""
    _heartbeat(client)
    r = client.post("/api/v1/jobs", headers=user_headers,
                    json={"job_name": "x", "model_name": "resnet18",
                          "dataset_path": "/data/datasets/whoever/nope.zip",
                          "config": {"epochs": 1}})
    assert r.status_code in (403, 404), r.text


# ──────────────────────────────────────────────────────────────────────────
# ZH: 二、列表 —— 沒有紀錄就沒有列表，而原始檔名只存在這裡
# ──────────────────────────────────────────────────────────────────────────

def test_list_shows_the_original_cjk_name(client, db, user_headers):
    """ZH: 磁碟上的檔名已經被清成 ASCII（防命令注入），
       「我的圖片.zip」在磁碟上是 `0fad32ff_dataset.zip`。
       **原始檔名只存在 DB 裡**——沒有這張表，列表就只能顯示一串亂碼。
    """
    _upload(client, user_headers, name="我的貓狗圖片.zip")
    body = client.get("/api/v1/datasets", headers=user_headers).json()
    assert [d["name"] for d in body["datasets"]] == ["我的貓狗圖片.zip"], body


def test_list_only_shows_my_own(client, db):
    make_user(db, username="alice", email="a@example.com")
    make_user(db, username="bob", email="b@example.com")
    alice, bob = auth_headers(client, "alice"), auth_headers(client, "bob")
    _upload(client, alice, "alice.zip")
    _upload(client, bob, "bob.zip")

    assert [d["name"] for d in client.get("/api/v1/datasets",
                                          headers=alice).json()["datasets"]] == ["alice.zip"]


def test_list_reports_quota_usage(client, db, user_headers):
    """ZH: 用量與列表一起回。分兩個請求拿的話，畫面上一定會有一瞬間兩邊數字對不起來。"""
    _upload(client, user_headers)
    body = client.get("/api/v1/datasets", headers=user_headers).json()
    assert body["used_bytes"] > 0
    assert body["quota_bytes"] >= body["used_bytes"]


# ──────────────────────────────────────────────────────────────────────────
# ZH: 三、刪除 —— 這是這整頁存在的理由（傳滿 2 GB 之後原本永遠卡住）
# ──────────────────────────────────────────────────────────────────────────

def test_delete_removes_the_row_and_the_file(client, db, user_headers, dataset_dir):
    """ZH: DB 與實體檔案要一起處理。只刪一邊的話，
       不是「列表沒了但空間沒還」就是「空間還了但列表還在」。
    """
    up = _upload(client, user_headers).json()
    ds_id = up["dataset_id"]
    path = pathlib.Path(up["dataset_path"])
    assert path.is_file()

    assert client.delete(f"/api/v1/datasets/{ds_id}", headers=user_headers).status_code == 200
    assert not path.exists(), "檔案還在，配額沒有真的還回去"
    assert client.get("/api/v1/datasets", headers=user_headers).json()["datasets"] == []


def test_delete_frees_quota(client, db, user_headers):
    """ZH: 這條才是重點——刪完之後**用量真的降下來**。"""
    ds_id = _upload(client, user_headers).json()["dataset_id"]
    before = client.get("/api/v1/datasets", headers=user_headers).json()["used_bytes"]
    assert before > 0
    client.delete(f"/api/v1/datasets/{ds_id}", headers=user_headers)
    after = client.get("/api/v1/datasets", headers=user_headers).json()["used_bytes"]
    assert after == 0, (before, after)


def test_cannot_delete_another_users_dataset(client, db):
    """ZH: 找不到與不是自己的**回同一個 404** —— 回 403 等於告訴對方這個 id 存在。"""
    make_user(db, username="alice", email="a@example.com")
    make_user(db, username="bob", email="b@example.com")
    alice, bob = auth_headers(client, "alice"), auth_headers(client, "bob")
    ds_id = _upload(client, alice).json()["dataset_id"]

    assert client.delete(f"/api/v1/datasets/{ds_id}", headers=bob).status_code == 404
    # ZH: 而且**真的沒被刪掉**（只看狀態碼不夠）
    assert len(client.get("/api/v1/datasets", headers=alice).json()["datasets"]) == 1


def test_cannot_delete_while_a_job_is_still_using_it(client, db, user_headers):
    """ZH: 🔴 還在排隊／執行中的單擋著不能刪。

    ZH: 刪掉的話那張單會在**領工之後**才失敗，而使用者根本不會把兩件事聯想在一起——
        他只會看到「訓練莫名其妙失敗了」。
    """
    ds_id = _upload(client, user_headers).json()["dataset_id"]
    _heartbeat(client)
    r = client.post("/api/v1/jobs", headers=user_headers,
                    json={"job_name": "x", "model_name": "resnet18",
                          "dataset_id": ds_id, "config": {"epochs": 1}})
    assert r.status_code == 201, r.text

    d = client.delete(f"/api/v1/datasets/{ds_id}", headers=user_headers)
    assert d.status_code == 409, d.text


def test_can_delete_once_the_job_finished(client, db, user_headers):
    """ZH: 陰性對照 —— 跑完就可以刪了。已完成的任務紀錄會保留（FK 是 SET NULL），
       刪資料集不該連歷史紀錄一起消失。
    """
    from app import models
    ds_id = _upload(client, user_headers).json()["dataset_id"]
    _heartbeat(client)
    jid = client.post("/api/v1/jobs", headers=user_headers,
                      json={"job_name": "x", "model_name": "resnet18",
                            "dataset_id": ds_id, "config": {"epochs": 1}}).json()["job_id"]
    db.query(models.TrainingJob).filter_by(id=jid).first().status = "completed"
    db.commit()

    assert client.delete(f"/api/v1/datasets/{ds_id}", headers=user_headers).status_code == 200
    # ZH: 任務紀錄還在
    assert client.get(f"/api/v1/jobs/{jid}", headers=user_headers).status_code == 200


# ──────────────────────────────────────────────────────────────────────────
# ZH: 四、重用 —— 用 dataset_id 送單（路徑完全不經過客戶端）
# ──────────────────────────────────────────────────────────────────────────

def test_submit_with_dataset_id(client, db, user_headers):
    ds_id = _upload(client, user_headers).json()["dataset_id"]
    _heartbeat(client)
    r = client.post("/api/v1/jobs", headers=user_headers,
                    json={"job_name": "reuse", "model_name": "resnet18",
                          "dataset_id": ds_id, "config": {"epochs": 1}})
    assert r.status_code == 201, r.text


def test_cannot_submit_with_another_users_dataset_id(client, db):
    """ZH: dataset_id 是 UUID，但**不能靠猜不到當作安全** —— 一樣要查所有權。"""
    make_user(db, username="alice", email="a@example.com")
    make_user(db, username="bob", email="b@example.com")
    alice, bob = auth_headers(client, "alice"), auth_headers(client, "bob")
    ds_id = _upload(client, alice).json()["dataset_id"]

    _heartbeat(client)
    r = client.post("/api/v1/jobs", headers=bob,
                    json={"job_name": "steal", "model_name": "resnet18",
                          "dataset_id": ds_id, "config": {"epochs": 1}})
    assert r.status_code == 403, r.text


def test_the_same_dataset_can_be_reused_for_several_jobs(client, db, user_headers):
    """ZH: 重用就是這頁的另一半價值 —— 同一包資料訓練不同輪數不必重傳。"""
    ds_id = _upload(client, user_headers).json()["dataset_id"]
    _heartbeat(client)
    for epochs in (1, 5):
        r = client.post("/api/v1/jobs", headers=user_headers,
                        json={"job_name": f"e{epochs}", "model_name": "resnet18",
                              "dataset_id": ds_id, "config": {"epochs": epochs}})
        assert r.status_code == 201, r.text
    assert len(client.get("/api/v1/datasets",
                          headers=user_headers).json()["datasets"]) == 1


# ──────────────────────────────────────────────────────────────────────────
# ZH: 五、刪帳號時，磁碟上的檔案也要跟著走
# ──────────────────────────────────────────────────────────────────────────

def test_deleting_a_user_removes_their_dataset_files(client, db, dataset_dir):
    """ZH: 🔴 DB 那邊 datasets 是 ON DELETE CASCADE，但**磁碟上的檔案不會跟著消失**。

    ZH: 刪了帳號，那些 zip 會永遠留在伺服器上——沒有人會發現，因為列表裡早就沒有了。
        與 Lab volume 封存是同一類：DB 與實體儲存要一起處理。

    ZH: ⚠ 這條一定要走**真的 admin 端點**。我第一次是用自己寫的清理腳本直接刪 DB，
        那條路根本不經過這段清理程式碼——量到「檔案還在」證明不了任何事。
    """
    import pathlib as _p
    make_user(db, username="victim", email="v@example.com")
    make_user(db, username="root", email="r@example.com", role="admin")
    victim = auth_headers(client, "victim")
    root = auth_headers(client, "root")

    path = _p.Path(_upload(client, victim).json()["dataset_path"])
    assert path.is_file()

    from app import models
    uid = db.query(models.User).filter_by(username="victim").first().id
    r = client.post(f"/api/v1/admin/users/{uid}/delete",
                    json={"admin_password": "password123"}, headers=root)
    assert r.status_code == 200, r.text

    assert not path.exists(), "帳號刪了，但他上傳的資料集還留在磁碟上"
    assert not path.parent.exists(), "使用者的資料集目錄沒有一起清掉"
