"""Fernet symmetric encryption for integration secrets.

Secrets stored in platform DB (tenant_integration_secrets) are encrypted
with a master key from INTEGRATION_SECRET_ENCRYPTION_KEY.
Generate a key: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
"""

from __future__ import annotations

import secrets

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings

_fernet: Fernet | None = None


def _get_fernet() -> Fernet:
    global _fernet
    if _fernet is not None:
        return _fernet
    env_key = getattr(settings, "integration_secret_encryption_key", None) or ""
    if not env_key or len(env_key) != 44:
        raise RuntimeError(
            "INTEGRATION_SECRET_ENCRYPTION_KEY must be set (44-char Fernet key). "
            "Generate: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        )
    try:
        _fernet = Fernet(env_key.encode("utf-8"))
        return _fernet
    except Exception as e:
        raise RuntimeError(f"INTEGRATION_SECRET_ENCRYPTION_KEY invalid: {e}") from e


def encrypt_secret(plaintext: str | bytes) -> bytes:
    data = plaintext.encode("utf-8") if isinstance(plaintext, str) else plaintext
    return _get_fernet().encrypt(data)


def decrypt_secret(ciphertext: bytes) -> bytes:
    try:
        return _get_fernet().decrypt(ciphertext)
    except InvalidToken:
        # Do not log; could leak secret context. Fail silently.
        raise ValueError("Decryption failed") from None


def generate_credential_ref() -> str:
    return secrets.token_urlsafe(32)
