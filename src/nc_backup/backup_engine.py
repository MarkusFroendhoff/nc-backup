"""Zentrale Backup-Logik."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from nc_backup.backup_mode import effective_backup_mode
from nc_backup.config_php import parse_config_php
from nc_backup.config_store import AppConfig
from nc_backup.db_dump import DatabaseDumpError, dump_database
from nc_backup.file_backup import (
    FileBackupError,
    backup_folders,
    backup_folders_incremental,
    create_backup_destination,
    create_incremental_snapshot,
    update_latest_snapshot_link,
)
from nc_backup.gpg_crypto import GpgError, encrypt_backup_directory
from nc_backup.paths import LOG_DIR
from nc_backup.space_check import check_backup_space
from nc_backup.stream_backup import run_stream_encrypted_backup

logger = logging.getLogger(__name__)


@dataclass
class BackupResult:
    success: bool
    destination: Path | None = None
    message: str = ""
    files_backed_up: list[str] = field(default_factory=list)
    database_dump: str | None = None
    encrypted_archive: str | None = None
    errors: list[str] = field(default_factory=list)


def setup_logging() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_file = LOG_DIR / "backup.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )


def validate_config(config: AppConfig) -> list[str]:
    errors: list[str] = []
    if not config.export_path:
        errors.append("Kein Export-Pfad konfiguriert.")
    if not config.source_folders:
        errors.append("Keine Quellordner ausgewählt.")
    if config.include_database and not config.config_php_path:
        errors.append("config.php-Pfad fehlt für Datenbank-Dump.")
    return errors


def run_backup(config: AppConfig, progress_callback=None) -> BackupResult:
    def report(percent: int, phase: str, detail: str = "") -> None:
        if progress_callback:
            progress_callback(percent, phase, detail)
        if detail:
            logger.info("%s – %s", phase, detail)

    validation_errors = validate_config(config)
    if validation_errors:
        return BackupResult(success=False, message="; ".join(validation_errors), errors=validation_errors)

    report(1, "Speicherplatz", "Quellgröße und freier Speicher werden geprüft…")
    space = check_backup_space(config)
    report(2, "Speicherplatz", space.message)
    if not space.ok:
        return BackupResult(success=False, message=space.message, errors=[space.message, *space.details])

    report(3, "Vorbereitung", "Backup-Ziel wird angelegt…")
    mode = effective_backup_mode(config)

    if mode == "stream_encrypted":
        return _run_stream_backup(config, report, errors=[])

    previous_snapshot = None
    try:
        if mode == "incremental":
            destination, previous_snapshot = create_incremental_snapshot(config.export_path)
            if previous_snapshot:
                report(4, "Inkrementell", f"Vorheriger Snapshot: {previous_snapshot.name}")
            else:
                report(4, "Inkrementell", "Erster Snapshot (volle Sicherung)")
        else:
            destination = create_backup_destination(config.export_path)
    except FileBackupError as exc:
        return BackupResult(success=False, message=str(exc), errors=[str(exc)])

    errors: list[str] = []
    files_backed_up: list[str] = []
    database_dump: str | None = None

    def file_progress(percent: int, phase: str, detail: str = "") -> None:
        report(percent, phase, detail)

    try:
        if mode == "incremental":
            backed = backup_folders_incremental(
                config.source_folders,
                destination,
                previous_snapshot,
                progress_callback=file_progress,
            )
        else:
            backed = backup_folders(config.source_folders, destination, progress_callback=file_progress)
        files_backed_up = [str(path) for path in backed]
        report(72, "Dateien", f"Fertig: {len(files_backed_up)} Ordner")
        logger.info("Dateien gesichert: %s", files_backed_up)
    except FileBackupError as exc:
        errors.append(str(exc))
        logger.error("Datei-Backup fehlgeschlagen: %s", exc)

    if config.include_database and config.config_php_path:
        report(75, "Datenbank", "Datenbank-Dump wird erstellt…")
        try:
            db_config = parse_config_php(config.config_php_path)
            dump_path = dump_database(
                db_config,
                destination / "database",
                docker_db_container=config.docker_db_container,
            )
            database_dump = str(dump_path)
            report(85, "Datenbank", f"Dump erstellt: {dump_path.name}")
            logger.info("Datenbank-Dump erstellt: %s", database_dump)
        except (DatabaseDumpError, FileNotFoundError, ValueError) as exc:
            errors.append(f"Datenbank-Dump: {exc}")
            logger.error("Datenbank-Dump fehlgeschlagen: %s", exc)

    folder_mapping = [
        {"source": source, "backup": backup}
        for source, backup in zip(config.source_folders, files_backed_up)
    ]
    report(88, "Manifest", "manifest.json wird geschrieben…")
    manifest = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "install_mode": config.install_mode,
        "source_folders": config.source_folders,
        "export_path": config.export_path,
        "files_backed_up": files_backed_up,
        "folder_mapping": folder_mapping,
        "database_dump": database_dump,
        "encrypted": config.encrypt_backups,
        "backup_mode": mode,
        "errors": errors,
    }
    manifest_path = destination / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    if mode == "incremental":
        snapshot_root = destination.parent
        update_latest_snapshot_link(snapshot_root, destination)
        report(89, "Inkrementell", f"Snapshot: {destination.name}")

    encrypted_archive: str | None = None
    final_destination = destination
    if config.encrypt_backups and mode == "classic" and (files_backed_up or database_dump):
        report(90, "Verschlüsselung", "GPG-Verschlüsselung läuft…")
        try:
            gpg_path = encrypt_backup_directory(destination, config)
            encrypted_archive = str(gpg_path)
            final_destination = gpg_path
            report(98, "Verschlüsselung", f"Fertig: {gpg_path.name}")
            logger.info("Backup verschlüsselt: %s", encrypted_archive)
        except GpgError as exc:
            errors.append(f"Verschlüsselung: {exc}")
            logger.error("Verschlüsselung fehlgeschlagen: %s", exc)

    if errors and not files_backed_up and not database_dump:
        return BackupResult(
            success=False,
            destination=destination,
            message="Backup fehlgeschlagen.",
            errors=errors,
        )

    if errors:
        return BackupResult(
            success=True,
            destination=final_destination,
            message="Backup mit Warnungen abgeschlossen.",
            files_backed_up=files_backed_up,
            database_dump=database_dump,
            encrypted_archive=encrypted_archive,
            errors=errors,
        )

    message = "Backup erfolgreich abgeschlossen."
    if mode == "incremental":
        message = "Inkrementelles Backup erfolgreich abgeschlossen."
    if encrypted_archive:
        message = "Backup erfolgreich verschlüsselt abgeschlossen."
    report(100, "Fertig", message)
    return BackupResult(
        success=True,
        destination=final_destination,
        message=message,
        files_backed_up=files_backed_up,
        database_dump=database_dump,
        encrypted_archive=encrypted_archive,
    )


def _run_stream_backup(config: AppConfig, report, errors: list[str]) -> BackupResult:
    def stream_progress(percent, phase, detail=""):
        mapped = 5 + int((percent / 100) * 93)
        report(mapped, phase, detail)

    try:
        gpg_path, files_backed_up, database_dump, stream_errors = run_stream_encrypted_backup(
            config,
            progress_callback=stream_progress,
        )
    except (FileBackupError, GpgError) as exc:
        return BackupResult(success=False, message=str(exc), errors=[str(exc)])

    all_errors = [*errors, *stream_errors]
    if all_errors and not files_backed_up and not database_dump:
        return BackupResult(
            success=False,
            destination=gpg_path,
            message="Stream-Backup fehlgeschlagen.",
            errors=all_errors,
        )

    message = "Stream-Backup erfolgreich (direkt verschlüsselt, ohne Pi-Zwischenspeicher)."
    if all_errors:
        message = "Stream-Backup mit Warnungen abgeschlossen."
    report(100, "Fertig", message)
    return BackupResult(
        success=True,
        destination=gpg_path,
        message=message,
        files_backed_up=files_backed_up,
        database_dump=database_dump,
        encrypted_archive=str(gpg_path),
        errors=all_errors,
    )
