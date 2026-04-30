"""Tests for server/app/utils/crypto.py — AES-256-GCM encryption helpers."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "server"))

from app.utils.crypto import encrypt, decrypt, is_encrypted, encrypt_if_needed, decrypt_safe


class TestEncryptDecryptRoundtrip:
    def test_roundtrip_api_key(self):
        plaintext = "sk_live_abc123"
        assert decrypt(encrypt(plaintext)) == plaintext

    def test_roundtrip_long_value(self):
        plaintext = "x" * 500
        assert decrypt(encrypt(plaintext)) == plaintext

    def test_roundtrip_unicode(self):
        plaintext = "token-with-unicode-éàü"
        assert decrypt(encrypt(plaintext)) == plaintext

    def test_encrypt_empty_string_returns_empty(self):
        assert encrypt("") == ""

    def test_decrypt_plaintext_no_colon_returns_unchanged(self):
        assert decrypt("not_encrypted") == "not_encrypted"

    def test_decrypt_malformed_iv_returns_unchanged(self):
        # Has colon but invalid hex
        assert decrypt("xx:yy") == "xx:yy"

    def test_decrypt_tampered_ciphertext_returns_unchanged_no_crash(self):
        encrypted = encrypt("sensitive-token")
        iv_hex, ct_hex = encrypted.split(":")
        ct = bytes.fromhex(ct_hex)
        # Flip last byte — corrupts GCM auth tag
        tampered_ct = ct[:-1] + bytes([ct[-1] ^ 0xFF])
        tampered = f"{iv_hex}:{tampered_ct.hex()}"
        result = decrypt(tampered)
        # Must not crash, must return tampered string unchanged (graceful fallback)
        assert result == tampered
        assert result != "sensitive-token"

    def test_each_encrypt_call_produces_different_ciphertext(self):
        plaintext = "same-secret"
        enc1 = encrypt(plaintext)
        enc2 = encrypt(plaintext)
        # Different IVs per call
        assert enc1 != enc2
        # Both decrypt to same plaintext
        assert decrypt(enc1) == decrypt(enc2) == plaintext


class TestIsEncrypted:
    def test_recognizes_fresh_encrypt_output(self):
        assert is_encrypted(encrypt("x")) is True

    def test_rejects_plaintext(self):
        assert is_encrypted("plaintext") is False

    def test_rejects_empty_string(self):
        assert is_encrypted("") is False

    def test_rejects_short_iv(self):
        # IV must be 32 hex chars (16 bytes). This has <32.
        assert is_encrypted("xx:yy") is False

    def test_rejects_mixed_case_hex_in_iv(self):
        # is_encrypted checks lowercase hex only in parts[0]
        bad_iv = "A" * 32 + ":" + "b" * 32
        # Uppercase is outside "0-9abcdef" — should fail
        assert is_encrypted(bad_iv) is False

    def test_accepts_valid_looking_format(self):
        iv = "a" * 32
        ct = "b" * 32
        assert is_encrypted(f"{iv}:{ct}") is True


class TestEncryptIfNeeded:
    def test_does_not_double_encrypt(self):
        already = encrypt("x")
        result = encrypt_if_needed(already)
        assert result == already

    def test_encrypts_plaintext(self):
        result = encrypt_if_needed("plaintext-key")
        assert is_encrypted(result) is True

    def test_passthrough_empty(self):
        assert encrypt_if_needed("") == ""


class TestDecryptSafe:
    def test_decrypts_encrypted_value(self):
        enc = encrypt("my-secret")
        assert decrypt_safe(enc) == "my-secret"

    def test_passthrough_plaintext(self):
        assert decrypt_safe("plaintext") == "plaintext"


class TestDifferentKeys:
    def test_different_keys_produce_different_ciphertexts(self, monkeypatch):
        monkeypatch.setenv("ENCRYPTION_KEY", "key-one")
        ct1 = encrypt("same-text")

        monkeypatch.setenv("ENCRYPTION_KEY", "key-two")
        ct2 = encrypt("same-text")

        assert ct1 != ct2

    def test_ciphertext_only_decryptable_with_same_key(self, monkeypatch):
        monkeypatch.setenv("ENCRYPTION_KEY", "key-alpha")
        enc = encrypt("my-secret")
        # Decrypt with same key → success
        assert decrypt(enc) == "my-secret"

        # Decrypt with different key → graceful fallback (returns tampered/encrypted string)
        monkeypatch.setenv("ENCRYPTION_KEY", "key-beta")
        result = decrypt(enc)
        assert result != "my-secret"
