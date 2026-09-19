#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ZH: 產生「交給平台訓練」頁面上的範例資料集（表格分類、文字分類）。

ZH: 為什麼是產生器而不是直接放檔案：範例的內容要能被讀、被改、被審 ——
    一個 zip 進了版控之後沒有人看得出裡面是什麼，而這兩份是**合成**資料，
    規則就在這支腳本裡。跑一次就會把 zip 重新產出到 web-ui-V1/samples/。

ZH: 🔴 **固定隨機種子**。範例要可重現：同一支腳本跑兩次要得到同一個 zip，
    不然每次 commit 都會有一份「內容變了」的二進位 diff。

ZH: 貓狗那份**不在這裡**——它是真實照片，在 infrastructure/base-images/code-server/samples/，
    由 docker-compose 掛進 nginx 的 /V1/samples/。

用法：
    python scripts/make_training_samples.py
"""
import csv
import io
import pathlib
import random
import sys
import zipfile

try:
    sys.stdout.reconfigure(errors="replace")
except (AttributeError, ValueError):
    pass

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "web-ui-V1" / "samples"

# ZH: zip 裡的檔案時間固定 —— 不固定的話同一份內容每次壓出來的 bytes 都不一樣。
FIXED_TIME = (2026, 1, 1, 0, 0, 0)


def _zip_with(name: str, rows, out_path: pathlib.Path) -> None:
    """ZH: 把一份 CSV 壓成只有一個檔案的 zip。

    @node scripts/make_training_samples.py::_zip_with
    """
    buf = io.StringIO()
    csv.writer(buf, lineterminator="\n").writerows(rows)
    data = buf.getvalue().encode("utf-8-sig")   # ZH: 帶 BOM，Excel 直接打開不會亂碼
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        info = zipfile.ZipInfo(name, date_time=FIXED_TIME)
        info.compress_type = zipfile.ZIP_DEFLATED
        zf.writestr(info, data)


def tabular_sample() -> list:
    """ZH: 「這個學生會不會及格」—— 四個特徵、兩個類別，規則刻意讓模型學得到。

    ZH: 特徵：每週讀書時數、出席率、平均睡眠、期中成績、科系（文字欄，示範 one-hot）。
        及格與否由一個帶雜訊的線性規則決定，正確率上限大約九成（雜訊 sd=3 時實測約 88–92%） ——
        故意不做成 100%，太完美的範例會讓人以為真實資料也會這樣。

    @node scripts/make_training_samples.py::tabular_sample
    """
    rng = random.Random(20260101)
    depts = ["資工", "企管", "設計", "傳播"]
    rows = [["study_hours", "attendance", "sleep_hours", "midterm", "department", "label"]]
    for _ in range(320):
        study = round(rng.uniform(0, 12), 1)
        attend = round(rng.uniform(0.3, 1.0), 2)
        sleep = round(rng.uniform(4, 9), 1)
        midterm = int(rng.gauss(60, 15))
        midterm = max(0, min(100, midterm))
        dept = rng.choice(depts)
        score = 0.35 * study + 25 * attend + 0.5 * midterm + rng.gauss(0, 3)
        label = "pass" if score > 52 else "fail"
        rows.append([study, attend, sleep, midterm, dept, label])
    return rows


def text_sample() -> list:
    """ZH: 餐廳評論的情緒分類（正面／負面），中文為主、混一些英文。

    ZH: 用模板組句子：主題 × 正面說法 / 負面說法。字元層級的模型
        幾百句就學得到「好吃／難吃」「快／慢」這種字的傾向。

    @node scripts/make_training_samples.py::text_sample
    """
    rng = random.Random(20260102)
    subjects = ["這家店的牛肉麵", "今天的午餐", "他們的服務", "這間咖啡廳", "外送的披薩",
                "夜市的鹽酥雞", "早餐店的蛋餅", "這道甜點", "The ramen here", "This café"]
    positive = ["真的很好吃", "超乎期待", "份量很足又便宜", "服務很親切，會再來", "環境乾淨舒服",
                "等一下就上菜了", "是我吃過最好的", "值得推薦給朋友", "is amazing", "was worth every dollar"]
    negative = ["難吃到吃不完", "等了四十分鐘還沒來", "價格貴又小份", "服務態度很差", "桌子油膩膩的",
                "完全不推薦", "跟照片差太多", "吃完肚子不舒服", "was cold and bland", "is a waste of money"]
    rows = [["text", "label"]]
    for _ in range(240):
        s = rng.choice(subjects)
        if rng.random() < 0.5:
            rows.append([f"{s}{rng.choice(positive)}", "正面"])
        else:
            rows.append([f"{s}{rng.choice(negative)}", "負面"])
    return rows


def main() -> int:
    """@node scripts/make_training_samples.py::main"""
    _zip_with("students.csv", tabular_sample(), OUT / "tabular_classification.zip")
    _zip_with("reviews.csv", text_sample(), OUT / "text_classification.zip")
    for p in sorted(OUT.glob("*.zip")):
        print("  %-32s %6.1f KB" % (p.name, p.stat().st_size / 1024))
    return 0


if __name__ == "__main__":
    sys.exit(main())
