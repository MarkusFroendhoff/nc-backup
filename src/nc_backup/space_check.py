"""Speicherplatz-Prüfung vor dem Backup."""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path

from nc_backup.config_store import AppConfig
from nc_backup.backup_mode import effective_backup_mode
from nc_backup.file_backup import format_bytes

# Sicherheitsreserve: DB-Dump, Manifest, Dateisystem-Overhead
BASE_MARGIN_BYTES = 2 * 1024 ** 3  # 2 GB
# Bei klassischer Verschlüsselung kurzzeitig Quellkopie + tar.gz auf dem Ziel
ENCRYPT_FACTOR = 2.0
# Inkrementell: nur Reserve für Änderungen (Schätzung)
INCREMENTAL_FACTOR = 0.15
# Stream: nur ein Archiv auf dem Ziel, Pi nutzt nur /tmp für DB
STREAM_MARGIN_BYTES = 512 * 1024 ** 2  # 512 MB auf Ziel


@dataclass
class SpaceCheckResult:
    ok: bool
    required_bytes: int
    free_bytes: int
    source_bytes: int
    export_path: str
    message: str
    details: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "required_bytes": self.required_bytes,
            "free_bytes": self.free_bytes,
            "source_bytes": self.source_bytes,
            "required_human": format_bytes(self.required_bytes),
            "free_human": format_bytes(self.free_bytes),
            "source_human": format_bytes(self.source_bytes),
            "export_path": self.export_path,
            "message": self.message,
            "details": self.details,
        }


def directory_size(path: Path) -> int:
    total = 0
    if not path.exists():
        return 0
    if path.is_file():
        return path.stat().st_size
    for entry in path.rglob("*"):
        try:
            if entry.is_file() and not entry.is_symlink():
                total += entry.stat().st_size
        except OSError:
            continue
    return total


def check_backup_space(config: AppConfig) -> SpaceCheckResult:
    export = Path(config.export_path) if config.export_path else None
    if not export or not export.exists() or not export.is_dir():
        return SpaceCheckResult(
            ok=False,
            required_bytes=0,
            free_bytes=0,
            source_bytes=0,
            export_path=config.export_path or "",
            message="Export-Pfad existiert nicht oder ist kein Verzeichnis.",
        )

    details: list[str] = []
    source_bytes = 0
    for folder in config.source_folders:
        path = Path(folder)
        size = directory_size(path)
        source_bytes += size
        details.append(f"{folder}: {format_bytes(size)}")

    required = source_bytes + BASE_MARGIN_BYTES
    mode = effective_backup_mode(config)
    if mode == "stream_encrypted":
        required = source_bytes + STREAM_MARGIN_BYTES
        details.append("Stream-Verschlüsselung: keine Pi-Zwischenkopie, ~1× Quellgröße auf Ziel.")
    elif mode == "incremental":
        required = int(source_bytes * INCREMENTAL_FACTOR) + BASE_MARGIN_BYTES
        details.append("Inkrementell: nur geänderte Dateien (Hardlinks), Reserve geschätzt.")
    elif config.encrypt_backups and mode == "classic":
        required = int(source_bytes * ENCRYPT_FACTOR) + BASE_MARGIN_BYTES
        details.append("Klassisch + Verschlüsselung: ~2× Quellgröße auf Ziel reserviert.")
    elif mode == "classic":
        details.append("Klassischer Modus: volle Kopie auf Ziel.")

    try:
        export_dev = export.stat().st_dev
        root_dev = Path("/").stat().st_dev
        if export_dev == root_dev:
            details.append(
                "Hinweis: Ziel liegt auf derselben Festplatte wie /. "
                "Für Netzwerk-Backups besser ein echtes Netzlaufwerk wählen."
            )
    except OSError:
        pass

    try:
        tmp_free = shutil.disk_usage("/tmp").free
        if mode == "stream_encrypted" and tmp_free < 1024 ** 3:
            details.append(
                f"/tmp frei: {format_bytes(tmp_free)} – DB-Dump kann bei großen DB knapp werden."
            )
    except OSError:
        pass

    try:
        free_bytes = shutil.disk_usage(export).free
    except OSError as exc:
        return SpaceCheckResult(
            ok=False,
            required_bytes=required,
            free_bytes=0,
            source_bytes=source_bytes,
            export_path=str(export),
            message=f"Freier Speicher konnte nicht ermittelt werden: {exc}",
            details=details,
        )

    if free_bytes < required:
        missing = required - free_bytes
        message = (
            f"Ziel zu klein: benötigt ca. {format_bytes(required)}, "
            f"frei nur {format_bytes(free_bytes)} "
            f"(fehlen ca. {format_bytes(missing)}) auf {export}."
        )
        return SpaceCheckResult(
            ok=False,
            required_bytes=required,
            free_bytes=free_bytes,
            source_bytes=source_bytes,
            export_path=str(export),
            message=message,
            details=details,
        )

    message = (
        f"Speicherplatz ok: benötigt ca. {format_bytes(required)}, "
        f"frei {format_bytes(free_bytes)} auf {export}."
    )
    return SpaceCheckResult(
        ok=True,
        required_bytes=required,
        free_bytes=free_bytes,
        source_bytes=source_bytes,
        export_path=str(export),
        message=message,
        details=details,
    )
