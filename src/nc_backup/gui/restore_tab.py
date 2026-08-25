"""GUI-Tab für Backup-Wiederherstellung."""

from __future__ import annotations

import threading
from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk  # noqa: E402

from nc_backup.gui.dialogs import confirm_dialog, error_dialog, info_dialog, password_dialog
from nc_backup.restore_engine import RestoreOptions, is_encrypted_backup, load_backup_info, run_restore


def build_restore_tab(window) -> Gtk.Widget:
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, margin=12)

    info = Gtk.Label(
        label="Backup-Ordner oder verschlüsselte .gpg-Datei wählen, analysieren und wiederherstellen.",
        wrap=True,
        xalign=0,
    )
    box.pack_start(info, False, False, 0)

    path_box = Gtk.Box(spacing=6)
    window.restore_path_entry = Gtk.Entry(placeholder_text="/mnt/backup/nextcloud-backup_… oder .tar.gz.gpg")
    path_box.pack_start(window.restore_path_entry, True, True, 0)
    folder_btn = Gtk.Button(label="Ordner …")
    folder_btn.connect("clicked", lambda _b: _pick_restore_path(window, folder=True))
    path_box.pack_start(folder_btn, False, False, 0)
    file_btn = Gtk.Button(label="Datei …")
    file_btn.connect("clicked", lambda _b: _pick_restore_path(window, folder=False))
    path_box.pack_start(file_btn, False, False, 0)
    box.pack_start(path_box, False, False, 0)

    analyze_btn = Gtk.Button(label="Backup analysieren")
    analyze_btn.connect("clicked", window._on_analyze_backup)
    box.pack_start(analyze_btn, False, False, 0)

    window.restore_info_view = Gtk.TextView()
    window.restore_info_view.set_editable(False)
    window.restore_info_view.set_monospace(True)
    info_scroll = Gtk.ScrolledWindow()
    info_scroll.set_min_content_height(140)
    info_scroll.add(window.restore_info_view)
    box.pack_start(info_scroll, False, False, 0)

    window.restore_files_check = Gtk.CheckButton(label="Dateien wiederherstellen")
    window.restore_files_check.set_active(True)
    box.pack_start(window.restore_files_check, False, False, 0)

    window.restore_db_check = Gtk.CheckButton(label="Datenbank wiederherstellen")
    window.restore_db_check.set_active(True)
    box.pack_start(window.restore_db_check, False, False, 0)

    window.restore_maintenance_check = Gtk.CheckButton(label="Wartungsmodus während Restore (occ)")
    window.restore_maintenance_check.set_active(True)
    box.pack_start(window.restore_maintenance_check, False, False, 0)

    window.restore_delete_check = Gtk.CheckButton(
        label="Zusätzliche Dateien am Ziel löschen (--delete, Vorsicht!)"
    )
    box.pack_start(window.restore_delete_check, False, False, 0)

    restore_btn = Gtk.Button(label="Wiederherstellen")
    restore_btn.connect("clicked", window._on_restore_clicked)
    box.pack_start(restore_btn, False, False, 0)

    window.restore_log_view = Gtk.TextView()
    window.restore_log_view.set_editable(False)
    window.restore_log_view.set_monospace(True)
    log_scroll = Gtk.ScrolledWindow()
    log_scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
    log_scroll.set_min_content_height(160)
    log_scroll.add(window.restore_log_view)
    box.pack_start(log_scroll, True, True, 0)

    window._restore_busy = False
    window._restore_backup_encrypted = False
    return box


def _pick_restore_path(window, folder: bool) -> None:
    action = Gtk.FileChooserAction.SELECT_FOLDER if folder else Gtk.FileChooserAction.OPEN
    dialog = Gtk.FileChooserDialog(
        title="Backup-Ordner wählen" if folder else "Backup-Datei wählen",
        transient_for=window,
        action=action,
    )
    dialog.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OPEN, Gtk.ResponseType.OK)
    response = dialog.run()
    path = dialog.get_filename()
    dialog.destroy()
    if response == Gtk.ResponseType.OK and path:
        window.restore_path_entry.set_text(path)


def append_restore_log(window, text: str) -> None:
    buffer = window.restore_log_view.get_buffer()
    end = buffer.get_end_iter()
    buffer.insert(end, text + "\n")


def set_restore_info(window, text: str) -> None:
    buffer = window.restore_info_view.get_buffer()
    buffer.set_text(text)


def handle_analyze_backup(window) -> None:
    path_text = window.restore_path_entry.get_text().strip()
    if not path_text:
        error_dialog(window, "Analyse", "Bitte einen Backup-Pfad angeben.")
        return

    path = Path(path_text)
    window._restore_backup_encrypted = is_encrypted_backup(path)
    passphrase = ""
    if window._restore_backup_encrypted:
        passphrase = password_dialog(window, "Entschlüsseln", "Verschlüsselungs-Passphrase:")
        if passphrase is None:
            return

    window.status_label.set_text("Backup wird analysiert…")

    def worker() -> None:
        try:
            info = load_backup_info(path, gpg_passphrase=passphrase)
            GLib.idle_add(_on_analyze_done, window, info.summary, None)
        except Exception as exc:  # noqa: BLE001 - GUI-Fehlermeldung
            GLib.idle_add(_on_analyze_done, window, "", str(exc))

    threading.Thread(target=worker, daemon=True).start()


def _on_analyze_done(window, summary: str, error: str | None) -> None:
    window.status_label.set_text("Bereit.")
    if error:
        error_dialog(window, "Analyse fehlgeschlagen", error)
        return
    set_restore_info(window, summary)
    window.restore_db_check.set_sensitive(bool(summary and "Datenbank: ja" in summary))


def handle_restore_clicked(window) -> None:
    if window._restore_busy:
        return

    path_text = window.restore_path_entry.get_text().strip()
    if not path_text:
        error_dialog(window, "Restore", "Bitte einen Backup-Pfad angeben.")
        return

    if not confirm_dialog(
        window,
        "Wiederherstellen",
        "Backup wirklich einspielen? Bestehende Daten können überschrieben werden.",
    ):
        return

    gpg_passphrase = ""
    if window._restore_backup_encrypted or is_encrypted_backup(Path(path_text)):
        gpg_passphrase = password_dialog(window, "Entschlüsseln", "Verschlüsselungs-Passphrase:")
        if gpg_passphrase is None:
            return

    config = window._collect_config_from_ui()
    options = RestoreOptions(
        restore_files=window.restore_files_check.get_active(),
        restore_database=window.restore_db_check.get_active(),
        maintenance_mode=window.restore_maintenance_check.get_active(),
        delete_extra_files=window.restore_delete_check.get_active(),
        gpg_passphrase=gpg_passphrase,
    )

    window._restore_busy = True
    window.status_label.set_text("Wiederherstellung läuft…")
    append_restore_log(window, "--- Restore gestartet ---")

    def worker() -> None:
        result = run_restore(config, Path(path_text), options)
        GLib.idle_add(_on_restore_done, window, result)


def _on_restore_done(window, result) -> None:
    window._restore_busy = False
    window.status_label.set_text("Bereit.")
    append_restore_log(window, result.message)
    for folder in result.restored_folders:
        append_restore_log(window, f"Ordner: {folder}")
    if result.restored_database:
        append_restore_log(window, f"DB: {result.restored_database}")
    for err in result.errors:
        append_restore_log(window, f"Warnung: {err}")
    if result.success:
        info_dialog(window, "Restore", result.message)
    else:
        error_dialog(window, "Restore fehlgeschlagen", result.message)
