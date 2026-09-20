# -*- coding: utf-8 -*-
"""
表格資料分類範例 —— 用幾個數字預測「這個學生會不會及格」
==========================================================

怎麼跑（一步就好）：
    在這個檔案上按右鍵 → 「Run on GPU」
    （或 Ctrl+Shift+P → AI Base: Run on GPU）

接下來會發生什麼：
    1. 讀取旁邊的 students.csv（320 筆：讀書時數、出席率、睡眠、期中成績、科系 → 及格/不及格）
    2. 把文字欄（科系）轉成數字、把數字欄標準化，訓練一個小型神經網路（幾秒鐘）
    3. 印出驗證正確率、猜錯的那幾筆，並把模型存成 students_model.pt

看懂之後你可以改：
    EPOCHS、HIDDEN（隱藏層大小）、LR，
    或把 students.csv 換成你自己的表格 —— 只要「一列一筆、一欄一個特徵、
    其中一欄是答案（欄名 label，或放最後一欄）」就能用。

-----------------------------------------------------------------------
ZH（維運注記）: 這份檔案由服務層在「學習程式碼」選「表格」時放進使用者的
    ~/projects/（lab_manager.seed_sample）。正本在 job-scheduler/lab_samples/。
    students.csv 由 scripts/make_training_samples.py 產生（固定種子）。
ZH: 進度列印格式 `Epoch i/n` 是 gpu-worker 的 parse_progress 認得的，
    改掉會讓平台上的進度條靜默停住。
"""
import csv
import os
import sys
import time

import torch
import torch.nn as nn

# ── 可以動手改的設定 ─────────────────────────────────────────────────
EPOCHS    = 30
HIDDEN    = 64          # 隱藏層的神經元數
LR        = 0.001
VAL_SPLIT = 0.2         # 留 20% 當驗證集（不參與訓練，用來檢驗真實實力）
SEED      = 42
CSV_NAME  = "students.csv"
LABEL_COL = "label"     # 答案欄的名字；找不到就用最後一欄

# ZH: 訓練容器與 code-server 共用 /home/coder，資料就在裡面——依序找：
#     這個檔案旁邊 → ~/projects → 工作目錄。
#     🔴 Run on GPU 走 heredoc（python3 -），__file__ 是 '<stdin>'，
#        dirname 會落在工作目錄而不是檔案所在 —— 所以要多候選。
_cands = []
try:
    _cands.append(os.path.dirname(os.path.abspath(__file__)))
except NameError:
    pass
_cands += [os.path.expanduser("~/projects"), os.getcwd()]
HERE = next((c for c in _cands if os.path.isfile(os.path.join(c, CSV_NAME))), None)
if HERE is None:
    sys.exit("找不到 %s（找過：%s）\n範例資料應該跟這個檔案放在一起。"
             % (CSV_NAME, "、".join(dict.fromkeys(_cands))))
CSV_PATH  = os.path.join(HERE, CSV_NAME)
MODEL_OUT = os.path.join(HERE, "students_model.pt")

torch.manual_seed(SEED)
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
print("使用裝置：%s" % device)

# ── 1. 讀 CSV ────────────────────────────────────────────────────────
# ZH: 先試 UTF-8（含 BOM），不行再試 cp950 —— 台灣 Excel 存的 CSV 常是後者。
for enc in ("utf-8-sig", "cp950"):
    try:
        with open(CSV_PATH, encoding=enc, newline="") as f:
            rows = [r for r in csv.reader(f) if any(c.strip() for c in r)]
        break
    except UnicodeDecodeError:
        continue
header, body = rows[0], rows[1:]
label_idx = header.index(LABEL_COL) if LABEL_COL in header else len(header) - 1
print("欄位：%s（答案欄：%s）｜ %d 筆" % ("、".join(header), header[label_idx], len(body)))

# ── 2. 把每一列變成一排數字 ──────────────────────────────────────────
# ZH: 數值欄直接用；文字欄（像「科系」）做 one-hot：每一種值變成一個 0/1 的欄。
#     模型只認數字，這一步就是「翻譯」。
def is_number(s):
    try:
        float(s); return True
    except ValueError:
        return False

feature_idx = [i for i in range(len(header)) if i != label_idx]
numeric = [i for i in feature_idx if all(is_number(r[i]) for r in body if r[i].strip())]
onehot = {i: sorted({r[i].strip() for r in body}) for i in feature_idx if i not in numeric}
names = [header[i] for i in numeric] + ["%s=%s" % (header[i], c) for i in onehot for c in onehot[i]]

X, y_text = [], []
for r in body:
    row = [float(r[i]) if r[i].strip() else 0.0 for i in numeric]
    for i, cats in onehot.items():
        row += [1.0 if r[i].strip() == c else 0.0 for c in cats]
    X.append(row)
    y_text.append(r[label_idx].strip())
classes = sorted(set(y_text))
y = [classes.index(v) for v in y_text]
print("特徵 %d 個：%s" % (len(names), "、".join(names)))
print("類別：%s" % "、".join(classes))

# ── 3. 切訓練／驗證集、標準化 ────────────────────────────────────────
# ZH: 標準化＝每一欄減平均、除以標準差，讓「期中成績 0–100」和「出席率 0–1」
#     站在同一個尺度上，否則大數字的欄會把小數字的欄淹掉。
#     🔴 平均與標準差只能用**訓練集**算 —— 偷看驗證集會讓正確率虛高。
X = torch.tensor(X, dtype=torch.float32)
y = torch.tensor(y, dtype=torch.long)
g = torch.Generator().manual_seed(SEED)
perm = torch.randperm(len(X), generator=g)
n_val = int(len(X) * VAL_SPLIT)
va_i, tr_i = perm[:n_val], perm[n_val:]
mean, std = X[tr_i].mean(0), X[tr_i].std(0)
std[std == 0] = 1.0
X = (X - mean) / std
print("訓練 %d 筆 ｜ 驗證 %d 筆" % (len(tr_i), len(va_i)))

# ── 4. 模型：兩層的小型神經網路 ──────────────────────────────────────
model = nn.Sequential(
    nn.Linear(len(names), HIDDEN), nn.ReLU(),
    nn.Linear(HIDDEN, len(classes)),
).to(device)
opt = torch.optim.Adam(model.parameters(), lr=LR)
loss_fn = nn.CrossEntropyLoss()
Xtr, ytr, Xva, yva = X[tr_i].to(device), y[tr_i].to(device), X[va_i].to(device), y[va_i].to(device)

# ── 5. 訓練 ──────────────────────────────────────────────────────────
t0 = time.time()
for epoch in range(1, EPOCHS + 1):
    model.train()
    for s in range(0, len(tr_i), 32):
        xb, yb = Xtr[s:s + 32], ytr[s:s + 32]
        opt.zero_grad()
        loss = loss_fn(model(xb), yb)
        loss.backward()
        opt.step()
    model.eval()
    with torch.no_grad():
        acc = (model(Xva).argmax(1) == yva).float().mean().item()
    # ZH: 「Epoch i/n」是平台進度條認得的格式，不要改字樣。
    print("Epoch %d/%d ｜ 誤差 %.3f ｜ 驗證正確率 %.1f%% ｜ %.1f 秒"
          % (epoch, EPOCHS, loss.item(), acc * 100, time.time() - t0), flush=True)

# ── 6. 存模型＋看看猜錯了哪些 ────────────────────────────────────────
torch.save({"model": model.state_dict(), "features": names, "classes": classes,
            "mean": mean, "std": std}, MODEL_OUT)
print("\n模型已存到 %s" % MODEL_OUT)

with torch.no_grad():
    pred = model(Xva).argmax(1).cpu()
wrong = [(int(va_i[k]), int(pred[k])) for k in range(len(va_i)) if pred[k] != y[va_i[k]]]
print("驗證集裡猜錯的（共 %d 筆）：" % len(wrong))
for row_i, p in wrong[:15]:
    r = body[row_i]
    desc = "、".join("%s=%s" % (header[i], r[i]) for i in feature_idx)
    print("  第 %d 列 ｜ %s ｜ 正解 %s → 被判成 %s" % (row_i + 2, desc, r[label_idx], classes[p]))
if len(wrong) > 15:
    print("  …其餘 %d 筆略。" % (len(wrong) - 15))

print("\n下一步：把 EPOCHS 或 HIDDEN 改大看看正確率會不會變；"
      "或把 students.csv 換成你自己的表格。")
