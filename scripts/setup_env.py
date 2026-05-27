#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
==============================================================================
AI 訓練平台 — 一鍵部署初始化腳本
AI Training Platform — One-Click Deployment Initialization Script
==============================================================================
ZH: 功能：
  1. 自動以密碼學安全方式生成 JWT_SECRET_KEY / WORKER_API_TOKEN / WEBUI_SECRET_KEY
  2. 互動式引導填入 IP、路徑、Token 額度、SMTP 等可配置數值
  3. 同步寫入服務層 .env 與 gpu-worker/.env（Token 自動對齊）
  4. 備份舊版 .env（若已存在）
  5. 輸出完整設定摘要表與下一步指引

EN: Features:
  1. Cryptographically secure generation of JWT / Worker / WebUI secrets
  2. Interactive prompts for IPs, paths, quota, SMTP, etc.
  3. Write .env (service layer) + gpu-worker/.env with matching tokens
  4. Backup any existing .env before overwriting
  5. Print full configuration summary and next steps

ZH: 使用方式：
  python scripts/setup_env.py          ← 互動式（推薦，首次部署）
  python scripts/setup_env.py --show   ← 僅顯示現有 .env 設定，不寫入
  python scripts/setup_env.py --check  ← 檢查 .env 缺哪些必要 key，只追加不覆寫

EN: Usage:
  python scripts/setup_env.py          ← interactive (recommended, first deploy)
  python scripts/setup_env.py --show   ← show existing .env config without writing
  python scripts/setup_env.py --check  ← detect missing required keys, append only

ZH: 需求：Python 3.6+，無額外套件
EN: Requirements: Python 3.6+, no extra packages
==============================================================================
"""

import os
import sys
import secrets
import platform
import re
import shutil
import datetime
import getpass
from pathlib import Path

# ══════════════════════════════════════════════════════════════════════════════
# 路徑定義 / Path Definitions
# ══════════════════════════════════════════════════════════════════════════════
SCRIPT_DIR   = Path(__file__).parent.resolve()
ROOT_DIR     = SCRIPT_DIR.parent.resolve()   # CodeSpace/
SERVICE_ENV  = ROOT_DIR / ".env"
WORKER_DIR   = ROOT_DIR / "gpu-worker"
WORKER_ENV   = WORKER_DIR / ".env"

# ══════════════════════════════════════════════════════════════════════════════
# ANSI 顏色 / ANSI Colors
# ══════════════════════════════════════════════════════════════════════════════
IS_WIN  = platform.system() == "Windows"
ANSI_OK = False

if IS_WIN:
    try:
        import ctypes
        k32 = ctypes.windll.kernel32
        # ZH: 切換主控台至 UTF-8 (code page 65001)，避免中文/Emoji 出現 UnicodeEncodeError
        # EN: Switch console to UTF-8 (code page 65001) to avoid UnicodeEncodeError on CJK terminals
        k32.SetConsoleOutputCP(65001)
        k32.SetConsoleCP(65001)
        k32.SetConsoleMode(k32.GetStdHandle(-11), 7)   # enable ANSI VT processing
        ANSI_OK = True
    except Exception:
        ANSI_OK = False
    # ZH: 重新設定 stdout/stderr 編碼，Python 3.7+ 支援 | EN: Reconfigure stdout encoding (Py 3.7+)
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass  # Python < 3.7，不影響執行 / Python < 3.7, non-critical
else:
    ANSI_OK = sys.stdout.isatty()

def _c(code, text):
    return f"\033[{code}m{text}\033[0m" if ANSI_OK else text

def red(t):    return _c("31",   t)
def green(t):  return _c("32",   t)
def yellow(t): return _c("33",   t)
def cyan(t):   return _c("36",   t)
def bold(t):   return _c("1",    t)
def dim(t):    return _c("2",    t)
def ok(t):     return green("✓ ") + t
def warn(t):   return yellow("⚠ ") + t
def err(t):    return red("✗ ") + t

# ══════════════════════════════════════════════════════════════════════════════
# 輸入輔助 / Input Helpers
# ══════════════════════════════════════════════════════════════════════════════
def ask(prompt: str, default=None, validator=None, hidden=False) -> str:
    """互動式輸入，支援預設值與驗證 / Interactive input with default + validation."""
    suffix = f"  {dim('[' + str(default) + ']')}" if default is not None else ""
    while True:
        try:
            line = f"  {cyan('?')} {prompt}{suffix}: "
            raw = (getpass.getpass(line) if hidden else input(line)).strip()
        except (EOFError, KeyboardInterrupt):
            print("\n\n" + yellow("腳本已中止 / Script aborted."))
            sys.exit(0)

        value = raw if raw else (str(default) if default is not None else "")

        if not value and default is None:
            print("  " + err("此欄位為必填 / This field is required."))
            continue

        if validator and value:
            error_msg = validator(value)
            if error_msg:
                print("  " + err(error_msg))
                continue

        return value


def ask_yes_no(prompt: str, default: bool = True) -> bool:
    hint = dim("[Y/n]") if default else dim("[y/N]")
    try:
        raw = input(f"  {cyan('?')} {prompt} {hint}: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print("\n\n" + yellow("腳本已中止 / Script aborted."))
        sys.exit(0)
    if not raw:
        return default
    return raw in ("y", "yes", "1", "true")


# ══════════════════════════════════════════════════════════════════════════════
# 驗證器 / Validators
# ══════════════════════════════════════════════════════════════════════════════
# v2.1: 服務層預設 port，給 SERVICE_LAYER_URL 自動補齊用
SERVICE_PORT_DEFAULT = "8002"


def smart_url_normalize(raw: str) -> str:
    """
    ZH: 把使用者輸入的多種形式正規化為完整 URL
    EN: Normalize various URL input forms into a full URL

    支援 / Supports:
      127.0.0.1                  → http://127.0.0.1:8002
      192.168.1.50               → http://192.168.1.50:8002
      192.168.1.50:8002          → http://192.168.1.50:8002
      host.docker.internal       → http://host.docker.internal:8002
      http://server              → http://server:8002 (自動補 port)
      http://server:8002         → http://server:8002 (保留)
      https://prod.example.com   → https://prod.example.com (HTTPS 不補 port)
    """
    raw = raw.strip().rstrip("/")
    if not raw:
        return raw
    has_scheme = raw.startswith(("http://", "https://"))
    if not has_scheme:
        raw = "http://" + raw
    # 切出 scheme + body 來檢查 body 有沒有 port
    scheme, _, rest = raw.partition("://")
    # body 可能含 /path，先切出 host[:port]
    host_part = rest.split("/", 1)[0]
    if ":" not in host_part:
        # HTTPS 不主動補預設 port（一般是 443，留給瀏覽器決定）
        if scheme == "http":
            raw = raw.replace(host_part, f"{host_part}:{SERVICE_PORT_DEFAULT}", 1)
    return raw


def validate_url(v):
    """v2.1: 改為驗證 smart_url_normalize 後的結果是否合法 URL"""
    normalized = smart_url_normalize(v)
    if not normalized.startswith(("http://", "https://")):
        return "必須包含主機/IP 或以 http(s):// 開頭 / Must contain host/IP or start with http(s)://"
    # 確認 host 部分非空
    scheme, _, rest = normalized.partition("://")
    host_part = rest.split("/", 1)[0]
    if ":" in host_part:
        host_only = host_part.split(":", 1)[0]
    else:
        host_only = host_part
    if not host_only:
        return "主機名稱不可為空 / Host cannot be empty"


def validate_positive_int(v):
    try:
        if int(v) <= 0:
            return "必須為正整數 / Must be a positive integer"
    except ValueError:
        return "必須為整數 / Must be an integer"

def validate_log_level(v):
    if v.upper() not in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
        return "必須為 DEBUG / INFO / WARNING / ERROR / CRITICAL"


# ══════════════════════════════════════════════════════════════════════════════
# 工具函式 / Utility Functions
# ══════════════════════════════════════════════════════════════════════════════
def mask_secret(s: str, show: int = 10) -> str:
    """顯示前幾碼，其餘遮蔽 / Show first N chars, mask the rest."""
    if len(s) <= show + 4:
        return s
    return s[:show] + dim("…") + s[-4:]


def backup_if_exists(path: Path) -> None:
    if path.exists():
        ts  = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        bak = path.parent / (path.name + f".bak_{ts}")
        shutil.copy2(path, bak)
        print(f"  {warn('已備份舊設定 / Existing .env backed up')} → {dim(str(bak))}")


def section(title: str) -> None:
    print()
    print(bold(f"── {title} {'─' * max(0, 60 - len(title))}"))
    print()


# ══════════════════════════════════════════════════════════════════════════════
# 密鑰生成 / Secret Generation
# ══════════════════════════════════════════════════════════════════════════════
# v2.1: REQUIRED_KEYS 同時供首次生成、--check migration、--show 列表使用。
# 每筆 = (產生器, 中英文用途說明)。修改此表時，service_content 範本也要同步更新。
REQUIRED_KEYS = {
    "JWT_SECRET_KEY":     (lambda: secrets.token_hex(64),     "512-bit JWT 簽章 / signing key"),
    "WORKER_API_TOKEN":   (lambda: secrets.token_hex(32),     "256-bit Worker 認證 / worker auth"),
    "WEBUI_SECRET_KEY":   (lambda: secrets.token_hex(32),     "256-bit Open WebUI session"),
    # v2.0 Lab 模組 AES-256-GCM 加密主金鑰（必須 ≥ 32 字元）
    "SECRETS_MASTER_KEY": (lambda: secrets.token_urlsafe(48), "v2.0 Lab AES-256-GCM KEK"),
}


def generate_secrets() -> dict:
    """產生全部必要 secrets (首次部署用) / Generate all required secrets (first deploy)"""
    return {key: gen() for key, (gen, _desc) in REQUIRED_KEYS.items()}


def parse_env_file(path: Path) -> dict:
    """讀取 .env 為 dict（用於 --check 與 migrate 邏輯）/ Parse .env into dict"""
    if not path.exists():
        return {}
    result = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip()
            if not line or line.startswith("#"):
                continue
            key, _, val = line.partition("=")
            key, val = key.strip(), val.strip()
            if key:
                result[key] = val
    return result


# ══════════════════════════════════════════════════════════════════════════════
# --check 模式：補齊 .env 缺漏 key / Migration: patch missing required keys
# ══════════════════════════════════════════════════════════════════════════════
def check_and_patch(path: Path) -> int:
    """
    ZH: 檢測 .env 缺少哪些必要 key，只追加不覆寫既有值。
    EN: Detect missing required keys and append only — never overwrite existing.

    Returns:
        缺失欄位數 / number of missing fields patched
    """
    section(f"檢查 .env / Checking {path.name}")
    if not path.exists():
        print(f"  {err('.env 不存在 / .env not found：' + str(path))}")
        print(f"  {dim('請先用互動模式建立 / Run setup_env.py without --check first')}")
        return -1

    existing = parse_env_file(path)
    print(f"  {dim(f'已存在欄位 / Existing keys: {len(existing)}')}")

    missing = []
    for key, (gen, desc) in REQUIRED_KEYS.items():
        if not existing.get(key):
            missing.append((key, gen(), desc))
            print(f"  {err('缺失 / Missing')}  {cyan(key.ljust(20))}  {dim(desc)}")
        else:
            print(f"  {ok('存在 / OK     ')}  {cyan(key.ljust(20))}  {dim(mask_secret(existing[key]))}")

    if not missing:
        print()
        print(f"  {bold(green('✅ 所有必要 key 都存在 / All required keys present'))}")
        return 0

    print()
    print(f"  {warn(f'共 {len(missing)} 個欄位缺失，準備追加 / Patching {len(missing)} missing fields')}")
    if not ask_yes_no("確認追加？/ Confirm append?", default=True):
        print(f"  {dim('已取消 / Cancelled')}")
        return -1

    backup_if_exists(path)
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(path, "a", encoding="utf-8") as f:
        f.write(f"\n# ── Migrated by setup_env.py --check at {now_str} ──\n")
        for key, val, desc in missing:
            f.write(f"# {desc}\n{key}={val}\n")
    print(f"  {ok(f'已補齊 {len(missing)} 個欄位 / Patched {len(missing)} fields → ' + str(path))}")
    return len(missing)


# ══════════════════════════════════════════════════════════════════════════════
# 顯示現有設定 / Show Existing Config
# ══════════════════════════════════════════════════════════════════════════════
def show_existing() -> None:
    section("現有設定 / Existing Configuration")
    for label, path in [("Service layer", SERVICE_ENV), ("GPU Worker", WORKER_ENV)]:
        print(f"  {bold(label)}: {dim(str(path))}")
        if not path.exists():
            print(f"    {warn('檔案不存在 / File not found')}")
            continue
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.rstrip()
                if not line or line.startswith("#"):
                    continue
                key, _, val = line.partition("=")
                key = key.strip()
                val = val.strip()
                if any(s in key.upper() for s in ("KEY", "TOKEN", "PASSWORD", "SECRET")):
                    val = mask_secret(val) if val else dim("(未設定/not set)")
                print(f"    {cyan(key.ljust(35))} = {bold(val)}")
        print()


# ══════════════════════════════════════════════════════════════════════════════
# 主流程 / Main Setup
# ══════════════════════════════════════════════════════════════════════════════
def main() -> None:
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # ── Banner ────────────────────────────────────────────────────────────────
    print()
    print(bold(cyan("╔══════════════════════════════════════════════════════════════════╗")))
    print(bold(cyan("║   AI 訓練平台 一鍵部署初始化 / One-Click Deployment Init          ║")))
    print(bold(cyan("╚══════════════════════════════════════════════════════════════════╝")))
    print()
    print(f"  工作目錄 / Root dir : {dim(str(ROOT_DIR))}")
    print(f"  作業系統 / OS       : {dim(platform.system())} {dim(platform.release())}")
    print(f"  Python   / Version  : {dim(sys.version.split()[0])}")
    print()

    # ── --show 模式 ───────────────────────────────────────────────────────────
    if "--show" in sys.argv:
        show_existing()
        return

    # ── --check 模式：偵測 .env 缺漏 key，只追加不覆寫 ─────────────────────────
    if "--check" in sys.argv:
        rc1 = check_and_patch(SERVICE_ENV)
        rc2 = check_and_patch(WORKER_ENV) if WORKER_ENV.exists() else 0
        print()
        if rc1 < 0 or rc2 < 0:
            print(f"  {warn('部分檢查未完成 / Some checks not completed')}")
            sys.exit(1)
        if rc1 == 0 and rc2 == 0:
            print(f"  {bold(green('✅ 一切就緒 / Everything in order — 可以 docker compose up -d 了'))}")
        else:
            print(f"  {bold(yellow('⚠ 已補齊缺漏，請重新啟動容器 / Patched — restart containers:'))}")
            print(f"     {cyan('docker compose down && docker compose up -d')}")
        return

    # ── 平台提示 / Platform note ──────────────────────────────────────────────
    if IS_WIN:
        print(yellow("  ⚠  Windows 環境偵測到 / Windows detected"))
        print(yellow("     GPU Worker 需要 Docker Desktop + WSL2 後端才能使用 NVIDIA GPU"))
        print(yellow("     GPU Worker requires Docker Desktop + WSL2 backend for NVIDIA GPU"))
        print()

    # ══════════════════════════════════════════════════════════════════════════
    # 步驟 1：自動生成密鑰
    # ══════════════════════════════════════════════════════════════════════════
    section("步驟 1 / Step 1：自動生成安全密鑰 Auto-generate Secrets")

    gen = generate_secrets()
    print(f"  {ok('JWT_SECRET_KEY   已生成 512-bit / generated')}")
    print(f"  {ok('WORKER_API_TOKEN 已生成 256-bit / generated')}")
    print(f"  {ok('WEBUI_SECRET_KEY 已生成 256-bit / generated')}")

    # ══════════════════════════════════════════════════════════════════════════
    # 步驟 2：服務層基本設定
    # ══════════════════════════════════════════════════════════════════════════
    section("步驟 2 / Step 2：服務層設定 Service Layer Configuration")

    cors = ask(
        "CORS_ORIGINS  留空=允許所有 / empty=allow all  (逗號分隔 comma-sep)",
        default=""
    )
    token_limit = ask(
        "DEFAULT_MONTHLY_TOKEN_LIMIT  每用戶月 Token 配額 / per-user monthly token quota",
        default="5000000",
        validator=validate_positive_int
    )
    jwt_expire = ask(
        "ACCESS_TOKEN_EXPIRE_MINUTES  JWT 有效期(分) / JWT expiry minutes",
        default="120",
        validator=validate_positive_int
    )
    job_timeout = ask(
        "JOB_TIMEOUT_MINUTES  任務超時(分) / Job timeout minutes",
        default="120",
        validator=validate_positive_int
    )
    log_level = ask(
        "LOG_LEVEL  (DEBUG / INFO / WARNING / ERROR)",
        default="INFO",
        validator=validate_log_level
    )

    # ══════════════════════════════════════════════════════════════════════════
    # 步驟 3：SMTP（可選）
    # ══════════════════════════════════════════════════════════════════════════
    section("步驟 3 / Step 3：SMTP 郵件設定（選填）SMTP Email Config (Optional)")

    print(f"  {dim('設定後，forgot_password 不再於 API 回應中回傳明文密碼')}")
    print(f"  {dim('Once set, forgot_password will not return temp_password in API responses')}")
    print()

    setup_smtp = ask_yes_no("現在設定 SMTP？/ Configure SMTP now?", default=False)
    smtp: dict = {}
    if setup_smtp:
        smtp["SMTP_SERVER"]     = ask("SMTP_SERVER   (例 / e.g.: smtp.gmail.com)", default="smtp.gmail.com")
        smtp["SMTP_PORT"]       = ask("SMTP_PORT", default="587", validator=validate_positive_int)
        smtp["SMTP_USERNAME"]   = ask("SMTP_USERNAME  (Email 帳號 / account)")
        smtp["SMTP_PASSWORD"]   = ask("SMTP_PASSWORD  (App Password)", hidden=True)
        smtp["SMTP_FROM_EMAIL"] = ask("SMTP_FROM_EMAIL", default=smtp.get("SMTP_USERNAME", "noreply@ai-platform.local"))
        print(f"  {ok('SMTP 設定完成 / SMTP configured')}")
    else:
        smtp = {
            "SMTP_SERVER": "",    "SMTP_PORT": "587",
            "SMTP_USERNAME": "",  "SMTP_PASSWORD": "",
            "SMTP_FROM_EMAIL": "noreply@ai-platform.local"
        }
        print(f"  {warn('SMTP 跳過 / Skipped — temp_password 仍會出現在 API 回應中')}")

    # ══════════════════════════════════════════════════════════════════════════
    # 步驟 4：GPU Worker 設定
    # ══════════════════════════════════════════════════════════════════════════
    section("步驟 4 / Step 4：GPU Worker 設定 GPU Worker Configuration")

    has_worker_dir = WORKER_DIR.exists()
    if not has_worker_dir:
        print(f"  {warn('gpu-worker/ 目錄不存在，跳過 / Directory not found, skipping')}")

    setup_worker = has_worker_dir and ask_yes_no(
        "現在設定 GPU Worker .env？/ Configure GPU Worker .env now?",
        default=True
    )
    worker: dict = {}
    if setup_worker:
        # v2.1: 部署模式前置題 — 自動帶入合適的 SERVICE_LAYER_URL 預設值
        print()
        print(f"  {bold('部署模式 / Deployment Mode')}")
        print(f"     {cyan('[1]')} 單機完全體 All-in-one（服務層 + GPU Worker 都在這台）")
        print(f"     {cyan('[2]')} 分機 Multi-host（GPU Worker 與服務層在不同電腦）")
        mode = ask("選擇 / Choose", default="1", validator=lambda v: None if v in ("1", "2") else "請輸入 1 或 2")

        if mode == "1":
            # 單機：用 Docker Desktop 的 host.docker.internal（Win/Mac）或 172.17.0.1（Linux）
            default_url = "http://host.docker.internal:8002" if IS_WIN else "http://172.17.0.1:8002"
            print(f"  {dim('單機模式：worker 容器透過 ' + default_url.split('//')[1].split(':')[0] + ' 找到主機上的 scheduler')}")
        else:
            default_url = "http://192.168.1.50:8002"
            print(f"  {dim('分機模式：請填入服務層那台的區網 IP（先在那台跑 ipconfig / ip a 查）')}")

        print(f"  {dim('輸入格式都可：純 IP / 主機名 / 完整 URL — 沒寫 port 會自動補 :' + SERVICE_PORT_DEFAULT)}")
        print(f"  {dim('Accepts: bare IP, hostname, or full URL — port :' + SERVICE_PORT_DEFAULT + ' auto-appended')}")
        raw_url = ask(
            "SERVICE_LAYER_URL  服務層位址 / Service layer address",
            default=default_url,
            validator=validate_url,
        )
        worker["SERVICE_LAYER_URL"] = smart_url_normalize(raw_url)
        if worker["SERVICE_LAYER_URL"] != raw_url:
            print(f"  {dim('  → 已正規化為 / normalized to: ' + worker['SERVICE_LAYER_URL'])}")

        worker["NODE_ID"] = ask(
            "NODE_ID  此 Worker 在儀表板的名稱 / Worker name shown in dashboard",
            default="gpu-node-01"
        )
        worker["POLL_INTERVAL"] = ask(
            "POLL_INTERVAL  領取任務輪詢間隔（秒）/ Job poll interval seconds",
            default="5",
            validator=validate_positive_int
        )
        worker["HEARTBEAT_INTERVAL"] = ask(
            "HEARTBEAT_INTERVAL  心跳上報間隔（秒）/ Heartbeat interval seconds",
            default="30",
            validator=validate_positive_int
        )

        default_storage = "C:\\storage" if IS_WIN else "/mnt/storage"
        storage_hint = (
            "Windows 路徑，Docker Desktop 可直接掛載 / Windows path, Docker Desktop handles mount"
            if IS_WIN else
            "Linux 路徑，必須先掛載 SMB / Linux path — SMB must be mounted first"
        )
        print(f"  {dim(storage_hint)}")
        worker["STORAGE_MOUNT_PATH"] = ask(
            "STORAGE_MOUNT_PATH  共享儲存掛載路徑 / Shared storage path",
            default=default_storage
        )

    # ══════════════════════════════════════════════════════════════════════════
    # 寫入設定檔 / Write Config Files
    # ══════════════════════════════════════════════════════════════════════════
    section("寫入設定檔 / Writing Config Files")

    # ── Service Layer .env ────────────────────────────────────────────────────
    backup_if_exists(SERVICE_ENV)

    smtp_block = f"""# ── SMTP 郵件 / SMTP Email ─────────────────────────────────────────────────
SMTP_SERVER={smtp['SMTP_SERVER']}
SMTP_PORT={smtp['SMTP_PORT']}
SMTP_USERNAME={smtp['SMTP_USERNAME']}
SMTP_PASSWORD={smtp['SMTP_PASSWORD']}
SMTP_FROM_EMAIL={smtp['SMTP_FROM_EMAIL']}
"""

    service_content = f"""# ==============================================================================
# ZH: AI 訓練平台 — 環境變數
# EN: AI Training Platform — Environment Variables
#
# ZH: 由 scripts/setup_env.py 自動生成於 {now_str}
# EN: Auto-generated by scripts/setup_env.py at {now_str}
#
# ⚠  請勿將此檔案提交至版本控制！/ Do NOT commit this file to version control!
#    .gitignore 已設定排除 .env / .gitignore already excludes .env
# ==============================================================================

# ── 密鑰（自動生成，請勿手動修改）/ Secrets (auto-generated, do not edit manually)
JWT_SECRET_KEY={gen['JWT_SECRET_KEY']}
WORKER_API_TOKEN={gen['WORKER_API_TOKEN']}
WEBUI_SECRET_KEY={gen['WEBUI_SECRET_KEY']}
# v2.0 Lab AES-256-GCM 加密主金鑰（變更會讓既有 secrets 全部失效）
# v2.0 Lab AES-256-GCM master key (changing this invalidates all existing secrets)
SECRETS_MASTER_KEY={gen['SECRETS_MASTER_KEY']}

# ── JWT 設定 / JWT Configuration
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES={jwt_expire}

# ── 資料庫 / Database
DATABASE_PATH=/data/ai_platform.db

# ── Token 額度 / Token Quota
DEFAULT_MONTHLY_TOKEN_LIMIT={token_limit}
TOKEN_RESET_DAY=1

# ── Portkey LLM Gateway
PORTKEY_URL=http://ai-platform-portkey:8000/v1/chat/completions
PORTKEY_ENABLED=true

# ── 任務超時 / Job Timeout
JOB_TIMEOUT_MINUTES={job_timeout}

# ── CORS（正式環境填入，開發環境留空=允許所有）
# ── CORS origins (fill in for production; empty = allow all in dev)
CORS_ORIGINS={cors}

# ── 日誌 / Logging
LOG_LEVEL={log_level}

{smtp_block}"""

    SERVICE_ENV.write_text(service_content, encoding="utf-8")
    print(f"  {ok('服務層 / Service layer .env')} → {bold(str(SERVICE_ENV))}")

    # ── GPU Worker .env ───────────────────────────────────────────────────────
    if setup_worker:
        backup_if_exists(WORKER_ENV)

        worker_content = f"""# ==============================================================================
# ZH: GPU Worker — 環境變數
# EN: GPU Worker — Environment Variables
#
# ZH: 由 scripts/setup_env.py 自動生成於 {now_str}
# EN: Auto-generated by scripts/setup_env.py at {now_str}
#
# ⚠  請勿將此檔案提交至版本控制！/ Do NOT commit this file to version control!
# ==============================================================================

# ── 服務層連線（換主機唯一必改項）/ Service layer URL (only change when redeploying)
SERVICE_LAYER_URL={worker['SERVICE_LAYER_URL']}

# ── 安全憑證（自動與服務層對齊，請勿手動修改）
# ── Must match WORKER_API_TOKEN in service layer .env — auto-synced, do not edit
API_TOKEN={gen['WORKER_API_TOKEN']}

# ── 節點識別 / Node Identity
NODE_ID={worker['NODE_ID']}

# ── 輪詢設定 / Polling Configuration
POLL_INTERVAL={worker['POLL_INTERVAL']}
HEARTBEAT_INTERVAL={worker['HEARTBEAT_INTERVAL']}

# ── 儲存掛載 / Storage Mount
# ▶ Windows 宿主：保留 Windows 路徑，Docker Desktop 可直接掛載
# ▶ Linux  宿主：必須使用 Linux 絕對路徑，並先以 mount -t cifs 掛載 SMB
STORAGE_MOUNT_PATH={worker['STORAGE_MOUNT_PATH']}
"""
        WORKER_ENV.write_text(worker_content, encoding="utf-8")
        print(f"  {ok('GPU Worker .env')} → {bold(str(WORKER_ENV))}")

    # ══════════════════════════════════════════════════════════════════════════
    # 設定摘要表 / Configuration Summary Table
    # ══════════════════════════════════════════════════════════════════════════
    section("設定摘要 / Configuration Summary")

    rows = [
        # (key, value, note)
        ("JWT_SECRET_KEY",            mask_secret(gen['JWT_SECRET_KEY'], 12),
                                      "512-bit · 自動生成 / auto-gen"),
        ("WORKER_API_TOKEN",          mask_secret(gen['WORKER_API_TOKEN'], 12),
                                      "256-bit · 服務層+Worker 已對齊 / synced"),
        ("WEBUI_SECRET_KEY",          mask_secret(gen['WEBUI_SECRET_KEY'], 12),
                                      "256-bit · 自動生成 / auto-gen"),
        ("SECRETS_MASTER_KEY",        mask_secret(gen['SECRETS_MASTER_KEY'], 12),
                                      "v2.0 Lab AES-256-GCM KEK · 自動生成 / auto-gen"),
        ("ACCESS_TOKEN_EXPIRE",       f"{jwt_expire} 分鐘 / min",
                                      "JWT 有效期 / expiry"),
        ("DEFAULT_TOKEN_LIMIT",       f"{int(token_limit):,} tokens",
                                      "每用戶月配額 / per-user / month"),
        ("JOB_TIMEOUT",               f"{job_timeout} 分鐘 / min",
                                      "任務超時閾值 / job timeout"),
        ("CORS_ORIGINS",              cors if cors else "(空=允許所有 / empty=allow all)",
                                      "正式環境請填寫 / fill in for prod"),
        ("LOG_LEVEL",                 log_level,
                                      ""),
        ("SMTP",                      "已設定 / configured" if smtp.get("SMTP_SERVER") else "未設定 / not set",
                                      "" if smtp.get("SMTP_SERVER") else "⚠ temp_password 將明文回傳"),
    ]

    if setup_worker:
        rows += [
            ("SERVICE_LAYER_URL",     worker['SERVICE_LAYER_URL'],
                                      "GPU Worker 連線目標 / worker target"),
            ("NODE_ID",               worker['NODE_ID'],
                                      "叢集儀表板顯示名 / cluster dashboard name"),
            ("STORAGE_MOUNT_PATH",    worker['STORAGE_MOUNT_PATH'],
                                      "訓練容器掛載路徑 / training container mount"),
        ]

    # 計算欄寬
    c0 = max(len(r[0]) for r in rows) + 2
    c1 = max(len(r[1]) for r in rows) + 2
    c2 = max(len(r[2]) for r in rows) + 2

    def trow(k, v, n):
        # Strip ANSI for length calculation
        ansi_strip = re.compile(r'\x1b\[[0-9;]*m')
        vlen = len(ansi_strip.sub("", v))
        nlen = len(ansi_strip.sub("", n))
        return (f"  │  {cyan(k.ljust(c0))}│  {bold(v)}{' ' * (c1 - vlen)}│  "
                f"{dim(n)}{' ' * max(0, c2 - nlen)}│")

    border = lambda l, m, r: (
        f"  {l}" + ("─" * (c0 + 3)) + m + ("─" * (c1 + 3)) + m + ("─" * (c2 + 2)) + r
    )

    print(border("┌", "┬", "┐"))
    print(trow("變數名稱 / Key", "值 / Value", "說明 / Note"))
    print(border("├", "┼", "┤"))
    for k, v, n in rows:
        print(trow(k, v, n))
    print(border("└", "┴", "┘"))

    # ══════════════════════════════════════════════════════════════════════════
    # 安全提醒 / Security Reminders
    # ══════════════════════════════════════════════════════════════════════════
    section("安全提醒 / Security Reminders")

    reminders = [
        (True,  ".env 已在 .gitignore 中排除，請確認不會意外提交"),
        (True,  ".env is excluded in .gitignore — verify no accidental commits"),
        (not bool(cors),
                "⚠ CORS_ORIGINS 未設定，正式上線前請填入真實域名/IP"),
        (not bool(cors),
                "⚠ CORS_ORIGINS is empty — set real domain/IP before going live"),
        (not smtp.get("SMTP_SERVER"),
                "⚠ SMTP 未設定：forgot_password 仍會在 API 回應中回傳明文臨時密碼"),
        (not smtp.get("SMTP_SERVER"),
                "⚠ SMTP not set: temp_password will appear in API responses"),
        (True,  "建議定期輪換 JWT_SECRET_KEY（輪換後所有已登入使用者需重新登入）"),
        (True,  "Rotate JWT_SECRET_KEY periodically (all users must re-login after rotation)"),
    ]

    for show, msg in reminders:
        if show:
            color = yellow if msg.startswith("⚠") else dim
            print(f"  {color(msg)}")

    # ══════════════════════════════════════════════════════════════════════════
    # 下一步 / Next Steps
    # ══════════════════════════════════════════════════════════════════════════
    section("下一步 / Next Steps")

    if IS_WIN:
        print(f"  {bold('① 啟動服務層 / Start service layer')}")
        print(f"     {cyan('docker compose up -d --build')}")
        print()
        print(f"  {bold('② 確認健康 / Health check')}")
        print(f"     {cyan('curl http://localhost:8002/health')}")
        print()
        if setup_worker:
            print(f"  {bold('③ 啟動 GPU Worker（需 Docker Desktop + WSL2 + NVIDIA Driver）')}")
            print(f"     {cyan('cd gpu-worker')}")
            print(f"     {cyan('docker compose up -d')}")
            print(f"     {cyan('docker logs -f mcu-gpu-worker')}")
            print()
    else:
        print(f"  {bold('① 安裝 NVIDIA Container Toolkit（首次部署）/ Install nvidia-container-toolkit (first deploy)')}")
        print(f"     {cyan('sudo apt-get install -y nvidia-container-toolkit')}")
        print(f"     {cyan('sudo nvidia-ctk runtime configure --runtime=docker')}")
        print(f"     {cyan('sudo systemctl restart docker')}")
        print()
        print(f"  {bold('② 啟動服務層 / Start service layer')}")
        print(f"     {cyan('docker compose up -d --build')}")
        print()
        print(f"  {bold('③ 確認健康 / Health check')}")
        print(f"     {cyan('curl http://localhost:8002/health')}")
        print()
        if setup_worker:
            print(f"  {bold('④ 啟動 GPU Worker / Start GPU Worker')}")
            print(f"     {cyan('cd gpu-worker && docker compose up -d')}")
            print(f"     {cyan('docker logs -f mcu-gpu-worker')}")
            print()

    print(f"  {bold('API 文件 / API Docs')}  → {cyan('http://localhost:8002/docs')}")
    print(f"  {bold('Web UI')}              → {cyan('http://localhost:80')}")
    print(f"  {bold('Admin UI')}            → {cyan('http://localhost:8888')}")
    print()
    print(bold(green("  ✅ 初始化完成！/ Initialization complete!")))
    print()


if __name__ == "__main__":
    main()
