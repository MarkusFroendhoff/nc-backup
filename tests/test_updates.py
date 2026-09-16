"""Update-Check-Cache: nach Upgrade nicht die alte installierte Version zeigen."""

from __future__ import annotations

import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from nc_backup import updates

REPO_URL = "https://github.com/MarkusFroendhoff/nc-backup"


def _payload(
    *,
    installed: str,
    latest: str,
    update_available: bool,
    checked_at: float | None = None,
    message: str = "cached",
    url: str = REPO_URL,
) -> dict:
    return {
        "ok": True,
        "installed": installed,
        "latest": latest,
        "update_available": update_available,
        "url": url,
        "message": message,
        "checked_at": time.time() if checked_at is None else checked_at,
    }


class UpdateCacheTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.cache = Path(self._tmp.name) / "update-check.json"
        self._path_patch = patch.object(updates, "_cache_path", return_value=self.cache)
        self._path_patch.start()

    def tearDown(self) -> None:
        self._path_patch.stop()
        self._tmp.cleanup()

    def _write(self, payload: dict) -> None:
        self.cache.write_text(json.dumps(payload), encoding="utf-8")

    def test_stale_cache_after_upgrade_returns_current_installed(self) -> None:
        self._write(
            _payload(
                installed="2.0.3",
                latest="2.1.0",
                update_available=True,
                message="NC Backup 2.1.0 ist verfügbar (installiert: 2.0.3).",
            )
        )
        with (
            patch.object(updates, "INSTALLED", "2.1.1"),
            patch.object(updates, "_from_releases", return_value=("2.1.1", REPO_URL)) as releases,
            patch.object(updates, "_from_pyproject") as pyproject,
        ):
            result = updates.check_for_update()
        releases.assert_called_once()
        pyproject.assert_not_called()
        self.assertEqual(result["installed"], "2.1.1")
        self.assertEqual(result["latest"], "2.1.1")
        self.assertFalse(result["update_available"])
        stored = json.loads(self.cache.read_text(encoding="utf-8"))
        self.assertEqual(stored["installed"], "2.1.1")

    def test_ttl_cache_used_when_installed_matches(self) -> None:
        cached = _payload(
            installed="2.1.1",
            latest="2.1.1",
            update_available=False,
            message="from cache",
            url="https://example.test/cached",
        )
        self._write(cached)
        with (
            patch.object(updates, "INSTALLED", "2.1.1"),
            patch.object(
                updates, "_from_releases", side_effect=AssertionError("network must not run")
            ),
            patch.object(
                updates, "_from_pyproject", side_effect=AssertionError("network must not run")
            ),
        ):
            result = updates.check_for_update()
        self.assertEqual(result["installed"], "2.1.1")
        self.assertEqual(result["message"], "from cache")
        self.assertEqual(result["url"], "https://example.test/cached")

    def test_expired_ttl_is_ignored_even_if_installed_matches(self) -> None:
        self._write(
            _payload(
                installed="2.1.1",
                latest="2.1.1",
                update_available=False,
                message="expired",
                checked_at=time.time() - updates.CACHE_TTL - 10,
            )
        )
        with (
            patch.object(updates, "INSTALLED", "2.1.1"),
            patch.object(updates, "_from_releases", return_value=("2.2.0", REPO_URL)),
        ):
            result = updates.check_for_update()
        self.assertEqual(result["installed"], "2.1.1")
        self.assertEqual(result["latest"], "2.2.0")
        self.assertTrue(result["update_available"])

    def test_cache_ignored_if_update_available_wrong_for_installed(self) -> None:
        self._write(
            _payload(
                installed="2.1.1",
                latest="2.1.0",
                update_available=True,
                message="still advertising an older latest",
            )
        )
        with (
            patch.object(updates, "INSTALLED", "2.1.1"),
            patch.object(updates, "_from_releases", return_value=("2.1.1", REPO_URL)),
        ):
            result = updates.check_for_update()
        self.assertEqual(result["installed"], "2.1.1")
        self.assertFalse(result["update_available"])
        self.assertNotEqual(result["message"], "still advertising an older latest")


if __name__ == "__main__":
    unittest.main()
