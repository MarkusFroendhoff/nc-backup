"""Zugangsschlüssel und Restic-Passwörter: Pflicht, gemischt, nie nur Hex."""

from __future__ import annotations

import os
import secrets
import string
from pathlib import Path

WEB_TOKEN_PATH = Path("/etc/nc-backup/web-token")
SECRET_ERROR_DE = (
    "Schlüssel muss Groß- und Kleinbuchstaben, Zahlen und ein Sonderzeichen enthalten."
)
EMPTY_ERROR_DE = "Ein leerer Schlüssel ist nicht erlaubt."

# Erzeugung: 24–32 Zeichen aus genau diesem Vorrat.
SPECIAL_CHARS = "!#$%&*+-=?@^_"
ALPHABET = string.ascii_letters + string.digits + SPECIAL_CHARS
_UPPER = string.ascii_uppercase
_LOWER = string.ascii_lowercase
_DIGIT = string.digits


def is_valid_secret(value: str | None) -> bool:
    """True nur bei nicht-leerem Schlüssel mit Groß, Klein, Ziffer und Sonderzeichen."""
    if value is None:
        return False
    if not isinstance(value, str):
        return False
    if value.strip() == "" or value == "":
        return False
    has_upper = any(c.isupper() and c.isascii() for c in value)
    has_lower = any(c.islower() and c.isascii() for c in value)
    has_digit = any(c.isdigit() for c in value)
    has_special = any((not c.isalnum()) and (not c.isspace()) for c in value)
    return has_upper and has_lower and has_digit and has_special


def secret_error(value: str | None) -> str | None:
    """None wenn gültig, sonst deutsche Fehlermeldung."""
    if value is None or value == "" or (isinstance(value, str) and value.strip() == ""):
        return EMPTY_ERROR_DE
    if not is_valid_secret(value):
        return SECRET_ERROR_DE
    return None


def generate_secret(min_len: int = 24, max_len: int = 32) -> str:
    """Erzeugt einen Schlüssel mit allen Pflichtklassen; nie nur hexadezimal."""
    if min_len < 4:
        min_len = 4
    if max_len < min_len:
        max_len = min_len
    length = secrets.randbelow(max_len - min_len + 1) + min_len
    rng = secrets.SystemRandom()
    for _ in range(64):
        chars = [
            secrets.choice(_UPPER),
            secrets.choice(_LOWER),
            secrets.choice(_DIGIT),
            secrets.choice(SPECIAL_CHARS),
        ]
        chars.extend(secrets.choice(ALPHABET) for _ in range(length - 4))
        rng.shuffle(chars)
        token = "".join(chars)
        if is_valid_secret(token) and not _looks_hex(token):
            return token
    raise RuntimeError("Konnte keinen gültigen Schlüssel erzeugen")


def _looks_hex(value: str) -> bool:
    try:
        int(value, 16)
    except ValueError:
        return False
    return True


def write_web_token(token: str, path: Path | None = None) -> Path:
    err = secret_error(token)
    if err:
        raise ValueError(err)
    target = path or WEB_TOKEN_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(token + "\n", encoding="utf-8")
    os.chmod(target, 0o600)
    return target


def load_web_token(path: Path | None = None) -> str | None:
    target = path or WEB_TOKEN_PATH
    if not target.is_file():
        return None
    try:
        raw = target.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return raw or None


def ensure_web_token(path: Path | None = None) -> str:
    """Liest den Web-Schlüssel oder legt einen gültigen an. Ungültige Dateien werden ersetzt."""
    target = path or WEB_TOKEN_PATH
    existing = load_web_token(target)
    if existing and is_valid_secret(existing):
        return existing
    token = generate_secret()
    write_web_token(token, target)
    return token
