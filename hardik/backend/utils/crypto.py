import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from backend.config.settings import get_settings


def _fernet() -> Fernet:
    settings = get_settings()
    key = settings.credential_encryption_key.strip()
    if not key:
        # Derive a stable Fernet key from SECRET_KEY when no dedicated key is configured
        digest = hashlib.sha256(settings.secret_key.encode()).digest()
        key = base64.urlsafe_b64encode(digest).decode()
    return Fernet(key.encode())


def encrypt_secret(value: str | None) -> str | None:
    if value is None or value == "":
        return value
    return _fernet().encrypt(value.encode()).decode()


def decrypt_secret(value: str | None) -> str | None:
    if value is None or value == "":
        return value
    try:
        return _fernet().decrypt(value.encode()).decode()
    except InvalidToken:
        return None
