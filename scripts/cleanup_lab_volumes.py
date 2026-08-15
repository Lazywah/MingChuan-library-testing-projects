#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
==============================================================================
Lab volume 盤點與清理 (v3.3) | Inventory & cleanup of per-user Lab volumes
==============================================================================
ZH: 掃描所有 `home_*` volume，分類為四種並可選擇性清除：

      使用中        對應現存使用者（現行命名：底線）→ 絕不刪
      封存          已登記在 archived_lab_volumes（到期由背景任務自動銷毀）→ 不刪
      舊命名(dash)  早期以連字號命名的殘留（現行程式用底線）→ 可刪
      孤兒          使用者已不存在、也不在封存清單（多半是加入封存機制前刪掉的帳號）→ 可刪

    ⚠️ 預設只「列出」不刪。確認清單後加 --apply 才會真的移除。
    ⚠️ 「孤兒」可能仍含當事人的檔案，刪除不可逆；如需保留請改用 --adopt
       將其收編為封存（沿用 lab_archive_days 天數，之後才自動銷毀）。

EN: Classify all `home_*` volumes (in-use / archived / legacy-dash / orphan) and
    optionally remove the removable ones. Dry-run by default.

用法 / Usage（需在 scheduler 容器內執行，因需同時存取 DB 與 docker socket）：
  docker exec ai-platform-scheduler python /app/scripts/cleanup_lab_volumes.py
  docker exec ai-platform-scheduler python /app/scripts/cleanup_lab_volumes.py --apply
  docker exec ai-platform-scheduler python /app/scripts/cleanup_lab_volumes.py --adopt --apply
==============================================================================
"""
import sys

sys.path.insert(0, "/app")

IN_USE, ARCHIVED, LEGACY, ORPHAN = "使用中", "封存", "舊命名(dash)", "孤兒"


def human(n):
    """@node scripts/cleanup_lab_volumes.py::human"""
    if n is None:
        return "?"
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.1f}{unit}" if unit != "B" else f"{n}B"
        n /= 1024.0


def classify():
    """@node scripts/cleanup_lab_volumes.py::classify"""
    import docker
    from app.database import SessionLocal
    from app import models

    db = SessionLocal()
    dc = docker.from_env()
    user_ids = {u.id for u in db.query(models.User).all()}
    in_use = {uid.replace("-", "_") for uid in user_ids}          # 現行命名：底線
    legacy_ok = {uid for uid in user_ids}                          # 舊命名：連字號
    archived = {a.volume_name for a in db.query(models.ArchivedLabVolume).all()}

    sizes = {}
    try:
        for d in dc.df().get("Volumes", []):
            sizes[d["Name"]] = (d.get("UsageData") or {}).get("Size")
    except Exception:
        pass

    rows = []
    for v in sorted(x.name for x in dc.volumes.list()):
        if not v.startswith("home_"):
            continue
        body = v[5:]
        if body in in_use:
            kind = IN_USE
        elif v in archived:
            kind = ARCHIVED
        elif body in legacy_ok:
            kind = LEGACY          # dash 版且對應現存使用者 → 舊命名殘留
        else:
            kind = ORPHAN
        rows.append({"name": v, "kind": kind, "size": sizes.get(v)})
    return db, dc, rows


def main():
    """@node scripts/cleanup_lab_volumes.py::main"""
    apply_ = "--apply" in sys.argv
    adopt = "--adopt" in sys.argv
    db, dc, rows = classify()

    print()
    print("=== Lab volume 盤點 ===")
    total_removable = 0
    for r in rows:
        mark = "  " if r["kind"] in (IN_USE, ARCHIVED) else "→ "
        print(f"  {mark}{r['name']:48} {r['kind']:14} {human(r['size']):>10}")
        if r["kind"] in (LEGACY, ORPHAN) and r["size"]:
            total_removable += r["size"]

    targets = [r for r in rows if r["kind"] in (LEGACY, ORPHAN)]
    orphans = [r for r in targets if r["kind"] == ORPHAN]
    print()
    print(f"可處理 {len(targets)} 個（其中孤兒 {len(orphans)} 個），共約 {human(total_removable)}")

    if not targets:
        print("沒有需要處理的 volume。")
        return 0

    if adopt and orphans:
        # ZH: 把孤兒收編為封存 → 給它保留期而非立刻銷毀
        from datetime import datetime, timedelta, timezone
        from app import models, crud
        days = crud.get_setting(db, "lab_archive_days")
        now = datetime.now(timezone.utc)
        for r in orphans:
            if db.query(models.ArchivedLabVolume).filter_by(volume_name=r["name"]).first():
                continue
            if apply_:
                db.add(models.ArchivedLabVolume(
                    volume_name=r["name"], size_bytes=r["size"], reason="adopted_orphan",
                    archived_at=now, expires_at=now + timedelta(days=days)))
            print(f"  {'收編' if apply_ else '[試跑] 將收編'}為封存（{days} 天後銷毀）：{r['name']}")
        if apply_:
            db.commit()
        targets = [r for r in targets if r["kind"] == LEGACY]   # 孤兒已收編，只剩舊命名要刪

    if not apply_:
        print()
        print("（試跑模式，未實際刪除。確認無誤後加 --apply 執行；")
        print("  想保留孤兒資料請用 --adopt --apply 收編為封存。）")
        return 0

    removed = 0
    for r in targets:
        try:
            dc.volumes.get(r["name"]).remove(force=True)
            print(f"  已刪除 {r['name']}")
            removed += 1
        except Exception as e:
            print(f"  刪除失敗 {r['name']}: {e}")
    print(f"\n完成，共刪除 {removed} 個 volume。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
