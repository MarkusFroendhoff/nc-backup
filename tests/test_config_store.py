"""Tests für das Laden der Konfiguration."""

import unittest

from nc_backup.config_store import AppConfig


class ConfigStoreTests(unittest.TestCase):
    def test_from_dict_ignores_unknown_top_level_and_schedule_keys(self) -> None:
        cfg = AppConfig.from_dict(
            {
                "install_mode": "native",
                "setup_complete": True,
                "export_path": "/mnt/backup",
                "unknown_mac_field": "1.7",
                "schedule": {
                    "enabled": True,
                    "hour": 11,
                    "minute": 39,
                    "weekdays": [0, 1, 2, 3, 4],
                    "last_run": "2026-08-27T11:39:00",
                },
            }
        )
        self.assertEqual(cfg.export_path, "/mnt/backup")
        self.assertTrue(cfg.schedule.enabled)
        self.assertEqual(cfg.schedule.hour, 11)
        self.assertEqual(cfg.schedule.minute, 39)
        self.assertEqual(cfg.schedule.weekdays, [0, 1, 2, 3, 4])

    def test_from_dict_does_not_mutate_input(self) -> None:
        payload = {"schedule": {"enabled": True, "hour": 2, "minute": 0}, "setup_complete": True}
        AppConfig.from_dict(payload)
        self.assertIn("schedule", payload)
