"""Nextcloud occ / Wartungsmodus."""

from __future__ import annotations

import os
import pwd
from subprocess import run as sp_run

from nc_backup.logutil import log
from nc_backup.models import AppConfig


def _occ_cmd(cfg: AppConfig, *args: str) -> list[str]:
    occ = os.path.join(cfg.nextcloud.install_dir, "occ")
    if os.path.isfile(occ):
        return ["sudo", "-u", cfg.nextcloud.occ_user, "php", occ, *args]
    container = (getattr(cfg.nextcloud, "container", "") or "").strip()
    if container:
        from nc_backup.docker_detect import docker_bin
        binary = docker_bin() or "docker"
        inner = (getattr(cfg.nextcloud, "occ_inner", "") or "").strip() or "/var/www/html/occ"
        user = cfg.nextcloud.occ_user or "www-data"
        return [binary, "exec", "-u", user, container, "php", inner, *args]
    raise FileNotFoundError(f"occ nicht gefunden: {occ}")


def maintenance(cfg: AppConfig, enabled: bool) -> None:
    if not cfg.nextcloud.maintenance_mode:
        return
    flag = "--on" if enabled else "--off"
    log(f"Wartungsmodus {'an' if enabled else 'aus'} …")
    sp_run(_occ_cmd(cfg, "maintenance:mode", flag), check=True, timeout=60)


def nc_version(cfg: AppConfig) -> str:
    try:
        r = sp_run(
            _occ_cmd(cfg, "-V"),
            capture_output=True,
            text=True,
            check=True,
            timeout=60,
        )
        return (r.stdout or r.stderr or "").strip()
    except Exception:
        return "unknown"


def verify_paths(cfg: AppConfig) -> list[str]:
    errors: list[str] = []
    nc = getattr(cfg, "nextcloud", None)
    if nc is None:
        errors.append("Konfiguration ist noch im alten Format. Bitte speichern Sie die Einrichtung neu.")
        return errors
    container = (getattr(nc, "container", "") or "").strip()
    if container:
        if not nc.data_dir or not os.path.isdir(nc.data_dir):
            errors.append(
                f"Datenverzeichnis auf dem Host fehlt: {nc.data_dir or '(leer)'}. "
                "Das Docker-Volume ist nicht gemountet oder der Pfad stimmt nicht — "
                "restic sichert nur Host-Pfade."
            )
        return errors
    if not os.path.isdir(nc.install_dir):
        errors.append(f"Installationsverzeichnis fehlt: {nc.install_dir}")
    if not os.path.isdir(nc.data_dir):
        errors.append(f"Datenverzeichnis fehlt: {nc.data_dir}")
    try:
        pwd.getpwnam(nc.occ_user)
    except KeyError:
        errors.append(f"Benutzer existiert nicht: {nc.occ_user}")
    return errors
