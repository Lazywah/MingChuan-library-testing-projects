"""
ZH: v4.39 GPU 功能依身分開放（擁有者 2026-10-06：老師／職員／管理員可用，學生／訪客不可用）。

ZH: 守的是三件會「騙到人」或「出事」的事：
    1. 後端沒擋 —— v4.38 以前只有前端擋，學生的 token 直接打 API 照樣跑得起來。
       這是這一版的重點，所以每一支閘門都要有自己的測試。
    2. 管理員被自己的政策鎖在外面 —— 關閉期間必須有人能驗證平台還活著。
    3. /auth/me 的 gpu_access 與後端閘門對不上 —— 畫面說可以、按下去 403，
       或反過來（畫面灰掉但其實能用）。前端完全依賴這個欄位，所以它要跟閘門同一個答案。

@node tests/test_gpu_role_access.py
"""
import io
import zipfile

import pytest

from conftest import auth_headers, make_user

from app import crud, models


def _set(client, admin_headers, **kw):
    r = client.put("/api/v1/admin/system-settings", headers=admin_headers, json=kw)
    assert r.status_code == 200, r.text
    return r


@pytest.fixture(autouse=True)
def default_gpu_policy(db, gpu_open_for_tests):
    """ZH: conftest 的 gpu_open_for_tests 把所有身分都打開了（給其他測試用）。
        這一檔要測的就是政策本身，所以先清掉覆寫、回到**出廠預設**
        （老師／職員／管理員開，學生／訪客關）。

    ZH: 參數裡放 gpu_open_for_tests 是為了**排序**：autouse 的順序不保證，
        明寫相依才能確保先開再清，而不是先清再被開回去。
    """
    from app import models
    db.query(models.SystemConfig).filter(
        models.SystemConfig.key.like("gpu_enabled_%")).delete(synchronize_session=False)
    db.commit()


@pytest.fixture()
def admin_headers(client, db):
    make_user(db, username="gpu-admin", email="gpu-admin@example.com", role="admin")
    return auth_headers(client, "gpu-admin", "password123")


@pytest.fixture()
def user_factory(client, db):
    def _make(role):
        name = "gpu-%s" % role
        make_user(db, username=name, email="%s@example.com" % name, role=role)
        return auth_headers(client, name, "password123")
    return _make


# ── 預設值（擁有者 2026-10-06 的裁定）────────────────────────────────

@pytest.mark.parametrize("role,allowed", [
    ("teacher", True), ("staff", True), ("admin", True),
    ("student", False), ("guest", False),
])
def test_default_policy(db, role, allowed):
    u = make_user(db, username="d-%s" % role, email="d-%s@example.com" % role, role=role)
    assert crud.gpu_access(db, u)["allowed"] is allowed


def test_blocked_reason_is_role_not_paused(db):
    u = make_user(db, username="r-stu", email="r-stu@example.com")
    assert crud.gpu_access(db, u) == {"allowed": False, "reason": "role"}


def test_master_switch_pauses_everyone_but_admin(db, client, admin_headers):
    """ZH: 總開關＝維護時一鍵全部暫停；管理員仍然進得去。"""
    teacher = make_user(db, username="p-tea", email="p-tea@example.com", role="teacher")
    admin = db.query(models.User).filter(models.User.username == "gpu-admin").first()
    _set(client, admin_headers, gpu_features_enabled=0)
    db.expire_all()
    assert crud.gpu_access(db, teacher) == {"allowed": False, "reason": "paused"}
    assert crud.gpu_access(db, admin)["allowed"] is True


def test_admin_allowed_even_with_every_switch_off(db, client, admin_headers):
    """ZH: 管理員看 is_admin 不看 role —— 把五個身分開關全關掉也擋不住他（v4.8 的理由）。"""
    admin = db.query(models.User).filter(models.User.username == "gpu-admin").first()
    _set(client, admin_headers, **{"gpu_enabled_%s" % r: 0 for r, _z, _e in crud.ROLES})
    db.expire_all()
    assert crud.gpu_access(db, admin)["allowed"] is True


def test_unknown_role_is_closed(db):
    """ZH: 不認得的身分往「關」的那一邊猜 —— 存取控制不往開的那邊猜。"""
    u = make_user(db, username="weird", email="weird@example.com")
    u.role = "visiting_scholar"
    db.commit()
    assert crud.gpu_access(db, u) == {"allowed": False, "reason": "role"}


def test_switch_can_be_flipped_from_admin_ui(db, client, admin_headers):
    stu = make_user(db, username="f-stu", email="f-stu@example.com")
    _set(client, admin_headers, gpu_enabled_student=1)
    db.expire_all()
    assert crud.gpu_access(db, stu)["allowed"] is True
    _set(client, admin_headers, gpu_enabled_student=0)
    db.expire_all()
    assert crud.gpu_access(db, stu)["allowed"] is False


# ── /auth/me ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("role,allowed,reason", [
    ("teacher", True, None), ("student", False, "role"),
])
def test_me_carries_gpu_access(client, user_factory, role, allowed, reason):
    """ZH: 前端只讀這個欄位，不自己算 —— 所以它必須在。"""
    r = client.get("/api/v1/auth/me", headers=user_factory(role))
    assert r.status_code == 200, r.text
    assert r.json()["gpu_access"] == {"allowed": allowed, "reason": reason}


# ── 後端閘門（v4.39 之前完全沒有）────────────────────────────────────

def _zip_bytes():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("cat/1.txt", "x")
        z.writestr("dog/1.txt", "y")
    return buf.getvalue()


GATED = [
    ("post", "/api/v1/jobs", {"json": {"job_name": "t", "model_name": "resnet18",
                                       "dataset_path": "/tmp/x.zip", "config": {"epochs": 1}}}),
    ("post", "/api/v1/lab/start", {"json": {}}),
    ("post", "/api/v1/lab/sessions", {"json": {"display_name": "t"}}),
]


@pytest.mark.parametrize("method,url,kw", GATED)
def test_student_gets_403_from_api(client, user_factory, method, url, kw):
    """ZH: 🔴 這一組是這一版的重點：v4.38 以前學生的 token 打這些端點照樣會跑。"""
    r = getattr(client, method)(url, headers=user_factory("student"), **kw)
    assert r.status_code == 403, r.text
    assert "身分" in r.json()["detail"]


def test_student_cannot_upload_dataset(client, user_factory):
    r = client.post("/api/v1/datasets/upload", headers=user_factory("student"),
                    files={"file": ("d.zip", _zip_bytes(), "application/zip")})
    assert r.status_code == 403
    assert "身分" in r.json()["detail"]


def test_teacher_passes_the_gate(client, user_factory):
    """ZH: 老師不該被擋在閘門 —— 之後的錯誤（找不到資料集之類）是別的事，不是 403。"""
    r = client.post("/api/v1/lab/sessions", headers=user_factory("teacher"),
                    json={"display_name": "t"})
    assert r.status_code != 403, r.text


def test_paused_message_differs_from_role_message(client, db, admin_headers, user_factory):
    """ZH: 兩種原因要講不同的話 —— 講一樣的話，學生會一直等一個不會來的恢復。"""
    h = user_factory("teacher")
    _set(client, admin_headers, gpu_features_enabled=0)
    r = client.post("/api/v1/lab/sessions", headers=h, json={"display_name": "t"})
    assert r.status_code == 403
    assert "暫停" in r.json()["detail"] and "身分" not in r.json()["detail"]


# ── 一次性遷移 ───────────────────────────────────────────────────────

def test_migration_restores_master_switch_once(db):
    """ZH: 09-07 的「全部暫停」是沒有身分概念時唯一能做的事；搬完要把總開關還給維護用。"""
    crud.set_system_config(db, "gpu_features_enabled", "0")
    crud.set_system_config(db, crud.GPU_ROLE_MIGRATED_KEY, "")
    assert crud.migrate_gpu_role_switches(db)["status"] == "migrated"
    assert crud.get_setting(db, "gpu_features_enabled") == 1
    # ZH: 搬完之後管理者自己關掉總開關（維護），不可以被下一次開機搬回去。
    crud.set_system_config(db, "gpu_features_enabled", "0")
    assert crud.migrate_gpu_role_switches(db)["status"] == "already_done"
    assert crud.get_setting(db, "gpu_features_enabled") == 0


def test_migration_leaves_role_switches_at_default(db):
    crud.set_system_config(db, crud.GPU_ROLE_MIGRATED_KEY, "")
    crud.migrate_gpu_role_switches(db)
    assert crud.get_setting(db, "gpu_enabled_teacher") == 1
    assert crud.get_setting(db, "gpu_enabled_student") == 0
