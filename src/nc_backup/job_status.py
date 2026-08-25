"""Status und Fortschritt laufender Backup-Jobs."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Callable


@dataclass
class JobStatus:
    running: bool = False
    percent: int = 0
    phase: str = "Bereit"
    detail: str = ""
    success: bool | None = None
    message: str = ""
    destination: str = ""
    errors: list[str] = field(default_factory=list)
    log_lines: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "running": self.running,
            "percent": self.percent,
            "phase": self.phase,
            "detail": self.detail,
            "success": self.success,
            "message": self.message,
            "destination": self.destination,
            "errors": self.errors,
            "log_lines": self.log_lines[-40:],
        }


class ProgressTracker:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.status = JobStatus()

    def reset(self) -> None:
        with self._lock:
            self.status = JobStatus(running=True, phase="Start", detail="Backup wird vorbereitet…", percent=1)

    def update(self, *, percent: int | None = None, phase: str | None = None, detail: str | None = None) -> None:
        with self._lock:
            if percent is not None:
                # Fortschritt nie zuruecksetzen (rsync-Prozent kann schwanken).
                self.status.percent = max(self.status.percent, max(0, min(100, percent)))
            if phase is not None:
                self.status.phase = phase
            if detail is not None:
                self.status.detail = detail
                self.status.log_lines.append(detail)

    def finish(self, *, success: bool, message: str, destination: str = "", errors: list[str] | None = None) -> None:
        with self._lock:
            self.status.running = False
            self.status.success = success
            self.status.message = message
            self.status.destination = destination
            self.status.errors = errors or []
            self.status.percent = 100 if success else self.status.percent
            self.status.phase = "Fertig" if success else "Fehler"
            self.status.detail = message
            self.status.log_lines.append(message)

    def snapshot(self) -> dict:
        with self._lock:
            return self.status.to_dict()


ProgressCallback = Callable[[int, str, str], None]


backup_tracker = ProgressTracker()
_backup_lock = threading.Lock()
