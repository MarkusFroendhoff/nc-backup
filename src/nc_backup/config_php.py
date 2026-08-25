"""Nextcloud config.php auslesen."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class NextcloudDbConfig:
    dbtype: str
    dbname: str
    dbuser: str
    dbpassword: str
    dbhost: str
    datadirectory: str | None = None


def _extract_php_value(content: str, key: str) -> str | None:
    pattern = rf"'{re.escape(key)}'\s*=>\s*(?:'((?:\\'|[^'])*)'|\"((?:\\\"|[^\"])*)\"|(-?\d+))"
    match = re.search(pattern, content)
    if not match:
        return None
    if match.group(1) is not None:
        return match.group(1).replace("\\'", "'")
    if match.group(2) is not None:
        return match.group(2).replace('\\"', '"')
    return match.group(3)


def parse_config_php(path: str | Path) -> NextcloudDbConfig:
    config_path = Path(path)
    if not config_path.is_file():
        raise FileNotFoundError(f"config.php nicht gefunden: {config_path}")

    content = config_path.read_text(encoding="utf-8", errors="replace")
    dbtype = _extract_php_value(content, "dbtype")
    dbname = _extract_php_value(content, "dbname")
    dbuser = _extract_php_value(content, "dbuser")
    dbpassword = _extract_php_value(content, "dbpassword") or ""
    dbhost = _extract_php_value(content, "dbhost") or "localhost"
    datadirectory = _extract_php_value(content, "datadirectory")

    missing = [name for name, value in [
        ("dbtype", dbtype), ("dbname", dbname), ("dbuser", dbuser),
    ] if not value]
    if missing:
        raise ValueError(f"Unvollständige config.php – fehlend: {', '.join(missing)}")

    return NextcloudDbConfig(
        dbtype=dbtype.lower(),
        dbname=dbname,
        dbuser=dbuser,
        dbpassword=dbpassword,
        dbhost=dbhost,
        datadirectory=datadirectory,
    )
