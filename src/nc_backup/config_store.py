"""Konfiguration laden und speichern."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field, fields
from typing import Any

from nc_backup.paths import SYSTEM_CONFIG_DIR, config_file, ensure_config_dir


@dataclass
class ScheduleConfig:
    enabled: bool = False
    hour: int = 2
    minute: int = 0
    weekdays: list[int] = field(default_factory=lambda: [0, 1, 2, 3, 4, 5, 6])


@dataclass
class AppConfig:
    install_mode: str = "native"  # native | docker | custom
    source_folders: list[str] = field(default_factory=list)
    export_path: str = ""
    config_php_path: str = ""
    docker_nextcloud_container: str = ""
    docker_db_container: str = ""
    include_database: bool = True
    encrypt_backups: bool = False
    gpg_mode: str = "symmetric"
    gpg_recipient: str = ""
    remove_plaintext_after_encrypt: bool = True
    backup_mode: str = "auto"  # auto | classic | stream_encrypted | incremental
    ui_language: str = "auto"  # auto | de | en
    api_token_hash: str | None = None
    password_hash: str | None = None
    schedule: ScheduleConfig = field(default_factory=ScheduleConfig)
    setup_complete: bool = False

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AppConfig:
        payload = dict(data)
        schedule_raw = payload.pop("schedule", {}) or {}
        if not isinstance(schedule_raw, dict):
            schedule_raw = {}
        schedule_known = {item.name for item in fields(ScheduleConfig)}
        schedule = ScheduleConfig(
            **{key: value for key, value in schedule_raw.items() if key in schedule_known}
        )
        known = {item.name for item in fields(cls) if item.name != "schedule"}
        filtered = {key: value for key, value in payload.items() if key in known}
        return cls(schedule=schedule, **filtered)


DEFAULT_NATIVE_PATHS = {
    "config_php": "/var/www/nextcloud/config/config.php",
    "data": "/var/www/nextcloud/data",
    "config_dir": "/var/www/nextcloud/config",
}

DEFAULT_DOCKER_HINTS = {
    "config_php": "",
    "data": "",
    "config_dir": "",
}


def default_config_for_mode(mode: str) -> AppConfig:
    cfg = AppConfig(install_mode=mode)
    if mode == "native":
        try:
            from nc_backup.path_discover import apply_discovered_paths, discover_paths_from_config_php

            discovery = discover_paths_from_config_php(DEFAULT_NATIVE_PATHS["config_php"])
            apply_discovered_paths(cfg, discovery)
        except (FileNotFoundError, ValueError, OSError):
            cfg.config_php_path = DEFAULT_NATIVE_PATHS["config_php"]
            cfg.source_folders = [
                DEFAULT_NATIVE_PATHS["data"],
                DEFAULT_NATIVE_PATHS["config_dir"],
            ]
    return cfg


def load_config() -> AppConfig:
    path = config_file()
    if not path.exists():
        return AppConfig()
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    return AppConfig.from_dict(data)


def save_config(config: AppConfig) -> None:
    directory = ensure_config_dir()
    path = directory / "config.json"
    payload = config.to_dict()
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    os.chmod(path, 0o660 if directory == SYSTEM_CONFIG_DIR else 0o600)


def config_needs_password(config: AppConfig) -> bool:
    return bool(config.password_hash)
