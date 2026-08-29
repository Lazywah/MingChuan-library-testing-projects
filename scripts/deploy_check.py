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
    6. 全站時間是否一律 Asia/Taipei（呼叫 check_timezone.py）
    7. Python 模組層有沒有重複定義（呼叫 check_duplicate_defs.py）
    8. 回應的時間欄位有沒有明示時區（呼叫 check_naive_datetime.py）
    9. 每頁 HTML 有沒有載它的 JS 用到的共用檔（呼叫 check_js_globals.py）
    9b. 各 v2 目錄的共用檔是否與正本一致（呼叫 check_shared_ui_files.py）
    9c. 前端 JS 是否為可解析的 JavaScript（呼叫 check_js_syntax.py）
    9d. 會送到畫面上的錯誤訊息有沒有中文（呼叫 check_error_messages.py）
    9e. HTML 裡看得見的中文有沒有掛 data-i18n（呼叫 check_untranslated_html.py）
    9f. 有沒有把 <select> 的值當成布林用（呼叫 check_select_bool.py）
    9g. 全 repo 的 .py 在最低支援版本下編不編得過（呼叫 check_python_compat.py）
    9h. 後端挂的 API 前綴 nginx 有沒有跟著開路（呼叫 check_nginx_routes.py）
   10. 主機埠（80/8888/8002/3000/8787/11434）占用狀況

    退出碼：有 FAIL → 1（別部署）；只有 WARN 或全過 → 0。

用法 / Usage:
  python scripts/deploy_check.py

需求 / Requirements: Python 3.6+，無額外套件（重用 setup_env.py 的解析函式）。
==============================================================================
"""
import re
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
    (80,    "nginx web (/ → /V1/，使用者入口)"),
    (8888,  "nginx admin (管理端)"),
    (8002,  "job-scheduler API"),
    (3000,  "open-webui"),
    (8787,  "portkey gateway"),
    (11434, "ollama"),
]

PASS, WARN, FAIL = "PASS", "WARN", "FAIL"


def port_in_use(port: int) -> bool:
    """@node scripts/deploy_check.py::port_in_use"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.3)
        return s.connect_ex(("127.0.0.1", port)) == 0


def check_docker():
    """@node scripts/deploy_check.py::check_docker"""
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
    """@node scripts/deploy_check.py::check_env_file"""
    if se.SERVICE_ENV.exists():
        return PASS, f"根 .env 存在 / found: {se.SERVICE_ENV}"
    return FAIL, f"根 .env 不存在 → 先跑 python scripts/setup_env.py"


def check_secrets(env: dict):
    """@node scripts/deploy_check.py::check_secrets"""
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

    @node scripts/deploy_check.py::check_inline_comments
    """
    import re as _re
    bad = [k for k, v in env.items() if _re.search(r"\s#", v)]
    if bad:
        return FAIL, ("以下 key 的值疑似黏到行內註解（compose 會把 # 後面當成值）："
                      + "、".join(bad) + " → 請把該行改成純 KEY=值")
    return PASS, ".env 值中無行內註解殘留"


def check_bootstrap_admin(env: dict):
    """
    ZH: v3.3 —— 首次部署若 BOOTSTRAP_ADMIN_PASSWORD 留空，服務啟動後不會自動建立管理員，
        使用者將完全無法進入管理端（學生端也要 SSO）。此處提前提醒。
        （已存在 admin 的既有部署留空是正常的，故為 WARN 而非 FAIL。）
    EN: Warn when no bootstrap admin password is set (fresh installs would have no admin).

    @node scripts/deploy_check.py::check_bootstrap_admin
    """
    pw = (env.get("BOOTSTRAP_ADMIN_PASSWORD") or "").strip()
    if pw:
        if len(pw) < 8:
            return WARN, "BOOTSTRAP_ADMIN_PASSWORD 短於 8 字元，建議加長"
        return PASS, "初始管理員密碼已設定（首次啟動且無任何 admin 時會自動建立 admin）"
    return WARN, ("BOOTSTRAP_ADMIN_PASSWORD 留空 → 全新部署不會自動建立管理員。"
                  "既有部署已有 admin 則屬正常；否則請重跑 setup_env.py 或用 scripts/create-admin.bat")


def check_sso(env: dict):
    """
    ZH: SSO 設定健檢。sso_policy.yaml committed 為 provider=oidc + mock_mode=false，
        若新機器沒填 OIDC 憑證，系統會 fallback 成 mock、/providers 回空
        → **學生一個都登入不了**（admin 仍可走 :8888）。這在畫面上看起來像壞掉，
        故在部署前就明講。此為 WARN 而非 FAIL：憑證要跟學校 IT 申請，新機初期沒有是正常的。
    EN: Warn when provider=oidc but credentials are absent — students cannot log in at all.

    @node scripts/deploy_check.py::check_sso
    """
    policy = se.ROOT_DIR / "job-scheduler" / "app" / "sso_policy.yaml"
    if not policy.exists():
        return WARN, "找不到 sso_policy.yaml，無法檢查 SSO 設定"
    text = policy.read_text(encoding="utf-8")

    def _val(key):
        """@node scripts/deploy_check.py::check_sso.<nested@147>._val"""
        m = re.search(rf"(?m)^\s*{key}\s*:\s*(.+?)\s*(?:#.*)?$", text)
        return m.group(1).strip().strip('"\'') if m else ""

    provider = _val("provider")
    mock_mode = _val("mock_mode").lower()
    if provider != "oidc":
        return WARN, f"SSO provider={provider or '?'}（非 oidc）；學生端登入將走 mock/停用狀態"
    has_id = bool(env.get("OIDC_CLIENT_ID"))
    has_secret = bool(env.get("OIDC_CLIENT_SECRET"))
    if not (has_id and has_secret):
        missing = " / ".join(k for k, v in (("OIDC_CLIENT_ID", has_id),
                                            ("OIDC_CLIENT_SECRET", has_secret)) if not v)
        return WARN, (f"provider=oidc 但 .env 缺 {missing} → SSO 停用、**學生無法登入**"
                      f"（admin 仍可用 :8888）。請向學校 IT 申請憑證後填入 .env")
    if mock_mode == "true":
        return FAIL, "OIDC 憑證已備但 mock_mode=true → 會強制走 mock SSO，請改為 false"
    redirect = env.get("OIDC_REDIRECT_URI", "")
    if redirect and ":8002" in redirect:
        return FAIL, "OIDC_REDIRECT_URI 指向 :8002（API 直連埠，不服務 /V0/）→ 請改走 nginx origin"
    return PASS, "SSO OIDC 設定完整（provider=oidc、憑證已填、mock_mode=false）"


def check_kb_freshness():
    """
    ZH: 知識庫提到的介面字串是否還存在（小基會不會拿舊名稱指路）。

    ZH: 這一條是 WARN 不是 FAIL —— 知識庫過期不會讓平台起不來，
        但會讓小基自信地講錯，而那要兩個月才有人發現。

    @node scripts/deploy_check.py::check_kb_freshness
    """
    import subprocess as _sp
    r = _sp.run([sys.executable, str(SCRIPTS_DIR / "check_kb_freshness.py")],
                capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode == 0:
        return PASS, "知識庫提到的介面字串都還在"
    return WARN, "知識庫可能過期（介面改名了沒跟上）→ python scripts/check_kb_freshness.py"


def check_ollama_models(env: dict):
    """
    ZH: 設定裡指名的 Ollama 模型有沒有真的下載下來。

    ZH: 🔴 為什麼需要這一條：原本只檢查 11434 埠通不通 —— 那只證明 Ollama 活著，
        不證明它有那個模型。模型沒下載時**小基不會報錯**，它會拿到空的檢索結果
        然後照樣回答（內容是編的），或是回一句「AI 服務尚未啟動」。
        兩種都不會讓人聯想到「模型沒 pull」。

    ZH: ⚠ 2026-08-28 嵌入模型從 nomic-embed-text 換成 bge-m3，
        舊機器上照舊指南裝的人只會 pull 到舊的那個。這條就是給那種情況看的。

    @node scripts/deploy_check.py::check_ollama_models
    """
    want = [v for v in (env.get("RAG_EMBED_MODEL"), env.get("RAG_CHAT_MODEL")) if v]
    if not want:
        return WARN, ".env 沒有指定 RAG_EMBED_MODEL / RAG_CHAT_MODEL（會用程式預設）"
    if not port_in_use(11434):
        return WARN, "Ollama 沒在跑（11434 不通），跳過模型檢查"
    try:
        r = subprocess.run(["docker", "exec", "ai-platform-ollama", "ollama", "list"],
                           capture_output=True, timeout=20, text=True, encoding="utf-8",
                           errors="replace")
    except Exception as e:
        return WARN, f"問不到 Ollama 的模型清單：{e}"
    if r.returncode != 0:
        return WARN, "問不到 Ollama 的模型清單（容器名可能不是 ai-platform-ollama）"
    # ZH: `ollama list` 會把 `bge-m3` 顯示成 `bge-m3:latest`，所以比對要去掉 tag。
    have = {ln.split()[0].split(":")[0] for ln in r.stdout.splitlines()[1:] if ln.strip()}
    missing = [m for m in want if m.split(":")[0] not in have]
    if missing:
        return FAIL, ("Ollama 缺模型 → " + "、".join(missing)
                      + "（補：docker exec ai-platform-ollama ollama pull <名稱>）")
    return PASS, "Ollama 已備妥設定指名的模型：" + "、".join(want)


def check_drift():
    """@node scripts/deploy_check.py::check_drift"""
    order, _defaults = se.parse_env_example(se.ENV_EXAMPLE)
    if not order:
        return FAIL, "讀不到 .env.example"
    _ref, missing_from_example, _orphan, _intentional = se.audit_drift(set(order))
    if missing_from_example:
        return FAIL, "設定漂移：compose/Settings 引用但 .env.example 未宣告 → " + "、".join(sorted(missing_from_example))
    return PASS, ".env.example 與 compose∪Settings 一致（無漂移）"


def check_env_completeness(env: dict):
    """@node scripts/deploy_check.py::check_env_completeness"""
    order, _defaults = se.parse_env_example(se.ENV_EXAMPLE)
    missing = [k for k in order if k not in env]
    if missing:
        return WARN, (f".env 少了 {len(missing)} 個範本 key（將用程式預設；可跑 "
                      f"python scripts/setup_env.py --check 補齊）")
    return PASS, ".env 已涵蓋 .env.example 全部 key"


def check_worker_convergence():
    """@node scripts/deploy_check.py::check_worker_convergence"""
    if se.WORKER_ENV.exists():
        return WARN, (f"偵測到已停用的 gpu-worker/.env（step 3 已收斂）→ 建議刪除："
                      f"rm {se.WORKER_ENV}")
    return PASS, "gpu-worker 設定單一來源（無殘留 gpu-worker/.env）"


def check_asset_versions():
    """@node scripts/deploy_check.py::check_asset_versions"""
    script = SCRIPTS_DIR / "bump_assets.py"
    if not script.exists():
        return WARN, "找不到 bump_assets.py，略過 ?v= 檢查"
    r = subprocess.run([sys.executable, str(script), "--check"], capture_output=True)
    if r.returncode == 0:
        return PASS, "前端 ?v= 皆為最新內容 hash"
    return WARN, "前端 ?v= 有過期 → 跑 python scripts/bump_assets.py 後再部署"


def check_timezone():
    """ZH: 全站時間一律 Asia/Taipei —— tz.js 五份一致 + 載入順序 + 行為測試。

    ZH: 為什麼列進部署前健檢：時區壞掉**不會報錯、不會壞版面**，
        只是每個時間都錯 8 小時。沒有人會回報這種東西，只會慢慢不信任畫面上的數字。

    @node scripts/deploy_check.py::check_timezone
    """
    script = SCRIPTS_DIR / "check_timezone.py"
    if not script.exists():
        return WARN, "找不到 check_timezone.py，略過時區一致性檢查"
    r = subprocess.run([sys.executable, str(script)], capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    out = (r.stdout or "") + (r.stderr or "")
    if r.returncode != 0:
        first = next((l.strip() for l in out.splitlines() if "[FAIL]" in l), "")
        return FAIL, f"tz.js 時區檢查不通過 → python scripts/check_timezone.py　{first}"
    if "[WARN]" in out:
        # ZH: 行為測試沒跑到（多半是機器沒有 node）。**不要顯示成通過**——
        #     「沒檢查」與「檢查過了」必須看得出來（§26.8）。
        return WARN, "tz.js 五份一致，但**行為測試未執行**（機器沒有 node）"
    return PASS, "tz.js 五份一致、載入順序正確、行為測試通過（全站 Asia/Taipei）"


def check_i18n():
    """ZH: 翻譯完整性——key 齊全、無多餘、佔位符一致。

    ZH: 為什麼列進部署前健檢：漏翻**不會報錯**，那一句只是永遠維持中文，
        而看得出來的人正是看不懂中文的那個。

    @node scripts/deploy_check.py::check_i18n
    """
    script = SCRIPTS_DIR / "check_i18n.py"
    if not script.exists():
        return WARN, "找不到 check_i18n.py，略過翻譯完整性檢查"
    r = subprocess.run([sys.executable, str(script)], capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        first = next((l.strip() for l in (r.stdout or "").splitlines() if "[FAIL]" in l), "")
        return FAIL, f"翻譯不完整 → python scripts/check_i18n.py　{first}"
    return PASS, "翻譯 key 兩種語言齊全、佔位符一致"


def check_naive_datetime():
    """ZH: 回應的時間欄位有沒有明示時區。

    ZH: 為什麼列進部署前健檢：漏掉**不會報錯、不會壞版面**，
        只是 +08:00 的使用者看到的每個時間都早 8 小時。
        第一次發現時只修了問題回報一個，其餘**九個** schema 是機械掃出來的。

    @node scripts/deploy_check.py::check_naive_datetime
    """
    script = SCRIPTS_DIR / "check_naive_datetime.py"
    if not script.exists():
        return WARN, "找不到 check_naive_datetime.py，略過時區標記檢查"
    r = subprocess.run([sys.executable, str(script)], capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        first = next((l.strip() for l in (r.stdout or "").splitlines() if "[FAIL]" in l), "")
        return FAIL, f"有時間欄位沒帶時區 → python scripts/check_naive_datetime.py　{first}"
    return PASS, "回應的時間欄位都有明示時區（UTC）"


def check_untranslated_html():
    """ZH: HTML 裡看得見的中文有沒有掛 data-i18n。

    ZH: 為什麼與 check_i18n 分開：那一支檢查的是「**已經掛上** data-i18n 的
        key 有沒有翻譯」。一段**完全沒掛**的中文它看不到 ——
        於是那段文字在英文模式下永遠是中文，而且沒有任何提示。

    ZH: 實際找到六處：四個載入佔位字、train.html 常駐的路徑約定、
        以及管理端五頁的 <title>（我自己漏的）。

    @node scripts/deploy_check.py::check_untranslated_html
    """
    script = SCRIPTS_DIR / "check_untranslated_html.py"
    if not script.exists():
        return WARN, "找不到 check_untranslated_html.py，略過"
    r = subprocess.run([sys.executable, str(script)], capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        first = next((l.strip() for l in (r.stdout or "").splitlines()
                      if l.strip().startswith("-")), "")
        return FAIL, f"有中文沒掛 data-i18n → python scripts/check_untranslated_html.py　{first}"
    return PASS, "HTML 裡的中文都掛了 data-i18n"


def check_error_messages():
    """ZH: 會送到畫面上的錯誤訊息有沒有中文。

    ZH: 為什麼列進部署前健檢：使用者是中文為主的師生。
        一個寫著 `Permission denied` 的錯誤對他們等於沒有訊息 ——
        不知道發生什麼事、也不知道能做什麼，只會來問管理員。
        而這種漏掉**不會壞任何功能**，所以除非有人剛好撞到那條路徑，
        否則永遠不會被發現。

    @node scripts/deploy_check.py::check_error_messages
    """
    script = SCRIPTS_DIR / "check_error_messages.py"
    if not script.exists():
        return WARN, "找不到 check_error_messages.py，略過錯誤訊息檢查"
    r = subprocess.run([sys.executable, str(script)], capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        first = next((l.strip() for l in (r.stdout or "").splitlines()
                      if l.strip().startswith("-")), "")
        return FAIL, f"有錯誤訊息只有英文 → python scripts/check_error_messages.py　{first}"
    return PASS, "錯誤訊息都有中文"


def check_select_bool():
    """ZH: 有沒有把 <select> 的值當成布林用。

    ZH: 為什麼列進部署前健檢：`<select>` 的 .value 永遠是字串，而 '0' 在 JS
        裡是 truthy。實測過一次——管理端「模型」的「公開」欄寫成
        `is_public: !!m.is_public`，結果是**光按下編輯再按儲存，所有非公開的
        模型都被改成公開**，畫面還顯示「存好了：改了 2 列」。

    ZH: 後端測試抓不到：它收到的是一個合法的 true，無從知道那個 true 是
        從字串 '0' 變出來的。

    @node scripts/deploy_check.py::check_select_bool
    """
    script = SCRIPTS_DIR / "check_select_bool.py"
    if not script.exists():
        return WARN, "找不到 check_select_bool.py，略過"
    r = subprocess.run([sys.executable, str(script)], capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    out = r.stdout or ""
    if r.returncode != 0:
        first = next((l.strip() for l in out.splitlines() if l.strip().startswith("-")), "")
        return FAIL, f"下拉的值被當成布林 → python scripts/check_select_bool.py　{first}"
    return PASS, "沒有把下拉的值當成布林用"


def check_python_compat():
    """ZH: 全 repo 的 .py 在最低支援版本（Python 3.9）下還編不編得過。

    ZH: 為什麼列進部署前健檢：實際發生過（2026-08-22，設 5090 節點時）——
        `setup_env.py` 把反斜線寫進了 f-string 的 `{}`，那是 3.12 才合法的寫法。
        開發機是 3.13，所以 11 支 check_*.py 與 365 個測試**全綠**，
        使用者在節點上一跑就是 SyntaxError，而且是**部署的第一步**就卡死。

    ZH: 這類缺陷本機一道關卡都碰不到，因為驗證全部跑在比使用者更新的直譯器上。

    @node scripts/deploy_check.py::check_python_compat
    """
    script = SCRIPTS_DIR / "check_python_compat.py"
    if not script.exists():
        return WARN, "找不到 check_python_compat.py，略過"
    r = subprocess.run([sys.executable, str(script)], capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    out = r.stdout or ""
    if r.returncode != 0:
        first = next((l.strip() for l in out.splitlines() if l.strip().startswith("-")), "")
        return FAIL, f"有程式碼在 Python 3.9 下編不過 → python scripts/check_python_compat.py　{first}"
    # ZH: Docker 沒開時第 2 段（權威）不會跑，這時只能算 WARN，不能報成完全通過。
    if "沒有跑" in out:
        return WARN, "只做了 AST 檢查；要完整驗證請開 Docker Desktop 再跑一次"
    return PASS, "全部 .py 在 Python 3.9 下都編得過"


def check_nginx_routes():
    """ZH: main.py 挂的 API 前綴，nginx :80 有沒有對應的 location。

    ZH: 為什麼列進部署前健檢 —— **同一類已經發生兩次**：
        2026-07 `/api/v1/models` 回 502、2026-08 `/api/v1/reports` 回 405
        （問題回報送不出去）。兩次都是加了 include_router 卻沒回
        nginx.conf 補 location，請求落到 catch-all 被送去 Open WebUI。

    ZH: 後端測試拓不到這類缺陷 —— 它根本沒被呼叫到；
        而且症狀是 405/502 而不是 404，Server 標頭還是 nginx，
        看起來像後端壞了。

    @node scripts/deploy_check.py::check_nginx_routes
    """
    script = SCRIPTS_DIR / "check_nginx_routes.py"
    if not script.exists():
        return WARN, "找不到 check_nginx_routes.py，略過"
    r = subprocess.run([sys.executable, str(script)], capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    out = r.stdout or ""
    if r.returncode != 0:
        first = next((l.strip() for l in out.splitlines() if l.strip().startswith("-")), "")
        return FAIL, f"有 API 前綴 nginx 沒開路 → python scripts/check_nginx_routes.py　{first}"
    # ZH: 白名單長灰塵不擋部署，但要看得到。
    if "可以清掉" in out:
        return WARN, "前綴都有開路，但 ALLOW_NOT_ON_80 有過期項目可以清"
    return PASS, "後端 API 前綴在 nginx :80 都有對應的 location"


def check_js_syntax():
    """ZH: 前端每一支 .js 是否為可解析的 JavaScript。

    ZH: 為什麼列進部署前健檢：實際發生過而且已經 commit ——
        `i18n-admin.js` 裡一個沒跳脫的撇號（`user's`）讓整個檔案無法解析，
        `Object.assign` 從來沒執行，**英文模式下管理端的翻譯全部失效**。

    ZH: 它沒被發現的原因值得記著：中文模式因為有 fallback 看起來完全正常、
        check_i18n 用正規表示式讀字典不驗語法、而每個 <script> 各自獨立
        所以頁面不會整個壞掉。三件事加起來就是一個看不出來的靜默失效。

    @node scripts/deploy_check.py::check_js_syntax
    """
    script = SCRIPTS_DIR / "check_js_syntax.py"
    if not script.exists():
        return WARN, "找不到 check_js_syntax.py，略過 JS 語法檢查"
    r = subprocess.run([sys.executable, str(script)], capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    out = r.stdout or ""
    if r.returncode != 0:
        first = next((l.strip() for l in out.splitlines() if l.strip().startswith("-")), "")
        return FAIL, f"有 JS 無法解析 → python scripts/check_js_syntax.py　{first}"
    if "[WARN]" in out:
        return WARN, "找不到 node，略過 JS 語法檢查"
    return PASS, "前端 JS 都能解析"


def check_shared_ui_files():
    """ZH: 各 v2 目錄的共用檔（tokens/styles/i18n/prefs）是否與正本逐位元組相同。

    ZH: 為什麼列進部署前健檢：nginx 每個 UI 版本是各自的 alias 根目錄，跨不過去，
        所以共用檔只能每個目錄各放一份。重複的檔案**沒有機械檢查就一定會漂開**——
        症狀是「同一個功能在管理端好好的、在使用者端壞掉」，
        而兩邊的程式碼看起來都對，因為沒有人會同時打開四個檔案比對。

    @node scripts/deploy_check.py::check_shared_ui_files
    """
    script = SCRIPTS_DIR / "check_shared_ui_files.py"
    if not script.exists():
        return WARN, "找不到 check_shared_ui_files.py，略過共用檔一致性檢查"
    r = subprocess.run([sys.executable, str(script)], capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        first = next((l.strip() for l in (r.stdout or "").splitlines()
                      if l.strip().startswith("-")), "")
        return FAIL, ("共用檔已漂開 → python scripts/check_shared_ui_files.py --fix　"
                      f"{first}")
    return PASS, "各 v2 目錄的共用檔與正本一致"


def check_js_globals():
    """ZH: 每頁 HTML 有沒有載它的 JS 會用到的共用檔（tz.js / i18n.js / prefs.js）。

    ZH: 為什麼列進部署前健檢：漏一個 `<script>` 標籤的症狀**會騙人**。
        實際發生過 —— `lab.js` 用了 `TW.when()` 而 `lab.html` 沒載 `tz.js`：
        頁面正常載入、console 乾乾淨淨（例外被 catch 吃掉），
        畫面顯示「暫時讀不到清單」，看起來完全像**後端或網路**壞了。
        而後端好好的、資料也真的拿到了。

    @node scripts/deploy_check.py::check_js_globals
    """
    script = SCRIPTS_DIR / "check_js_globals.py"
    if not script.exists():
        return WARN, "找不到 check_js_globals.py，略過共用檔載入檢查"
    r = subprocess.run([sys.executable, str(script)], capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        first = next((l.strip() for l in (r.stdout or "").splitlines() if l.strip().startswith("-")), "")
        return FAIL, f"有頁面少載共用檔 → python scripts/check_js_globals.py　{first}"
    return PASS, "每頁都載了它用到的共用檔"


def check_duplicate_defs():
    """ZH: Python 模組層重複定義——同名的 def/class 出現兩次，後者無聲蓋掉前者。

    ZH: 為什麼列進部署前健檢：這種錯誤**不會報錯也不會讓測試變紅**，
        程式行為甚至是正確的（用最後一份）。它會在「只改了其中一份」時才爆——
        症狀是「我明明改了卻沒有作用」。

    @node scripts/deploy_check.py::check_duplicate_defs
    """
    script = SCRIPTS_DIR / "check_duplicate_defs.py"
    if not script.exists():
        return WARN, "找不到 check_duplicate_defs.py，略過重複定義檢查"
    r = subprocess.run([sys.executable, str(script)], capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        first = next((l.strip() for l in (r.stdout or "").splitlines() if "[X]" in l), "")
        return FAIL, f"有重複定義 → python scripts/check_duplicate_defs.py　{first}"
    return PASS, "Python 模組層無重複定義"


def check_ports():
    """回傳單一彙總（有占用列為 WARN，因可能是本平台已在跑）。

    @node scripts/deploy_check.py::check_ports
    """
    in_use = [(p, label) for p, label in EXPECTED_PORTS if port_in_use(p)]
    if not in_use:
        return PASS, "主機埠 80/8888/8002/3000/8787/11434 皆空閒"
    detail = "、".join(f"{p}({label})" for p, label in in_use)
    return WARN, f"以下埠占用中（若本平台已在運行則屬正常）：{detail}"


def main():
    """@node scripts/deploy_check.py::main"""
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
        ("初始管理員",     check_bootstrap_admin(env)),
        ("SSO 設定",       check_sso(env)),
        ("設定漂移",       check_drift()),
        (".env 完整性",    check_env_completeness(env)),
        ("gpu-worker 收斂", check_worker_convergence()),
        ("前端 ?v=",       check_asset_versions()),
        ("時間時區",       check_timezone()),
        ("翻譯完整性",     check_i18n()),
        ("重複定義",       check_duplicate_defs()),
        ("時間帶時區",     check_naive_datetime()),
        ("共用檔載入",     check_js_globals()),
        ("共用檔一致",     check_shared_ui_files()),
        ("JS 語法",        check_js_syntax()),
        ("nginx 路由",     check_nginx_routes()),
        ("Python 相容",    check_python_compat()),
        ("下拉當布林",     check_select_bool()),
        ("錯誤訊息中文",   check_error_messages()),
        ("HTML 中文標記",  check_untranslated_html()),
        ("知識庫新鮮度",   check_kb_freshness()),
        ("Ollama 模型",    check_ollama_models(env)),
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
