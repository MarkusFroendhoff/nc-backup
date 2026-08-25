"""Tests für Docker-Mount-Erkennung."""

import unittest

from nc_backup.docker_detect import resolve_paths_from_mounts


class DockerDetectTests(unittest.TestCase):
    def test_standard_nextcloud_mounts(self) -> None:
        mounts = [
            {"source": "/srv/nextcloud/data", "destination": "/var/www/html/data"},
            {"source": "/srv/nextcloud/config", "destination": "/var/www/html/config"},
        ]
        folders, config_php, notes = resolve_paths_from_mounts(mounts)
        self.assertIn("/srv/nextcloud/data", folders)
        self.assertIn("/srv/nextcloud/config", folders)
        self.assertTrue(any("config.php" in note for note in notes) or config_php)

    def test_root_mount_expansion(self) -> None:
        mounts = [{"source": "/srv/nextcloud/html", "destination": "/var/www/html"}]
        folders, _, _ = resolve_paths_from_mounts(mounts)
        self.assertIn("/srv/nextcloud/html/data", folders)
        self.assertIn("/srv/nextcloud/html/config", folders)

    def test_docker_volume_note(self) -> None:
        mounts = [
            {
                "source": "/var/lib/docker/volumes/nextcloud_data/_data",
                "destination": "/var/www/html/data",
            }
        ]
        folders, _, notes = resolve_paths_from_mounts(mounts)
        self.assertIn("/var/lib/docker/volumes/nextcloud_data/_data", folders)
        self.assertTrue(any("Docker-Volume" in note for note in notes))


if __name__ == "__main__":
    unittest.main()
