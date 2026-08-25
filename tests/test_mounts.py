"""Tests für Laufwerks-/Mount-Erkennung."""

import unittest
from unittest.mock import patch

from nc_backup.mounts import MountCandidate, _classify


class MountsTests(unittest.TestCase):
    def test_classify_network(self) -> None:
        self.assertEqual(_classify("/mnt/nas", "cifs", "//nas/share"), "network")
        self.assertEqual(_classify("/mnt/nfs", "nfs4", "192.168.1.10:/data"), "network")

    def test_classify_usb_media(self) -> None:
        self.assertEqual(_classify("/media/markus/USBSTICK", "exfat", "/dev/sda1"), "usb")

    def test_display_label(self) -> None:
        item = MountCandidate(path="/media/markus/Backup", label="Backup", kind="usb", free_gb=12.5, writable=True)
        text = item.display
        self.assertIn("[USB]", text)
        self.assertIn("12.5 GB frei", text)
        self.assertIn("/media/markus/Backup", text)


if __name__ == "__main__":
    unittest.main()
