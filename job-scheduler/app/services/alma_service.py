# -*- coding: utf-8 -*-
"""
ZH: 圖書館 Alma API —— SSO 首次登入時查權威身分。

ZH: 背景（2026-09-02）：圖書館提供唯讀查詢的 API Key。在此之前身分只能
    用信箱網域猜（7 碼員編/8 碼學號/英文帳號，見 sso_policy.yaml），
    而老師與職員同網域根本分不出來，只能請本人首登自選。
    Alma 的 `user_group` 直接回答這題，附帶慣用信箱（圖書館寄通知的那個，
    比我們組出來的可靠）。

ZH: 🔴 保守版（擁有者裁定 2026-09-02）：**只映射實測確認過的代碼**，
    未知代碼一律當「查無」→ 呼叫端走原本的網域判定＋首登自選。
    寧可多問一次本人，也不要拿猜的代碼表定人家的權限。

ZH: 🔴 這支在**登入路徑**上 —— 任何失敗（沒設 Key、逾時、5xx、格式不對）
    都回 None，絕不拋例外、絕不拖慢登入超過 timeout。
    降級後的行為＝接 Alma 之前的行為，不會更糟。

@node job-scheduler/app/services/alma_service.py
"""
import logging
from datetime import datetime, timezone
from typing import Optional

import requests
from sqlalchemy import func

from ..config import settings

logger = logging.getLogger(__name__)

# ZH: 實測確認的 user_group 代碼（2026-09-02，拿真實證號逐一驗過）：
#       0  = 大學生    → student
#       61 = 專任教師  → teacher
#       63 = 行政人員  → staff
#     完整代碼表尚未取得（可能還有兼任教師、研究生等）——
#     不在表上的代碼**不猜**，讓呼叫端降級。拿到代碼表後在這裡補。
USER_GROUP_ROLES = {
    "0":  "student",
    "61": "teacher",
    "63": "staff",
}

# ZH: 登入路徑上的外呼要短 —— Alma 慢就放棄，別讓全校的登入陪它等。
TIMEOUT_SECONDS = 4

# ZH: campus_code → 平台校區名（org_seed.CAMPUSES 的值）。未知代碼不猜、不預填。
# ZH: 2026-09-07 掃了 3,315 位教職員後補齊五碼（原本只有 SL/TY，
#     於是基河 152 人、金門 24 人、美國分校 12 人的校區一律預填不到）。
#     GH/KM/MI 是**用資料反推的**，不是猜的 —— 那些人的單位分別集中在
#     產學暨推廣處／進修推廣處（基河）、金門分部、美國分校。
CAMPUS_CODES = {"SL": "台北", "TY": "桃園",
                "GH": "基河", "KM": "金門", "MI": "美國分校"}


def lookup_identity(sub: str) -> Optional[dict]:
    """
    ZH: 以 學號/員編（SSO 的 sub）查 Alma。回：
          {"role": "teacher"|"staff"|"student"|None,   # None = 代碼不在保守表上
           "email": "<preferred 信箱>"|None,
           "user_group": "<代碼>", "user_group_desc": "<中文描述>"}
        查不到 / 未設 Key / 任何錯誤 → 回 None（呼叫端自行降級）。

    ZH: ⚠ 回應含個資（信箱、系所）——**不要**把整包 response 寫進 log，
        log 只記代碼與判定結果。

    @node job-scheduler/app/services/alma_service.py::lookup_identity
    """
    if not settings.ALMA_API_KEY:
        return None
    sub = (sub or "").strip()
    if not sub:
        return None

    url = (settings.ALMA_BASE_URL.rstrip("/")
           + f"/almaws/v1/users/{sub}")
    try:
        r = requests.get(
            url,
            params={"user_id_type": "all_unique", "view": "full",
                    "expand": "none", "apikey": settings.ALMA_API_KEY},
            headers={"Accept": "application/json"},
            timeout=TIMEOUT_SECONDS,
        )
    except requests.RequestException as e:
        logger.warning("Alma 查詢失敗（%s）：%s —— 降級走網域判定", sub, e)
        return None

    if r.status_code != 200:
        # ZH: 400 查無此人是正常情況（校外訪客、離職）——記 info 不記 warning。
        (logger.info if r.status_code == 400 else logger.warning)(
            "Alma 回 %s（%s）—— 降級走網域判定", r.status_code, sub)
        return None

    try:
        d = r.json()
        group = str((d.get("user_group") or {}).get("value") or "")
        desc = (d.get("user_group") or {}).get("desc") or ""
        email = None
        for e in (d.get("contact_info") or {}).get("email") or []:
            if e.get("preferred"):
                email = (e.get("email_address") or "").strip() or None
                break
    except (ValueError, AttributeError, TypeError) as e:
        logger.warning("Alma 回應解析失敗（%s）：%s —— 降級走網域判定", sub, e)
        return None

    role = USER_GROUP_ROLES.get(group)
    if role is None:
        # ZH: 有查到人但代碼不在保守表上 —— 講出來，日後補表就靠這些 log。
        logger.info("Alma user_group=%s(%s) 不在保守對照表，角色交回網域判定（%s）",
                    group, desc, sub)

    # ZH: v4.2 預填初次設定用的欄位（擁有者裁定 2026-09-02）。
    #     user_statistic 的 desc 長相是「代碼-名稱[-名稱…]」：
    #       ZBE 學系  36-資訊工程學系-Computer Science…  → 取第 2 段中文名
    #       ZBT 單位  0721-圖書館-資訊組                 → 取第 2 段起（可能多層）
    #     這裡只**萃取**，對得上平台組織表才用（見 crud.apply_alma_profile）。
    campus = CAMPUS_CODES.get(str((d.get("campus_code") or {}).get("value") or ""))
    department = None
    unit_segments = None
    for st in d.get("user_statistic") or []:
        cat = (st.get("category_type") or {}).get("value")
        parts = ((st.get("statistic_category") or {}).get("desc") or "").split("-")
        if cat == "ZBE" and len(parts) >= 2 and department is None:
            department = parts[1].strip() or None
        elif cat == "ZBT" and len(parts) >= 2 and unit_segments is None:
            unit_segments = [x.strip() for x in parts[1:] if x.strip()] or None

    return {"role": role, "email": email,
            "user_group": group, "user_group_desc": desc,
            "campus": campus, "department": department,
            "unit_segments": unit_segments}


# ══════════════════════════════════════════════════════════════════════════
# ZH: 既有帳號的定期回填（擁有者需求 2026-09-07）
# ══════════════════════════════════════════════════════════════════════════
# ZH: 為什麼需要：SSO 只在**建號當下**問 Alma（見 routers/sso.py）。之後
#     Alma 那邊改了身分／系所／信箱，平台不會自己跟上。2026-09-03 用一次性
#     腳本補過一輪，那種東西不會有人記得再跑第二次。
#
# ZH: 🔴 鐵則：**只補空值，絕不覆蓋**。
#       role   —— 只升級 role_source='sso_email'（當初用信箱猜的）。
#                 人工設過（admin）或本人選過（self_onboard）一律不動。
#       校區/系所/單位/常用信箱 —— 空的才寫。
#       主信箱 —— **永遠不動**（它是 MYAI 綁定與身分的鍵）。
#     這條界線是刻意的：管理者的判斷與本人的確認，權威高於 Alma 的快照。
# ══════════════════════════════════════════════════════════════════════════

# ZH: 一次跑幾個人。Alma 是外部 API，全校跑下去要幾千次往返——分批做，
#     下一輪接著跑（`synced_at` 沒有欄位可記，所以用「最久沒登入的優先」
#     這種無狀態排序：每輪都會輪到不同的人，長期覆蓋全體）。
BACKFILL_BATCH = 50


def backfill_users(db, limit: int = BACKFILL_BATCH, dry_run: bool = False) -> dict:
    """
    ZH: 拿 Alma 補既有帳號的空欄位。回 {checked, changed, skipped, details:[...]}。

    ZH: 跳過：本機帳號、臨時帳號（有 expires_at）、Alma 查無。
    ZH: `dry_run=True` 只算不寫 —— 管理端可以先看會動到誰。

    @node job-scheduler/app/services/alma_service.py::backfill_users
    """
    from .. import crud, models

    q = (db.query(models.User)
           .filter(models.User.auth_source != "local")
           .filter(models.User.expires_at.is_(None))
           # ZH: 最久沒登入的先補 —— 無狀態的輪替，不必為此加一張表。
           .order_by(models.User.last_login_time.asc().nullsfirst()))
    users = q.limit(max(1, limit)).all()

    out = {"checked": 0, "changed": 0, "skipped": 0, "details": []}
    for u in users:
        out["checked"] += 1
        alma = lookup_identity(u.username)
        if alma is None:
            out["skipped"] += 1
            continue

        plan = []
        # ── 角色：只升級「當初用信箱猜的」──────────────────────────────
        if alma.get("role") and u.role_source == "sso_email":
            if alma["role"] != u.role:
                plan.append("role: %s→%s" % (u.role, alma["role"]))
                if not dry_run:
                    u.role = alma["role"]
            else:
                plan.append("role_source: sso_email→alma")
            if not dry_run:
                u.role_source = "alma"

        # ── 校區：完全沒設才補 ────────────────────────────────────────
        has_campus = (db.query(models.UserCampus)
                        .filter(models.UserCampus.user_id == u.id).count() > 0)
        if not has_campus and alma.get("campus"):
            plan.append("campus=%s" % alma["campus"])
            if not dry_run:
                try:
                    crud.set_user_campuses(db, u, [alma["campus"]])
                except ValueError as e:
                    plan[-1] += "（略過：%s）" % e

        # ── 學系／單位：照角色對應的那一欄，空的才補、對得上組織表才寫 ──
        role_now = alma.get("role") if (alma.get("role") and u.role_source in
                                        ("sso_email", "alma")) else u.role
        field = crud.ONBOARDING_FIELDS.get(role_now, "department")
        if field == "department" and not u.department and alma.get("department"):
            v = alma["department"]
            if db.query(models.OrgDepartment).filter(
                    models.OrgDepartment.name == v).first():
                plan.append("department=%s" % v)
                if not dry_run:
                    u.department = v
        elif field == "unit" and not u.unit and alma.get("unit_segments"):
            # ZH: 對照邏輯只有 crud.match_org_unit 一份（兩段一起比，唯一解才寫）。
            hit = crud.match_org_unit(db, alma["unit_segments"])
            if hit:
                plan.append("unit=%s" % hit)
                if not dry_run:
                    u.unit = hit

        # ── 常用信箱：空的、且與主信箱不同才有意義 ────────────────────
        if (not u.contact_email and alma.get("email")
                and alma["email"].lower() != (u.email or "").lower()):
            plan.append("contact_email（Alma 慣用信箱）")
            if not dry_run:
                u.contact_email = alma["email"]

        if plan:
            out["changed"] += 1
            out["details"].append({"username": u.username, "changes": plan})

    if not dry_run and out["changed"]:
        db.commit()
    logger.info("Alma 回填：檢查 %d、變更 %d、查無 %d%s",
                out["checked"], out["changed"], out["skipped"],
                "（乾跑）" if dry_run else "")
    return out


# ══════════════════════════════════════════════════════════════════════════
# ZH: 組織對照表改以 Alma 為準（擁有者裁定 2026-09-07）
# ══════════════════════════════════════════════════════════════════════════
# ZH: 在此之前，`org_departments` / `org_units` 是 2026-08-27 從銘傳官網抓下來
#     的一份快照（51 系 + 97 單位）。它有兩個問題：
#       1. 會過時，而且過時的時候沒有任何徵兆 —— 沒有人會定期回去對官網。
#       2. 跟 Alma 對不起來。每個人的系所/單位是從 Alma 讀的，卻要拿去對一張
#          不同來源的表；對不上就留白。實測 57% 命中、25% 是官網根本沒有的。
#     擁有者的判斷是：**乾脆整張表就用 Alma 的**。同一個來源，就不會有兩份真相。
#
# ZH: 🔴 為什麼要掃全部教職員才建得出這張表：
#     Alma 沒有「組織清單」這種端點（conf/code-tables 我們的 Key 沒有權限）。
#     使用者清單 API 又不含組織欄位（只回 gender/last_name/link/password/
#     primary_id/status）。所以唯一的辦法是**逐人查明細、把出現過的組織收集起來**。
#     教師 1,236 ＋ 職員 2,079 ＝ 3,315 人，約 20 分鐘。
#     學生不掃 —— 76,907 人跑不完，而且學生的 ZBE 用的是同一份代碼表，
#     少掃學生不會漏掉任何一個學系。
#
# ZH: 🔴 「學系屬於哪個學院」是**推出來的，不是 Alma 直接說的**：
#     ZBE(學系) 與 ZBF(學院) 是同一個人身上的兩個統計欄位，靠共現才對得起來。
#     實測 82 個學系全部都對得到學院，只有 3 個對到一個以上（都是舊名 vs 新名，
#     少數那邊只有 1 個人）—— 所以取**多數決**，並把票數留在 log 裡。
# ══════════════════════════════════════════════════════════════════════════

# ZH: 掃哪些身分。學生刻意不掃（理由見上）。
HARVEST_GROUPS = ("61", "63")

# ZH: 這支不在登入路徑上（背景跑），所以逾時可以放寬 —— 4 秒是為了不讓
#     全校的登入陪 Alma 等，這裡沒有人在等。
HARVEST_TIMEOUT = 25

# ZH: 校區要幾成的人一致才敢寫。組織的 campus 只是輔助標籤（每個人自己的
#     校區存在 user_campuses，不看這欄），但寫錯會讓管理端看起來像有人搞錯了。
#     跨校區的單位（總務處在四個校區都有人）就留白，不猜。
CAMPUS_DOMINANCE = 0.9
CAMPUS_MIN_PEOPLE = 3


def _alma_get(path: str, params: dict, tries: int = 3):
    """
    ZH: 背景用的 Alma GET（會重試）。**不要拿來用在登入路徑上** ——
        那裡要的是 lookup_identity 的「一次就放棄」。

    @node job-scheduler/app/services/alma_service.py::_alma_get
    """
    import time
    url = settings.ALMA_BASE_URL.rstrip("/") + path
    for i in range(tries):
        try:
            r = requests.get(url, params=dict(params, apikey=settings.ALMA_API_KEY),
                             headers={"Accept": "application/json"},
                             timeout=HARVEST_TIMEOUT)
            if r.status_code == 200:
                return r.json()
            if r.status_code == 400:
                return None            # ZH: 查無此人，正常，不必重試
        except requests.RequestException:
            pass
        time.sleep(1.5 * (i + 1))
    return None


def _split_desc(desc):
    """
    ZH: `36-資訊工程學系-Computer Science…` → `['36','資訊工程學系','Computer…']`。
        少於兩段（只有代碼、沒有名字）回 None —— 那種值沒有東西可以顯示。

    @node job-scheduler/app/services/alma_service.py::_split_desc
    """
    parts = [x.strip() for x in (desc or "").split("-") if x.strip()]
    return parts if len(parts) >= 2 else None


def fold_org(records: list) -> dict:
    """
    ZH: 把「每人一筆」的原始紀錄摺成兩張表。**純函式，不碰網路也不碰資料庫**
        —— 掃描要 20 分鐘，這一段的規則要能單獨驗。

    ZH: 收 `[{"campus": "SL", "zbe": [代碼,中,英]|None,
                "zbf": [...]|None, "zbt": [代碼,[段,段]]|None}, …]`
        回 `{"departments": [...], "units": [...], "ambiguous": [...]}`

    @node job-scheduler/app/services/alma_service.py::fold_org
    """
    from collections import Counter, defaultdict

    dept_en = {}
    dept_college = defaultdict(Counter)      # ZH: 學系 → 學院票數（共現，見檔頭）
    college_en = {}
    dept_campus = defaultdict(Counter)
    unit_campus = defaultdict(Counter)
    unit_paths = set()

    for r in records:
        campus = CAMPUS_CODES.get(r.get("campus") or "")
        zbe, zbf, zbt = r.get("zbe"), r.get("zbf"), r.get("zbt")
        if zbe:
            name = zbe[1]
            if zbe[2] and name not in dept_en:
                dept_en[name] = zbe[2]
            if campus:
                dept_campus[name][campus] += 1
            if zbf:
                dept_college[name][zbf[1]] += 1
        if zbf and zbf[2] and zbf[1] not in college_en:
            college_en[zbf[1]] = zbf[2]
        if zbt:
            segs = zbt[1]
            path = "/".join(segs)
            unit_paths.add(path)
            # ZH: 上層也要自成一列 —— 不然 `總務處/事務組` 在下拉裡沒有
            #     可以掛的分組標題，而只有子單位的處室會整個看不見。
            if len(segs) > 1:
                unit_paths.add(segs[0])
            if campus:
                unit_campus[path][campus] += 1

    def dominant(counter):
        """ZH: 壓倒性多數才回，否則 None（理由見 CAMPUS_DOMINANCE）。"""
        total = sum(counter.values())
        if total < CAMPUS_MIN_PEOPLE:
            return None
        name, n = counter.most_common(1)[0]
        return name if n / total >= CAMPUS_DOMINANCE else None

    ambiguous = []
    departments = []
    for name in sorted(dept_en.keys() | dept_college.keys() | dept_campus.keys()):
        votes = dept_college.get(name)
        college = votes.most_common(1)[0][0] if votes else None
        if votes and len(votes) > 1:
            # ZH: 講出來 —— 多數決是猜的，猜了什麼要留下痕跡。
            ambiguous.append({"name": name, "picked": college, "votes": dict(votes)})
        departments.append({
            "name": name,
            "name_en": dept_en.get(name) or None,
            # ZH: 沒有學院可歸的學系（理論上不該有，實測 0 個）先掛「未分類」，
            #     不要留 None —— `OrgDepartment.college` 是 NOT NULL。
            "college": college or "未分類",
            "college_en": college_en.get(college) if college else None,
            "campus": dominant(dept_campus.get(name, Counter())),
        })

    units = []
    for path in sorted(unit_paths):
        segs = path.split("/")
        units.append({
            "path": path,
            "name": segs[-1],
            "parent": segs[0] if len(segs) > 1 else None,
            "campus": dominant(unit_campus.get(path, Counter())),
        })

    return {"departments": departments, "units": units, "ambiguous": ambiguous}


def harvest_org(progress=None) -> Optional[dict]:
    """
    ZH: 掃 Alma 的教職員，收集組織詞彙表。**唯讀，不寫資料庫。**
        約 20 分鐘 —— 呼叫端要自己丟到背景（見 routers/admin.py 的 org-rebuild）。

    ZH: `progress` 是 `f(done, total)`，給管理端顯示進度用。

    ZH: 任何一步失敗回 None —— 這支的失敗**不能**變成「掃到一半的清單」，
        那會讓下一步把沒掃到的單位全部當成「Alma 已經沒有了」而清掉。

    @node job-scheduler/app/services/alma_service.py::harvest_org
    """
    if not settings.ALMA_API_KEY:
        logger.warning("沒有 ALMA_API_KEY，組織掃描略過")
        return None

    ids = []
    for group in HARVEST_GROUPS:
        offset = 0
        while True:
            d = _alma_get("/almaws/v1/users",
                          {"q": f"user_group~{group}", "limit": 100, "offset": offset})
            if d is None:
                logger.warning("組織掃描：列 user_group=%s 失敗（offset=%s）", group, offset)
                return None
            page = [u.get("primary_id") for u in (d.get("user") or []) if u.get("primary_id")]
            ids += page
            if len(page) < 100:
                break
            offset += 100

    records = []
    failed = 0
    for n, pid in enumerate(ids, 1):
        if progress and n % 50 == 0:
            progress(n, len(ids))
        d = _alma_get(f"/almaws/v1/users/{pid}",
                      {"user_id_type": "all_unique", "view": "full", "expand": "none"})
        if d is None:
            failed += 1
            continue
        rec = {"campus": str((d.get("campus_code") or {}).get("value") or ""),
               "zbe": None, "zbf": None, "zbt": None}
        for st in d.get("user_statistic") or []:
            cat = (st.get("category_type") or {}).get("value")
            parts = _split_desc((st.get("statistic_category") or {}).get("desc"))
            if not parts:
                continue
            if cat == "ZBE" and rec["zbe"] is None:
                rec["zbe"] = [parts[0], parts[1], parts[2] if len(parts) > 2 else ""]
            elif cat == "ZBF" and rec["zbf"] is None:
                rec["zbf"] = [parts[0], parts[1], parts[2] if len(parts) > 2 else ""]
            elif cat == "ZBT" and rec["zbt"] is None:
                rec["zbt"] = [parts[0], parts[1:]]
        records.append(rec)

    # ZH: 🔴 掉太多人就整批放棄。半份清單會被下一步當成「Alma 精簡了組織」，
    #     然後把沒掃到的單位清掉 —— 那種錯誤看起來完全像正常的重建結果。
    if not records or failed > len(ids) * 0.05:
        logger.warning("組織掃描：%d/%d 查詢失敗，整批放棄", failed, len(ids))
        return None

    out = fold_org(records)
    out["scanned"] = len(records)
    out["failed"] = failed
    logger.info("組織掃描完成：%d 人 → %d 學系、%d 單位（%d 個學系的學院是多數決）",
                len(records), len(out["departments"]), len(out["units"]),
                len(out["ambiguous"]))
    return out


# ZH: 重建時**不會動**的來源標記。管理者自己加的一列，代表 Alma 沒有而他知道
#     它存在（新成立的單位、Alma 還沒更新的改名）—— 重建把它清掉的話，
#     那個判斷每掃一次就要重做一次。
KEEP_SOURCES = ("admin",)


def rebuild_org_from_alma(db, folded: dict, dry_run: bool = True) -> dict:
    """
    ZH: 用掃描結果重建兩張組織對照表。回一份「動了什麼」的報告。

    ZH: 規則（擁有者裁定 2026-09-07「清空我們自己抓的，改記 Alma 的」）：
          Alma 有的        → 寫進去，標 source='alma'
          管理者自己加的    → **完全不動**（source='admin'，見 KEEP_SOURCES）
          官網舊種子 / 舊的 Alma 列，而 Alma 已經沒有了：
              還有人掛在上面 → **留著但停用**（不進下拉，既有的人仍對得上）
              沒有人用       → 刪掉

    ZH: 🔴 「沒有人用才刪」這條是整支函式最重要的一行。
        `users.department` 存的是系名本身、`users.unit` 存的是 path，
        **兩個都不是外鍵** —— 刪掉一列，填過它的人不會有任何錯誤，
        他們只是從此不出現在依組織的統計裡，而且沒有人會發現。
        （routers/org.py 的檔頭寫的是同一件事：那裡索性連刪除都不做。）

    ZH: 🔴 `dry_run=True` 是預設。這支會刪列，而刪掉的東西沒有復原鍵。

    @node job-scheduler/app/services/alma_service.py::rebuild_org_from_alma
    """
    from .. import models

    report = {"departments": {"added": [], "updated": [], "disabled": [], "deleted": []},
              "units": {"added": [], "updated": [], "disabled": [], "deleted": []},
              "kept_admin": 0, "dry_run": dry_run,
              "ambiguous": folded.get("ambiguous") or [],
              "scanned": folded.get("scanned")}

    # ── 學系 ───────────────────────────────────────────────────────────
    want = {d["name"]: d for d in folded["departments"]}
    dept_users = dict(db.query(models.User.department, func.count(models.User.id))
                      .filter(models.User.department.isnot(None))
                      .group_by(models.User.department).all())
    for cur in db.query(models.OrgDepartment).all():
        if (cur.source or "") in KEEP_SOURCES:
            report["kept_admin"] += 1
            want.pop(cur.name, None)          # ZH: 人工那列優先，Alma 不覆蓋它
            continue
        d = want.pop(cur.name, None)
        if d is None:
            if dept_users.get(cur.name):
                report["departments"]["disabled"].append(cur.name)
                if not dry_run:
                    cur.active = 0
            else:
                report["departments"]["deleted"].append(cur.name)
                if not dry_run:
                    db.delete(cur)
            continue
        after = (d["college"], d["name_en"], d["college_en"], d["campus"], "alma", 1)
        if (cur.college, cur.name_en, cur.college_en, cur.campus, cur.source, cur.active) != after:
            report["departments"]["updated"].append(cur.name)
            if not dry_run:
                (cur.college, cur.name_en, cur.college_en, cur.campus,
                 cur.source, cur.active) = after
    for name, d in sorted(want.items()):
        report["departments"]["added"].append(name)
        if not dry_run:
            db.add(models.OrgDepartment(
                name=name, college=d["college"], name_en=d["name_en"],
                college_en=d["college_en"], campus=d["campus"],
                active=1, source="alma"))

    # ── 行政單位 ───────────────────────────────────────────────────────
    want = {u["path"]: u for u in folded["units"]}
    unit_users = dict(db.query(models.User.unit, func.count(models.User.id))
                      .filter(models.User.unit.isnot(None))
                      .group_by(models.User.unit).all())
    for cur in db.query(models.OrgUnit).all():
        if (cur.source or "") in KEEP_SOURCES:
            report["kept_admin"] += 1
            want.pop(cur.path, None)
            continue
        u = want.pop(cur.path, None)
        if u is None:
            if unit_users.get(cur.path):
                report["units"]["disabled"].append(cur.path)
                if not dry_run:
                    cur.active = 0
            else:
                report["units"]["deleted"].append(cur.path)
                if not dry_run:
                    db.delete(cur)
            continue
        # ZH: name_en 保留現值 —— Alma 的 ZBT 沒有英文名（只有 ZBE/ZBF 有），
        #     照抄 None 會把人工填過的英文名洗掉。
        after = (u["name"], u["parent"], u["campus"], "alma", 1)
        if (cur.name, cur.parent, cur.campus, cur.source, cur.active) != after:
            report["units"]["updated"].append(cur.path)
            if not dry_run:
                (cur.name, cur.parent, cur.campus, cur.source, cur.active) = after
    for path, u in sorted(want.items()):
        report["units"]["added"].append(path)
        if not dry_run:
            db.add(models.OrgUnit(path=path, name=u["name"], parent=u["parent"],
                                  campus=u["campus"], active=1, source="alma"))

    if not dry_run:
        # ZH: 旗標一旦寫下，開機的種子就永遠不再撒（見 crud.seed_org_tables）——
        #     否則哪天這兩張表被清空，2026-08-27 的官網舊資料會無聲地復活。
        from .. import crud
        crud.set_system_config(db, crud.ORG_REBUILT_KEY,
                               datetime.now(timezone.utc).isoformat(),
                               "組織對照表最後一次用 Alma 重建的時間")
        db.commit()
        logger.info("組織對照表已用 Alma 重建：%s", {
            k: {kk: len(vv) for kk, vv in v.items()}
            for k, v in report.items() if isinstance(v, dict) and "added" in v})
    return report
