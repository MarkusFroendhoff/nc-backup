"""Prüfen, ob auf GitHub eine neuere NC-Backup-Version liegt (nur Hinweis, kein Auto-Update)."""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from nc_backup import __version__ as INSTALLED

REPO = "MarkusFroendhoff/nc-backup"
RELEASES_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
PYPROJECT_URL = f"https://raw.githubusercontent.com/{REPO}/main/pyproject.toml"
REPO_URL = f"https://github.com/{REPO}"
CACHE_TTL = 12 * 3600
USER_AGENT = f"nc-backup/{INSTALLED} (+https://github.com/{REPO})"

_VERSION_RE = re.compile(r"""version\s*=\s*["']([0-9]+(?:\.[0-9]+)*)["']""")


def _cache_path() -> Path:
    for raw in ("/var/lib/nc-backup", "/etc/nc-backup", "/tmp"):
        p = Path(raw)
        if p.is_dir() and os.access(p, os.W_OK):
            return p / "update-check.json"
    return Path("/tmp/nc-backup-update-check.json")


def _parse_version(text: str) -> tuple[int, ...]:
    parts = [int(x) for x in re.findall(r"\d+", text or "")]
    return tuple(parts) if parts else (0,)


def is_newer(remote: str, local: str) -> bool:
    return _parse_version(remote) > _parse_version(local)


def _http_get(url: str, timeout: float = 4.0) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _from_releases() -> tuple[str, str] | None:
    try:
        data = json.loads(_http_get(RELEASES_URL))
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return None
    tag = str(data.get("tag_name") or data.get("name") or "").strip()
    if not tag:
        return None
    version = tag.lstrip("vV")
    url = str(data.get("html_url") or REPO_URL)
    return version, url


def _from_pyproject() -> tuple[str, str] | None:
    try:
        text = _http_get(PYPROJECT_URL)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError):
        return None
    match = _VERSION_RE.search(text)
    if not match:
        return None
    return match.group(1), REPO_URL


def _load_cache() -> dict[str, Any] | None:
    path = _cache_path()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if time.time() - float(raw.get("checked_at") or 0) > CACHE_TTL:
        return None
    return raw


def _save_cache(payload: dict[str, Any]) -> None:
    path = _cache_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")
    except OSError:
        pass


def check_for_update(*, force: bool = False) -> dict[str, Any]:
    """Vergleicht die installierte Version mit GitHub. Nie automatisch installieren."""
    if not force:
        cached = _load_cache()
        if cached:
            return cached

    latest = ""
    url = REPO_URL
    found = _from_releases() or _from_pyproject()
    if found:
        latest, url = found

    available = bool(latest) and is_newer(latest, INSTALLED)
    if available:
        message = (
            f"NC Backup {latest} ist verfügbar (installiert: {INSTALLED}). "
            "Bitte aktualisieren — wie bei einem WordPress-Plugin."
        )
    else:
        message = f"NC Backup {INSTALLED} ist aktuell."

    payload: dict[str, Any] = {
        "ok": True,
        "installed": INSTALLED,
        "latest": latest or INSTALLED,
        "update_available": available,
        "url": url,
        "message": message,
        "checked_at": time.time(),
    }
    _save_cache(payload)
    return payload
