"""Tests für Größenformatierung."""

import unittest

from nc_backup.file_backup import format_bytes, format_rsync_progress_line


class FormatBytesTests(unittest.TestCase):
    def test_mb(self) -> None:
        self.assertEqual(format_bytes(50 * 1024 * 1024), "50.0 MB")

    def test_gb(self) -> None:
        self.assertEqual(format_bytes(46_103_980_056), "42.94 GB")

    def test_tb(self) -> None:
        self.assertEqual(format_bytes(2 * 1024 ** 4), "2.00 TB")

    def test_rsync_line(self) -> None:
        line = "46.103.980.056  87%  22,31MB/s    0:05:00"
        pretty = format_rsync_progress_line(line)
        self.assertIn("GB", pretty)
        self.assertIn("87%", pretty)
        self.assertNotIn("46103980056", pretty.replace(".", "").replace(",", ""))


if __name__ == "__main__":
    unittest.main()
