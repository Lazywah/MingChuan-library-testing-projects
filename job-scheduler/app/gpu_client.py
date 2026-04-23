"""
==============================================================================
Module 7: GPU 通訊模組 (GPU Client - SSH/Mock Dual Mode)
==============================================================================
ZH: 用途：透過 SSH 與 GPU 伺服器通訊，或使用 Mock 模式模擬 GPU 操作
EN: Purpose: Communicate with GPU servers via SSH, or use Mock mode to simulate

ZH: 流程：
    排程器 → get_gpu_client() → 依環境變數選擇模式
                ├── GPU_MOCK_MODE=true  → MockGPUClient (模擬)
                └── GPU_MOCK_MODE=false → SSHGPUClient  (真實 SSH)

    兩種模式的 API 完全相同 (繼承 BaseGPUClient)：
        connect()              → 建立連線
        get_available_gpus()   → 查詢可用 GPU
        execute_training()     → 執行訓練腳本
        check_job_status()     → 檢查任務狀態
        disconnect()           → 斷開連線

ZH: 模組化設計 (積木式)：
    - 新增 GPU 後端只需繼承 BaseGPUClient
    - 切換模式只需改 .env 中的 GPU_MOCK_MODE，零程式碼修改
    - 如需支援 Slurm，可新增 SlurmGPUClient 類別
EN: Modular design (building-block style):
    - Adding GPU backends only requires inheriting BaseGPUClient
    - Switching modes only requires changing GPU_MOCK_MODE in .env
    - To support Slurm, add new SlurmGPUClient class
==============================================================================
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Optional
import asyncio
import random
import logging
import time

logger = logging.getLogger(__name__)


# ==============================================================================
# ZH: 基礎介面 (抽象類別) - 所有 GPU Client 必須實作此介面
# EN: Base interface (abstract class) - all GPU Clients must implement this
# ==============================================================================
class BaseGPUClient(ABC):
    """
    ZH: GPU 客戶端抽象基底類別
    EN: GPU Client abstract base class

    ZH: 任何 GPU 後端 (Mock, SSH, Slurm) 都繼承此類別
    EN: Any GPU backend (Mock, SSH, Slurm) inherits from this class
    """

    def __init__(self, host: str, port: int = 22, username: str = "gpu_admin"):
        self.host = host
        self.port = port
        self.username = username
        self.connected = False

    @abstractmethod
    async def connect(self) -> bool:
        """ZH: 建立連線 | EN: Establish connection"""
        pass

    @abstractmethod
    async def get_available_gpus(self) -> List[int]:
        """ZH: 查詢可用 GPU ID 列表 | EN: Get available GPU ID list"""
        pass

    @abstractmethod
    async def execute_training(self, script_path: str, config: dict, dataset_path: Optional[str] = None) -> Dict:
        """ZH: 執行訓練腳本 | EN: Execute training script"""
        pass

    @abstractmethod
    async def check_job_progress(self) -> float:
        """ZH: 檢查任務進度 (0-100) | EN: Check job progress (0-100)"""
        pass

    @abstractmethod
    def disconnect(self):
        """ZH: 斷開連線 | EN: Disconnect"""
        pass

    @abstractmethod
    async def get_cluster_stats(self) -> List[Dict]:
        """ZH: 獲取叢集詳細狀態 | EN: Get detailed cluster status"""
        pass


# ==============================================================================
# ZH: Mock GPU 客戶端 - 模擬 GPU 操作 (開發/測試用)
# EN: Mock GPU Client - Simulate GPU operations (dev/testing)
# ZH: 行為：
#   - connect(): 永遠成功，延遲 0.5 秒
#   - get_available_gpus(): 回傳 [0, 1] (模擬 2 張 GPU)
#   - execute_training(): 模擬 15 秒訓練，進度遞增
#   - 10% 機率模擬訓練失敗
# EN: Behavior:
#   - connect(): always succeeds, 0.5s delay
#   - get_available_gpus(): returns [0, 1] (simulates 2 GPUs)
#   - execute_training(): simulates 15s training with progress
#   - 10% chance of simulated failure
# ==============================================================================
class MockGPUClient(BaseGPUClient):
    """
    ZH: Mock GPU 客戶端 (開發/測試用)
    EN: Mock GPU Client (for development/testing)
    """

    def __init__(self, host: str, **kwargs):
        # Only pass known arguments to super().__init__
        safe_kwargs = {k: v for k, v in kwargs.items() if k in ["port", "username"]}
        super().__init__(host, **safe_kwargs)
        self._progress = 0.0

    async def connect(self) -> bool:
        logger.info(f"ZH: [Mock] 模擬連線到 GPU 伺服器 {self.host} | "
                    f"EN: [Mock] Simulating connection to GPU server {self.host}")
        await asyncio.sleep(0.5)  # ZH: 模擬連線延遲 | EN: Simulate connection delay
        self.connected = True
        return True

    async def get_available_gpus(self) -> List[int]:
        if not self.connected:
            raise ConnectionError("ZH: 尚未連線 | EN: Not connected")
        # ZH: 模擬 2 張 GPU，偶爾只有 1 張可用 | EN: Simulate 2 GPUs, occasionally only 1
        if random.random() < 0.1:
            return [0]  # ZH: 10% 機率只有 1 張 | EN: 10% chance only 1
        return [0, 1]

    async def execute_training(self, script_path: str, config: dict, dataset_path: Optional[str] = None) -> Dict:
        if not self.connected:
            raise ConnectionError("ZH: 尚未連線 | EN: Not connected")

        logger.info(f"ZH: [Mock] 開始模擬訓練 script={script_path}, dataset={dataset_path} | "
                    f"EN: [Mock] Starting mock training script={script_path}, dataset={dataset_path}")

        # ZH: 模擬訓練過程 (10% 機率失敗) | EN: Simulate training (10% failure chance)
        if random.random() < 0.1:
            raise RuntimeError("ZH: [Mock] 模擬訓練失敗 - GPU OOM | EN: [Mock] Simulated failure - GPU OOM")

        self._progress = 0.0
        return {
            "status": "started",
            "output_path": f"/mock/outputs/{int(time.time())}/model_final.pt"
        }

    async def check_job_progress(self) -> float:
        """
        ZH: 每次呼叫遞增 20% 進度 (模擬 3 秒一個步驟)
        EN: Increment 20% per call (simulates 3s per step)
        """
        await asyncio.sleep(3)  # ZH: 模擬訓練延遲 | EN: Simulate training delay
        self._progress = min(100.0, self._progress + 20.0)
        return self._progress

    def disconnect(self):
        self.connected = False
        logger.info(f"ZH: [Mock] 已斷開與 {self.host} 的模擬連線 | "
                    f"EN: [Mock] Disconnected from {self.host}")

    async def get_cluster_stats(self) -> List[Dict]:
        """ZH: 產生變動的模擬硬體數據 | EN: Generate fluctuating mock hardware stats"""
        import random
        # 模擬 2 張 GPU
        stats = []
        for i in range(2):
            stats.append({
                "gpu_id": i,
                "name": f"Mock-RTX-4090-{i}",
                "temperature": random.randint(35, 85),
                "utilization": random.randint(0, 100),
                "memory_used": random.randint(1000, 24000),
                "memory_total": 24576
            })
        return stats


# ==============================================================================
# ZH: SSH GPU 客戶端 - 透過 paramiko 連接真實 GPU 伺服器
# EN: SSH GPU Client - Connect to real GPU servers via paramiko
# ZH: 條件：GPU_MOCK_MODE=false 時啟用
# EN: Condition: activated when GPU_MOCK_MODE=false
#
# ZH: 注意：GPU 伺服器尚未部署，此實作為預留框架
# EN: Note: GPU servers not yet deployed, this is a pre-built framework
# ==============================================================================
class SSHGPUClient(BaseGPUClient):
    """
    ZH: SSH GPU 客戶端 (透過 paramiko 連接真實 GPU 伺服器)
    EN: SSH GPU Client (connects to real GPU servers via paramiko)
    """

    def __init__(self, host: str, port: int = 22, username: str = "gpu_admin",
                 key_path: str = "/root/.ssh/id_rsa"):
        super().__init__(host, port, username)
        self.key_path = key_path
        self._ssh_client = None
        self._progress = 0.0

    async def connect(self) -> bool:
        try:
            import paramiko
            self._ssh_client = paramiko.SSHClient()
            self._ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            self._ssh_client.connect(
                hostname=self.host,
                port=self.port,
                username=self.username,
                key_filename=self.key_path,
                timeout=10
            )
            self.connected = True
            logger.info(f"ZH: [SSH] 已連線到 GPU 伺服器 {self.host} | "
                        f"EN: [SSH] Connected to GPU server {self.host}")
            return True
        except Exception as e:
            logger.error(f"ZH: [SSH] 連線失敗 {self.host}: {e} | "
                         f"EN: [SSH] Connection failed {self.host}: {e}")
            return False

    async def get_available_gpus(self) -> List[int]:
        if not self.connected or not self._ssh_client:
            raise ConnectionError("ZH: SSH 尚未連線 | EN: SSH not connected")

        # ZH: 執行 nvidia-smi 查詢 GPU 利用率 | EN: Run nvidia-smi to check GPU utilization
        cmd = "nvidia-smi --query-gpu=index,utilization.gpu --format=csv,noheader,nounits"
        stdin, stdout, stderr = self._ssh_client.exec_command(cmd)
        output = stdout.read().decode().strip()
        error = stderr.read().decode().strip()

        if error:
            logger.warning(f"ZH: [SSH] nvidia-smi 錯誤: {error} | EN: [SSH] nvidia-smi error: {error}")
            return []

        available = []
        for line in output.split("\n"):
            parts = line.strip().split(",")
            if len(parts) == 2:
                gpu_id = int(parts[0].strip())
                utilization = int(parts[1].strip())
                # ZH: 利用率 < 10% 視為可用 | EN: Utilization < 10% considered available
                if utilization < 10:
                    available.append(gpu_id)

        logger.info(f"ZH: [SSH] {self.host} 可用 GPU: {available} | "
                    f"EN: [SSH] {self.host} available GPUs: {available}")
        return available

    async def execute_training(self, script_path: str, config: dict, dataset_path: Optional[str] = None) -> Dict:
        if not self.connected or not self._ssh_client:
            raise ConnectionError("ZH: SSH 尚未連線 | EN: SSH not connected")

        # ZH: 組建遠端訓練指令 | EN: Build remote training command
        config_str = " ".join([f"--{k}={v}" for k, v in config.items()]) if config else ""
        if dataset_path:
            config_str += f" --dataset_path={dataset_path}"
        cmd = f"nohup python {script_path} {config_str} > /tmp/training.log 2>&1 &"

        logger.info(f"ZH: [SSH] 執行訓練指令: {cmd} | EN: [SSH] Executing training: {cmd}")
        stdin, stdout, stderr = self._ssh_client.exec_command(cmd)

        self._progress = 0.0
        return {
            "status": "started",
            "output_path": f"/workspace/outputs/model_latest.pt"
        }

    async def check_job_progress(self) -> float:
        if not self.connected or not self._ssh_client:
            return self._progress

        # ZH: 解析訓練日誌中的進度 | EN: Parse progress from training log
        try:
            cmd = "tail -1 /tmp/training.log"
            stdin, stdout, stderr = self._ssh_client.exec_command(cmd)
            last_line = stdout.read().decode().strip()
            # ZH: 嘗試從日誌解析進度百分比 | EN: Try to parse progress percentage
            if "%" in last_line:
                import re
                match = re.search(r'(\d+\.?\d*)%', last_line)
                if match:
                    self._progress = float(match.group(1))
        except Exception as e:
            logger.warning(f"ZH: [SSH] 進度查詢失敗: {e} | EN: [SSH] Progress check failed: {e}")

        return self._progress

    def disconnect(self):
        if self._ssh_client:
            self._ssh_client.close()
            self._ssh_client = None
        self.connected = False
        logger.info(f"ZH: [SSH] 已斷開與 {self.host} 的連線 | "
                    f"EN: [SSH] Disconnected from {self.host}")

    async def get_cluster_stats(self) -> List[Dict]:
        if not self.connected or not self._ssh_client:
            return []
        
        # ZH: 查詢 GPU 詳細數據 | EN: Query detailed GPU stats
        cmd = "nvidia-smi --query-gpu=index,name,temperature.gpu,utilization.gpu,memory.used,memory.total --format=csv,noheader,nounits"
        try:
            stdin, stdout, stderr = self._ssh_client.exec_command(cmd)
            output = stdout.read().decode().strip()
            error = stderr.read().decode().strip()
            
            if error:
                logger.warning(f"ZH: [SSH] nvidia-smi stats 錯誤: {error} | EN: [SSH] nvidia-smi stats error: {error}")
                return []
                
            stats = []
            for line in output.split("\n"):
                parts = [p.strip() for p in line.split(",")]
                if len(parts) >= 6:
                    stats.append({
                        "gpu_id": int(parts[0]),
                        "name": parts[1],
                        "temperature": int(parts[2]) if parts[2].isdigit() else 0,
                        "utilization": int(parts[3]) if parts[3].isdigit() else 0,
                        "memory_used": int(parts[4]) if parts[4].isdigit() else 0,
                        "memory_total": int(parts[5]) if parts[5].isdigit() else 0
                    })
            return stats
        except Exception as e:
            logger.warning(f"ZH: [SSH] 獲取硬體數據失敗: {e} | EN: [SSH] Failed to get hardware stats: {e}")
            return []


# ==============================================================================
# ZH: GPU Client 工廠函式 - 依環境變數自動選擇模式
# EN: GPU Client factory function - auto-selects mode based on env var
# ZH: 用法：client = get_gpu_client("192.168.1.100")
# EN: Usage: client = get_gpu_client("192.168.1.100")
# ==============================================================================
def get_gpu_client(host: str, mock_mode: bool = True, **kwargs) -> BaseGPUClient:
    """
    ZH: 工廠函式 - 根據 mock_mode 回傳對應的 GPU Client
    EN: Factory function - returns appropriate GPU Client based on mock_mode

    ZH: 積木式設計：未來新增 SlurmGPUClient 只需在此加一個條件
    EN: Building-block design: adding SlurmGPUClient only needs one more condition
    """
    if mock_mode:
        logger.info(f"ZH: 使用 Mock GPU Client (host={host}) | EN: Using Mock GPU Client (host={host})")
        return MockGPUClient(host=host, **kwargs)
    else:
        logger.info(f"ZH: 使用 SSH GPU Client (host={host}) | EN: Using SSH GPU Client (host={host})")
        return SSHGPUClient(host=host, **kwargs)
