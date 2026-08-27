"""Hintergrund-Jobs, damit pkexec die GTK-Oberfläche nicht einfriert."""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

from gi.repository import GLib


def run_async(work: Callable[[], Any], done: Callable[[Any], None]) -> None:
    """Führt work() in einem Daemon-Thread aus und ruft done(result) im GTK-Thread auf.

    Schlägt work() fehl, erhält done die Exception.
    """

    def _thread() -> None:
        try:
            result = work()
        except Exception as exc:  # noqa: BLE001 — an die UI durchreichen
            result = exc
        GLib.idle_add(_finish, result)

    def _finish(result: Any) -> bool:
        done(result)
        return False

    threading.Thread(target=_thread, daemon=True, name="nc-backup-admin").start()


def idle_log(callback: Callable[[str], None], line: str) -> None:
    """Zeile vom Worker-Thread sicher ins GTK-Log schreiben."""
    GLib.idle_add(lambda: (callback(line), False)[1])
