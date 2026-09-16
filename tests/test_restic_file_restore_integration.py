"""End-to-end with a real restic binary (skipped if missing)."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from nc_backup.models import AppConfig, BackupMode, Provider
from nc_backup.restic_backend import (
    list_snapshot_paths,
    list_snapshots,
    resolve_export_file,
    restore_include_path,
)

RESTIC_BIN = Path("/tmp/restic")


def _have_restic() -> bool:
    return RESTIC_BIN.is_file() or shutil.which("restic") is not None


@unittest.skipUnless(_have_restic(), "restic nicht verfügbar")
class RealResticFileRestoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="nc-restic-it-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        self.repo = self.tmp / "repo"
        self.live = self.tmp / "nextcloud"
        self.data = self.live / "data"
        self.photo_dir = self.data / "alice" / "files" / "Photos"
        self.photo_dir.mkdir(parents=True)
        self.photo = self.photo_dir / "Urlaub.jpg"
        self.photo.write_bytes(b"JPEG-FAKE-PHOTO")
        (self.data / "alice" / "files" / "keep.txt").write_text("live")
        self.export = self.tmp / "exports"
        self.pw = "TestResticPw1!"
        env = os.environ.copy()
        bin_dir = str(RESTIC_BIN.parent) if RESTIC_BIN.is_file() else ""
        if bin_dir:
            env["PATH"] = bin_dir + os.pathsep + env.get("PATH", "")
        env["RESTIC_PASSWORD"] = self.pw
        env["RESTIC_REPOSITORY"] = str(self.repo)
        self.env = env
        restic = str(RESTIC_BIN) if RESTIC_BIN.is_file() else "restic"
        subprocess.run([restic, "init"], env=env, check=True, capture_output=True, text=True)
        subprocess.run(
            [restic, "backup", str(self.data), "--host", "test"],
            env=env,
            check=True,
            capture_output=True,
            text=True,
        )
        self.cfg = AppConfig()
        self.cfg.nextcloud.install_dir = str(self.live)
        self.cfg.nextcloud.data_dir = str(self.data)
        self.cfg.destination.mode = BackupMode.INCREMENTAL
        self.cfg.destination.provider = Provider.LOCAL
        self.cfg.destination.local_path = str(self.repo)
        self.cfg.destination.restic_password = self.pw

    def test_list_and_restore_one_photo_leaves_live_untouched(self) -> None:
        os.environ["NC_BACKUP_EXPORT_ROOT"] = str(self.export)
        extra_path = str(RESTIC_BIN.parent) + os.pathsep + os.environ.get("PATH", "")
        os.environ["PATH"] = extra_path
        self.addCleanup(lambda: os.environ.pop("NC_BACKUP_EXPORT_ROOT", None))
        snaps = list_snapshots(self.cfg)
        self.assertTrue(snaps)
        sid = snaps[0].id

        current, entries = list_snapshot_paths(self.cfg, sid, prefix=str(self.data))
        self.assertEqual(Path(current), self.data)
        names = {e.name for e in entries}
        self.assertIn("alice", names)

        _cur, files = list_snapshot_paths(self.cfg, sid, prefix=str(self.photo_dir))
        photo_nodes = [e for e in files if e.name == "Urlaub.jpg"]
        self.assertEqual(len(photo_nodes), 1)
        self.assertEqual(photo_nodes[0].type, "file")

        _cur, found = list_snapshot_paths(self.cfg, sid, search="urlaub")
        self.assertTrue(any(n.name == "Urlaub.jpg" for n in found))

        live_before = self.photo.read_bytes()
        keep_before = (self.data / "alice" / "files" / "keep.txt").read_text()

        restored = restore_include_path(self.cfg, sid, str(self.photo))
        self.assertTrue(restored.is_file())
        self.assertTrue(restored.is_relative_to(self.export.resolve()))
        self.assertEqual(restored.read_bytes(), b"JPEG-FAKE-PHOTO")
        self.assertFalse(restored.is_relative_to(self.data.resolve()))

        self.assertEqual(self.photo.read_bytes(), live_before)
        self.assertEqual((self.data / "alice" / "files" / "keep.txt").read_text(), keep_before)
        self.assertEqual(resolve_export_file(str(restored)), restored.resolve())
