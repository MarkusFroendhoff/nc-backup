"""Passwortschutz für GUI-Zugriff."""

from __future__ import annotations

import hashlib
import hmac


def hash_password(password: str) -> str:
    import bcrypt

    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str | None) -> bool:
    import bcrypt

    if not password_hash:
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def hash_api_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def verify_api_token(token: str, token_hash: str | None) -> bool:
    if not token or not token_hash:
        return False
    digest = hash_api_token(token)
    return hmac.compare_digest(digest, token_hash)
