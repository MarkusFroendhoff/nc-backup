"""Tests für systemd-Zeitplan."""

import unittest

from nc_backup.systemd_schedule import _write_systemd_files, backup_run_path
from nc_backup.config_store import ScheduleConfig


class SystemdScheduleTests(unittest.TestCase):
    def test_backup_run_path_returns_string(self) -> None:
        path = backup_run_path()
        self.assertTrue(path.endswith("nc-backup-run"))

    def test_written_service_is_not_a_boot_unit(self) -> None:
        import tempfile
        from pathlib import Path
        from unittest import mock

        with tempfile.TemporaryDirectory() as tmp:
            service = Path(tmp) / "nc-backup.service"
            timer = Path(tmp) / "nc-backup.timer"
            with mock.patch("nc_backup.systemd_schedule.SERVICE_PATH", service), mock.patch(
                "nc_backup.systemd_schedule.TIMER_PATH", timer
            ):
                _write_systemd_files(ScheduleConfig(enabled=True, hour=11, minute=39))
            text = service.read_text(encoding="utf-8")
            self.assertNotIn("WantedBy=multi-user.target", text)
            self.assertIn("ExecStart=", text)
            self.assertIn("Type=oneshot", text)
            self.assertIn("OnCalendar=Mon,Tue,Wed,Thu,Fri,Sat,Sun *-*-* 11:39:00", timer.read_text(encoding="utf-8"))
