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
from datetime import datetime, timezone
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
# ZH: 高階 API — 給 router 與 scheduler 呼叫
# EN: High-level API — called by routers & scheduler
# ==============================================================================

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
