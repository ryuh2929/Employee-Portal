import hashlib
import secrets

from pwdlib import PasswordHash


PASSWORD_HASH = PasswordHash.recommended()
DUMMY_PASSWORD_HASH = PASSWORD_HASH.hash("not-a-real-user-password")


def generate_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
