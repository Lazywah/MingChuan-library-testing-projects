# -*- coding: utf-8 -*-
"""
ZH: 內建訓練腳本 —— 表格資料分類。使用者只要上傳一個 CSV 就能訓練，不必寫程式。

ZH: 資料版面：zip 裡放**一個 CSV**（有沒有多包一層資料夾都可以）。
    每一列是一筆資料，每一欄是一個特徵，**其中一欄是答案（類別）**：

        study_hours,attendance,sleep_hours,prior_score,label
        3.5,0.9,7,72,pass
        1.0,0.4,5,40,fail

    答案欄的判定順序：環境變數 LABEL_COLUMN → 名字叫 label / target / class / y /
    答案 / 類別 的欄 → **最後一欄**。文字欄位會自動轉成 one-hot，
    數值欄位會標準化 —— 使用者不需要先自己處理。

ZH: 這支腳本在**訓練容器**裡跑，看得到的路徑與慣例和 image_classification.py 完全一樣：
        DATASET_DIR / OUTPUT_DIR / EPOCHS / BATCH_SIZE / LEARNING_RATE
        進度靠印 `Epoch i/n`；指標靠 `@@METRIC {json}`；失敗印 `[錯誤]` / `[怎麼修]`。
    **改這些格式要一起改 gpu-worker/worker.py 的 parse_progress / parse_metric。**

ZH: 指標的欄位名刻意與圖片分類**相同**（classes / val_accuracy / best_val_accuracy），
    只是 `images` 換成 `samples` —— 前端據此決定要寫「張圖片」還是「筆資料」。

@node gpu-worker/builtin_scripts/tabular_classification.py
"""
import csv
import json
import os
import sys
import time

DATASET_DIR = os.environ.get("DATASET_DIR", "/workspace/dataset")
OUTPUT_DIR  = os.environ.get("OUTPUT_DIR", "/workspace/outputs")
EPOCHS      = int(os.environ.get("EPOCHS", "30"))
BATCH_SIZE  = int(os.environ.get("BATCH_SIZE", "32"))
LR          = float(os.environ.get("LEARNING_RATE", "0.001"))
VAL_SPLIT   = float(os.environ.get("VAL_SPLIT", "0.2"))
SEED        = int(os.environ.get("SEED", "42"))
LABEL_COLUMN = os.environ.get("LABEL_COLUMN", "").strip()

# ZH: 文字欄位的類別數超過這個就不做 one-hot（多半是 id 或姓名那種每列都不同的欄）。
MAX_ONEHOT = 50
# ZH: 答案欄的常見名字（不分大小寫）。找不到就用最後一欄。
LABEL_NAMES = ("label", "target", "class", "y", "答案", "類別", "標籤")

METRIC_PREFIX = "@@METRIC "


def metric(**kv) -> None:
    """@node gpu-worker/builtin_scripts/tabular_classification.py::metric"""
    print(METRIC_PREFIX + json.dumps(kv, ensure_ascii=False), flush=True)


def fail(msg: str, hint: str = "") -> None:
    """@node gpu-worker/builtin_scripts/tabular_classification.py::fail"""
    print(f"\n[錯誤] {msg}", flush=True)
    if hint:
        print(f"[怎麼修] {hint}", flush=True)
    sys.exit(1)


def find_csv(base: str) -> str:
    """ZH: 找到 zip 裡那一個 CSV。略過壓縮軟體與作業系統的雜物。

    ZH: 找到多個時用**最大**的那個並說出來 —— 使用者常會順手把一份小的說明檔
        或範例一起壓進去，那不該讓整個訓練失敗。

    @node gpu-worker/builtin_scripts/tabular_classification.py::find_csv
    """
    found = []
    for root, dirs, files in os.walk(base):
        dirs[:] = [d for d in dirs if d not in ("__MACOSX",)]
        for f in files:
            if f.lower().endswith(".csv") and not f.startswith("."):
                p = os.path.join(root, f)
                found.append((os.path.getsize(p), p))
    if not found:
        fail("zip 裡找不到任何 .csv 檔。",
             "請把資料存成 CSV（Excel 可用「另存新檔 → CSV UTF-8」），再壓成 zip 上傳。")
    found.sort(reverse=True)
    if len(found) > 1:
        print(f"找到 {len(found)} 個 CSV，用最大的那個：{os.path.relpath(found[0][1], base)}",
              flush=True)
    return found[0][1]


def read_rows(path: str):
    """ZH: 讀 CSV 成 (欄名, 列)。先試 UTF-8（含 BOM），不行再試 cp950 ——
        台灣的 Excel 存出來的 CSV 常是 cp950。

    @node gpu-worker/builtin_scripts/tabular_classification.py::read_rows
    """
    for enc in ("utf-8-sig", "cp950", "big5", "latin-1"):
        try:
            with open(path, "r", encoding=enc, newline="") as f:
                rows = list(csv.reader(f))
            break
        except UnicodeDecodeError:
            continue
    else:
        fail("CSV 的文字編碼讀不出來。", "請用 UTF-8 存檔（Excel：另存新檔 → CSV UTF-8）。")
    rows = [r for r in rows if any(c.strip() for c in r)]
    if len(rows) < 2:
        fail("CSV 裡沒有資料（只有標題列或是空的）。")
    header = [h.strip() for h in rows[0]]
    body = [r for r in rows[1:] if len(r) == len(header)]
    dropped = len(rows) - 1 - len(body)
    if dropped:
        print(f"[注意] 有 {dropped} 列的欄位數與標題列不同，已略過。", flush=True)
    return header, body


def pick_label_column(header) -> int:
    """ZH: 決定哪一欄是答案。順序：環境變數 → 常見名字 → 最後一欄。

    @node gpu-worker/builtin_scripts/tabular_classification.py::pick_label_column
    """
    if LABEL_COLUMN:
        for i, h in enumerate(header):
            if h == LABEL_COLUMN:
                return i
        fail(f"找不到你指定的答案欄「{LABEL_COLUMN}」。", f"CSV 的欄位是：{', '.join(header)}")
    lower = [h.lower() for h in header]
    for name in LABEL_NAMES:
        if name in lower:
            return lower.index(name)
    return len(header) - 1


def is_number(s: str) -> bool:
    """@node gpu-worker/builtin_scripts/tabular_classification.py::is_number"""
    try:
        float(s)
        return True
    except ValueError:
        return False


def build_features(header, body, label_idx):
    """ZH: 把每一列變成一排數字。數值欄照用；文字欄 one-hot；每列都不同的文字欄丟掉。

    ZH: 回傳 (特徵矩陣 list[list[float]], 特徵名稱 list, 標籤 list[str], 用不到的欄)。
        標準化留給呼叫端做 —— 平均與標準差要用**訓練集**算，不能偷看驗證集。

    @node gpu-worker/builtin_scripts/tabular_classification.py::build_features
    """
    feature_cols = [i for i in range(len(header)) if i != label_idx]
    numeric, onehot, skipped = [], {}, []
    for i in feature_cols:
        vals = [r[i].strip() for r in body]
        non_empty = [v for v in vals if v != ""]
        if non_empty and all(is_number(v) for v in non_empty):
            numeric.append(i)
        else:
            cats = sorted(set(non_empty))
            # ZH: 「每一列都不同」的文字欄（學號、姓名）不能學 —— 判準是
            #     不同值的數量**等於**列數，不是只看有沒有超過 MAX_ONEHOT：
            #     三列的小表格裡 id 也只有三種值，光看上限會把它 one-hot 進去。
            if 1 < len(cats) <= MAX_ONEHOT and len(cats) < len(non_empty):
                onehot[i] = cats
            else:
                skipped.append(header[i])

    names = [header[i] for i in numeric]
    for i, cats in onehot.items():
        names.extend(f"{header[i]}={c}" for c in cats)

    X, y = [], []
    for r in body:
        label = r[label_idx].strip()
        if label == "":
            continue
        row = []
        for i in numeric:
            v = r[i].strip()
            row.append(float(v) if v != "" else float("nan"))
        for i, cats in onehot.items():
            v = r[i].strip()
            row.extend(1.0 if v == c else 0.0 for c in cats)
        X.append(row)
        y.append(label)
    return X, names, y, skipped


def main() -> int:
    """@node gpu-worker/builtin_scripts/tabular_classification.py::main"""
    import torch
    import torch.nn as nn

    torch.manual_seed(SEED)

    print("=" * 60, flush=True)
    print("表格資料分類訓練 / Tabular classification", flush=True)
    print("=" * 60, flush=True)

    path = find_csv(DATASET_DIR)
    header, body = read_rows(path)
    label_idx = pick_label_column(header)
    print(f"答案欄 / Label column: {header[label_idx]}", flush=True)

    X, names, y, skipped = build_features(header, body, label_idx)
    if skipped:
        print(f"[注意] 這些欄位每列都不同（像 id 或姓名），不能拿來學，已略過：{', '.join(skipped)}",
              flush=True)
    if not names:
        fail("除了答案欄之外沒有可以學習的欄位。",
             "至少要有一欄數字或一欄可以分類的文字（例如 性別、科系）。")

    classes = sorted(set(y))
    n_total = len(X)
    print(f"類別 / Classes: {len(classes)} → {', '.join(classes)}", flush=True)
    print(f"資料筆數 / Rows: {n_total}　特徵數 / Features: {len(names)}", flush=True)
    if len(classes) < 2:
        fail(f"答案欄只有 {len(classes)} 種值，分不出東西。",
             "答案欄至少要有兩種不同的值（例如 pass / fail）。")
    if len(classes) > 100:
        fail(f"答案欄有 {len(classes)} 種不同的值，看起來不像類別。",
             "答案欄應該是有限的幾種類別；如果是要預測一個數字，這支腳本不適用。")
    if n_total < len(classes) * 5:
        fail(f"資料太少（{n_total} 筆 / {len(classes)} 類）。", "每個類別至少要有幾十筆才學得到東西。")

    # ZH: 缺值用該欄的中位數補。留 NaN 的話第一個 batch 就是 NaN loss。
    import math
    for j in range(len(names)):
        col = [row[j] for row in X if not math.isnan(row[j])]
        fill = sorted(col)[len(col) // 2] if col else 0.0
        for row in X:
            if math.isnan(row[j]):
                row[j] = fill

    cls_index = {c: i for i, c in enumerate(classes)}
    y_idx = [cls_index[v] for v in y]

    # ZH: 分層切驗證集 —— 類別少的那一類要保證兩邊都有，
    #     否則驗證正確率會在「那一類剛好全在訓練集」時虛高。
    try:
        from sklearn.model_selection import train_test_split
        tr_i, va_i = train_test_split(list(range(n_total)), test_size=VAL_SPLIT,
                                      random_state=SEED, stratify=y_idx)
    except Exception:
        import random
        idx = list(range(n_total))
        random.Random(SEED).shuffle(idx)
        n_val = max(1, int(n_total * VAL_SPLIT))
        va_i, tr_i = idx[:n_val], idx[n_val:]
    print(f"訓練 / train {len(tr_i)}　驗證 / validation {len(va_i)}", flush=True)
    metric(kind="dataset", classes=classes, samples=n_total, features=len(names),
           train_samples=len(tr_i), val_samples=len(va_i), epochs=EPOCHS)

    Xt = torch.tensor(X, dtype=torch.float32)
    yt = torch.tensor(y_idx, dtype=torch.long)
    mean = Xt[tr_i].mean(0)
    std = Xt[tr_i].std(0)
    std[std == 0] = 1.0
    Xt = (Xt - mean) / std

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    if device.type == "cpu":
        print("[注意] 沒有偵測到 GPU，改用 CPU 訓練（表格資料通常不大，還是很快）。", flush=True)
    else:
        print(f"GPU：{torch.cuda.get_device_name(0)}", flush=True)

    model = nn.Sequential(
        nn.Linear(len(names), 128), nn.ReLU(), nn.Dropout(0.1),
        nn.Linear(128, 64), nn.ReLU(),
        nn.Linear(64, len(classes)),
    ).to(device)
    criterion = nn.CrossEntropyLoss()
    optimizer = torch.optim.Adam(model.parameters(), lr=LR)

    Xtr, ytr = Xt[tr_i].to(device), yt[tr_i].to(device)
    Xva, yva = Xt[va_i].to(device), yt[va_i].to(device)
    bs = max(1, min(BATCH_SIZE, len(tr_i)))

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    best_acc = 0.0
    history = []
    t0 = time.time()
    g = torch.Generator(device="cpu").manual_seed(SEED)

    for epoch in range(1, EPOCHS + 1):
        print(f"Epoch {epoch}/{EPOCHS}", flush=True)
        model.train()
        perm = torch.randperm(len(tr_i), generator=g).to(device)
        run_loss = 0.0
        for s in range(0, len(tr_i), bs):
            b = perm[s:s + bs]
            optimizer.zero_grad()
            loss = criterion(model(Xtr[b]), ytr[b])
            loss.backward()
            optimizer.step()
            run_loss += loss.item() * len(b)
        train_loss = run_loss / len(tr_i)

        model.eval()
        with torch.no_grad():
            acc = (model(Xva).argmax(1) == yva).float().mean().item()
        history.append({"epoch": epoch, "train_loss": round(train_loss, 4),
                        "val_accuracy": round(acc, 4)})
        metric(kind="epoch", epoch=epoch, epochs=EPOCHS,
               train_loss=round(train_loss, 4), val_accuracy=round(acc, 4))
        print(f"  loss {train_loss:.4f} | 驗證正確率 / val accuracy {acc * 100:.1f}%", flush=True)

        if acc >= best_acc:
            best_acc = acc
            torch.save({"state_dict": model.state_dict(),
                        "classes": classes,
                        "features": names,
                        "mean": mean.tolist(), "std": std.tolist(),
                        "arch": "mlp"},
                       os.path.join(OUTPUT_DIR, "model.pt"))

    elapsed = time.time() - t0
    result = {
        "task": "tabular_classification",
        "classes": classes, "samples": n_total, "features": names,
        "train_samples": len(tr_i), "val_samples": len(va_i),
        "epochs": EPOCHS, "best_val_accuracy": round(best_acc, 4),
        "elapsed_seconds": round(elapsed, 1), "history": history,
    }
    with open(os.path.join(OUTPUT_DIR, "result.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    took = f"{elapsed:.0f} 秒" if elapsed < 60 else f"{elapsed / 60:.1f} 分鐘"
    metric(kind="summary", best_val_accuracy=round(best_acc, 4),
           elapsed_seconds=round(elapsed, 1), classes=classes, samples=n_total)
    print("=" * 60, flush=True)
    print(f"完成 / Done. 最佳驗證正確率 / best val accuracy {best_acc * 100:.1f}%"
          f"，花了 / took {took}。", flush=True)
    print(f"模型 / Model: {OUTPUT_DIR}/model.pt", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
