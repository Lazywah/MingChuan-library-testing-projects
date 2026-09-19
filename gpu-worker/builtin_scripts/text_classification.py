# -*- coding: utf-8 -*-
"""
ZH: 內建訓練腳本 —— 文字分類（例如：這句評論是正面還是負面）。
    使用者只要上傳一個 CSV 就能訓練，不必寫程式，**也不需要下載任何預訓練模型**。

ZH: 資料版面：zip 裡放**一個 CSV**，一欄是句子、一欄是答案：

        text,label
        這家店的服務很好，會再來,正面
        等了四十分鐘餐還沒來,負面

    文字欄的判定：環境變數 TEXT_COLUMN → 名字叫 text / sentence / content / 句子 /
    內容 / 評論 的欄 → **第一個不是答案欄的欄**。答案欄同表格分類的規則。

ZH: 為什麼不用預訓練語言模型：那要下載幾百 MB 的權重，離線的 GPU 主機會直接失敗，
    而這一頁是給「不會寫程式的人 20 分鐘做出一個模型」用的。
    這裡用**字元層級**的斷詞 —— 中文一個字一個 token，英文一個單字一個 token ——
    什麼都不用下載，中英文都能跑，幾百句就學得到明顯的規律。
    要做到最好的準確率，該去程式實驗室用 transformers。

ZH: 慣例（進度 `Epoch i/n`、指標 `@@METRIC`、失敗 `[錯誤]`）與其他內建腳本相同；
    改格式要一起改 gpu-worker/worker.py。指標欄位與圖片分類相同，`images` 換成 `samples`。

@node gpu-worker/builtin_scripts/text_classification.py
"""
import csv
import json
import os
import re
import sys
import time
from collections import Counter

DATASET_DIR = os.environ.get("DATASET_DIR", "/workspace/dataset")
OUTPUT_DIR  = os.environ.get("OUTPUT_DIR", "/workspace/outputs")
EPOCHS      = int(os.environ.get("EPOCHS", "20"))
BATCH_SIZE  = int(os.environ.get("BATCH_SIZE", "32"))
LR          = float(os.environ.get("LEARNING_RATE", "0.002"))
VAL_SPLIT   = float(os.environ.get("VAL_SPLIT", "0.2"))
SEED        = int(os.environ.get("SEED", "42"))
LABEL_COLUMN = os.environ.get("LABEL_COLUMN", "").strip()
TEXT_COLUMN  = os.environ.get("TEXT_COLUMN", "").strip()

LABEL_NAMES = ("label", "target", "class", "y", "答案", "類別", "標籤", "sentiment")
TEXT_NAMES  = ("text", "sentence", "content", "review", "句子", "內容", "評論", "文字")
MAX_VOCAB   = 50000
EMBED_DIM   = 64
# ZH: 保留給 padding 與沒看過的 token。
PAD, UNK = 0, 1

METRIC_PREFIX = "@@METRIC "

# ZH: 斷詞規則：一串英數字算一個 token（英文單字），其餘**每個字元**一個 token（中文）。
#     空白與標點丟掉。這樣中英混合的句子也能處理，而且不用任何字典。
_TOKEN_RE = re.compile(r"[A-Za-z0-9]+|[^\sA-Za-z0-9\W_]", re.UNICODE)


def metric(**kv) -> None:
    """@node gpu-worker/builtin_scripts/text_classification.py::metric"""
    print(METRIC_PREFIX + json.dumps(kv, ensure_ascii=False), flush=True)


def fail(msg: str, hint: str = "") -> None:
    """@node gpu-worker/builtin_scripts/text_classification.py::fail"""
    print(f"\n[錯誤] {msg}", flush=True)
    if hint:
        print(f"[怎麼修] {hint}", flush=True)
    sys.exit(1)


def tokenize(text: str):
    """ZH: 句子 → token 清單。英文轉小寫；中文逐字。

    @node gpu-worker/builtin_scripts/text_classification.py::tokenize
    """
    return [t.lower() for t in _TOKEN_RE.findall(text or "")]


def find_csv(base: str) -> str:
    """@node gpu-worker/builtin_scripts/text_classification.py::find_csv"""
    found = []
    for root, dirs, files in os.walk(base):
        dirs[:] = [d for d in dirs if d not in ("__MACOSX",)]
        for f in files:
            if f.lower().endswith(".csv") and not f.startswith("."):
                p = os.path.join(root, f)
                found.append((os.path.getsize(p), p))
    if not found:
        fail("zip 裡找不到任何 .csv 檔。",
             "請把資料存成 CSV（兩欄：句子、答案），再壓成 zip 上傳。")
    found.sort(reverse=True)
    if len(found) > 1:
        print(f"找到 {len(found)} 個 CSV，用最大的那個：{os.path.relpath(found[0][1], base)}",
              flush=True)
    return found[0][1]


def read_rows(path: str):
    """@node gpu-worker/builtin_scripts/text_classification.py::read_rows"""
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
    return header, body


def pick_columns(header):
    """ZH: 決定 (文字欄, 答案欄) 的索引。

    @node gpu-worker/builtin_scripts/text_classification.py::pick_columns
    """
    lower = [h.lower() for h in header]

    if LABEL_COLUMN:
        if LABEL_COLUMN not in header:
            fail(f"找不到你指定的答案欄「{LABEL_COLUMN}」。", f"CSV 的欄位是：{', '.join(header)}")
        label = header.index(LABEL_COLUMN)
    else:
        label = next((lower.index(n) for n in LABEL_NAMES if n in lower), len(header) - 1)

    if TEXT_COLUMN:
        if TEXT_COLUMN not in header:
            fail(f"找不到你指定的文字欄「{TEXT_COLUMN}」。", f"CSV 的欄位是：{', '.join(header)}")
        text = header.index(TEXT_COLUMN)
    else:
        text = next((lower.index(n) for n in TEXT_NAMES if n in lower and lower.index(n) != label),
                    next((i for i in range(len(header)) if i != label), None))
    if text is None or text == label:
        fail("CSV 至少要有兩欄：一欄句子、一欄答案。")
    return text, label


def main() -> int:
    """@node gpu-worker/builtin_scripts/text_classification.py::main"""
    import torch
    import torch.nn as nn

    torch.manual_seed(SEED)

    print("=" * 60, flush=True)
    print("文字分類訓練 / Text classification", flush=True)
    print("=" * 60, flush=True)

    path = find_csv(DATASET_DIR)
    header, body = read_rows(path)
    ti, li = pick_columns(header)
    print(f"文字欄 / Text column: {header[ti]}　答案欄 / Label column: {header[li]}", flush=True)

    texts, labels = [], []
    for r in body:
        t, l = r[ti].strip(), r[li].strip()
        if t and l:
            texts.append(t)
            labels.append(l)

    classes = sorted(set(labels))
    n_total = len(texts)
    print(f"類別 / Classes: {len(classes)} → {', '.join(classes)}", flush=True)
    print(f"句子數 / Sentences: {n_total}", flush=True)
    if len(classes) < 2:
        fail(f"答案欄只有 {len(classes)} 種值，分不出東西。", "答案欄至少要有兩種不同的值。")
    if len(classes) > 100:
        fail(f"答案欄有 {len(classes)} 種不同的值，看起來不像類別。")
    if n_total < len(classes) * 5:
        fail(f"句子太少（{n_total} 句 / {len(classes)} 類）。", "每個類別至少要有幾十句才學得到東西。")

    tokens = [tokenize(t) for t in texts]
    empty = sum(1 for tk in tokens if not tk)
    if empty:
        print(f"[注意] 有 {empty} 句斷詞之後是空的（只有標點或空白），已略過。", flush=True)
    keep = [i for i, tk in enumerate(tokens) if tk]
    tokens = [tokens[i] for i in keep]
    labels = [labels[i] for i in keep]
    n_total = len(tokens)

    cls_index = {c: i for i, c in enumerate(classes)}
    y_idx = [cls_index[v] for v in labels]

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

    # ZH: 字典只用**訓練集**建 —— 用全部建的話驗證正確率會虛高（偷看到了答案那邊的字）。
    counter = Counter(t for i in tr_i for t in tokens[i])
    vocab = {"<pad>": PAD, "<unk>": UNK}
    for tok, _ in counter.most_common(MAX_VOCAB - 2):
        vocab[tok] = len(vocab)
    print(f"訓練 / train {len(tr_i)}　驗證 / validation {len(va_i)}　字典 / vocab {len(vocab)}",
          flush=True)
    metric(kind="dataset", classes=classes, samples=n_total, vocab=len(vocab),
           train_samples=len(tr_i), val_samples=len(va_i), epochs=EPOCHS)

    def encode(idx_list):
        """ZH: 變成 EmbeddingBag 要的 (flat, offsets)。"""
        flat, offsets = [], []
        for i in idx_list:
            offsets.append(len(flat))
            flat.extend(vocab.get(t, UNK) for t in tokens[i])
        return torch.tensor(flat, dtype=torch.long), torch.tensor(offsets, dtype=torch.long)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    if device.type == "cpu":
        print("[注意] 沒有偵測到 GPU，改用 CPU 訓練。", flush=True)
    else:
        print(f"GPU：{torch.cuda.get_device_name(0)}", flush=True)

    class BagClassifier(nn.Module):
        """ZH: 詞袋模型：把句子裡每個 token 的向量取平均，再接一層分類。"""
        def __init__(self, vocab_size, dim, n_classes):
            super().__init__()
            self.emb = nn.EmbeddingBag(vocab_size, dim, mode="mean", padding_idx=PAD)
            self.head = nn.Sequential(nn.Linear(dim, 64), nn.ReLU(), nn.Dropout(0.2),
                                      nn.Linear(64, n_classes))

        def forward(self, flat, offsets):
            return self.head(self.emb(flat, offsets))

    model = BagClassifier(len(vocab), EMBED_DIM, len(classes)).to(device)
    criterion = nn.CrossEntropyLoss()
    optimizer = torch.optim.Adam(model.parameters(), lr=LR)

    yt = torch.tensor(y_idx, dtype=torch.long)
    va_flat, va_off = encode(va_i)
    va_flat, va_off, yva = va_flat.to(device), va_off.to(device), yt[va_i].to(device)
    bs = max(1, min(BATCH_SIZE, len(tr_i)))

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    best_acc = 0.0
    history = []
    t0 = time.time()
    import random as _rnd
    rng = _rnd.Random(SEED)

    for epoch in range(1, EPOCHS + 1):
        print(f"Epoch {epoch}/{EPOCHS}", flush=True)
        model.train()
        order = list(tr_i)
        rng.shuffle(order)
        run_loss = 0.0
        for s in range(0, len(order), bs):
            batch = order[s:s + bs]
            flat, off = encode(batch)
            flat, off = flat.to(device), off.to(device)
            yb = yt[batch].to(device)
            optimizer.zero_grad()
            loss = criterion(model(flat, off), yb)
            loss.backward()
            optimizer.step()
            run_loss += loss.item() * len(batch)
        train_loss = run_loss / len(tr_i)

        model.eval()
        with torch.no_grad():
            acc = (model(va_flat, va_off).argmax(1) == yva).float().mean().item()
        history.append({"epoch": epoch, "train_loss": round(train_loss, 4),
                        "val_accuracy": round(acc, 4)})
        metric(kind="epoch", epoch=epoch, epochs=EPOCHS,
               train_loss=round(train_loss, 4), val_accuracy=round(acc, 4))
        print(f"  loss {train_loss:.4f} | 驗證正確率 / val accuracy {acc * 100:.1f}%", flush=True)

        if acc >= best_acc:
            best_acc = acc
            torch.save({"state_dict": model.state_dict(),
                        "classes": classes, "vocab": vocab,
                        "embed_dim": EMBED_DIM, "arch": "embedding_bag"},
                       os.path.join(OUTPUT_DIR, "model.pt"))

    elapsed = time.time() - t0
    result = {
        "task": "text_classification",
        "classes": classes, "samples": n_total, "vocab": len(vocab),
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
