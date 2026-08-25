"""Hilfsfunktionen für Backup-Modi."""

from __future__ import annotations

from nc_backup.config_store import AppConfig


def effective_backup_mode(config: AppConfig) -> str:
    mode = (config.backup_mode or "auto").strip().lower()
    if mode == "auto":
        if config.encrypt_backups:
            return "stream_encrypted"
        return "incremental"
    if mode == "incremental" and config.encrypt_backups:
        return "stream_encrypted"
    return mode
