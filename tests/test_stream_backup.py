"""Tests für Stream-Backup."""

import tempfile
import unittest
from pathlib import Path

from nc_backup.stream_backup import _build_tar_command


class StreamBackupTests(unittest.TestCase):
    def test_build_tar_command_includes_sources(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "data"
            source.mkdir()
            (source / "file.txt").write_text("x", encoding="utf-8")
            cmd = _build_tar_command(
                "nextcloud-backup_test",
                [str(source)],
                [],
            )
            self.assertEqual(cmd[0], "tar")
            self.assertIn("-cf", cmd)
            self.assertIn("-", cmd)
            joined = " ".join(cmd)
            self.assertIn("nextcloud-backup_test/files/data/", joined)

    def test_manifest_transform_no_double_comma(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manifest = Path(tmp) / "manifest.json"
            manifest.write_text("{}", encoding="utf-8")
            cmd = _build_tar_command(
                "nextcloud-backup_test",
                [],
                [(manifest, "")],
            )
            transform = cmd[cmd.index("--transform") + 1]
            self.assertNotIn(",,", transform)
            self.assertIn("manifest.json", transform)
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "data"
            source.mkdir()
            (source / "file.txt").write_text("x", encoding="utf-8")
            cmd = _build_tar_command(
                "nextcloud-backup_test",
                [str(source)],
                [],
            )
            self.assertEqual(cmd[0], "tar")
            self.assertIn("-cf", cmd)
            self.assertIn("-", cmd)
            joined = " ".join(cmd)
            self.assertIn("nextcloud-backup_test/files/data/", joined)


if __name__ == "__main__":
    unittest.main()
