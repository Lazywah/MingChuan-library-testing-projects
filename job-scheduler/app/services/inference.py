"""
Service: 用剛訓練好的模型判斷一張圖（「上傳一張圖片試試看」）
==============================================================

ZH: v4.36（擁有者 2026-10-02，接管者回饋 2026-09-30 ①：「訓練完是否可以多一個測試的步驟」）。
    擁有者選的做法 (a)：**在服務層用 CPU 推論**，一次一張，不佔 GPU、不排隊。

ZH: 🔴 **只開放「平台內建程式訓練出來的圖片模型」**（crud.builtin_task_for == image_classification）。
    自帶程式（「用自己的程式」）產出的 model.pt 是使用者自己的程式寫出來的；
    torch 的模型檔格式本質上可以夾帶程式碼，服務層去載入它等於讓他在伺服器上執行任意程式。
    內建腳本存的格式是固定的（state_dict／classes／img_size／arch），
    而且一律用 `weights_only=True` 載入 —— 只接受張量與基本型別，夾帶的東西直接拒絕。
    兩道都要：任務種類擋掉自帶程式，weights_only 擋掉「萬一哪天內建腳本被換掉」。

ZH: 服務層是整個平台的入口，推論不能把它拖垮：
      · 同時最多 _MAX_CONCURRENT 個推論（其餘回「忙碌中，等一下再試」）
      · torch 只用 _TORCH_THREADS 條執行緒
      · 圖片大小與像素數都有上限（防解壓炸彈）
      · 模型留在記憶體裡（最近 _CACHE_SIZE 個），不要每張圖都從磁碟載 43 MB

ZH: ⚠ 前處理必須與 gpu-worker/builtin_scripts/image_classification.py 一致
    （Resize 成 img_size×img_size → ToTensor → ImageNet 的 Normalize）。那邊改了這裡要跟著改，
    不然判斷結果會靜靜地變差，而不會有任何錯誤訊息。

@node job-scheduler/app/services/inference.py
"""
import io
import logging
import os
import threading
from collections import OrderedDict

logger = logging.getLogger(__name__)

_MAX_CONCURRENT = 2
_TORCH_THREADS = 2
_CACHE_SIZE = 3
# ZH: 上傳的圖最大幾 MB、最多幾百萬像素。手機照片約 3–8 MB、1200 萬像素，都放得進來；
#     更大的通常是掃描檔或刻意的炸彈。
MAX_IMAGE_BYTES = 15 * 1024 * 1024
MAX_IMAGE_PIXELS = 40_000_000

_IMAGENET_MEAN = [0.485, 0.456, 0.406]
_IMAGENET_STD = [0.229, 0.224, 0.225]

_slots = threading.BoundedSemaphore(_MAX_CONCURRENT)
_cache_lock = threading.Lock()
_cache: "OrderedDict[tuple, tuple]" = OrderedDict()


class InferenceBusy(Exception):
    """ZH: 同時推論的名額滿了 —— 呼叫端回 503，請他等一下再試。"""


class InferenceRejected(Exception):
    """ZH: 這張圖或這個模型不能拿來推論（訊息是給使用者看的中英雙語）。"""


def _load_model(path: str):
    """ZH: 載入內建腳本存的 ResNet-18。回 (model, classes, img_size)。

    ZH: 用 (路徑, 修改時間) 當快取鍵 —— 同一張單重新上傳了模型檔就會重載，不會拿到舊的。

    @node job-scheduler/app/services/inference.py::_load_model
    """
    import torch
    from torch import nn
    from torchvision import models

    key = (path, os.path.getmtime(path))
    with _cache_lock:
        hit = _cache.get(key)
        if hit is not None:
            _cache.move_to_end(key)
            return hit

    # ZH: 🔴 weights_only=True —— 見檔頭。不要為了「載得進來」把它拿掉。
    ckpt = torch.load(path, map_location="cpu", weights_only=True)
    if not isinstance(ckpt, dict) or ckpt.get("arch") != "resnet18":
        raise InferenceRejected("ZH: 這個模型檔不是平台內建的圖片分類格式 | "
                                "EN: This model file is not the built-in image format")
    classes = [str(c) for c in ckpt.get("classes") or []]
    if len(classes) < 2:
        raise InferenceRejected("ZH: 模型檔裡沒有類別資訊 | EN: The model file has no classes")
    img_size = int(ckpt.get("img_size") or 224)

    model = models.resnet18(weights=None)
    model.fc = nn.Linear(model.fc.in_features, len(classes))
    model.load_state_dict(ckpt["state_dict"])
    model.eval()

    value = (model, classes, img_size)
    with _cache_lock:
        _cache[key] = value
        _cache.move_to_end(key)
        while len(_cache) > _CACHE_SIZE:
            _cache.popitem(last=False)
    return value


def _read_image(data: bytes):
    """ZH: bytes → RGB 的 PIL 圖。打不開、太大、像素太多一律 InferenceRejected。

    @node job-scheduler/app/services/inference.py::_read_image
    """
    from PIL import Image
    if len(data) > MAX_IMAGE_BYTES:
        raise InferenceRejected("ZH: 圖片太大（上限 15 MB）| EN: Image too large (max 15 MB)")
    try:
        img = Image.open(io.BytesIO(data))
        w, h = img.size
        if w * h > MAX_IMAGE_PIXELS:
            raise InferenceRejected("ZH: 圖片像素太多 | EN: Image has too many pixels")
        return img.convert("RGB")
    except InferenceRejected:
        raise
    except Exception:  # noqa: BLE001 - 任何打不開的東西對使用者來說都是同一件事
        raise InferenceRejected("ZH: 這個檔案打不開，請換一張 JPG 或 PNG | "
                                "EN: Could not open this file - try a JPG or PNG")


def predict_image(model_path: str, data: bytes) -> dict:
    """ZH: 用這個模型判斷這張圖。回 {"label", "confidence", "scores": [{"label","p"}...]}（由高到低）。

    @node job-scheduler/app/services/inference.py::predict_image
    """
    if not _slots.acquire(blocking=False):
        raise InferenceBusy()
    try:
        import torch
        from torchvision import transforms
        torch.set_num_threads(_TORCH_THREADS)
        img = _read_image(data)
        model, classes, img_size = _load_model(model_path)
        tf = transforms.Compose([
            transforms.Resize((img_size, img_size)),
            transforms.ToTensor(),
            transforms.Normalize(_IMAGENET_MEAN, _IMAGENET_STD),
        ])
        with torch.no_grad():
            probs = torch.softmax(model(tf(img).unsqueeze(0)), dim=1)[0].tolist()
        scores = sorted(({"label": c, "p": round(p, 4)} for c, p in zip(classes, probs)),
                        key=lambda s: -s["p"])
        return {"label": scores[0]["label"], "confidence": scores[0]["p"], "scores": scores}
    finally:
        _slots.release()
