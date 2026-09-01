"""Wiederherstellung aus Restic-Snapshots."""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from nc_backup.detect import parse_dbhost
from nc_backup.logutil import log
from nc_backup.models import AppConfig, BackupMode
from nc_backup.nextcloud import maintenance
from nc_backup.restic_backend import SnapshotInfo, list_snapshots, restore_snapshot
from nc_backup.runner import which


@dataclass
class RestoreOptions:
    restore_database: bool = True
    restore_config: bool = True
    restore_data: bool = False
    snapshot_id: str = ""


def find_sql_dump(root: Path) -> Path | None:
    for candidate in root.rglob("nextcloud.sql"):
        if candidate.is_file():
            return candidate
    return None


def find_config_tree(root: Path) -> Path | None:
    for candidate in root.rglob("config.php"):
        return candidate.parent
    # Backup-Layout: config/config/...
    p = root / "config" / "config"
    if (p / "config.php").is_file():
        return p
    p = root / "config"
    if (p / "config.php").is_file():
        return p
    return None


def _import_database(cfg: AppConfig, sql_file: Path) -> None:
    if which("mysql") is None:
        raise RuntimeError("mysql-Client nicht installiert (Paket mariadb-client)")
    db = cfg.database
    env = os.environ.copy()
    if db.password:
        env["MYSQL_PWD"] = db.password
    host, port_from_host = parse_dbhost(db.host or "localhost")
    if host.startswith("/") or host.endswith(".sock"):
        cmd = ["mysql", "-S", host, "-u", db.user, db.name]
    else:
        cmd = [
            "mysql",
            "-h",
            host,
            "-P",
            str(port_from_host or db.port or 3306),
            "-u",
            db.user,
            db.name,
        ]
    log(f"Importiere Datenbank aus {sql_file} …")
    with sql_file.open("rb") as fh:
        subprocess.run(cmd, env=env, stdin=fh, check=True)
    log("Datenbank importiert.")


def _restore_config(cfg: AppConfig, config_src: Path) -> None:
    dest = Path(cfg.nextcloud.install_dir) / "config"
    backup = dest.with_suffix(".bak-before-restore")
    if dest.exists() and not backup.exists():
        shutil.copytree(dest, backup)
        log(f"Alte Config gesichert unter {backup}")
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(config_src, dest)
    log(f"Konfiguration wiederhergestellt nach {dest}")


def _restore_data(cfg: AppConfig, restore_root: Path) -> None:
    data_path = Path(cfg.nextcloud.data_dir).resolve()
    # Restic speichert den absoluten Pfad
    source = restore_root / str(data_path)
    if not source.is_dir():
        # Fallback: data/ im Snapshot-Stamm
        for name in ("data", data_path.name):
            alt = restore_root / name
            if alt.is_dir():
                source = alt
                break
        else:
            raise FileNotFoundError(
                f"Datenverzeichnis im Snapshot nicht gefunden (gesucht: {data_path})"
            )
    log(f"Kopiere Dateidaten nach {data_path} …")
    if data_path.exists():
        staging_old = data_path.with_name(data_path.name + ".old-restore")
        if staging_old.exists():
            shutil.rmtree(staging_old)
        data_path.rename(staging_old)
        log(f"Bestehende Daten umbenannt nach {staging_old}")
    shutil.copytree(source, data_path)
    log("Dateidaten wiederhergestellt.")


def run_restore(cfg: AppConfig, options: RestoreOptions) -> None:
    if not options.snapshot_id:
        raise ValueError("Kein Snapshot ausgewählt")
    if not any(
        (options.restore_database, options.restore_config, options.restore_data)
    ):
        raise ValueError("Mindestens eine Komponente zum Wiederherstellen wählen")

    import tempfile

    staging = Path(tempfile.mkdtemp(prefix="nc-restore-"))
    try:
        maintenance(cfg, True)
        restore_snapshot(cfg, options.snapshot_id, staging)

        if options.restore_database:
            sql = find_sql_dump(staging)
            if not sql:
                raise FileNotFoundError("Keine nextcloud.sql im Snapshot gefunden")
            _import_database(cfg, sql)

        if options.restore_config:
            config_src = find_config_tree(staging)
            if not config_src:
                raise FileNotFoundError("Keine config.php im Snapshot gefunden")
            _restore_config(cfg, config_src)

        if options.restore_data:
            _restore_data(cfg, staging)

        log("=== Wiederherstellung abgeschlossen ===")
    finally:
        shutil.rmtree(staging, ignore_errors=True)
        maintenance(cfg, False)


def get_snapshots(cfg: AppConfig) -> list[SnapshotInfo]:
    if cfg.destination.mode != BackupMode.INCREMENTAL:
        raise RuntimeError("Wiederherstellung nur für inkrementelle (Restic) Backups")
    return list_snapshots(cfg)
