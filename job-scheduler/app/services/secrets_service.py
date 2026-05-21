"""
==============================================================================
Service: User Secrets 加密儲存與注入 | User Secrets Encryption & Injection
==============================================================================
ZH: 用途：使用者 HF_TOKEN / WANDB_API_KEY / GH_TOKEN 等敏感值的安全儲存
    - AES-256-GCM 對稱加密
    - 主金鑰 (KEK) 從 settings.SECRETS_MASTER_KEY 讀取
    - DB 內只存密文 (nonce + ciphertext + tag)，明文僅在記憶體
    - 提交 GPU Job / 啟動 code-server 時透明注入 docker env

EN: Purpose: Secure storage of user secrets like HF_TOKEN / WANDB_API_KEY / GH_TOKEN
    - AES-256-GCM symmetric encryption
    - Master key (KEK) read from settings.SECRETS_MASTER_KEY
    - DB stores ciphertext only (nonce + ciphertext + tag); plaintext in memory only
    - Transparently injected into docker env on Job submit / code-server start
==============================================================================
"""

from __future__ import annotations

import base64
import hashlib
import logging
import os
import secrets as _stdlib_secrets
from datetime import datetime, timezone
from typing import Dict, List, Optional

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy.orm import Session

from .. import models
from ..config import settings

logger = logging.getLogger(__name__)


# ==============================================================================
# ZH: AES-256-GCM 加密 / 解密底層 | AES-256-GCM crypto primitives
# ==============================================================================

def _derive_key() -> bytes:
    """
    ZH: 從 settings.SECRETS_MASTER_KEY 推導 256-bit AES key
    EN: Derive 256-bit AES key from settings.SECRETS_MASTER_KEY

    ZH: 使用 SHA-256 將任意長度的 master key 壓到 32 bytes
    EN: SHA-256 compresses arbitrary-length master key to 32 bytes
    """
    master = getattr(settings, "SECRETS_MASTER_KEY", None)
    if not master:
        raise RuntimeError(
            "SECRETS_MASTER_KEY is not configured. "
            "Set it in .env (min 32 chars) and restart."
        )
    return hashlib.sha256(master.encode("utf-8")).digest()


def encrypt_value(plaintext: str) -> bytes:
    """
    ZH: 加密單一 secret value，回傳 nonce(12) + ciphertext + tag(16)
    EN: Encrypt a secret value; returns nonce(12) + ciphertext + tag(16)
    """
    key = _derive_key()
    aesgcm = AESGCM(key)
    nonce = _stdlib_secrets.token_bytes(12)              # GCM 標準 12-byte nonce
    ciphertext_with_tag = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
    return nonce + ciphertext_with_tag


def decrypt_value(blob: bytes) -> str:
    """
    ZH: 解密；blob 為 encrypt_value() 的輸出
    EN: Decrypt blob produced by encrypt_value()
    """
    key = _derive_key()
    aesgcm = AESGCM(key)
    nonce, ciphertext_with_tag = blob[:12], blob[12:]
    return aesgcm.decrypt(nonce, ciphertext_with_tag, None).decode("utf-8")


# ==============================================================================
# ZH: 公開 API | Public API
# ==============================================================================

def set_secret(db: Session, user_id: str, name: str, value: str) -> models.UserSecret:
    """
    ZH: 新增或更新使用者的某個 secret（upsert）
    EN: Insert or update a user's secret (upsert)
    """
    if not name or not name.replace("_", "").isalnum():
        raise ValueError("Secret name must be alphanumeric + underscore only")
    if not value:
        raise ValueError("Secret value cannot be empty")
    if len(value) > 4096:
        raise ValueError("Secret value too long (max 4096 chars)")

    enc = encrypt_value(value)
    existing = db.query(models.UserSecret).filter(
        models.UserSecret.user_id == user_id,
        models.UserSecret.name == name,
    ).first()

    if existing:
        existing.value_enc = enc
        existing.updated_at = datetime.now(timezone.utc)
        secret = existing
    else:
        secret = models.UserSecret(user_id=user_id, name=name, value_enc=enc)
        db.add(secret)

    db.commit()
    db.refresh(secret)
    logger.info("Secret %s upserted for user %s", name, user_id[:8])
    return secret


def get_secret_plaintext(db: Session, user_id: str, name: str) -> Optional[str]:
    """
    ZH: 取得單一 secret 的明文（僅用於 Job 注入等內部呼叫）
    EN: Get plaintext of a single secret (internal use only, e.g. job injection)
    """
    row = db.query(models.UserSecret).filter(
        models.UserSecret.user_id == user_id,
        models.UserSecret.name == name,
    ).first()
    if not row:
        return None
    try:
        return decrypt_value(bytes(row.value_enc))
    except Exception as e:
        logger.error("Failed to decrypt secret %s for user %s: %s", name, user_id[:8], e)
        return None


def get_all_secrets_plaintext(db: Session, user_id: str) -> Dict[str, str]:
    """
    ZH: 取得使用者全部 secrets 明文，回傳 {name: plaintext}
        僅供 Job 提交、code-server 啟動時內部呼叫，**不可**透過 API 回傳給前端
    EN: Get all user secrets as plaintext {name: plaintext}
        Internal use only; NEVER return through API to frontend
    """
    out: Dict[str, str] = {}
    for row in db.query(models.UserSecret).filter(models.UserSecret.user_id == user_id).all():
        try:
            out[row.name] = decrypt_value(bytes(row.value_enc))
        except Exception as e:
            logger.error("Skipping un-decryptable secret %s for user %s: %s",
                         row.name, user_id[:8], e)
    return out


def list_secrets_masked(db: Session, user_id: str) -> List[dict]:
    """
    ZH: 列出使用者 secrets 的 name + masked value（API 安全回傳格式）
    EN: List user secrets with name + masked value (safe to return through API)

    範例 masked 格式：
        "hf_abc123def456..." → "hf_********f456"
        "sk-xxx"             → "***x"
    """
    rows = db.query(models.UserSecret).filter(models.UserSecret.user_id == user_id).all()
    out = []
    for row in rows:
        try:
            plain = decrypt_value(bytes(row.value_enc))
            masked = _mask(plain)
        except Exception:
            masked = "<decryption-failed>"
        out.append({
            "name": row.name,
            "value_masked": masked,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        })
    return out


def _mask(plaintext: str) -> str:
    """ZH: 將值打碼 — 保留前 3 + 後 4 字元，中間用 * | EN: Mask middle of value"""
    n = len(plaintext)
    if n <= 8:
        return "*" * n
    return plaintext[:3] + "*" * 8 + plaintext[-4:]


def delete_secret(db: Session, user_id: str, name: str) -> bool:
    """
    ZH: 刪除某個 secret，回傳 True if 找到並刪除
    EN: Delete a secret; returns True if found and deleted
    """
    row = db.query(models.UserSecret).filter(
        models.UserSecret.user_id == user_id,
        models.UserSecret.name == name,
    ).first()
    if not row:
        return False
    db.delete(row)
    db.commit()
    logger.info("Secret %s deleted for user %s", name, user_id[:8])
    return True


def build_docker_env(db: Session, user_id: str) -> Dict[str, str]:
    """
    ZH: 取得使用者全部 secrets 並以 docker env 字典格式回傳，給 lab_manager
        或 worker /take 端點使用
    EN: Get all user secrets as a dict ready for docker -e injection
    """
    return get_all_secrets_plaintext(db, user_id)


def admin_list_user_secret_names(db: Session, user_id: str) -> List[dict]:
    """
    ZH: 管理員用 — 列出某使用者 secrets 名稱（**絕不**回傳 value，連 masked 都不給）
    EN: Admin-only — list secret names of a user (NEVER returns value, not even masked)
    """
    rows = db.query(models.UserSecret).filter(models.UserSecret.user_id == user_id).all()
    return [
        {
            "name": r.name,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "updated_at": r.updated_at.isoformat() if r.updated_at else None,
        }
        for r in rows
    ]
