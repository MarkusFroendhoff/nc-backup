"""Startet GTK oder Web-GUI abhängig von der Umgebung."""

from __future__ import annotations

import os
import sys


def main() -> int:
    args = sys.argv[1:]
    force_web = "--web" in args
    force_gui = "--gui" in args

    has_display = bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))

    if force_gui or (has_display and not force_web):
        from nc_backup.gui.app import main as gui_main

        return gui_main()

    from nc_backup.web.app import main as web_main

    return web_main()


if __name__ == "__main__":
    raise SystemExit(main())
