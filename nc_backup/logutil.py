"""Einfaches Logging nach stdout (journald bei systemd)."""

from __future__ import annotations

import sys
from datetime import datetime


def log(msg: str) -> None:
    line = f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}"
    print(line, flush=True)


def log_error(msg: str) -> None:
    log(f"FEHLER: {msg}")
    print(msg, file=sys.stderr, flush=True)
