"""
ZH: 組織對照表的管理端編輯（v3.8）—— 學系→學院、行政單位、校區。

ZH: 端點（都掛在 /api/v1/admin/org 底下，全部要 admin）：
      GET  /departments   學系清單 + 每個系有幾個人
      PUT  /departments   批次寫入（新增／改學院／改校區／停用／改名）
      GET  /units         行政單位清單 + 每個單位有幾個人
      PUT  /units         同上

ZH: 🔴 **沒有刪除，只有停用。** `users.department` 存的是**系名本身**、
    `users.unit` 存的是 `org_units.path` —— 都不是外鍵。
    把一列刪掉，填過那個系的人不會有任何錯誤，他們只是**從分組統計裡消失**，
    而且沒有人會發現。`active=0` 才是正確的做法：留著對得上，只是不進下拉。
    （`OrgDepartment.active` 的原始註解就寫著「停招的留著但不進下拉」。）

ZH: 🔴 **改名一定要連動使用者，否則同一個坑會從另一邊發生。**
    主鍵就是使用者存的那個字串，所以改名 = 把所有填過舊名的人變成孤兒。
    這裡在同一個交易裡一起改，並把「動到幾個人」回報給前端顯示 ——
    管理者按下去之前要看得到影響範圍。

ZH: ⚠ 校區一律對照 `org_seed.CAMPUSES` 驗。打錯的值存進去之後，
    那一列在任何以校區分組的報表裡都會自成一格，看起來像多了一個校區。
    （`crud.set_user_campuses` 也是這樣驗的，兩邊用同一份清單。）
"""
from typing import Any, Optional

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import models, org_seed
from ..auth import require_admin
from ..database import get_db

router = APIRouter(tags=["組織對照 Org"])


# ── 共用 ────────────────────────────────────────────────────────────────
def _clean_campus(v: Optional[str]) -> Optional[str]:
    """
    ZH: 校區欄位正規化。空字串一律存成 NULL —— 「沒填」與「填了空字串」
        在報表裡會是兩種不同的分組，看起來像多出一個沒有名字的校區。

    @node job-scheduler/app/routers/org.py::_clean_campus
    """
    c = (v or "").strip()
    if not c:
        return None
    if c not in org_seed.CAMPUSES:
        raise HTTPException(
            status_code=400,
            detail=(f"ZH: 沒有這個校區：{c}（可選：{'、'.join(org_seed.CAMPUSES)}） | "
                    f"EN: Unknown campus: {c}"))
    return c


def _as_active(v: Any) -> int:
    """ZH: 前端可能送 true/1/"1"。一律收斂成 0/1。

    @node job-scheduler/app/routers/org.py::_as_active
    """
    return 0 if v in (0, "0", False, "false", "False") else 1


# ── 學系 ────────────────────────────────────────────────────────────────
@router.get("/departments", summary="學系→學院對照（含每系人數）")
def list_departments(db: Session = Depends(get_db),
                     _: models.User = Depends(require_admin)) -> Any:
    """
    ZH: 含 `users` 人數 —— 停用或改名之前要看得到影響範圍。

    @node job-scheduler/app/routers/org.py::list_departments
    """
    counts = dict(db.query(models.User.department, func.count(models.User.id))
                  .filter(models.User.department.isnot(None))
                  .group_by(models.User.department).all())
    rows = (db.query(models.OrgDepartment)
            .order_by(models.OrgDepartment.college, models.OrgDepartment.name).all())
    return {
        "campuses": org_seed.CAMPUSES,
        "colleges": sorted({r.college for r in rows}),
        "rows": [{"name": r.name, "college": r.college, "campus": r.campus,
                  "active": r.active, "users": counts.get(r.name, 0)} for r in rows],
    }


@router.put("/departments", summary="批次寫入學系對照")
def save_departments(payload: dict = Body(...),
                     db: Session = Depends(get_db),
                     _: models.User = Depends(require_admin)) -> Any:
    """
    ZH: body: `{"rows": [{"key": 現在的系名 or null(新增), "name", "college",
        "campus", "active"}]}`

    ZH: `key` 與 `name` 不同 = 改名 → 連同 `users.department` 一起改。

    @node job-scheduler/app/routers/org.py::save_departments
    """
    rows = payload.get("rows")
    if not isinstance(rows, list):
        raise HTTPException(status_code=400, detail="ZH: rows 要是陣列 | EN: rows must be a list")

    added = updated = renamed = moved_users = 0
    for r in rows:
        name = (r.get("name") or "").strip()
        college = (r.get("college") or "").strip()
        if not name or not college:
            raise HTTPException(status_code=400,
                                detail="ZH: 系名與學院都不能空白 | EN: name and college are required")
        campus = _clean_campus(r.get("campus"))
        active = _as_active(r.get("active", 1))
        key = (r.get("key") or "").strip() or None

        if key is None:
            if db.get(models.OrgDepartment, name):
                raise HTTPException(status_code=409,
                                    detail=f"ZH: 已經有這個學系：{name} | EN: duplicate: {name}")
            db.add(models.OrgDepartment(name=name, college=college,
                                        campus=campus, active=active))
            added += 1
            continue

        cur = db.get(models.OrgDepartment, key)
        if not cur:
            raise HTTPException(status_code=404,
                                detail=f"ZH: 找不到學系：{key} | EN: not found: {key}")

        if name != key:
            # ZH: 改名 —— 主鍵換掉，所以是「新增一列 + 刪掉舊列」，
            #     而且**填過舊名的人要一起搬**，否則他們會從分組統計裡消失。
            if db.get(models.OrgDepartment, name):
                raise HTTPException(status_code=409,
                                    detail=f"ZH: 已經有這個學系：{name} | EN: duplicate: {name}")
            moved_users += (db.query(models.User)
                            .filter(models.User.department == key)
                            .update({models.User.department: name},
                                    synchronize_session=False))
            db.add(models.OrgDepartment(name=name, college=college,
                                        campus=campus, active=active))
            db.delete(cur)
            renamed += 1
            continue

        if (cur.college, cur.campus, cur.active) != (college, campus, active):
            cur.college, cur.campus, cur.active = college, campus, active
            updated += 1

    db.commit()
    return {"added": added, "updated": updated, "renamed": renamed,
            "moved_users": moved_users}


# ── 行政單位 ────────────────────────────────────────────────────────────
@router.get("/units", summary="行政單位（含每單位人數）")
def list_units(db: Session = Depends(get_db),
               _: models.User = Depends(require_admin)) -> Any:
    """
    ZH: ⚠ 人數用 `users.unit` 比對，而那裡存的是 **path 不是 name**
        （官網底下有兩個「事務組」，名稱會撞 —— 見 models.OrgUnit）。

    @node job-scheduler/app/routers/org.py::list_units
    """
    counts = dict(db.query(models.User.unit, func.count(models.User.id))
                  .filter(models.User.unit.isnot(None))
                  .group_by(models.User.unit).all())
    rows = db.query(models.OrgUnit).order_by(models.OrgUnit.path).all()
    return {
        "campuses": org_seed.CAMPUSES,
        "rows": [{"path": r.path, "name": r.name, "parent": r.parent,
                  "campus": r.campus, "active": r.active,
                  "users": counts.get(r.path, 0)} for r in rows],
    }


@router.put("/units", summary="批次寫入行政單位")
def save_units(payload: dict = Body(...),
               db: Session = Depends(get_db),
               _: models.User = Depends(require_admin)) -> Any:
    """
    ZH: body: `{"rows": [{"key": 現在的 path or null(新增), "name", "parent",
        "campus", "active"}]}`

    ZH: path 由 `parent/name` 推出來，不讓前端直接送 —— 前端自己組的話，
        兩邊的組法遲早會不一致，而不一致的那一天沒有任何錯誤訊息。

    @node job-scheduler/app/routers/org.py::save_units
    """
    rows = payload.get("rows")
    if not isinstance(rows, list):
        raise HTTPException(status_code=400, detail="ZH: rows 要是陣列 | EN: rows must be a list")

    added = updated = renamed = moved_users = 0
    for r in rows:
        name = (r.get("name") or "").strip()
        if not name:
            raise HTTPException(status_code=400,
                                detail="ZH: 單位名稱不能空白 | EN: name is required")
        parent = (r.get("parent") or "").strip() or None
        campus = _clean_campus(r.get("campus"))
        active = _as_active(r.get("active", 1))
        path = f"{parent}/{name}" if parent else name
        key = (r.get("key") or "").strip() or None

        if key is None:
            if db.get(models.OrgUnit, path):
                raise HTTPException(status_code=409,
                                    detail=f"ZH: 已經有這個單位：{path} | EN: duplicate: {path}")
            db.add(models.OrgUnit(path=path, name=name, parent=parent,
                                  campus=campus, active=active))
            added += 1
            continue

        cur = db.get(models.OrgUnit, key)
        if not cur:
            raise HTTPException(status_code=404,
                                detail=f"ZH: 找不到單位：{key} | EN: not found: {key}")

        if path != key:
            if db.get(models.OrgUnit, path):
                raise HTTPException(status_code=409,
                                    detail=f"ZH: 已經有這個單位：{path} | EN: duplicate: {path}")
            moved_users += (db.query(models.User)
                            .filter(models.User.unit == key)
                            .update({models.User.unit: path},
                                    synchronize_session=False))
            db.add(models.OrgUnit(path=path, name=name, parent=parent,
                                  campus=campus, active=active))
            db.delete(cur)
            renamed += 1
            continue

        if (cur.name, cur.campus, cur.active) != (name, campus, active):
            cur.name, cur.campus, cur.active = name, campus, active
            updated += 1

    db.commit()
    return {"added": added, "updated": updated, "renamed": renamed,
            "moved_users": moved_users}
