"""Tests für Restore-Planung."""

import json
import tempfile
import unittest
from pathlib import Path

from nc_backup.restore_engine import _infer_folder_mapping, inspect_backup_directory


class RestoreEngineTests(unittest.TestCase):
    def test_infer_folder_mapping_by_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            backup_dir = Path(tmp)
            data = backup_dir / "files" / "data"
            config = backup_dir / "files" / "config"
            data.mkdir(parents=True)
            config.mkdir(parents=True)
            mapping = _infer_folder_mapping(
                ["/var/www/nextcloud/data", "/var/www/nextcloud/config"],
                backup_dir,
            )
        self.assertEqual(len(mapping), 2)
        self.assertEqual(mapping[0]["source"], "/var/www/nextcloud/data")
        self.assertTrue(mapping[0]["backup"].endswith("/files/data"))

    def test_inspect_backup_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            backup_dir = Path(tmp) / "nextcloud-backup_test"
            (backup_dir / "files" / "data").mkdir(parents=True)
            manifest = {
                "created_at": "2026-06-08T02:00:00",
                "install_mode": "native",
                "source_folders": ["/var/www/nextcloud/data"],
                "folder_mapping": [
                    {"source": "/var/www/nextcloud/data", "backup": str(backup_dir / "files" / "data")}
                ],
                "database_dump": None,
                "encrypted": True,
            }
            (backup_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            info = inspect_backup_directory(backup_dir, backup_dir, encrypted=False)
        self.assertIn("Erstellt:", info.summary)
        self.assertEqual(len(info.folder_mapping), 1)


if __name__ == "__main__":
    unittest.main()
