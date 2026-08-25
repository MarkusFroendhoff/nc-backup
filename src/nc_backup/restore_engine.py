"""Backup-Analyse und Wiederherstellung."""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from nc_backup.config_php import NextcloudDbConfig, parse_config_php
from nc_backup.config_store import AppConfig
from nc_backup.db_dump import DatabaseDumpError
from nc_backup.file_backup import FileBackupError, rsync_folder
from nc_backup.gpg_crypto import GpgError, open_encrypted_backup
from nc_backup.maintenance_mode import MaintenanceModeError, set_maintenance_mode

logger = logging.getLogger(__name__)


@dataclass
class RestoreOptions:
    restore_files: bool = True
    restore_database: bool = True
    maintenance_mode: bool = True
    delete_extra_files: bool = False
    gpg_passphrase: str = ""


@dataclass
class BackupInfo:
    path: Path
    encrypted: bool
    created_at: str = ""
    install_mode: str = ""
    source_folders: list[str] = field(default_factory=list)
    folder_mapping: list[dict[str, str]] = field(default_factory=list)
    database_dump: str | None = None
    manifest_errors: list[str] = field(default_factory=list)
    summary: str = ""


@dataclass
class RestoreResult:
    success: bool
    message: str = ""
    errors: list[str] = field(default_factory=list)
    restored_folders: list[str] = field(default_factory=list)
    restored_database: str | None = None


def is_encrypted_backup(path: Path) -> bool:
    name = path.name.lower()
    return path.is_file() and name.endswith(".gpg")


def resolve_backup_directory(
    path: Path,
    gpg_passphrase: str = "",
) -> tuple[Path, tempfile.TemporaryDirectory | None]:
    if path.is_dir():
        if (path / "manifest.json").exists():
            return path, None
        raise FileBackupError(f"Kein gültiges Backup (manifest.json fehlt): {path}")

    if is_encrypted_backup(path):
        if not gpg_passphrase:
            raise GpgError("Passphrase für verschlüsseltes Backup erforderlich.")
        temp_dir = tempfile.TemporaryDirectory(prefix="nc-backup-restore-")
        extracted = open_encrypted_backup(path, gpg_passphrase, Path(temp_dir.name))
        return extracted, temp_dir

    raise FileBackupError("Unbekanntes Backup-Format. Erwartet: Ordner oder .gpg-Archiv.")


def inspect_backup_directory(backup_dir: Path, original_path: Path, encrypted: bool) -> BackupInfo:
    manifest_path = backup_dir / "manifest.json"
    if not manifest_path.exists():
        raise FileBackupError("manifest.json nicht gefunden.")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    folder_mapping = manifest.get("folder_mapping") or _infer_folder_mapping(
        manifest.get("source_folders", []),
        backup_dir,
    )
    database_dump = _resolve_database_dump_path(backup_dir, manifest.get("database_dump"))

    return BackupInfo(
        path=original_path,
        encrypted=encrypted,
        created_at=manifest.get("created_at", ""),
        install_mode=manifest.get("install_mode", ""),
        source_folders=manifest.get("source_folders", []),
        folder_mapping=folder_mapping,
        database_dump=database_dump,
        manifest_errors=manifest.get("errors", []),
        summary=_build_summary(manifest, folder_mapping, database_dump),
    )


def load_backup_info(path: Path, gpg_passphrase: str = "") -> BackupInfo:
    backup_dir, temp = resolve_backup_directory(path, gpg_passphrase=gpg_passphrase)
    try:
        return inspect_backup_directory(backup_dir, path, is_encrypted_backup(path))
    finally:
        if temp is not None:
            temp.cleanup()


def _resolve_database_dump_path(backup_dir: Path, manifest_value: str | None) -> str | None:
    if manifest_value:
        candidate = Path(manifest_value)
        if candidate.is_file():
            return str(candidate)
        by_name = backup_dir / "database" / candidate.name
        if by_name.is_file():
            return str(by_name)
    return _find_database_dump(backup_dir)


def _find_database_dump(backup_dir: Path) -> str | None:
    db_dir = backup_dir / "database"
    if not db_dir.is_dir():
        return None
    candidates = sorted(db_dir.glob("database_*"))
    return str(candidates[-1]) if candidates else None


def _infer_folder_mapping(source_folders: list[str], backup_dir: Path) -> list[dict[str, str]]:
    mapping: list[dict[str, str]] = []
    files_root = backup_dir / "files"
    if not files_root.is_dir():
        return mapping

    by_name = {path.name: str(path) for path in files_root.iterdir() if path.is_dir()}
    for source in source_folders:
        backup = by_name.get(Path(source).name)
        if backup:
            mapping.append({"source": source, "backup": backup})

    if not mapping:
        for folder in files_root.iterdir():
            if folder.is_dir():
                mapping.append({"source": "", "backup": str(folder)})
    return mapping


def _build_summary(manifest: dict, folder_mapping: list[dict[str, str]], database_dump: str | None) -> str:
    lines = [
        f"Erstellt: {manifest.get('created_at', 'unbekannt')}",
        f"Modus: {manifest.get('install_mode', 'unbekannt')}",
        f"Ordner: {len(folder_mapping)}",
        f"Datenbank: {'ja' if database_dump else 'nein'}",
    ]
    if manifest.get("encrypted"):
        lines.append("Verschlüsselung: ja")
    for entry in folder_mapping:
        source = entry.get("source") or "(aus Einstellungen)"
        lines.append(f"  • {source} ← {entry.get('backup', '')}")
    return "\n".join(lines)


def run_restore(config: AppConfig, backup_path: Path, options: RestoreOptions) -> RestoreResult:
    errors: list[str] = []
    restored_folders: list[str] = []
    restored_database: str | None = None
    temp_holder: tempfile.TemporaryDirectory | None = None
    maintenance_enabled = False

    try:
        backup_dir, temp_holder = resolve_backup_directory(
            backup_path,
            gpg_passphrase=options.gpg_passphrase,
        )
        info = inspect_backup_directory(backup_dir, backup_path, is_encrypted_backup(backup_path))

        if options.maintenance_mode:
            try:
                set_maintenance_mode(config, True)
                maintenance_enabled = True
            except MaintenanceModeError as exc:
                errors.append(str(exc))

        if options.restore_files:
            mapping = info.folder_mapping or _infer_folder_mapping(info.source_folders, backup_dir)
            for entry in mapping:
                source_target = entry.get("source") or _match_source_from_config(entry.get("backup", ""), config)
                backup_source = entry.get("backup", "")
                if not source_target:
                    errors.append(f"Kein Zielpfad für Backup-Ordner: {backup_source}")
                    continue
                if not backup_source or not Path(backup_source).exists():
                    errors.append(f"Backup-Ordner fehlt: {backup_source}")
                    continue
                try:
                    rsync_folder(
                        Path(backup_source),
                        Path(source_target),
                        delete_extra=options.delete_extra_files,
                    )
                    restored_folders.append(source_target)
                    logger.info("Wiederhergestellt: %s -> %s", backup_source, source_target)
                except FileBackupError as exc:
                    errors.append(str(exc))

        if options.restore_database and info.database_dump:
            try:
                restore_database_dump(Path(info.database_dump), config)
                restored_database = info.database_dump
            except DatabaseDumpError as exc:
                errors.append(str(exc))

        if maintenance_enabled:
            try:
                set_maintenance_mode(config, False)
            except MaintenanceModeError as exc:
                errors.append(str(exc))

        if errors and not restored_folders and not restored_database:
            return RestoreResult(success=False, message="Wiederherstellung fehlgeschlagen.", errors=errors)

        message = "Wiederherstellung abgeschlossen."
        if errors:
            message = "Wiederherstellung mit Warnungen abgeschlossen."
        return RestoreResult(
            success=True,
            message=message,
            errors=errors,
            restored_folders=restored_folders,
            restored_database=restored_database,
        )
    except (FileBackupError, GpgError) as exc:
        if maintenance_enabled:
            try:
                set_maintenance_mode(config, False)
            except MaintenanceModeError:
                pass
        return RestoreResult(success=False, message=str(exc), errors=[str(exc)])
    finally:
        if temp_holder is not None:
            temp_holder.cleanup()


def _match_source_from_config(backup_folder: str, config: AppConfig) -> str:
    backup_name = Path(backup_folder).name
    for source in config.source_folders:
        if Path(source).name == backup_name:
            return source
    return ""


def restore_database_dump(dump_path: Path, config: AppConfig) -> None:
    if not config.config_php_path:
        raise DatabaseDumpError("config.php-Pfad fehlt für Datenbank-Restore.")
    db_config = parse_config_php(config.config_php_path)
    dbtype = db_config.dbtype

    if dbtype in ("mysql", "mariadb"):
        _restore_mysql(dump_path, db_config, config.docker_db_container)
        return
    if dbtype in ("pgsql", "postgres", "postgresql"):
        _restore_postgres(dump_path, db_config, config.docker_db_container)
        return
    if dbtype == "sqlite":
        _restore_sqlite(dump_path, db_config)
        return
    raise DatabaseDumpError(f"Unbekannter Datenbanktyp: {dbtype}")


def _restore_mysql(dump_path: Path, db_config: NextcloudDbConfig, docker_db_container: str) -> None:
    if docker_db_container:
        env_args: list[str] = []
        if db_config.dbpassword:
            env_args = ["-e", f"MYSQL_PWD={db_config.dbpassword}"]
        command = [
            "docker", "exec", *env_args, "-i", docker_db_container,
            "mysql", "-u", db_config.dbuser, db_config.dbname,
        ]
        with dump_path.open("rb") as handle:
            result = subprocess.run(command, stdin=handle, capture_output=True, check=False)
    else:
        import os

        env = os.environ.copy()
        if db_config.dbpassword:
            env["MYSQL_PWD"] = db_config.dbpassword
        host = db_config.dbhost.split(":")[0]
        port = db_config.dbhost.split(":")[1] if ":" in db_config.dbhost else None
        binary = shutil.which("mysql") or shutil.which("mariadb")
        if not binary:
            raise DatabaseDumpError("mysql/mariadb-Client nicht installiert.")
        command = [binary, "-h", host, "-u", db_config.dbuser, db_config.dbname]
        if port:
            command.extend(["-P", port])
        with dump_path.open("rb") as handle:
            result = subprocess.run(command, stdin=handle, capture_output=True, env=env, check=False)
    if result.returncode != 0:
        raise DatabaseDumpError(result.stderr.decode("utf-8", errors="replace"))


def _restore_postgres(dump_path: Path, db_config: NextcloudDbConfig, docker_db_container: str) -> None:
    if docker_db_container:
        env_args: list[str] = []
        if db_config.dbpassword:
            env_args = ["-e", f"PGPASSWORD={db_config.dbpassword}"]
        command = [
            "docker", "exec", *env_args, "-i", docker_db_container,
            "psql", "-U", db_config.dbuser, "-d", db_config.dbname,
        ]
        with dump_path.open("r", encoding="utf-8") as handle:
            result = subprocess.run(command, stdin=handle, capture_output=True, text=True, check=False)
    else:
        import os

        env = os.environ.copy()
        if db_config.dbpassword:
            env["PGPASSWORD"] = db_config.dbpassword
        host = db_config.dbhost.split(":")[0]
        port = db_config.dbhost.split(":")[1] if ":" in db_config.dbhost else "5432"
        command = ["psql", "-h", host, "-p", port, "-U", db_config.dbuser, "-d", db_config.dbname]
        with dump_path.open("r", encoding="utf-8") as handle:
            result = subprocess.run(command, stdin=handle, capture_output=True, text=True, env=env, check=False)
    if result.returncode != 0:
        raise DatabaseDumpError(result.stderr or result.stdout or "PostgreSQL-Restore fehlgeschlagen")


def _restore_sqlite(dump_path: Path, db_config: NextcloudDbConfig) -> None:
    from nc_backup.db_dump import _resolve_sqlite_path

    target = _resolve_sqlite_path(db_config)
    shutil.copy2(dump_path, target)
