"""Wiederherstellungs-Passwort: erzeugen und prüfen."""

from __future__ import annotations

import secrets
import string

UPPER = string.ascii_uppercase
LOWER = string.ascii_lowercase
DIGIT = string.digits
SPECIAL = "!#$%&*+-=?@^_"
ALPHABET = UPPER + LOWER + DIGIT + SPECIAL
MIN_LENGTH = 16
GEN_LENGTH = 24


def password_requirements(pw: str) -> list[str]:
    """Welche Pflicht-Bestandteile fehlen (deutsche Kurztexte)."""
    missing: list[str] = []
    if len(pw) < MIN_LENGTH:
        missing.append(f"mindestens {MIN_LENGTH} Zeichen")
    if not any(c in UPPER for c in pw):
        missing.append("einen Großbuchstaben")
    if not any(c in LOWER for c in pw):
        missing.append("einen Kleinbuchstaben")
    if not any(c in DIGIT for c in pw):
        missing.append("eine Ziffer")
    if not any(c in SPECIAL for c in pw):
        missing.append("ein Sonderzeichen (!#$%&*+-=?@^_)")
    return missing


def is_strong_password(pw: str) -> bool:
    return not password_requirements(pw)


def password_error_message(pw: str) -> str | None:
    missing = password_requirements(pw)
    if not missing:
        return None
    if not (pw or "").strip():
        return (
            "Ein Wiederherstellungs-Passwort ist Pflicht. "
            "Es braucht Groß- und Kleinbuchstaben, eine Ziffer und ein Sonderzeichen."
        )
    if len(missing) == 1:
        return f"Das Wiederherstellungs-Passwort braucht {missing[0]}."
    return (
        "Das Wiederherstellungs-Passwort braucht "
        + ", ".join(missing[:-1])
        + " und "
        + missing[-1]
        + "."
    )


def generate_restic_password(length: int = GEN_LENGTH) -> str:
    """~24 Zeichen mit Groß-, Kleinbuchstaben, Ziffer und Sonderzeichen."""
    n = max(length, 4)
    chars = [
        secrets.choice(UPPER),
        secrets.choice(LOWER),
        secrets.choice(DIGIT),
        secrets.choice(SPECIAL),
    ]
    chars.extend(secrets.choice(ALPHABET) for _ in range(n - 4))
    secrets.SystemRandom().shuffle(chars)
    pw = "".join(chars)
    if not is_strong_password(pw):
        return generate_restic_password(length)
    return pw
