# -*- coding: utf-8 -*-
"""
ZH: 訓練圈數的上限（擁有者 2026-09-24 問「有限制訓練圈數嗎」時發現的）。

ZH: 🔴 在此之前**畫面擋 50、API 放到 1000** ——
    `scheduler_policy.yaml` 的 `max_epochs_per_job` 是 1000，
    而 train.html 的 `<input max="50">` 只是瀏覽器層的擋。
    直接打 `/api/v1/jobs` 就繞得過去，然後那張單會跑到撞逾時
    （120 分鐘）才被中止，中間一直佔著一張卡。

ZH: 這一族守的是**同一個數字被寫在三個地方**：
      1. `scheduler_policy.yaml` 的 max_epochs_per_job   ← 真正擋得住的那個
      2. `web-ui-V1/train.html` 的 <input id="epochs" max>
      3. `web-ui-V1/train.js` 送單前的 Math.min(...)
    三份漂開的症狀都是安靜的：不是使用者被擋得莫名其妙，
    就是後端根本沒擋。

ZH: ⚠ 這個上限只管 `config.epochs`，也就是三種內建訓練。
    自己帶 .py 的單，圈數在使用者的程式裡，這裡看不到也擋不了 ——
    那條路的保險是 job_timeout_minutes。下面有一條陰性對照守這件事。

@node tests/test_epoch_cap.py
"""
import re

import pytest

from conftest import make_user, auth_headers, repo_file


def _policy_cap():
    from app.config import SCHEDULER_POLICY
    return int(SCHEDULER_POLICY.get("scheduling", {}).get("max_epochs_per_job"))


def _html_max():
    html = repo_file("web-ui-V1", "train.html").read_text(encoding="utf-8")
    m = re.search(r'<input[^>]*id="epochs"[^>]*>', html)
    assert m, "train.html 裡找不到 id=\"epochs\" 的輸入框（改版了？）"
    mx = re.search(r'max="(\d+)"', m.group(0))
    assert mx, "那個輸入框沒有 max（瀏覽器層的擋不見了）"
    return int(mx.group(1))


def _js_clamp():
    js = repo_file("web-ui-V1", "train.js").read_text(encoding="utf-8")
    m = re.search(r"Math\.min\((\d+),\s*Math\.max\(1,\s*parseInt\(\$\('epochs'\)", js)
    assert m, "train.js 裡找不到送單前夾圈數的那一行"
    return int(m.group(1))


# ── 三個地方要同一個數字 ─────────────────────────────────────────────

def test_the_cap_is_the_same_in_all_three_places():
    """ZH: 🔴 後端才是真正擋得住的那一個，畫面那兩份是體驗。三份要一致。"""
    cap = _policy_cap()
    assert cap == _html_max(), (
        "後端上限 %d 與畫面的 max %d 不同 —— "
        "小的那個是體驗、大的那個是真的擋得住的" % (cap, _html_max()))
    assert cap == _js_clamp(), (
        "後端上限 %d 與 train.js 夾的 %d 不同" % (cap, _js_clamp()))


def test_the_cap_is_sane():
    """ZH: 上限 × 單輪時間要塞得進逾時 —— 不然使用者填得下去卻一定跑不完。

    ZH: 範例資料約「10 輪 20 分鐘」，所以 50 輪 ≈ 100 分鐘，
        而預設逾時是 120 分鐘。這條不是要釘死某個數字，
        是要擋住「有人把上限調成 500」那種改法。
    """
    from app.config import settings
    cap = _policy_cap()
    est_minutes = cap * 2          # ZH: 範例資料一輪約兩分鐘（10 輪 20 分鐘）
    assert est_minutes <= settings.JOB_TIMEOUT_MINUTES, (
        "上限 %d 輪照範例資料估要 %d 分鐘，超過逾時 %d 分鐘 —— "
        "使用者填得下去卻一定跑不完" % (cap, est_minutes, settings.JOB_TIMEOUT_MINUTES))


# ── 後端真的擋 ───────────────────────────────────────────────────────

@pytest.fixture
def headers(client, db):
    make_user(db)
    return auth_headers(client)


def _payload(epochs):
    return {"job_name": "cap test", "model_name": "test-model",
            "gpu_required": 1, "config": {"epochs": epochs}, "priority": 1}


def test_over_the_cap_is_rejected(client, db, headers):
    cap = _policy_cap()
    r = client.post("/api/v1/jobs", json=_payload(cap + 1), headers=headers)
    assert r.status_code == 400, r.text
    assert str(cap) in r.text, "錯誤訊息要講出上限是多少，否則使用者不知道改成什麼"


def test_at_the_cap_is_accepted(client, db, headers):
    """ZH: 陰性對照 —— 剛好等於上限不能被擋（差一錯誤）。"""
    r = client.post("/api/v1/jobs", json=_payload(_policy_cap()), headers=headers)
    assert r.status_code == 201, r.text


def test_own_script_is_not_capped_by_this(client, db, headers):
    """ZH: ⚠ 自己帶程式的單**不受這條限制**，而那是刻意的。

    ZH: 圈數寫在使用者的程式裡，`config.epochs` 根本不存在 ——
        這裡沒有東西可以擋。那條路的保險是 job_timeout_minutes。
        寫成測試是為了讓「以為自帶程式也被擋住」的人看得到真相。
    """
    r = client.post("/api/v1/jobs",
                    json={"job_name": "own", "model_name": "test-model",
                          "gpu_required": 1, "script_source": "print('hi')"},
                    headers=headers)
    assert r.status_code == 201, r.text
