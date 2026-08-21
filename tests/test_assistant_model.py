# -*- coding: utf-8 -*-
"""
ZH: v3.7 —— 小基（RAG 客服助手）的模型由後台選。

ZH: 這份測試的重點是**選了之後真的會照著走**，以及選錯時不要靜默：
      1. choice 型的設定不能被數字轉換吃掉（會靜默退回 .env 的預設）
      2. 只接受選單裡真的有的值（打錯的模型名會讓小基每次都失敗，而設定頁看起來正常）
      3. 查不到 provider 時要往「本機」猜，**不要往校外猜**
"""
import pathlib
import sys

import pytest

from conftest import make_user, auth_headers

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "job-scheduler"))
from app import crud, models   # noqa: E402
from app.config import settings   # noqa: E402


@pytest.fixture
def admin_headers(client, db):
    make_user(db, username="root", email="root@example.com", role="admin")
    return auth_headers(client, "root")


def _add_model(db, name, provider, model_id):
    # ZH: `models.uploaded_by` 是 NOT NULL，所以要先有一個上傳者。
    owner = db.query(models.User).first()
    if owner is None:
        make_user(db, username="owner", email="owner@example.com")
        owner = db.query(models.User).filter_by(username="owner").first()
    m = models.Model(name=name, api_provider=provider, api_model_id=model_id,
                     is_public=0, uploaded_by=owner.id)
    db.add(m)
    db.commit()
    return m


def test_choice_setting_is_not_eaten_by_number_conversion(client, db):
    """ZH: 🔴 字串型的設定不能走 int/float 轉換。

    ZH: `float("llama3:latest")` 會丟例外，而原本的寫法**靜默退回預設值** ——
        管理者選了 Claude，小基卻還在用 .env 的 Ollama，
        而設定頁顯示的是他選的那個。沒有任何錯誤訊息。
    """
    _add_model(db, "Claude 3.5", "anthropic", "claude-3-5-sonnet")
    crud.set_settings(db, {"rag_chat_model": "claude-3-5-sonnet"})
    assert crud.get_setting(db, "rag_chat_model") == "claude-3-5-sonnet"


def test_choices_come_from_the_model_registry(client, db):
    """ZH: 選項來自「平台設定 → 模型」那張表，不是程式碼裡的另一份清單。"""
    _add_model(db, "Gemini 1.5 Pro", "google", "gemini-1.5-pro")
    vals = [c["value"] for c in crud.rag_model_choices(db)]
    assert "gemini-1.5-pro" in vals


def test_env_default_is_always_selectable(client, db):
    """ZH: `.env` 的預設值就算沒被登錄也要在選單裡。

    ZH: 不然「目前生效的值」在下拉裡找不到，瀏覽器會顯示成第一個選項 ——
        管理者看到的與實際生效的**不是同一個**。
    """
    vals = [c["value"] for c in crud.rag_model_choices(db)]
    assert settings.RAG_CHAT_MODEL in vals


def test_unknown_model_is_rejected(client, db):
    """ZH: 打錯的模型名要當場擋掉。

    ZH: 存進去的話小基每次回答都會失敗，而設定頁看起來一切正常 ——
        那種錯誤要花很久才會被連結到「原來是那天改了設定」。
    """
    with pytest.raises(ValueError):
        crud.set_settings(db, {"rag_chat_model": "gpt-99-turbo-typo"})


def test_provider_lookup_falls_back_to_local_not_external(client, db):
    """ZH: 🔴 查不到 provider 時要當成 **ollama（本機）**。

    ZH: 往「校外」猜的話，會把使用者的問題送到廠商，
        而管理者以為它還在本機跑 —— 那是隱私問題，不只是設定錯誤。
        往本機猜最壞只是「Ollama 沒有這個模型」然後明確報錯。
    """
    assert crud.rag_model_provider(db, "something-never-registered") == "ollama"


def test_provider_lookup_uses_the_registry(client, db):
    """ZH: 陰性對照 —— 有登錄的就要回它真正的 provider，不能一律回 ollama。"""
    _add_model(db, "Claude 3.5", "anthropic", "claude-3-5-sonnet")
    assert crud.rag_model_provider(db, "claude-3-5-sonnet") == "anthropic"


def test_admin_settings_endpoint_exposes_the_choices(client, db, admin_headers):
    """ZH: 設定端點要把選項一起送 —— 前端不該自己去猜有哪些值。"""
    _add_model(db, "Claude 3.5", "anthropic", "claude-3-5-sonnet")
    body = client.get("/api/v1/admin/system-settings", headers=admin_headers).json()
    row = [s for s in body["settings"] if s["key"] == "rag_chat_model"][0]
    assert row["type"] == "choice"
    assert any(c["value"] == "claude-3-5-sonnet" for c in row["choices"])


def test_assistant_status_reports_the_effective_model(client, db, admin_headers):
    """ZH: 診斷資訊要回**目前生效**的模型，不是 .env 的預設。

    ZH: 不然管理者改了設定、去看診斷卻還顯示舊的那個，
        會以為設定沒存進去。
    """
    _add_model(db, "Claude 3.5", "anthropic", "claude-3-5-sonnet")
    crud.set_settings(db, {"rag_chat_model": "claude-3-5-sonnet"})
    body = client.get("/api/v1/assistant/status").json()
    assert body["chat_model"] == "claude-3-5-sonnet", body
