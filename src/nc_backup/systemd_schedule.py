"""systemd-Timer für geplante Backups."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from nc_backup.config_store import AppConfig, ScheduleConfig, load_config, save_config

SERVICE_NAME = "nc-backup"
SERVICE_PATH = Path("/etc/systemd/system/nc-backup.service")
TIMER_PATH = Path("/etc/systemd/system/nc-backup.timer")

WEEKDAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def describe_schedule(schedule: ScheduleConfig) -> str:
    if not schedule.enabled:
        return "Geplanter Backup ist deaktiviert."
    days = ", ".join(WEEKDAY_NAMES[day] for day in schedule.weekdays)
    return f"Aktiv: {schedule.hour:02d}:{schedule.minute:02d} Uhr an {days}"


def _timer_on_calendar(schedule: ScheduleConfig) -> str:
    days = ",".join(WEEKDAY_NAMES[day] for day in sorted(schedule.weekdays))
    return f"{days} *-*-* {schedule.hour:02d}:{schedule.minute:02d}:00"


def _write_systemd_files(schedule: ScheduleConfig) -> None:
    service = """[Unit]
Description=Nextcloud Backup (geplant)
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
ExecStart=/usr/bin/nc-backup-run
User=root
Group=root

[Install]
WantedBy=multi-user.target
"""
    timer = f"""[Unit]
Description=Nextcloud Backup Timer

[Timer]
OnCalendar={_timer_on_calendar(schedule)}
Persistent=true
Unit=nc-backup.service

[Install]
WantedBy=timers.target
"""
    SERVICE_PATH.write_text(service, encoding="utf-8")
    TIMER_PATH.write_text(timer, encoding="utf-8")


def _run_systemctl(*args: str) -> None:
    result = subprocess.run(["systemctl", *args], capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise OSError(result.stderr.strip() or "systemctl fehlgeschlagen")


def apply_schedule_as_root(config: AppConfig) -> str:
    if not config.schedule.enabled:
        _run_systemctl("disable", "--now", f"{SERVICE_NAME}.timer")
        return "Geplanter Backup wurde deaktiviert."

    _write_systemd_files(config.schedule)
    _run_systemctl("daemon-reload")
    _run_systemctl("enable", "--now", f"{SERVICE_NAME}.timer")
    return f"Zeitplan aktiviert: {describe_schedule(config.schedule)}"


def apply_schedule(config: AppConfig) -> str:
    save_config(config)
    if os.geteuid() != 0:
        # Headless fallback: wenn keine grafische Polkit-Abfrage moeglich ist,
        # versuche sudo im Terminal.
        if not os.environ.get("DISPLAY"):
            sudo_result = subprocess.run(
                ["sudo", "nc-backup-run", "--apply-schedule"],
                capture_output=True,
                text=True,
                check=False,
            )
            if sudo_result.returncode == 0:
                return sudo_result.stdout.strip() or "Zeitplan angewendet."
        result = subprocess.run(
            ["pkexec", "--action", "org.ncbackup.apply-schedule", "/usr/lib/nc-backup/apply-schedule.sh"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            stderr = result.stderr.strip() or result.stdout.strip()
            raise OSError(stderr or "Zeitplan konnte nicht angewendet werden (pkexec).")
        return result.stdout.strip() or "Zeitplan angewendet."
    return apply_schedule_as_root(config)


def apply_schedule_from_cli() -> int:
    config = load_config()
    message = apply_schedule_as_root(config)
    print(message)
    return 0
