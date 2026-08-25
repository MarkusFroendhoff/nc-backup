"""Tests für Speicherplatz-Prüfung."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from nc_backup.config_store import AppConfig
from nc_backup.space_check import check_backup_space, directory_size


class SpaceCheckTests(unittest.TestCase):
    def test_directory_size(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            (path / "a.bin").write_bytes(b"x" * 1000)
            self.assertEqual(directory_size(path), 1000)

    def test_target_too_small(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "src"
            dst = Path(tmp) / "dst"
            src.mkdir()
            dst.mkdir()
            (src / "big.bin").write_bytes(b"x" * 5000)
            cfg = AppConfig(source_folders=[str(src)], export_path=str(dst))
            with patch("nc_backup.space_check.shutil.disk_usage") as usage:
                usage.return_value = type("U", (), {"free": 1000})()
                result = check_backup_space(cfg)
            self.assertFalse(result.ok)
            self.assertIn("Ziel zu klein", result.message)


if __name__ == "__main__":
    unittest.main()
