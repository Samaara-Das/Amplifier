"""Client-side AES-256-GCM encryption for local sensitive data.

Encrypts API keys stored in the local SQLite settings table.
Uses a machine-derived key (username + hostname) so encrypted values
are tied to the specific device — moving the DB file to another
machine won't expose the keys.

Same API as server/app/utils/crypto.py for consistency.
"""

import hashlib
import os
import platform

_SALT = b"amplifire-local-encryption-v1"


def _derive_key() -> bytes:
    """Derive a 256-bit key from machine-specific data.

    Uses username + hostname so the key is unique per device.
    Not as secure as a user-provided password, but protects against
    casual access to the SQLite file.
    """
    machine_id = f"{os.getlogin()}@{platform.node()}".encode()
    return hashlib.pbkdf2_hmac("sha256", machine_id, _SALT, iterations=100_000)


def encrypt(plaintext: str) -> str:
    """Encrypt a string with AES-256-GCM. Returns 'iv_hex:ciphertext_hex'."""
    if not plaintext:
        return plaintext

    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    key = _derive_key()
    iv = os.urandom(16)
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(iv, plaintext.encode("utf-8"), None)
    return f"{iv.hex()}:{ciphertext.hex()}"


def decrypt(encrypted: str) -> str:
    """Decrypt an AES-256-GCM encrypted string."""
    if not encrypted or ":" not in encrypted:
        return encrypted

    parts = encrypted.split(":", 1)
    if len(parts) != 2:
        return encrypted

    try:
        iv = bytes.fromhex(parts[0])
        ciphertext = bytes.fromhex(parts[1])
    except ValueError:
        return encrypted

    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    key = _derive_key()
    aesgcm = AESGCM(key)
    try:
        return aesgcm.decrypt(iv, ciphertext, None).decode("utf-8")
    except Exception:
        return encrypted


def is_encrypted(value: str) -> bool:
    """Check if a value looks like it was encrypted by this module."""
    if not value or ":" not in value:
        return False
    parts = value.split(":", 1)
    return (
        len(parts) == 2
        and len(parts[0]) == 32
        and len(parts[1]) >= 32
        and all(c in "0123456789abcdef" for c in parts[0])
    )


def encrypt_if_needed(value: str) -> str:
    """Encrypt only if not already encrypted."""
    if not value or is_encrypted(value):
        return value
    return encrypt(value)


def decrypt_safe(value: str) -> str:
    """Decrypt if encrypted, return as-is if plaintext."""
    if is_encrypted(value):
        return decrypt(value)
    return value
