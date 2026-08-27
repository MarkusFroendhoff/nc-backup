"""systemd-Timer aus Konfiguration schreiben."""

from __future__ import annotations

from pathlib import Path

from nc_backup.models import AppConfig

TIMER_PATH = Path("/etc/systemd/system/nc-backup.timer")
TIMER_TEMPLATE = """[Unit]
Description=NC Backup — geplanter Nextcloud-Backup-Lauf
Documentation=file:///usr/share/doc/nc-backup/README.md

[Timer]
OnCalendar=*-*-* {hour:02d}:{minute:02d}:00
Persistent=true
RandomizedDelaySec=900

[Install]
WantedBy=timers.target
"""


def apply_schedule(cfg: AppConfig) -> None:
    if not cfg.schedule.enabled:
        TIMER_PATH.write_text(
            """[Unit]
Description=NC Backup (deaktiviert)

[Timer]
OnCalendar=
""",
            encoding="utf-8",
        )
        return

    parts = cfg.schedule.on_calendar.strip().split(":")
    hour = int(parts[0]) if parts else 2
    minute = int(parts[1]) if len(parts) > 1 else 30
    TIMER_PATH.write_text(
        TIMER_TEMPLATE.format(hour=hour, minute=minute),
        encoding="utf-8",
    )
