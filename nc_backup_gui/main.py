#!/usr/bin/env python3
"""NC Backup GUI — Einstiegspunkt."""

from __future__ import annotations

import sys


def main() -> int:
    try:
        import gi

        gi.require_version("Adw", "1")
        gi.require_version("Gtk", "4.0")
    except ImportError:
        print(
            "GTK4 nicht verfügbar. Auf Ubuntu installieren:\n"
            "  sudo apt install python3-gi gir1.2-adw-1 gir1.2-gtk-4.0",
            file=sys.stderr,
        )
        return 1

    from nc_backup_gui.app import NcBackupApplication

    app = NcBackupApplication()
    return app.run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
