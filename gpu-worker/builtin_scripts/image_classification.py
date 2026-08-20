# -*- coding: utf-8 -*-
"""
ZH: 內建訓練腳本 —— 圖片分類。使用者只要上傳一包分好類的圖片就能訓練，不必寫程式。

ZH: 資料版面（就是 gpu.html 上寫的「每個類別一個資料夾」）：

        dataset/
          cats/  a.jpg  b.jpg …
          dogs/  c.jpg  d.jpg …

    解壓後如果只有**一個**最外層資料夾（zip 常見的包一層），會自動往下鑽一層，
    使用者不必知道自己壓的時候有沒有多包一層。

ZH: 這支腳本在**訓練容器**裡跑，不是在 worker 裡。它看得到的路徑：
        DATASET_DIR   解壓好的資料（唯讀看待）
        OUTPUT_DIR    模型與結果要寫到這裡

ZH: 進度回報靠印出 `Epoch i/n` —— worker 的 parse_progress 認得這個格式，
    不需要額外的通訊管道。**改這行格式會讓進度條靜默停住**，要改請一起改
    gpu-worker/worker.py::parse_progress。

@node gpu-worker/builtin_scripts/image_classification.py
"""
import json
import os
import sys
import time

# ── 設定：全部從環境變數來，由 worker 注入 ──────────────────────────────
DATASET_DIR = os.environ.get("DATASET_DIR", "/workspace/dataset")
OUTPUT_DIR  = os.environ.get("OUTPUT_DIR", "/workspace/outputs")
EPOCHS      = int(os.environ.get("EPOCHS", "10"))
BATCH_SIZE  = int(os.environ.get("BATCH_SIZE", "16"))
LR          = float(os.environ.get("LEARNING_RATE", "0.001"))
# ZH: 驗證集比例。資料太少時會自動調整（見下）。
VAL_SPLIT   = float(os.environ.get("VAL_SPLIT", "0.2"))
SEED        = int(os.environ.get("SEED", "42"))

IMG_SIZE = 224


def fail(msg: str, hint: str = "") -> None:
    """ZH: 明確失敗。訊息是給**使用者**看的（會出現在任務日誌裡），所以講人話。

    @node gpu-worker/builtin_scripts/image_classification.py::fail
    """
    print(f"\n[錯誤] {msg}", flush=True)
    if hint:
        print(f"[怎麼修] {hint}", flush=True)
    sys.exit(1)


def find_data_root(base: str) -> str:
    """ZH: 找到真正放著「每類一個資料夾」的那一層。

    ZH: 為什麼需要：壓縮的時候多包一層是最常見的狀況（`my_data.zip` 解開是
        `my_data/cats/…` 而不是 `cats/…`）。與其要求使用者壓對，不如往下鑽。
        只有在「這一層剛好只有一個資料夾、且沒有圖片」時才鑽，避免把
        「只有一個類別」的合法資料集誤判。

    @node gpu-worker/builtin_scripts/image_classification.py::find_data_root
    """
    from torchvision.datasets.folder import IMG_EXTENSIONS

    cur = base
    for _ in range(4):                       # ZH: 最多鑽 4 層，防止怪異結構無限下探
        try:
            entries = sorted(os.listdir(cur))
        except OSError as e:
            fail(f"讀不到資料夾 {cur}：{e}")
        # ZH: 略過壓縮軟體與作業系統產生的雜物
        entries = [e for e in entries
                   if e not in ("__MACOSX", ".DS_Store", "Thumbs.db")]
        dirs  = [e for e in entries if os.path.isdir(os.path.join(cur, e))]
        files = [e for e in entries
                 if os.path.splitext(e)[1].lower() in IMG_EXTENSIONS]
        if len(dirs) == 1 and not files:
            cur = os.path.join(cur, dirs[0])
            continue
        return cur
    return cur


def main() -> int:
    """@node gpu-worker/builtin_scripts/image_classification.py::main"""
    import torch
    import torch.nn as nn
    from torch.utils.data import DataLoader, random_split
    from torchvision import datasets, models, transforms

    torch.manual_seed(SEED)

    print("=" * 60, flush=True)
    print("圖片分類訓練 / Image classification", flush=True)
    print("=" * 60, flush=True)

    root = find_data_root(DATASET_DIR)
    if root != DATASET_DIR:
        print(f"資料實際在：{os.path.relpath(root, DATASET_DIR)}/（自動往下找到的）", flush=True)

    tf = transforms.Compose([
        transforms.Resize((IMG_SIZE, IMG_SIZE)),
        transforms.ToTensor(),
        # ZH: ImageNet 的統計值——因為下面用的是 ImageNet 預訓練權重
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
    ])

    try:
        full = datasets.ImageFolder(root, transform=tf)
    except (FileNotFoundError, RuntimeError) as e:
        fail(f"這包資料看起來不是「每個類別一個資料夾」的格式：{e}",
             "請把同一類的圖片放進同一個資料夾，例如 cats/ 和 dogs/，再壓成 zip。")

    classes = full.classes
    n_total = len(full)
    print(f"類別：{len(classes)} 個 → {', '.join(classes)}", flush=True)
    print(f"圖片：{n_total} 張", flush=True)

    if len(classes) < 2:
        fail(f"只找到 {len(classes)} 個類別，分不出東西。",
             "至少要有兩個資料夾（兩個類別）才能訓練分類模型。")
    if n_total < len(classes) * 2:
        fail(f"圖片太少（{n_total} 張 / {len(classes)} 類）。",
             "每個類別至少放幾十張圖片，訓練出來才有意義。")

    # ZH: 切驗證集。資料很少時固定留 1 張以上，不要切出空的驗證集（會除以零）。
    n_val = max(1, int(n_total * VAL_SPLIT))
    n_val = min(n_val, n_total - 1)
    n_train = n_total - n_val
    train_set, val_set = random_split(
        full, [n_train, n_val], generator=torch.Generator().manual_seed(SEED))
    print(f"訓練 {n_train} 張 / 驗證 {n_val} 張", flush=True)

    bs = min(BATCH_SIZE, n_train)
    train_loader = DataLoader(train_set, batch_size=bs, shuffle=True, num_workers=2)
    val_loader   = DataLoader(val_set, batch_size=bs, shuffle=False, num_workers=2)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    if device.type == "cpu":
        # ZH: 不是致命錯誤，但要**說出來**——不然使用者只會覺得「怎麼這麼慢」。
        print("[注意] 沒有偵測到 GPU，改用 CPU 訓練，會慢很多。", flush=True)
    else:
        print(f"GPU：{torch.cuda.get_device_name(0)}", flush=True)

    # ZH: 用 ImageNet 預訓練的 ResNet-18 只換最後一層（transfer learning）。
    #     校園情境下資料通常只有幾百張，從頭訓練幾乎一定過擬合。
    # ZH: 把 torch 的權重快取指到共享儲存。不設的話它落在 `--rm` 的容器裡，
    #     **每一張單都重新下載 45 MB**；而且離線的 GPU 主機會直接失敗。
    #     指到共享儲存後只有第一次要外網。
    os.environ.setdefault("TORCH_HOME", "/workspace/.torch")
    try:
        model = models.resnet18(weights=models.ResNet18_Weights.DEFAULT)
    except Exception as e:
        fail(f"取不到 ResNet-18 的預訓練權重：{e}",
             "這台機器第一次跑需要連得到 download.pytorch.org。"
             "下載過一次之後就會用共享儲存裡的快取，不必再連外網。")
    model.fc = nn.Linear(model.fc.in_features, len(classes))
    model = model.to(device)

    criterion = nn.CrossEntropyLoss()
    optimizer = torch.optim.Adam(model.parameters(), lr=LR)

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    best_acc = 0.0
    history = []
    t0 = time.time()

    for epoch in range(1, EPOCHS + 1):
        # ZH: 這一行的格式 worker 會解析成進度條，不要改（見檔頭）。
        print(f"Epoch {epoch}/{EPOCHS}", flush=True)

        model.train()
        run_loss = 0.0
        for x, y in train_loader:
            x, y = x.to(device), y.to(device)
            optimizer.zero_grad()
            loss = criterion(model(x), y)
            loss.backward()
            optimizer.step()
            run_loss += loss.item() * x.size(0)
        train_loss = run_loss / max(1, n_train)

        model.eval()
        correct = 0
        with torch.no_grad():
            for x, y in val_loader:
                x, y = x.to(device), y.to(device)
                correct += (model(x).argmax(1) == y).sum().item()
        acc = correct / max(1, n_val)
        history.append({"epoch": epoch, "train_loss": round(train_loss, 4),
                        "val_accuracy": round(acc, 4)})
        print(f"  loss {train_loss:.4f} | 驗證正確率 {acc * 100:.1f}%", flush=True)

        if acc >= best_acc:
            best_acc = acc
            torch.save({"state_dict": model.state_dict(),
                        "classes": classes,
                        "img_size": IMG_SIZE,
                        "arch": "resnet18"},
                       os.path.join(OUTPUT_DIR, "model.pt"))

    elapsed = time.time() - t0
    result = {
        "task": "image_classification",
        "classes": classes,
        "images": n_total,
        "train_images": n_train,
        "val_images": n_val,
        "epochs": EPOCHS,
        "best_val_accuracy": round(best_acc, 4),
        "elapsed_seconds": round(elapsed, 1),
        "history": history,
    }
    with open(os.path.join(OUTPUT_DIR, "result.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    # ZH: 不到一分鐘就寫秒——「花了 0.0 分鐘」看起來像壞掉了。
    took = f"{elapsed:.0f} 秒" if elapsed < 60 else f"{elapsed / 60:.1f} 分鐘"
    print("=" * 60, flush=True)
    print(f"完成。最佳驗證正確率 {best_acc * 100:.1f}%，花了 {took}。", flush=True)
    print(f"模型：{OUTPUT_DIR}/model.pt", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
