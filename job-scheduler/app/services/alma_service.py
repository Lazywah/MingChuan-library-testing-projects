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
from typing import Optional

import requests

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

# ZH: campus_code → 平台校區名（org_seed.CAMPUSES 的值）。
#     實測只見過 SL/TY；未知代碼不猜、不預填。
CAMPUS_CODES = {"SL": "台北", "TY": "桃園"}


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
