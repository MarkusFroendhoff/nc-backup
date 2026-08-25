"""Erkennt USB-, Netzwerk- und Medien-Laufwerke für die Zielauswahl."""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class MountCandidate:
    path: str
    label: str
    kind: str  # usb | network | media | local
    free_gb: float | None = None
    writable: bool = False

    @property
    def display(self) -> str:
        free = f", {self.free_gb:.1f} GB frei" if self.free_gb is not None else ""
        write = "" if self.writable else ", nur lesen"
        kind_de = {
            "usb": "USB",
            "network": "Netzwerk",
            "media": "Medien",
            "local": "Lokal",
        }.get(self.kind, self.kind)
        return f"[{kind_de}] {self.label} → {self.path}{free}{write}"


def list_backup_targets() -> list[MountCandidate]:
    """Sammelt sinnvolle Backup-Ziele: USB, Medien, Netzwerk-Mounts."""
    found: dict[str, MountCandidate] = {}

    for candidate in _from_findmnt() + _from_media_dirs() + _from_mnt_dirs():
        try:
            path = str(Path(candidate.path).resolve())
        except OSError:
            path = candidate.path
        if path in found:
            continue
        if not Path(path).is_dir():
            continue
        candidate.path = path
        candidate.writable = os.access(path, os.W_OK)
        candidate.free_gb = _free_gb(path)
        found[path] = candidate

    order = {"usb": 0, "network": 1, "media": 2, "local": 3}
    return sorted(found.values(), key=lambda item: (order.get(item.kind, 9), item.path.lower()))


def _free_gb(path: str) -> float | None:
    try:
        usage = shutil.disk_usage(path)
        return usage.free / (1024 ** 3)
    except OSError:
        return None


def _from_findmnt() -> list[MountCandidate]:
    if not shutil.which("findmnt"):
        return []
    result = subprocess.run(
        ["findmnt", "-ln", "-o", "TARGET,FSTYPE,SOURCE,LABEL"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return []

    candidates: list[MountCandidate] = []
    for line in result.stdout.splitlines():
        parts = line.split(None, 3)
        if len(parts) < 2:
            continue
        target = parts[0]
        fstype = parts[1]
        source = parts[2] if len(parts) > 2 else ""
        label = parts[3].strip() if len(parts) > 3 else ""

        if target in {"/", "/boot", "/boot/firmware", "/boot/efi"}:
            continue
        if target.startswith(("/snap", "/run/user", "/sys", "/proc", "/dev")):
            continue

        kind = _classify(target, fstype, source)
        if kind is None:
            continue
        display_label = label or Path(target).name or target
        candidates.append(MountCandidate(path=target, label=display_label, kind=kind))
    return candidates


def _classify(target: str, fstype: str, source: str) -> str | None:
    network_fs = {"nfs", "nfs4", "cifs", "smb3", "fuse.sshfs", "fuse.rclone"}
    removable_fs = {"vfat", "exfat", "ntfs", "ntfs3", "fuseblk"}

    if fstype.lower() in network_fs:
        return "network"
    if target.startswith(("/media/", "/run/media/")):
        return "usb"
    if source.startswith("/dev/sd") or "usb" in source.lower():
        if fstype.lower() in removable_fs or target.startswith(("/mnt/", "/media/", "/run/media/")):
            return "usb"
    if target.startswith("/mnt/") and target != "/mnt":
        return "local"
    return None


def _from_media_dirs() -> list[MountCandidate]:
    candidates: list[MountCandidate] = []
    users = {
        "root",
        os.environ.get("SUDO_USER") or "",
        os.environ.get("USER") or "",
    }
    roots = [Path("/media"), Path("/run/media")]
    for root in roots:
        if not root.is_dir():
            continue
        for user_dir in root.iterdir():
            if not user_dir.is_dir():
                continue
            if users - {""} and user_dir.name not in users and user_dir.parent.name not in {"media", "run"}:
                pass
            for volume in user_dir.iterdir() if user_dir.is_dir() else []:
                if volume.is_dir():
                    candidates.append(
                        MountCandidate(path=str(volume), label=volume.name, kind="usb")
                    )
            # Falls direkt /media/USBNAME ohne User-Unterordner
            if user_dir.parent == root and not any(user_dir.iterdir()):
                continue
    return candidates


def _from_mnt_dirs() -> list[MountCandidate]:
    mnt = Path("/mnt")
    if not mnt.is_dir():
        return []
    return [
        MountCandidate(path=str(path), label=path.name, kind="local")
        for path in mnt.iterdir()
        if path.is_dir()
    ]
