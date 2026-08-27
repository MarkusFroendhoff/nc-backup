"""Kommandozeile — für systemd und Tests."""

from __future__ import annotations

import argparse
import json
import sys

from nc_backup.config_store import load_config, save_config
from nc_backup.engine import run_backup, validate
from nc_backup.logutil import log
from nc_backup.models import AppConfig
from nc_backup.restore import RestoreOptions, get_snapshots, run_restore


def _cmd_run(_: argparse.Namespace) -> int:
    return run_backup()


def _cmd_validate(_: argparse.Namespace) -> int:
    cfg = load_config()
    errors = validate(cfg)
    if errors:
        for e in errors:
            log(f"✗ {e}")
        return 1
    log("Konfiguration OK.")
    return 0


def _cmd_save(args: argparse.Namespace) -> int:
    import yaml
    from pathlib import Path

    data = yaml.safe_load(Path(args.file).read_text(encoding="utf-8"))
    cfg = AppConfig.from_dict(data or {})
    save_config(cfg)
    log(f"Gespeichert: {args.file}")
    return 0


def _cmd_install_timer(_: argparse.Namespace) -> int:
    import subprocess

    subprocess.run(["systemctl", "daemon-reload"], check=True)
    subprocess.run(["systemctl", "enable", "--now", "nc-backup.timer"], check=True)
    log("Timer nc-backup.timer aktiviert.")
    return 0


def _cmd_snapshots(args: argparse.Namespace) -> int:
    cfg = load_config()
    snaps = get_snapshots(cfg)
    if args.json:
        print(json.dumps([s.__dict__ for s in snaps], indent=2))
    else:
        for s in snaps:
            tags = ",".join(s.tags) if s.tags else "-"
            print(f"{s.short_id}  {s.time}  {s.hostname}  [{tags}]  id={s.id}")
    return 0


def _cmd_restore(args: argparse.Namespace) -> int:
    if not (args.database or args.config or args.data):
        args.database = True
        args.config = True
    cfg = load_config()
    opts = RestoreOptions(
        snapshot_id=args.snapshot,
        restore_database=args.database,
        restore_config=args.config,
        restore_data=args.data,
    )
    try:
        run_restore(cfg, opts)
        return 0
    except Exception as exc:
        log(f"FEHLER: {exc}")
        return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="NC Backup — Nextcloud sichern")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("run", help="Backup jetzt ausführen").set_defaults(func=_cmd_run)
    sub.add_parser("validate", help="Konfiguration prüfen").set_defaults(func=_cmd_validate)

    p_save = sub.add_parser("save-yaml", help="YAML nach /etc/nc-backup importieren")
    p_save.add_argument("file")
    p_save.set_defaults(func=_cmd_save)

    sub.add_parser("install-timer", help="systemd-Timer aktivieren").set_defaults(
        func=_cmd_install_timer
    )

    p_snap = sub.add_parser("snapshots", help="Verfügbare Restic-Snapshots auflisten")
    p_snap.add_argument("--json", action="store_true")
    p_snap.set_defaults(func=_cmd_snapshots)

    p_rst = sub.add_parser("restore", help="Aus Snapshot wiederherstellen")
    p_rst.add_argument("snapshot", help="Snapshot-ID oder short_id")
    p_rst.add_argument("--database", action="store_true", help="MariaDB importieren")
    p_rst.add_argument("--config", action="store_true", help="config/ wiederherstellen")
    p_rst.add_argument("--data", action="store_true", help="Dateidaten (Vorsicht!)")
    p_rst.set_defaults(func=_cmd_restore)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
