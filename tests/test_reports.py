"""
ZH: v3.4 問題回報 —— 送出、自己看歷史、admin 看全部與回應。
EN: v3.4 issue reports — submit, own history, admin list & reply.

ZH: 這一支特別守三件事，因為它們都是「壞了也不會有人立刻發現」的那種：
    1. 使用者只能看到自己的回報（越權讀取不會有錯誤訊息，只會多看到東西）
    2. 後端**不加**任何使用者沒看到的欄位（IP 等）——見 models.IssueReport 註解
    3. 刪帳號後回報仍在、仍認得出是誰報的（靠 ondelete="SET NULL" + 帳號名快照）
"""
import json

from conftest import auth_headers, make_user


def _submit(client, headers, body="按下前往 MYAI 之後是空白頁", diag=None):
    return client.post("/api/v1/reports",
                       json={"body": body,
                             "diagnostics": diag if diag is not None
                             else {"介面版本": "v2", "瀏覽器": "TestClient"}},
                       headers=headers)


# ── 使用者側 ────────────────────────────────────────────────────────────────

def test_submit_and_read_own_report(client, db):
    make_user(db)
    h = auth_headers(client)

    r = _submit(client, h)
    assert r.status_code == 201, r.text
    created = r.json()
    assert created["status"] == "open"
    assert created["admin_reply"] is None
    assert created["username_at_report"] == "testuser"

    mine = client.get("/api/v1/reports/mine", headers=h)
    assert mine.status_code == 200
    rows = mine.json()
    assert len(rows) == 1 and rows[0]["id"] == created["id"]


def test_blank_body_is_rejected(client, db):
    """ZH: 整串空白會產生一筆管理者看不懂的空回報——min_length 擋不掉。"""
    make_user(db)
    h = auth_headers(client)
    assert _submit(client, h, body="   \n\t ").status_code == 422


def test_anonymous_cannot_submit(client, db):
    assert _submit(client, {}).status_code in (401, 403)


def test_user_sees_only_their_own(client, db):
    """ZH: 越權讀取不會噴錯，只會**多看到東西**——所以要有測試。"""
    make_user(db, username="alice", email="a@example.com")
    make_user(db, username="bob", email="b@example.com")
    ha = auth_headers(client, "alice")
    hb = auth_headers(client, "bob")

    _submit(client, ha, body="alice 的問題")
    _submit(client, hb, body="bob 的問題")

    rows = client.get("/api/v1/reports/mine", headers=ha).json()
    assert [x["body"] for x in rows] == ["alice 的問題"]


def test_backend_stores_only_what_the_user_saw(client, db):
    """ZH: 頁面把診斷資訊整段攤開給使用者看，並宣稱「交了什麼你都知道」。
    後端若補上 IP 或 session，那句話就變成假的。這支釘住那個宣稱。
    """
    make_user(db)
    h = auth_headers(client)
    sent = {"介面版本": "v2", "視窗": "1280x800"}
    rid = _submit(client, h, diag=sent).json()["id"]

    from app import models
    row = db.query(models.IssueReport).filter(models.IssueReport.id == rid).first()
    stored = json.loads(row.diagnostics)
    assert stored == sent, f"後端改動了診斷內容：{stored}"
    # ZH: 反向守門——這張表根本不該有 IP 欄位。有人日後加了就要紅。
    assert not hasattr(row, "ip_address"), "issue_reports 出現 IP 欄位，違反本表的隱私約定"


def test_oversized_diagnostics_rejected(client, db):
    make_user(db)
    h = auth_headers(client)
    r = _submit(client, h, diag={"x": "a" * 9000})
    assert r.status_code == 413


# ── 管理端 ──────────────────────────────────────────────────────────────────

def test_non_admin_cannot_list_all(client, db):
    make_user(db)
    h = auth_headers(client)
    assert client.get("/api/v1/admin/reports", headers=h).status_code == 403


def test_admin_sees_all_and_can_reply(client, db):
    make_user(db, username="stu", email="s@example.com")
    make_user(db, username="boss", email="boss@example.com", role="admin")
    hs = auth_headers(client, "stu")
    ha = auth_headers(client, "boss")

    rid = _submit(client, hs).json()["id"]

    rows = client.get("/api/v1/admin/reports", headers=ha).json()
    assert [x["id"] for x in rows] == [rid]

    r = client.put(f"/api/v1/admin/reports/{rid}",
                   json={"status": "resolved", "admin_reply": "已修好，請重新整理"},
                   headers=ha)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "resolved"
    assert r.json()["replied_at"] is not None

    # ZH: 使用者這一側必須看得到回應——這是整個功能的目的。
    mine = client.get("/api/v1/reports/mine", headers=hs).json()
    assert mine[0]["admin_reply"] == "已修好，請重新整理"
    assert mine[0]["status"] == "resolved"


def test_clearing_reply_clears_its_metadata(client, db):
    """ZH: 回應打錯字想收回。只清文字不清 replied_at，
    使用者端會看到「已回覆但沒有內容」。
    """
    make_user(db, username="stu", email="s@example.com")
    make_user(db, username="boss", email="boss@example.com", role="admin")
    hs, ha = auth_headers(client, "stu"), auth_headers(client, "boss")
    rid = _submit(client, hs).json()["id"]

    client.put(f"/api/v1/admin/reports/{rid}", json={"admin_reply": "打錯了"}, headers=ha)
    out = client.put(f"/api/v1/admin/reports/{rid}", json={"admin_reply": "  "},
                     headers=ha).json()
    assert out["admin_reply"] is None
    assert out["replied_at"] is None


def test_status_only_update_keeps_reply(client, db):
    """ZH: 兩個欄位都可選——只改狀態不該把回應洗掉。"""
    make_user(db, username="stu", email="s@example.com")
    make_user(db, username="boss", email="boss@example.com", role="admin")
    hs, ha = auth_headers(client, "stu"), auth_headers(client, "boss")
    rid = _submit(client, hs).json()["id"]

    client.put(f"/api/v1/admin/reports/{rid}", json={"admin_reply": "處理中"}, headers=ha)
    out = client.put(f"/api/v1/admin/reports/{rid}", json={"status": "in_progress"},
                     headers=ha).json()
    assert out["admin_reply"] == "處理中"
    assert out["status"] == "in_progress"


def test_unknown_status_rejected(client, db):
    make_user(db, username="boss", email="boss@example.com", role="admin")
    ha = auth_headers(client, "boss")
    assert client.get("/api/v1/admin/reports?status=nope", headers=ha).status_code == 400


def test_open_reports_sort_first(client, db):
    """ZH: 管理者打開這頁是要找**待辦**。待辦埋在已解決裡面＝沒有列表。"""
    make_user(db, username="stu", email="s@example.com")
    make_user(db, username="boss", email="boss@example.com", role="admin")
    hs, ha = auth_headers(client, "stu"), auth_headers(client, "boss")

    old = _submit(client, hs, body="舊的").json()["id"]
    new = _submit(client, hs, body="新的").json()["id"]
    client.put(f"/api/v1/admin/reports/{new}", json={"status": "resolved"}, headers=ha)

    rows = client.get("/api/v1/admin/reports", headers=ha).json()
    assert rows[0]["id"] == old, "未處理的沒有排在最前面"


def test_summary_counts(client, db):
    make_user(db, username="stu", email="s@example.com")
    make_user(db, username="boss", email="boss@example.com", role="admin")
    hs, ha = auth_headers(client, "stu"), auth_headers(client, "boss")
    a = _submit(client, hs).json()["id"]
    _submit(client, hs)
    client.put(f"/api/v1/admin/reports/{a}", json={"status": "resolved"}, headers=ha)

    s = client.get("/api/v1/admin/reports/summary", headers=ha).json()
    assert s["open"] == 1
    assert s["counts"]["resolved"] == 1


# ── 刪帳號 ──────────────────────────────────────────────────────────────────

def test_deleting_user_keeps_report_and_does_not_500(client, db):
    """ZH: 刪掉報告者之後，回報要留著且認得出是誰報的。

    ⚠ 這支**只有在 conftest 開了 PRAGMA foreign_keys=ON 時才驗得到東西**。
      預設關閉時 SQLite 不會執行 ON DELETE SET NULL，也不會擋 NO ACTION，
      於是「忘了處理 users FK」這一整類缺陷在測試裡完全看不見。
      實測過：把 FK 關掉，這支的 user_id 斷言會紅，但**不是**因為 500——
      是因為 SET NULL 根本沒發生。兩種紅法要分清楚。
    """
    stu = make_user(db, username="stu", email="s@example.com")
    make_user(db, username="boss", email="boss@example.com", role="admin")
    hs, ha = auth_headers(client, "stu"), auth_headers(client, "boss")
    rid = _submit(client, hs).json()["id"]
    client.put(f"/api/v1/admin/reports/{rid}", json={"admin_reply": "看到了"}, headers=ha)

    r = client.post(f"/api/v1/admin/users/{stu.id}/delete",
                    json={"admin_password": "password123"}, headers=ha)
    assert r.status_code == 200, f"刪帳號失敗（issue_reports 沒解參照？）：{r.text}"

    rows = client.get("/api/v1/admin/reports", headers=ha).json()
    assert len(rows) == 1
    assert rows[0]["user_id"] is None
    assert rows[0]["username_at_report"] == "stu", "刪帳號後認不出是誰報的"
    assert rows[0]["admin_reply"] == "看到了"


def test_deleting_the_replying_admin_keeps_the_reply(client, db):
    """ZH: replied_by 也是 users FK，且同樣宣告 SET NULL——回應內容不該跟著消失。"""
    make_user(db, username="stu", email="s@example.com")
    a1 = make_user(db, username="admin1", email="a1@example.com", role="admin")
    make_user(db, username="admin2", email="a2@example.com", role="admin")
    hs = auth_headers(client, "stu")
    h1 = auth_headers(client, "admin1")
    h2 = auth_headers(client, "admin2")
    rid = _submit(client, hs).json()["id"]
    client.put(f"/api/v1/admin/reports/{rid}", json={"admin_reply": "由 admin1 回覆"},
               headers=h1)

    r = client.post(f"/api/v1/admin/users/{a1.id}/delete",
                    json={"admin_password": "password123"}, headers=h2)
    assert r.status_code == 200, f"刪回覆者失敗（replied_by 沒解參照？）：{r.text}"
    rows = client.get("/api/v1/admin/reports", headers=h2).json()
    assert rows[0]["admin_reply"] == "由 admin1 回覆"


def test_timestamps_are_marked_utc(client, db):
    """ZH: 時間欄位序列化必須帶時區。

    ZH: DB 存的是 UTC，但 SQLite 回來是 naive datetime；不標時區的話
        瀏覽器的 new Date() 會當成本地時間，+08:00 的使用者看到的時間
        **早 8 小時**。不會報錯、版面正常，只是每個時間都錯——
        實測抓到過（送出 09:42 顯示 01:42）。
    """
    make_user(db)
    h = auth_headers(client)
    row = _submit(client, h).json()
    for k in ("created_at", "updated_at"):
        v = row[k]
        assert v is not None
        assert v.endswith("+00:00") or v.endswith("Z"), \
            f"{k} 沒有時區標記：{v!r} —— 前端會當成本地時間，差 8 小時"
