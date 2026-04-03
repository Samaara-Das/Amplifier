"""AES-256-GCM authenticated encryption for sensitive data at rest.

Adopted from AmpliFire v2's crypto.util.ts. Encrypts OAuth tokens, API keys,
payment details, and any other sensitive fields before storage.

Format: "iv_hex:ciphertext_hex" where ciphertext includes the GCM auth tag
(last 16 bytes). The auth tag prevents tampering.

Usage:
    from app.utils.crypto import encrypt, decrypt, is_encrypted

    encrypted = encrypt("sk_live_abc123")
    plaintext = decrypt(encrypted)
    if is_encrypted(value):
        value = decrypt(value)
"""

import hashlib
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_SALT = b"amplifire-encryption-salt-v1"


def _derive_key() -> bytes:
    """Derive a 256-bit key from the ENCRYPTION_KEY environment variable."""
    raw_key = os.environ.get("ENCRYPTION_KEY", "")
    if not raw_key:
        # Fallback for development — NOT secure for production
        raw_key = "amplifire-dev-key-change-in-production"
    return hashlib.pbkdf2_hmac("sha256", raw_key.encode(), _SALT, iterations=100_000)


def encrypt(plaintext: str) -> str:
    """Encrypt a string with AES-256-GCM. Returns 'iv_hex:ciphertext_hex'.

    The ciphertext includes the 16-byte GCM auth tag appended by AESGCM.
    """
    if not plaintext:
        return plaintext

    key = _derive_key()
    iv = os.urandom(16)
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(iv, plaintext.encode("utf-8"), None)
    return f"{iv.hex()}:{ciphertext.hex()}"


def decrypt(encrypted: str) -> str:
    """Decrypt an AES-256-GCM encrypted string. Input format: 'iv_hex:ciphertext_hex'."""
    if not encrypted or ":" not in encrypted:
        return encrypted

    parts = encrypted.split(":", 1)
    if len(parts) != 2:
        return encrypted

    try:
        iv = bytes.fromhex(parts[0])
        ciphertext = bytes.fromhex(parts[1])
    except ValueError:
        # Not valid hex — return as-is (probably plaintext)
        return encrypted

    key = _derive_key()
    aesgcm = AESGCM(key)
    try:
        plaintext = aesgcm.decrypt(iv, ciphertext, None)
        return plaintext.decode("utf-8")
    except Exception:
        # Decryption failed — return as-is (wrong key or corrupted)
        return encrypted


def is_encrypted(value: str) -> bool:
    """Check if a value looks like it was encrypted by this module.

    Useful during migration to detect whether a stored value is already
    encrypted or still plaintext.
    """
    if not value or ":" not in value:
        return False
    parts = value.split(":", 1)
    if len(parts) != 2:
        return False
    # IV should be exactly 32 hex chars (16 bytes)
    # Ciphertext should be at least 32 hex chars (16 bytes auth tag minimum)
    return len(parts[0]) == 32 and len(parts[1]) >= 32 and all(
        c in "0123456789abcdef" for c in parts[0]
    )


def encrypt_if_needed(value: str) -> str:
    """Encrypt a value only if it's not already encrypted. For migration."""
    if not value or is_encrypted(value):
        return value
    return encrypt(value)


def decrypt_safe(value: str) -> str:
    """Decrypt if encrypted, return as-is if plaintext. For migration."""
    if is_encrypted(value):
        return decrypt(value)
    return value
