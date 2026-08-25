"""Tests für Backup-Modi."""

import unittest

from nc_backup.backup_mode import effective_backup_mode
from nc_backup.config_store import AppConfig


class BackupModeTests(unittest.TestCase):
    def test_auto_stream_when_encrypted(self) -> None:
        cfg = AppConfig(backup_mode="auto", encrypt_backups=True)
        self.assertEqual(effective_backup_mode(cfg), "stream_encrypted")

    def test_auto_incremental_when_plain(self) -> None:
        cfg = AppConfig(backup_mode="auto", encrypt_backups=False)
        self.assertEqual(effective_backup_mode(cfg), "incremental")

    def test_incremental_with_encrypt_becomes_stream(self) -> None:
        cfg = AppConfig(backup_mode="incremental", encrypt_backups=True)
        self.assertEqual(effective_backup_mode(cfg), "stream_encrypted")


if __name__ == "__main__":
    unittest.main()
