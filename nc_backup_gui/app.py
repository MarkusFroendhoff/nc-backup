"""Adw.Application."""

from __future__ import annotations

import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")
from gi.repository import Adw, Gio  # noqa: E402

from nc_backup.config_store import load_config
from nc_backup.detect import needs_setup
from nc_backup.models import AppConfig
from nc_backup_gui.window import MainWindow


class NcBackupApplication(Adw.Application):
    def __init__(self) -> None:
        super().__init__(
            application_id="de.ncbackup.NcBackup",
            flags=getattr(
                Gio.ApplicationFlags,
                "DEFAULT_FLAGS",
                getattr(Gio.ApplicationFlags, "DEFAULT", 0),
            ),
        )
        self.connect("activate", self._on_activate)
        self._main: MainWindow | None = None

    def _on_activate(self, _app: Adw.Application) -> None:
        if self._main is not None:
            self._main.present()
            return
        config = load_config()
        if needs_setup(config):
            from nc_backup_gui.setup_wizard import SetupWizard

            wiz = SetupWizard(application=self, config=config, on_done=self._after_wizard)
            wiz.present()
            return
        self._show_main(config)

    def _after_wizard(self, config: AppConfig, completed: bool) -> None:
        if not completed:
            return
        self._show_main(config, page="overview")

    def _show_main(self, config: AppConfig, page: str = "overview") -> None:
        if self._main is None:
            self._main = MainWindow(application=self, config=config, start_page=page)
        self._main.present()
