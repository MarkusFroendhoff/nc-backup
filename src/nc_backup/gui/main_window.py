"""Hauptfenster der Backup-Anwendung."""

from __future__ import annotations

import threading

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk  # noqa: E402

from nc_backup.backup_engine import run_backup, setup_logging
from nc_backup.config_store import AppConfig, ScheduleConfig, default_config_for_mode, save_config
from nc_backup.docker_detect import detect_docker_installations
from nc_backup.gui.dialogs import (
    choose_docker_detection,
    confirm_dialog,
    error_dialog,
    folder_chooser,
    info_dialog,
    password_dialog,
)
from nc_backup.gui.restore_tab import build_restore_tab, handle_analyze_backup, handle_restore_clicked
from nc_backup.secrets_store import clear_gpg_passphrase, load_gpg_passphrase, save_gpg_passphrase
from nc_backup.systemd_schedule import apply_schedule, describe_schedule


WEEKDAY_LABELS = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]


class MainWindow(Gtk.Window):
    def __init__(self, config: AppConfig):
        super().__init__(title="Nextcloud Backup")
        self.set_default_size(760, 620)
        self.config = config
        self._building = True

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        outer.set_margin_start(16)
        outer.set_margin_end(16)
        outer.set_margin_top(16)
        outer.set_margin_bottom(16)
        self.add(outer)

        header = Gtk.Label()
        header.set_markup("<b>Nextcloud Backup</b>")
        header.set_xalign(0)
        outer.pack_start(header, False, False, 0)

        notebook = Gtk.Notebook()
        outer.pack_start(notebook, True, True, 0)

        notebook.append_page(self._build_backup_tab(), Gtk.Label(label="Backup"))
        notebook.append_page(self._build_settings_tab(), Gtk.Label(label="Einstellungen"))
        notebook.append_page(build_restore_tab(self), Gtk.Label(label="Wiederherstellen"))
        notebook.append_page(self._build_schedule_tab(), Gtk.Label(label="Zeitplan"))

        self.status_label = Gtk.Label(label="Bereit.", xalign=0)
        outer.pack_start(self.status_label, False, False, 0)

        self._load_config_into_ui()
        self._building = False

    def _build_backup_tab(self) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box.set_border_width(12)

        info = Gtk.Label(
            label="Startet eine sofortige Sicherung aller ausgewählten Ordner und optional der Datenbank.",
            wrap=True,
            xalign=0,
        )
        box.pack_start(info, False, False, 0)

        self.backup_button = Gtk.Button(label="Jetzt sichern")
        self.backup_button.connect("clicked", self._on_backup_clicked)
        box.pack_start(self.backup_button, False, False, 0)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_min_content_height(280)
        self.log_view = Gtk.TextView()
        self.log_view.set_editable(False)
        self.log_view.set_monospace(True)
        scrolled.add(self.log_view)
        box.pack_start(scrolled, True, True, 0)
        return box

    def _build_settings_tab(self) -> Gtk.Widget:
        grid = Gtk.Grid(column_spacing=10, row_spacing=8, margin=12)

        row = 0
        grid.attach(Gtk.Label(label="Installationsart:", xalign=0), 0, row, 1, 1)
        self.mode_combo = Gtk.ComboBoxText()
        for mode_id, label in [
            ("native", "Nativ (apt)"),
            ("docker", "Docker"),
            ("custom", "Benutzerdefiniert"),
        ]:
            self.mode_combo.append(mode_id, label)
        self.mode_combo.connect("changed", self._on_mode_changed)
        grid.attach(self.mode_combo, 1, row, 1, 1)
        row += 1

        docker_detect_btn = Gtk.Button(label="Docker automatisch erkennen")
        docker_detect_btn.connect("clicked", self._detect_docker)
        grid.attach(docker_detect_btn, 1, row, 1, 1)
        row += 1

        grid.attach(Gtk.Label(label="config.php:", xalign=0), 0, row, 1, 1)
        config_box = Gtk.Box(spacing=6)
        self.config_php_entry = Gtk.Entry()
        config_box.pack_start(self.config_php_entry, True, True, 0)
        config_btn = Gtk.Button(label="…")
        config_btn.connect("clicked", self._pick_config_php)
        config_box.pack_start(config_btn, False, False, 0)
        grid.attach(config_box, 1, row, 1, 1)
        row += 1

        grid.attach(Gtk.Label(label="Export-Pfad:", xalign=0), 0, row, 1, 1)
        export_box = Gtk.Box(spacing=6)
        self.export_entry = Gtk.Entry()
        export_box.pack_start(self.export_entry, True, True, 0)
        export_btn = Gtk.Button(label="…")
        export_btn.connect("clicked", self._pick_export_path)
        export_box.pack_start(export_btn, False, False, 0)
        grid.attach(export_box, 1, row, 1, 1)
        row += 1

        grid.attach(Gtk.Label(label="Quellordner:", xalign=0), 0, row, 1, 1)
        source_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        list_box = Gtk.Box(spacing=6)
        self.source_list = Gtk.ListBox()
        self.source_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_min_content_height(120)
        scrolled.add(self.source_list)
        list_box.pack_start(scrolled, True, True, 0)
        buttons = Gtk.Box(spacing=6)
        add_btn = Gtk.Button(label="Hinzufügen")
        add_btn.connect("clicked", self._add_source_folder)
        remove_btn = Gtk.Button(label="Entfernen")
        remove_btn.connect("clicked", self._remove_source_folder)
        buttons.pack_start(add_btn, False, False, 0)
        buttons.pack_start(remove_btn, False, False, 0)
        source_box.pack_start(list_box, True, True, 0)
        source_box.pack_start(buttons, False, False, 0)
        grid.attach(source_box, 1, row, 1, 1)
        row += 1

        self.db_check = Gtk.CheckButton(label="Datenbank-Dump einschließen")
        grid.attach(self.db_check, 1, row, 1, 1)
        row += 1

        self.encrypt_check = Gtk.CheckButton(label="Backups mit GPG verschlüsseln")
        grid.attach(self.encrypt_check, 1, row, 1, 1)
        row += 1

        grid.attach(Gtk.Label(label="GPG-Modus:", xalign=0), 0, row, 1, 1)
        self.gpg_mode_combo = Gtk.ComboBoxText()
        self.gpg_mode_combo.append("symmetric", "Passphrase (AES256)")
        self.gpg_mode_combo.append("recipient", "GPG-Schlüssel (Empfänger)")
        grid.attach(self.gpg_mode_combo, 1, row, 1, 1)
        row += 1

        grid.attach(Gtk.Label(label="GPG-Empfänger:", xalign=0), 0, row, 1, 1)
        self.gpg_recipient_entry = Gtk.Entry(placeholder_text="E-Mail oder Key-ID")
        grid.attach(self.gpg_recipient_entry, 1, row, 1, 1)
        row += 1

        gpg_pass_btn = Gtk.Button(label="Verschlüsselungs-Passphrase festlegen")
        gpg_pass_btn.connect("clicked", self._set_gpg_passphrase)
        grid.attach(gpg_pass_btn, 1, row, 1, 1)
        row += 1

        self.remove_plaintext_check = Gtk.CheckButton(
            label="Unverschlüsselten Ordner nach Verschlüsselung löschen"
        )
        self.remove_plaintext_check.set_active(True)
        grid.attach(self.remove_plaintext_check, 1, row, 1, 1)
        row += 1

        grid.attach(Gtk.Label(label="Docker DB-Container:", xalign=0), 0, row, 1, 1)
        self.docker_db_entry = Gtk.Entry(placeholder_text="z. B. nextcloud-db (leer = Host)")
        grid.attach(self.docker_db_entry, 1, row, 1, 1)
        row += 1

        grid.attach(Gtk.Label(label="Docker NC-Container:", xalign=0), 0, row, 1, 1)
        self.docker_nc_entry = Gtk.Entry(placeholder_text="optional, nur zur Dokumentation")
        grid.attach(self.docker_nc_entry, 1, row, 1, 1)
        row += 1

        save_btn = Gtk.Button(label="Einstellungen speichern")
        save_btn.connect("clicked", self._save_settings)
        grid.attach(save_btn, 1, row, 1, 1)
        return grid

    def _build_schedule_tab(self) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, margin=12)

        self.schedule_enabled = Gtk.CheckButton(label="Geplantes Backup aktivieren")
        box.pack_start(self.schedule_enabled, False, False, 0)

        time_box = Gtk.Box(spacing=8)
        time_box.pack_start(Gtk.Label(label="Uhrzeit:"), False, False, 0)
        self.hour_spin = Gtk.SpinButton.new_with_range(0, 23, 1)
        self.hour_spin.set_width_chars(3)
        time_box.pack_start(self.hour_spin, False, False, 0)
        time_box.pack_start(Gtk.Label(label=":"), False, False, 0)
        self.minute_spin = Gtk.SpinButton.new_with_range(0, 59, 1)
        self.minute_spin.set_width_chars(3)
        time_box.pack_start(self.minute_spin, False, False, 0)
        box.pack_start(time_box, False, False, 0)

        weekdays_box = Gtk.Box(spacing=6)
        weekdays_box.pack_start(Gtk.Label(label="Wochentage:"), False, False, 0)
        self.weekday_checks: list[Gtk.CheckButton] = []
        for index, label in enumerate(WEEKDAY_LABELS):
            check = Gtk.CheckButton(label=label)
            if index > 0:
                check.join_group(self.weekday_checks[0])
            self.weekday_checks.append(check)
            weekdays_box.pack_start(check, False, False, 0)
        box.pack_start(weekdays_box, False, False, 0)

        self.schedule_info = Gtk.Label(xalign=0, wrap=True)
        box.pack_start(self.schedule_info, False, False, 0)

        hint = Gtk.Label(
            label="Geplante Backups laufen ohne Passwortabfrage über systemd.\n"
            "Das Master-Passwort schützt nur die GUI und Einstellungen.",
            wrap=True,
            xalign=0,
        )
        box.pack_start(hint, False, False, 0)

        apply_btn = Gtk.Button(label="Zeitplan anwenden")
        apply_btn.connect("clicked", self._apply_schedule)
        box.pack_start(apply_btn, False, False, 0)
        return box

    def _load_config_into_ui(self) -> None:
        self.mode_combo.set_active_id(self.config.install_mode or "native")
        self.config_php_entry.set_text(self.config.config_php_path)
        self.export_entry.set_text(self.config.export_path)
        self.db_check.set_active(self.config.include_database)
        self.encrypt_check.set_active(self.config.encrypt_backups)
        self.gpg_mode_combo.set_active_id(self.config.gpg_mode or "symmetric")
        self.gpg_recipient_entry.set_text(self.config.gpg_recipient)
        self.remove_plaintext_check.set_active(self.config.remove_plaintext_after_encrypt)
        self.docker_db_entry.set_text(self.config.docker_db_container)
        self.docker_nc_entry.set_text(self.config.docker_nextcloud_container)

        for child in self.source_list.get_children():
            self.source_list.remove(child)
        for folder in self.config.source_folders:
            self._append_source_row(folder)

        self.schedule_enabled.set_active(self.config.schedule.enabled)
        self.hour_spin.set_value(self.config.schedule.hour)
        self.minute_spin.set_value(self.config.schedule.minute)
        for index, check in enumerate(self.weekday_checks):
            check.set_active(index in self.config.schedule.weekdays)
        self._refresh_schedule_info()

    def _append_source_row(self, folder: str) -> None:
        row = Gtk.ListBoxRow()
        box = Gtk.Box(spacing=8)
        label = Gtk.Label(label=folder, xalign=0, selectable=True)
        box.pack_start(label, True, True, 0)
        row.add(box)
        row.folder_path = folder
        self.source_list.add(row)
        self.source_list.show_all()

    def _collect_source_folders(self) -> list[str]:
        folders: list[str] = []
        for row in self.source_list.get_children():
            path = getattr(row, "folder_path", "")
            if path:
                folders.append(path)
        return folders

    def _collect_config_from_ui(self) -> AppConfig:
        weekdays = [index for index, check in enumerate(self.weekday_checks) if check.get_active()]
        if not weekdays:
            weekdays = list(range(7))

        return AppConfig(
            install_mode=self.mode_combo.get_active_id() or "native",
            source_folders=self._collect_source_folders(),
            export_path=self.export_entry.get_text().strip(),
            config_php_path=self.config_php_entry.get_text().strip(),
            docker_nextcloud_container=self.docker_nc_entry.get_text().strip(),
            docker_db_container=self.docker_db_entry.get_text().strip(),
            include_database=self.db_check.get_active(),
            encrypt_backups=self.encrypt_check.get_active(),
            gpg_mode=self.gpg_mode_combo.get_active_id() or "symmetric",
            gpg_recipient=self.gpg_recipient_entry.get_text().strip(),
            remove_plaintext_after_encrypt=self.remove_plaintext_check.get_active(),
            password_hash=self.config.password_hash,
            schedule=ScheduleConfig(
                enabled=self.schedule_enabled.get_active(),
                hour=int(self.hour_spin.get_value()),
                minute=int(self.minute_spin.get_value()),
                weekdays=weekdays,
            ),
            setup_complete=True,
        )

    def _apply_docker_detection(self, detection) -> None:
        self.mode_combo.set_active_id("docker")
        self.docker_nc_entry.set_text(detection.nextcloud_container)
        self.docker_db_entry.set_text(detection.db_container)
        self.config_php_entry.set_text(detection.config_php_path)

        for child in self.source_list.get_children():
            self.source_list.remove(child)
        for folder in detection.source_folders:
            self._append_source_row(folder)

        notes = "\n".join(f"• {note}" for note in detection.notes)
        info_dialog(
            self,
            "Docker erkannt",
            f"Container: {detection.nextcloud_container}\n"
            f"DB-Container: {detection.db_container or '–'}\n\n{notes}",
        )

    def _detect_docker(self, _button: Gtk.Button) -> None:
        self.status_label.set_text("Docker wird analysiert…")

        def worker() -> None:
            try:
                detections = detect_docker_installations()
                GLib.idle_add(self._on_docker_detected, detections, None)
            except RuntimeError as exc:
                GLib.idle_add(self._on_docker_detected, [], str(exc))

        threading.Thread(target=worker, daemon=True).start()

    def _on_docker_detected(self, detections: list, error: str | None) -> None:
        self.status_label.set_text("Bereit.")
        if error:
            error_dialog(self, "Docker-Erkennung", error)
            return
        if not detections:
            error_dialog(self, "Docker-Erkennung", "Keine Installation erkannt.")
            return
        detection = detections[0] if len(detections) == 1 else choose_docker_detection(self, detections)
        if detection:
            self._apply_docker_detection(detection)

    def _on_mode_changed(self, _combo: Gtk.ComboBoxText) -> None:
        if self._building:
            return
        mode = self.mode_combo.get_active_id()
        if mode in ("native", "docker") and not self._collect_source_folders():
            defaults = default_config_for_mode(mode)
            self.config_php_entry.set_text(defaults.config_php_path)
            for child in self.source_list.get_children():
                self.source_list.remove(child)
            for folder in defaults.source_folders:
                if folder:
                    self._append_source_row(folder)

    def _pick_config_php(self, _button: Gtk.Button) -> None:
        dialog = Gtk.FileChooserDialog(
            title="config.php wählen",
            transient_for=self,
            action=Gtk.FileChooserAction.OPEN,
        )
        dialog.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OPEN, Gtk.ResponseType.OK)
        response = dialog.run()
        path = dialog.get_filename()
        dialog.destroy()
        if response == Gtk.ResponseType.OK and path:
            self.config_php_entry.set_text(path)

    def _pick_export_path(self, _button: Gtk.Button) -> None:
        path = folder_chooser(self, "Export-Zielordner wählen")
        if path:
            self.export_entry.set_text(path)

    def _add_source_folder(self, _button: Gtk.Button) -> None:
        path = folder_chooser(self, "Quellordner hinzufügen")
        if path and path not in self._collect_source_folders():
            self._append_source_row(path)

    def _remove_source_folder(self, _button: Gtk.Button) -> None:
        row = self.source_list.get_selected_row()
        if row:
            self.source_list.remove(row)

    def _set_gpg_passphrase(self, _button: Gtk.Button) -> None:
        passphrase = password_dialog(
            self,
            "Verschlüsselungs-Passphrase",
            "Passphrase für GPG-Backups (wird sicher für Zeitplan gespeichert):",
            confirm=True,
        )
        if passphrase is None:
            return
        if not passphrase:
            error_dialog(self, "Passphrase", "Die Passwörter stimmen nicht überein.")
            return
        save_gpg_passphrase(passphrase)
        info_dialog(self, "Gespeichert", "Verschlüsselungs-Passphrase wurde gespeichert.")

    def _save_settings(self, _button: Gtk.Button) -> None:
        self.config = self._collect_config_from_ui()
        if self.config.encrypt_backups and self.config.gpg_mode == "symmetric" and not load_gpg_passphrase():
            error_dialog(
                self,
                "Verschlüsselung",
                "Bitte zuerst eine Verschlüsselungs-Passphrase festlegen.",
            )
            return
        if not self.config.encrypt_backups:
            clear_gpg_passphrase()
        save_config(self.config)
        self._refresh_schedule_info()
        self.status_label.set_text("Einstellungen gespeichert.")
        info_dialog(self, "Gespeichert", "Die Einstellungen wurden gespeichert.")

    def _apply_schedule(self, _button: Gtk.Button) -> None:
        self.config = self._collect_config_from_ui()
        save_config(self.config)
        try:
            message = apply_schedule(self.config)
            self._refresh_schedule_info()
            info_dialog(self, "Zeitplan", message)
        except OSError as exc:
            error_dialog(self, "Zeitplan", str(exc))

    def _refresh_schedule_info(self) -> None:
        self.schedule_info.set_text(describe_schedule(self.config.schedule))

    def _append_log(self, text: str) -> None:
        buffer = self.log_view.get_buffer()
        end = buffer.get_end_iter()
        buffer.insert(end, text + "\n")

    def _set_busy(self, busy: bool) -> None:
        self.backup_button.set_sensitive(not busy)
        self.status_label.set_text("Backup läuft…" if busy else "Bereit.")

    def _on_backup_clicked(self, _button: Gtk.Button) -> None:
        self.config = self._collect_config_from_ui()
        save_config(self.config)
        if not confirm_dialog(self, "Backup starten", "Sicherung jetzt starten?"):
            return

        self._append_log("--- Backup gestartet ---")
        self._set_busy(True)

        def worker() -> None:
            setup_logging()
            result = run_backup(self.config)
            GLib.idle_add(self._on_backup_finished, result)

        threading.Thread(target=worker, daemon=True).start()

    def _on_backup_finished(self, result) -> None:
        self._set_busy(False)
        self._append_log(result.message)
        if result.destination:
            self._append_log(f"Ziel: {result.destination}")
        if result.database_dump:
            self._append_log(f"Datenbank: {result.database_dump}")
        if result.encrypted_archive:
            self._append_log(f"Verschlüsselt: {result.encrypted_archive}")
        for err in result.errors:
            self._append_log(f"Warnung: {err}")
        if result.success:
            info_dialog(self, "Backup", result.message)
        else:
            error_dialog(self, "Backup fehlgeschlagen", result.message)

    def _on_analyze_backup(self, _button: Gtk.Button) -> None:
        handle_analyze_backup(self)

    def _on_restore_clicked(self, _button: Gtk.Button) -> None:
        handle_restore_clicked(self)
