"""Pfad-Erkennung aus Nextcloud config.php."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from nc_backup.config_php import parse_config_php

COMMON_CONFIG_PHP_PATHS = [
    "/var/www/nextcloud/config/config.php",
    "/var/www/html/nextcloud/config/config.php",
    "/var/www/html/config/config.php",
    "/opt/nextcloud/config/config.php",
    "/srv/nextcloud/config/config.php",
]


@dataclass
class PathDiscovery:
    config_php_path: str
    data_directory: str = ""
    config_directory: str = ""
    source_folders: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def summary(self) -> str:
        lines = [
            f"config.php: {self.config_php_path}",
            f"Daten: {self.data_directory or '–'}",
            f"Config-Ordner: {self.config_directory or '–'}",
        ]
        lines.extend(f"• {note}" for note in self.notes)
        return "\n".join(lines)


def find_config_php(preferred: str = "") -> str:
    candidates = []
    if preferred:
        candidates.append(preferred)
    candidates.extend(COMMON_CONFIG_PHP_PATHS)
    for path in candidates:
        if Path(path).is_file():
            return path
    return preferred or COMMON_CONFIG_PHP_PATHS[0]


def discover_paths_from_config_php(config_php_path: str = "") -> PathDiscovery:
    """Liest datadirectory und Config-Ordner aus config.php."""
    resolved = find_config_php(config_php_path)
    if not Path(resolved).is_file():
        raise FileNotFoundError(
            "config.php nicht gefunden. Bitte Pfad manuell setzen "
            "(z. B. /var/www/nextcloud/config/config.php)."
        )

    parsed = parse_config_php(resolved)
    config_dir = str(Path(resolved).parent)
    data_dir = (parsed.datadirectory or "").rstrip("/")
    notes: list[str] = []
    folders: list[str] = []

    if data_dir:
        if Path(data_dir).is_dir():
            folders.append(data_dir)
            notes.append(f"datadirectory aus config.php: {data_dir}")
        else:
            notes.append(f"datadirectory gesetzt, Ordner fehlt aber: {data_dir}")
            folders.append(data_dir)
    else:
        notes.append("Kein 'datadirectory' in config.php gefunden.")

    if Path(config_dir).is_dir() and config_dir not in folders:
        folders.append(config_dir)
        notes.append(f"Config-Ordner: {config_dir}")

    return PathDiscovery(
        config_php_path=resolved,
        data_directory=data_dir,
        config_directory=config_dir,
        source_folders=folders,
        notes=notes,
    )


def apply_discovered_paths(config, discovery: PathDiscovery):
    """Schreibt erkannte Pfade in die AppConfig."""
    config.config_php_path = discovery.config_php_path
    if discovery.source_folders:
        config.source_folders = discovery.source_folders
    return config
