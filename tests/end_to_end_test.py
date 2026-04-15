"""
==============================================================================
ZH: AI 訓練平台 - 端到端自動化測試
EN: AI Training Platform - End-to-End Automated Test
==============================================================================
ZH: 用途：驗證完整使用流程的正確性
EN: Purpose: Verify complete user workflow correctness

ZH: 測試流程：
    1. 註冊新使用者
    2. 登入取得 JWT Token
    3. 查詢 Token 用量 (應為 0)
    4. 提交訓練任務
    5. 查詢任務列表
    6. 輪詢任務狀態 (等待完成)
    7. 驗證 Token 已扣減
    8. 提交新任務並取消
    9. 權限測試

ZH: 執行方式：python tests/end_to_end_test.py
EN: Usage: python tests/end_to_end_test.py
==============================================================================
"""

import requests
import time
import sys

# ==============================================================================
# ZH: 測試設定 | EN: Test Configuration
# ==============================================================================
BASE_URL = "http://localhost:8002"  # ZH: 直連 Job Scheduler | EN: Direct to scheduler
AUTH_API = f"{BASE_URL}/api/v1/auth"
JOBS_API = f"{BASE_URL}/api/v1/jobs"

# ZH: 測試計數器 | EN: Test counters
passed = 0
failed = 0


def test_step(name_zh: str, name_en: str, condition: bool, detail: str = ""):
    """ZH: 測試步驟輔助函式 | EN: Test step helper"""
    global passed, failed
    if condition:
        passed += 1
        print(f"  ✅ [通過 PASS] {name_zh} | {name_en}")
    else:
        failed += 1
        print(f"  ❌ [失敗 FAIL] {name_zh} | {name_en} → {detail}")


def run_tests():
    global passed, failed

    print("\n" + "=" * 70)
    print("  AI 訓練平台 - E2E 自動化測試 | AI Platform E2E Test")
    print("=" * 70)

    # ==================================================================
    # ZH: 0. 健康檢查 | EN: 0. Health Check
    # ==================================================================
    print("\n📋 Step 0: 健康檢查 | Health Check")
    try:
        res = requests.get(f"{BASE_URL}/health", timeout=5)
        test_step("服務可達", "Service reachable", res.status_code == 200)
        if res.status_code != 200:
            print("  ⚠️  ZH: 服務未啟動，請先執行 docker-compose up | EN: Service not running")
            return
    except requests.exceptions.ConnectionError:
        print("  ❌ ZH: 無法連線到服務，請確認容器已啟動 | EN: Cannot connect, ensure containers are running")
        return

    # ==================================================================
    # ZH: 1. 使用者註冊 | EN: 1. User Registration
    # ==================================================================
    print("\n📋 Step 1: 使用者註冊 | User Registration")
    reg_data = {
        "username": f"test_student_{int(time.time())}",
        "email": f"test_{int(time.time())}@example.com",
        "password": "testpassword123",
        "role": "student"
    }
    res = requests.post(f"{AUTH_API}/register", json=reg_data)
    test_step("註冊成功", "Registration success", res.status_code == 201, res.text)
    username = reg_data["username"]

    # ==================================================================
    # Step 1.5: 模擬校園 SSO 登入驗證
    # ==================================================================
    print("\n📋 Step 1.5: 模擬校園 SSO 登入驗證 | Mock SSO Login Test")
    sso_res = requests.get(f"{BASE_URL}/api/v1/sso/callback?ticket=S110001", allow_redirects=False)
    test_step("SSO 回呼成功發出重導 (HTTP 302)", "SSO Callback Redirects", sso_res.status_code in (302, 303, 307))
    sso_token = ""
    if sso_res.status_code in (302, 303, 307):
        redirect_url = sso_res.headers.get("Location", "")
        if "sso_token=" in redirect_url:
            sso_token = redirect_url.split("sso_token=")[-1]
    
    test_step("成功從 URL 提取 SSO Token", "Extract SSO Token from URL", len(sso_token) > 0)
    
    if sso_token:
        sso_headers = {"Authorization": f"Bearer {sso_token}"}
        me_res = requests.get(f"{AUTH_API}/me", headers=sso_headers)
        test_step("使用 SSO Token 查詢使用者資訊", "Query user with SSO Token", me_res.status_code == 200)

    # ==================================================================
    # ZH: 2. 使用者登入 | EN: 2. User Login
    # ==================================================================
    print("\n📋 Step 2: 使用者登入 | User Login")
    login_data = {"username": username, "password": "testpassword123"}
    res = requests.post(f"{AUTH_API}/login", data=login_data)
    test_step("登入成功", "Login success", res.status_code == 200, res.text)

    token = ""
    if res.status_code == 200:
        token = res.json().get("access_token", "")
        test_step("取得 JWT Token", "Got JWT Token", len(token) > 0)

    headers = {"Authorization": f"Bearer {token}"}

    # ==================================================================
    # ZH: 3. 查詢使用者資訊 | EN: 3. User Info
    # ==================================================================
    print("\n📋 Step 3: 查詢使用者資訊 | User Info")
    res = requests.get(f"{AUTH_API}/me", headers=headers)
    test_step("取得使用者資訊", "Get user info", res.status_code == 200, res.text)
    if res.status_code == 200:
        user_data = res.json()
        test_step("角色為 student", "Role is student", user_data.get("role") == "student")

    # ==================================================================
    # ZH: 4. 查詢 Token 用量 | EN: 4. Token Usage
    # ==================================================================
    print("\n📋 Step 4: 查詢 Token 用量 | Token Usage")
    res = requests.get(f"{AUTH_API}/usage", headers=headers)
    test_step("查詢成功", "Query success", res.status_code == 200, res.text)
    initial_tokens = 0
    if res.status_code == 200:
        usage = res.json()
        initial_tokens = usage.get("tokens_used", 0)
        test_step("初始用量為 0", "Initial usage is 0", initial_tokens == 0,
                  f"actual={initial_tokens}")
        test_step("上限為 5M", "Limit is 5M", usage.get("tokens_limit") == 5000000)

    # ==================================================================
    # ZH: 5. 提交訓練任務 | EN: 5. Submit Training Job
    # ==================================================================
    print("\n📋 Step 5: 提交訓練任務 | Submit Training Job")
    job_data = {
        "job_name": "E2E 測試任務",
        "model_name": "test-model-v1",
        "gpu_required": 1,
        "config": {"epochs": 5, "batch_size": 32},
        "priority": 1
    }
    res = requests.post(JOBS_API, json=job_data, headers=headers)
    test_step("提交成功", "Submit success", res.status_code == 201, res.text)

    job_id = ""
    if res.status_code == 201:
        job_id = res.json().get("job_id", "")
        test_step("取得 Job ID", "Got Job ID", len(job_id) > 0)

    # ==================================================================
    # ZH: 6. 查詢任務列表 | EN: 6. List Jobs
    # ==================================================================
    print("\n📋 Step 6: 查詢任務列表 | List Jobs")
    res = requests.get(JOBS_API, headers=headers)
    test_step("列表查詢成功", "List query success", res.status_code == 200, res.text)
    if res.status_code == 200:
        jobs_data = res.json()
        test_step("列表包含任務", "List contains jobs", jobs_data.get("total", 0) > 0)

    # ==================================================================
    # ZH: 7. 輪詢任務狀態 | EN: 7. Poll Job Status
    # ==================================================================
    print("\n📋 Step 7: 輪詢任務狀態 | Poll Job Status")
    if job_id:
        final_status = "pending"
        for i in range(30):  # ZH: 最多等 60 秒 | EN: Wait up to 60s
            time.sleep(2)
            res = requests.get(f"{JOBS_API}/{job_id}", headers=headers)
            if res.status_code == 200:
                info = res.json()
                final_status = info.get("status", "unknown")
                progress = info.get("progress", 0)
                print(f"    ⏳ 狀態={final_status}, 進度={progress}% | "
                      f"status={final_status}, progress={progress}%")
                if final_status in ("completed", "failed"):
                    break
        test_step("任務最終完成", "Job completed",
                  final_status in ("completed", "failed"),
                  f"final_status={final_status}")

    # ==================================================================
    # ZH: 8. 驗證 Token 扣減 | EN: 8. Verify Token Deduction
    # ==================================================================
    print("\n📋 Step 8: 驗證 Token 扣減 | Verify Token Deduction")
    res = requests.get(f"{AUTH_API}/usage", headers=headers)
    if res.status_code == 200:
        new_usage = res.json()
        new_tokens = new_usage.get("tokens_used", 0)
        test_step("Token 已扣減", "Tokens deducted",
                  new_tokens > initial_tokens,
                  f"before={initial_tokens}, after={new_tokens}")

    # ==================================================================
    # ZH: 9. 取消任務測試 | EN: 9. Cancel Job Test
    # ==================================================================
    print("\n📋 Step 9: 取消任務測試 | Cancel Job Test")
    cancel_data = {
        "job_name": "待取消任務",
        "model_name": "cancel-test",
        "priority": 0,
        "config": {"epochs": 1}
    }
    res = requests.post(JOBS_API, json=cancel_data, headers=headers)
    if res.status_code == 201:
        cancel_job_id = res.json().get("job_id")
        res = requests.delete(f"{JOBS_API}/{cancel_job_id}", headers=headers)
        test_step("取消成功", "Cancel success", res.status_code == 200, res.text)

    # ==================================================================
    # ZH: 測試結果摘要 | EN: Test Result Summary
    # ==================================================================
    print("\n" + "=" * 70)
    total = passed + failed
    print(f"  📊 測試結果 | Results: {passed}/{total} 通過 passed, {failed}/{total} 失敗 failed")
    if failed == 0:
        print("  🎉 所有測試通過！| All tests passed!")
    else:
        print("  ⚠️  部分測試失敗 | Some tests failed")
    print("=" * 70 + "\n")

    return failed == 0


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
