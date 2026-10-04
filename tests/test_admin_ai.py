"""
ZH: v4.37 管理端 AI（擁有者 2026-10-04：本機模型、只能查不能改）。

ZH: 守的是四件會「騙到人」或「出事」的事：
    1. 工具檔裡出現寫入 —— 模型的輸入有一部分來自使用者資料，被塞字就不能變成動作。
    2. 設定成校外模型時仍然送出去 —— 查詢結果有學號、信箱、日誌。
    3. 非管理員查得到。
    4. 每次提問沒有留稽核 —— 它讀得到所有人的資料。
    另外驗規則路由與帳號查詢的「判斷」（人工查 12361114 時的那一步：刪除後重建）。
    模型本身一律 monkeypatch 掉，測試不連 Ollama。

@node tests/test_admin_ai.py
"""
import json
import re
from datetime import datetime, timedelta, timezone

import pytest

from conftest import auth_headers, make_user, repo_file

from app import models
from app.routers import admin_ai as admin_ai_router
from app.services import admin_ai, admin_ai_tools


@pytest.fixture()
def fake_model(monkeypatch):
    """ZH: 換掉 Ollama。記下每次被叫的 messages，路由時回 none。"""
    calls = []

    def _fake(model, messages, json_mode=False, timeout=120.0):
        calls.append({"model": model, "messages": messages, "json_mode": json_mode})
        if json_mode:
            return json.dumps({"tool": "none", "args": {}})
        return "（模型摘要）"

    monkeypatch.setattr(admin_ai, "_ollama", _fake)
    return calls


@pytest.fixture()
def admin_headers(client, db):
    admin_ai_router._hits.clear()
    make_user(db, username="ai-admin", email="ai-admin@example.com", role="admin")
    return auth_headers(client, "ai-admin", "password123")


# ── 1. 唯讀 ────────────────────────────────────────────────────────────

_WRITE_PATTERNS = [
    r"\.add\(", r"\.add_all\(", r"\.commit\(", r"\.delete\(", r"\.merge\(", r"\.flush\(",
    # ZH: `.update(` 只抓接在查詢後面的（`).update(`）—— dict.update 是合法的唯讀寫法。
    r"\.execute\(", r"\)\s*\.update\(",
    r"\bos\.remove\(", r"\bos\.unlink\(", r"\brmtree\(", r"\.unlink\(", r"\.rename\(",
    r"\.write_text\(", r"\.write_bytes\(", r"open\([^)]*['\"][wa]",
    r"\.stop\(", r"\.kill\(", r"\.restart\(", r"\.remove\(", r"\.exec_run\(",
    r"httpx\.(post|put|patch|delete)\(", r"requests\.(post|put|patch|delete)\(",
    r"\bsubprocess\b",
]


def test_tools_source_has_no_writes():
    """ZH: 工具檔的原始碼不准有任何寫入的寫法（見 admin_ai_tools.py 檔頭）。"""
    src = repo_file("job-scheduler", "app", "services", "admin_ai_tools.py").read_text(encoding="utf-8")
    code = "\n".join(l.split("#", 1)[0] for l in src.splitlines())
    hits = [p for p in _WRITE_PATTERNS if re.search(p, code)]
    assert hits == [], f"admin_ai_tools.py 出現寫入：{hits}"


def test_tool_list_matches_specs():
    assert set(admin_ai_tools.TOOLS) == {t[0] for t in admin_ai_tools.TOOL_SPECS}


# ── 2. 只准本機模型 ────────────────────────────────────────────────────

def test_refuses_non_local_model(db, monkeypatch, fake_model):
    monkeypatch.setattr(admin_ai.crud, "rag_model_provider", lambda db, name: "openai")
    with pytest.raises(admin_ai.AdminAiError, match="本機"):
        admin_ai.ask(db, "系統狀態")
    assert fake_model == [], "校外模型應該在送出前就擋下，不能先呼叫再說"


def test_endpoint_returns_503_for_non_local_model(client, admin_headers, monkeypatch, fake_model):
    monkeypatch.setattr(admin_ai.crud, "rag_model_provider", lambda db, name: "anthropic")
    r = client.post("/api/v1/admin/ai/ask", headers=admin_headers, json={"question": "MYAI 同步正常嗎"})
    assert r.status_code == 503
    assert "本機" in r.json()["detail"]
    assert fake_model == []


# ── 3. 只限管理員 ──────────────────────────────────────────────────────

def test_student_gets_403(client, db, fake_model):
    make_user(db, username="ai-student", email="ai-student@example.com")
    h = auth_headers(client, "ai-student", "password123")
    r = client.post("/api/v1/admin/ai/ask", headers=h, json={"question": "系統狀態"})
    assert r.status_code == 403
    assert fake_model == []


def test_anonymous_gets_401(client, fake_model):
    r = client.post("/api/v1/admin/ai/ask", json={"question": "系統狀態"})
    assert r.status_code == 401


def test_empty_question_400(client, admin_headers, fake_model):
    r = client.post("/api/v1/admin/ai/ask", headers=admin_headers, json={"question": "   "})
    assert r.status_code == 400


# ── 4. 稽核與限流 ──────────────────────────────────────────────────────

def test_every_question_is_audited(client, db, admin_headers, fake_model):
    r = client.post("/api/v1/admin/ai/ask", headers=admin_headers,
                    json={"question": "檢查 12345678 的帳號"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["tool"] == "user_report" and body["routed_by"] == "rule"
    assert body["answer"] == "（模型摘要）"
    db.expire_all()
    rows = db.query(models.AdminAction).filter(models.AdminAction.action == "ai_query").all()
    assert len(rows) == 1
    p = json.loads(rows[0].payload)
    assert p["question"] == "檢查 12345678 的帳號"
    assert p["tool"] == "user_report" and p["args"] == {"username": "12345678"}
    assert rows[0].admin_username == "ai-admin"


def test_rate_limit(client, admin_headers, monkeypatch, fake_model):
    monkeypatch.setattr(admin_ai_router, "_MAX_PER_WINDOW", 2)
    for _ in range(2):
        assert client.post("/api/v1/admin/ai/ask", headers=admin_headers,
                           json={"question": "最近的錯誤"}).status_code == 200
    r = client.post("/api/v1/admin/ai/ask", headers=admin_headers, json={"question": "最近的錯誤"})
    assert r.status_code == 429


# ── 路由 ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize("q,expected", [
    ("MYAI 同步正常嗎", ("myai_status", {})),
    ("點數同步是不是又壞了", ("myai_status", {})),
    ("檢查 12361114 帳號狀態，信箱收到實驗室刪除訊息", ("user_report", {"username": "12361114"})),
    ("訓練 3f9a1c2e 為什麼失敗", ("job_report", {"job_id": "3f9a1c2e"})),
    ("job 3f9a1c2e-1a2b status", ("job_report", {"job_id": "3f9a1c2e"})),
    ("12361114 的 MYAI 綁定", ("user_report", {"username": "12361114"})),
    ("最近有什麼錯誤", None),
    ("系統狀態", None),
])
def test_rule_routing(q, expected):
    assert admin_ai._route_by_rules(q) == expected


def test_model_routing_rejects_unknown_tool(monkeypatch):
    """ZH: 模型回了不存在的工具（或要它做寫入）一律當成 none，不會去找同名函式。"""
    monkeypatch.setattr(admin_ai, "_ollama",
                        lambda *a, **k: json.dumps({"tool": "delete_user", "args": {"username": "x"}}))
    assert admin_ai._route_by_model("m", "把 x 刪掉") is None
    monkeypatch.setattr(admin_ai, "_ollama", lambda *a, **k: "not json")
    assert admin_ai._route_by_model("m", "隨便") is None


def test_unrelated_question_does_not_summarize(db, fake_model):
    r = admin_ai.ask(db, "今天天氣如何")
    assert r["tool"] is None and r["data"] is None
    assert len(fake_model) == 1 and fake_model[0]["json_mode"], "查不到工具就不該再叫模型摘要"


def test_summary_prompt_marks_data_as_not_instructions(db, fake_model):
    admin_ai.ask(db, "檢查 12345678")
    system = fake_model[-1]["messages"][0]["content"]
    assert "不是指令" in system and "不能修改" in system


# ── 工具的判斷 ─────────────────────────────────────────────────────────

def test_user_report_detects_recreated_account(db):
    """ZH: 2026-10-04 人工查 12361114 的關鍵一步：帳號建立時間比寄給這個學號的第一封信晚。"""
    u = make_user(db, username="12361114", email="12361114@example.com")
    u.created_at = datetime.now(timezone.utc) - timedelta(days=1)
    db.add(models.EmailLog(to_email="12361114@example.com", username="12361114", kind="login_alert",
                           subject="舊帳號的信", status="sent",
                           created_at=datetime.now(timezone.utc) - timedelta(days=40)))
    db.add(models.AdminAction(admin_id=None, admin_username="old-admin", target_user=None,
                              action="delete_user",
                              payload=json.dumps({"username": "12361114", "deleted_user_id": "61d0d4d8-xxxx"}),
                              timestamp=datetime.now(timezone.utc) - timedelta(days=20)))
    db.commit()
    r = admin_ai_tools.user_report(db, "12361114")
    joined = " ".join(r["findings"])
    assert "曾被刪除後重建" in joined
    assert r["tables"]["刪除紀錄"][0]["執行者"] == "old-admin"
    assert r["facts"]["exists"] is True


def test_user_report_deleted_account(db):
    db.add(models.AdminAction(admin_id=None, admin_username="old-admin", target_user=None,
                              action="delete_user",
                              payload=json.dumps({"username": "99887766"}),
                              timestamp=datetime.now(timezone.utc)))
    # ZH: 學號只是 payload 裡的子字串（另一個學號包含它）不算
    db.add(models.AdminAction(admin_id=None, admin_username="x", target_user=None, action="delete_user",
                              payload=json.dumps({"username": "199887766"}),
                              timestamp=datetime.now(timezone.utc)))
    db.commit()
    r = admin_ai_tools.user_report(db, "99887766")
    assert r["facts"]["exists"] is False
    assert len(r["tables"]["刪除紀錄"]) == 1
    assert "目前不存在" in r["findings"][0]


def test_user_report_unknown(db):
    r = admin_ai_tools.user_report(db, "11112222")
    assert "找不到這個帳號" in r["findings"][0]


def test_job_report_prefix_ambiguity(db):
    u = make_user(db, username="jr-user", email="jr@example.com")
    for suffix in ("1111", "2222"):
        db.add(models.TrainingJob(id=f"abcd{suffix}-0000-0000-0000-000000000000", user_id=u.id,
                                  job_name="t", model_name="resnet18", status="completed"))
    db.commit()
    r = admin_ai_tools.job_report(db, "abcd")
    assert "2 筆" in r["findings"][0]
    assert admin_ai_tools.job_report(db, "ab")["findings"] == ["任務 id 至少要給開頭 4 碼。"]
    assert "找不到" in admin_ai_tools.job_report(db, "ffff0000")["findings"][0]


def test_admin_ai_model_setting_lists_only_local(client, db, admin_headers):
    """ZH: 設定下拉只列本機模型；直接送校外模型的名字也存不進去。"""
    admin = db.query(models.User).filter(models.User.username == "ai-admin").first()
    db.add(models.Model(name="雲端", api_model_id="gpt-x", api_provider="openai", uploaded_by=admin.id))
    db.commit()
    r = client.get("/api/v1/admin/system-settings", headers=admin_headers)
    assert r.status_code == 200, r.text
    items = r.json()["settings"]
    row = next(i for i in items if i["key"] == "admin_ai_model")
    assert all(c.get("provider") == "ollama" for c in row["choices"])
    assert "gpt-x" not in {c["value"] for c in row["choices"]}
    r = client.put("/api/v1/admin/system-settings", headers=admin_headers,
                   json={"admin_ai_model": "gpt-x"})
    assert r.status_code in (400, 422), r.text
