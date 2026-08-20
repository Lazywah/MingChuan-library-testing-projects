# -*- coding: utf-8 -*-
"""
ZH: v3.6 —— 平台自身的 Token 計費由 `INTERNAL_TOKEN_ACCOUNTING` 統一控制。

ZH: 🔴 這個開關**原本只有 chat.py 讀**，送單那條路照扣照擋。
    也就是：設成 false 的部署以為計費關了，實際上訓練仍在扣額度。
    扣到見底時使用者會收到 429，而 v2 畫面上**沒有任何地方看得到平台 Token 餘額**
    —— 他不會知道發生什麼事，也不知道去哪看。

ZH: 目前規劃是「訓練不消耗 Token」（未接外部 LLM API），所以預設關閉。
    機制整套保留：把開關打開就恢復原本行為。
"""
import pytest

from conftest import make_user, auth_headers

WORKER_AUTH = {"Authorization": "Bearer test-worker-token-16c"}


@pytest.fixture
def user_headers(client, db):
    make_user(db)
    return auth_headers(client)


def _heartbeat(client):
    client.post("/api/v1/worker/heartbeat",
                json={"node_id": "n1", "available_gpus": ["0"], "pool_type": "batch",
                      "shares_service_storage": True}, headers=WORKER_AUTH)


def _submit(client, headers, epochs=10):
    return client.post("/api/v1/jobs", headers=headers,
                       json={"job_name": "t", "model_name": "resnet18",
                             "config": {"epochs": epochs}})


def _usage(db, username="testuser"):
    from app import crud, models
    uid = db.query(models.User).filter_by(username=username).first().id
    return crud.get_token_usage(db, user_id=uid)


def _set_flag(monkeypatch, on: bool):
    from app.routers import jobs as jr
    monkeypatch.setattr(jr.settings, "INTERNAL_TOKEN_ACCOUNTING", on)


# ──────────────────────────────────────────────────────────────────────────
# ZH: 關閉時（目前的預設）
# ──────────────────────────────────────────────────────────────────────────

def test_no_deduction_when_accounting_is_off(client, db, user_headers, monkeypatch):
    """ZH: 關掉計費之後，送單**不應該扣任何額度**。"""
    _set_flag(monkeypatch, False)
    _heartbeat(client)
    before = _usage(db)
    used_before = before.tokens_used if before else 0

    assert _submit(client, user_headers).status_code == 201
    db.expire_all()
    after = _usage(db)
    assert (after.tokens_used if after else 0) == used_before


def test_submission_is_not_blocked_when_accounting_is_off(client, db, user_headers,
                                                          monkeypatch):
    """ZH: 🔴 額度已經見底時，關掉計費就**不該再擋**。

    ZH: 這是關掉計費最重要的一件事：不然「已經扣到見底」的舊帳
        會繼續擋著新的送單，而使用者完全查不到原因。
    """
    _set_flag(monkeypatch, False)
    _heartbeat(client)
    u = _usage(db)
    u.tokens_used = u.tokens_limit          # 見底
    db.commit()

    assert _submit(client, user_headers).status_code == 201


# ──────────────────────────────────────────────────────────────────────────
# ZH: 打開時（陰性對照 —— 證明機制還在，只是被關掉）
# ──────────────────────────────────────────────────────────────────────────

def test_deduction_happens_when_accounting_is_on(client, db, user_headers, monkeypatch):
    """ZH: 陰性對照。沒有這條，上面兩條在「扣額功能整個壞掉」時也會綠。"""
    _set_flag(monkeypatch, True)
    _heartbeat(client)
    before = _usage(db)
    used_before = before.tokens_used if before else 0

    assert _submit(client, user_headers, epochs=10).status_code == 201
    db.expire_all()
    after = _usage(db)
    assert after.tokens_used == used_before + 10000, (used_before, after.tokens_used)


def test_submission_is_blocked_when_out_of_quota_and_accounting_is_on(
        client, db, user_headers, monkeypatch):
    """ZH: 陰性對照 —— 打開時該擋還是要擋（機制沒有被拆掉，只是被關掉）。"""
    _set_flag(monkeypatch, True)
    _heartbeat(client)
    u = _usage(db)
    u.tokens_used = u.tokens_limit
    db.commit()

    r = _submit(client, user_headers)
    assert r.status_code == 429, r.text
