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

# v3.1 step 2: .env.example 為單一真相；setup_env 從它衍生題目與寫檔範本。
ENV_EXAMPLE  = ROOT_DIR / ".env.example"
# 漂移偵測來源：compose 的 ${VAR} ∪ pydantic Settings 欄位
COMPOSE_FILES = [
    ROOT_DIR / "docker-compose.yml",
    ROOT_DIR / "docker-compose.ai-models.yml",
    WORKER_DIR / "docker-compose.yml",
]
CONFIG_PY = ROOT_DIR / "job-scheduler" / "app" / "config.py"

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
# v3.1 step 2：.env.example 單一真相 — 解析、漂移稽核、範本渲染
# v3.1 step 2: .env.example single source — parse, drift audit, template render
# ══════════════════════════════════════════════════════════════════════════════
_KEY_LINE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$")


def parse_env_example(path: Path):
    """
    ZH: 解析 .env.example，回傳「有效 key（未被註解）」的順序與預設值。
        被 # 註解掉的行（含『已停用』區）不算有效 key。
    EN: Parse .env.example; return active (uncommented) keys in order with defaults.

    Returns:
        (order: list[str], defaults: dict[str, str])
    """
    order, defaults = [], {}
    if not path.exists():
        return order, defaults
    for raw in path.read_text(encoding="utf-8").splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        m = _KEY_LINE.match(stripped)
        if not m:
            continue
        key, val = m.group(1), m.group(2)
        # 去掉行內註解（value 後方 空白+# …）；本專案的值不含 '#'，安全
        val = re.sub(r"\s+#.*$", "", val).strip()
        if key not in defaults:
            order.append(key)
        defaults[key] = val
    return order, defaults


def extract_compose_keys() -> set:
    """撈出所有 compose 檔引用的 ${VAR} 名稱 / All ${VAR} names referenced by compose."""
    pat = re.compile(r"\$\{([A-Z_][A-Z0-9_]*)")
    keys = set()
    for p in COMPOSE_FILES:
        if p.exists():
            keys.update(pat.findall(p.read_text(encoding="utf-8")))
    return keys


def extract_settings_keys() -> set:
    """
    ZH: 從 config.py 撈 pydantic Settings 欄位（4 空格縮排的 UPPER: ）
        + os.environ.get / os.getenv 直接讀的 key（如 OIDC_*）。
    EN: Settings field annotations + direct os.environ reads from config.py.
    """
    keys = set()
    if not CONFIG_PY.exists():
        return keys
    text = CONFIG_PY.read_text(encoding="utf-8")
    # 只認「4 空格縮排 + 有型別註記」的 Settings 欄位，避免吃到 docstring 的 ZH:/EN:
    # （型別限 str/int/bool/float；新增其他型別欄位時請一併補進此清單）
    keys.update(re.findall(
        r"(?m)^[ \t]{4}([A-Z][A-Z0-9_]*)[ \t]*:[ \t]*(?:str|int|bool|float)\b", text))
    keys.update(re.findall(
        r"os\.(?:environ\.get|getenv)\(\s*['\"]([A-Z][A-Z0-9_]*)['\"]", text))
    return keys


# ZH: 刻意不放進 .env.example 的 key（不算漂移）：
#   KNOWLEDGE_DIR — 容器內計算路徑，不由 .env 設定
_INTENTIONAL_UNDECLARED = {
    "KNOWLEDGE_DIR": "容器內計算路徑，不經 .env",
}


def audit_drift(example_keys: set):
    """
    ZH: 交叉比對 .env.example（宣告）vs compose∪Settings（實際引用）。
    EN: Cross-check declared (.env.example) vs referenced (compose ∪ Settings).

    Returns:
        (referenced, missing_from_example, orphan_in_example, intentional)
    """
    referenced = extract_compose_keys() | extract_settings_keys()
    missing_from_example = (referenced - example_keys) - set(_INTENTIONAL_UNDECLARED)
    intentional = (referenced - example_keys) & set(_INTENTIONAL_UNDECLARED)
    orphan_in_example = example_keys - referenced
    return referenced, missing_from_example, orphan_in_example, intentional


def render_env_from_example(overlay: dict, note: str) -> str:
    """
    ZH: 以 .env.example 為骨架渲染出一份 .env：有效 key 以 overlay 值覆寫（沒給則沿用範本預設），
        行內註解一律移除（避免 docker-compose/pydantic 把 '# …' 當成值的一部分），
        全行註解、空行、『已停用』區原樣保留。
    EN: Render a .env from .env.example skeleton; active keys take overlay value (else the
        example default), inline comments stripped, full-line comments/blanks preserved.
    """
    lines_out = [
        "# ==============================================================================",
        f"# {note}",
        "# ⚠  請勿提交此檔至版本控制 / Do NOT commit this file (.gitignore excludes .env)",
        "# ==============================================================================",
        "",
    ]
    for raw in ENV_EXAMPLE.read_text(encoding="utf-8").splitlines():
        stripped = raw.strip()
        m = _KEY_LINE.match(stripped)
        if m and not stripped.startswith("#"):
            key = m.group(1)
            val = overlay.get(key)
            if val is None:
                # 沿用範本預設（去行內註解）
                val = re.sub(r"\s+#.*$", "", m.group(2)).strip()
            lines_out.append(f"{key}={val}")
        else:
            lines_out.append(raw)
    return "\n".join(lines_out).rstrip() + "\n"


# ══════════════════════════════════════════════════════════════════════════════
# --check 模式：漂移稽核 + 補齊 .env 缺漏 key / Drift audit + patch missing keys
# ══════════════════════════════════════════════════════════════════════════════
def print_drift_audit(example_order) -> int:
    """
    ZH: 交叉比對 .env.example vs compose∪Settings，印出漂移報告。
    EN: Print drift report between .env.example and compose ∪ Settings.

    Returns:
        真漂移數（compose/Settings 有引用、但 .env.example 沒宣告）/ number of real drifts
    """
    section("漂移稽核 / Drift Audit（.env.example vs compose ∪ Settings）")
    if not ENV_EXAMPLE.exists():
        print(f"  {err('.env.example 不存在 / not found：' + str(ENV_EXAMPLE))}")
        return -1

    example_keys = set(example_order)
    referenced, missing_from_example, orphan_in_example, intentional = audit_drift(example_keys)

    print(f"  {dim(f'compose∪Settings 引用 {len(referenced)} 個 key；.env.example 宣告 {len(example_keys)} 個')}")

    if missing_from_example:
        print()
        print(f"  {err('漂移：以下 key 有被引用，但 .env.example 沒宣告（換機會漏設）')}")
        for k in sorted(missing_from_example):
            print(f"    {red('•')} {cyan(k)}")
    if orphan_in_example:
        print()
        print(f"  {warn('孤兒：.env.example 有宣告，但 compose/Settings 都沒引用（可能已廢棄）')}")
        for k in sorted(orphan_in_example):
            print(f"    {yellow('•')} {cyan(k)}")
    if intentional:
        print()
        print(f"  {dim('刻意未宣告（非漂移，供參考）：')}")
        for k in sorted(intentional):
            print(f"    {dim('• ' + k + ' — ' + _INTENTIONAL_UNDECLARED[k])}")

    print()
    if not missing_from_example and not orphan_in_example:
        print(f"  {bold(green('✅ 無漂移：.env.example 與 compose∪Settings 一致'))}")
    return len(missing_from_example)


def check_and_patch(path: Path, example_order, example_defaults) -> int:
    """
    ZH: 以 .env.example 的有效 key 為準，檢測 .env 缺少哪些，只追加不覆寫既有值。
        缺的是秘鑰（REQUIRED_KEYS）→ 自動生成；其餘 → 沿用 .env.example 預設值。
    EN: Using .env.example active keys as the reference, detect keys missing from .env
        and append only. Missing secrets are auto-generated; others copy the example default.

    Returns:
        缺失欄位數 / number of missing fields patched
    """
    section(f"檢查 .env 完整性 / Checking {path.name} against .env.example")
    if not path.exists():
        print(f"  {err('.env 不存在 / .env not found：' + str(path))}")
        print(f"  {dim('請先用互動模式建立 / Run setup_env.py without --check first')}")
        return -1

    existing = parse_env_file(path)
    print(f"  {dim(f'已存在欄位 / Existing keys: {len(existing)}；範本有效 key: {len(example_order)}')}")

    missing = []
    for key in example_order:
        if key not in existing:
            if key in REQUIRED_KEYS:
                val = REQUIRED_KEYS[key][0]()          # 秘鑰自動生成 / auto-gen secret
            else:
                val = example_defaults.get(key, "")     # 其餘沿用範本預設 / copy example default
            missing.append((key, val))

    if not missing:
        print(f"  {bold(green('✅ .env 已涵蓋範本所有 key / .env covers all example keys'))}")
        return 0

    for key, _ in missing:
        print(f"  {err('缺失 / Missing')}  {cyan(key)}")
    print()
    print(f"  {warn(f'共 {len(missing)} 個 key 缺失，準備追加 / Patching {len(missing)} missing keys')}")
    if not ask_yes_no("確認追加？/ Confirm append?", default=True):
        print(f"  {dim('已取消 / Cancelled')}")
        return -1

    backup_if_exists(path)
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(path, "a", encoding="utf-8") as f:
        f.write(f"\n# ── Migrated by setup_env.py --check at {now_str} ──\n")
        for key, val in missing:
            f.write(f"{key}={val}\n")
    print(f"  {ok(f'已補齊 {len(missing)} 個 key / Patched {len(missing)} keys → ' + str(path))}")
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

    # ── --check 模式：漂移稽核 + .env 完整性 + worker token 一致性 ──────────────
    if "--check" in sys.argv:
        example_order, example_defaults = parse_env_example(ENV_EXAMPLE)
        if not example_order:
            print(f"  {err('讀不到 .env.example，無法檢查 / cannot read .env.example')}")
            sys.exit(1)

        drift = print_drift_audit(example_order)
        rc1 = check_and_patch(SERVICE_ENV, example_order, example_defaults)

        # ── worker token 一致性（不一致 → heartbeat/領工作全 401 且無聲）──────────
        worker_warn = False
        if WORKER_ENV.exists():
            section("GPU Worker Token 一致性 / Worker token consistency")
            svc = parse_env_file(SERVICE_ENV)
            wk = parse_env_file(WORKER_ENV)
            root_token = svc.get("WORKER_API_TOKEN", "")
            worker_token = wk.get("API_TOKEN", "")
            if not worker_token:
                print(f"  {warn('gpu-worker/.env 沒有 API_TOKEN')}")
                worker_warn = True
            elif root_token and worker_token != root_token:
                print(f"  {err('不一致！worker API_TOKEN ≠ 根 .env WORKER_API_TOKEN → 會靜默 401')}")
                print(f"    {dim('根 .env  WORKER_API_TOKEN = ' + mask_secret(root_token))}")
                print(f"    {dim('worker   API_TOKEN        = ' + mask_secret(worker_token))}")
                worker_warn = True
            else:
                print(f"  {ok('worker API_TOKEN 與根 .env 一致 / matches root .env')}")

        print()
        if drift < 0 or rc1 < 0:
            print(f"  {warn('部分檢查未完成 / Some checks not completed')}")
            sys.exit(1)
        if drift == 0 and rc1 == 0 and not worker_warn:
            print(f"  {bold(green('✅ 一切就緒 / Everything in order — 可以 docker compose up -d 了'))}")
        else:
            if drift > 0:
                print(f"  {bold(yellow('⚠ .env.example 有漂移，請先補齊範本（step 1）再重跑 --check'))}")
            if rc1 > 0:
                print(f"  {bold(yellow('⚠ 已補齊 .env 缺漏，請重新啟動容器 / Patched — restart containers:'))}")
                print(f"     {cyan('docker compose down && docker compose up -d')}")
            if worker_warn:
                print(f"  {bold(yellow('⚠ 請修正 gpu-worker token 後重啟 worker'))}")
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

    # ── Service Layer .env（v3.1 step 2：從 .env.example 渲染，不再用寫死範本）──
    backup_if_exists(SERVICE_ENV)

    # 互動答案 + 自動生成秘鑰 → 疊到 .env.example 骨架上；沒被覆寫的 key 沿用範本預設。
    overlay = dict(gen)  # JWT/WORKER/WEBUI/SECRETS 四把秘鑰
    overlay.update({
        "ACCESS_TOKEN_EXPIRE_MINUTES": jwt_expire,
        "DEFAULT_MONTHLY_TOKEN_LIMIT": token_limit,
        "JOB_TIMEOUT_MINUTES":         job_timeout,
        "CORS_ORIGINS":                cors,
        "LOG_LEVEL":                   log_level,
        "SMTP_SERVER":                 smtp["SMTP_SERVER"],
        "SMTP_PORT":                   smtp["SMTP_PORT"],
        "SMTP_USERNAME":               smtp["SMTP_USERNAME"],
        "SMTP_PASSWORD":               smtp["SMTP_PASSWORD"],
        "SMTP_FROM_EMAIL":             smtp["SMTP_FROM_EMAIL"],
    })
    if setup_worker:
        overlay.update({
            "SERVICE_LAYER_URL":  worker["SERVICE_LAYER_URL"],
            "NODE_ID":            worker["NODE_ID"],
            "POLL_INTERVAL":      worker["POLL_INTERVAL"],
            "HEARTBEAT_INTERVAL": worker["HEARTBEAT_INTERVAL"],
            "STORAGE_MOUNT_PATH": worker["STORAGE_MOUNT_PATH"],
        })

    example_order, _example_defaults = parse_env_example(ENV_EXAMPLE)
    if example_order:
        service_content = render_env_from_example(
            overlay, f"由 scripts/setup_env.py 從 .env.example 渲染於 {now_str}"
        )
    else:
        # 保險：讀不到範本時，至少把已知 overlay 寫出去，不中斷部署
        print(f"  {warn('讀不到 .env.example，改用最小必要集寫入 / example missing, minimal write')}")
        service_content = "\n".join(f"{k}={v}" for k, v in overlay.items()) + "\n"

    SERVICE_ENV.write_text(service_content, encoding="utf-8")
    print(f"  {ok('服務層 / Service layer .env（從 .env.example 渲染）')} → {bold(str(SERVICE_ENV))}")

    # ── GPU Worker（v3.1 step 3：收斂為單一來源，不再寫獨立 gpu-worker/.env）──────
    # worker 的設定（SERVICE_LAYER_URL / WORKER_API_TOKEN / NODE_ID / POLL / HEARTBEAT /
    # STORAGE_MOUNT_PATH）已隨上面的 overlay 一起寫進「根 .env」；worker 由 gpu-worker/
    # start-worker.sh(.bat) 以 --env-file ../.env 啟動，避免雙 .env 漂移→靜默 401。
    if setup_worker:
        print(f"  {ok('GPU Worker 設定已併入根 .env / merged into root .env')}"
              f" — 啟動請用 {cyan('gpu-worker/start-worker.sh')}")
        # 舊版遺留的 gpu-worker/.env 已停用；若存在則提醒刪除（--env-file 會忽略它，但直接
        # docker compose up 仍可能誤用，留著是風險）。
        if WORKER_ENV.exists():
            print(f"  {warn('偵測到已停用的 gpu-worker/.env，建議刪除 / delete the deprecated file:')}")
            print(f"     {cyan('rm ' + str(WORKER_ENV))}")

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
            print(f"     {cyan('.\\start-worker.bat')}       {dim('# 自動帶 --env-file ..\\.env，勿直接 docker compose up')}")
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
            print(f"     {cyan('cd gpu-worker && ./start-worker.sh')}   {dim('# 自動帶 --env-file ../.env，勿直接 docker compose up')}")
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
