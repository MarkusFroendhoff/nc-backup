"""Backup-Orchestrierung."""

from __future__ import annotations

from nc_backup.config_store import load_config
from nc_backup.legacy_engine import run_legacy_backup
from nc_backup.logutil import log, log_error
from nc_backup.models import AppConfig, BackupMode, Provider
from nc_backup.nextcloud import maintenance, verify_paths
from nc_backup.restic_backend import run_incremental_backup
from nc_backup.rclone_backend import sync_local_repo, write_rclone_config


def validate(cfg: AppConfig) -> list[str]:
    errors = verify_paths(cfg)
    if not hasattr(cfg, "database") or not hasattr(cfg, "destination"):
        errors.append("Konfiguration unvollständig (Format 1.7). Bitte Einrichtung speichern.")
        return errors
    if not cfg.database.user or not cfg.database.name:
        errors.append("Datenbank: Benutzer und Datenbankname sind Pflicht.")
    dest = cfg.destination
    if dest.mode == BackupMode.INCREMENTAL:
        if not dest.restic_password:
            errors.append("Restic-Passwort fehlt (verschlüsselt das Backup-Repository).")
        if dest.provider == Provider.S3 and (not dest.s3_bucket or not dest.s3_access_key):
            errors.append("S3: Bucket und Zugangsschlüssel angeben.")
        if dest.provider == Provider.SFTP and (not dest.sftp_host or not dest.sftp_user):
            errors.append("SFTP: Host und Benutzer angeben.")
        if dest.provider == Provider.WEBDAV and not dest.webdav_url:
            errors.append("WebDAV: URL angeben.")
        if dest.provider == Provider.AZURE and (not dest.azure_account or not dest.azure_key):
            errors.append("Azure: Storage-Account und Key angeben.")
        if dest.provider == Provider.B2 and (not dest.b2_account_id or not dest.b2_bucket):
            errors.append("Backblaze B2: Account ID und Bucket angeben.")
        if dest.provider == Provider.RCLONE and not dest.rclone_remote:
            errors.append("Rclone: Remote-Namen angeben (rclone config).")
    return errors


def run_backup(cfg: AppConfig | None = None) -> int:
    cfg = cfg or load_config()
    errors = validate(cfg)
    if errors:
        for e in errors:
            log_error(e)
        return 1

    try:
        maintenance(cfg, True)
        if cfg.destination.mode == BackupMode.LEGACY:
            run_legacy_backup(cfg)
        else:
            run_incremental_backup(cfg)
            if cfg.destination.provider in (Provider.WEBDAV, Provider.RCLONE):
                write_rclone_config(cfg)
                sync_local_repo(cfg)
        log("=== Backup erfolgreich ===")
        return 0
    except Exception as exc:
        log_error(str(exc))
        return 1
    finally:
        maintenance(cfg, False)
