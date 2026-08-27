"""Laden und Speichern der YAML-Konfiguration."""

from __future__ import annotations

import json
import os
from pathlib import Path

import yaml

from nc_backup.models import AppConfig

CONFIG_ENV = "NC_BACKUP_CONFIG"
DEFAULT_CONFIG_PATH = Path("/etc/nc-backup/config.yaml")
LEGACY_JSON = Path("/etc/nc-backup/config.json")
PASSWORD_FILE = Path("/etc/nc-backup/restic-password")


def config_path() -> Path:
    return Path(os.environ.get(CONFIG_ENV, DEFAULT_CONFIG_PATH))


def _read_json(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _read_yaml(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        with path.open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        return data if isinstance(data, dict) else {}
    except OSError:
        return {}


def load_config() -> AppConfig:
    yaml_data = _read_yaml(config_path())
    legacy = _read_json(LEGACY_JSON)
    data: dict = {**legacy, **yaml_data}

    export = str(legacy.get("export_path") or "")
    dest = dict(data.get("destination") or {})
    default_local = "/var/backups/nextcloud/restic-repo"
    if export and dest.get("local_path", default_local) in ("", default_local):
        dest["local_path"] = export
        dest.setdefault("provider", "local")
        data["destination"] = dest
    if legacy.get("config_php_path") and "nextcloud" not in yaml_data:
        data["config_php_path"] = legacy["config_php_path"]
        data["source_folders"] = legacy.get("source_folders") or data.get("source_folders") or []
    if legacy.get("schedule") and not (yaml_data.get("schedule") or {}).get("on_calendar"):
        merged_sched = {**(legacy.get("schedule") or {}), **(data.get("schedule") or {})}
        data["schedule"] = merged_sched

    cfg = AppConfig.from_dict(data)
    if not cfg.destination.restic_password and PASSWORD_FILE.is_file():
        cfg.destination.restic_password = PASSWORD_FILE.read_text(encoding="utf-8").strip()
    return cfg


def save_config(cfg: AppConfig, path: Path | None = None) -> Path:
    target = path or config_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    data = cfg.to_dict()
    restic_pw = data["destination"].pop("restic_password", "")
    with target.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(data, fh, default_flow_style=False, allow_unicode=True)
    os.chmod(target, 0o600)
    if restic_pw:
        PASSWORD_FILE.write_text(restic_pw + "\n", encoding="utf-8")
        os.chmod(PASSWORD_FILE, 0o600)
    return target
