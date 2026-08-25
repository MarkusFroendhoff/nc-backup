"""Tests für config.php-Parser."""

import tempfile
import unittest
from pathlib import Path

from nc_backup.config_php import parse_config_php


SAMPLE_CONFIG = """<?php
$CONFIG = array (
  'dbtype' => 'mysql',
  'dbname' => 'nextcloud',
  'dbuser' => 'ncuser',
  'dbpassword' => 'secret\\'quote',
  'dbhost' => 'localhost:3306',
  'datadirectory' => '/var/www/nextcloud/data',
);
"""


class ConfigPhpTests(unittest.TestCase):
    def test_parse_mysql_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.php"
            path.write_text(SAMPLE_CONFIG, encoding="utf-8")
            cfg = parse_config_php(path)
        self.assertEqual(cfg.dbtype, "mysql")
        self.assertEqual(cfg.dbname, "nextcloud")
        self.assertEqual(cfg.dbuser, "ncuser")
        self.assertEqual(cfg.dbpassword, "secret'quote")
        self.assertEqual(cfg.dbhost, "localhost:3306")
        self.assertEqual(cfg.datadirectory, "/var/www/nextcloud/data")


if __name__ == "__main__":
    unittest.main()
