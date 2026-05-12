"""
ZH: SlowAPI 速率限制器共用實例（所有 Router 共享同一個 limiter）
EN: Shared SlowAPI rate limiter instance (shared across all routers)
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
