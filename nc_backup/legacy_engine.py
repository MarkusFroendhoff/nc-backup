"""Klassisches Vollbackup (tar.gz) — kompatibel zu Bash-Skripten."""

from __future__ import annotations

import gzip
import os
import shutil
import subprocess
import tarfile
from datetime import datetime, timedelta
from pathlib import Path

from nc_backup.logutil import log
from nc_backup.models import AppConfig
from nc_backup.mariadb import dump_database


def run_legacy_backup(cfg: AppConfig) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    root = Path(cfg.destination.legacy_root)
    dest = root / stamp
    dest.mkdir(parents=True, exist_ok=True)

    sql = dest / "database.sql"
    dump_database(cfg, sql)
    with sql.open("rb") as f_in, gzip.open(f"{sql}.gz", "wb") as f_out:
        shutil.copyfileobj(f_in, f_out)
    sql.unlink()

    data_archive = dest / "nextcloud-data.tar.gz"
    log(f"Dateidaten archivieren …")
    subprocess.run(
        [
            "tar",
            "-czf",
            str(data_archive),
            "-C",
            str(Path(cfg.nextcloud.data_dir).parent),
            Path(cfg.nextcloud.data_dir).name,
        ],
        check=True,
    )

    config_archive = dest / "nextcloud-config.tar.gz"
    subprocess.run(
        [
            "tar",
            "-czf",
            str(config_archive),
            "-C",
            cfg.nextcloud.install_dir,
            "config",
        ],
        check=True,
    )

    _prune(root, cfg.destination.legacy_retention_days)
    log(f"Legacy-Backup abgeschlossen: {dest}")
    return dest


def _prune(root: Path, days: int) -> None:
    if days <= 0:
        return
    cutoff = datetime.now() - timedelta(days=days)
    for child in root.iterdir():
        if not child.is_dir():
            continue
        try:
            mtime = datetime.fromtimestamp(child.stat().st_mtime)
            if mtime < cutoff:
                shutil.rmtree(child)
                log(f"Gelöscht: {child}")
        except OSError:
            pass
