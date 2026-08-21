# -*- coding: utf-8 -*-
"""
ZH: v3.6 —— 實驗室多份存檔（一次只開一份）。

ZH: 資料模型本來就支援：`lab_sessions` 的主鍵一直是 `(user_id, session_name)`，
    而 `session_name` 的註解直接寫著「v2.0 強制 default」。是程式碼把它釘死。

ZH: 這份測試的兩個重點，都不是「功能會不會動」：
      1. **既有資料不被動到** —— `default` 必須沿用原本的容器／volume／網址名。
         改名等於要遷移正在用的東西。
      2. **授權不會放行別份** —— `/code/<uid>-<存檔>/` 的前綴比對寫錯的話，
         要嘛擋掉自己的，要嘛放行別人的。
"""
import pathlib
import sys

import pytest

from conftest import make_user, auth_headers

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "job-scheduler"))
from app.services import lab_manager as lm   # noqa: E402


@pytest.fixture
def user_headers(client, db):
    make_user(db)
    return auth_headers(client)


def _uid(db, username="testuser"):
    from app import models
    return db.query(models.User).filter_by(username=username).first().id


# ──────────────────────────────────────────────────────────────────────────
# ZH: 一、🔴 既有資料不被動到
# ──────────────────────────────────────────────────────────────────────────

def test_default_keeps_the_original_names():
    """ZH: 🔴 `default` 的容器／volume 名**必須與加這個功能之前完全一樣**。

    ZH: 既有使用者的檔案都在 `home_<uid>` 裡，正在跑的容器叫 `cs-<uid>`。
        名字一改就要遷移正在用的東西 —— 風險與收益不成比例。
    """
    lc = lm.get_lifecycle()
    uid = "abc-123-def"
    assert lc._container_name(uid) == "cs-abc-123-def"
    assert lc._volume_name(uid) == "home_abc_123_def"
    # ZH: 明確帶 default 也要一樣（呼叫端可能兩種寫法都有）
    assert lc._container_name(uid, lm.DEFAULT_SESSION) == lc._container_name(uid)
    assert lc._volume_name(uid, lm.DEFAULT_SESSION) == lc._volume_name(uid)


def test_other_workspaces_get_a_suffix():
    """ZH: 陰性對照 —— 新增的那幾份確實帶後綴（否則會與 default 撞名共用同一個 volume）。"""
    lc = lm.get_lifecycle()
    uid = "abc-123-def"
    assert lc._container_name(uid, "ws2") == "cs-abc-123-def-ws2"
    assert lc._volume_name(uid, "ws2") == "home_abc_123_def_ws2"
    assert lc._volume_name(uid, "ws2") != lc._volume_name(uid)


# ──────────────────────────────────────────────────────────────────────────
# ZH: 二、名字：使用者看得懂的 vs 進網址的
# ──────────────────────────────────────────────────────────────────────────

def test_slug_is_dns_safe_and_unique():
    """ZH: session_name 會進**容器名與網址**，只能是 DNS-safe 的字元。"""
    assert lm._slugify("Deep Learning HW", set()) == "deep-learning-hw"
    # ZH: 中文清光之後退回 ws —— 看得懂這件事由 display_name 負責
    assert lm._slugify("我的畢業專題", set()) == "ws"
    # ZH: 撞名加序號
    assert lm._slugify("ws", {"ws"}) == "ws-2"
    # ZH: 不可以變出 default（那會與既有那一份共用 volume）
    assert lm._slugify("default", set()) != lm.DEFAULT_SESSION


def test_slug_never_contains_unsafe_characters():
    for name in ("a/b", "..", "  ", "A_B_C", "中文 mixed 名字", "x" * 100):
        slug = lm._slugify(name, set())
        assert slug, name
        assert all(c in lm._SLUG_OK for c in slug), (name, slug)
        assert "/" not in slug and ".." not in slug, (name, slug)


# ──────────────────────────────────────────────────────────────────────────
# ZH: 三、端點
# ──────────────────────────────────────────────────────────────────────────

def test_list_returns_default_even_when_nothing_exists(client, db, user_headers):
    """ZH: 一份都沒建過時**至少回一份 default**。

    ZH: 既有使用者的資料都在那一份底下 —— 列表空白會讓他以為東西不見了。
    """
    body = client.get("/api/v1/lab/sessions", headers=user_headers).json()
    assert [s["session_name"] for s in body["sessions"]] == [lm.DEFAULT_SESSION]


def test_create_and_list(client, db, user_headers):
    r = client.post("/api/v1/lab/sessions", headers=user_headers,
                    json={"display_name": "我的畢業專題"})
    assert r.status_code == 200, r.text
    slug = r.json()["session_name"]

    body = client.get("/api/v1/lab/sessions", headers=user_headers).json()
    names = {s["session_name"]: s["display_name"] for s in body["sessions"]}
    assert slug in names
    # ZH: 中文名字要留得住（那是使用者看得懂的那一個）
    assert names[slug] == "我的畢業專題"


def test_default_sorts_first(client, db, user_headers):
    """ZH: default 永遠排第一 —— 那是既有使用者唯一有東西的一份。"""
    from app import models
    db.add(models.LabSession(user_id=_uid(db), session_name=lm.DEFAULT_SESSION,
                             volume_name="home_x", base_image="i", status="stopped"))
    db.commit()
    client.post("/api/v1/lab/sessions", headers=user_headers, json={"display_name": "aaa"})
    body = client.get("/api/v1/lab/sessions", headers=user_headers).json()
    assert body["sessions"][0]["session_name"] == lm.DEFAULT_SESSION


def test_cannot_exceed_the_limit(client, db, user_headers, monkeypatch):
    """ZH: 每人要有上限 —— 沒有的話一個人可以開一百個 volume，
       而 volume 不佔 CPU 只佔磁碟，沒有人會發現。
    """
    monkeypatch.setattr(lm, "MAX_SESSIONS_PER_USER", 2)
    for i in range(2):
        assert client.post("/api/v1/lab/sessions", headers=user_headers,
                           json={"display_name": f"w{i}"}).status_code == 200
    r = client.post("/api/v1/lab/sessions", headers=user_headers,
                    json={"display_name": "太多了"})
    assert r.status_code == 400, r.text


def test_cannot_delete_the_default_one(client, db, user_headers):
    """ZH: 🔴 預設那一份不能刪 —— 那是既有使用者的工作區。"""
    r = client.delete(f"/api/v1/lab/sessions/{lm.DEFAULT_SESSION}", headers=user_headers)
    assert r.status_code == 409, r.text


def test_cannot_delete_someone_elses(client, db):
    """ZH: 別人的存檔刪不掉（查詢一律綁自己的 user_id）。"""
    make_user(db, username="alice", email="a@example.com")
    make_user(db, username="bob", email="b@example.com")
    alice, bob = auth_headers(client, "alice"), auth_headers(client, "bob")
    slug = client.post("/api/v1/lab/sessions", headers=alice,
                       json={"display_name": "alice ws"}).json()["session_name"]

    assert client.delete(f"/api/v1/lab/sessions/{slug}", headers=bob).status_code == 404
    # ZH: 而且真的還在
    names = [s["session_name"] for s in
             client.get("/api/v1/lab/sessions", headers=alice).json()["sessions"]]
    assert slug in names


def test_list_does_not_leak_other_users_workspaces(client, db):
    """ZH: 🔴 列表**只能**回自己的。

    ZH: 陽性對照抓到的：原本只斷言「自己的在裡面」，
        那樣把 user_id 過濾拿掉也照樣綠 —— 因為自己的確實還在裡面。
        要斷言的是**別人的不在**。
    """
    make_user(db, username="alice", email="a@example.com")
    make_user(db, username="bob", email="b@example.com")
    alice, bob = auth_headers(client, "alice"), auth_headers(client, "bob")

    alice_slug = client.post("/api/v1/lab/sessions", headers=alice,
                             json={"display_name": "alice secret project"}
                             ).json()["session_name"]
    bob_body = client.get("/api/v1/lab/sessions", headers=bob).json()

    names = [s["session_name"] for s in bob_body["sessions"]]
    displays = [s["display_name"] for s in bob_body["sessions"]]
    assert alice_slug not in names, names
    assert "alice secret project" not in displays, displays


def test_default_stays_in_the_list_after_creating_another(client, db, user_headers):
    """ZH: 🔴 建了第二份之後，`default` **不可以從列表裡消失**。

    ZH: 實測抓到的缺陷（不是想出來的）：`default` 要等使用者按過「開啟」才會有 DB 列，
        而補 default 的後備只在「一列都沒有」時觸發 —— 於是既有使用者一新增存檔，
        **他唯一真的有資料的那一份就從畫面上不見了**。

    ZH: 上面兩條測試都繞過了這個情況：一條測「完全沒有」、一條自己先插了 default 列。
        兩條都綠，缺陷照樣在。這裡測的是不變量本身：**default 永遠在**。
    """
    client.post("/api/v1/lab/sessions", headers=user_headers,
                json={"display_name": "第二份"})
    names = [s["session_name"] for s in
             client.get("/api/v1/lab/sessions", headers=user_headers).json()["sessions"]]
    assert lm.DEFAULT_SESSION in names, names
    assert names[0] == lm.DEFAULT_SESSION, names


def test_new_workspace_is_not_marked_as_recently_used(client, db, user_headers):
    """ZH: 剛建好、還沒開過的存檔，`last_activity` 必須是 None。

    ZH: 實測看到的：畫面寫「最後使用：今天 09:22」，而使用者根本沒開過它。
        原因是欄位的 `default=now` —— 建立時不明確寫 None 就會被填上「現在」。
        這不是版面問題，是**畫面在陳述一件沒發生過的事**。
    """
    from app import models
    slug = client.post("/api/v1/lab/sessions", headers=user_headers,
                       json={"display_name": "沒開過"}).json()["session_name"]
    row = (db.query(models.LabSession)
           .filter_by(user_id=_uid(db), session_name=slug).first())
    assert row.last_activity is None

    got = [s for s in client.get("/api/v1/lab/sessions", headers=user_headers).json()["sessions"]
           if s["session_name"] == slug][0]
    assert got["last_activity"] is None, got


# ──────────────────────────────────────────────────────────────────────────
# ZH: 五、🔴 真正啟動容器的那條路
#
# ZH: 上面所有測試全綠的時候，這個功能其實**是壞的**——
#     `lifecycle.start()` 沒有收到存檔名，所以不管使用者選哪一份，
#     啟動的都是 default 的容器與 volume。
#     命名函式對、端點對、DB 對，就是最後那一步把參數掉了。
#     所以這一節測的不是「函式回傳什麼」，而是**真的傳給 docker 的是什麼**。
# ──────────────────────────────────────────────────────────────────────────

class _FakeLifecycle:
    """ZH: 假的容器層 —— 只記下別人叫它做什麼，不碰真的 docker。"""

    def __init__(self):
        self.started = []       # [(user_id, config)]
        self.stopped = []       # [container_id]
        self.client = None

    # ZH: 命名規則要用**真的那一份**，不要在假物件裡重寫一次
    #     （重寫的話這個測試就變成在測我自己抄的規則）
    _container_name = lm.CodeServerLifecycle._container_name
    _volume_name = lm.CodeServerLifecycle._volume_name

    def _ensure_volume(self, user_id, session=lm.DEFAULT_SESSION):
        return self._volume_name(user_id, session)

    def start(self, user_id, config):
        self.started.append((user_id, config))
        session = config.get("session", lm.DEFAULT_SESSION)
        return "cid-" + session, self._container_name(user_id, session)

    def stop(self, container_id):
        self.stopped.append(container_id)


@pytest.fixture
def fake_lc(monkeypatch):
    lc = _FakeLifecycle()
    monkeypatch.setattr(lm, "get_lifecycle", lambda: lc)
    monkeypatch.setattr(lm, "_wait_until_ready", lambda *a, **k: True)
    return lc


def test_starting_a_workspace_uses_that_workspaces_container(client, db, user_headers, fake_lc):
    """ZH: 🔴 開「ws2」就要啟動 ws2 的容器與 volume，不是 default 的。

    ZH: 這是實際存在過的缺陷：`CodeServerLifecycle.start()` 裡寫的是
        `self._container_name(user_id)`（沒帶存檔名），於是每一份存檔
        都掛到同一個 `home_<uid>`。使用者切到「畢業專題」，
        看到的是 default 裡的檔案 —— 不報錯，只是東西不對。
    """
    uid = _uid(db)
    lm.start_session(db, uid, session="ws2")

    assert fake_lc.started, "根本沒有叫 lifecycle.start"
    _, config = fake_lc.started[-1]
    assert config.get("session") == "ws2", config

    lc = lm.CodeServerLifecycle
    from app import models
    row = (db.query(models.LabSession)
           .filter_by(user_id=uid, session_name="ws2").first())
    assert row.volume_name == lc._volume_name(None, uid, "ws2")
    assert row.volume_name != lc._volume_name(None, uid)


def test_the_container_layer_actually_uses_the_workspace_name():
    """ZH: 🔴 真的走 `CodeServerLifecycle.start()`，看它交給 docker 的是什麼名字。

    ZH: 為什麼要單獨一條 —— 上面那條**抓不到這個缺陷**。陽性對照證明的：
        把 `start()` 裡的 `_container_name(user_id, session)` 改回
        `_container_name(user_id)`，上面那條照樣全綠。
        因為假的 lifecycle 把整個 `start()` 換掉了，我修的那兩行根本沒被執行到。
        它驗的是「start_session 有把 session 傳出去」，不是「容器層有用它」。

    ZH: 所以這條把假的東西下移一層：換掉 docker client，讓真的 start() 跑完，
        然後看 `containers.run()` 收到的 name 與 volumes。
    """
    class _FakeVolumes:
        def get(self, name): raise lm.NotFound("no")
        def create(self, name, labels=None): return None

    class _FakeContainers:
        def __init__(self): self.calls = []
        def get(self, name): raise lm.NotFound("no")
        def run(self, **kw):
            self.calls.append(kw)
            return type("C", (), {"id": "cid"})()

    class _FakeClient:
        def __init__(self):
            self.volumes = _FakeVolumes()
            self.containers = _FakeContainers()

    lc = lm.CodeServerLifecycle()
    lc._client = _FakeClient()
    uid = "abc-123-def"

    cid, name = lc.start(uid, {"password": "p", "session": "ws2"})
    kw = lc._client.containers.calls[-1]

    assert name == "cs-abc-123-def-ws2", name
    assert kw["name"] == "cs-abc-123-def-ws2", kw["name"]
    # ZH: 掛的是這一份存檔的 volume，不是 default 的
    mounted = [v for v, spec in kw["volumes"].items() if spec["bind"] == "/home/coder"]
    assert mounted == ["home_abc_123_def_ws2"], kw["volumes"]

    # ZH: 陰性對照 —— 不給 session 時維持原本的名字（既有使用者不能被改名）
    lc.start(uid, {"password": "p"})
    kw2 = lc._client.containers.calls[-1]
    assert kw2["name"] == "cs-abc-123-def", kw2["name"]
    assert [v for v, s in kw2["volumes"].items()
            if s["bind"] == "/home/coder"] == ["home_abc_123_def"]


def test_starting_one_workspace_stops_the_other(client, db, user_headers, fake_lc):
    """ZH: 🔴 一次只開一份 —— 開 B 之前要先關掉還在跑的 A。

    ZH: 這條也是實際缺陷：`_stop_other_running` **定義了但沒有任何呼叫端**，
        所以「一次只開一份」寫在畫面上、寫在註解裡，就是沒有真的執行。
        （記憶裡的「不可達 ≠ 死碼」——這次是反過來：該可達卻不可達。）
    """
    uid = _uid(db)
    lm.start_session(db, uid, session="wsa")
    lm.start_session(db, uid, session="wsb")

    from app import models
    rows = {r.session_name: r.status for r in
            db.query(models.LabSession).filter_by(user_id=uid).all()}
    assert rows.get("wsa") == "stopped", rows
    assert rows.get("wsb") == "running", rows
    assert "cid-wsa" in fake_lc.stopped, fake_lc.stopped


def test_status_reports_the_workspace_that_was_asked_for(client, db, user_headers, fake_lc):
    """ZH: `get_status` 回的 session_name 要是**被問的那一個**。

    ZH: 原本查詢結果覆蓋掉同名參數，所以停止中的存檔回 `session_name: null`，
        執行中的則會把整個 ORM 物件塞進 JSON。
    """
    uid = _uid(db)
    stopped = lm.get_status(db, uid, session="never-opened")
    assert stopped["session_name"] == "never-opened", stopped

    lm.start_session(db, uid, session="wsx")
    running = lm.get_status(db, uid, session="wsx")
    assert running["session_name"] == "wsx", running
    assert isinstance(running["session_name"], str)


def test_deleting_an_account_archives_every_workspace(client, db, user_headers, monkeypatch):
    """ZH: 🔴 刪帳號時**每一份存檔**都要封存，不是只有 default。

    ZH: 原本只處理 `home_<uid>`。多份存檔上線後那等於：其他份的容器還開著、
        volume 沒封存也沒刪 —— 使用者再也沒有那 30 天可還原，
        磁碟上多出永遠沒人認領的孤兒。
    """
    from app import models
    uid = _uid(db)
    for name in ("ws2", "ws3"):
        db.add(models.LabSession(user_id=uid, session_name=name,
                                 volume_name=lm.get_lifecycle()._volume_name(uid, name),
                                 base_image="i", status="stopped"))
    db.commit()

    seen_removed, existing_vols = [], set()
    for sess in (lm.DEFAULT_SESSION, "ws2", "ws3"):
        existing_vols.add(lm.get_lifecycle()._volume_name(uid, sess))

    class _C:
        def __init__(self, n): self.name = n
        def remove(self, force=False): seen_removed.append(self.name)

    class _Vols:
        def get(self, name):
            if name not in existing_vols:
                raise lm.NotFound("no")
            return object()

    class _Containers:
        def get(self, name): return _C(name)

    class _Client:
        volumes, containers = _Vols(), _Containers()

    lc = lm.get_lifecycle()
    monkeypatch.setattr(type(lc), "client", property(lambda self: _Client()))
    monkeypatch.setattr(lm, "_volume_size", lambda n: 123)

    user = db.query(models.User).filter_by(username="testuser").first()
    out = lm.archive_user_lab(db, user, retention_days=30)

    got = {a["session"] for a in out["volumes"]}
    assert got == {lm.DEFAULT_SESSION, "ws2", "ws3"}, got
    # ZH: 每一份的容器都要被移除（不然刪了帳號還有容器在跑）
    assert len(seen_removed) == 3, seen_removed
    # ZH: 每一份都要真的進封存表
    names = {r.volume_name for r in db.query(models.ArchivedLabVolume).all()}
    assert names == existing_vols, names


def test_the_url_points_at_the_workspace_that_was_started(client, db, user_headers, fake_lc):
    """ZH: 🔴 回給前端的網址要帶存檔後綴。

    ZH: 實測抓到的：後端明明啟動了 `cs-<uid>-deep-learning-hw`，
        `_build_url` 卻恆為 `/code/<uid>/` —— 使用者點下去被導到 **default 的容器**，
        看到別份存檔的檔案，而且完全不會報錯。
        （nginx 的 `cs-$1` 與 authz 的前綴比對都早就支援，就差這個字串。）
    """
    uid = _uid(db)
    out = lm.start_session(db, uid, session="ws2")
    assert out["url"].startswith(f"/code/{uid}-ws2/"), out["url"]

    # ZH: 陰性對照 —— default 必須維持原本的網址（既有使用者的書籤不能壞）
    out2 = lm.start_session(db, uid)
    assert out2["url"].startswith(f"/code/{uid}/"), out2["url"]
    assert f"{uid}-" not in out2["url"].split("?")[0].rstrip("/"), out2["url"]


def test_status_without_a_workspace_reports_the_running_one(client, db, user_headers, fake_lc):
    """ZH: `/lab/status` 沒帶 session 時，要回**正在跑的那一份**。

    ZH: 不然畫面會自相矛盾：上方狀態卡「未啟動」、下方清單「執行中」。
        同一個畫面給兩個互斥的答案，比其中一個錯還糟。
    """
    uid = _uid(db)
    lm.start_session(db, uid, session="ws2")

    body = client.get("/api/v1/lab/status", headers=user_headers).json()
    assert body["session_name"] == "ws2", body
    assert body["status"] == "running", body


def test_status_without_a_workspace_falls_back_to_default(client, db, user_headers):
    """ZH: 陰性對照 —— 都沒在跑時仍是 default（升級前的所有人結果不變）。"""
    body = client.get("/api/v1/lab/status", headers=user_headers).json()
    assert body["session_name"] == lm.DEFAULT_SESSION, body
