"""Sync zu WebDAV und weiteren Rclone-Zielen nach lokalem Restic-Repo."""

from __future__ import annotations

import configparser
import os
from pathlib import Path

from nc_backup.logutil import log
from nc_backup.models import AppConfig, Provider
from nc_backup.runner import run, which

RCLONE_CONF = Path("/etc/nc-backup/rclone.conf")


def write_rclone_config(cfg: AppConfig) -> None:
    """Schreibt /etc/nc-backup/rclone.conf für WebDAV/Rclone-Provider."""
    dest = cfg.destination
    if dest.provider not in (Provider.WEBDAV, Provider.RCLONE):
        return

    parser = configparser.ConfigParser()
    remote = "ncbackup"

    if dest.provider == Provider.WEBDAV:
        parser[remote] = {
            "type": "webdav",
            "url": dest.webdav_url,
            "vendor": "other",
            "user": dest.webdav_user,
            "pass": _obscure(dest.webdav_password),
        }
    elif dest.provider == Provider.RCLONE and dest.rclone_remote:
        # Benutzerdefinierter Remote-Name — keine Datei überschreiben
        return

    RCLONE_CONF.parent.mkdir(parents=True, exist_ok=True)
    with RCLONE_CONF.open("w", encoding="utf-8") as fh:
        parser.write(fh)
    os.chmod(RCLONE_CONF, 0o600)


def _obscure(password: str) -> str:
    if not password:
        return ""
    if which("rclone") is None:
        return password
    import subprocess

    r = subprocess.run(
        ["rclone", "obscure", password],
        capture_output=True,
        text=True,
        check=True,
    )
    return r.stdout.strip()


def sync_local_repo(cfg: AppConfig) -> None:
    """Kopiert lokales Restic-Repository zu WebDAV/Rclone-Ziel."""
    if which("rclone") is None:
        raise RuntimeError("rclone nicht installiert")

    dest = cfg.destination
    local = Path(dest.local_path).resolve()
    if not local.is_dir():
        raise FileNotFoundError(f"Lokales Repository fehlt: {local}")

    if dest.provider == Provider.WEBDAV:
        write_rclone_config(cfg)
        remote = f"ncbackup:{dest.rclone_path or 'nextcloud-backup'}"
    elif dest.provider == Provider.RCLONE:
        if not dest.rclone_remote:
            raise ValueError("Rclone-Remote-Name fehlt")
        remote = f"{dest.rclone_remote}:{dest.rclone_path}"
    else:
        return

    log(f"Rclone-Sync nach {remote} …")
    env = os.environ.copy()
    env["RCLONE_CONFIG"] = str(RCLONE_CONF)
    run(
        [
            "rclone",
            "sync",
            str(local),
            remote,
            "--transfers",
            "4",
            "--checkers",
            "8",
            "--fast-list",
        ],
        env=env,
    )
    log("Cloud-Sync abgeschlossen.")
