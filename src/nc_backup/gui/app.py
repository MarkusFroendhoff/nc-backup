"""Einstiegspunkt der GTK-Anwendung."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # noqa: E402

from nc_backup.auth import hash_password, verify_password
from nc_backup.config_store import config_needs_password, load_config, save_config
from nc_backup.gui.dialogs import error_dialog, password_dialog
from nc_backup.gui.main_window import MainWindow


class SetupWindow(Gtk.Window):
    def __init__(self):
        super().__init__(title="Nextcloud Backup – Ersteinrichtung")
        self.set_default_size(480, 260)
        self.set_border_width(16)
        self.config = load_config()

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.add(box)

        title = Gtk.Label()
        title.set_markup("<b>Willkommen bei Nextcloud Backup</b>")
        box.pack_start(title, False, False, 0)

        info = Gtk.Label(
            label="Bitte lege ein Master-Passwort fest. Es schützt den Zugriff auf die Anwendung.",
            wrap=True,
            xalign=0,
        )
        box.pack_start(info, False, False, 0)

        button = Gtk.Button(label="Passwort festlegen und starten")
        button.connect("clicked", self._on_setup)
        box.pack_start(button, False, False, 0)

        self.connect("destroy", Gtk.main_quit)

    def _on_setup(self, _button: Gtk.Button) -> None:
        password = password_dialog(self, "Passwort festlegen", "Neues Master-Passwort:", confirm=True)
        if password is None:
            return
        if not password:
            error_dialog(self, "Passwort", "Die Passwörter stimmen nicht überein.")
            return
        self.config.password_hash = hash_password(password)
        self.config.setup_complete = True
        save_config(self.config)
        self.hide()
        launch_main_window(self.config)


def ask_password(parent: Gtk.Window | None, config) -> bool:
    for _attempt in range(3):
        password = password_dialog(parent, "Anmeldung", "Master-Passwort eingeben:")
        if password is None:
            return False
        if verify_password(password, config.password_hash):
            return True
        error_dialog(parent, "Anmeldung", "Falsches Passwort.")
    return False


def launch_main_window(config) -> None:
    window = MainWindow(config)
    window.connect("destroy", Gtk.main_quit)
    window.show_all()


def main() -> int:
    config = load_config()

    if not config.setup_complete or not config_needs_password(config):
        setup = SetupWindow()
        setup.show_all()
        Gtk.main()
        return 0

    login = Gtk.Window(title="Nextcloud Backup")
    login.set_default_size(1, 1)
    login.set_decorated(False)
    login.set_position(Gtk.WindowPosition.CENTER)

    if not ask_password(login, config):
        return 1

    login.destroy()
    launch_main_window(config)
    Gtk.main()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
