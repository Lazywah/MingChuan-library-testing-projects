"""
ZH: 個人組織資料的一次性解鎖（v3.8，擁有者裁定 2026-08-27）。

ZH: 校區／學系／行政單位在初次設定之後上鎖,要改就跟管理員申請（用既有的
    「問題回報」送單）,核可後開放**一次**。「一次」＝成功存檔一次,不是一段時間。
"""
import pytest
from conftest import make_user, auth_headers

from app import crud, models, schemas


@pytest.fixture
def seeded(db):
    crud.seed_org_tables(db)
    return db


def _admin(db, name="adm"):
    a = make_user(db, username=name, email=f"{name}@example.com", role="staff")
    a.is_admin = 1
    db.commit()
    return a


class TestTheLockActuallyLocks:
    def test_first_time_needs_no_unlock(self, seeded):
        u = make_user(seeded)
        crud.complete_onboarding(seeded, u, ["台北"], "資訊工程學系")
        assert u.onboarded_at is not None

    def test_second_time_is_refused(self, seeded):
        u = make_user(seeded)
        crud.complete_onboarding(seeded, u, ["台北"], "資訊工程學系")
        with pytest.raises(ValueError, match="鎖定"):
            crud.complete_onboarding(seeded, u, ["桃園"], "資訊工程學系")
        assert crud.campuses_of(seeded, u.id) == ["台北"], "被擋下來了卻已經改掉一半"

    def test_put_me_can_no_longer_change_department(self, client, seeded):
        """
        ZH: 🔴 這條是整個機制的前提。v3.8 之前 `department` 在使用者端的
            UserUpdate 裡,任何人都能用 PUT /auth/me 改成任何自由文字 ——
            那既繞過組織對照表的驗證,也讓這個鎖形同虛設。
        """
        assert "department" not in schemas.UserUpdate.model_fields
        u = make_user(seeded)
        crud.complete_onboarding(seeded, u, ["台北"], "資訊工程學系")
        r = client.put("/api/v1/auth/me",
                       json={"department": "我自己編的系"},
                       headers=auth_headers(client))
        assert r.status_code == 200
        seeded.refresh(u)
        assert u.department == "資訊工程學系"


class TestOneShot:
    def test_unlock_allows_exactly_one_save(self, seeded):
        u = make_user(seeded)
        adm = _admin(seeded)
        crud.complete_onboarding(seeded, u, ["台北"], "資訊工程學系")

        crud.grant_profile_unlock(seeded, u, ["campus"], adm, "轉校區")
        crud.complete_onboarding(seeded, u, ["桃園"], None)
        assert crud.campuses_of(seeded, u.id) == ["桃園"]

        # ZH: 用掉了 —— 第二次要再申請
        with pytest.raises(ValueError, match="鎖定"):
            crud.complete_onboarding(seeded, u, ["金門"], None)

    def test_it_is_consumed_by_a_save_not_by_time(self, seeded):
        """
        ZH: 🔴 **陽性對照。** 上面那條「第二次被擋」如果是因為解鎖根本沒生效
            （也就是第一次就被擋）也會綠。這條分開驗兩件事:
            核可之後 used_at 是 NULL、成功存檔之後才變成有值。
        """
        u = make_user(seeded)
        adm = _admin(seeded)
        crud.complete_onboarding(seeded, u, ["台北"], "資訊工程學系")

        row = crud.grant_profile_unlock(seeded, u, ["campus"], adm)
        assert row.used_at is None, "核可當下就被標成用掉了"
        assert crud.active_unlock(seeded, u.id) is not None

        crud.complete_onboarding(seeded, u, ["桃園"], None)
        seeded.refresh(row)
        assert row.used_at is not None, "存檔成功了卻沒有把解鎖用掉"
        assert crud.active_unlock(seeded, u.id) is None

    def test_a_failed_save_does_not_burn_the_unlock(self, seeded):
        """ZH: 填錯被擋不該浪費掉那一次 —— 否則他要再申請一輪。"""
        u = make_user(seeded)
        adm = _admin(seeded)
        crud.complete_onboarding(seeded, u, ["台北"], "資訊工程學系")
        crud.grant_profile_unlock(seeded, u, ["campus"], adm)

        with pytest.raises(ValueError):
            crud.complete_onboarding(seeded, u, ["台中"], None)   # 不存在的校區
        assert crud.active_unlock(seeded, u.id) is not None

    def test_granting_twice_does_not_stack(self, seeded):
        """ZH: 累積多筆的話「還剩幾次」會變成沒有人算得出來的數字。"""
        u = make_user(seeded)
        adm = _admin(seeded)
        crud.grant_profile_unlock(seeded, u, ["campus"], adm)
        crud.grant_profile_unlock(seeded, u, ["department"], adm)
        assert seeded.query(models.ProfileUnlock).filter_by(user_id=u.id).count() == 1
        assert crud.active_unlock(seeded, u.id).fields == "department"

    def test_scope_is_enforced(self, seeded):
        """ZH: 核可「改校區」不能被拿來改學系。"""
        u = make_user(seeded)
        adm = _admin(seeded)
        crud.complete_onboarding(seeded, u, ["台北"], "資訊工程學系")
        crud.grant_profile_unlock(seeded, u, ["campus"], adm)
        with pytest.raises(ValueError, match="範圍"):
            crud.complete_onboarding(seeded, u, ["台北"], "會計學系")


class TestUnlockIsNotABackdoor:
    @pytest.mark.parametrize("field", ["role", "is_admin", "is_active", "email", "password"])
    def test_privileged_fields_can_never_be_unlocked(self, seeded, field):
        """
        ZH: 🔴 使用者不能自己上管理員那條線是型別層擋的。
            這個機制不能變成繞過它的後門 —— crud 匯入時也有自檢擋著。
        """
        u = make_user(seeded)
        adm = _admin(seeded)
        with pytest.raises(ValueError):
            crud.grant_profile_unlock(seeded, u, [field], adm)

    def test_the_whitelist_itself_is_clean(self):
        assert set(crud.UNLOCKABLE_FIELDS).isdisjoint(
            {"role", "is_admin", "is_active", "email", "password"})


class TestEndpoint:
    def test_only_admins_can_grant(self, client, seeded):
        u = make_user(seeded)
        make_user(seeded, username="plain", email="plain@example.com")
        r = client.post(f"/api/v1/admin/users/{u.id}/profile-unlock",
                        json={"fields": ["campus"]},
                        headers=auth_headers(client, "plain", "password123"))
        assert r.status_code == 403

    def test_admin_grants_then_user_saves_once(self, client, seeded):
        u = make_user(seeded)
        _admin(seeded, "a2")
        crud.complete_onboarding(seeded, u, ["台北"], "資訊工程學系")

        h_adm = auth_headers(client, "a2", "password123")
        r = client.post(f"/api/v1/admin/users/{u.id}/profile-unlock",
                        json={"fields": ["campus"], "reason": "轉校區"}, headers=h_adm)
        assert r.status_code == 200, r.text
        assert r.json()["used_at"] is None

        h_usr = auth_headers(client)
        ok = client.post("/api/v1/system/onboarding",
                         json={"campuses": ["桃園"]}, headers=h_usr)
        assert ok.status_code == 200, ok.text
        again = client.post("/api/v1/system/onboarding",
                            json={"campuses": ["金門"]}, headers=h_usr)
        assert again.status_code == 400
        assert "問題回報" in again.json()["detail"], "沒有告訴使用者該去哪裡申請"

    def test_grant_is_audited(self, client, seeded):
        u = make_user(seeded)
        adm = _admin(seeded, "a3")
        client.post(f"/api/v1/admin/users/{u.id}/profile-unlock",
                    json={"fields": ["campus"], "reason": "轉校區"},
                    headers=auth_headers(client, "a3", "password123"))
        row = (seeded.query(models.AdminAction)
               .filter_by(action="grant_profile_unlock").first())
        assert row is not None, "核可解鎖沒有留下稽核紀錄"
        assert row.admin_id == adm.id and row.target_user == u.id


class TestQueryEndpoint:
    def test_locked_state(self, client, seeded):
        u = make_user(seeded)
        _admin(seeded)
        r = client.get(f"/api/v1/admin/users/{u.id}/profile-unlock",
                       headers=auth_headers(client, "adm", "password123"))
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["active"] is None and d["last_used"] is None
        # ZH: 可解鎖欄位由後端給 —— 前端自己維護一份的話,加了新欄位它還是舊的。
        assert d["unlockable"] == list(crud.UNLOCKABLE_FIELDS)

    def test_shows_the_scope_not_just_open(self, client, seeded):
        """ZH: 只說「已開放」的話,管理者不知道他能改哪幾項 —— 而範圍是核可時就定好的。"""
        u = make_user(seeded)
        adm = _admin(seeded)
        crud.grant_profile_unlock(seeded, u, ["campus", "department"], adm, "轉系")
        d = client.get(f"/api/v1/admin/users/{u.id}/profile-unlock",
                       headers=auth_headers(client, "adm", "password123")).json()
        assert sorted(d["active"]["fields"]) == ["campus", "department"]
        assert d["active"]["reason"] == "轉系"
        assert d["active"]["used_at"] is None

    def test_last_used_distinguishes_never_from_just_used(self, client, seeded):
        """
        ZH: 沒有 last_used 的話,「從沒申請過」與「剛用掉」在畫面上長得一樣 ——
            都是「目前鎖定中」。管理者要判斷「他上次申請是什麼時候、改完了沒」。
        """
        u = make_user(seeded)
        adm = _admin(seeded)
        crud.complete_onboarding(seeded, u, ["台北"], "資訊工程學系")
        crud.grant_profile_unlock(seeded, u, ["campus"], adm)
        crud.complete_onboarding(seeded, u, ["桃園"], None)
        d = client.get(f"/api/v1/admin/users/{u.id}/profile-unlock",
                       headers=auth_headers(client, "adm", "password123")).json()
        assert d["active"] is None
        assert d["last_used"] is not None and d["last_used"]["used_at"] is not None

    def test_unknown_user_is_404(self, client, seeded):
        """ZH: 回 200 帶一堆 null 的話,打錯 id 看起來像「這個人沒有解鎖」。"""
        _admin(seeded)
        r = client.get("/api/v1/admin/users/nope/profile-unlock",
                       headers=auth_headers(client, "adm", "password123"))
        assert r.status_code == 404

    def test_requires_admin(self, client, seeded):
        u = make_user(seeded)
        r = client.get(f"/api/v1/admin/users/{u.id}/profile-unlock",
                       headers=auth_headers(client))
        assert r.status_code == 403


class TestRevoke:
    def test_revoke_marks_used_and_keeps_the_row(self, client, seeded):
        """
        ZH: 🔴 收回是**標成已用掉,不刪紀錄**。刪掉的話「這個人曾經被開過一次」
            就查不到了 —— 而「開過但沒用」正是稽核時想知道的事
            （例如核可之後才發現不該開）。
        """
        u = make_user(seeded)
        adm = _admin(seeded)
        crud.grant_profile_unlock(seeded, u, ["campus"], adm)
        r = client.post(f"/api/v1/admin/users/{u.id}/profile-unlock/revoke",
                        headers=auth_headers(client, "adm", "password123"))
        assert r.status_code == 200, r.text
        assert crud.active_unlock(seeded, u.id) is None
        rows = seeded.query(models.ProfileUnlock).filter_by(user_id=u.id).all()
        assert len(rows) == 1, "紀錄被刪掉了 —— 之後查不出曾經開過"
        assert rows[0].used_at is not None

    def test_revoke_is_audited(self, client, seeded):
        u = make_user(seeded)
        adm = _admin(seeded)
        crud.grant_profile_unlock(seeded, u, ["campus"], adm)
        client.post(f"/api/v1/admin/users/{u.id}/profile-unlock/revoke",
                    headers=auth_headers(client, "adm", "password123"))
        row = (seeded.query(models.AdminAction)
               .filter_by(action="revoke_profile_unlock").first())
        assert row is not None and row.target_user == u.id

    def test_revoking_nothing_is_404(self, client, seeded):
        u = make_user(seeded)
        _admin(seeded)
        r = client.post(f"/api/v1/admin/users/{u.id}/profile-unlock/revoke",
                        headers=auth_headers(client, "adm", "password123"))
        assert r.status_code == 404

    def test_a_revoked_unlock_no_longer_lets_the_user_save(self, client, seeded):
        """ZH: 陽性對照 —— 收回之後使用者那邊真的存不了了,不是只有畫面變。"""
        u = make_user(seeded)
        adm = _admin(seeded)
        crud.complete_onboarding(seeded, u, ["台北"], "資訊工程學系")
        crud.grant_profile_unlock(seeded, u, ["campus"], adm)
        client.post(f"/api/v1/admin/users/{u.id}/profile-unlock/revoke",
                    headers=auth_headers(client, "adm", "password123"))
        with pytest.raises(ValueError, match="鎖定"):
            crud.complete_onboarding(seeded, u, ["桃園"], None)


class TestUserSeesTheUnlock:
    def test_me_reports_the_unlock_scope(self, client, seeded):
        """
        ZH: 🔴 沒有這個欄位的話,管理者開了解鎖,**使用者端沒有任何地方能用它** ——
            前端只在 onboarded_at 是 null 時才顯示表單。
            v3.8 開發中實際發生過:後端做完、管理端介面做完,而使用者那邊打不開。
        """
        u = make_user(seeded)
        adm = _admin(seeded)
        crud.complete_onboarding(seeded, u, ["台北"], "資訊工程學系")
        h = auth_headers(client)
        assert client.get("/api/v1/auth/me", headers=h).json()["profile_unlock"] is None

        crud.grant_profile_unlock(seeded, u, ["campus"], adm)
        assert client.get("/api/v1/auth/me", headers=h).json()["profile_unlock"] == ["campus"]

    def test_it_clears_after_the_edit(self, client, seeded):
        u = make_user(seeded)
        adm = _admin(seeded)
        crud.complete_onboarding(seeded, u, ["台北"], "資訊工程學系")
        crud.grant_profile_unlock(seeded, u, ["campus"], adm)
        h = auth_headers(client)
        client.post("/api/v1/system/onboarding", json={"campuses": ["桃園"]}, headers=h)
        me = client.get("/api/v1/auth/me", headers=h).json()
        assert me["profile_unlock"] is None
        assert me["campuses"] == ["桃園"]
        assert me["department"] == "資訊工程學系", "核可範圍外的欄位被動到了"
