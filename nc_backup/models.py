"""Konfigurationsmodelle."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class BackupMode(str, Enum):
    INCREMENTAL = "incremental"
    LEGACY = "legacy"


class Provider(str, Enum):
    LOCAL = "local"
    SFTP = "sftp"
    S3 = "s3"
    AZURE = "azure"
    B2 = "b2"
    WEBDAV = "webdav"
    RCLONE = "rclone"


@dataclass
class NextcloudConfig:
    install_dir: str = "/var/www/nextcloud"
    data_dir: str = "/var/www/nextcloud/data"
    occ_user: str = "www-data"
    maintenance_mode: bool = True
    container: str = ""
    occ_inner: str = ""


@dataclass
class DatabaseConfig:
    host: str = "localhost"
    port: int = 3306
    name: str = "nextcloud"
    user: str = "nextcloud"
    password: str = ""
    type: str = "mysql"
    container: str = ""


@dataclass
class RetentionConfig:
    keep_daily: int = 7
    keep_weekly: int = 4
    keep_monthly: int = 6


@dataclass
class DestinationConfig:
    mode: BackupMode = BackupMode.INCREMENTAL
    provider: Provider = Provider.LOCAL
    restic_password: str = ""
    retention: RetentionConfig = field(default_factory=RetentionConfig)
    # Provider-spezifisch
    local_path: str = "/var/backups/nextcloud/restic-repo"
    sftp_host: str = ""
    sftp_port: int = 22
    sftp_user: str = ""
    sftp_path: str = "/backups/nextcloud"
    sftp_password: str = ""
    s3_endpoint: str = "s3.amazonaws.com"
    s3_bucket: str = ""
    s3_prefix: str = "nextcloud"
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_region: str = "eu-central-1"
    azure_account: str = ""
    azure_key: str = ""
    azure_container: str = "nextcloud"
    azure_prefix: str = "backup"
    b2_account_id: str = ""
    b2_account_key: str = ""
    b2_bucket: str = ""
    b2_prefix: str = "nextcloud"
    webdav_url: str = ""
    webdav_user: str = ""
    webdav_password: str = ""
    rclone_remote: str = ""
    rclone_path: str = "nextcloud-backup"
    # Legacy Vollbackup
    legacy_root: str = "/var/backups/nextcloud"
    legacy_retention_days: int = 14


@dataclass
class ScheduleConfig:
    enabled: bool = True
    on_calendar: str = "02:30"


@dataclass
class AppConfig:
    nextcloud: NextcloudConfig = field(default_factory=NextcloudConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    destination: DestinationConfig = field(default_factory=DestinationConfig)
    schedule: ScheduleConfig = field(default_factory=ScheduleConfig)

    def to_dict(self) -> dict[str, Any]:
        d = _to_plain(self)
        d["destination"]["mode"] = self.destination.mode.value
        d["destination"]["provider"] = self.destination.provider.value
        return d


    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AppConfig:
        data = dict(data or {})
        dest = dict(data.get("destination") or {})
        nc = dict(data.get("nextcloud") or {})
        db_raw = dict(data.get("database") or {})
        sched = dict(data.get("schedule") or {})

        # 1.7.1: export_path, config.php, hour/minute, Docker-Container
        if data.get("export_path") and not dest.get("local_path"):
            dest["local_path"] = str(data["export_path"])
            dest.setdefault("provider", "local")
        php = str(data.get("config_php_path") or "")
        if php and not nc.get("install_dir"):
            from pathlib import Path as _P
            p = _P(php)
            install = p.parent.parent if p.name == "config.php" else p.parent
            nc["install_dir"] = str(install)
            nc.setdefault("data_dir", str(install / "data"))
        if data.get("docker_nextcloud_container") and not nc.get("container"):
            nc["container"] = str(data["docker_nextcloud_container"])
        if data.get("docker_db_container") and not db_raw.get("container"):
            db_raw["container"] = str(data["docker_db_container"])
        for folder in data.get("source_folders") or []:
            s = str(folder).rstrip("/")
            if s.endswith("/data") and not nc.get("data_dir"):
                nc["data_dir"] = folder
        if not sched.get("on_calendar") and ("hour" in sched or "minute" in sched):
            try:
                hour = int(sched.get("hour") or 2)
                minute = int(sched.get("minute") or 0)
            except (TypeError, ValueError):
                hour, minute = 2, 0
            sched["on_calendar"] = f"{hour:02d}:{minute:02d}"

        if "port" in db_raw:
            try:
                db_raw["port"] = int(db_raw["port"])
            except (TypeError, ValueError):
                db_raw.pop("port", None)

        nc = _known(NextcloudConfig, nc)
        db_raw = _known(DatabaseConfig, db_raw)
        ret = dest.get("retention") or {}
        mode_raw = dest.get("mode", BackupMode.INCREMENTAL.value)
        prov_raw = dest.get("provider", Provider.LOCAL.value)
        try:
            mode = BackupMode(mode_raw)
        except ValueError:
            mode = BackupMode.INCREMENTAL
        try:
            provider = Provider(prov_raw)
        except ValueError:
            provider = Provider.LOCAL
        dest_f = _known(DestinationConfig, dest)
        dest_f.pop("mode", None)
        dest_f.pop("provider", None)
        dest_f.pop("retention", None)
        dest_f.pop("restic_password", None)
        sched = _known(ScheduleConfig, sched)

        return cls(
            nextcloud=NextcloudConfig(**nc),
            database=DatabaseConfig(**db_raw),
            destination=DestinationConfig(
                mode=mode,
                provider=provider,
                restic_password=str(dest.get("restic_password") or ""),
                retention=RetentionConfig(**_known(RetentionConfig, ret)) if ret else RetentionConfig(),
                **dest_f,
            ),
            schedule=ScheduleConfig(**sched),
        )


def _known(cls: Any, data: dict[str, Any]) -> dict[str, Any]:
    names = set(getattr(cls, "__dataclass_fields__", {}))
    return {k: v for k, v in (data or {}).items() if k in names}



def _to_plain(obj: Any) -> Any:
    if hasattr(obj, "__dataclass_fields__"):
        return {k: _to_plain(getattr(obj, k)) for k in obj.__dataclass_fields__}
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, list):
        return [_to_plain(x) for x in obj]
    return obj
