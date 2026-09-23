"""
==============================================================================
Service: 程式實驗室的 per-user 網路 | Per-user lab networks
==============================================================================
ZH: 為什麼有這支（v4.24，原 v2.2 主項目）：
    所有 lab 容器原本都掛在同一個 `ai-platform-net` 上，於是**學生 A 可以從
    自己的容器連到學生 B 的 code-server**（`curl http://cs-<對方 uuid>:8080`）。
    威脅不高（要知道對方的 uuid 而且刻意為之），但它是真的。

ZH: 做法：每個使用者一個 bridge 網路 `aibase-lab-<uid 前 12 碼>`，
    lab 容器只掛在那上面。**另外把 nginx 與服務層連進去**，因為：
      · nginx 要 proxy `/code/<uid>/` → `cs-<uid>:8080`（不連就是 502）
      · 容器裡的 VS Code extension 要打 `http://job-scheduler:8000`
        （送訓練、心跳、查節點）
    兩個人各自的網路是分開的，所以 A 看得到 nginx 與服務層，**看不到 B**。

ZH: 🔴 **連服務層時一定要帶 alias `job-scheduler`。**
    compose 的服務名只在 compose 自己建的網路上有效；手動 connect 進來的話，
    預設只有容器名（`ai-platform-scheduler`）解得到。少了這個 alias 的症狀是
    「實驗室開得起來、但 Run on GPU 與心跳全部失敗」——而且**只在隔離開啟後**發生。

ZH: ⚠ **Docker 預設位址池大約只切得出 31 個 /16 bridge 網路。**
    同時開著的實驗室超過這個數字就會建不出網路（`could not find an available
    IP address pool`）。這支遇到那個錯誤會**明確講出來**，不會安靜失敗。
    台北 30 台上線、或要同時開超過 30 個實驗室時，要改 daemon 的
    `default-address-pools` 或改用 overlay。

ZH: ⚠ 這整件事由設定 `lab_network_isolation` 控制，**預設是關的**。
    開啟只影響**之後**啟動的實驗室；已經開著的那些維持原樣（它們在舊網路上）。

@node job-scheduler/app/services/network_manager.py
==============================================================================
"""

from __future__ import annotations

import logging
from typing import Optional

from docker.errors import APIError, NotFound

logger = logging.getLogger(__name__)

# ZH: 網路名前綴。⚠ 改名會讓既有的網路變成孤兒（清不掉也認不出來），
#     真要改的時候要連同清理程序一起想。
NET_PREFIX = "aibase-lab-"

# ZH: 要一起連進每個 lab 網路的平台容器，以及它們在網路上的別名。
#     ⚠ alias 不是裝飾 —— 見檔頭：少了 `job-scheduler` 這個名字，
#     容器裡的 extension 就找不到服務層。
PLATFORM_PEERS = {
    "ai-platform-nginx": [],
    "ai-platform-scheduler": ["job-scheduler"],
}


def network_name(user_id: str) -> str:
    """ZH: 這個使用者的網路名。

    ZH: 取 uuid 前 12 碼：Docker 的網路名沒有長度問題，但這個名字會出現在
        `docker network ls` 與問題排查的畫面上，整串 uuid 只是雜訊。
        12 碼的碰撞機率對一個學校的人數來說可以忽略。

    @node job-scheduler/app/services/network_manager.py::network_name
    """
    return f"{NET_PREFIX}{str(user_id).replace('-', '')[:12]}"


def ensure_network(client, user_id: str):
    """
    ZH: 確保這個使用者的網路存在（沒有就建），並把平台容器連進去。回傳網路名。

    ZH: 🔴 位址池用完時**丟出可讀的錯誤**，不要讓它以 Docker 的原文冒出來 ——
        「could not find an available IP address pool」看起來像 Docker 壞了，
        實際上是「同時開著的實驗室太多」，兩者的處理完全不同。

    @node job-scheduler/app/services/network_manager.py::ensure_network
    """
    name = network_name(user_id)
    try:
        net = client.networks.get(name)
    except NotFound:
        try:
            net = client.networks.create(
                name, driver="bridge",
                labels={"aibase.role": "lab-net", "aibase.user_id": str(user_id)},
            )
            logger.info("Created lab network %s", name)
        except APIError as e:
            if "address pool" in str(e).lower():
                raise RuntimeError(
                    "建不出新的實驗室網路：Docker 的位址池用完了"
                    "（預設大約 31 個）。同時開著的實驗室太多，"
                    "請等別人關掉，或調整 daemon 的 default-address-pools。") from e
            raise

    _attach_peers(client, net)
    return name


def _attach_peers(client, net) -> None:
    """
    ZH: 把 nginx 與服務層連進這個網路（已連的就跳過）。

    ZH: ⚠ 連不上**不中斷開實驗室** —— 但要記 error。
        少了 nginx 的話使用者會看到 502，少了服務層則是 Run on GPU 失敗；
        兩者都比「開不起來」好處理，而且 log 裡查得到原因。

    @node job-scheduler/app/services/network_manager.py::_attach_peers
    """
    net.reload()
    already = {c.get("Name") for c in (net.attrs.get("Containers") or {}).values()}
    for cname, aliases in PLATFORM_PEERS.items():
        if cname in already:
            continue
        try:
            net.connect(cname, aliases=aliases or None)
            logger.info("Connected %s to %s (aliases=%s)", cname, net.name, aliases)
        except NotFound:
            logger.error("要連進 %s 的容器 %s 不存在 —— 隔離網路會缺一角", net.name, cname)
        except APIError as e:
            # ZH: 已經連上時 Docker 會回 403/409，那不是錯誤。
            if "already exists" in str(e) or "already connected" in str(e):
                continue
            logger.error("把 %s 連進 %s 失敗：%s", cname, net.name, e)


def remove_network(client, user_id: str) -> bool:
    """
    ZH: 使用者的實驗室都關掉之後，把網路收掉。有收到回 True。

    ZH: ⚠ **還有容器掛在上面就不要收**（除了平台自己那兩個）——
        多份存檔的人可能還開著另一份。判斷方式是看網路上剩下誰，
        只剩平台容器才算空。

    ZH: ⚠ 收不掉**不要讓關實驗室失敗**：網路留著只是佔一個位址段，
        下次開同一個人的實驗室會重用它。

    @node job-scheduler/app/services/network_manager.py::remove_network
    """
    name = network_name(user_id)
    try:
        net = client.networks.get(name)
    except NotFound:
        return False
    except APIError as e:
        logger.warning("查 %s 失敗：%s", name, e)
        return False

    try:
        net.reload()
        names = {c.get("Name") for c in (net.attrs.get("Containers") or {}).values()}
        if names - set(PLATFORM_PEERS):
            logger.debug("%s 上還有容器 %s，先不收", name, names - set(PLATFORM_PEERS))
            return False
        for cname in list(names & set(PLATFORM_PEERS)):
            try:
                net.disconnect(cname, force=True)
            except APIError as e:
                logger.warning("把 %s 從 %s 斷開失敗：%s", cname, name, e)
        net.remove()
        logger.info("Removed lab network %s", name)
        return True
    except APIError as e:
        logger.warning("移除 %s 失敗（留著不影響下次使用）：%s", name, e)
        return False
