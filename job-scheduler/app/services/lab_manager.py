"""
==============================================================================
Service: Lab Manager — code-server 容器生命週期 | code-server lifecycle
==============================================================================
ZH: 用途：管理每位使用者的 code-server CPU 容器
    - POST /lab/start  → start_session()
    - POST /lab/stop   → stop_session()
    - GET  /lab/status → session_status()
    - 背景任務每 1 分鐘掃描 idle / hard-limit 並關閉
    - secrets 透過 secrets_service 自動注入容器 env
    - per-user volume `home_<user_id>` 動態建立

EN: Purpose: Manage per-user code-server CPU containers
    - lifecycle bound to lab_sessions table
    - idle + hard-limit enforcement via background scanner
    - secrets injection via secrets_service

ZH: v2.0 設計：採 Protocol 抽象 ContainerLifecycle，v2.1 可加 KernelLifecycle
    而不動 v2.0 的 schema 與 API
EN: v2.0 uses Protocol abstraction; v2.1 can add KernelLifecycle without
    touching v2.0 schema / API
==============================================================================
"""

from __future__ import annotations

import json
import logging
import os
import secrets as _stdlib_secrets
from datetime import datetime, timedelta, timezone
from typing import Optional, Protocol, Dict

import docker
from docker.errors import NotFound, APIError
from sqlalchemy.orm import Session

from .. import models
from ..config import SCHEDULER_POLICY, settings
from . import secrets_service, quota_service

logger = logging.getLogger(__name__)

DEFAULT_SESSION = "default"
# ZH: 每人最多幾份。**要有上限**——沒有的話一個人可以開一百個 volume，
#     而 volume 是不佔 CPU 但佔磁碟的東西，沒有人會發現。
MAX_SESSIONS_PER_USER = int(os.environ.get("LAB_MAX_SESSIONS", "5"))

# ZH: session_name 會進**容器名與網址**，所以只允許 DNS-safe 的字元。
#     使用者看得懂的名字（可中文）存在 display_name，兩者刻意分開。
_SLUG_OK = "abcdefghijklmnopqrstuvwxyz0123456789-"



# ==============================================================================
# ZH: ContainerLifecycle Protocol（v2.1 預留擴充點）
# EN: ContainerLifecycle Protocol (v2.1 extension point)
# ==============================================================================

class ContainerLifecycle(Protocol):
    """
    ZH: 所有容器類型（code-server、未來 Jupyter Kernel）的共通介面
    EN: Common interface for all container types

    @node job-scheduler/app/services/lab_manager.py::ContainerLifecycle
    """

    def start(self, user_id: str, config: dict) -> tuple[str, str]: ...
    """ZH: 啟動容器，回傳 (container_id, container_name) | EN: Start container, returns ids"""

    def stop(self, container_id: str) -> None: ...
    """ZH: 停止並移除容器 | EN: Stop and remove container"""

    def status(self, container_id: str) -> str: ...
    """ZH: 查詢容器狀態 | EN: Query container status"""


# ==============================================================================
# ZH: CodeServerLifecycle — v2.0 唯一實作
# EN: CodeServerLifecycle — sole v2.0 implementation
# ==============================================================================

class CodeServerLifecycle:
    """
    ZH: 用 Docker SDK 啟動 code-server 容器
    EN: Spawns code-server containers via Docker SDK

    @node job-scheduler/app/services/lab_manager.py::CodeServerLifecycle
    """

    def __init__(self):
        """@node job-scheduler/app/services/lab_manager.py::CodeServerLifecycle.__init__"""
        self._client: Optional[docker.DockerClient] = None

    @property
    def client(self) -> docker.DockerClient:
        """@node job-scheduler/app/services/lab_manager.py::CodeServerLifecycle.client"""
        if self._client is None:
            self._client = docker.from_env()
        return self._client

    def _container_name(self, user_id: str, session: str = DEFAULT_SESSION) -> str:
        # ZH: 容器名稱 cs-<user_id>（user_id 已是 UUID，符合 DNS-safe）
        # EN: Container name cs-<user_id> (user_id is UUID, DNS-safe)
        # ZH: 🔴 v3.6 —— `default` **維持原本的名字**，不加後綴。
        #     既有使用者的容器與 volume 都叫這個；改名等於要遷移正在用的東西，
        #     風險與收益不成比例。新增的存檔才帶 `-<slot>`。
        """@node job-scheduler/app/services/lab_manager.py::CodeServerLifecycle._container_name"""
        safe = user_id.replace("_", "-")[:60]
        return f"cs-{safe}" if session == DEFAULT_SESSION else f"cs-{safe}-{session}"

    def _volume_name(self, user_id: str, session: str = DEFAULT_SESSION) -> str:
        """ZH: 對應的 home volume 名稱 | EN: Home volume name

        ZH: 同上 —— `default` 沿用 `home_<uid>`，不遷移既有資料。

        @node job-scheduler/app/services/lab_manager.py::CodeServerLifecycle._volume_name
        """
        safe = user_id.replace("-", "_")[:60]
        return f"home_{safe}" if session == DEFAULT_SESSION else f"home_{safe}_{session}"

    def _ensure_volume(self, user_id: str, session: str = DEFAULT_SESSION) -> str:
        """ZH: 確保 per-user volume 存在 | EN: Ensure per-user volume exists

        @node job-scheduler/app/services/lab_manager.py::CodeServerLifecycle._ensure_volume
        """
        name = self._volume_name(user_id, session)
        try:
            self.client.volumes.get(name)
        except NotFound:
            self.client.volumes.create(name=name, labels={
                "aibase.user_id": user_id,
                "aibase.purpose": "home",
                # ZH: v3.6 —— 盤點與回收要分得出這是哪一份存檔
                "aibase.session": session,
            })
            logger.info("Created volume %s for user %s", name, user_id[:8])
        return name

    def start(self, user_id: str, config: dict) -> tuple[str, str]:
        """
        ZH: 啟動 code-server 容器
        EN: Start code-server container

        config 必要欄位 / required keys:
            - base_image:    str（編輯時的 base image，不是訓練 image）
            - cpu_quota:     float (CPU cores)
            - mem_quota_mb:  int
            - password:      str (one-time password for code-server access)
            - env:           dict[str, str] (secrets 與其他 env)

        @node job-scheduler/app/services/lab_manager.py::CodeServerLifecycle.start
        """
        # ZH: 🔴 v3.6 —— 這兩行原本沒有帶 session，於是**不管使用者選哪一份存檔，
        #     啟動的都是 default 的容器與 volume**。功能等於沒有，而且不會報錯：
        #     使用者切到「畢業專題」，看到的卻是 default 裡的檔案。
        session = config.get("session", DEFAULT_SESSION)
        name = self._container_name(user_id, session)
        volume_name = self._ensure_volume(user_id, session)

        # ZH: 若已存在同名容器（殘留 state），先移除
        # EN: Remove stale container with same name if exists
        try:
            old = self.client.containers.get(name)
            old.remove(force=True)
            logger.info("Removed stale container %s before start", name)
        except NotFound:
            pass

        env_vars = {
            "PASSWORD": config["password"],          # code-server 認證
            "PUID": "1000",
            "PGID": "1000",
            **config.get("env", {}),
        }

        try:
            container = self.client.containers.run(
                image=config.get("base_image", "aibase/code-server:2026-spring"),
                name=name,
                detach=True,
                environment=env_vars,
                volumes={
                    volume_name:      {"bind": "/home/coder",  "mode": "rw"},
                    "aibase_shared_models": {"bind": "/opt/models", "mode": "ro"},
                },
                network="ai-platform-net",
                cpu_period=100000,
                cpu_quota=int(config.get("cpu_quota", 0.5) * 100000),
                mem_limit=f"{config.get('mem_quota_mb', 2048)}m",
                labels={
                    "aibase.role":    "code-server",
                    "aibase.user_id": user_id,
                },
                restart_policy={"Name": "no"},      # 我們自己管，不要 docker auto-restart
            )
            logger.info("Started code-server container %s for user %s", name, user_id[:8])
            return container.id, name
        except APIError as e:
            logger.error("Failed to start container %s: %s", name, e)
            raise

    def stop(self, container_id: str) -> None:
        """ZH: 停止並移除容器 | EN: Stop and remove container

        @node job-scheduler/app/services/lab_manager.py::CodeServerLifecycle.stop
        """
        try:
            c = self.client.containers.get(container_id)
            c.stop(timeout=10)
            c.remove(force=True)
            logger.info("Stopped & removed container %s", container_id[:12])
        except NotFound:
            logger.debug("Container %s not found (already removed)", container_id[:12])
        except APIError as e:
            logger.warning("Error stopping container %s: %s", container_id[:12], e)

    def status(self, container_id: str) -> str:
        """ZH: 回傳 running/exited/missing | EN: Returns running/exited/missing

        @node job-scheduler/app/services/lab_manager.py::CodeServerLifecycle.status
        """
        try:
            c = self.client.containers.get(container_id)
            return c.status
        except NotFound:
            return "missing"


# ZH: 模組級單例（避免 Docker client 重複建立）
# EN: Module-level singleton (avoid repeated Docker client init)
_codeserver: Optional[CodeServerLifecycle] = None


def get_lifecycle() -> CodeServerLifecycle:
    """@node job-scheduler/app/services/lab_manager.py::get_lifecycle"""
    global _codeserver
    if _codeserver is None:
        _codeserver = CodeServerLifecycle()
    return _codeserver


# ==============================================================================
# ZH: v2.6 程式家教讀檔 — 供 assistant「程式家教」模式讀使用者「自己」的 Lab 檔案
# EN: v2.6 code-tutor file access — read the user's OWN lab files for the assistant
# ZH: 安全：只讀該使用者自己的 cs-<uid> 容器、路徑限 /home/coder、拒穿越、單檔 size cap
# ==============================================================================

LAB_HOME = "/home/coder"
TUTOR_FILE_EXTS = (".py", ".ipynb", ".txt", ".md", ".csv", ".json",
                   ".js", ".ts", ".java", ".c", ".cpp", ".h", ".sh", ".yaml", ".yml")
_MAX_TUTOR_FILE_BYTES = 64 * 1024  # ZH: 單檔最多讀 64KB（超過截斷）


def list_user_files(user_id: str, limit: int = 200) -> dict:
    """ZH: 列出使用者自己容器內 /home/coder 下可挑選的檔（相對路徑）。
       EN: List selectable files under /home/coder in the user's OWN container.
       回傳 {"running": bool, "files": [rel_path], "reason": str|None}

    @node job-scheduler/app/services/lab_manager.py::list_user_files
    """
    # ZH: 用 label 找正在跑的那一份，不要寫死 default（見 running_container_for）
    c = running_container_for(user_id)
    if c is None:
        return {"running": False, "files": [], "reason": "lab_not_started"}

    name_expr = " -o ".join([f"-name '*{e}'" for e in TUTOR_FILE_EXTS])
    cmd = (
        f"sh -c \"find {LAB_HOME} -type f \\( {name_expr} \\) "
        f"-not -path '*/.*' -not -path '*/node_modules/*' -not -path '*/__pycache__/*' "
        f"2>/dev/null | head -n {int(limit)}\""
    )
    try:
        res = c.exec_run(cmd)
        out = res.output.decode("utf-8", errors="replace") if res.output else ""
    except APIError as e:
        logger.warning("list_user_files exec failed for %s: %s", name, e)
        return {"running": True, "files": [], "reason": "exec_failed"}

    files = []
    for line in out.splitlines():
        line = line.strip()
        if line.startswith(LAB_HOME + "/"):
            files.append(line[len(LAB_HOME) + 1:])
    files.sort()
    return {"running": True, "files": files, "reason": None}


def read_user_file(user_id: str, rel_path: str) -> dict:
    """ZH: 讀使用者自己容器內 /home/coder/<rel_path> 的文字（安全檢查 + size cap）。
       EN: Read text of /home/coder/<rel_path> from the user's OWN container.
       回傳 {"ok": bool, "content": str, "path": str, "truncated": bool, "reason": str|None}

    @node job-scheduler/app/services/lab_manager.py::read_user_file
    """
    import io
    import tarfile
    import posixpath

    # ZH: 路徑安全 — 正規化後必須仍落在 /home/coder 下，拒絕 .. 穿越
    rel = (rel_path or "").lstrip("/")
    target = posixpath.normpath(posixpath.join(LAB_HOME, rel))
    if target != LAB_HOME and not target.startswith(LAB_HOME + "/"):
        return {"ok": False, "content": "", "path": rel_path, "truncated": False, "reason": "path_forbidden"}

    # ZH: 同上 —— 使用者開的可能不是 default 那一份
    c = running_container_for(user_id)
    if c is None:
        return {"ok": False, "content": "", "path": rel, "truncated": False, "reason": "lab_not_started"}

    try:
        stream, _stat = c.get_archive(target)
    except NotFound:
        return {"ok": False, "content": "", "path": rel, "truncated": False, "reason": "not_found"}
    except APIError as e:
        logger.warning("read_user_file get_archive failed for %s:%s: %s", name, target, e)
        return {"ok": False, "content": "", "path": rel, "truncated": False, "reason": "read_failed"}

    raw = b"".join(stream)  # ZH: get_archive 回 tar 串流 | EN: stream yields a tar archive
    try:
        with tarfile.open(fileobj=io.BytesIO(raw)) as tf:
            member = next((m for m in tf.getmembers() if m.isfile()), None)
            if member is None:
                return {"ok": False, "content": "", "path": rel, "truncated": False, "reason": "not_a_file"}
            fobj = tf.extractfile(member)
            data = fobj.read(_MAX_TUTOR_FILE_BYTES + 1) if fobj else b""
    except (tarfile.TarError, OSError) as e:
        logger.warning("read_user_file tar parse failed: %s", e)
        return {"ok": False, "content": "", "path": rel, "truncated": False, "reason": "parse_failed"}

    truncated = len(data) > _MAX_TUTOR_FILE_BYTES
    text = data[:_MAX_TUTOR_FILE_BYTES].decode("utf-8", errors="replace")
    return {"ok": True, "content": text, "path": rel, "truncated": truncated, "reason": None}


# ==============================================================================
# ZH: 高階 API — 給 router 與 scheduler 呼叫
# EN: High-level API — called by routers & scheduler
# ==============================================================================

def _wait_until_ready(container_name: str, timeout: float = 25.0, interval: float = 0.7) -> bool:
    """ZH: 輪詢 code-server(容器:8080) 直到能服務，避免容器剛起、前端就開頁面 → 503。
       EN: Poll code-server (container:8080) until it serves, so the new tab won't 503.
       任何 <500 的 HTTP 回應(200/302/401)都代表 code-server 已在服務。

    @node job-scheduler/app/services/lab_manager.py::_wait_until_ready
    """
    import time as _time
    import httpx
    url = f"http://{container_name}:8080/"
    deadline = _time.monotonic() + timeout
    while _time.monotonic() < deadline:
        try:
            r = httpx.get(url, timeout=2.0, follow_redirects=False)
            if r.status_code < 500:
                logger.info("code-server %s ready (HTTP %d)", container_name, r.status_code)
                return True
        except Exception:
            pass
        _time.sleep(interval)
    logger.warning("code-server %s not ready after %.0fs (returning anyway)", container_name, timeout)
    return False


# ==============================================================================
# ZH: v3.6 多份存檔 | EN: v3.6 Multiple workspaces
# ==============================================================================
# ZH: `lab_sessions` 的主鍵本來就是 `(user_id, session_name)` —— 資料模型一直支援多份，
#     是程式碼把它釘死成 "default"。這裡把它解開。
#
# ZH: 🔴 **一次只開一份**（擁有者裁定）：多份是「存檔」不是「同時開多個工作區」。
#     每個容器吃 0.5 CPU + 2 GB RAM，開三份就是三倍；而切換存檔＝關掉舊的開新的，
#     檔案全部保留。資源模型、閒置回收、同時在線上限都不必重新設計。


def _slugify(name: str, taken: set) -> str:
    """ZH: 把使用者取的名字轉成可以進容器名／網址的鍵；撞名就加序號。

    ZH: 中文會被清光，那時退回 `ws<N>` —— 名字看得懂這件事由 display_name 負責，
        這個鍵只要唯一且安全。

    @node job-scheduler/app/services/lab_manager.py::_slugify
    """
    base = "".join(c if c in _SLUG_OK else "-" for c in (name or "").strip().lower())
    base = "-".join(x for x in base.split("-") if x)[:24]
    if not base or base == DEFAULT_SESSION:
        base = "ws"
    slug = base
    n = 2
    while slug in taken:
        slug = f"{base}-{n}"
        n += 1
    return slug


def running_container_for(user_id: str):
    """ZH: 這個人**目前正在跑**的 code-server 容器（沒有就 None）。

    ZH: 為什麼不用 `_container_name(user_id)` —— 那寫死 default 那一份。
        多份存檔上線後，使用者開的是「畢業專題」時，小基（RAG 家教）
        會去找 `cs-<uid>`、找不到，然後回「實驗室還沒啟動」——
        而畫面上實驗室明明開著。

    ZH: 改用 docker label 找：容器啟動時就帶了 `aibase.role=code-server`
        與 `aibase.user_id`。一次只開一份，所以符合的最多一個。
        用 label 而不是自己拼名字，好處是**命名規則以後再改也不會漏掉這裡**。

    @node job-scheduler/app/services/lab_manager.py::running_container_for
    """
    lc = get_lifecycle()
    try:
        found = lc.client.containers.list(filters={
            "label": [f"aibase.user_id={user_id}", "aibase.role=code-server"],
            "status": "running",
        })
    except Exception as e:  # noqa: BLE001 - docker 不可用時當作沒開
        logger.warning("列出使用者 %s 的 Lab 容器失敗: %s", user_id[:8], e)
        return None
    return found[0] if found else None


def current_session_name(db: Session, user_id: str) -> str:
    """ZH: 這個人「現在算哪一份」—— 有在跑的就是那一份，都沒跑就是 default。

    ZH: 為什麼需要這個：狀態卡如果固定查 default，畫面會**自相矛盾**——
        上面寫「未啟動」，下面的存檔清單同時標著「執行中」。
        同一個畫面給出兩個互斥的答案，比其中一個是錯的還糟。

    ZH: 只有一份存檔的人（也就是升級前的所有人）結果完全不變：
        他在跑的就是 default，沒跑也是 default。

    @node job-scheduler/app/services/lab_manager.py::current_session_name
    """
    row = (db.query(models.LabSession)
           .filter(models.LabSession.user_id == user_id,
                   models.LabSession.status.in_(("running", "starting")))
           .first())
    return row.session_name if row else DEFAULT_SESSION


def volume_name_for(user_id: str, session: str = DEFAULT_SESSION) -> str:
    """ZH: 某人某一份存檔的 volume 名。**唯一定義** —— 別處要用請呼叫這裡。

    ZH: 🔴 這支的存在理由是一個實際發生過的缺陷：`routers/worker.py` 自己寫了
        `f"home_{user_id}"`，而 lab_manager 是 `home_<uid 的連字號換成底線>`。
        兩個名字不一樣，於是實驗室模式的任務掛到了一個 **docker 自動建的空 volume**
        ——不報錯、資料不在、訓練出沒有意義的結果。
        （用 volume 標籤查證過：底線版有 `aibase.purpose=home`，連字號版沒有標籤，
          而有一位真實使用者兩種都有。）

    @node job-scheduler/app/services/lab_manager.py::volume_name_for
    """
    return get_lifecycle()._volume_name(user_id, session)


def list_sessions(db: Session, user_id: str) -> list[dict]:
    """ZH: 這個人的所有存檔（含還沒建過容器的）。

    @node job-scheduler/app/services/lab_manager.py::list_sessions
    """
    rows = (db.query(models.LabSession)
            .filter(models.LabSession.user_id == user_id)
            .all())
    out = []
    for r in rows:
        out.append({
            "session_name": r.session_name,
            "display_name": r.display_name or ("我的實驗室" if r.session_name == DEFAULT_SESSION
                                               else r.session_name),
            "status": r.status,
            "last_activity": r.last_activity,
            "base_image": r.base_image,
            "url": _build_url(user_id, r).get("url"),
        })
    # ZH: 🔴 `default` **一定要在列表裡**，就算它還沒有 DB 列。
    #     實測抓到的：`default` 要等使用者按過「開啟」才會有列，
    #     所以他一新增第二份存檔，**唯一真的有資料的那一份就從畫面上消失**。
    #     （原本補 default 的後備寫在路由層，而且只在「一列都沒有」時才觸發——
    #       兩條測試剛好一條測空的、一條自己先插了 default 列，都繞過了這個情況。）
    if not any(d["session_name"] == DEFAULT_SESSION for d in out):
        out.append({
            "session_name": DEFAULT_SESSION,
            "display_name": "我的實驗室",
            "status": "stopped",
            "last_activity": None,
            "base_image": None,
            "url": None,
        })

    # ZH: default 永遠排第一 —— 那是既有使用者唯一有東西的那一份。
    out.sort(key=lambda d: (d["session_name"] != DEFAULT_SESSION, d["display_name"]))
    return out


def create_session(db: Session, user_id: str, display_name: str) -> dict:
    """ZH: 新增一份存檔（只建紀錄，容器與 volume 等到啟動時才建）。

    ZH: 不預先建 volume：使用者可能建了就忘了，而空 volume 也要佔磁碟與盤點。
        等他真的啟動再建。

    @node job-scheduler/app/services/lab_manager.py::create_session
    """
    existing = {r.session_name for r in db.query(models.LabSession)
                .filter(models.LabSession.user_id == user_id).all()}
    if len(existing) >= MAX_SESSIONS_PER_USER:
        raise ValueError(f"最多只能有 {MAX_SESSIONS_PER_USER} 份存檔")

    slug = _slugify(display_name, existing)
    row = models.LabSession(
        user_id=user_id,
        session_name=slug,
        display_name=(display_name or "").strip()[:60] or slug,
        volume_name=get_lifecycle()._volume_name(user_id, slug),
        # ZH: 與 start_session 用同一個來源（yaml 的 codeserver_resources.default_image）。
        #     ⚠ 我原本寫成 `_default_image(db)` —— 那個函式**不存在**，是我憑空假設的。
        base_image=SCHEDULER_POLICY.get("codeserver_resources", {}).get(
            "default_image", "aibase/code-server:2026-spring"),
        status="stopped",
        # ZH: 🔴 明確寫 None —— 這個欄位的 default 是「現在」，
        #     所以剛建好的存檔會顯示「最後使用：今天 09:22」，
        #     而使用者根本還沒開過它。這裡要的是「還沒開過」。
        last_activity=None,
    )
    db.add(row)
    db.commit()
    return {"session_name": slug, "display_name": row.display_name}


def delete_session(db: Session, user_id: str, session: str) -> bool:
    """ZH: 刪掉一份存檔（紀錄 + volume）。**default 不可刪** —— 那是他原本的工作區。

    ZH: 執行中的不給刪：正在跑的容器抽掉底下的 volume 會壞得很難查。

    @node job-scheduler/app/services/lab_manager.py::delete_session
    """
    if session == DEFAULT_SESSION:
        raise ValueError("預設的那一份不能刪除")
    row = (db.query(models.LabSession)
           .filter(models.LabSession.user_id == user_id,
                   models.LabSession.session_name == session).first())
    if not row:
        return False
    if row.status in ("running", "starting"):
        raise ValueError("這一份正在執行中，請先關閉再刪除")

    try:
        get_lifecycle().client.volumes.get(row.volume_name).remove(force=True)
    except Exception as e:  # noqa: BLE001 - volume 不見了不該擋住刪除紀錄
        logger.warning("Could not remove volume %s: %s", row.volume_name, e)
    db.delete(row)
    db.commit()
    return True


def _stop_other_running(db: Session, user_id: str, keep: str) -> Optional[str]:
    """ZH: 關掉這個人**其他**正在跑的存檔，回傳被關掉的那一個（沒有就 None）。

    ZH: 🔴 一次只開一份（擁有者裁定）：多份是「存檔」不是「同時開多個工作區」。
        每個容器吃 0.5 CPU + 2 GB RAM，允許並行等於把資源模型、閒置回收、
        同時在線上限全部要重新設計。切換＝關舊開新，**檔案全部保留**。

    @node job-scheduler/app/services/lab_manager.py::_stop_other_running
    """
    other = (db.query(models.LabSession)
             .filter(models.LabSession.user_id == user_id,
                     models.LabSession.session_name != keep,
                     models.LabSession.status.in_(("running", "starting")))
             .first())
    if not other:
        return None
    stop_session(db, user_id, reason="switched_workspace", session=other.session_name)
    return other.session_name


def start_session(db: Session, user_id: str, base_image: Optional[str] = None,
                  session: str = DEFAULT_SESSION) -> dict:
    """
    ZH: 啟動使用者的 code-server session（含配額檢查、secrets 注入、DB 紀錄）
    EN: Start a user's code-server session (with quota check, secrets injection, DB record)

    Returns:
        {
            "url": "/code/<user_id>/?folder=/home/coder/projects",
            "password": "<one-time password for this session>",
            "container_name": "cs-<user_id>",
            "started_at": "...",
        }

    @node job-scheduler/app/services/lab_manager.py::start_session
    """
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise ValueError(f"User {user_id} not found")

    # ZH: 配額檢查 | EN: Quota check
    allowed, reason = quota_service.can_start_session(db, user_id)
    if not allowed:
        raise PermissionError(f"Cannot start session: {reason}")

    # ZH: 找既有 session row（UNIQUE(user_id, session_name) 保證最多一筆）
    #     若仍 running 直接回傳；否則 reuse 該 row 重新啟動，避免 INSERT 撞 UNIQUE
    # EN: Find existing row (UNIQUE constraint guarantees at most one).
    #     If still running → return URL; otherwise reuse the row to avoid UNIQUE conflict on re-start
    # v2.1 修正：原本只查 running/starting，導致 stopped 殘留 row 讓下次 start INSERT 撞 UNIQUE
    existing = db.query(models.LabSession).filter(
        models.LabSession.user_id == user_id,
        models.LabSession.session_name == session,
    ).first()
    if existing and existing.status == "running":
        return _build_url(user_id, existing)

    lc = get_lifecycle()

    # ZH: 🔴 一次只開一份 —— 先關掉這個人其他還在跑的存檔。
    #     這一步原本漏掉了（`_stop_other_running` 定義了卻沒有任何呼叫端），
    #     所以「一次只開一份」實際上沒有生效。
    _stop_other_running(db, user_id, keep=session)

    # ZH: 預設 image 從 yaml 讀 | EN: Default image from yaml
    if base_image is None:
        base_image = SCHEDULER_POLICY.get("codeserver_resources", {}).get(
            "default_image", "aibase/code-server:2026-spring"
        )

    # ZH: 注入該 user 的所有 secrets
    # EN: Inject all user secrets as docker env
    secret_env = secrets_service.build_docker_env(db, user_id)

    # ZH: 產生 one-time password
    # EN: Generate one-time password
    password = _stdlib_secrets.token_urlsafe(24)

    # ZH: 設定 LabSession row 為 starting
    # EN: Set LabSession row to starting
    # ZH: 🔴 這裡原本叫 `session`，把同名的參數（存檔名）蓋掉了——
    #     於是下面 `lc.start()` 再也拿不到存檔名。改名成 row。
    row = existing or models.LabSession(
        user_id=user_id,
        session_name=session,
        volume_name=lc._volume_name(user_id, session),
        base_image=base_image,
    )
    row.status = "starting"
    row.base_image = base_image
    row.started_at = datetime.now(timezone.utc)
    row.last_activity = datetime.now(timezone.utc)
    if not existing:
        db.add(row)
    db.commit()

    # ZH: 啟動容器
    # EN: Start container
    cpu_quota = SCHEDULER_POLICY.get("codeserver_resources", {}).get("cpu_quota", 0.5)
    mem_quota = SCHEDULER_POLICY.get("codeserver_resources", {}).get("mem_quota_mb", 2048)
    try:
        container_id, container_name = lc.start(user_id, {
            "base_image":   base_image,
            "cpu_quota":    cpu_quota,
            "mem_quota_mb": mem_quota,
            "password":     password,
            "env":          secret_env,
            # ZH: 🔴 少了這個鍵，開哪一份存檔都會啟動 default 的容器
            "session":      session,
        })
    except Exception as e:
        row.status = "stopped"
        db.commit()
        raise RuntimeError(f"Failed to start container: {e}")

    row.container_id = container_id
    row.container_name = container_name
    # v2.4: 等 code-server HTTP 就緒再回傳，避免前端開分頁時容器尚未服務 → 503
    _wait_until_ready(container_name, timeout=25.0)
    row.status = "running"
    row.cpu_quota = cpu_quota
    row.mem_quota_mb = mem_quota
    db.commit()
    db.refresh(row)

    return {
        **_build_url(user_id, row),
        "password": password,
    }


def stop_session(db: Session, user_id: str, reason: str = "user_requested",
                 session: str = DEFAULT_SESSION) -> bool:
    """
    ZH: 停止使用者的 session，並累加今日已用時長
    EN: Stop user session and accumulate today's usage

    @node job-scheduler/app/services/lab_manager.py::stop_session
    """
    # ZH: 查詢結果叫 row，不要叫 session —— 那會蓋掉同名的參數（存檔名）。
    #     這個寫法在本檔已經害出過兩個缺陷（get_status 回錯的 session_name、
    #     start_session 啟動錯的容器），所以全檔統一。
    row = db.query(models.LabSession).filter(
        models.LabSession.user_id == user_id,
        models.LabSession.session_name == session,
    ).first()
    if not row or row.status == "stopped":
        return False

    elapsed = 0
    if row.started_at:
        started = row.started_at
        if started.tzinfo is None:
            started = started.replace(tzinfo=timezone.utc)
        elapsed = int((datetime.now(timezone.utc) - started).total_seconds())

    if row.container_id:
        get_lifecycle().stop(row.container_id)

    row.status = "stopped"
    row.container_id = None
    db.commit()

    if elapsed > 0:
        quota_service.increment_usage(db, user_id, elapsed)

    logger.info("Session stopped for user %s (reason=%s, elapsed=%ds)",
                user_id[:8], reason, elapsed)
    return True


def get_status(db: Session, user_id: str, session: str = DEFAULT_SESSION) -> dict:
    """
    ZH: 取得使用者目前的 session 完整狀態（給 /lab/status endpoint）
    EN: Get full session status for /lab/status endpoint

    @node job-scheduler/app/services/lab_manager.py::get_status
    """
    # ZH: 🔴 查詢結果**不可以叫 session** —— 那會蓋掉同名的參數（存檔名）。
    #     這裡原本就是這樣寫的，於是下面的 `"session_name": session` 回的是
    #     **ORM 物件**（或找不到時的 None），而不是存檔名。
    #     v3.6 之前 session_name 恆為 "default" 所以看不出來；多份存檔一開就會露餡。
    row = db.query(models.LabSession).filter(
        models.LabSession.user_id == user_id,
        models.LabSession.session_name == session,
    ).first()

    # 取使用者 secrets 名稱清單（masked）
    masked = secrets_service.list_secrets_masked(db, user_id)

    user = db.query(models.User).filter(models.User.id == user_id).first()
    limits = quota_service.get_session_limits(user.role if user else "student")
    remaining_min = quota_service.get_today_remaining_minutes(db, user_id)

    if not row or row.status == "stopped":
        return {
            "session_name": session,
            "status": "stopped",
            "limits": limits,
            "today_remaining_min": remaining_min,
            "injected_secrets": masked,
        }

    now = datetime.now(timezone.utc)
    started = row.started_at
    if started and started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)
    last_act = row.last_activity
    if last_act and last_act.tzinfo is None:
        last_act = last_act.replace(tzinfo=timezone.utc)

    return {
        "session_name": session,
        "status": row.status,
        "started_at": started.isoformat() if started else None,
        "last_activity": last_act.isoformat() if last_act else None,
        "idle_seconds": int((now - last_act).total_seconds()) if last_act else None,
        "elapsed_seconds": int((now - started).total_seconds()) if started else None,
        "base_image": row.base_image,
        "limits": limits,
        "today_remaining_min": remaining_min,
        "injected_secrets": masked,
        "url": _build_url(user_id, row).get("url"),
    }


def touch_activity(db: Session, user_id: str, session: str = DEFAULT_SESSION) -> None:
    """
    ZH: 更新 last_activity（heartbeat endpoint 呼叫）
    EN: Update last_activity (called by heartbeat endpoint)

    @node job-scheduler/app/services/lab_manager.py::touch_activity
    """
    # ZH: ⚠ 區域變數不要也叫 session —— 那會遮住參數。原本能動只是因為
    #     右邊先求值；下一個人在中間插一行就壞了，而且是 UnboundLocalError。
    row = db.query(models.LabSession).filter(
        models.LabSession.user_id == user_id,
        models.LabSession.session_name == session,
        models.LabSession.status == "running",
    ).first()
    if row:
        row.last_activity = datetime.now(timezone.utc)
        db.commit()


def scan_and_evict(db: Session) -> int:
    """
    ZH: 背景任務 — 掃描所有 running session，依 idle/hard-limit 規則關閉
    EN: Background scanner — close sessions exceeding idle/hard limits

    Returns:
        關閉的 session 數量 | number of sessions closed

    @node job-scheduler/app/services/lab_manager.py::scan_and_evict
    """
    closed = 0
    now = datetime.now(timezone.utc)

    sessions = db.query(models.LabSession).filter(
        models.LabSession.status == "running"
    ).all()

    for session in sessions:
        user = db.query(models.User).filter(models.User.id == session.user_id).first()
        if not user:
            continue
        limits = quota_service.get_session_limits(user.role)

        started = session.started_at
        if started and started.tzinfo is None:
            started = started.replace(tzinfo=timezone.utc)
        last_act = session.last_activity
        if last_act and last_act.tzinfo is None:
            last_act = last_act.replace(tzinfo=timezone.utc)

        # Hard limit 檢查
        hard_min = limits.get("hard_limit_min")
        if hard_min and started:
            if (now - started).total_seconds() >= hard_min * 60:
                stop_session(db, session.user_id, reason="hard_limit_reached")
                closed += 1
                continue

        # Idle timeout 檢查
        idle_min = limits.get("idle_timeout_min")
        if idle_min and last_act:
            if (now - last_act).total_seconds() >= idle_min * 60:
                stop_session(db, session.user_id, reason="idle_timeout")
                closed += 1

    if closed:
        logger.info("scan_and_evict: closed %d session(s)", closed)
    return closed


def list_all_sessions(db: Session) -> list[dict]:
    """ZH: 列出目前所有(非 stopped) lab sessions，供 admin「Lab 管理」監控。
       EN: List all non-stopped lab sessions for the admin Lab dashboard.

    @node job-scheduler/app/services/lab_manager.py::list_all_sessions
    """
    rows = (
        db.query(models.LabSession)
        .filter(models.LabSession.status != "stopped")
        .order_by(models.LabSession.started_at.desc())
        .all()
    )
    out: list[dict] = []
    for s in rows:
        user = db.query(models.User).filter(models.User.id == s.user_id).first()
        out.append({
            "user_id": s.user_id,
            "username": user.username if user else s.user_id,
            # ZH: 🔴 v3.6 —— 多份存檔之後，管理端必須看得出「是哪一份」。
            #     這個函式寫在多份存檔之前，原本只回 user_id，
            #     於是管理端把每一份都顯示成 default（看起來很正常的錯誤答案）。
            "session_name": s.session_name,
            "display_name": s.display_name or s.session_name,
            "status": s.status,
            "container_name": s.container_name,
            "base_image": s.base_image,
            "started_at": s.started_at.isoformat() if s.started_at else None,
            "last_activity": s.last_activity.isoformat() if s.last_activity else None,
            "cpu_quota": s.cpu_quota,
            "mem_quota_mb": s.mem_quota_mb,
        })
    return out


# ==============================================================================
# ZH: v3.3 Lab 資料封存 / 還原 / 逾期銷毀（刪除使用者時不直接毀掉學生檔案）
# EN: v3.3 archive / restore / purge of per-user Lab volumes on account deletion
# ==============================================================================
def force_stop(db: Session, user_id: str, admin_id: str,
               session: Optional[str] = None) -> bool:
    """ZH: 管理員強制關閉某人的實驗室。回傳有沒有真的關掉。

    ZH: 🔴 這支函式**原本不存在**，而 `/admin/lab/sessions/{id}/force-stop`
        一直在呼叫它 —— 那個端點從上線到 2026-08-21 為止**每次都是 500**。
        沒有任何測試涵蓋它，所以測試一直是綠的；也沒有人回報，
        因為要真的有人去按那顆按鈕才會發現。
        （「呼叫端打錯名字」在這個 repo 的第八次。）

    ZH: `session` 留空 = 關掉**他目前正在跑的那一份**。
        一次只開一份是既有的約束，所以「正在跑的那一份」是明確的；
        但**不要預設成 `default`** —— 他跑的可能是別份，
        那樣會回 404（找不到執行中的 default），看起來像「沒有實驗室在跑」。

    ZH: 寫進 admin_actions —— 這是會影響到別人工作的動作，要留下是誰做的。

    @node job-scheduler/app/services/lab_manager.py::force_stop
    """
    target = session or current_session_name(db, user_id)
    ok = stop_session(db, user_id, reason="admin_forced", session=target)
    if not ok:
        return False

    db.add(models.AdminAction(
        admin_id=admin_id,
        target_user=user_id,
        action="force_stop_lab",
        payload=json.dumps({"session": target}, ensure_ascii=False),
        timestamp=datetime.now(timezone.utc),
    ))
    db.commit()
    logger.info("Admin %s force-stopped lab %s/%s", admin_id[:8], user_id[:8], target)
    return True


def _volume_size(vol_name: str) -> Optional[int]:
    """ZH: 由 docker df 取 volume 大小（取不到回 None，不阻斷流程）

    @node job-scheduler/app/services/lab_manager.py::_volume_size
    """
    try:
        lc = get_lifecycle()
        for v in (lc.client.df().get("Volumes") or []):
            if v.get("Name") == vol_name:
                return (v.get("UsageData") or {}).get("Size")
    except Exception as e:  # noqa: BLE001
        logger.warning("取得 volume 大小失敗 %s: %s", vol_name, e)
    return None


def archive_user_lab(db: Session, user, retention_days: int, reason: str = "admin_delete") -> Optional[dict]:
    """
    ZH: 刪除使用者前呼叫。停掉並移除其 code-server 容器（容器無資料、可重建），
        **volume 原地保留**並登記到 archived_lab_volumes（零複製成本），逾期才真正銷毀。
        volume 不存在（從未用過 Lab）→ 回 None。
    EN: Stop/remove the container, keep the volume in place and register it for
        retention-based purge. Returns the archive record dict, or None if no volume.

    @node job-scheduler/app/services/lab_manager.py::archive_user_lab
    """
    lc = get_lifecycle()
    uid = user.id
    now = datetime.now(timezone.utc)

    # ZH: 🔴 v3.6 —— 這個人**每一份存檔**都要處理，不是只有 default。
    #     原本只封存 `home_<uid>`：多份存檔上線後，刪一個帳號會留下
    #     其他份的容器還在跑、volume 沒封存也沒刪 —— 那些人再也沒有那 30 天可還原，
    #     磁碟上則多出永遠沒人認領的孤兒。
    #     default 一定要在清單裡（它可能沒有 DB 列，見 list_sessions 的同一個理由）。
    names = {r.session_name for r in db.query(models.LabSession)
             .filter(models.LabSession.user_id == uid).all()}
    names.add(DEFAULT_SESSION)

    archived = []
    for sess in sorted(names, key=lambda n: (n != DEFAULT_SESSION, n)):
        # 1) 容器：直接移除（無狀態，資料都在 volume）
        try:
            c = lc.client.containers.get(lc._container_name(uid, sess))
            c.remove(force=True)
            logger.info("已移除 Lab 容器 %s", lc._container_name(uid, sess))
        except Exception:
            pass  # 容器不存在/已停 → 略過

        # 2) volume：確認存在才登記封存
        vol_name = lc._volume_name(uid, sess)
        try:
            lc.client.volumes.get(vol_name)
        except Exception:
            continue        # ZH: 這一份從沒真的啟動過 → 沒有 volume，跳過

        existing = db.query(models.ArchivedLabVolume).filter(
            models.ArchivedLabVolume.volume_name == vol_name).first()
        rec = existing or models.ArchivedLabVolume(volume_name=vol_name)
        rec.user_id = uid
        rec.username = getattr(user, "username", None)
        rec.email = getattr(user, "email", None)
        rec.size_bytes = _volume_size(vol_name)
        rec.reason = reason
        rec.archived_at = now
        rec.expires_at = now + timedelta(days=max(1, int(retention_days)))
        rec.restored_at = None
        rec.restored_to = None
        if not existing:
            db.add(rec)
        archived.append({"volume": vol_name, "session": sess, "size_bytes": rec.size_bytes})

    if not archived:
        logger.info("使用者 %s 無 Lab volume，略過封存", uid[:8])
        return None

    db.commit()
    expires = (now + timedelta(days=max(1, int(retention_days)))).isoformat()
    total = sum(a["size_bytes"] or 0 for a in archived)
    logger.info("Lab 資料已封存 %d 份 (%s bytes)，到期 %s", len(archived), total, expires)
    return {
        # ZH: 舊的三個鍵維持不變（admin 端直接顯示這個 dict）
        "volume": archived[0]["volume"],
        "size_bytes": total,
        "expires_at": expires,
        # ZH: 多份存檔之後才有的：實際封存了哪幾份
        "volumes": archived,
    }


def purge_expired_archives(db: Session) -> int:
    """
    ZH: 背景任務：(1) 移除逾期封存的 volume；(2) 自我修復——清掉「volume 早已不存在」
        的殘留紀錄（volume 被手動 rm / docker prune 掉時，逾期邏輯永遠碰不到它，
        紀錄會無限累積）。
        ⚠️ 防呆：只有在**成功列出 volume 清單**時才做 (2)。若 docker 暫時不可用，
        清單會是空的，此時若照做會誤刪全部紀錄。
    EN: Purge expired archives, plus self-heal stale records whose volume is already
        gone — but only when the volume listing actually succeeded (a Docker outage
        would otherwise look like "everything is missing" and wipe all records).

    @node job-scheduler/app/services/lab_manager.py::purge_expired_archives
    """
    lc = get_lifecycle()
    now = datetime.now(timezone.utc)

    present, listing_ok = set(), False
    try:
        present = {v.name for v in lc.client.volumes.list()}
        listing_ok = True
    except Exception as e:  # noqa: BLE001
        logger.warning("列出 volume 失敗，略過殘留紀錄清理: %s", e)

    rows = db.query(models.ArchivedLabVolume).all()
    n = 0
    for rec in rows:
        exp = rec.expires_at
        if exp is not None and exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        expired = exp is not None and exp <= now
        vanished = listing_ok and rec.volume_name not in present

        if not expired and not vanished:
            continue
        if expired and not vanished:
            try:
                lc.client.volumes.get(rec.volume_name).remove(force=True)
                logger.info("封存逾期，已銷毀 volume %s", rec.volume_name)
            except Exception as e:  # noqa: BLE001
                logger.warning("銷毀封存 volume %s 失敗: %s", rec.volume_name, e)
        elif vanished:
            logger.info("封存 volume %s 已不存在（外部移除），清除殘留紀錄", rec.volume_name)
        db.delete(rec)
        n += 1
    if n:
        db.commit()
    return n


def restore_archive(db: Session, volume_name: str, target_user_id: str) -> dict:
    """
    ZH: 把封存的 Lab 內容還原給指定使用者。因 SSO 使用者回來是**新 uuid**，
        還原＝將舊 volume 內容複製進目標使用者的（新）volume，而非改名。
        以臨時容器掛載兩個 volume 執行 cp -a；完成後保留封存紀錄（標記 restored）。
    EN: Copy archived volume contents into the target user's current volume via a
        throwaway container (SSO users return with a new uuid, so rename won't do).

    ZH: ⚠ v3.6 多份存檔之後要知道：還原的目的地**一律是目標使用者的 `default`**，
        不是「原本那一份存檔」。封存時每一份存檔各自留下一筆紀錄
        （`home_<uid>`、`home_<uid>_ws2`…），管理者選哪一筆就還原哪一筆的內容，
        但都會落到 default 裡。要還原多份時是**逐筆還原、內容會疊在一起**，
        不會自動長回原本的存檔結構。這是刻意的選擇（管理端沒有選目的地的欄位），
        不是漏掉。

    @node job-scheduler/app/services/lab_manager.py::restore_archive
    """
    lc = get_lifecycle()
    rec = db.query(models.ArchivedLabVolume).filter(
        models.ArchivedLabVolume.volume_name == volume_name).first()
    if not rec:
        raise ValueError("找不到該封存紀錄")
    target = db.query(models.User).filter(models.User.id == target_user_id).first()
    if not target:
        raise ValueError("找不到目標使用者")
    try:
        lc.client.volumes.get(volume_name)
    except Exception:
        raise ValueError("封存的 volume 已不存在（可能已逾期銷毀）")

    dest_vol = lc._ensure_volume(target_user_id)   # 目標不存在會自動建立
    # ZH: -a 保留權限/時間；來源內容整包倒入目標根層。目標同名檔會被覆蓋。
    cmd = "sh -c 'cp -a /from/. /to/ 2>/dev/null; echo done'"
    lc.client.containers.run(
        image="alpine:3.19", command=cmd, remove=True,
        volumes={volume_name: {"bind": "/from", "mode": "ro"},
                 dest_vol: {"bind": "/to", "mode": "rw"}},
    )
    rec.restored_at = datetime.now(timezone.utc)
    rec.restored_to = target_user_id
    db.commit()
    logger.info("已將封存 %s 還原給使用者 %s", volume_name, target.username)
    return {"volume": volume_name, "restored_to": target.username, "target_volume": dest_vol}


def list_archives(db: Session) -> list[dict]:
    """ZH: 給 admin 檢視封存清單（含目前實際是否還在、剩餘天數）

    @node job-scheduler/app/services/lab_manager.py::list_archives
    """
    lc = get_lifecycle()
    try:
        present = {v.name for v in lc.client.volumes.list()}
    except Exception:
        present = set()
    now = datetime.now(timezone.utc)
    out = []
    for rec in db.query(models.ArchivedLabVolume).order_by(
            models.ArchivedLabVolume.archived_at.desc()).all():
        exp = rec.expires_at
        if exp is not None and exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        out.append({
            "volume_name": rec.volume_name,
            "username": rec.username,
            "email": rec.email,
            "user_id": rec.user_id,
            "size_bytes": rec.size_bytes,
            "reason": rec.reason,
            "archived_at": rec.archived_at.isoformat() if rec.archived_at else None,
            "expires_at": exp.isoformat() if exp else None,
            "days_left": max(0, (exp - now).days) if exp else None,
            "exists": rec.volume_name in present,
            "restored_at": rec.restored_at.isoformat() if rec.restored_at else None,
            "restored_to": rec.restored_to,
        })
    return out


def delete_archive_now(db: Session, volume_name: str) -> bool:
    """ZH: admin 立即銷毀某筆封存（不等到期）

    @node job-scheduler/app/services/lab_manager.py::delete_archive_now
    """
    lc = get_lifecycle()
    rec = db.query(models.ArchivedLabVolume).filter(
        models.ArchivedLabVolume.volume_name == volume_name).first()
    if not rec:
        return False
    try:
        lc.client.volumes.get(volume_name).remove(force=True)
    except Exception as e:  # noqa: BLE001
        logger.warning("立即銷毀 volume %s 失敗（可能已不存在）: %s", volume_name, e)
    db.delete(rec)
    db.commit()
    return True


def _build_url(user_id: str, session) -> dict:
    """ZH: 組裝給前端跳轉的 URL | EN: Build URL for frontend redirect

    @node job-scheduler/app/services/lab_manager.py::_build_url
    """
    # ZH: 🔴 v3.6 —— 網址要帶存檔後綴。這裡原本恆為 `/code/<uid>/`，
    #     於是後端明明啟動了 `cs-<uid>-deep-learning-hw`，
    #     回給前端的網址卻指向 default 那一個容器 ——
    #     使用者點下去看到的是**別份存檔的檔案**，而且完全不會報錯。
    #     （nginx 的 `/code/<uid>-<存檔>/` 路由與 auth_request 的前綴比對
    #       都已經支援，就差這個字串沒補。）
    name = getattr(session, "session_name", None) or DEFAULT_SESSION
    seg = user_id if name == DEFAULT_SESSION else f"{user_id}-{name}"
    return {
        "url": f"/code/{seg}/?folder=/home/coder/projects",
        "container_name": session.container_name,
        "started_at": session.started_at.isoformat() if session.started_at else None,
    }


# ==============================================================================
# ZH: 工具 — 給 nginx auth_request 用
# EN: Helpers — for nginx auth_request endpoint
# ==============================================================================

def is_user_session_alive(db: Session, user_id: str,
                          session: Optional[str] = None) -> bool:
    """
    ZH: 確認該 user 是否有 running session（auth_request 驗證用）
    EN: Check if user has a running session (for auth_request)

    @node job-scheduler/app/services/lab_manager.py::is_user_session_alive
    """
    # ZH: v3.6 —— 多份存檔之後，「這個人有沒有在跑」與「**這一份**有沒有在跑」
    #     是兩個問題。nginx 的 auth_request 問的是後者（他要進的是某一個網址），
    #     所以指定了就查那一份；沒指定則問前者。
    q = db.query(models.LabSession).filter(
        models.LabSession.user_id == user_id,
        models.LabSession.status == "running",
    )
    if session is not None:
        q = q.filter(models.LabSession.session_name == session)
    return q.first() is not None
