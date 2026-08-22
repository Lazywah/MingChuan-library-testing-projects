# -*- coding: utf-8 -*-
"""
ZH: 檢查全 repo 的 .py 在**最低支援版本**下是不是還編得過。

ZH: 為什麼要有這支 —— 實際發生過（2026-08-22，設 5090 節點時）：
    `setup_env.py` 有一行把反斜線寫進了 f-string 的 `{}` 裡：

        print(f"     {cyan('.\\start-worker.bat')}  ...")

    這在 Python 3.12（PEP 701）之後才合法，3.11 以前是 **SyntaxError**。
    開發機是 3.13，所以：

      1. 11 支 check_*.py 全綠
      2. 365 個測試全綠
      3. 使用者在 GPU 節點上一跑 setup_env.py 就爆

    也就是說，**驗證全部跑在比使用者更新的直譯器上**，
    這個缺陷在本機沒有任何一道關卡碰得到它。
    這與記憶裡「我驗的路徑不是使用者走的路徑」是同一族。

ZH: 最低版本 3.9 的出處是 `docs/01-quick-start.md`：
    「Python 3.9+（只用來跑 setup 腳本）」。**改那份文件時要一起改這裡。**

ZH: 兩段式檢查，因為單靠本機直譯器抓不到：
    - 第 1 段（一定會跑，無外部相依）：用 AST 找出**已知的 3.12-only 語法**。
      注意 `ast.parse(feature_version=...)` **對 f-string 無效**——它不會回退
      3.12 改掉的 tokenizer，會靜默放行。所以這裡是直接比對原始碼片段，
      不是靠 feature_version。
    - 第 2 段（有 Docker 才跑）：在 `python:3.9-slim` 裡真的 py_compile 一遍。
      這段才是權威，能抓到第 1 段沒列舉到的任何語法。

ZH: 沒有 Docker 時**不會假裝通過** —— 會明講第 2 段沒跑（skip 不是 pass）。

ZH: exit code：有問題回 1。這支**是**可以擋的 —— 它檢查的是「編不編得過」
    這種零判斷空間的事實。

@node scripts/check_python_compat.py
"""
import ast
import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent

# ZH: 最低支援版本。出處見上面的 docstring（docs/01-quick-start.md）。
MIN_PY = (3, 9)
MIN_PY_STR = "%d.%d" % MIN_PY
DOCKER_IMAGE = "python:%s-slim" % MIN_PY_STR

SKIP_PARTS = {"node_modules", ".git", "venv", ".venv", "__pycache__", "site-packages"}


def _py_files():
    """@node scripts/check_python_compat.py::_py_files"""
    return sorted(
        p for p in ROOT.rglob("*.py")
        if not any(x in p.parts for x in SKIP_PARTS)
    )


def _fstring_backslashes(src, tree):
    """
    ZH: 找出 f-string 的 `{}` 運算式裡含反斜線的地方（3.12 以前是 SyntaxError）。

    ZH: 只在本機直譯器 >= 3.12 時有意義 —— 3.12 起 AST 才會給 f-string 內部
        正確的行列位置，`get_source_segment` 才切得出運算式原文。
        本機若是 3.11 以下，這種檔案根本 parse 不過，會被呼叫端的
        SyntaxError 分支接住，不會走到這裡。

    @node scripts/check_python_compat.py::_fstring_backslashes
    """
    if sys.version_info < (3, 12):
        return []
    hits = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.JoinedStr):
            continue
        for part in node.values:
            if not isinstance(part, ast.FormattedValue):
                continue
            seg = ast.get_source_segment(src, part.value)
            if seg and "\\" in seg:
                hits.append((part.lineno, "f-string 的 {} 裡有反斜線：%s" % seg.strip()))
    return hits


def _pep695(tree):
    """
    ZH: PEP 695 的泛型語法（`type X = int`、`def f[T]()`、`class C[T]`），3.12 才有。

    @node scripts/check_python_compat.py::_pep695
    """
    hits = []
    for node in ast.walk(tree):
        if isinstance(node, getattr(ast, "TypeAlias", ())):
            hits.append((node.lineno, "PEP 695 的 `type X = ...`（3.12+）"))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if getattr(node, "type_params", None):
                hits.append((node.lineno, "PEP 695 的泛型參數 `[T]`（3.12+）：%s" % node.name))
    return hits


def scan_ast():
    """
    ZH: 第 1 段。回傳 [(相對路徑, 行號, 說明)]。

    @node scripts/check_python_compat.py::scan_ast
    """
    problems = []
    files = _py_files()
    for p in files:
        try:
            src = p.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            problems.append((p.relative_to(ROOT), 0, "讀不到／不是 UTF-8：%s" % e))
            continue
        try:
            tree = ast.parse(src, filename=str(p))
        except SyntaxError as e:
            # ZH: 本機就 parse 不過（例如本機正好是 3.11）——直接就是答案。
            problems.append((p.relative_to(ROOT), e.lineno or 0, e.msg))
            continue
        for lineno, msg in _fstring_backslashes(src, tree) + _pep695(tree):
            problems.append((p.relative_to(ROOT), lineno, msg))
    return files, problems


def scan_docker():
    """
    ZH: 第 2 段。回傳 (狀態, 訊息清單)，狀態為 "ok" / "fail" / "skip"。

    @node scripts/check_python_compat.py::scan_docker
    """
    try:
        r = subprocess.run(["docker", "info"], capture_output=True, timeout=20)
    except Exception as e:
        return "skip", ["無法執行 docker：%s" % e]
    if r.returncode != 0:
        return "skip", ["Docker daemon 未啟動"]

    # ZH: 探測腳本要放在 **repo 外面** —— 放在 scripts/ 底下的話，
    #     容器內的 rglob 會把它自己也算進去（會出現 82 vs 83 這種對不上的數字）。
    tmpdir = pathlib.Path(tempfile.mkdtemp(prefix="pycompat-"))
    helper = tmpdir / "_compat_probe.py"
    probe = (
        "import pathlib, py_compile, sys\n"
        "SKIP = %r\n"
        "bad = []\n"
        "files = [p for p in pathlib.Path('/w').rglob('*.py')\n"
        "         if not any(x in p.parts for x in SKIP)]\n"
        "for p in sorted(files):\n"
        "    try:\n"
        "        py_compile.compile(str(p), cfile='/tmp/o.pyc', doraise=True)\n"
        "    except py_compile.PyCompileError as e:\n"
        "        bad.append('%%s|%%s' %% (str(p)[3:], str(e).strip().splitlines()[-1]))\n"
        "print('FILES=%%d' %% len(files))\n"
        "for b in bad:\n"
        "    print('BAD=' + b)\n"
    ) % (sorted(SKIP_PARTS),)
    helper.write_text(probe, encoding="utf-8")
    try:
        r = subprocess.run(
            ["docker", "run", "--rm",
             "-v", "%s:/w" % ROOT,
             "-v", "%s:/probe.py" % helper,
             DOCKER_IMAGE, "python", "/probe.py"],
            capture_output=True, timeout=300,
        )
    except Exception as e:
        return "skip", ["docker run 失敗：%s" % e]
    finally:
        try:
            helper.unlink()
            tmpdir.rmdir()
        except OSError:
            pass

    out = r.stdout.decode("utf-8", "replace")
    if r.returncode != 0:
        return "skip", ["容器回傳 %d：%s" % (r.returncode,
                                             r.stderr.decode('utf-8', 'replace')[:200])]
    bad = [ln[4:] for ln in out.splitlines() if ln.startswith("BAD=")]
    if bad:
        return "fail", bad
    n = next((ln[6:] for ln in out.splitlines() if ln.startswith("FILES=")), "?")
    return "ok", [n]


def main():
    """@node scripts/check_python_compat.py::main"""
    print("最低支援版本相容性檢查（目標 Python %s）" % MIN_PY_STR)

    files, problems = scan_ast()
    print("  第 1 段 AST：掃了 %d 個 .py" % len(files))
    if sys.version_info < (3, 12):
        print("            （本機是 %d.%d，f-string 那類會直接由 parse 失敗抓到）"
              % sys.version_info[:2])

    status, detail = scan_docker()
    if status == "ok":
        print("  第 2 段 %s：%s 個 .py 全部編譯通過" % (DOCKER_IMAGE, detail[0]))
    elif status == "skip":
        print("  第 2 段 %s：⚠️ 沒有跑（%s）" % (DOCKER_IMAGE, detail[0]))
    print()

    if problems or status == "fail":
        seen = set()
        rows = []
        flagged_files = set()
        for path, lineno, msg in problems:
            # ZH: 一律轉成正斜線，否則同一個檔在兩段之間對不起來（Windows 是 \）。
            rel = pathlib.PurePath(path).as_posix()
            flagged_files.add(rel)
            key = (rel, lineno)
            if key not in seen:
                seen.add(key)
                rows.append("%s:%s  %s" % (rel, lineno or "?", msg))
        if status == "fail":
            # ZH: 第 2 段只補報「第 1 段沒抓到」的檔 —— 它的價值就在這裡。
            #     同一個檔兩段都報只是雜訊，而且第 1 段有精確行號、比較好用。
            for b in detail:
                path, _, msg = b.partition("|")
                rel = pathlib.PurePath(path).as_posix()
                if rel not in flagged_files:
                    rows.append("%s  %s（只有 %s 實測抓到）" % (rel, msg, DOCKER_IMAGE))
        print("[FAIL] %d 處在 Python %s 下編不過：" % (len(rows), MIN_PY_STR))
        for r in rows:
            print("  - %s" % r)
        print()
        print("  修法：反斜線不能寫在 f-string 的 {} 裡 —— 先抽成區域變數再插值。")
        print("  若真的要提高最低版本，改 docs/01-quick-start.md 與本檔的 MIN_PY。")
        return 1

    if status == "skip":
        print("[OK] 第 1 段沒發現已知的 3.12-only 語法")
        print("     ⚠️ 但第 2 段（權威）沒跑，這**不等於**在 Python %s 下一定編得過。"
              % MIN_PY_STR)
        print("     要完整驗證請先啟動 Docker Desktop 再跑一次。")
        return 0

    print("[OK] %d 個 .py 在 Python %s 下全部編譯通過" % (len(files), MIN_PY_STR))
    return 0


if __name__ == "__main__":
    sys.exit(main())
