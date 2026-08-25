"""Geschützte Speicherung der GPG-Passphrase für geplante Backups."""

from __future__ import annotations

import json
import os
from pathlib import Path

from nc_backup.paths import SYSTEM_CONFIG_DIR, config_dir, ensure_config_dir


def secrets_file() -> Path:
    return config_dir() / "secrets.json"


def load_secrets() -> dict:
    path = secrets_file()
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def load_gpg_passphrase() -> str:
    return load_secrets().get("gpg_passphrase", "")


def save_gpg_passphrase(passphrase: str) -> None:
    directory = ensure_config_dir()
    path = directory / "secrets.json"
    payload = load_secrets()
    payload["gpg_passphrase"] = passphrase
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    os.chmod(path, 0o600 if directory == SYSTEM_CONFIG_DIR else 0o600)


def clear_gpg_passphrase() -> None:
    path = secrets_file()
    if not path.exists():
        return
    payload = load_secrets()
    payload.pop("gpg_passphrase", None)
    if payload:
        with path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        os.chmod(path, 0o600)
    else:
        path.unlink(missing_ok=True)
