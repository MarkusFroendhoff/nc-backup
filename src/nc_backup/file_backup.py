"""Dateisystem-Backup per rsync."""

from __future__ import annotations

import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path


class FileBackupError(RuntimeError):
    pass


def format_bytes(num_bytes: float) -> str:
    """Formatiert Bytes als MB / GB / TB."""
    if num_bytes < 0:
        num_bytes = 0
    mb = num_bytes / (1024 ** 2)
    if mb < 1024:
        return f"{mb:.1f} MB"
    gb = mb / 1024
    if gb < 1024:
        return f"{gb:.2f} GB"
    tb = gb / 1024
    return f"{tb:.2f} TB"


def format_rsync_progress_line(line: str) -> str:
    """Macht rsync-progress2-Zeilen lesbarer (Bytes -> MB/GB/TB)."""
    cleaned = line.strip()
    match = re.match(
        r"^([\d.,]+)\s+(\d+%)\s+(\S+)\s+(\S+)(?:\s+(.*))?$",
        cleaned,
    )
    if not match:
        return cleaned

    raw_bytes, percent, speed, elapsed, rest = match.groups()
    digits = re.sub(r"[^\d]", "", raw_bytes)
    if not digits:
        return cleaned
    try:
        size_text = format_bytes(float(digits))
    except ValueError:
        return cleaned

    speed_text = speed.replace(",", ".")
    suffix = f" {rest}" if rest else ""
    return f"{size_text}  {percent}  {speed_text}  {elapsed}{suffix}"


def create_backup_destination(export_path: str | Path) -> Path:
    base = Path(export_path)
    if not base.exists():
        raise FileBackupError(f"Export-Pfad existiert nicht: {base}")
    if not base.is_dir():
        raise FileBackupError(f"Export-Pfad ist kein Verzeichnis: {base}")
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    destination = base / f"nextcloud-backup_{stamp}"
    destination.mkdir(parents=True, exist_ok=False)
    return destination


def create_incremental_snapshot(export_path: str | Path) -> tuple[Path, Path | None]:
    """Legt einen neuen Snapshot an; link_dest zeigt auf den vorherigen Snapshot."""
    base = Path(export_path)
    if not base.exists():
        raise FileBackupError(f"Export-Pfad existiert nicht: {base}")
    if not base.is_dir():
        raise FileBackupError(f"Export-Pfad ist kein Verzeichnis: {base}")

    snapshot_root = base / "nextcloud-backup-snapshots"
    snapshot_root.mkdir(parents=True, exist_ok=True)

    previous: Path | None = None
    snapshots = sorted(
        (path for path in snapshot_root.iterdir() if path.is_dir() and path.name != "latest"),
        key=lambda path: path.name,
        reverse=True,
    )
    if snapshots:
        previous = snapshots[0]

    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    destination = snapshot_root / stamp
    destination.mkdir(parents=True, exist_ok=False)
    return destination, previous


def update_latest_snapshot_link(snapshot_root: Path, destination: Path) -> None:
    latest = snapshot_root / "latest"
    if latest.is_symlink() or latest.exists():
        latest.unlink()
    latest.symlink_to(destination.name)


def rsync_folder(
    source: Path,
    destination: Path,
    *,
    delete_extra: bool = False,
    link_dest: Path | None = None,
    progress_callback=None,
) -> None:
    if not source.exists():
        raise FileBackupError(f"Quellordner nicht gefunden: {source}")
    if not shutil.which("rsync"):
        raise FileBackupError("rsync ist nicht installiert")

    destination.mkdir(parents=True, exist_ok=True)
    command = ["rsync", "-aHAX", "--info=progress2"]
    if delete_extra:
        command.append("--delete-during")
    if link_dest is not None:
        command.append(f"--link-dest={link_dest}")
    command.extend([f"{source}/", f"{destination}/"])

    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    assert process.stdout is not None
    assert process.stderr is not None

    last_percent = -1
    for line in process.stdout:
        line = line.strip()
        if not line or progress_callback is None:
            continue
        if "%" in line:
            pretty = format_rsync_progress_line(line)
            try:
                percent_token = next(part for part in line.replace(",", "").split() if part.endswith("%"))
                percent = int(percent_token.rstrip("%"))
                if percent != last_percent:
                    last_percent = percent
                    progress_callback(percent, pretty)
            except (StopIteration, ValueError):
                progress_callback(None, pretty)

    stderr = process.stderr.read()
    returncode = process.wait()
    if returncode != 0:
        raise FileBackupError(stderr or "rsync fehlgeschlagen")


def backup_folders(source_folders: list[str], backup_root: Path, progress_callback=None) -> list[Path]:
    return _backup_folders_internal(source_folders, backup_root, progress_callback=progress_callback)


def backup_folders_incremental(
    source_folders: list[str],
    backup_root: Path,
    previous_snapshot: Path | None,
    progress_callback=None,
) -> list[Path]:
    return _backup_folders_internal(
        source_folders,
        backup_root,
        previous_snapshot=previous_snapshot,
        progress_callback=progress_callback,
    )


def _backup_folders_internal(
    source_folders: list[str],
    backup_root: Path,
    *,
    previous_snapshot: Path | None = None,
    progress_callback=None,
) -> list[Path]:
    copied: list[Path] = []
    total = max(len(source_folders), 1)
    for index, folder in enumerate(source_folders):
        source = Path(folder)
        if not source.exists():
            raise FileBackupError(f"Quellordner nicht gefunden: {source}")
        safe_name = source.name or source.as_posix().replace("/", "_")
        target = backup_root / "files" / safe_name

        def folder_progress(percent, detail, _index=index, _folder=folder):
            if progress_callback is None:
                return
            base = int((_index / total) * 70)
            span = max(int(70 / total), 1)
            if percent is None:
                overall = base
            else:
                overall = base + int((max(0, min(100, percent)) / 100) * span)
            progress_callback(overall, f"Dateien: {_folder}", detail)

        if progress_callback:
            progress_callback(int((index / total) * 70), f"Dateien: {folder}", f"Starte rsync für {folder}")
        link_dest = None
        if previous_snapshot is not None:
            link_dest = previous_snapshot / "files" / safe_name
        rsync_folder(source, target, link_dest=link_dest, progress_callback=folder_progress)
        copied.append(target)
    return copied
