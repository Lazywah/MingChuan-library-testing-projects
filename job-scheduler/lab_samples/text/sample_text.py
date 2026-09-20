# -*- coding: utf-8 -*-
"""
文字分類範例 —— 判斷一句評論是正面還是負面
================================================

怎麼跑（一步就好）：
    在這個檔案上按右鍵 → 「Run on GPU」
    （或 Ctrl+Shift+P → AI Base: Run on GPU）

接下來會發生什麼：
    1. 讀取旁邊的 reviews.csv（240 句餐廳評論，每句標了 正面／負面）
    2. 把句子切成一個一個「字」（中文逐字、英文逐個單字），每個字學一個向量，
       整句取平均後接一層分類 —— 這叫「詞袋模型」，幾秒鐘就能訓練
    3. 印出驗證正確率、猜錯的那幾句，並把模型存成 reviews_model.pt，
       最後拿幾句新的句子試試看

看懂之後你可以改：
    EPOCHS、EMBED_DIM（每個字的向量長度）、TRY_SENTENCES（自己寫幾句來試），
    或把 reviews.csv 換成你自己的資料 —— 兩欄：text、label。

為什麼不用 BERT 之類的大模型：那要先下載幾百 MB 的權重，而這裡要的是
「幾百句、幾秒鐘、看得懂每一行」。學會這個之後再去用 transformers 才知道它替你做了什麼。

-----------------------------------------------------------------------
ZH（維運注記）: 這份檔案由服務層在「學習程式碼」選「文字」時放進使用者的
    ~/projects/（lab_manager.seed_sample）。正本在 job-scheduler/lab_samples/。
    reviews.csv 由 scripts/make_training_samples.py 產生（固定種子）。
ZH: 進度列印格式 `Epoch i/n` 是 gpu-worker 的 parse_progress 認得的。
"""
import csv
import os
import re
import sys
import time
from collections import Counter

import torch
import torch.nn as nn

# ── 可以動手改的設定 ─────────────────────────────────────────────────
EPOCHS    = 20
EMBED_DIM = 32
LR        = 0.005
VAL_SPLIT = 0.2
SEED      = 42
CSV_NAME  = "reviews.csv"
TRY_SENTENCES = ["這家的湯頭真的很棒，會再來", "等了一小時，餐點還是冷的", "The dessert was amazing"]

_cands = []
try:
    _cands.append(os.path.dirname(os.path.abspath(__file__)))
except NameError:
    pass
_cands += [os.path.expanduser("~/projects"), os.getcwd()]
HERE = next((c for c in _cands if os.path.isfile(os.path.join(c, CSV_NAME))), None)
if HERE is None:
    sys.exit("找不到 %s（找過：%s）" % (CSV_NAME, "、".join(dict.fromkeys(_cands))))
CSV_PATH  = os.path.join(HERE, CSV_NAME)
MODEL_OUT = os.path.join(HERE, "reviews_model.pt")

torch.manual_seed(SEED)
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
print("使用裝置：%s" % device)

# ── 1. 讀 CSV（兩欄：text, label）────────────────────────────────────
for enc in ("utf-8-sig", "cp950"):
    try:
        with open(CSV_PATH, encoding=enc, newline="") as f:
            rows = [r for r in csv.reader(f) if any(c.strip() for c in r)]
        break
    except UnicodeDecodeError:
        continue
header, body = rows[0], rows[1:]
ti = header.index("text") if "text" in header else 0
li = header.index("label") if "label" in header else len(header) - 1
texts  = [r[ti].strip() for r in body]
labels = [r[li].strip() for r in body]
classes = sorted(set(labels))
print("%d 句 ｜ 類別：%s" % (len(texts), "、".join(classes)))

# ── 2. 斷詞：中文逐字、英文逐單字 ───────────────────────────────────
# ZH: 一串英數字算一個 token（單字），其他每個字元一個 token（中文字）。
#     空白與標點丟掉。不用任何字典，中英混合也能處理。
TOKEN_RE = re.compile(r"[A-Za-z0-9]+|[^\sA-Za-z0-9\W_]")
def tokenize(s):
    return [t.lower() for t in TOKEN_RE.findall(s)]
tokens = [tokenize(t) for t in texts]
print("例：「%s」→ %s" % (texts[0], " / ".join(tokens[0])))

# ── 3. 切訓練／驗證集，只用訓練集建字典 ─────────────────────────────
# ZH: 🔴 字典若用全部句子建，驗證正確率會虛高（等於先偷看了答案那邊的字）。
g = torch.Generator().manual_seed(SEED)
perm = torch.randperm(len(texts), generator=g).tolist()
n_val = int(len(texts) * VAL_SPLIT)
va_i, tr_i = perm[:n_val], perm[n_val:]
counter = Counter(t for i in tr_i for t in tokens[i])
vocab = {"<pad>": 0, "<unk>": 1}
for tok, _ in counter.most_common():
    vocab[tok] = len(vocab)
print("訓練 %d 句 ｜ 驗證 %d 句 ｜ 字典 %d 個字" % (len(tr_i), len(va_i), len(vocab)))

y = torch.tensor([classes.index(v) for v in labels], dtype=torch.long)

def encode(idx_list):
    """ZH: 把幾句話攤平成一長串 id，再記每句從哪裡開始（EmbeddingBag 要的格式）。"""
    flat, offsets = [], []
    for i in idx_list:
        offsets.append(len(flat))
        flat += [vocab.get(t, 1) for t in tokens[i]] or [1]
    return torch.tensor(flat).to(device), torch.tensor(offsets).to(device)

# ── 4. 模型：每個字一個向量 → 整句取平均 → 分類 ──────────────────────
class BagOfWords(nn.Module):
    def __init__(self):
        super().__init__()
        self.emb = nn.EmbeddingBag(len(vocab), EMBED_DIM, mode="mean")
        self.out = nn.Linear(EMBED_DIM, len(classes))
    def forward(self, flat, offsets):
        return self.out(self.emb(flat, offsets))

model = BagOfWords().to(device)
opt = torch.optim.Adam(model.parameters(), lr=LR)
loss_fn = nn.CrossEntropyLoss()
va_flat, va_off = encode(va_i)
yva = y[va_i].to(device)

# ── 5. 訓練 ──────────────────────────────────────────────────────────
t0 = time.time()
for epoch in range(1, EPOCHS + 1):
    model.train()
    order = tr_i[:]
    torch.manual_seed(SEED + epoch)
    order = [order[k] for k in torch.randperm(len(order)).tolist()]
    for s in range(0, len(order), 32):
        batch = order[s:s + 32]
        flat, off = encode(batch)
        opt.zero_grad()
        loss = loss_fn(model(flat, off), y[batch].to(device))
        loss.backward()
        opt.step()
    model.eval()
    with torch.no_grad():
        acc = (model(va_flat, va_off).argmax(1) == yva).float().mean().item()
    print("Epoch %d/%d ｜ 誤差 %.3f ｜ 驗證正確率 %.1f%% ｜ %.1f 秒"
          % (epoch, EPOCHS, loss.item(), acc * 100, time.time() - t0), flush=True)

# ── 6. 存模型、看猜錯的、試幾句新的 ─────────────────────────────────
torch.save({"model": model.state_dict(), "vocab": vocab, "classes": classes,
            "embed_dim": EMBED_DIM}, MODEL_OUT)
print("\n模型已存到 %s" % MODEL_OUT)

with torch.no_grad():
    pred = model(va_flat, va_off).argmax(1).cpu()
wrong = [(va_i[k], int(pred[k])) for k in range(len(va_i)) if pred[k] != y[va_i[k]]]
print("驗證集裡猜錯的（共 %d 句）：" % len(wrong))
for i, p in wrong[:15]:
    print("  「%s」｜ 正解 %s → 被判成 %s" % (texts[i], labels[i], classes[p]))
if not wrong:
    print("  一句都沒錯！")

print("\n拿新句子試試看：")
with torch.no_grad():
    for s in TRY_SENTENCES:
        ids = [vocab.get(t, 1) for t in tokenize(s)] or [1]
        out = model(torch.tensor(ids).to(device), torch.tensor([0]).to(device))
        prob = torch.softmax(out, 1)[0]
        k = int(prob.argmax())
        print("  「%s」→ %s（%.0f%%）" % (s, classes[k], prob[k] * 100))
print("  猜錯了？把握度只有五六成？多半是因為那句話裡的字在訓練資料裡沒出現過 ——")
print("  模型只認得它看過的字。這正是「資料量」的意義：240 句只夠學到明顯的規律。")

print("\n下一步：改 TRY_SENTENCES 寫幾句自己的話；或把 reviews.csv 換成你自己的資料。")
