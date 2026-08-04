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


# ==============================================================================
# ZH: ContainerLifecycle Protocol（v2.1 預留擴充點）
# EN: ContainerLifecycle Protocol (v2.1 extension point)
# ==============================================================================

class ContainerLifecycle(Protocol):
    """
    ZH: 所有容器類型（code-server、未來 Jupyter Kernel）的共通介面
    EN: Common interface for all container types
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
    """

    def __init__(self):
        self._client: Optional[docker.DockerClient] = None

    @property
    def client(self) -> docker.DockerClient:
        if self._client is None:
            self._client = docker.from_env()
        return self._client

    def _container_name(self, user_id: str) -> str:
        # ZH: 容器名稱 cs-<user_id>（user_id 已是 UUID，符合 DNS-safe）
        # EN: Container name cs-<user_id> (user_id is UUID, DNS-safe)
        safe = user_id.replace("_", "-")[:60]
        return f"cs-{safe}"

    def _volume_name(self, user_id: str) -> str:
        """ZH: 對應的 home volume 名稱 | EN: Home volume name"""
        safe = user_id.replace("-", "_")[:60]
        return f"home_{safe}"

    def _ensure_volume(self, user_id: str) -> str:
        """ZH: 確保 per-user volume 存在 | EN: Ensure per-user volume exists"""
        name = self._volume_name(user_id)
        try:
            self.client.volumes.get(name)
        except NotFound:
            self.client.volumes.create(name=name, labels={
                "aibase.user_id": user_id,
                "aibase.purpose": "home",
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
        """
        name = self._container_name(user_id)
        volume_name = self._ensure_volume(user_id)

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
        """ZH: 停止並移除容器 | EN: Stop and remove container"""
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
        """ZH: 回傳 running/exited/missing | EN: Returns running/exited/missing"""
        try:
            c = self.client.containers.get(container_id)
            return c.status
        except NotFound:
            return "missing"


# ZH: 模組級單例（避免 Docker client 重複建立）
# EN: Module-level singleton (avoid repeated Docker client init)
_codeserver: Optional[CodeServerLifecycle] = None


def get_lifecycle() -> CodeServerLifecycle:
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
       回傳 {"running": bool, "files": [rel_path], "reason": str|None}"""
    lc = get_lifecycle()
    name = lc._container_name(user_id)
    try:
        c = lc.client.containers.get(name)
    except NotFound:
        return {"running": False, "files": [], "reason": "lab_not_started"}
    if c.status != "running":
        return {"running": False, "files": [], "reason": "lab_not_running"}

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
       回傳 {"ok": bool, "content": str, "path": str, "truncated": bool, "reason": str|None}"""
    import io
    import tarfile
    import posixpath

    # ZH: 路徑安全 — 正規化後必須仍落在 /home/coder 下，拒絕 .. 穿越
    rel = (rel_path or "").lstrip("/")
    target = posixpath.normpath(posixpath.join(LAB_HOME, rel))
    if target != LAB_HOME and not target.startswith(LAB_HOME + "/"):
        return {"ok": False, "content": "", "path": rel_path, "truncated": False, "reason": "path_forbidden"}

    lc = get_lifecycle()
    name = lc._container_name(user_id)
    try:
        c = lc.client.containers.get(name)
    except NotFound:
        return {"ok": False, "content": "", "path": rel, "truncated": False, "reason": "lab_not_started"}
    if c.status != "running":
        return {"ok": False, "content": "", "path": rel, "truncated": False, "reason": "lab_not_running"}

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
       任何 <500 的 HTTP 回應(200/302/401)都代表 code-server 已在服務。"""
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


def start_session(db: Session, user_id: str, base_image: Optional[str] = None) -> dict:
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
        models.LabSession.session_name == "default",
    ).first()
    if existing and existing.status == "running":
        return _build_url(user_id, existing)

    lc = get_lifecycle()

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
    session = existing or models.LabSession(
        user_id=user_id,
        session_name="default",
        volume_name=lc._volume_name(user_id),
        base_image=base_image,
    )
    session.status = "starting"
    session.base_image = base_image
    session.started_at = datetime.now(timezone.utc)
    session.last_activity = datetime.now(timezone.utc)
    if not existing:
        db.add(session)
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
        })
    except Exception as e:
        session.status = "stopped"
        db.commit()
        raise RuntimeError(f"Failed to start container: {e}")

    session.container_id = container_id
    session.container_name = container_name
    # v2.4: 等 code-server HTTP 就緒再回傳，避免前端開分頁時容器尚未服務 → 503
    _wait_until_ready(container_name, timeout=25.0)
    session.status = "running"
    session.cpu_quota = cpu_quota
    session.mem_quota_mb = mem_quota
    db.commit()
    db.refresh(session)

    return {
        **_build_url(user_id, session),
        "password": password,
    }


def stop_session(db: Session, user_id: str, reason: str = "user_requested") -> bool:
    """
    ZH: 停止使用者的 session，並累加今日已用時長
    EN: Stop user session and accumulate today's usage
    """
    session = db.query(models.LabSession).filter(
        models.LabSession.user_id == user_id,
        models.LabSession.session_name == "default",
    ).first()
    if not session or session.status == "stopped":
        return False

    elapsed = 0
    if session.started_at:
        started = session.started_at
        if started.tzinfo is None:
            started = started.replace(tzinfo=timezone.utc)
        elapsed = int((datetime.now(timezone.utc) - started).total_seconds())

    if session.container_id:
        get_lifecycle().stop(session.container_id)

    session.status = "stopped"
    session.container_id = None
    db.commit()

    if elapsed > 0:
        quota_service.increment_usage(db, user_id, elapsed)

    logger.info("Session stopped for user %s (reason=%s, elapsed=%ds)",
                user_id[:8], reason, elapsed)
    return True


def get_status(db: Session, user_id: str) -> dict:
    """
    ZH: 取得使用者目前的 session 完整狀態（給 /lab/status endpoint）
    EN: Get full session status for /lab/status endpoint
    """
    session = db.query(models.LabSession).filter(
        models.LabSession.user_id == user_id,
        models.LabSession.session_name == "default",
    ).first()

    # 取使用者 secrets 名稱清單（masked）
    masked = secrets_service.list_secrets_masked(db, user_id)

    user = db.query(models.User).filter(models.User.id == user_id).first()
    limits = quota_service.get_session_limits(user.role if user else "student")
    remaining_min = quota_service.get_today_remaining_minutes(db, user_id)

    if not session or session.status == "stopped":
        return {
            "session_name": "default",
            "status": "stopped",
            "limits": limits,
            "today_remaining_min": remaining_min,
            "injected_secrets": masked,
        }

    now = datetime.now(timezone.utc)
    started = session.started_at
    if started and started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)
    last_act = session.last_activity
    if last_act and last_act.tzinfo is None:
        last_act = last_act.replace(tzinfo=timezone.utc)

    return {
        "session_name": "default",
        "status": session.status,
        "started_at": started.isoformat() if started else None,
        "last_activity": last_act.isoformat() if last_act else None,
        "idle_seconds": int((now - last_act).total_seconds()) if last_act else None,
        "elapsed_seconds": int((now - started).total_seconds()) if started else None,
        "base_image": session.base_image,
        "limits": limits,
        "today_remaining_min": remaining_min,
        "injected_secrets": masked,
        "url": _build_url(user_id, session).get("url"),
    }


def touch_activity(db: Session, user_id: str) -> None:
    """
    ZH: 更新 last_activity（heartbeat endpoint 呼叫）
    EN: Update last_activity (called by heartbeat endpoint)
    """
    session = db.query(models.LabSession).filter(
        models.LabSession.user_id == user_id,
        models.LabSession.session_name == "default",
        models.LabSession.status == "running",
    ).first()
    if session:
        session.last_activity = datetime.now(timezone.utc)
        db.commit()


def scan_and_evict(db: Session) -> int:
    """
    ZH: 背景任務 — 掃描所有 running session，依 idle/hard-limit 規則關閉
    EN: Background scanner — close sessions exceeding idle/hard limits

    Returns:
        關閉的 session 數量 | number of sessions closed
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
       EN: List all non-stopped lab sessions for the admin Lab dashboard."""
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
def _volume_size(vol_name: str) -> Optional[int]:
    """ZH: 由 docker df 取 volume 大小（取不到回 None，不阻斷流程）"""
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
    """
    lc = get_lifecycle()
    uid = user.id
    # 1) 容器：直接移除（無狀態，資料都在 volume）
    try:
        c = lc.client.containers.get(lc._container_name(uid))
        c.remove(force=True)
        logger.info("已移除 Lab 容器 cs-%s", uid[:8])
    except Exception:
        pass  # 容器不存在/已停 → 略過

    # 2) volume：確認存在才登記封存
    vol_name = lc._volume_name(uid)
    try:
        lc.client.volumes.get(vol_name)
    except Exception:
        logger.info("使用者 %s 無 Lab volume，略過封存", uid[:8])
        return None

    now = datetime.now(timezone.utc)
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
    db.commit()
    logger.info("Lab 資料已封存 %s (%s bytes)，到期 %s", vol_name, rec.size_bytes, rec.expires_at)
    return {"volume": vol_name, "size_bytes": rec.size_bytes, "expires_at": rec.expires_at.isoformat()}


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
    """ZH: 給 admin 檢視封存清單（含目前實際是否還在、剩餘天數）"""
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
    """ZH: admin 立即銷毀某筆封存（不等到期）"""
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
    """ZH: 組裝給前端跳轉的 URL | EN: Build URL for frontend redirect"""
    return {
        "url": f"/code/{user_id}/?folder=/home/coder/projects",
        "container_name": session.container_name,
        "started_at": session.started_at.isoformat() if session.started_at else None,
    }


# ==============================================================================
# ZH: 工具 — 給 nginx auth_request 用
# EN: Helpers — for nginx auth_request endpoint
# ==============================================================================

def is_user_session_alive(db: Session, user_id: str) -> bool:
    """
    ZH: 確認該 user 是否有 running session（auth_request 驗證用）
    EN: Check if user has a running session (for auth_request)
    """
    session = db.query(models.LabSession).filter(
        models.LabSession.user_id == user_id,
        models.LabSession.session_name == "default",
        models.LabSession.status == "running",
    ).first()
    return session is not None
