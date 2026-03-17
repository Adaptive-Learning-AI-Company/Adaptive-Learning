import base64
import hashlib
import os

from cryptography.fernet import Fernet, InvalidToken

from .config import load_local_env

load_local_env()


def encrypt_profile_secret(secret_value: str | None) -> str | None:
    if not secret_value:
        return None
    return _get_cipher().encrypt(secret_value.encode("utf-8")).decode("utf-8")


def decrypt_profile_secret(secret_value: str | None) -> str | None:
    if not secret_value:
        return None
    try:
        return _get_cipher().decrypt(secret_value.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        return None


def mask_secret(secret_value: str | None) -> str | None:
    if not secret_value:
        return None

    decrypted = decrypt_profile_secret(secret_value)
    if not decrypted:
        return None

    if len(decrypted) <= 4:
        return "****"

    return "****" + decrypted[-4:]


def _get_cipher() -> Fernet:
    secret = (
        os.getenv("PROFILE_SECRET_KEY")
        or os.getenv("SECRET_KEY")
        or "dev_secret_key_change_me"
    )
    digest = hashlib.sha256(secret.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))
