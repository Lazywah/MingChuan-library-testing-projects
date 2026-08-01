#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
==============================================================================
部署前健檢 / Pre-deploy health check — 「非 IT 看綠燈」
==============================================================================
ZH: 在 `docker compose up` 之前跑一次，把常見的無聲地雷一次檢查完，給出綠/黃/紅燈：
    1. Docker daemon 是否可用（Docker Desktop 有沒有開）
    2. 根 .env 是否存在、必填秘鑰是否夠強（非 CHANGE_ME/夠長）
    3. 設定漂移（.env.example vs compose∪Settings）與 .env 完整性
    4. gpu-worker 是否已收斂（沒有殘留的 gpu-worker/.env）
    5. 前端 ?v= 是否為最新內容 hash（呼叫 bump_assets.py --check）
    6. 主機埠（80/8888/8002/3000/8787/11434）占用狀況

    退出碼：有 FAIL → 1（別部署）；只有 WARN 或全過 → 0。

用法 / Usage:
  python scripts/deploy_check.py

需求 / Requirements: Python 3.6+，無額外套件（重用 setup_env.py 的解析函式）。
==============================================================================
"""
import socket
import subprocess
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).parent.resolve()
sys.path.insert(0, str(SCRIPTS_DIR))
import setup_env as se   # 重用：路徑、.env 解析、漂移稽核、顏色輔助（其 console 設定也一併生效）

# 必填秘鑰的最小長度（對齊 job-scheduler/app/config.py 的 validator）
SECRET_MIN_LEN = {
    "JWT_SECRET_KEY": 32,
    "WORKER_API_TOKEN": 16,
    "SECRETS_MASTER_KEY": 32,
    "WEBUI_SECRET_KEY": 16,   # config.py 未驗，但仍不該是弱值
}
_WEAK_VALUES = {
    "CHANGE_ME", "changeme", "secret", "",
    "default-insecure-secret-key",
    "dev-jwt-secret-key-change-in-production",
    "mcu-secret-token-change-in-production",
    "dev-secrets-master-key-change-in-production",
    "mcu-secret-token",
}

# 各 compose 發佈的主機埠（host:container 的 host 側）
EXPECTED_PORTS = [
    (80,    "nginx web (/train, 使用者入口)"),
    (8888,  "nginx admin (管理端)"),
    (8002,  "job-scheduler API"),
    (3000,  "open-webui"),
    (8787,  "portkey gateway"),
    (11434, "ollama"),
]

PASS, WARN, FAIL = "PASS", "WARN", "FAIL"


def port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.3)
        return s.connect_ex(("127.0.0.1", port)) == 0


def check_docker():
    import shutil
    if shutil.which("docker") is None:
        return FAIL, "Docker 未安裝或不在 PATH / docker not found"
    try:
        r = subprocess.run(["docker", "info"], capture_output=True, timeout=20)
    except Exception as e:
        return FAIL, f"無法執行 docker：{e}"
    if r.returncode == 0:
        return PASS, "Docker daemon 運作中 / running"
    return FAIL, "Docker daemon 未啟動（請先開 Docker Desktop）/ daemon not running"


def check_env_file():
    if se.SERVICE_ENV.exists():
        return PASS, f"根 .env 存在 / found: {se.SERVICE_ENV}"
    return FAIL, f"根 .env 不存在 → 先跑 python scripts/setup_env.py"


def check_secrets(env: dict):
    bad = []
    for key, min_len in SECRET_MIN_LEN.items():
        val = env.get(key, "")
        if not val:
            bad.append(f"{key}（缺失）")
        elif val in _WEAK_VALUES:
            bad.append(f"{key}（弱/預設值）")
        elif len(val) < min_len:
            bad.append(f"{key}（長度 {len(val)}<{min_len}）")
    if bad:
        return FAIL, "必填秘鑰有問題：" + "、".join(bad)
    return PASS, "必填秘鑰皆存在且強度足夠（JWT/WORKER/SECRETS/WEBUI）"


def check_inline_comments(env: dict):
    """
    ZH: 偵測「值後面黏著行內註解」的 .env 行（例：KEY=value   # 註解）。
        docker compose / pydantic 不會剝行內 #，註解會變成值的一部分（實際踩過：
        OIDC tenant 變成註解亂碼）。比對「空白+#」避免誤殺含 # 的密碼。
    EN: Detect values with a trailing inline comment (whitespace + '#') — compose
        and pydantic treat it as part of the value. Happened once in the wild.
    """
    import re as _re
    bad = [k for k, v in env.items() if _re.search(r"\s#", v)]
    if bad:
        return FAIL, ("以下 key 的值疑似黏到行內註解（compose 會把 # 後面當成值）："
                      + "、".join(bad) + " → 請把該行改成純 KEY=值")
    return PASS, ".env 值中無行內註解殘留"


def check_drift():
    order, _defaults = se.parse_env_example(se.ENV_EXAMPLE)
    if not order:
        return FAIL, "讀不到 .env.example"
    _ref, missing_from_example, _orphan, _intentional = se.audit_drift(set(order))
    if missing_from_example:
        return FAIL, "設定漂移：compose/Settings 引用但 .env.example 未宣告 → " + "、".join(sorted(missing_from_example))
    return PASS, ".env.example 與 compose∪Settings 一致（無漂移）"


def check_env_completeness(env: dict):
    order, _defaults = se.parse_env_example(se.ENV_EXAMPLE)
    missing = [k for k in order if k not in env]
    if missing:
        return WARN, (f".env 少了 {len(missing)} 個範本 key（將用程式預設；可跑 "
                      f"python scripts/setup_env.py --check 補齊）")
    return PASS, ".env 已涵蓋 .env.example 全部 key"


def check_worker_convergence():
    if se.WORKER_ENV.exists():
        return WARN, (f"偵測到已停用的 gpu-worker/.env（step 3 已收斂）→ 建議刪除："
                      f"rm {se.WORKER_ENV}")
    return PASS, "gpu-worker 設定單一來源（無殘留 gpu-worker/.env）"


def check_asset_versions():
    script = SCRIPTS_DIR / "bump_assets.py"
    if not script.exists():
        return WARN, "找不到 bump_assets.py，略過 ?v= 檢查"
    r = subprocess.run([sys.executable, str(script), "--check"], capture_output=True)
    if r.returncode == 0:
        return PASS, "前端 ?v= 皆為最新內容 hash"
    return WARN, "前端 ?v= 有過期 → 跑 python scripts/bump_assets.py 後再部署"


def check_ports():
    """回傳單一彙總（有占用列為 WARN，因可能是本平台已在跑）。"""
    in_use = [(p, label) for p, label in EXPECTED_PORTS if port_in_use(p)]
    if not in_use:
        return PASS, "主機埠 80/8888/8002/3000/8787/11434 皆空閒"
    detail = "、".join(f"{p}({label})" for p, label in in_use)
    return WARN, f"以下埠占用中（若本平台已在運行則屬正常）：{detail}"


def main():
    print()
    print(se.bold(se.cyan("== 部署前健檢 / Pre-deploy Health Check ==")))
    print(se.dim(f"   root: {se.ROOT_DIR}"))
    print()

    env = se.parse_env_file(se.SERVICE_ENV) if se.SERVICE_ENV.exists() else {}

    checks = [
        ("Docker",        check_docker()),
        ("根 .env",        check_env_file()),
        ("必填秘鑰",       check_secrets(env)),
        ("行內註解殘留",   check_inline_comments(env)),
        ("設定漂移",       check_drift()),
        (".env 完整性",    check_env_completeness(env)),
        ("gpu-worker 收斂", check_worker_convergence()),
        ("前端 ?v=",       check_asset_versions()),
        ("主機埠",         check_ports()),
    ]

    n_fail = n_warn = 0
    for name, (status, detail) in checks:
        if status == FAIL:
            n_fail += 1
            line = se.err(f"{name}")
        elif status == WARN:
            n_warn += 1
            line = se.warn(f"{name}")
        else:
            line = se.ok(f"{name}")
        print(f"  {line}")
        print(f"      {se.dim(detail)}")

    print()
    if n_fail:
        print(se.bold(se.red(f"🔴 有 {n_fail} 項未通過（另有 {n_warn} 項提醒）— 請修正後再 docker compose up")))
        return 1
    if n_warn:
        print(se.bold(se.yellow(f"🟡 可部署，但有 {n_warn} 項提醒 — 建議先看一下上面黃字")))
        return 0
    print(se.bold(se.green("🟢 全部通過 — 可以 docker compose up -d 了")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
