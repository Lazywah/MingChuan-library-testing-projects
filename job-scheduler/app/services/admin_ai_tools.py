"""
Service: 管理端 AI 的查詢工具（全部唯讀）
=========================================

ZH: v4.37（擁有者 2026-10-04）—— 「平台管理端 AI」，目的是像人工查問題那樣：
    「12361114 收到實驗室刪除通知是怎麼回事」「MYAI 同步正常嗎」。
    擁有者裁定：**本機模型（資料不出校）、只能查不能改**。

ZH: 🔴 設計核心：**判斷寫在工具裡，不靠模型。**
    本機 8B 模型連續多步推理的能力弱（實測 llama3 不支援原生工具呼叫）。所以每個工具
    自己把「人工查的時候會注意到的事」算成 findings（例：帳號建立時間比第一封登入通知晚
    → 曾被刪除重建）。模型只做兩件事：選工具、用中文講給管理員聽。
    換成更強的模型也不用改這裡。

ZH: 🔴 **全部唯讀**。這個檔案裡不准出現任何寫入（db.add／commit／刪檔／停容器）。理由：工具的輸入來自模型、模型的輸入有一部分來自使用者資料
    （帳號名、回報內容、日誌），那條鏈上任何一環被塞了奇怪的字，都不能變成一個動作。
    tests/test_admin_ai.py 會掃這個檔的原始碼，出現寫入的寫法就紅。

ZH: 每個工具回 {"title", "facts": {...}, "findings": [str], "tables": {名稱: [列]}}。
    findings 是給人看的結論句（中文）；facts／tables 是原始資料，畫面上一定附上，
    模型講錯的時候管理員看得出來。

@node job-scheduler/app/services/admin_ai_tools.py
"""
import json
import logging
import re
import shutil
import socket
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from .. import crud, models

logger = logging.getLogger(__name__)

SCHEDULER_CONTAINER = "ai-platform-scheduler"
WORKER_CONTAINER = "mcu-gpu-worker"
MYAI_HOST = "www.myai168.com"

# ZH: 給模型看的工具清單（路由用）。改了工具要一起改這裡。
#     第二欄的 key 就是**允許的參數**：validate_args 只留這些 key，模型多塞的（例如 action: delete）一律丟掉。
TOOL_SPECS = [
    ("user_report", {"username": "學號或帳號"},
     "某個帳號的狀態、寄給他的信、刪除紀錄、實驗室與封存、MYAI 綁定、訓練"),
    ("myai_status", {}, "MYAI 廠商同步是否正常、最近失敗原因、廠商現在連不連得上"),
    ("recent_errors", {"hours": "數字，預設 24"}, "最近的錯誤與警告（服務層與 GPU 節點）"),
    ("job_report", {"job_id": "訓練任務 id 或開頭幾碼"}, "某一次訓練的狀況、失敗原因"),
    ("system_status", {}, "各服務是否正常、GPU 節點、排隊中的訓練、開著的實驗室、磁碟"),
    ("email_report", {"kind": "類別，可留空：告警／登入／實驗室／MYAI／密碼",
                      "status": "狀態，可留空：失敗／退信／被擋",
                      "to": "收件人的學號或信箱，可留空", "days": "幾天內，預設 7"},
     "平台寄出的信：最近寄了哪些、寄給管理員的告警信、哪些沒寄到（退信、失敗、被擋）與原因"),
    ("admin_activity", {"action": "動作，可留空：刪帳號／臨時帳號／匯出／點數／解鎖／停止實驗室",
                        "target": "被操作的學號，可留空", "admin": "做操作的管理員帳號，可留空",
                        "days": "幾天內，預設 30"},
     "管理員做過的操作（稽核紀錄）：誰刪了誰、誰建了臨時帳號、誰發了點數、誰匯出了名單"),
    ("log_search", {"keyword": "要找的字（學號、錯誤訊息的一段）", "hours": "幾小時內，預設 24，最多 72"},
     "在服務層與 GPU 節點的日誌裡找含某個字的行"),
]


def _iso(dt) -> Optional[str]:
    """ZH: 時間一律轉成台北時間的字串（給人看），None 照回 None。

    @node job-scheduler/app/services/admin_ai_tools.py::_iso
    """
    if not dt:
        return None
    if isinstance(dt, str):
        # ZH: 封存清單之類的資料給的是 ISO 字串（UTC）—— 一樣轉成台北時間，
        #     不然同一份報告裡有的時間是台北、有的是 UTC，管理員會看錯 8 小時。
        try:
            dt = datetime.fromisoformat(dt)
        except ValueError:
            return dt
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    from ..gpu_schedule import TZ_TAIPEI
    return dt.astimezone(TZ_TAIPEI).strftime("%Y-%m-%d %H:%M")


def _utc(dt):
    """@node job-scheduler/app/services/admin_ai_tools.py::_utc"""
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _container_logs(name: str, hours: float) -> str:
    """ZH: 讀某個容器最近幾小時的日誌（唯讀）。讀不到回空字串，不讓整個查詢失敗。

    @node job-scheduler/app/services/admin_ai_tools.py::_container_logs
    """
    try:
        import docker
        c = docker.from_env().containers.get(name)
        since = datetime.now(timezone.utc) - timedelta(hours=hours)
        return c.logs(since=since, stdout=True, stderr=True).decode("utf-8", errors="replace")
    except Exception as e:  # noqa: BLE001 - 日誌讀不到只是少一段資料
        logger.info("admin_ai: 讀不到 %s 的日誌：%s", name, e)
        return ""


# ══════════════════════════════════════════════════════════════════════
# ZH: 一、帳號
# ══════════════════════════════════════════════════════════════════════

def user_report(db: Session, username: str) -> dict:
    """ZH: 一個帳號的全貌。2026-10-04 人工查 12361114 時走過的每一步都在這裡。

    @node job-scheduler/app/services/admin_ai_tools.py::user_report
    """
    username = (username or "").strip()
    if not username:
        return {"title": "帳號查詢", "facts": {}, "findings": ["沒有給帳號或學號。"], "tables": {}}
    U, A, E = models.User, models.AdminAction, models.EmailLog
    u = db.query(U).filter(U.username == username).first()
    findings, tables, facts = [], {}, {"username": username, "exists": bool(u)}

    # ZH: 刪除紀錄（帳號刪了 target_user 會是 NULL，只能從 payload 找學號）
    deletions = []
    for a in db.query(A).filter(A.action == "delete_user", A.payload.like(f"%{username}%")) \
                        .order_by(A.timestamp).all():
        try:
            p = json.loads(a.payload or "{}")
        except ValueError:
            p = {}
        if p.get("username") != username:
            continue
        who = a.admin_username
        if not who and a.admin_id:
            w = db.query(U).filter(U.id == a.admin_id).first()
            who = w.username if w else a.admin_id[:8]
        deletions.append({"時間": _iso(a.timestamp), "執行者": who or "（未記錄）",
                          "被刪的帳號 id": (p.get("deleted_user_id") or "")[:8],
                          "當時是管理員": bool(p.get("is_admin"))})
    tables["刪除紀錄"] = deletions

    emails_to = [username]
    if u:
        facts.update({
            "id": u.id[:8], "身分": u.role, "管理員": bool(u.is_admin), "啟用": bool(u.is_active),
            "登入方式": u.auth_source, "主信箱": u.email, "常用信箱": u.contact_email,
            "到期": _iso(u.expires_at), "建立": _iso(u.created_at),
            "最後活動": _iso(getattr(u, "last_activity", None)),
            "學系": getattr(u, "department", None),
        })
        emails_to += [x for x in (u.email, u.contact_email) if x]
        if not u.is_active:
            findings.append("這個帳號目前是**停用**狀態，登不進來。")
        exp = _utc(u.expires_at)
        if exp and exp < datetime.now(timezone.utc):
            findings.append(f"這個帳號已經在 {_iso(exp)} 到期。")
    else:
        if deletions:
            d = deletions[-1]
            findings.append(f"這個帳號**目前不存在**；最近一次在 {d['時間']} 被 {d['執行者']} 刪除。")
        else:
            findings.append("找不到這個帳號，也沒有刪除紀錄 —— 可能從來沒有建立過，或學號打錯。")

    # ZH: 寄信紀錄
    q = db.query(E).filter(or_(E.username == username, E.to_email.in_(emails_to),
                               *( [E.user_id == u.id] if u else [] )))
    mails = q.order_by(E.created_at.desc()).limit(12).all()
    tables["最近寄給他的信"] = [{"時間": _iso(m.created_at), "類別": m.kind, "狀態": m.status,
                              "主旨": (m.subject or "")[:60], "收件": m.to_email} for m in mails]
    if any(m.status in ("bounced", "failed") for m in mails):
        findings.append("最近有信**沒寄到**（退信或失敗），看下面「最近寄給他的信」的狀態欄。")

    # ZH: 曾被刪除重建：帳號建立時間晚於這個學號最早的一封信
    if u and mails:
        earliest = min(_utc(m.created_at) for m in mails if m.created_at)
        created = _utc(u.created_at)
        if created and earliest and earliest < created - timedelta(minutes=1):
            last_del = deletions[-1]["時間"] if deletions else "（刪除紀錄裡找不到）"
            findings.append(f"這個學號**曾被刪除後重建**：現在的帳號在 {_iso(created)} 建立，"
                            f"但更早就有寄給這個學號的信。最近一次刪除：{last_del}。")

    # ZH: 實驗室與封存
    if u:
        sess = db.query(models.LabSession).filter(models.LabSession.user_id == u.id).all()
        tables["實驗室存檔"] = [{"存檔": s.session_name, "狀態": s.status, "volume": s.volume_name,
                              "最後啟動": _iso(s.started_at)} for s in sess]
    try:
        from . import lab_manager
        archives = [a for a in lab_manager.list_archives(db) if a.get("username") == username]
    except Exception as e:  # noqa: BLE001
        logger.info("admin_ai: 讀不到封存清單：%s", e)
        archives = []
    tables["實驗室封存（刪帳號時留下的）"] = [
        {"volume": a.get("volume_name"), "大小 MB": round((a.get("size_bytes") or 0) / 1048576),
         "原因": a.get("reason"), "封存": _iso(a.get("archived_at")), "銷毀": _iso(a.get("expires_at")),
         "剩幾天": a.get("days_left"), "已還原": bool(a.get("restored_at"))} for a in archives]
    for a in archives:
        if a.get("restored_at") or not a.get("exists", True):
            continue
        old_id = (a.get("user_id") or "")[:8]
        cur = " —— 不是目前這個帳號的，目前帳號的實驗室不受影響" if (u and old_id and old_id != u.id[:8]) else ""
        findings.append(f"有一份實驗室封存（舊帳號 {old_id}，{round((a.get('size_bytes') or 0) / 1048576)} MB）"
                        f"將在 {_iso(a.get('expires_at'))} 銷毀（剩 {a.get('days_left')} 天）{cur}。"
                        "銷毀前會寄兩次通知到同一個信箱。")

    # ZH: MYAI
    if u:
        acc = db.query(models.ExternalAiAccount).filter(models.ExternalAiAccount.user_id == u.id).first()
        if acc:
            row = None
            if acc.myai_vendor_sn:
                row = db.query(models.MyaiAccount).filter(
                    models.MyaiAccount.vendor_sn == acc.myai_vendor_sn).first()
            facts["MYAI"] = {"綁定帳號": acc.vendor_username, "狀態": acc.status,
                             "點數": (row.points if row else None),
                             "初始點數": acc.credit_granted_pts, "發點備註": acc.credit_grant_note}
            if acc.status != "active":
                findings.append(f"MYAI 綁定狀態是 {acc.status}，不是 active。")
            if (acc.credit_grant_note or "").startswith(("failed", "unknown")):
                findings.append(f"MYAI 初始點數發放有問題：{acc.credit_grant_note}")
        else:
            facts["MYAI"] = "沒有綁定"

        # ZH: 訓練
        J = models.TrainingJob
        jobs = db.query(J).filter(J.user_id == u.id).order_by(J.created_at.desc()).limit(6).all()
        tables["最近的訓練"] = [{"id": j.id[:8], "狀態": j.status, "種類": crud.builtin_task_for(j) or "自帶程式",
                               "建立": _iso(j.created_at), "錯誤": (j.error_message or "")[:60]} for j in jobs]

    if not findings:
        findings.append("沒有看到異常。")
    return {"title": f"帳號 {username}", "facts": facts, "findings": findings, "tables": tables}


# ══════════════════════════════════════════════════════════════════════
# ZH: 二、MYAI 同步
# ══════════════════════════════════════════════════════════════════════

def _tcp_ok(host: str, port: int = 443, timeout: float = 5.0) -> tuple:
    """ZH: 從服務層連一次廠商的 443（跟同步走同一條網路）。回 (通不通, 說明)。

    @node job-scheduler/app/services/admin_ai_tools.py::_tcp_ok
    """
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True, "連得上"
    except socket.timeout:
        return False, f"連線逾時（{timeout:.0f} 秒）"
    except OSError as e:
        return False, f"連不上（{e.__class__.__name__}: {e}）"


_TS = re.compile(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)")


def _log_time(line: str):
    """@node job-scheduler/app/services/admin_ai_tools.py::_log_time"""
    m = _TS.match(line)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def myai_status(db: Session) -> dict:
    """ZH: MYAI 同步現在好不好。2026-10-03 人工查廠商掛掉時走過的每一步都在這裡。

    @node job-scheduler/app/services/admin_ai_tools.py::myai_status
    """
    logs = _container_logs(SCHEDULER_CONTAINER, 48).splitlines()
    ok = [l for l in logs if "MYAI 自動同步完成" in l]
    bad = [l for l in logs if "MYAI 自動同步錯誤" in l or "MYAI 自動同步失敗" in l]
    retried = [l for l in logs if "MYAI" in l and "次失敗" in l]
    last_ok, last_bad = (_log_time(ok[-1]) if ok else None), (_log_time(bad[-1]) if bad else None)
    reach, why = _tcp_ok(MYAI_HOST)
    facts = {
        "最近成功": _iso(last_ok), "最近失敗": _iso(last_bad),
        "48 小時內成功次數": len(ok), "48 小時內失敗次數": len(bad), "重試救回次數": len(retried),
        "廠商現在": why,
        "同步間隔（小時）": crud.get_setting(db, "myai_sync_interval_hours"),
        "告警最短間隔（小時）": crud.get_setting(db, "admin_alert_min_hours"),
    }
    if bad:
        facts["最近失敗原因"] = bad[-1].split("error:", 1)[-1].strip()[:200]
    E = models.EmailLog
    alert = db.query(E).filter(E.kind == "alert:myai_sync").order_by(E.created_at.desc()).first()
    facts["最近一封同步告警信"] = _iso(alert.created_at) if alert else None

    findings = []
    if not reach:
        findings.append(f"**現在連不到廠商**（{MYAI_HOST}:443 {why}）。如果別的網站都正常，"
                        "多半是廠商自己掛了；廠商恢復後下一輪同步會自動補上，不用手動處理。")
    if last_bad and (not last_ok or last_bad > last_ok):
        findings.append(f"最近一次同步在 {_iso(last_bad)} **失敗**，之後還沒有成功過。")
    elif last_bad:
        findings.append(f"48 小時內失敗 {len(bad)} 次（最近一次 {_iso(last_bad)}），"
                        f"之後已經恢復（最近成功 {_iso(last_ok)}）。")
    if retried:
        findings.append(f"48 小時內有 {len(retried)} 次是「第一下連線斷掉、重試救回來」—— 偶發，不用處理。")
    if not ok and not bad:
        findings.append("48 小時內的日誌裡沒有同步紀錄（服務可能剛重啟，或同步被關掉了）。")
    if not findings:
        findings.append("同步正常。")
    return {"title": "MYAI 同步狀態", "facts": facts, "findings": findings, "tables": {}}


# ══════════════════════════════════════════════════════════════════════
# ZH: 三、最近的錯誤
# ══════════════════════════════════════════════════════════════════════

_NORMALIZE = [
    (re.compile(r"^\S+ \S+ \| "), ""),                       # 時間戳
    (re.compile(r"[0-9a-f]{8}-[0-9a-f-]{27,}"), "<id>"),     # uuid
    (re.compile(r"\b\d+(\.\d+)?\b"), "<n>"),                 # 數字
]


def recent_errors(db: Session, hours=24) -> dict:
    """ZH: 服務層與 GPU 節點最近的錯誤／警告，相同訊息合併計數（不然一個重複的警告會洗掉其他的）。

    @node job-scheduler/app/services/admin_ai_tools.py::recent_errors
    """
    try:
        hours = max(1, min(int(hours or 24), 168))
    except (TypeError, ValueError):
        hours = 24
    groups = {}
    for src, name in (("服務層", SCHEDULER_CONTAINER), ("GPU 節點", WORKER_CONTAINER)):
        for line in _container_logs(name, hours).splitlines():
            if not re.search(r"\b(ERROR|WARNING|CRITICAL)\b|\[(ERROR|WARNING)\]|Traceback", line):
                continue
            key = line
            for rx, rep in _NORMALIZE:
                key = rx.sub(rep, key)
            key = (src, key[:160])
            g = groups.setdefault(key, {"來源": src, "次數": 0, "第一次": None, "最近": None,
                                        "範例": line[:220]})
            g["次數"] += 1
            t = _log_time(line)
            if t:
                g["第一次"] = g["第一次"] or _iso(t)
                g["最近"] = _iso(t)
                g["範例"] = line[:220]
    rows = sorted(groups.values(), key=lambda g: -g["次數"])[:15]
    findings = ([f"最近 {hours} 小時沒有錯誤或警告。"] if not rows else
                [f"最近 {hours} 小時有 {sum(g['次數'] for g in groups.values())} 行錯誤／警告，"
                 f"合併成 {len(groups)} 種；最多的是：{rows[0]['範例'][:120]}（{rows[0]['次數']} 次）。"])
    return {"title": f"最近 {hours} 小時的錯誤與警告", "facts": {"小時": hours},
            "findings": findings, "tables": {"錯誤與警告（相同的合併）": rows}}


# ══════════════════════════════════════════════════════════════════════
# ZH: 四、某一次訓練
# ══════════════════════════════════════════════════════════════════════

def job_report(db: Session, job_id: str) -> dict:
    """ZH: 用 id 或開頭幾碼找一次訓練。對到多筆就列出來讓管理員挑，不猜。

    @node job-scheduler/app/services/admin_ai_tools.py::job_report
    """
    import os
    jid = re.sub(r"[^0-9a-fA-F-]", "", job_id or "")
    J = models.TrainingJob
    if len(jid) < 4:
        return {"title": "訓練查詢", "facts": {}, "findings": ["任務 id 至少要給開頭 4 碼。"], "tables": {}}
    hits = db.query(J).filter(J.id.like(f"{jid}%")).limit(6).all()
    if not hits:
        return {"title": "訓練查詢", "facts": {"id": jid}, "findings": [f"找不到開頭是 {jid} 的訓練。"], "tables": {}}
    if len(hits) > 1:
        return {"title": "訓練查詢", "facts": {"id": jid},
                "findings": [f"開頭是 {jid} 的訓練有 {len(hits)} 筆，請多給幾碼。"],
                "tables": {"符合的訓練": [{"id": j.id[:12], "狀態": j.status, "建立": _iso(j.created_at)} for j in hits]}}
    j = hits[0]
    owner = db.query(models.User).filter(models.User.id == j.user_id).first()
    try:
        ms = json.loads(j.metrics) if isinstance(j.metrics, str) else (j.metrics or [])
    except ValueError:
        ms = []
    summ = next((m for m in reversed(ms) if isinstance(m, dict) and m.get("kind") == "summary"), {})
    mis = next((m for m in reversed(ms) if isinstance(m, dict) and m.get("kind") == "mistakes"), {})
    from ..routers.worker import artifact_path
    facts = {
        "id": j.id[:12], "名稱": j.job_name, "使用者": owner.username if owner else None,
        "狀態": j.status, "種類": crud.builtin_task_for(j) or "自帶程式",
        "建立": _iso(j.created_at), "開始": _iso(j.started_at), "結束": _iso(j.completed_at),
        "最佳正確率": summ.get("best_val_accuracy"), "花費秒數": summ.get("elapsed_seconds"),
        "判斷錯的": f"{mis.get('wrong')}/{mis.get('checked')}" if mis else None,
        "有模型檔": bool(j.artifact_bytes) and os.path.isfile(artifact_path(j.id)),
        "資料集還在": bool(j.dataset_path) and os.path.isfile(j.dataset_path or ""),
        "錯誤訊息": j.error_message,
    }
    findings = []
    if j.status == "failed":
        findings.append(f"這次訓練**失敗**：{(j.error_message or '沒有錯誤訊息').strip()[:200]}")
        tail = [l for l in (j.logs or "").splitlines() if l.strip()][-15:]
        if tail:
            return {"title": f"訓練 {j.id[:8]}", "facts": facts, "findings": findings,
                    "tables": {"訓練紀錄最後 15 行": [{"行": l[:200]} for l in tail]}}
    elif j.status in ("pending", "queued"):
        findings.append("這次訓練還在**排隊**。看「系統狀態」可以知道 GPU 節點在不在線。")
    elif j.status == "completed" and j.artifact_bytes and not facts["有模型檔"]:
        findings.append("訓練完成，但模型檔已經不在伺服器上（可能已逾保留期）。")
    if not findings:
        findings.append(f"狀態：{j.status}。")
    return {"title": f"訓練 {j.id[:8]}", "facts": facts, "findings": findings, "tables": {}}


# ══════════════════════════════════════════════════════════════════════
# ZH: 五、系統狀態
# ══════════════════════════════════════════════════════════════════════

def system_status(db: Session) -> dict:
    """ZH: 各服務容器、GPU 節點心跳、排隊、開著的實驗室、磁碟。

    @node job-scheduler/app/services/admin_ai_tools.py::system_status
    """
    rows, findings = [], []
    try:
        import docker
        for c in docker.from_env().containers.list(all=True):
            name = c.name
            if not (name.startswith("ai-platform-") or name == WORKER_CONTAINER):
                continue
            health = (c.attrs.get("State", {}).get("Health") or {}).get("Status")
            rows.append({"服務": name, "狀態": c.status, "健康檢查": health or "—"})
            if c.status != "running" or health == "unhealthy":
                findings.append(f"**{name}** 不正常：{c.status}{'／' + health if health else ''}。")
    except Exception as e:  # noqa: BLE001
        findings.append(f"讀不到容器清單（{e.__class__.__name__}）。")
    now = datetime.now(timezone.utc)
    nodes = []
    for h in db.query(models.WorkerHeartbeat).all():
        age = (now - _utc(h.last_seen)).total_seconds() if h.last_seen else None
        nodes.append({"節點": h.node_id, "最後心跳": _iso(h.last_seen),
                      "幾秒前": round(age) if age is not None else None})
        if age is None or age > 180:
            findings.append(f"GPU 節點 **{h.node_id}** 已經 {round(age or 0)} 秒沒有心跳。")
    J = models.TrainingJob
    queued = db.query(J).filter(J.status.in_(["pending", "queued"])).count()
    running = db.query(J).filter(J.status.in_(["running", "assigned"])).count()
    labs = db.query(models.LabSession).filter(models.LabSession.status == "running").count()
    du = shutil.disk_usage("/data") if __import__("os").path.isdir("/data") else None
    facts = {"排隊中的訓練": queued, "執行中的訓練": running, "開著的實驗室": labs,
             # ZH: v4.39 GPU 依身分開放 —— 只講總開關會誤導（總開關開著，學生仍可能沒開放）。
             "GPU 總開關": "開" if crud.get_setting(db, "gpu_features_enabled") else "全部暫停",
             "GPU 開放的身分": "、".join(
                 zh for r, zh, _e in crud.ROLES if crud.get_setting(db, "gpu_enabled_%s" % r)
             ) or "（都沒開）",
             "帳號": crud.account_cap_state(db),
             "資料磁碟剩餘 GB": round(du.free / 1024 ** 3) if du else None}
    if du and du.free / du.total < 0.1:
        findings.append("資料磁碟剩不到 10%。")
    if not findings:
        findings.append("各服務正常。")
    return {"title": "系統狀態", "facts": facts, "findings": findings,
            "tables": {"服務": rows, "GPU 節點": nodes}}


# ══════════════════════════════════════════════════════════════════════
# ZH: 六、寄信紀錄（2026-10-05 擁有者問「查寄信」「近期寄出的管理信」時沒有對應的查詢）
# ══════════════════════════════════════════════════════════════════════

# ZH: 信件類別 → 中文。新增寄信類別時在這裡補一行；沒補也不會壞，只是畫面顯示原始代碼。
KIND_LABEL = {
    "login_alert": "登入通知", "password_change_alert": "密碼變更通知",
    "account_provisioned": "帳號開通（含臨時密碼）", "password_reset": "密碼重設", "temp_password": "臨時密碼",
    "myai_provisioned": "MYAI 開通通知", "myai_balance:low": "MYAI 點數偏低",
    "myai_balance:empty": "MYAI 點數用完",
    "lab_purge:first": "實驗室銷毀通知（第一次）", "lab_purge:final": "實驗室銷毀通知（最後一次）",
    "alert:myai_sync": "管理告警：MYAI 同步失敗", "alert:myai_balance_alert": "管理告警：MYAI 餘額",
    "alert:myai_topup": "管理告警：MYAI 每月補點", "alert:bounce_scan": "管理告警：退信回收",
    "alert:watchdog_test": "管理告警：測試信", "smtp_465_test": "寄信測試",
}
STATUS_LABEL = {
    "sent": "已交給郵件伺服器", "failed": "寄送失敗", "bounced": "退信（地址有問題）",
    "deferred": "暫時退信（對方伺服器晚點再收）", "refused": "被郵件伺服器拒收",
    "blocked": "平台擋下沒寄（保留網域）", "mock": "測試模式，沒有真的寄",
}
_PROBLEM = ("failed", "bounced", "deferred", "refused", "blocked")

# ZH: 類別關鍵字 → kind 前綴。中英文都認；認不得就不篩、在 findings 講明。
_KIND_GROUPS = [
    (("告警", "管理", "alert", "admin"), "管理告警", ("alert:",)),
    (("登入", "login"), "登入通知", ("login_alert",)),
    (("實驗室", "銷毀", "封存", "lab"), "實驗室銷毀通知", ("lab_purge:",)),
    (("密碼", "開通帳號", "password"), "帳號與密碼", ("password", "account_provisioned", "temp_password")),
    (("點數", "myai", "餘額"), "MYAI", ("myai_",)),
]
_STATUS_GROUPS = [
    (("退信", "bounce"), "退信", ("bounced", "deferred")),
    (("被擋", "擋下", "blocked"), "被擋", ("blocked",)),
    (("失敗", "沒寄到", "寄不出", "有問題", "problem", "fail"), "沒寄成功", _PROBLEM),
    (("成功", "寄出", "sent"), "已寄出", ("sent",)),
]
_IDENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._@+\-]{1,127}$")


def kind_label(kind: Optional[str]) -> str:
    """@node job-scheduler/app/services/admin_ai_tools.py::kind_label"""
    if not kind:
        return "（未分類）"
    if kind in KIND_LABEL:
        return KIND_LABEL[kind]
    if kind.startswith("alert:"):
        return "管理告警：" + kind[6:]
    return kind


def _pick(text, groups):
    """ZH: 從一段話裡認出類別／狀態。回 (名稱, 值) 或 None。

    @node job-scheduler/app/services/admin_ai_tools.py::_pick
    """
    t = (text or "").strip().lower()
    if not t:
        return None
    for words, name, values in groups:
        if any(w.lower() in t for w in words):
            return name, values
    return None


def _int(v, default, lo, hi):
    """@node job-scheduler/app/services/admin_ai_tools.py::_int"""
    try:
        return max(lo, min(int(v), hi))
    except (TypeError, ValueError):
        return default


def _ident(v) -> Optional[str]:
    """ZH: 學號／帳號／信箱才收；「請提供帳號」這種說明文字回 None。

    @node job-scheduler/app/services/admin_ai_tools.py::_ident
    """
    v = str(v or "").strip()
    return v if _IDENT.match(v) else None


def email_report(db: Session, kind="", status="", to="", days=7) -> dict:
    """ZH: 平台寄出的信。可依類別、狀態、收件人、天數篩。

    ZH: ⚠ 「已交給郵件伺服器」不等於「對方收到」—— 退信是事後才回填的（bounce_reader）。
        管理告警還有節流：同一類在設定的小時數內只寄一封，其餘的只記在日誌（這裡也會數出來）。

    @node job-scheduler/app/services/admin_ai_tools.py::email_report
    """
    days = _int(days, 7, 1, 90)
    E = models.EmailLog
    since = datetime.now(timezone.utc) - timedelta(days=days)
    q = db.query(E).filter(E.created_at >= since.replace(tzinfo=None))
    findings, facts = [], {"幾天內": days}

    k = _pick(kind, _KIND_GROUPS)
    if k:
        q = q.filter(or_(*[E.kind.like(f"{v}%") for v in k[1]]))
        facts["類別"] = k[0]
    elif str(kind or "").strip():
        findings.append(f"看不懂「{kind}」這個類別，已列出全部類別。")
    st = _pick(status, _STATUS_GROUPS)
    if st:
        q = q.filter(E.status.in_(st[1]))
        facts["狀態"] = st[0]
    elif str(status or "").strip():
        findings.append(f"看不懂「{status}」這個狀態，已列出全部狀態。")
    who = _ident(to)
    if who:
        cond = [E.to_email == who] if "@" in who else [E.username == who, E.to_email.like(f"{who}@%")]
        q = q.filter(or_(*cond))
        facts["收件人"] = who
    elif str(to or "").strip():
        findings.append(f"「{to}」不像學號或信箱，已忽略、不篩收件人。")

    rows = q.order_by(E.created_at.desc()).limit(5000).all()
    facts["共幾封"] = len(rows)

    stats = {}
    for m in rows:
        g = stats.setdefault(m.kind, {"類別": kind_label(m.kind), "共": 0, "已交給郵件伺服器": 0,
                                      "沒寄成功": 0, "最近一封": _iso(m.created_at)})
        g["共"] += 1
        if m.status == "sent":
            g["已交給郵件伺服器"] += 1
        elif m.status in _PROBLEM:
            g["沒寄成功"] += 1
    tables = {
        "依類別統計": sorted(stats.values(), key=lambda g: -g["共"]),
        "最近的信（最多 30 封）": [
            {"時間": _iso(m.created_at), "類別": kind_label(m.kind),
             "狀態": STATUS_LABEL.get(m.status, m.status), "收件": m.to_email,
             # ZH: 不切 " | " —— 告警信主旨是「[AI Base 告警 | Alert] 標題」，切了只剩前綴。
             "主旨": (m.subject or "")[:90],
             "原因": (m.detail or "")[:120] or None} for m in rows[:30]],
    }

    if not rows:
        findings.append(f"最近 {days} 天沒有符合的信。")
    else:
        findings.append(f"最近 {days} 天共 {len(rows)} 封，"
                        + "、".join(f"{g['類別']} {g['共']} 封" for g in tables["依類別統計"][:6]) + "。")
    bad = [m for m in rows if m.status in _PROBLEM]
    if bad:
        by = {}
        for m in bad:
            by.setdefault(m.status, []).append(m)
        for code, ms in by.items():
            last = ms[0]
            findings.append(f"**{STATUS_LABEL.get(code, code)}** {len(ms)} 封；最近一封 {_iso(last.created_at)} "
                            f"寄給 {last.to_email}（{kind_label(last.kind)}），原因：{(last.detail or '沒有記錄')[:120]}")
        if "blocked" in by:
            findings.append("「平台擋下」是收件地址用了保留網域（例如 example.com），平台刻意不寄，不是故障。")

    # ZH: 管理告警：收件人沒設就一封都不會寄；節流略過的只在日誌裡。
    #     只在「看全部」或「看告警」時講 —— 問「哪些信沒寄到」時混進告警節流是答非所問。
    if (not k and not st and not who) or (k and k[0] == "管理告警"):
        to_set = crud.get_setting(db, "admin_alert_emails") or ""
        cc_set = crud.get_setting(db, "admin_alert_cc_emails") or ""
        facts["告警收件人 To"] = to_set or None
        facts["告警收件人 CC"] = cc_set or None
        facts["同一類告警最短間隔（小時）"] = crud.get_setting(db, "admin_alert_min_hours")
        if not to_set.strip() and not cc_set.strip():
            findings.append("**沒有設定管理告警的收件人**，告警信一封都不會寄出（平台設定 → 寄信）。")
        hours = min(days * 24, 168)
        skipped = [l for l in _container_logs(SCHEDULER_CONTAINER, hours).splitlines()
                   if "已寄過" in l and "略過" in l]
        if skipped:
            facts[f"最近 {hours} 小時因節流沒寄的告警"] = len(skipped)
            findings.append(f"另外有 {len(skipped)} 次告警因為「同一類在間隔內已寄過」而沒有再寄（只記在日誌）。")
    if rows:
        findings.append("「已交給郵件伺服器」不保證對方收到；退信會在之後回填，狀態會變成退信。")
    return {"title": "寄信紀錄", "facts": facts, "findings": findings, "tables": tables}


# ══════════════════════════════════════════════════════════════════════
# ZH: 七、管理操作紀錄（稽核）
# ══════════════════════════════════════════════════════════════════════

ACTION_LABEL = {
    "delete_user": "刪除帳號", "create_temp_account": "建立臨時帳號", "extend_temp_account": "延長臨時帳號",
    "export_users": "匯出帳號名單", "grant_profile_unlock": "開放修改個人資料",
    "revoke_profile_unlock": "收回修改個人資料", "myai_grant_points": "發 MYAI 點數",
    "myai_manual_topup": "手動補 MYAI 點數", "force_stop_lab": "強制停止實驗室", "ai_query": "AI 查詢",
}
_ACTION_GROUPS = [
    (("刪", "delete"), "刪除帳號", ("delete_user",)),
    (("臨時", "temp"), "臨時帳號", ("create_temp_account", "extend_temp_account")),
    (("匯出", "export"), "匯出名單", ("export_users",)),
    (("點數", "myai", "補點"), "MYAI 點數", ("myai_grant_points", "myai_manual_topup")),
    (("解鎖", "個人資料", "unlock"), "個人資料解鎖", ("grant_profile_unlock", "revoke_profile_unlock")),
    (("實驗室", "停止", "lab"), "強制停止實驗室", ("force_stop_lab",)),
    (("ai", "查詢", "提問"), "AI 查詢", ("ai_query",)),
]


def _payload_text(raw: Optional[str]) -> str:
    """ZH: 稽核內容精簡成一行（拿掉長 id，畫面放得下）。

    @node job-scheduler/app/services/admin_ai_tools.py::_payload_text
    """
    try:
        p = json.loads(raw or "{}")
    except ValueError:
        return (raw or "")[:120]
    if not isinstance(p, dict):
        return str(p)[:120]
    keep = {k: v for k, v in p.items() if k not in ("deleted_user_id", "columns", "expires_at", "new_expires_at")}
    return ", ".join(f"{k}={v}" for k, v in keep.items())[:160]


def admin_activity(db: Session, action="", target="", admin="", days=30) -> dict:
    """ZH: 管理員做過的事（admin_actions）。預設不含「AI 查詢」本身 —— 那會洗掉其他操作。

    @node job-scheduler/app/services/admin_ai_tools.py::admin_activity
    """
    days = _int(days, 30, 1, 365)
    A, U = models.AdminAction, models.User
    since = datetime.now(timezone.utc) - timedelta(days=days)
    q = db.query(A).filter(A.timestamp >= since.replace(tzinfo=None))
    findings, facts = [], {"幾天內": days}
    act = _pick(action, _ACTION_GROUPS)
    if act:
        q = q.filter(A.action.in_(act[1]))
        facts["動作"] = act[0]
    else:
        if str(action or "").strip():
            findings.append(f"看不懂「{action}」這個動作，已列出全部動作。")
        q = q.filter(A.action != "ai_query")
    who = _ident(admin)
    if who:
        wu = db.query(U).filter(U.username == who).first()
        q = q.filter(or_(A.admin_username == who, *([A.admin_id == wu.id] if wu else [])))
        facts["管理員"] = who
    elif str(admin or "").strip():
        findings.append(f"「{admin}」不像帳號，已忽略、不篩管理員。")
    tgt = _ident(target)
    if tgt:
        u = db.query(U).filter(U.username == tgt).first()
        cond = [A.payload.like(f'%"{tgt}"%')]
        if u:
            cond.append(A.target_user == u.id)
        q = q.filter(or_(*cond))
        facts["對象"] = tgt
    elif str(target or "").strip():
        findings.append(f"「{target}」不像學號，已忽略、不篩對象。")

    rows = q.order_by(A.timestamp.desc()).limit(2000).all()
    ids = {r.target_user for r in rows if r.target_user} | {r.admin_id for r in rows if r.admin_id}
    names = {u.id: u.username for u in db.query(U).filter(U.id.in_(ids)).all()} if ids else {}

    def _admin(r):
        # ZH: 較早的紀錄沒存 admin_username，只有 admin_id（2026-10-05 實測 44/64 筆）—— 反查帳號。
        return r.admin_username or names.get(r.admin_id) or "（未記錄）"

    def _target(r):
        # ZH: target_user 是外鍵（刪帳號時變 NULL），所以有值就一定找得到人；NULL 才去 payload 找。
        if r.target_user and r.target_user in names:
            return names[r.target_user]
        try:
            p = json.loads(r.payload or "{}")
        except ValueError:
            p = {}
        return (p.get("username") or p.get("email")) if isinstance(p, dict) else None

    counts = {}
    for r in rows:
        c = counts.setdefault(r.action, {"動作": ACTION_LABEL.get(r.action, r.action), "次數": 0,
                                         "最近": _iso(r.timestamp), "做的人": set()})
        c["次數"] += 1
        c["做的人"] |= {_admin(r)}
    count_rows = [dict(c, 做的人="、".join(sorted(c["做的人"]))) for c in
                  sorted(counts.values(), key=lambda c: -c["次數"])]
    tables = {
        "依動作統計": count_rows,
        "最近的操作（最多 30 筆）": [
            {"時間": _iso(r.timestamp), "管理員": _admin(r),
             "動作": ACTION_LABEL.get(r.action, r.action), "對象": _target(r),
             "內容": _payload_text(r.payload), "IP": r.ip_address} for r in rows[:30]],
    }
    facts["共幾筆"] = len(rows)
    if not rows:
        findings.append(f"最近 {days} 天沒有符合的管理操作。")
    else:
        findings.append(f"最近 {days} 天共 {len(rows)} 筆："
                        + "、".join(f"{c['動作']} {c['次數']} 次" for c in count_rows[:6]) + "。")
        dels = [r for r in rows if r.action == "delete_user"]
        if dels:
            findings.append(f"其中**刪除帳號 {len(dels)} 次**，最近一次 {_iso(dels[0].timestamp)} "
                            f"由 {_admin(dels[0])} 刪除 {_target(dels[0])}。")
    return {"title": "管理操作紀錄", "facts": facts, "findings": findings, "tables": tables}


# ══════════════════════════════════════════════════════════════════════
# ZH: 八、日誌搜尋
# ══════════════════════════════════════════════════════════════════════

# ZH: 🔴 日誌裡偶爾會有 token（下載網址的 ?token=、Authorization 標頭）。
#     它們只會送進本機模型、只給管理員看，但仍然遮掉 —— 畫面可能被截圖、貼到別處。
_REDACT = [
    (re.compile(r"eyJ[\w-]{8,}\.[\w-]{8,}\.[\w-]{8,}"), "<遮蔽的 token>"),
    (re.compile(r"(?i)(bearer\s+)[\w.\-]+"), r"\1<遮蔽>"),
    (re.compile(r"(?i)\b(token|access_token|password|passwd|secret|api_key|apikey|key)=([^&\s\"']+)"), r"\1=<遮蔽>"),
]


def _redact(line: str) -> str:
    """@node job-scheduler/app/services/admin_ai_tools.py::_redact"""
    for rx, rep in _REDACT:
        line = rx.sub(rep, line)
    return line


def log_search(db: Session, keyword="", hours=24) -> dict:
    """ZH: 在服務層與 GPU 節點的日誌裡找含某個字的行（不分大小寫），最多列最近 40 行。

    @node job-scheduler/app/services/admin_ai_tools.py::log_search
    """
    kw = str(keyword or "").strip()
    hours = _int(hours, 24, 1, 72)
    if len(kw) < 2 or len(kw) > 80:
        return {"title": "日誌搜尋", "facts": {}, "findings": ["要找的字至少 2 個字、最多 80 個字。"], "tables": {}}
    low = kw.lower()
    hits = []
    for src, name in (("服務層", SCHEDULER_CONTAINER), ("GPU 節點", WORKER_CONTAINER)):
        for line in _container_logs(name, hours).splitlines():
            if low in line.lower():
                t = _log_time(line)
                hits.append({"來源": src, "時間": _iso(t) if t else None, "內容": _redact(line)[:300]})
    facts = {"關鍵字": kw, "幾小時內": hours, "共幾行": len(hits)}
    if not hits:
        findings = [f"最近 {hours} 小時的日誌裡沒有「{kw}」。"
                    "（日誌只保留到服務上次重啟；更早的事可以改查寄信或管理操作紀錄。）"]
    else:
        findings = [f"最近 {hours} 小時的日誌裡有 {len(hits)} 行含「{kw}」"
                    + ("，只列最後 40 行。" if len(hits) > 40 else "。")]
    return {"title": f"日誌搜尋：{kw}", "facts": facts, "findings": findings,
            "tables": {"符合的日誌": hits[-40:]}}


# ══════════════════════════════════════════════════════════════════════
# ZH: 參數驗證（2026-10-05：模型把「請提供帳號」「管理員帳號」當成學號填進來）
# ══════════════════════════════════════════════════════════════════════

_ASK_FOR = {
    "user_report": ("username", "要查哪個帳號？請給學號或帳號，例如：檢查 12361114 帳號狀態。"),
    "job_report": ("job_id", "要查哪一次訓練？請給訓練任務 id（至少開頭 4 碼）。"),
    "log_search": ("keyword", "要在日誌裡找什麼？請給要找的字，例如：日誌裡找「12361114」。"),
}


def validate_args(name: str, args) -> tuple:
    """ZH: 只留 TOOL_SPECS 宣告過的參數；必填的參數看起來是說明文字就回 (args, 要問管理員的話)。

    @node job-scheduler/app/services/admin_ai_tools.py::validate_args
    """
    allowed = next((set(a) for n, a, _ in TOOL_SPECS if n == name), set())
    clean = {k: v for k, v in (args or {}).items() if k in allowed and v not in (None, "")}
    need = _ASK_FOR.get(name)
    if need:
        key, ask = need
        v = str(clean.get(key) or "").strip()
        ok = {"username": lambda x: bool(_ident(x)),
              "job_id": lambda x: len(re.sub(r"[^0-9a-fA-F]", "", x)) >= 4 and re.fullmatch(r"[0-9a-fA-F-]+", x),
              "keyword": lambda x: 2 <= len(x) <= 80 and not re.search(r"(請提供|請輸入|關鍵字|<|>)", x)}[key](v)
        if not ok:
            return clean, ask
    return clean, None


TOOLS = {
    "user_report": lambda db, a: user_report(db, a.get("username", "")),
    "myai_status": lambda db, a: myai_status(db),
    "recent_errors": lambda db, a: recent_errors(db, a.get("hours", 24)),
    "job_report": lambda db, a: job_report(db, a.get("job_id", "")),
    "system_status": lambda db, a: system_status(db),
    "email_report": lambda db, a: email_report(db, a.get("kind", ""), a.get("status", ""),
                                               a.get("to", ""), a.get("days", 7)),
    "admin_activity": lambda db, a: admin_activity(db, a.get("action", ""), a.get("target", ""),
                                                   a.get("admin", ""), a.get("days", 30)),
    "log_search": lambda db, a: log_search(db, a.get("keyword", ""), a.get("hours", 24)),
}
assert set(TOOLS) == {t[0] for t in TOOL_SPECS}, "TOOL_SPECS 與 TOOLS 對不上"
