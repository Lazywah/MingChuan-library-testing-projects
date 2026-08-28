"""
==============================================================================
Service: 使用者儲存生命週期狀態機 | User Storage Lifecycle State Machine
==============================================================================
ZH: 用途：管理使用者 home volume 從 active 到 archive / pending_delete 的轉換
    狀態：active → frozen → archived → pending_delete
    永不自動硬刪：pending_delete 仍需 admin 二次確認 + 密碼

EN: Purpose: Manage user home-volume lifecycle from active to archive/delete
    States: active → frozen → archived → pending_delete
    Never auto-delete: pending_delete still requires admin re-confirmation

ZH: 學期保護：scheduler_policy.yaml 中 academic_calendar 控制是否執行歸檔/刪除
EN: Academic protection: academic_calendar in yaml controls archive/delete eligibility
==============================================================================
"""

from __future__ import annotations

import logging
# ZH: 2026-08-27 —— 這裡原本還匯入 os / shutil / subprocess / tarfile。
#     全部**沒有任何一行在用**（`os` 是我把 archive 的假路徑拿掉後才變成沒用的，
#     另外三個更早就沒用了）。留著它們會讓人以為這個模組真的在做打包與檔案操作 ——
#     它現在完全沒有碰過檔案系統。真的要實作 archive 時再加回來。
from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from .. import models
from ..config import SCHEDULER_POLICY
from . import quota_service

logger = logging.getLogger(__name__)


# ==============================================================================
# ZH: 學期日曆判斷 | Academic calendar check
# ==============================================================================

def is_archival_allowed_today() -> bool:
    """
    ZH: 今日是否在「允許執行歸檔 / 刪除」的月份內（暑假）
    EN: Is today within the archival months (typically July-August)?

    @node job-scheduler/app/services/storage_lifecycle.py::is_archival_allowed_today
    """
    cal = SCHEDULER_POLICY.get("academic_calendar", {})
    archival_months = cal.get("archival_months", [7, 8])
    return datetime.now(timezone.utc).month in archival_months


def is_semester_today() -> bool:
    """
    ZH: 今日是否在學期月份內（保護學生資料）
    EN: Is today within a semester month (data is protected)

    @node job-scheduler/app/services/storage_lifecycle.py::is_semester_today
    """
    cal = SCHEDULER_POLICY.get("academic_calendar", {})
    semester_months = cal.get("semester_months", [9, 10, 11, 12, 1, 2, 3, 4, 5, 6])
    return datetime.now(timezone.utc).month in semester_months


# ==============================================================================
# ZH: 狀態取得 / 建立 | State get/init
# ==============================================================================

def get_or_create_state(db: Session, user_id: str) -> models.UserStorageState:
    """ZH: 取得或建立 storage state | EN: Get or create storage state

    @node job-scheduler/app/services/storage_lifecycle.py::get_or_create_state
    """
    state = db.query(models.UserStorageState).filter(
        models.UserStorageState.user_id == user_id
    ).first()
    if state is None:
        state = models.UserStorageState(
            user_id=user_id,
            state="active",
            state_since=datetime.now(timezone.utc),
            current_size_gb=0.0,
        )
        db.add(state)
        db.commit()
        db.refresh(state)
    return state


def list_states(db: Session, filter_state: Optional[str] = None) -> list[dict]:
    """ZH: 列出所有使用者儲存狀態，供 admin Lab「儲存生命週期」面板。
       EN: List all user storage states for the admin Lab storage panel.

    @node job-scheduler/app/services/storage_lifecycle.py::list_states
    """
    q = db.query(models.UserStorageState)
    if filter_state and filter_state not in ("all", ""):
        q = q.filter(models.UserStorageState.state == filter_state)
    out: list[dict] = []
    for s in q.all():
        out.append({
            "user_id": s.user_id,
            "state": s.state,
            "current_size_gb": s.current_size_gb,
            "state_since": s.state_since.isoformat() if s.state_since else None,
            "archive_path": s.archive_path,
            "notes": s.notes,
        })
    return out


# ==============================================================================
# ZH: 狀態轉換 | State transitions
# ==============================================================================

def freeze(db: Session, user_id: str, admin_id: Optional[str] = None,
           reason: str = "manual") -> bool:
    """
    ZH: 把使用者的儲存狀態**標記**為 frozen。

    ZH: 🔴 **它不會讓儲存真的變成唯讀。** 這一版做的事情只有三件：
          1. `user_storage_state.state` 改成 `frozen`
          2. 寫一筆管理稽核（有 admin_id 時）
          3. 記一行 log
        使用者**照樣讀寫**，容器不會被暫停，掛載也不會變唯讀。

    ZH: ⚠️ 這個 docstring 原本寫的是「切到 frozen 狀態（**唯讀模式**）」——
        那句話會讓管理者以為按下「凍結」就擋住了對方。實際上
        `user_storage_state.state` 除了管理端的列表之外**沒有任何地方在讀**，
        所以這個狀態目前是純粹的帳面紀錄。
        （2026-08-27 稽核查證；擁有者尚未決定要不要真的實作。）

    ZH: ⚠️ **2026-08-28 更新，但只更新了一半：**
        `daily_scan` 的「超配額 → 凍結」那條分支在此之前**一次都沒有執行過** ——
        它看的 `current_size_gb` 沒有任何地方更新它，永遠是 0.0。
        v3.9 加了 `lab_manager.refresh_storage_usage`（每日 03:00 先量再判），
        所以**現在超配額真的會把人凍結**。
        但 `state` 依然沒有人在讀 —— 也就是說：**被凍結的人照樣讀寫，
        只是管理端會看到他是 frozen。** 「擋住」那一半仍然沒有做。

    ZH: 回傳 True 代表「狀態已改」，**不代表「已經擋住了」**。

    觸發場景：超過配額 / 90 天未登入 / admin 手動。
    ⚠ 前兩者由每日排程自動呼叫,所以這支不能改成拋錯 —— 會把整個迴圈打斷。

    EN: Marks the storage state as `frozen`. It does NOT make storage read-only;
        nothing enforces the state today. Returns True = "state changed".

    @node job-scheduler/app/services/storage_lifecycle.py::freeze
    """
    state = get_or_create_state(db, user_id)
    if state.state == "frozen":
        return False
    old_state = state.state
    state.state = "frozen"
    state.state_since = datetime.now(timezone.utc)
    state.notes = f"frozen ({reason}) at {state.state_since.isoformat()}"

    if admin_id:
        _log_admin_action(db, admin_id, user_id, "freeze",
                          {"old_state": old_state, "reason": reason})

    db.commit()
    logger.info("User %s storage state: %s → frozen (reason=%s)",
                user_id[:8], old_state, reason)
    # TODO: 實際暫停容器、移除寫入權限（v2.0 透過 Docker 重啟以唯讀掛載實現）
    # ZH: ⚠ 上面那個 TODO 沒做之前,這個 True 的意思只有「狀態已改」——
    #     呼叫端不可以據此宣稱使用者已被擋住（見 docstring）。
    return True


def archive(db: Session, user_id: str, admin_id: Optional[str] = None,
            reason: str = "manual") -> bool:
    """
    ZH: 把 frozen 使用者歸檔到 HDD —— 🔴 **實際打包尚未實作，所以這支一律拒絕執行**。

    ZH: 為什麼是「拒絕」而不是「照舊回 True」：
        `archived` 這個狀態的意思是「資料已經安全地放在 HDD 上」。
        在真的打包出來之前，把使用者標成 archived 是**記錄一件沒有發生的事**。

    ZH: 改之前它做的事（2026-08-27 稽核查證）：
          · 算出 `archive_path = /data/archive/home_<uid>.tar.gz`
          · 把那個路徑寫進 `user_storage_state.archive_path` **與管理稽核**
          · log 印「User xxx archived → /data/archive/…」
          · **從來沒有建立過那個檔案**
        於是 DB 與稽核紀錄裡有一個指向不存在檔案的路徑。
        真正的危險不是「沒備份」,是**有人相信那個備份存在**而去砍掉 volume。

    ZH: ⚠️ 這支**只有管理員手動呼叫**（每日排程只會自動 freeze，不會 archive），
        所以拒絕執行不會打斷任何背景迴圈。管理端會收到 409 與說明。

    ZH: 要真的實作時，把下面的 `return False` 換成實際的打包
        （`docker run --rm -v home_<uid>:/src -v archive:/dest alpine tar czf …`），
        並且**先確認檔案存在再改狀態**。

    EN: Archiving is NOT implemented, so this refuses instead of recording a state
        that would mean "data is safely on HDD". It previously wrote a path to a
        file that was never created — into the DB and the admin audit log.

    @node job-scheduler/app/services/storage_lifecycle.py::archive
    """
    # ZH: 既有的兩道守衛照跑 —— 它們是對的，而且日誌要分得出是哪個原因擋下的。
    if not is_archival_allowed_today() and not admin_id:
        logger.info("Archive skipped for %s (in semester, no admin override)",
                    user_id[:8])
        return False

    state = get_or_create_state(db, user_id)
    if state.state != "frozen":
        logger.warning("Cannot archive: user %s not in frozen state (current=%s)",
                       user_id[:8], state.state)
        return False

    # ==========================================================================
    # ZH: 🔴 到這裡「該歸檔」了，但**實際打包還沒實作** —— 所以停在這裡。
    #
    # ZH: 原本這裡會算出 archive_path、把它寫進 state 與管理稽核、log 印
    #     「archived → …」然後 return True，而那個 tar.gz **從來沒有被建立過**。
    #     那不是「沒做完」,是**記錄一件沒有發生的事**：
    #     DB 與稽核裡有一個指向不存在檔案的路徑,
    #     而真正的危險是有人相信那個備份存在、去砍掉 volume。
    #
    # ZH: 要實作時,把下面換成實際的打包，**先確認檔案存在再改狀態**：
    #       docker run --rm -v home_<uid>:/src -v <archive_dir>:/dest alpine     #              tar czf /dest/home_<uid>.tar.gz -C /src .
    #     然後才 state.state = "archived"、寫 archive_path、寫稽核、commit。
    # ==========================================================================
    logger.warning(
        "Archive refused for %s: packing is not implemented — refusing rather than "
        "recording a tar.gz path that does not exist", user_id[:8])
    return False


def restore(db: Session, user_id: str, admin_id: str) -> bool:
    """
    ZH: 從 archived 還原為 active（管理員操作）
    EN: Restore archived user back to active (admin op)

    @node job-scheduler/app/services/storage_lifecycle.py::restore
    """
    state = get_or_create_state(db, user_id)
    if state.state not in ("archived", "frozen", "pending_delete"):
        return False

    old_state = state.state
    state.state = "active"
    state.state_since = datetime.now(timezone.utc)
    state.notes = f"restored from {old_state} by admin {admin_id[:8]}"

    _log_admin_action(db, admin_id, user_id, "restore",
                      {"old_state": old_state, "archive_path": state.archive_path})

    db.commit()
    logger.info("User %s restored from %s to active by admin %s",
                user_id[:8], old_state, admin_id[:8])
    return True


def mark_pending_delete(db: Session, user_id: str, admin_id: str,
                       reason: str = "manual") -> bool:
    """
    ZH: 將使用者標記為 pending_delete，等待 admin 二次確認真正刪除
    EN: Mark user as pending_delete; waiting for admin re-confirmation

    @node job-scheduler/app/services/storage_lifecycle.py::mark_pending_delete
    """
    state = get_or_create_state(db, user_id)
    old_state = state.state
    state.state = "pending_delete"
    state.state_since = datetime.now(timezone.utc)
    state.notes = f"pending delete ({reason}) — requires admin confirmation"

    _log_admin_action(db, admin_id, user_id, "mark_pending_delete",
                      {"old_state": old_state, "reason": reason})
    db.commit()
    logger.warning("User %s marked pending_delete by admin %s",
                   user_id[:8], admin_id[:8])
    return True


def permanent_delete(db: Session, user_id: str, admin_id: str,
                     admin_password_verified: bool) -> bool:
    """
    ZH: 永久刪除（需先通過 admin 二次驗證）
    EN: Permanent delete (requires admin re-verification)

    Args:
        admin_password_verified: 必須先呼叫 /api/v1/admin/verify 取得 True

    @node job-scheduler/app/services/storage_lifecycle.py::permanent_delete
    """
    if not admin_password_verified:
        raise PermissionError("Admin password re-verification required for permanent delete")

    state = get_or_create_state(db, user_id)
    if state.state != "pending_delete":
        raise ValueError(f"User must be in pending_delete state (current: {state.state})")

    # ZH: dump metadata 到 audit log（刪除前最後快照）
    # EN: Dump metadata to audit log (last snapshot before delete)
    _log_admin_action(db, admin_id, user_id, "permanent_delete", {
        "archive_path": state.archive_path,
        "current_size_gb": state.current_size_gb,
        "state_since": state.state_since.isoformat() if state.state_since else None,
        "notes": state.notes,
    })

    # ZH: 標為已刪除（保留 audit），實際磁碟刪除由運維人員執行
    # EN: Mark as deleted (audit preserved); actual disk wipe by ops
    state.state = "deleted"
    state.state_since = datetime.now(timezone.utc)
    state.notes = f"PERMANENTLY DELETED by admin {admin_id[:8]} at {state.state_since.isoformat()}"
    db.commit()

    logger.critical("PERMANENT DELETE executed: user %s by admin %s",
                    user_id[:8], admin_id[:8])
    return True


# ==============================================================================
# ZH: 背景掃描 — 每日 03:00 執行
# EN: Background scan — runs daily at 03:00
# ==============================================================================

def daily_scan(db: Session) -> dict:
    """
    ZH: 每日狀態轉換掃描；學期中只執行 active → frozen，暑假執行完整轉換
    EN: Daily state-transition scan; semester = only active→frozen,
        summer = full chain

    Returns: 統計 dict

    @node job-scheduler/app/services/storage_lifecycle.py::daily_scan
    """
    stats = {"active_to_frozen": 0, "frozen_to_archived": 0,
             "archived_to_pending_delete": 0}
    now = datetime.now(timezone.utc)
    in_semester = is_semester_today()

    # ZH: active → frozen（學期中也執行：超配額或 90 天未登入）
    # EN: active → frozen (active even in semester: over-quota or 90d inactive)
    users = db.query(models.User).all()
    for user in users:
        if user.role == "teacher":          # 教師例外，預設不歸檔
            continue
        state = get_or_create_state(db, user.id)
        if state.state != "active":
            continue
        effective_quota = quota_service.get_effective_quota_gb(db, user.id)

        # 超配額觸發
        if state.current_size_gb > effective_quota:
            freeze(db, user.id, reason="quota_exceeded")
            stats["active_to_frozen"] += 1
            continue

        # 90 天未登入觸發
        if user.last_login_time:
            last = user.last_login_time
            if last.tzinfo is None:
                last = last.replace(tzinfo=timezone.utc)
            if (now - last) > timedelta(days=90):
                freeze(db, user.id, reason="inactive_90d")
                stats["active_to_frozen"] += 1

    # ZH: 學期中不再執行更深的轉換
    # EN: Don't run deeper transitions during semester
    if in_semester:
        logger.info("daily_scan in semester — stopped at active→frozen: %s", stats)
        return stats

    # ZH: frozen → archived（30 天無動作）
    # EN: frozen → archived (30 days no activity)
    frozen_states = db.query(models.UserStorageState).filter(
        models.UserStorageState.state == "frozen"
    ).all()
    for s in frozen_states:
        state_since = s.state_since
        if state_since and state_since.tzinfo is None:
            state_since = state_since.replace(tzinfo=timezone.utc)
        if state_since and (now - state_since) > timedelta(days=30):
            archive(db, s.user_id, reason="frozen_30d_no_action")
            stats["frozen_to_archived"] += 1

    # ZH: archived → pending_delete（1 年無動作；不自動執行，僅標記）
    # EN: archived → pending_delete (1 year no action; only flag, never auto-delete)
    archived_states = db.query(models.UserStorageState).filter(
        models.UserStorageState.state == "archived"
    ).all()
    for s in archived_states:
        state_since = s.state_since
        if state_since and state_since.tzinfo is None:
            state_since = state_since.replace(tzinfo=timezone.utc)
        if state_since and (now - state_since) > timedelta(days=365):
            # 不呼叫 mark_pending_delete（那需要 admin_id），改直接設 state
            s.state = "pending_delete"
            s.state_since = now
            s.notes = f"auto-flagged pending_delete after 1 year archived (awaiting admin)"
            db.commit()
            stats["archived_to_pending_delete"] += 1

    logger.info("daily_scan summary: %s", stats)
    return stats


# ==============================================================================
# ZH: Audit log 寫入 | Audit log helper
# ==============================================================================

def _log_admin_action(db: Session, admin_id: str, target_user: Optional[str],
                      action: str, payload: dict) -> None:
    """ZH: 寫一筆 admin_actions 記錄 | EN: Write admin_actions row

    @node job-scheduler/app/services/storage_lifecycle.py::_log_admin_action
    """
    import json
    db.add(models.AdminAction(
        admin_id=admin_id,
        target_user=target_user,
        action=action,
        payload=json.dumps(payload, ensure_ascii=False),
        timestamp=datetime.now(timezone.utc),
    ))
    db.commit()
