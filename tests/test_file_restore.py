"""Einzeldatei-Export aus Restic-Snapshots — ohne Live-Nextcloud."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from nc_backup.models import AppConfig, BackupMode
from nc_backup.restic_backend import (
    SnapshotNode,
    _immediate_children,
    export_root,
    list_snapshot_paths,
    normalize_snapshot_path,
    parse_find_json,
    parse_ls_json,
    parent_snapshot_path,
    resolve_export_file,
    restore_include_path,
    restore_snapshot,
    validate_snapshot_id,
)
from nc_backup.restore import run_file_restore


LS_JSON = """
{"message_type":"snapshot","id":"aabbccdd","short_id":"aabbccdd","struct_type":"snapshot"}
{"message_type":"node","struct_type":"node","name":"data","type":"dir","path":"/var/www/nextcloud/data"}
{"message_type":"node","struct_type":"node","name":"alice","type":"dir","path":"/var/www/nextcloud/data/alice"}
{"message_type":"node","struct_type":"node","name":"files","type":"dir","path":"/var/www/nextcloud/data/alice/files"}
{"message_type":"node","struct_type":"node","name":"Urlaub.jpg","type":"file","path":"/var/www/nextcloud/data/alice/files/Urlaub.jpg","size":2048}
{"message_type":"node","struct_type":"node","name":"Notes.md","type":"file","path":"/var/www/nextcloud/data/alice/files/Notes.md","size":12}
"""

FIND_JSON = json.dumps(
    [
        {
            "hits": 1,
            "snapshot": "aabbccdd",
            "matches": [
                {
                    "path": "/var/www/nextcloud/data/alice/files/Urlaub.jpg",
                    "name": "Urlaub.jpg",
                    "type": "file",
                    "size": 2048,
                }
            ],
        }
    ]
)


class PathHelperTests(unittest.TestCase):
    def test_normalize_absolute(self) -> None:
        self.assertEqual(
            normalize_snapshot_path("/var/www/nextcloud/data/alice/files/Urlaub.jpg"),
            "/var/www/nextcloud/data/alice/files/Urlaub.jpg",
        )

    def test_normalize_rejects_dotdot(self) -> None:
        with self.assertRaises(ValueError):
            normalize_snapshot_path("/var/www/nextcloud/data/../config")

    def test_normalize_rejects_globs(self) -> None:
        with self.assertRaises(ValueError):
            normalize_snapshot_path("/var/www/**/Urlaub.jpg")

    def test_snapshot_id(self) -> None:
        self.assertEqual(validate_snapshot_id("aabbccdd"), "aabbccdd")
        with self.assertRaises(ValueError):
            validate_snapshot_id("latest")
        with self.assertRaises(ValueError):
            validate_snapshot_id("../etc")

    def test_parent(self) -> None:
        self.assertEqual(parent_snapshot_path("/var/www/data/alice"), "/var/www/data")
        self.assertIsNone(parent_snapshot_path("/"))


class ParseTests(unittest.TestCase):
    def test_parse_ls_skips_snapshot_object(self) -> None:
        nodes = parse_ls_json(LS_JSON)
        paths = [n.path for n in nodes]
        self.assertIn("/var/www/nextcloud/data/alice/files/Urlaub.jpg", paths)
        self.assertTrue(all(n.type in ("file", "dir") for n in nodes))

    def test_immediate_children_only_one_level(self) -> None:
        nodes = parse_ls_json(LS_JSON)
        children = _immediate_children(nodes, "/var/www/nextcloud/data")
        self.assertEqual([c.name for c in children], ["alice"])
        self.assertEqual(children[0].type, "dir")
        files = _immediate_children(nodes, "/var/www/nextcloud/data/alice/files")
        names = {c.name for c in files}
        self.assertEqual(names, {"Notes.md", "Urlaub.jpg"})
        self.assertTrue(all(c.type == "file" for c in files))

    def test_parse_find(self) -> None:
        nodes = parse_find_json(FIND_JSON)
        self.assertEqual(len(nodes), 1)
        self.assertEqual(nodes[0].name, "Urlaub.jpg")
        self.assertEqual(nodes[0].size, 2048)


class ListSnapshotPathsTests(unittest.TestCase):
    def test_browse_uses_ls_without_recursive(self) -> None:
        cfg = AppConfig()
        captured: list[list[str]] = []

        def fake_ls(cfg_arg, sid, args, timeout=60):
            captured.append(args)
            return LS_JSON

        with patch("nc_backup.restic_backend._restic_ls_find", side_effect=fake_ls):
            current, entries = list_snapshot_paths(
                cfg, "aabbccdd", prefix="/var/www/nextcloud/data/alice/files"
            )
        self.assertEqual(current, "/var/www/nextcloud/data/alice/files")
        self.assertEqual(captured[0][:3], ["ls", "--json", "aabbccdd"])
        self.assertNotIn("--recursive", captured[0])
        self.assertEqual({e.name for e in entries}, {"Notes.md", "Urlaub.jpg"})

    def test_search_uses_find_include_filter(self) -> None:
        cfg = AppConfig()
        captured: list[list[str]] = []

        def fake_ls(cfg_arg, sid, args, timeout=60):
            captured.append(args)
            return FIND_JSON

        with patch("nc_backup.restic_backend._restic_ls_find", side_effect=fake_ls):
            _current, entries = list_snapshot_paths(
                cfg, "aabbccdd", search="urlaub"
            )
        self.assertEqual(captured[0][0], "find")
        self.assertIn("--ignore-case", captured[0])
        self.assertIn("*urlaub*", captured[0])
        self.assertEqual(entries[0].name, "Urlaub.jpg")


class RestoreIncludeTests(unittest.TestCase):
    def _cfg(self, tmp: Path) -> AppConfig:
        live = tmp / "nextcloud"
        data = live / "data"
        data.mkdir(parents=True)
        cfg = AppConfig()
        cfg.nextcloud.install_dir = str(live)
        cfg.nextcloud.data_dir = str(data)
        cfg.destination.restic_password = "Abcd1234!"
        cfg.destination.mode = BackupMode.INCREMENTAL
        cfg.destination.local_path = str(tmp / "repo")
        return cfg

    def test_restore_include_stays_in_export_not_live(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            export = tmp / "exports"
            cfg = self._cfg(tmp)
            photo = "/var/www/nextcloud/data/alice/files/Urlaub.jpg"
            seen: list[list[str]] = []

            def fake_run(cmd, env=None, check=True):
                seen.append(list(cmd))
                target = Path(cmd[cmd.index("--target") + 1])
                include = cmd[cmd.index("--include") + 1]
                dest = target / include.lstrip("/")
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(b"jpeg")
                return subprocess.CompletedProcess(cmd, 0, "", "")

            with patch.dict(os.environ, {"NC_BACKUP_EXPORT_ROOT": str(export)}):
                with patch("nc_backup.restic_backend._restic_env", return_value={}):
                    with patch("nc_backup.restic_backend.run", side_effect=fake_run):
                        out = restore_include_path(cfg, "aabbccddeeff0011", photo)

            self.assertTrue(out.is_file())
            self.assertTrue(out.is_relative_to(export.resolve()))
            self.assertFalse(out.is_relative_to(Path(cfg.nextcloud.data_dir).resolve()))
            cmd = seen[0]
            self.assertEqual(cmd[0:3], ["restic", "restore", "aabbccddeeff0011"])
            self.assertIn("--include", cmd)
            self.assertIn(photo, cmd)
            self.assertTrue(Path(cmd[cmd.index("--target") + 1]).is_relative_to(export.resolve()))

    def test_refuses_whole_data_dir(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            cfg = self._cfg(tmp)
            with patch.dict(os.environ, {"NC_BACKUP_EXPORT_ROOT": str(tmp / "exports")}):
                with self.assertRaises(ValueError) as ctx:
                    restore_include_path(cfg, "aabbccdd", cfg.nextcloud.data_dir)
            self.assertIn("Datenverzeichnis", str(ctx.exception))

    def test_download_rejects_outside_export(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            export = tmp / "exports"
            export.mkdir()
            secret = tmp / "secret.txt"
            secret.write_text("nope")
            inside = export / "ok.jpg"
            inside.write_bytes(b"x")
            with patch.dict(os.environ, {"NC_BACKUP_EXPORT_ROOT": str(export)}):
                self.assertEqual(resolve_export_file(str(inside)), inside.resolve())
                with self.assertRaises(ValueError):
                    resolve_export_file(str(secret))
                with self.assertRaises(ValueError):
                    resolve_export_file("/etc/passwd")

    def test_full_restore_helper_has_no_include(self) -> None:
        import inspect

        source = inspect.getsource(restore_snapshot)
        self.assertNotIn("--include", source)
        self.assertIn("--target", source)

    def test_run_file_restore_rejects_legacy(self) -> None:
        cfg = AppConfig()
        cfg.destination.mode = BackupMode.LEGACY
        with self.assertRaises(RuntimeError):
            run_file_restore(cfg, "aabbccdd", "/tmp/x")

    def test_export_root_env(self) -> None:
        with patch.dict(os.environ, {"NC_BACKUP_EXPORT_ROOT": "/tmp/nc-exports"}):
            self.assertEqual(export_root(), Path("/tmp/nc-exports"))


class ImmediateChildrenRootTests(unittest.TestCase):
    def test_root_listing(self) -> None:
        nodes = [
            SnapshotNode(path="/var", name="var", type="dir"),
            SnapshotNode(path="/var/www", name="www", type="dir"),
            SnapshotNode(path="/etc", name="etc", type="dir"),
        ]
        children = _immediate_children(nodes, "")
        self.assertEqual({c.path for c in children}, {"/var", "/etc"})


if __name__ == "__main__":
    unittest.main()
