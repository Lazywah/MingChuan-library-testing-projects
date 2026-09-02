# -*- coding: utf-8 -*-
"""
貓狗分類範例 —— 你的第一個影像分類模型
========================================

怎麼跑（一步就好）：
    在這個檔案上按右鍵 → 「Run on GPU」
    （或 Ctrl+Shift+P → AI Base: Run on GPU）

接下來會發生什麼：
    1. 讀取旁邊的 cat_dog_data/（500 張貓、500 張狗，已經幫你準備好）
    2. 在學校的 GPU 上用「遷移學習」訓練（預設 5 輪，幾分鐘內完成）
    3. 訓練完把模型存成 cat_dog_model.pt，並列出「判斷錯的圖片」

看懂之後你可以改：
    EPOCHS（多練幾輪會不會更準？）、IMG_SIZE、BATCH_SIZE、
    或把 cat_dog_data/ 換成你自己的圖片（每個類別一個資料夾）。

-----------------------------------------------------------------------
ZH（維運注記）: 這份檔案由 code-server 映像的 entrypoint 在首次啟動時
    放進使用者的 ~/projects/。正本在
    infrastructure/base-images/code-server/samples/，改完要重建映像。
ZH: 資料集是 Microsoft "Kaggle Cats and Dogs Dataset" 的精選子集
    （各 500 張、縮到 224px），已通過 PIL 完整性檢查——原始包裡的
    壞圖（截斷/非 JPEG）在製作時就剔除了，這裡不需要再防。
ZH: 進度列印格式 `Epoch i/n` 是 gpu-worker 的 parse_progress 認得的，
    改掉會讓平台上的進度條靜默停住。
"""
import os
import sys
import time

import torch
import torch.nn as nn
from torch.utils.data import DataLoader, random_split
from torchvision import datasets, transforms

# ── 可以動手改的設定 ─────────────────────────────────────────────────
EPOCHS     = 5          # 訓練幾輪
IMG_SIZE   = 224        # 預訓練模型看的是 224px 的圖
BATCH_SIZE = 32
LR         = 0.001      # 學習率
VAL_SPLIT  = 0.2        # 留 20% 當驗證集（不參與訓練，用來檢驗真實實力）
SEED       = 42

# ZH: 訓練容器與 code-server 共用 /home/coder，資料就在裡面——依序找：
#     這個檔案旁邊 → ~/projects（entrypoint 放範例的地方）→ 工作目錄。
#     🔴 Run on GPU 走 heredoc（python3 -），__file__ 是 '<stdin>'，
#       dirname 會落在工作目錄而不是檔案位置 —— 所以不能只信 __file__，
#       實測踩過（E2E 第一輪就是這樣 failed 的）。
_cands = []
try:
    _cands.append(os.path.dirname(os.path.abspath(__file__)))
except NameError:
    pass
_cands += [os.path.expanduser("~/projects"), os.getcwd()]
HERE = next((c for c in _cands if os.path.isdir(os.path.join(c, "cat_dog_data"))), None)
if HERE is None:
    # ZH: 講清楚找過哪裡、去哪拿回來，而不是丟 FileNotFoundError 的堆疊。
    sys.exit(
        "找不到資料夾 cat_dog_data/（找過：%s）\n"
        "範例資料應該跟這個檔案放在一起。如果被刪掉了，"
        "重新啟動實驗室會自動補回來。" % "、".join(dict.fromkeys(_cands))
    )
DATA_DIR  = os.path.join(HERE, "cat_dog_data")
MODEL_OUT = os.path.join(HERE, "cat_dog_model.pt")

torch.manual_seed(SEED)
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
print("使用裝置：%s" % device)
if device.type == "cpu":
    print("（沒偵測到 GPU——照樣能跑，只是慢一些。）")

# ── 1. 讀資料 ────────────────────────────────────────────────────────
# ZH: ImageFolder 慣例：每個子資料夾是一個類別（cats/、dogs/）。
#     換成自己的資料時維持同一個版面即可。
# ZH: Normalize 的數字是 ImageNet 的平均/標準差 —— 預訓練模型當年就是
#     看這種「口味」的圖長大的，餵一樣口味它才發揮得出來。
tfm = transforms.Compose([
    transforms.Resize((IMG_SIZE, IMG_SIZE)),
    transforms.ToTensor(),
    transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
])
full = datasets.ImageFolder(DATA_DIR, transform=tfm)
n_val = max(1, int(len(full) * VAL_SPLIT))
train_set, val_set = random_split(
    full, [len(full) - n_val, n_val],
    generator=torch.Generator().manual_seed(SEED))
# ZH: num_workers=0（單程序載入）—— 資料才 1000 張小圖，多程序快不了多少，
#     卻要吃容器的共享記憶體（/dev/shm 不夠時 worker 直接 Bus error 死給你看，
#     E2E 實測踩過）。想開多程序請先確認容器的 --shm-size 夠大。
train_dl = DataLoader(train_set, batch_size=BATCH_SIZE, shuffle=True,  num_workers=0)
val_dl   = DataLoader(val_set,   batch_size=BATCH_SIZE, shuffle=False, num_workers=0)
print("類別：%s ｜ 訓練 %d 張、驗證 %d 張"
      % (full.classes, len(train_set), len(val_set)))

# ── 2. 遷移學習：借一個「已經會看圖」的模型來教 ─────────────────────
# ZH: ResNet18 在一百多萬張圖上練過，已經懂邊緣、毛髮、耳朵這些概念。
#     我們把它凍結（不動它學過的），只換掉最後一層、教它分貓狗 ——
#     1000 張圖就夠，幾輪就能到 95% 以上。這招叫「遷移學習」，
#     也是實務上最常見的起手式。
# ZH: 🔴 第一次跑會下載預訓練權重（約 45MB，存 ~/.cache 之後不再下載）。
#     若外網抓不到，退回從零訓練的小 CNN —— 能跑完但正確率會低很多，
#     訊息會講清楚，不讓人以為自己做錯了什麼。
from torchvision import models

try:
    base = models.resnet18(weights=models.ResNet18_Weights.DEFAULT)
    for p in base.parameters():
        p.requires_grad = False          # 凍結：只教最後一層
    base.fc = nn.Linear(base.fc.in_features, len(full.classes))
    model = base.to(device)
    trainable = model.fc.parameters()
    print("使用預訓練 ResNet18（遷移學習）")
except Exception as e:
    print("拿不到預訓練權重（%s）——退回從零訓練的小 CNN，正確率會低很多。" % e)
    model = nn.Sequential(
        nn.Conv2d(3, 32, 3, padding=1), nn.ReLU(), nn.MaxPool2d(2),
        nn.Conv2d(32, 64, 3, padding=1), nn.ReLU(), nn.MaxPool2d(2),
        nn.Conv2d(64, 128, 3, padding=1), nn.ReLU(), nn.MaxPool2d(2),
        nn.Flatten(),
        nn.Linear(128 * (IMG_SIZE // 8) ** 2, 64), nn.ReLU(), nn.Dropout(0.3),
        nn.Linear(64, len(full.classes)),
    ).to(device)
    trainable = model.parameters()
loss_fn = nn.CrossEntropyLoss()
opt = torch.optim.Adam(trainable, lr=LR)

# ── 3. 訓練 ──────────────────────────────────────────────────────────
for epoch in range(1, EPOCHS + 1):
    t0 = time.time()
    model.train()
    total = correct = 0
    for x, y in train_dl:
        x, y = x.to(device), y.to(device)
        opt.zero_grad()
        out = model(x)
        loss = loss_fn(out, y)
        loss.backward()
        opt.step()
        total += y.size(0)
        correct += (out.argmax(1) == y).sum().item()

    model.eval()
    v_total = v_correct = 0
    with torch.no_grad():
        for x, y in val_dl:
            x, y = x.to(device), y.to(device)
            v_total += y.size(0)
            v_correct += (model(x).argmax(1) == y).sum().item()

    # ZH: 「Epoch i/n」是平台進度條認得的格式，不要改字樣。
    print("Epoch %d/%d ｜ 訓練正確率 %.1f%% ｜ 驗證正確率 %.1f%% ｜ %.0f 秒"
          % (epoch, EPOCHS, 100.0 * correct / total,
             100.0 * v_correct / v_total, time.time() - t0), flush=True)

# ── 4. 存模型＋看看哪些判斷錯了 ─────────────────────────────────────
torch.save({"model": model.state_dict(),
            "classes": full.classes, "img_size": IMG_SIZE}, MODEL_OUT)
print("\n模型已存到 %s" % MODEL_OUT)

model.eval()
wrong = []
with torch.no_grad():
    for i in range(len(val_set)):
        x, y = val_set[i]
        pred = model(x.unsqueeze(0).to(device)).argmax(1).item()
        if pred != y:
            # ZH: random_split 的子集靠 .indices 對回原始 ImageFolder 的檔名。
            path = full.samples[val_set.indices[i]][0]
            wrong.append("  %s ｜ 正解 %s → 被判成 %s"
                         % (os.path.basename(path),
                            full.classes[y], full.classes[pred]))
print("驗證集裡判斷錯的（共 %d 張）：" % len(wrong))
print("\n".join(wrong[:20]) if wrong else "  一張都沒錯！")
if len(wrong) > 20:
    print("  …其餘 %d 張略。" % (len(wrong) - 20))

print("\n下一步：試著把 EPOCHS 改大、或把 cat_dog_data/ 換成你自己的圖片。")
