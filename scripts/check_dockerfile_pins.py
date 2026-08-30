# -*- coding: utf-8 -*-
"""
ZH: 檢查 base image 的 Dockerfile 有沒有抓「會漂的標的」。

ZH: 為什麼要有這支 —— 實際發生過兩次，**同一個根因、換了個形狀**：

    第一次：`aibase/tensorflow` 建不起來。當時的解法是逐案把 TF 升到 2.21
            （因為舊版沒有 cp313 wheel）。沒有人去處理「為什麼 Python 版本會變」。

    第二次（2026-08-22，5090 節點首次建置）：`aibase/pytorch` 的 `[2/3]` 失敗 ——

        ERROR: Could not find a version that satisfies the requirement torch==2.7.0
               (from versions: 2.9.0+cu128, 2.9.1+cu128, 2.10.0+cu128, 2.11.0+cu128)

            根因是 `Miniconda3-latest-Linux-x86_64.sh`：兩個月前它給 Python 3.13，
            2026-08 變成 3.14，而 repo 釘的 torch 2.7.0 / TF 2.21 都沒有 cp314 wheel。
            波及三個 image（pytorch / pytorch-legacy / tensorflow），
            其中後兩個**一個可升的版本都沒有**。

ZH: 「升 torch 到 2.9」不是修法 —— 那只救得了三個裡的一個。
    要修的是**機制**：把底下的 Python 釘住。這支就是那道防線。

ZH: 🔴 這類缺陷最惡劣的地方是**它不會在寫程式的當下爆**。
    Dockerfile 一個字都沒改，昨天建得起來、今天建不起來，
    差別只在上游把 `latest` 指到別的地方。開發機還留著兩個月前建好的 image，
    所以那台**永遠不會重現**。

ZH: 抓什麼：
      · Miniconda / Anaconda 安裝檔用 `-latest-`
      · `FROM xxx:latest`、以及 `FROM xxx`（省略 tag ＝ latest）
      · apt/pip 之外的 `curl … latest …` 下載

ZH: ⚠ 刻意**不**抓的（抓了會變成假警報，而會誤報的檢查會被整支忽略）：
      · 註解裡出現的 `latest`（就像本檔上面那幾行）
      · `ollama/ollama:latest`、`registry:2` 這類**服務**映像 —— 它們在
        docker-compose 裡，不在 base-images/ 底下，本支不掃。
      · pip 套件不釘版（那是另一個問題，且 requirements.txt 有自己的規矩）

ZH: exit code：有問題回 1。可以擋 —— 「有沒有寫 latest」是零判斷空間的事實。

@node scripts/check_dockerfile_pins.py
"""
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
BASE_IMAGES = ROOT / "infrastructure" / "base-images"

# ZH: Miniconda/Anaconda 安裝檔的 `-latest-`
_INSTALLER = re.compile(r"(Miniconda3|Anaconda3)-latest-", re.I)

# ZH: FROM 後面的映像。`AS builder` 之類的尾巴要先切掉。
_FROM = re.compile(r"^\s*FROM\s+(\S+)", re.I)

# ZH: 其他 curl 到含 latest 的網址（例如某些工具的 /latest/download）
_CURL_LATEST = re.compile(r"curl[^\n]*\blatest\b", re.I)


def _strip_comment(line):
    """ZH: 去掉 `#` 之後的內容。Dockerfile 的註解一律整行或行尾。

    ZH: 這一步是**假警報的主要來源**——本檔自己的說明就含 `latest`，
        不剝註解的話它會報自己。

    @node scripts/check_dockerfile_pins.py::_strip_comment
    """
    i = line.find("#")
    return line if i < 0 else line[:i]


def _dockerfiles():
    """@node scripts/check_dockerfile_pins.py::_dockerfiles"""
    if not BASE_IMAGES.is_dir():
        return []
    return sorted(
        p for p in BASE_IMAGES.rglob("*")
        if p.is_file() and p.name.startswith("Dockerfile")
    )


def scan():
    """ZH: 回傳 (掃到的檔數, [(相對路徑, 行號, 說明)])。

    @node scripts/check_dockerfile_pins.py::scan
    """
    problems = []
    files = _dockerfiles()
    for p in files:
        try:
            lines = p.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError) as e:
            problems.append((p.relative_to(ROOT), 0, "讀不到／不是 UTF-8：%s" % e))
            continue

        rel = p.relative_to(ROOT)
        for n, raw in enumerate(lines, 1):
            line = _strip_comment(raw)
            if not line.strip():
                continue

            if _INSTALLER.search(line):
                problems.append((
                    rel, n,
                    "Miniconda/Anaconda 安裝檔用了 -latest-（Python 版本會漂；"
                    "改成 Miniconda3-py313_<版本>-Linux-x86_64.sh）",
                ))

            m = _FROM.match(line)
            if m:
                img = m.group(1)
                # ZH: ARG 展開（`FROM ${BASE_IMAGE}`）交給 ARG 的預設值那一行去管，
                #     這裡看不到值，硬報會是假警報。
                if not img.startswith("$"):
                    if img.endswith(":latest"):
                        problems.append((rel, n, "FROM 用了 :latest（%s）" % img))
                    elif ":" not in img.rsplit("/", 1)[-1]:
                        problems.append((
                            rel, n,
                            "FROM 沒寫 tag ＝ 隱含 :latest（%s）" % img,
                        ))

            if _CURL_LATEST.search(line) and not _INSTALLER.search(line):
                problems.append((rel, n, "curl 抓了含 latest 的網址（會漂）"))

    # ZH: ARG 的預設值也要看 —— `ARG BASE_IMAGE=nvidia/cuda:latest` 一樣會漂。
    for p in files:
        try:
            lines = p.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        rel = p.relative_to(ROOT)
        for n, raw in enumerate(lines, 1):
            line = _strip_comment(raw)
            m = re.match(r"^\s*ARG\s+\w*BASE_IMAGE\w*\s*=\s*(\S+)", line, re.I)
            if m and (m.group(1).endswith(":latest")
                      or ":" not in m.group(1).rsplit("/", 1)[-1]):
                problems.append((rel, n, "ARG BASE_IMAGE 預設值沒釘 tag（%s）" % m.group(1)))

    return files, problems


def main():
    """@node scripts/check_dockerfile_pins.py::main"""
    print("base image 釘版檢查")

    files, problems = scan()
    if not files:
        print("  找不到 %s，略過" % BASE_IMAGES.relative_to(ROOT))
        return 0

    print("  掃了 %d 個 Dockerfile" % len(files))

    if problems:
        print()
        print("[FAIL] %d 處抓了會漂的標的：" % len(problems))
        for path, lineno, msg in problems:
            print("  - %s:%s  %s" % (pathlib.PurePath(path).as_posix(), lineno or "?", msg))
        print()
        print("  為什麼要擋：Dockerfile 一個字都沒改，昨天建得起來、今天建不起來，")
        print("  而開發機留著舊 image 所以永遠不會重現。2026-08 就這樣壞了三個 image。")
        return 1

    print("[OK] 沒有 latest 這類會漂的標的")
    print("  * 這只證明「有釘」，不證明釘的版本是對的 ——")
    print("    換 Python 版本時要連同 torch / TF 的 wheel 相容性一起評估。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
