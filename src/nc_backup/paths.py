"""Standardpfade und Konfigurationsorte."""

from __future__ import annotations

import os
from pathlib import Path

APP_NAME = "nc-backup"
SYSTEM_CONFIG_DIR = Path("/etc/nc-backup")
USER_CONFIG_DIR = Path.home() / ".config" / APP_NAME
LOG_DIR = Path("/var/log/nc-backup")


def config_dir() -> Path:
    env_dir = os.environ.get("NC_BACKUP_CONFIG_DIR")
    if env_dir:
        return Path(env_dir)
    if SYSTEM_CONFIG_DIR.exists():
        return SYSTEM_CONFIG_DIR
    if SYSTEM_CONFIG_DIR.joinpath("config.json").exists():
        return SYSTEM_CONFIG_DIR
    return USER_CONFIG_DIR


def config_file() -> Path:
    return config_dir() / "config.json"


def ensure_config_dir() -> Path:
    directory = config_dir()
    directory.mkdir(parents=True, exist_ok=True)
    if directory == SYSTEM_CONFIG_DIR:
        os.chmod(directory, 0o750)
    return directory
