# -*- coding: utf-8 -*-
"""
ZH: 公告附件（v3.9）。

ZH: 這裡釘的四件事，每一件都是「壞掉的時候畫面上看不出來」的那種：
    1. 副檔名白名單 —— .html/.svg 傳得進來就是一個在自己網域下執行的 XSS
    2. 草稿的附件不可以外流 —— 公告藏起來了，附件的網址卻還通
    3. 下載一律 Content-Disposition: attachment + nosniff —— 不可以內嵌開啟
    4. 刪公告要**連磁碟上的檔案一起刪** —— CASCADE 只清資料庫的列
"""
import io
import os

import pytest
from conftest import auth_headers, make_user

from app import models
from app.routers import announcements as ann_mod


@pytest.fixture()
def admin_headers(client, db):
    """ZH: 建立管理員並取得 token。email 用 @example.com（RFC 保留網域）——
       測試帳號一律不用真網域，不然 login_alert 會真的寄出去。"""
    make_user(db, username="ann-admin", email="ann-admin@example.com", role="admin")
    return auth_headers(client, "ann-admin", "password123")


@pytest.fixture()
def ann_dir(tmp_path, monkeypatch):
    """ZH: 把附件目錄指到暫存資料夾 —— 測試不碰 /data。"""
    d = tmp_path / "announcements"
    monkeypatch.setattr(ann_mod, "ANNOUNCEMENT_DIR", str(d))
    return d


def _ann(db, *, visible=1):
    a = models.Announcement(title="公告", body="內文", is_visible=visible)
    db.add(a)
    db.commit()
    return a


def _upload(client, admin_headers, ann_id, name, content=b"x" * 16):
    return client.post(
        f"/api/v1/admin/announcements/{ann_id}/files",
        headers=admin_headers,
        files={"file": (name, io.BytesIO(content), "application/octet-stream")},
    )


def test_upload_and_download(client, db, admin_headers, ann_dir):
    a = _ann(db)

    up = _upload(client, admin_headers, a.id, "說明.pdf", b"hello-pdf")
    assert up.status_code == 201, up.text
    fid = up.json()["id"]
    # ZH: 回應不得含 stored_name —— 那是磁碟上的路徑片段
    assert "stored_name" not in up.json()
    assert up.json()["filename"] == "說明.pdf"

    dl = client.get(f"/api/v1/announcements/{a.id}/files/{fid}", headers=admin_headers)
    assert dl.status_code == 200
    assert dl.content == b"hello-pdf"
    # ZH: 一律當附件下載，且不准瀏覽器猜型別
    assert "attachment" in dl.headers.get("content-disposition", "")
    assert dl.headers.get("x-content-type-options") == "nosniff"


@pytest.mark.parametrize("bad", ["evil.html", "evil.svg", "evil.exe", "evil.js"])
def test_extension_whitelist(client, db, admin_headers, ann_dir, bad):
    """ZH: 🔴 .html/.svg 會在**我們自己的網域下**執行 script。"""
    a = _ann(db)

    r = _upload(client, admin_headers, a.id, bad)

    assert r.status_code == 400, f"{bad} 不應該傳得進來"


def test_path_traversal_filename(client, db, admin_headers, ann_dir):
    """ZH: 檔名帶目錄成分時只留最後一段，不可以寫到別的地方去。"""
    a = _ann(db)

    r = _upload(client, admin_headers, a.id, "../../etc/passwd.pdf")

    assert r.status_code == 201
    # ZH: 檔案必須落在這則公告自己的資料夾裡
    files = list((ann_dir / str(a.id)).iterdir())
    assert len(files) == 1
    assert files[0].parent.name == str(a.id)


def test_hidden_announcement_hides_its_files(client, db, admin_headers, ann_dir):
    """ZH: 🔴 草稿的附件不可以外流 —— 公告藏起來了，網址卻還通。"""
    a = _ann(db)
    fid = _upload(client, admin_headers, a.id, "草稿附件.pdf").json()["id"]

    a.is_visible = 0
    db.commit()

    r = client.get(f"/api/v1/announcements/{a.id}/files/{fid}", headers=admin_headers)

    # ZH: 回 404 不回 403 —— 403 等於承認「這裡有東西但你不能看」
    assert r.status_code == 404


def test_delete_announcement_removes_files_from_disk(client, db, admin_headers, ann_dir):
    """ZH: 🔴 CASCADE 只清資料庫的列，磁碟上的檔案要自己刪。"""
    a = _ann(db)
    _upload(client, admin_headers, a.id, "會被刪的.pdf")
    on_disk = ann_dir / str(a.id)
    assert on_disk.exists()

    r = client.delete(f"/api/v1/admin/announcements/{a.id}", headers=admin_headers)
    assert r.status_code in (200, 204), r.text

    assert not on_disk.exists(), "公告刪了，附件目錄卻還在——這就是孤兒"
    assert db.query(models.AnnouncementFile).count() == 0


def test_delete_single_file(client, db, admin_headers, ann_dir):
    a = _ann(db)
    fid = _upload(client, admin_headers, a.id, "一個.pdf").json()["id"]

    r = client.delete(f"/api/v1/admin/announcements/{a.id}/files/{fid}",
                      headers=admin_headers)

    assert r.status_code == 204, r.text
    assert db.query(models.AnnouncementFile).count() == 0
    assert not list((ann_dir / str(a.id)).iterdir())


def test_per_file_size_limit(client, db, admin_headers, ann_dir, monkeypatch):
    """ZH: 超過單檔上限要擋，而且**不可以留下半個檔案**。

    ZH: 留著的話它會一直算進總量，而列表上看不到它 ——
        症狀是「明明沒幾個附件卻說滿了」。
    """
    from app import crud
    real = crud.get_setting
    monkeypatch.setattr(
        crud, "get_setting",
        lambda db_, k: 1 if k == "announcement_file_max_mb" else real(db_, k))

    a = _ann(db)
    r = _upload(client, admin_headers, a.id, "太大.pdf", b"y" * (2 * 1024 * 1024))

    assert r.status_code == 413
    assert not list((ann_dir / str(a.id)).iterdir()), "半個檔案沒有清掉"


def test_files_listed_on_announcement(client, db, admin_headers, ann_dir):
    """ZH: 公告列表要帶出附件，前端才畫得出連結。"""
    a = _ann(db)
    _upload(client, admin_headers, a.id, "附件.pdf")

    rows = client.get("/api/v1/announcements", headers=admin_headers).json()

    me = [r for r in rows if r["id"] == a.id][0]
    assert [f["filename"] for f in me["files"]] == ["附件.pdf"]
