"""Inkrementelle Backups mit Restic."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from nc_backup.logutil import log
from nc_backup.models import AppConfig, Provider
from nc_backup.runner import run, which

# Feste Pfade, damit Restic Parent-Snapshots erkennt (kein /tmp/nc-backup-* pro Lauf).
STAGING_ROOT = Path("/var/lib/nc-backup/staging")


@dataclass
class SnapshotInfo:
    id: str
    short_id: str
    time: str
    hostname: str
    tags: list[str]


def _restic_env(cfg: AppConfig) -> dict[str, str]:
    dest = cfg.destination
    env = os.environ.copy()
    pw = dest.restic_password
    if not pw:
        raise ValueError("Restic-Passwort fehlt (Repository-Verschlüsselung)")
    env["RESTIC_PASSWORD"] = pw

    repo = repository_url(cfg)
    env["RESTIC_REPOSITORY"] = repo

    if dest.provider == Provider.S3:
        env["AWS_ACCESS_KEY_ID"] = dest.s3_access_key
        env["AWS_SECRET_ACCESS_KEY"] = dest.s3_secret_key
        if dest.s3_region:
            env["AWS_DEFAULT_REGION"] = dest.s3_region
    elif dest.provider == Provider.AZURE:
        env["AZURE_ACCOUNT_NAME"] = dest.azure_account
        env["AZURE_ACCOUNT_KEY"] = dest.azure_key
    elif dest.provider == Provider.B2:
        env["B2_ACCOUNT_ID"] = dest.b2_account_id
        env["B2_ACCOUNT_KEY"] = dest.b2_account_key

    if dest.provider == Provider.SFTP and dest.sftp_password:
        env["SSHPASS"] = dest.sftp_password

    return env


def repository_url(cfg: AppConfig) -> str:
    d = cfg.destination
    p = d.provider
    if p in (Provider.WEBDAV, Provider.RCLONE):
        Path(d.local_path).mkdir(parents=True, exist_ok=True)
        return str(Path(d.local_path).resolve())
    if p == Provider.LOCAL:
        Path(d.local_path).mkdir(parents=True, exist_ok=True)
        return str(Path(d.local_path).resolve())
    if p == Provider.SFTP:
        port = f":{d.sftp_port}" if d.sftp_port != 22 else ""
        return f"sftp:{d.sftp_user}@{d.sftp_host}{port}:{d.sftp_path}"
    if p == Provider.S3:
        prefix = d.s3_prefix.strip("/")
        path = f"{d.s3_bucket}/{prefix}" if prefix else d.s3_bucket
        return f"s3:{d.s3_endpoint}/{path}"
    if p == Provider.AZURE:
        return f"azure:{d.azure_container}/{d.azure_prefix}"
    if p == Provider.B2:
        return f"b2:{d.b2_bucket}/{d.b2_prefix}"
    raise ValueError(f"Provider {p.value} nutzt kein Restic-Repository direkt")


def ensure_repository(cfg: AppConfig) -> None:
    if which("restic") is None:
        raise RuntimeError("restic nicht installiert — siehe README")
    env = _restic_env(cfg)
    snapshots = run(["restic", "snapshots"], env=env, check=False)
    if snapshots.returncode == 0:
        return
    log("Restic-Repository wird initialisiert …")
    run(["restic", "init"], env=env)


def list_snapshots(cfg: AppConfig) -> list[SnapshotInfo]:
    if which("restic") is None:
        raise RuntimeError("restic nicht installiert")
    env = _restic_env(cfg)
    proc = subprocess.run(
        ["restic", "snapshots", "--json"],
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    raw = json.loads(proc.stdout or "[]")
    result: list[SnapshotInfo] = []
    for item in raw:
        result.append(
            SnapshotInfo(
                id=item["id"],
                short_id=item["short_id"],
                time=item["time"],
                hostname=item.get("hostname", ""),
                tags=item.get("tags") or [],
            )
        )
    result.sort(key=lambda s: s.time, reverse=True)
    return result


def restore_snapshot(cfg: AppConfig, snapshot_id: str, target: Path) -> None:
    env = _restic_env(cfg)
    target.mkdir(parents=True, exist_ok=True)
    log(f"Restic restore {snapshot_id} → {target}")
    run(["restic", "restore", snapshot_id, "--target", str(target)], env=env)


def _prepare_staging_dirs() -> tuple[Path, Path]:
    if STAGING_ROOT.exists():
        shutil.rmtree(STAGING_ROOT)
    db_dir = STAGING_ROOT / "database"
    cfg_dir = STAGING_ROOT / "config"
    db_dir.mkdir(parents=True)
    cfg_dir.mkdir(parents=True)
    return db_dir, cfg_dir


def _latest_snapshot_id(env: dict[str, str]) -> str | None:
    """Neueste Snapshot-ID, ohne Pfad-Filter (restic 'latest' verlangt gleiche Pfade)."""
    snapshots = run(["restic", "snapshots", "--json"], env=env, check=False)
    if snapshots.returncode != 0:
        return None
    try:
        raw = json.loads(snapshots.stdout or "[]")
    except json.JSONDecodeError:
        return None
    if not isinstance(raw, list) or not raw:
        return None
    raw.sort(key=lambda s: str(s.get("time") or ""), reverse=True)
    sid = raw[0].get("id") or raw[0].get("short_id")
    return str(sid) if sid else None


def backup_paths(cfg: AppConfig, paths: list[Path], tag: str) -> None:
    env = _restic_env(cfg)
    cmd = [
        "restic",
        "backup",
        "--tag",
        tag,
        "--host",
        os.uname().nodename,
    ]
    parent = _latest_snapshot_id(env)
    if parent:
        cmd.extend(["--parent", parent])
        log(f"Restic-Parent: {parent[:12]}")
    cmd.extend(str(p) for p in paths)
    run(cmd, env=env)
    _apply_retention(cfg, env)


def _apply_retention(cfg: AppConfig, env: dict[str, str]) -> None:
    r = cfg.destination.retention
    cmd = [
        "restic",
        "forget",
        "--prune",
        "--keep-daily",
        str(r.keep_daily),
        "--keep-weekly",
        str(r.keep_weekly),
        "--keep-monthly",
        str(r.keep_monthly),
    ]
    run(cmd, env=env)
    log("Aufbewahrungsregeln angewendet.")


def run_incremental_backup(cfg: AppConfig) -> None:
    """Staging mit DB + Config, Restic-Backup inkl. Datenverzeichnis."""
    ensure_repository(cfg)
    stamp = __import__("datetime").datetime.now().strftime("%Y%m%d-%H%M%S")
    db_dir, cfg_dir = _prepare_staging_dirs()

    from nc_backup.mariadb import dump_database

    dump_database(cfg, db_dir / "nextcloud.sql")

    nc_config = Path(cfg.nextcloud.install_dir) / "config"
    if nc_config.is_dir():
        shutil.copytree(nc_config, cfg_dir / "config", dirs_exist_ok=True)
    else:
        container = (getattr(cfg.nextcloud, "container", "") or "").strip()
        if container:
            from nc_backup.docker_detect import copy_config_from_container

            if copy_config_from_container(container, cfg_dir / "config"):
                log(f"config/ aus Container {container} kopiert.")
            else:
                log(
                    "config/ liegt nicht auf dem Host und konnte nicht "
                    f"aus dem Container {container} kopiert werden."
                )

    paths = [db_dir, cfg_dir, Path(cfg.nextcloud.data_dir)]
    backup_paths(cfg, paths, tag=f"nc-backup-{stamp}")
    log(f"Inkrementelles Backup abgeschlossen (Snapshot-Tag: nc-backup-{stamp}).")
