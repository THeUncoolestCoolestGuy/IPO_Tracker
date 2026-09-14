"""
Cryptographic Utilities for Encrypting and Decrypting Sensitive User Data (e.g. PAN cards).
Uses AES-256 Fernet authenticated symmetric encryption.
Key is derived from Config.TELEGRAM_BOT_TOKEN (or PAN_ENCRYPTION_KEY if set).
"""

import os
import base64
import hashlib
import logging
from typing import Optional
from cryptography.fernet import Fernet
from config import Config

logger = logging.getLogger("ipo_tracker.crypto")

_fernet_instance: Optional[Fernet] = None

def _get_fernet() -> Fernet:
    global _fernet_instance
    if _fernet_instance is not None:
        return _fernet_instance

    raw_key = os.getenv("PAN_ENCRYPTION_KEY", "").strip()
    if raw_key:
        try:
            _fernet_instance = Fernet(raw_key.encode() if isinstance(raw_key, str) else raw_key)
            return _fernet_instance
        except Exception as e:
            logger.warning(f"Invalid PAN_ENCRYPTION_KEY provided, falling back to token derivation: {e}")

    # Deterministic secret derivation from TELEGRAM_BOT_TOKEN
    token = Config.TELEGRAM_BOT_TOKEN or "IPO_TRACKER_DEFAULT_KEY_DO_NOT_USE_IN_PROD"
    key_hash = hashlib.sha256(token.encode("utf-8")).digest()
    b64_key = base64.urlsafe_b64encode(key_hash)
    _fernet_instance = Fernet(b64_key)
    return _fernet_instance


def encrypt_pan(pan: str) -> str:
    """Encrypt a plain text PAN card to an 'enc:...' ciphertext."""
    if not pan:
        return ""
    pan_str = str(pan).strip().upper()
    if pan_str.startswith("enc:"):
        return pan_str

    try:
        f = _get_fernet()
        encrypted = f.encrypt(pan_str.encode("utf-8")).decode("utf-8")
        return f"enc:{encrypted}"
    except Exception as e:
        logger.error(f"Error encrypting PAN: {e}")
        return pan_str


def decrypt_pan(val: str) -> str:
    """Decrypt an 'enc:...' ciphertext back to a plain text PAN card."""
    if not val:
        return ""
    val_str = str(val).strip()
    if not val_str.startswith("enc:"):
        # Backwards compatible with unencrypted legacy PANs
        return val_str.upper()

    try:
        f = _get_fernet()
        ciphertext = val_str[4:].encode("utf-8")
        decrypted = f.decrypt(ciphertext).decode("utf-8")
        return decrypted.strip().upper()
    except Exception as e:
        logger.error(f"Error decrypting PAN token: {e}")
        return val_str
