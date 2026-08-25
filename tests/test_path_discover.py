"""Tests für Pfad-Erkennung aus config.php."""

import tempfile
import unittest
from pathlib import Path

from nc_backup.path_discover import discover_paths_from_config_php


SAMPLE = """<?php
$CONFIG = array (
  'dbtype' => 'mysql',
  'dbname' => 'nextcloud',
  'dbuser' => 'nc',
  'dbpassword' => 'secret',
  'dbhost' => 'localhost',
  'datadirectory' => '/srv/nc-data',
);
"""


class PathDiscoverTests(unittest.TestCase):
    def test_reads_datadirectory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config_dir = Path(tmp) / "config"
            data_dir = Path(tmp) / "nc-data"
            config_dir.mkdir()
            data_dir.mkdir()
            config_php = config_dir / "config.php"
            content = SAMPLE.replace("/srv/nc-data", str(data_dir))
            config_php.write_text(content, encoding="utf-8")

            discovery = discover_paths_from_config_php(str(config_php))
            self.assertEqual(discovery.data_directory, str(data_dir))
            self.assertIn(str(data_dir), discovery.source_folders)
            self.assertIn(str(config_dir), discovery.source_folders)


if __name__ == "__main__":
    unittest.main()
