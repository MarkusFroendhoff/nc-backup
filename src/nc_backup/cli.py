"""CLI für geplante Backups (systemd)."""

from __future__ import annotations

import sys

from nc_backup.backup_engine import run_backup, setup_logging
from nc_backup.config_store import load_config
from nc_backup.systemd_schedule import apply_schedule_from_cli


def main(argv: list[str] | None = None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    if "--apply-schedule" in args:
        return apply_schedule_from_cli()

    setup_logging()
    config = load_config()
    if not config.setup_complete:
        print("nc-backup: Ersteinrichtung in der GUI abschließen.", file=sys.stderr)
        return 2

    result = run_backup(config)
    print(result.message)
    if result.destination:
        print(f"Ziel: {result.destination}")
    for err in result.errors:
        print(f"Warnung: {err}", file=sys.stderr)
    return 0 if result.success else 1


if __name__ == "__main__":
    raise SystemExit(main())
