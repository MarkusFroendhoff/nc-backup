"""Rclone-Remote anlegen und testen."""

from __future__ import annotations

import configparser
import os
import subprocess
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from nc_backup.runner import which

RCLONE_CONF = Path("/etc/nc-backup/rclone.conf")


class RcloneProvider(str, Enum):
    WEBDAV = "webdav"
    S3 = "s3"
    SFTP = "sftp"
    GOOGLE_DRIVE = "drive"
    DROPBOX = "dropbox"
    ONEDRIVE = "onedrive"


@dataclass
class RcloneRemoteSpec:
    name: str
    provider: RcloneProvider
    # WebDAV
    webdav_url: str = ""
    webdav_user: str = ""
    webdav_pass: str = ""
    # S3
    s3_endpoint: str = ""
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_region: str = "eu-central-1"
    # SFTP
    sftp_host: str = ""
    sftp_user: str = ""
    sftp_pass: str = ""
    sftp_port: int = 22
    # OAuth — manuell per rclone authorize
    client_id: str = ""
    client_secret: str = ""


def _obscure(password: str) -> str:
    if not password:
        return ""
    if which("rclone") is None:
        return password
    r = subprocess.run(
        ["rclone", "obscure", password],
        capture_output=True,
        text=True,
        check=True,
    )
    return r.stdout.strip()


def build_section(spec: RcloneRemoteSpec) -> dict[str, str]:
    p = spec.provider
    if p == RcloneProvider.WEBDAV:
        return {
            "type": "webdav",
            "url": spec.webdav_url,
            "vendor": "other",
            "user": spec.webdav_user,
            "pass": _obscure(spec.webdav_pass),
        }
    if p == RcloneProvider.S3:
        return {
            "type": "s3",
            "provider": "Other",
            "endpoint": spec.s3_endpoint,
            "access_key_id": spec.s3_access_key,
            "secret_access_key": _obscure(spec.s3_secret_key),
            "region": spec.s3_region,
        }
    if p == RcloneProvider.SFTP:
        host = spec.sftp_host
        if spec.sftp_port != 22:
            host = f"{host}:{spec.sftp_port}"
        return {
            "type": "sftp",
            "host": host,
            "user": spec.sftp_user,
            "pass": _obscure(spec.sftp_pass),
        }
    if p == RcloneProvider.GOOGLE_DRIVE:
        section: dict[str, str] = {"type": "drive", "scope": "drive"}
        if spec.client_id:
            section["client_id"] = spec.client_id
        if spec.client_secret:
            section["client_secret"] = spec.client_secret
        return section
    if p == RcloneProvider.DROPBOX:
        section = {"type": "dropbox"}
        if spec.client_id:
            section["client_id"] = spec.client_id
        if spec.client_secret:
            section["client_secret"] = spec.client_secret
        return section
    if p == RcloneProvider.ONEDRIVE:
        return {"type": "onedrive", "region": "global"}
    raise ValueError(f"Unbekannter Provider: {p}")


def write_remote(spec: RcloneRemoteSpec, conf_path: Path | None = None) -> Path:
    path = conf_path or RCLONE_CONF
    path.parent.mkdir(parents=True, exist_ok=True)

    parser = configparser.ConfigParser()
    if path.is_file():
        parser.read(path, encoding="utf-8")

    if spec.name in parser:
        parser.remove_section(spec.name)
    parser.add_section(spec.name)
    for key, value in build_section(spec).items():
        if value:
            parser.set(spec.name, key, value)

    with path.open("w", encoding="utf-8") as fh:
        parser.write(fh)
    os.chmod(path, 0o600)
    return path


def list_remotes(conf_path: Path | None = None) -> list[str]:
    path = conf_path or RCLONE_CONF
    if not path.is_file():
        return []
    parser = configparser.ConfigParser()
    parser.read(path, encoding="utf-8")
    return parser.sections()


def test_remote(remote_name: str, conf_path: Path | None = None) -> tuple[bool, str]:
    if which("rclone") is None:
        return False, "rclone nicht installiert"
    path = conf_path or RCLONE_CONF
    env = os.environ.copy()
    env["RCLONE_CONFIG"] = str(path)
    r = subprocess.run(
        ["rclone", "lsd", f"{remote_name}:", "--max-depth", "1"],
        env=env,
        capture_output=True,
        text=True,
    )
    out = (r.stdout or "") + (r.stderr or "")
    return r.returncode == 0, out.strip() or ("OK" if r.returncode == 0 else "Verbindung fehlgeschlagen")


def authorize_oauth(remote_name: str, conf_path: Path | None = None) -> tuple[bool, str]:
    """Startet interaktive OAuth-Einrichtung (im Terminal)."""
    if which("rclone") is None:
        return False, "rclone nicht installiert"
    path = conf_path or RCLONE_CONF
    env = os.environ.copy()
    env["RCLONE_CONFIG"] = str(path)
    r = subprocess.run(
        ["rclone", "config", "reconnect", f"{remote_name}:"],
        env=env,
        text=True,
    )
    return r.returncode == 0, "OAuth abgeschlossen" if r.returncode == 0 else "OAuth abgebrochen"
