"""Einstieg: nc-backup-web."""

from __future__ import annotations

import os
import sys


def main(argv: list[str] | None = None) -> int:
    del argv  # keine CLI-Flags — Bind/Port über Umgebung
    bind = os.environ.get("NC_BACKUP_WEB_BIND", "0.0.0.0")
    try:
        port = int(os.environ.get("NC_BACKUP_WEB_PORT", "42173"))
    except ValueError:
        print("NC_BACKUP_WEB_PORT ist keine Zahl.", file=sys.stderr)
        return 2
    from nc_backup.secrets import ensure_web_token, WEB_TOKEN_PATH
    from nc_backup_web.server import serve

    ensure_web_token()
    print(f"NC Backup Web-Oberfläche: http://{bind}:{port}/", flush=True)
    print(f"Zugangsschlüssel: {WEB_TOKEN_PATH}", flush=True)
    serve(bind, port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
