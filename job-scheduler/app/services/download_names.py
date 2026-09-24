# -*- coding: utf-8 -*-
"""
ZH: 下載檔名的清理與 Content-Disposition 組裝 —— **唯一的一份實作**。

ZH: 為什麼獨立成一支：模型檔（/jobs/{id}/model）與資料集
    （/datasets/{id}/download）都要「檔名帶著使用者取的名字、但那是使用者
    輸入的字串」。同一條規則寫兩份的話，日後補一個邊界只會補到其中一份，
    而另外一份看起來仍然正常（v4.24 下載那次就是這樣，四份實作）。

ZH: 規則（與 jobs.py 原本那段逐字相同，只是搬過來）：
      · 路徑分隔符、`..`、控制字元一律換掉 —— 百分比編碼**不算清理**
        （`../..` 只是變成 `..%2F..`）
      · 兩段一起送（RFC 5987）：
          filename=   純 ASCII 的保守版本，老瀏覽器看這個
          filename*=  UTF-8 百分比編碼，保住原本的中文名
        ⚠ 只給 filename= 的話中文會被清成空字串，每個人下載到的都叫 model.pt
        （實測踩過：任務叫「下載測試」，下載下來是 model.pt）。

@node job-scheduler/app/services/download_names.py
"""
import re
import urllib.parse


def safe_stem(raw: str, fallback: str) -> str:
    """ZH: 把使用者輸入的名字清成可以放進檔名的主檔名（保留中文）。

    @node job-scheduler/app/services/download_names.py::safe_stem
    """
    s = (raw or "").strip()
    s = re.sub(r'[\x00-\x1f\x7f/\\:*?"<>|]', "_", s)   # 路徑與控制字元
    s = re.sub(r"\.{2,}", "_", s).strip("._ ")
    return s or fallback


def content_disposition(raw_name: str, ext: str, fallback: str = "download") -> str:
    """ZH: 回 `attachment; filename="…"; filename*=UTF-8''…`。

    ZH: `ext` 是**呼叫端決定**的副檔名（`.pt` / `.zip`），不從 raw_name 猜 ——
        副檔名決定的是「這是什麼檔」，那不該由使用者輸入的字串說了算。

    @node job-scheduler/app/services/download_names.py::content_disposition
    """
    stem = safe_stem(raw_name, fallback)
    ascii_safe = re.sub(r"[^A-Za-z0-9._-]", "_", stem).strip("._-") or fallback
    encoded = urllib.parse.quote(f"{stem}{ext}", safe="")
    return f"attachment; filename=\"{ascii_safe}{ext}\"; filename*=UTF-8''{encoded}"
