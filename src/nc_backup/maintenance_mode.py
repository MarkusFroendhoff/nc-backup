"""Nextcloud-Wartungsmodus per occ."""

from __future__ import annotations

import subprocess
from pathlib import Path

from nc_backup.config_store import AppConfig


class MaintenanceModeError(RuntimeError):
    pass


def _find_occ_path() -> str:
    for candidate in ("/var/www/nextcloud/occ", "/usr/local/bin/occ"):
        if Path(candidate).exists():
            return candidate
    return ""


def _occ_command(config: AppConfig, enable: bool) -> list[str]:
    flag = "--on" if enable else "--off"
    if config.install_mode == "docker" and config.docker_nextcloud_container:
        return [
            "docker", "exec", "-u", "www-data",
            config.docker_nextcloud_container,
            "php", "occ", "maintenance:mode", flag,
        ]

    occ_path = _find_occ_path()
    if not occ_path:
        raise MaintenanceModeError("occ nicht gefunden.")
    return ["sudo", "-u", "www-data", "php", occ_path, "maintenance:mode", flag]


def set_maintenance_mode(config: AppConfig, enabled: bool) -> None:
    command = _occ_command(config, enabled)
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        stderr = result.stderr.strip() or result.stdout.strip()
        state = "aktivieren" if enabled else "deaktivieren"
        raise MaintenanceModeError(f"Wartungsmodus konnte nicht {state} werden: {stderr}")
