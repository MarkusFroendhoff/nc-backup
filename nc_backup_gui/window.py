"""Hauptfenster — GTK4 / Libadwaita, Mockup A (Sidebar + Übersicht)."""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path

import gi
import yaml

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Adw, Gdk, Gtk  # noqa: E402

from nc_backup.models import AppConfig, BackupMode, Provider
from nc_backup_gui.admin import (
    install_timer_as_admin,
    list_snapshots_as_admin,
    restore_as_admin,
    run_backup_as_admin,
    save_config_as_admin,
)
from nc_backup_gui.jobs import idle_log, run_async
from nc_backup_gui.passwords import (
    generate_restic_password,
    password_error_message,
)
from nc_backup_gui.rclone_dialog import RcloneWizardDialog

PAGES = [
    ("overview", "Übersicht", "go-home-symbolic"),
    ("setup", "Einrichtung", "emblem-system-symbolic"),
    ("dest", "Ziel", "folder-remote-symbolic"),
    ("schedule", "Zeitplan", "alarm-symbolic"),
    ("restore", "Wiederherstellung", "document-revert-symbolic"),
    ("log", "Protokoll", "text-x-generic-symbolic"),
]

MODE_IDS = ["incremental", "legacy"]
MODE_LABELS = [
    "Laufende Sicherung (empfohlen)",
    "Jedes Mal eine komplette Datei",
]
PROVIDER_IDS = ["local", "sftp", "s3", "azure", "b2", "webdav", "rclone"]
PROVIDER_LABELS = [
    "Dieser Rechner / NAS-Ordner",
    "Anderer Server (SFTP)",
    "S3-Speicher (AWS, MinIO, …)",
    "Azure Blob",
    "Backblaze B2",
    "WebDAV (andere Nextcloud, Synology)",
    "Cloud-Dienst (Dropbox, Google Drive, …)",
]
PROVIDER_STACK_IDS = ("sftp", "s3", "webdav", "rclone", "azure", "b2")
TIME_RE = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")

CSS = """
window.nc-backup-window {
  background-color: #f6f5f4;
}
.nc-sidebar {
  background-color: #f6f5f4;
  min-width: 220px;
}
.nc-card {
  background-color: #ffffff;
  border-radius: 16px;
  padding: 20px 24px;
}
.nc-card-title {
  font-weight: 700;
  font-size: 15pt;
}
.nc-hero {
  min-height: 44px;
  min-width: 200px;
}
"""


def _apply_css() -> None:
    provider = Gtk.CssProvider()
    try:
        provider.load_from_string(CSS)
    except AttributeError:
        provider.load_from_data(CSS.encode("utf-8"))
    display = Gdk.Display.get_default()
    if display is None:
        return
    Gtk.StyleContext.add_provider_for_display(
        display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
    )


def _combo_row(title: str, subtitle: str, labels: list[str]) -> Adw.ComboRow:
    row = Adw.ComboRow(title=title, subtitle=subtitle)
    row.set_model(Gtk.StringList.new(labels))
    return row


def _spin_row(title: str, subtitle: str, value: int, low: int, high: int) -> Adw.SpinRow:
    row = Adw.SpinRow.new_with_range(low, high, 1)
    row.set_title(title)
    if subtitle:
        row.set_subtitle(subtitle)
    row.set_value(value)
    row.set_digits(0)
    return row


def _selected_id(combo: Adw.ComboRow, ids: list[str], fallback: str) -> str:
    idx = int(combo.get_selected())
    if 0 <= idx < len(ids):
        return ids[idx]
    return fallback


def _set_selected_id(combo: Adw.ComboRow, ids: list[str], value: str) -> None:
    try:
        combo.set_selected(ids.index(value))
    except ValueError:
        combo.set_selected(0)


class MainWindow(Adw.ApplicationWindow):
    def __init__(
        self,
        *,
        application: Adw.Application,
        config: AppConfig,
        start_page: str = "overview",
    ) -> None:
        super().__init__(application=application, title="NC Backup")
        self._cfg = config
        self._dirty = False
        self._loading = True
        self._busy = False
        self._snaps_tried = False
        self._selected_snapshot_id: str | None = None
        self._page_rows: dict[str, Gtk.ListBoxRow] = {}
        self.set_default_size(1040, 740)
        self.add_css_class("nc-backup-window")
        _apply_css()

        header = Adw.HeaderBar()
        self._window_title = Adw.WindowTitle(title="Übersicht", subtitle="NC Backup")
        header.set_title_widget(self._window_title)

        self._save_btn = Gtk.Button(label="Speichern")
        self._save_btn.add_css_class("suggested-action")
        self._save_btn.connect("clicked", self._on_save)
        header.pack_start(self._save_btn)

        self._header_spinner = Gtk.Spinner()
        self._header_spinner.set_visible(False)
        header.pack_end(self._header_spinner)

        self._toast_overlay = Adw.ToastOverlay()
        toolbar = Adw.ToolbarView()
        toolbar.add_top_bar(header)

        self._stack = Adw.ViewStack()
        self._stack.add_named(self._build_overview_page(), "overview")
        self._stack.add_named(self._build_setup_page(), "setup")
        self._stack.add_named(self._build_dest_page(), "dest")
        self._stack.add_named(self._build_schedule_page(), "schedule")
        self._stack.add_named(self._build_restore_page(), "restore")
        self._stack.add_named(self._build_log_page(), "log")
        self._stack.connect("notify::visible-child-name", self._on_page_changed)

        sidebar = Gtk.ListBox()
        sidebar.add_css_class("navigation-sidebar")
        sidebar.set_selection_mode(Gtk.SelectionMode.SINGLE)
        for page_id, title, icon in PAGES:
            row = Gtk.ListBoxRow()
            box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            box.set_margin_start(8)
            box.set_margin_end(8)
            box.set_margin_top(10)
            box.set_margin_bottom(10)
            img = Gtk.Image.new_from_icon_name(icon)
            lab = Gtk.Label(label=title, xalign=0)
            lab.set_hexpand(True)
            box.append(img)
            box.append(lab)
            row.set_child(box)
            row.page_id = page_id  # type: ignore[attr-defined]
            sidebar.append(row)
            self._page_rows[page_id] = row
        sidebar.connect("row-selected", self._on_sidebar)
        self._sidebar = sidebar

        side_wrap = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        side_wrap.add_css_class("nc-sidebar")
        side_wrap.set_size_request(220, -1)
        side_wrap.append(sidebar)

        split = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        split.append(side_wrap)
        split.append(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL))
        self._stack.set_hexpand(True)
        split.append(self._stack)

        busy = Adw.StatusPage(
            title="Bitte warten …",
            description="Die Aktion läuft mit Administratorrechten. Das Fenster bleibt bedienbar.",
        )
        spinner = Gtk.Spinner()
        spinner.set_spinning(True)
        spinner.set_size_request(36, 36)
        spinner.set_halign(Gtk.Align.CENTER)
        busy.set_child(spinner)
        self._busy_page = busy

        self._root_stack = Gtk.Stack()
        self._root_stack.add_named(split, "main")
        self._root_stack.add_named(busy, "busy")

        toolbar.set_content(self._root_stack)
        self._toast_overlay.set_child(toolbar)
        self.set_content(self._toast_overlay)

        self._bind_from_config()
        self._loading = False
        self._set_dirty(False)
        self._connect_dirty_signals()
        self.connect("close-request", self._on_close_request)

        target = start_page if start_page in self._page_rows else "overview"
        sidebar.select_row(self._page_rows[target])
        self._refresh_overview()

    def _show_toast(self, msg: str) -> None:
        self._toast_overlay.add_toast(Adw.Toast.new(msg))

    def _wrap_page(self, *widgets: Gtk.Widget, max_size: int = 720) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        box.set_margin_top(28)
        box.set_margin_bottom(32)
        box.set_margin_start(28)
        box.set_margin_end(28)
        for w in widgets:
            box.append(w)
        clamp = Adw.Clamp()
        clamp.set_maximum_size(max_size)
        clamp.set_tightening_threshold(480)
        clamp.set_child(box)
        sw = Gtk.ScrolledWindow()
        sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        sw.set_child(clamp)
        sw.set_vexpand(True)
        return sw

    def _choose_folder(self, setter) -> None:
        dialog = Gtk.FileDialog(title="Ordner wählen")
        dialog.set_modal(True)

        def finished(dlg: Gtk.FileDialog, result) -> None:
            try:
                folder = dlg.select_folder_finish(result)
            except Exception:
                return
            if folder is None:
                return
            path = folder.get_path()
            if path:
                setter(path)

        dialog.select_folder(self, None, finished)

    def _add_folder_btn(self, row: Adw.EntryRow) -> None:
        btn = Gtk.Button(icon_name="folder-open-symbolic")
        btn.add_css_class("flat")
        btn.set_valign(Gtk.Align.CENTER)
        btn.set_tooltip_text("Ordner wählen")
        btn.connect("clicked", lambda *_: self._choose_folder(row.set_text))
        row.add_suffix(btn)

    def _card(self, title: str, body: str) -> tuple[Gtk.Box, Gtk.Label, Gtk.Label]:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.add_css_class("nc-card")
        box.add_css_class("card")
        t = Gtk.Label(label=title, xalign=0, wrap=True)
        t.add_css_class("nc-card-title")
        b = Gtk.Label(label=body, xalign=0, wrap=True)
        b.add_css_class("dim-label")
        box.append(t)
        box.append(b)
        return box, t, b

    # --- Overview ---
    def _build_overview_page(self) -> Gtk.Widget:
        heading = Gtk.Label(label="Übersicht", xalign=0)
        heading.add_css_class("title-1")
        intro = Gtk.Label(
            label="Ein Blick darauf, ob Ihre Nextcloud geschützt ist — ohne Fachchinesisch.",
            wrap=True,
            xalign=0,
        )
        intro.add_css_class("dim-label")

        c1, self._ov_nc_title, self._ov_nc_body = self._card("Nextcloud", "…")
        c2, self._ov_dest_title, self._ov_dest_body = self._card("Speicherort", "…")
        c3, self._ov_sched_title, self._ov_sched_body = self._card("Zeitplan", "…")
        c4, self._ov_log_title, self._ov_log_body = self._card("Letzte Meldung", "Noch kein Protokoll.")

        self._ov_hints = Gtk.Label(wrap=True, xalign=0)
        self._ov_hints.add_css_class("heading")

        self._ov_backup_btn = Gtk.Button(label="Jetzt sichern")
        self._ov_backup_btn.add_css_class("suggested-action")
        self._ov_backup_btn.add_css_class("pill")
        self._ov_backup_btn.add_css_class("nc-hero")
        self._ov_backup_btn.set_halign(Gtk.Align.START)
        self._ov_backup_btn.connect("clicked", self._on_run)

        self._update_banner = Adw.Banner(title="")
        self._update_banner.set_revealed(False)
        self._update_banner.set_button_label("Ansehen")
        self._update_url = "https://github.com/MarkusFroendhoff/nc-backup"
        self._update_banner.connect("button-clicked", self._on_open_update)

        return self._wrap_page(
            self._update_banner, heading, intro, c1, c2, c3, c4, self._ov_hints, self._ov_backup_btn
        )

    def _on_open_update(self, *_args) -> None:
        from gi.repository import Gio

        url = getattr(self, "_update_url", "") or "https://github.com/MarkusFroendhoff/nc-backup"
        try:
            Gio.AppInfo.launch_default_for_uri(url, None)
        except Exception:
            pass

    def _apply_update_info(self, info) -> None:
        if isinstance(info, Exception) or not isinstance(info, dict) or not info.get("update_available"):
            self._update_banner.set_revealed(False)
            return
        self._update_url = str(info.get("url") or "https://github.com/MarkusFroendhoff/nc-backup")
        self._update_banner.set_title(str(info.get("message") or "Eine neue Version ist verfügbar."))
        self._update_banner.set_revealed(True)

    def _refresh_overview(self) -> None:
        install = self._nc_install.get_text().strip()
        data = self._nc_data.get_text().strip()
        if install:
            self._ov_nc_title.set_text("Nextcloud")
            self._ov_nc_body.set_text(f"gefunden unter {install}" if install else "Noch kein Ordner angegeben.")
            extra = f"\nDatenordner: {data}" if data else ""
            self._ov_nc_body.set_text(f"{install}{extra}")
        else:
            self._ov_nc_title.set_text("Nextcloud")
            self._ov_nc_body.set_text("Noch kein Ordner angegeben. Unter Einrichtung nachtragen.")

        mode = _selected_id(self._mode_combo, MODE_IDS, "incremental")
        pid = _selected_id(self._provider_combo, PROVIDER_IDS, "local")
        self._ov_dest_title.set_text("Speicherort")
        self._ov_dest_body.set_text(self._dest_summary_text(mode, pid))

        if self._sched_enabled.get_active():
            t = self._sched_time.get_text().strip() or "02:30"
            self._ov_sched_title.set_text("Zeitplan")
            self._ov_sched_body.set_text(f"Täglich automatisch um {t} Uhr.")
        else:
            self._ov_sched_title.set_text("Zeitplan")
            self._ov_sched_body.set_text("Kein automatischer Zeitplan — nur manuell mit „Jetzt sichern“.")

        snippet = self._log_snippet()
        self._ov_log_title.set_text("Letzte Meldung")
        self._ov_log_body.set_text(snippet or "Noch kein Protokoll in dieser Sitzung.")

        hints = self._validation_errors()
        if hints:
            self._ov_hints.set_text("Damit eine Sicherung klappt, fehlt noch:\n• " + "\n• ".join(hints))
            self._ov_hints.set_visible(True)
        else:
            self._ov_hints.set_text("Alles bereit für eine Sicherung.")
            self._ov_hints.set_visible(True)

        def _check():
            from nc_backup.updates import check_for_update

            return check_for_update()

        run_async(_check, self._apply_update_info)

    def _dest_summary_text(self, mode: str, pid: str) -> str:
        kind = "laufende Sicherung" if mode == "incremental" else "komplette Archive"
        if pid == "local":
            path = self._local_path.get_text().strip() or "dieser Rechner"
            return f"{kind} auf diesem Rechner\n{path}"
        if pid == "sftp":
            host = self._sftp_host.get_text().strip() or "…"
            return f"{kind} auf einem anderen Server ({host})"
        if pid == "s3":
            return f"{kind} in einem S3-Speicher ({self._s3_bucket.get_text().strip() or 'Bucket fehlt'})"
        if pid == "azure":
            return f"{kind} in Azure"
        if pid == "b2":
            return f"{kind} bei Backblaze B2"
        if pid == "webdav":
            return f"{kind} per WebDAV"
        if pid == "rclone":
            remote = self._rclone_remote.get_text().strip() or "noch nicht eingerichtet"
            return f"{kind} in der Cloud ({remote})"
        return kind

    def _log_snippet(self) -> str:
        start = self._log_buffer.get_start_iter()
        end = self._log_buffer.get_end_iter()
        text = self._log_buffer.get_text(start, end, False).strip()
        if not text:
            return ""
        lines = [ln for ln in text.splitlines() if ln.strip()]
        return "\n".join(lines[-6:])

    # --- Einrichtung (Nextcloud + Datenbank) ---
    def _build_setup_page(self) -> Gtk.Widget:
        self._nc_install = Adw.EntryRow(title="Ordner der Nextcloud")
        self._add_folder_btn(self._nc_install)
        self._nc_data = Adw.EntryRow(title="Datenordner")
        self._add_folder_btn(self._nc_data)
        self._nc_user = Adw.EntryRow(title="Konto der Website")
        self._nc_user.set_tooltip_text("Meist www-data — das Konto, unter dem der Webserver läuft.")
        self._nc_maint = Adw.SwitchRow(
            title="Während der Sicherung sperren",
            subtitle="Nextcloud kurz in den Wartungsmodus versetzen, damit Dateien nicht halb kopiert werden.",
        )

        nc = Adw.PreferencesGroup(
            title="Nextcloud",
            description="Wo Ihre Cloud auf diesem Rechner liegt.",
        )
        self._nc_container = Adw.EntryRow(title="Docker-Container Nextcloud")
        self._nc_container.set_tooltip_text("Leer lassen, wenn Nextcloud nicht in Docker läuft.")

        nc.add(self._nc_install)
        nc.add(self._nc_data)
        nc.add(self._nc_user)
        nc.add(self._nc_container)
        nc.add(self._nc_maint)

        self._db_host = Adw.EntryRow(title="Datenbank-Rechner")
        self._db_port = _spin_row("Port", "Nur ändern, wenn Ihre Datenbank nicht den Standard nutzt.", 3306, 1, 65535)
        self._db_name = Adw.EntryRow(title="Name der Datenbank")
        self._db_user = Adw.EntryRow(title="Benutzername")
        self._db_pass = Adw.PasswordEntryRow(title="Passwort")
        self._db_container = Adw.EntryRow(title="Docker-Container Datenbank")
        self._db_container.set_tooltip_text(
            "Wenn gesetzt, erfolgt der Dump per docker exec in diesen Container."
        )
        self._db_type = Adw.EntryRow(title="Datenbanktyp")
        self._db_type.set_tooltip_text("mysql, mariadb oder pgsql")

        db = Adw.PreferencesGroup(
            title="Datenbank",
            description="Zugangsdaten, damit die Sicherung auch Ihre Dateiliste und Einstellungen enthält.",
        )
        db.add(self._db_host)
        db.add(self._db_port)
        db.add(self._db_name)
        db.add(self._db_user)
        db.add(self._db_pass)
        db.add(self._db_type)
        db.add(self._db_container)
        return self._wrap_page(nc, db)

    # --- Ziel ---
    def _build_dest_page(self) -> Gtk.Widget:
        self._mode_combo = _combo_row(
            "Art der Sicherung",
            "Die laufende Sicherung merkt sich nur Änderungen und spart Platz.",
            MODE_LABELS,
        )
        self._provider_combo = _combo_row(
            "Wohin soll kopiert werden?",
            "",
            PROVIDER_LABELS,
        )
        self._mode_combo.connect("notify::selected", self._on_mode_changed)
        self._provider_combo.connect("notify::selected", self._on_provider_changed)

        self._restic_pw = Adw.PasswordEntryRow(title="Wiederherstellungs-Passwort")
        gen = Gtk.Button(icon_name="view-refresh-symbolic")
        gen.add_css_class("flat")
        gen.set_valign(Gtk.Align.CENTER)
        gen.set_tooltip_text("Sicheres Passwort erzeugen")
        gen.connect("clicked", self._on_generate_pw)
        self._restic_pw.add_suffix(gen)

        self._legacy_hint = Gtk.Label(
            label="Bei kompletten Archiven (tar.gz) ist kein Wiederherstellungs-Passwort nötig. "
            "Die Dateien werden größer und die Sicherung dauert länger.",
            wrap=True,
            xalign=0,
        )
        self._legacy_hint.add_css_class("dim-label")

        self._local_path = Adw.EntryRow(title="Ordner für die Sicherung")
        self._local_path.set_tooltip_text(
            "Restic-Repository — bei WebDAV und Cloud-Diensten auch der Zwischenordner auf diesem Rechner."
        )
        self._add_folder_btn(self._local_path)

        self._sftp_host = Adw.EntryRow(title="Server")
        self._sftp_user = Adw.EntryRow(title="Benutzername")
        self._sftp_path = Adw.EntryRow(title="Ordner auf dem Server")
        self._sftp_pass = Adw.PasswordEntryRow(title="Passwort (optional, Schlüssel ist besser)")

        self._s3_endpoint = Adw.EntryRow(title="Server-Adresse")
        self._s3_bucket = Adw.EntryRow(title="Bucket")
        self._s3_prefix = Adw.EntryRow(title="Unterordner")
        self._s3_region = Adw.EntryRow(title="Region")
        self._s3_key = Adw.EntryRow(title="Zugangsschlüssel")
        self._s3_secret = Adw.PasswordEntryRow(title="Geheimschlüssel")

        self._webdav_url = Adw.EntryRow(title="Adresse")
        self._webdav_user = Adw.EntryRow(title="Benutzername")
        self._webdav_pass = Adw.PasswordEntryRow(title="Passwort")

        self._rclone_remote = Adw.EntryRow(title="Name der Cloud-Verbindung")
        self._rclone_path = Adw.EntryRow(title="Ordner in der Cloud")
        self._rclone_row = Adw.ActionRow(
            title="Cloud-Assistent",
            subtitle="Dropbox, Google Drive, OneDrive und andere Dienste einrichten",
        )
        self._rclone_row.set_activatable(True)
        self._rclone_row.add_suffix(Gtk.Image.new_from_icon_name("go-next-symbolic"))
        self._rclone_row.connect("activated", self._on_rclone_wizard)

        self._azure_account = Adw.EntryRow(title="Storage-Konto")
        self._azure_key = Adw.PasswordEntryRow(title="Schlüssel")
        self._azure_container = Adw.EntryRow(title="Container")

        self._b2_account_id = Adw.EntryRow(title="Konto-ID")
        self._b2_account_key = Adw.PasswordEntryRow(title="Anwendungsschlüssel")
        self._b2_bucket = Adw.EntryRow(title="Bucket")

        self._keep_daily = _spin_row("Tage behalten", "Wie viele tägliche Stände bleiben erhalten.", 7, 1, 365)
        self._keep_weekly = _spin_row("Wochen behalten", "", 4, 0, 52)
        self._keep_monthly = _spin_row("Monate behalten", "", 6, 0, 120)

        self._provider_stack = Gtk.Stack()
        self._provider_stack.add_named(
            self._group("Verbindungsdaten", [
                self._sftp_host, self._sftp_user, self._sftp_path, self._sftp_pass,
            ]),
            "sftp",
        )
        self._provider_stack.add_named(
            self._group("Verbindungsdaten", [
                self._s3_endpoint, self._s3_bucket, self._s3_prefix,
                self._s3_region, self._s3_key, self._s3_secret,
            ]),
            "s3",
        )
        self._provider_stack.add_named(
            self._group("Verbindungsdaten", [
                self._webdav_url, self._webdav_user, self._webdav_pass,
            ]),
            "webdav",
        )
        rclone_g = self._group("Verbindungsdaten", [self._rclone_remote, self._rclone_path, self._rclone_row])
        self._provider_stack.add_named(rclone_g, "rclone")
        self._provider_stack.add_named(
            self._group("Verbindungsdaten", [
                self._azure_account, self._azure_key, self._azure_container,
            ]),
            "azure",
        )
        self._provider_stack.add_named(
            self._group("Verbindungsdaten", [
                self._b2_account_id, self._b2_account_key, self._b2_bucket,
            ]),
            "b2",
        )
        self._provider_stack.add_named(Adw.PreferencesGroup(), "local")

        top = Adw.PreferencesGroup(title="Ziel der Sicherung")
        top.add(self._mode_combo)
        top.add(self._provider_combo)
        top.add(self._restic_pw)
        top.add(self._local_path)

        self._ret_group = Adw.PreferencesGroup(
            title="Wie lange aufheben?",
            description="Ältere Stände werden automatisch entfernt.",
        )
        self._ret_group.add(self._keep_daily)
        self._ret_group.add(self._keep_weekly)
        self._ret_group.add(self._keep_monthly)

        local_hint = Gtk.Label(
            label="„Ordner für die Sicherung“ ist das Restic-Archiv. "
            "Bei WebDAV und Cloud-Diensten dient er zusätzlich als Zwischenordner auf diesem Rechner.",
            wrap=True,
            xalign=0,
        )
        local_hint.add_css_class("caption")
        local_hint.add_css_class("dim-label")

        return self._wrap_page(top, self._legacy_hint, local_hint, self._provider_stack, self._ret_group)

    def _group(self, title: str, rows: list[Gtk.Widget]) -> Adw.PreferencesGroup:
        g = Adw.PreferencesGroup(title=title)
        for row in rows:
            g.add(row)
        return g

    def _build_schedule_page(self) -> Gtk.Widget:
        self._sched_enabled = Adw.SwitchRow(
            title="Täglich automatisch sichern",
            subtitle="Nachts, wenn niemand arbeitet",
        )
        self._sched_time = Adw.EntryRow(title="Uhrzeit (Stunden:Minuten)")
        self._sched_time.set_text("02:30")
        self._sched_time.connect("changed", self._on_time_changed)
        self._timer_row = Adw.ActionRow(
            title="Automatik auf dem Rechner aktivieren",
            subtitle="Speichert und stellt den täglichen Timer ein (Administratorrechte)",
        )
        self._timer_row.set_activatable(True)
        self._timer_row.add_suffix(Gtk.Image.new_from_icon_name("go-next-symbolic"))
        self._timer_row.connect("activated", self._on_install_timer)
        group = Adw.PreferencesGroup(title="Zeitplan")
        group.add(self._sched_enabled)
        group.add(self._sched_time)
        group.add(self._timer_row)
        hint = Gtk.Label(
            label="Bitte die Uhrzeit als 02:30 schreiben. Ungültige Angaben werden vor dem Speichern gemeldet.",
            wrap=True,
            xalign=0,
        )
        hint.add_css_class("dim-label")
        return self._wrap_page(group, hint)

    def _build_restore_page(self) -> Gtk.Widget:
        banner = Adw.Banner(
            title="Wiederherstellen überschreibt vorhandene Daten. Vorher am besten testen."
        )
        banner.set_revealed(True)

        empty = Adw.StatusPage(
            icon_name="document-open-recent-symbolic",
            title="Noch keine Sicherungen geladen",
            description="Die Liste kommt aus Ihrem Sicherungsarchiv. "
            "Beim ersten Öffnen dieser Seite wird automatisch geladen.",
        )
        load_btn = Gtk.Button(label="Sicherungen laden")
        load_btn.add_css_class("pill")
        load_btn.add_css_class("suggested-action")
        load_btn.set_halign(Gtk.Align.CENTER)
        load_btn.connect("clicked", self._on_refresh_snapshots)
        empty.set_child(load_btn)
        self._restore_load_btn = load_btn

        loading = Adw.StatusPage(title="Sicherungen werden geladen …")
        sp = Gtk.Spinner()
        sp.set_spinning(True)
        sp.set_halign(Gtk.Align.CENTER)
        loading.set_child(sp)

        self._snap_list = Gtk.ListBox()
        self._snap_list.add_css_class("boxed-list")
        self._snap_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self._snap_list.connect("row-selected", self._on_snapshot_selected)

        self._restore_db = Adw.SwitchRow(title="Datenbank wiederherstellen", subtitle="Dateiliste, Freigaben, Einstellungen")
        self._restore_db.set_active(True)
        self._restore_cfg = Adw.SwitchRow(title="Konfiguration wiederherstellen", subtitle="Ordner config/")
        self._restore_cfg.set_active(True)
        self._restore_data = Adw.SwitchRow(
            title="Nutzerdateien wiederherstellen",
            subtitle="Überschreibt alle Dateien in der Cloud — nur bei Bedarf",
        )
        self._restore_data.set_active(False)
        opts = Adw.PreferencesGroup(title="Was soll zurück?")
        opts.add(self._restore_db)
        opts.add(self._restore_cfg)
        opts.add(self._restore_data)

        restore_btn = Gtk.Button(label="Ausgewählte Sicherung wiederherstellen")
        restore_btn.add_css_class("destructive-action")
        restore_btn.add_css_class("pill")
        restore_btn.set_halign(Gtk.Align.START)
        restore_btn.connect("clicked", self._on_restore)
        self._restore_btn = restore_btn

        list_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        list_box.append(self._snap_list)
        list_box.append(opts)
        list_box.append(restore_btn)

        self._restore_stack = Gtk.Stack()
        self._restore_stack.add_named(empty, "empty")
        self._restore_stack.add_named(loading, "loading")
        self._restore_stack.add_named(list_box, "list")

        refresh = Gtk.Button(label="Liste aktualisieren")
        refresh.add_css_class("flat")
        refresh.set_halign(Gtk.Align.START)
        refresh.connect("clicked", self._on_refresh_snapshots)
        self._restore_refresh = refresh

        return self._wrap_page(banner, self._restore_stack, refresh)

    def _build_log_page(self) -> Gtk.Widget:
        self._log_buffer = Gtk.TextBuffer()
        view = Gtk.TextView(buffer=self._log_buffer, editable=False, monospace=True)
        view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        view.set_margin_top(12)
        view.set_margin_bottom(12)
        view.set_margin_start(16)
        view.set_margin_end(16)
        sw = Gtk.ScrolledWindow()
        sw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        sw.set_child(view)
        sw.set_vexpand(True)
        return sw

    def _on_sidebar(self, _lb: Gtk.ListBox, row: Gtk.ListBoxRow | None) -> None:
        if row is None:
            return
        page_id = getattr(row, "page_id", "overview")
        self._stack.set_visible_child_name(page_id)

    def _on_page_changed(self, *_args) -> None:
        name = self._stack.get_visible_child_name() or "overview"
        titles = {p[0]: p[1] for p in PAGES}
        self._window_title.set_title(titles.get(name, "NC Backup"))
        if name == "overview":
            self._refresh_overview()
        if name == "restore" and not self._snaps_tried and not self._busy:
            self._snaps_tried = True
            self._on_refresh_snapshots()

    def show_overview(self) -> None:
        self._sidebar.select_row(self._page_rows["overview"])

    def _show_page(self, page_id: str) -> None:
        row = self._page_rows.get(page_id)
        if row is not None:
            self._sidebar.select_row(row)

    def _on_mode_changed(self, *_args) -> None:
        legacy = _selected_id(self._mode_combo, MODE_IDS, "incremental") == "legacy"
        self._restic_pw.set_visible(not legacy)
        self._ret_group.set_visible(not legacy)
        self._legacy_hint.set_visible(legacy)
        self._mark_dirty()

    def _on_provider_changed(self, *_args) -> None:
        pid = _selected_id(self._provider_combo, PROVIDER_IDS, "local")
        self._provider_stack.set_visible_child_name(pid if pid in PROVIDER_STACK_IDS else "local")
        self._mark_dirty()

    def _on_time_changed(self, *_args) -> None:
        text = self._sched_time.get_text().strip()
        if text and not TIME_RE.fullmatch(text):
            self._sched_time.add_css_class("error")
        else:
            self._sched_time.remove_css_class("error")
        self._mark_dirty()

    def _on_generate_pw(self, *_args) -> None:
        pw = generate_restic_password()
        self._restic_pw.set_text(pw)
        self._show_toast("Neues Passwort erzeugt — bitte notieren und speichern. Es wird nur hier angezeigt.")

    def _bind_from_config(self) -> None:
        c = self._cfg
        self._nc_install.set_text(c.nextcloud.install_dir)
        self._nc_data.set_text(c.nextcloud.data_dir)
        self._nc_user.set_text(c.nextcloud.occ_user)
        self._nc_container.set_text(getattr(c.nextcloud, "container", "") or "")
        self._nc_maint.set_active(c.nextcloud.maintenance_mode)

        self._db_host.set_text(c.database.host)
        self._db_port.set_value(c.database.port)
        self._db_name.set_text(c.database.name)
        self._db_user.set_text(c.database.user)
        self._db_pass.set_text(c.database.password)
        self._db_type.set_text(getattr(c.database, "type", "") or "mysql")
        self._db_container.set_text(getattr(c.database, "container", "") or "")

        _set_selected_id(self._mode_combo, MODE_IDS, c.destination.mode.value)
        _set_selected_id(self._provider_combo, PROVIDER_IDS, c.destination.provider.value)
        self._restic_pw.set_text(c.destination.restic_password)
        self._local_path.set_text(c.destination.local_path)
        self._sftp_host.set_text(c.destination.sftp_host)
        self._sftp_user.set_text(c.destination.sftp_user)
        self._sftp_path.set_text(c.destination.sftp_path)
        self._sftp_pass.set_text(c.destination.sftp_password)
        self._s3_endpoint.set_text(c.destination.s3_endpoint)
        self._s3_bucket.set_text(c.destination.s3_bucket)
        self._s3_prefix.set_text(c.destination.s3_prefix)
        self._s3_key.set_text(c.destination.s3_access_key)
        self._s3_secret.set_text(c.destination.s3_secret_key)
        self._s3_region.set_text(c.destination.s3_region)
        self._webdav_url.set_text(c.destination.webdav_url)
        self._webdav_user.set_text(c.destination.webdav_user)
        self._webdav_pass.set_text(c.destination.webdav_password)
        self._azure_account.set_text(c.destination.azure_account)
        self._azure_key.set_text(c.destination.azure_key)
        self._azure_container.set_text(c.destination.azure_container)
        self._b2_account_id.set_text(c.destination.b2_account_id)
        self._b2_account_key.set_text(c.destination.b2_account_key)
        self._b2_bucket.set_text(c.destination.b2_bucket)
        self._rclone_remote.set_text(c.destination.rclone_remote)
        self._rclone_path.set_text(c.destination.rclone_path)
        self._keep_daily.set_value(c.destination.retention.keep_daily)
        self._keep_weekly.set_value(c.destination.retention.keep_weekly)
        self._keep_monthly.set_value(c.destination.retention.keep_monthly)

        self._sched_enabled.set_active(c.schedule.enabled)
        self._sched_time.set_text(c.schedule.on_calendar)
        self._on_mode_changed()
        self._on_provider_changed()

    def _collect_config(self) -> AppConfig:
        c = self._cfg
        c.nextcloud.install_dir = self._nc_install.get_text().strip()
        c.nextcloud.data_dir = self._nc_data.get_text().strip()
        c.nextcloud.occ_user = self._nc_user.get_text().strip()
        c.nextcloud.container = self._nc_container.get_text().strip()
        c.nextcloud.maintenance_mode = self._nc_maint.get_active()

        c.database.host = self._db_host.get_text().strip()
        c.database.port = int(self._db_port.get_value())
        c.database.name = self._db_name.get_text().strip()
        c.database.user = self._db_user.get_text().strip()
        c.database.password = self._db_pass.get_text()
        c.database.type = self._db_type.get_text().strip() or "mysql"
        c.database.container = self._db_container.get_text().strip()

        c.destination.mode = BackupMode(_selected_id(self._mode_combo, MODE_IDS, "incremental"))
        c.destination.provider = Provider(_selected_id(self._provider_combo, PROVIDER_IDS, "local"))
        c.destination.restic_password = self._restic_pw.get_text()
        c.destination.local_path = self._local_path.get_text().strip()
        c.destination.sftp_host = self._sftp_host.get_text().strip()
        c.destination.sftp_user = self._sftp_user.get_text().strip()
        c.destination.sftp_path = self._sftp_path.get_text().strip()
        c.destination.sftp_password = self._sftp_pass.get_text()
        c.destination.s3_endpoint = self._s3_endpoint.get_text().strip()
        c.destination.s3_bucket = self._s3_bucket.get_text().strip()
        c.destination.s3_prefix = self._s3_prefix.get_text().strip()
        c.destination.s3_access_key = self._s3_key.get_text().strip()
        c.destination.s3_secret_key = self._s3_secret.get_text()
        c.destination.s3_region = self._s3_region.get_text().strip()
        c.destination.webdav_url = self._webdav_url.get_text().strip()
        c.destination.webdav_user = self._webdav_user.get_text().strip()
        c.destination.webdav_password = self._webdav_pass.get_text()
        c.destination.azure_account = self._azure_account.get_text().strip()
        c.destination.azure_key = self._azure_key.get_text()
        c.destination.azure_container = self._azure_container.get_text().strip()
        c.destination.b2_account_id = self._b2_account_id.get_text().strip()
        c.destination.b2_account_key = self._b2_account_key.get_text()
        c.destination.b2_bucket = self._b2_bucket.get_text().strip()
        c.destination.rclone_remote = self._rclone_remote.get_text().strip()
        c.destination.rclone_path = self._rclone_path.get_text().strip()
        c.destination.retention.keep_daily = int(self._keep_daily.get_value())
        c.destination.retention.keep_weekly = int(self._keep_weekly.get_value())
        c.destination.retention.keep_monthly = int(self._keep_monthly.get_value())

        c.schedule.enabled = self._sched_enabled.get_active()
        c.schedule.on_calendar = self._sched_time.get_text().strip() or "02:30"
        return c

    def _validation_errors(self) -> list[str]:
        errs: list[str] = []
        if not self._nc_install.get_text().strip():
            errs.append("Ordner der Nextcloud (Einrichtung)")
        if not self._nc_data.get_text().strip():
            errs.append("Datenordner (Einrichtung)")
        mode = _selected_id(self._mode_combo, MODE_IDS, "incremental")
        if mode == "incremental":
            msg = password_error_message(self._restic_pw.get_text())
            if msg:
                errs.append(msg)
        pid = _selected_id(self._provider_combo, PROVIDER_IDS, "local")
        if pid == "local" and not self._local_path.get_text().strip():
            errs.append("Ordner für die Sicherung (Ziel)")
        if pid == "sftp" and (
            not self._sftp_host.get_text().strip() or not self._sftp_user.get_text().strip()
        ):
            errs.append("Server und Benutzername für SFTP (Ziel)")
        if pid == "s3" and not self._s3_bucket.get_text().strip():
            errs.append("S3-Bucket (Ziel)")
        if pid == "webdav" and not self._webdav_url.get_text().strip():
            errs.append("Adresse der Cloud (Ziel)")
        if pid == "rclone" and not self._rclone_remote.get_text().strip():
            errs.append("Name der Cloud-Verbindung (Ziel)")
        if pid == "azure" and not self._azure_account.get_text().strip():
            errs.append("Azure-Konto (Ziel)")
        if pid == "b2" and (
            not self._b2_account_id.get_text().strip() or not self._b2_bucket.get_text().strip()
        ):
            errs.append("Backblaze-Konto und Bucket (Ziel)")
        t = self._sched_time.get_text().strip()
        if t and not TIME_RE.fullmatch(t):
            errs.append("Uhrzeit bitte als HH:MM angeben, z. B. 02:30")
        return errs

    def _connect_dirty_signals(self) -> None:
        for w in (
            self._nc_install, self._nc_data, self._nc_user, self._nc_container,
            self._db_host, self._db_name, self._db_user, self._db_pass,
            self._db_type, self._db_container,
            self._restic_pw, self._local_path,
            self._sftp_host, self._sftp_user, self._sftp_path, self._sftp_pass,
            self._s3_endpoint, self._s3_bucket, self._s3_prefix, self._s3_region,
            self._s3_key, self._s3_secret,
            self._webdav_url, self._webdav_user, self._webdav_pass,
            self._rclone_remote, self._rclone_path,
            self._azure_account, self._azure_key, self._azure_container,
            self._b2_account_id, self._b2_account_key, self._b2_bucket,
            self._sched_time,
        ):
            w.connect("changed", lambda *_: self._mark_dirty())
        for w in (self._nc_maint, self._sched_enabled):
            w.connect("notify::active", lambda *_: self._mark_dirty())
        for w in (self._db_port, self._keep_daily, self._keep_weekly, self._keep_monthly):
            w.connect("notify::value", lambda *_: self._mark_dirty())

    def _mark_dirty(self, *_args) -> None:
        if self._loading:
            return
        self._set_dirty(True)

    def _set_dirty(self, dirty: bool) -> None:
        self._dirty = dirty
        self._save_btn.set_sensitive(dirty and not self._busy)
        if dirty:
            self._save_btn.add_css_class("suggested-action")
        else:
            self._save_btn.remove_css_class("suggested-action")

    def _append_log(self, text: str) -> None:
        if not text:
            return
        end = self._log_buffer.get_end_iter()
        self._log_buffer.insert(end, text + "\n")

    def _write_temp_yaml(self, cfg: AppConfig) -> Path:
        fd, name = tempfile.mkstemp(suffix=".yaml")
        os.close(fd)
        tmp = Path(name)
        tmp.write_text(
            yaml.safe_dump(cfg.to_dict(), allow_unicode=True, default_flow_style=False),
            encoding="utf-8",
        )
        return tmp

    def _set_busy(self, busy: bool, message: str = "", overlay: bool = True) -> None:
        self._busy = busy
        self._save_btn.set_sensitive((self._dirty and not busy))
        self._ov_backup_btn.set_sensitive(not busy)
        self._timer_row.set_sensitive(not busy)
        self._restore_btn.set_sensitive(not busy)
        self._restore_refresh.set_sensitive(not busy)
        if busy:
            self._header_spinner.set_visible(True)
            self._header_spinner.start()
            if message:
                self._append_log(message)
                self._busy_page.set_description(message)
            if overlay:
                self._root_stack.set_visible_child_name("busy")
        else:
            self._header_spinner.stop()
            self._header_spinner.set_visible(False)
            self._root_stack.set_visible_child_name("main")

    def _run_admin(self, work, on_done, status: str, *, overlay: bool = True, goto_log: bool = False) -> None:
        if self._busy:
            self._show_toast("Es läuft bereits ein Vorgang.")
            return
        self._set_busy(True, status, overlay=overlay)

        def done(result) -> None:
            self._set_busy(False)
            if goto_log:
                self._show_page("log")
            if isinstance(result, Exception):
                self._append_log(str(result))
                self._show_toast("Vorgang fehlgeschlagen")
                return
            on_done(result)

        run_async(work, done)

    def _on_save(self, *_args) -> None:
        errs = self._validation_errors()
        if errs:
            self._alert("Bitte zuerst prüfen", "• " + "\n• ".join(errs))
            return
        cfg = self._collect_config()
        tmp = self._write_temp_yaml(cfg)

        def done(result) -> None:
            if isinstance(result, tuple):
                ok, msg = result
                self._append_log(msg)
                if ok:
                    self._set_dirty(False)
                    self._refresh_overview()
                self._show_toast("Gespeichert" if ok else "Speichern fehlgeschlagen")

        self._run_admin(
            lambda: save_config_as_admin(tmp, on_output=lambda ln: idle_log(self._append_log, ln)),
            done,
            "Einstellungen werden gespeichert …",
            overlay=False,
        )

    def _on_run(self, *_args) -> None:
        errs = self._validation_errors()
        if errs:
            self._alert("Sicherung noch nicht möglich", "• " + "\n• ".join(errs))
            return
        if self._dirty:
            self._show_toast("Bitte zuerst speichern.")
            return

        def done(result) -> None:
            if isinstance(result, tuple):
                ok, msg = result
                if msg:
                    self._append_log(msg)
                self._show_toast("Sicherung fertig" if ok else "Sicherung fehlgeschlagen")
                self._refresh_overview()

        self._run_admin(
            lambda: run_backup_as_admin(on_output=lambda ln: idle_log(self._append_log, ln)),
            done,
            "Sicherung läuft … Das kann einige Minuten dauern.",
            goto_log=True,
        )

    def _on_install_timer(self, *_args) -> None:
        errs = self._validation_errors()
        if errs:
            self._alert("Bitte zuerst prüfen", "• " + "\n• ".join(errs))
            return
        cfg = self._collect_config()
        tmp = self._write_temp_yaml(cfg)

        def done(result) -> None:
            if isinstance(result, tuple):
                ok, msg = result
                self._append_log(msg)
                if ok:
                    self._set_dirty(False)
                    self._refresh_overview()
                self._show_toast("Zeitplan aktiv" if ok else "Zeitplan konnte nicht gesetzt werden")

        self._run_admin(
            lambda: install_timer_as_admin(tmp, on_output=lambda ln: idle_log(self._append_log, ln)),
            done,
            "Zeitplan wird eingerichtet …",
            overlay=False,
        )

    def _on_rclone_wizard(self, *_args) -> None:
        def on_saved(name: str) -> None:
            self._rclone_remote.set_text(name)
            _set_selected_id(self._provider_combo, PROVIDER_IDS, "rclone")
            self._on_provider_changed()
            self._show_toast(f"Verbindung „{name}“ gespeichert")

        dlg = RcloneWizardDialog(self, on_saved)
        dlg.present()

    def _clear_snaps(self) -> None:
        child = self._snap_list.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self._snap_list.remove(child)
            child = nxt
        self._selected_snapshot_id = None

    def _on_refresh_snapshots(self, *_args) -> None:
        self._restore_stack.set_visible_child_name("loading")
        self._append_log("Lade Sicherungen …")

        def done(result) -> None:
            self._clear_snaps()
            if isinstance(result, Exception):
                self._restore_stack.set_visible_child_name("empty")
                self._append_log(str(result))
                self._show_toast("Sicherungen laden fehlgeschlagen")
                return
            ok, msg, snaps = result
            if not ok:
                self._append_log(msg)
                self._restore_stack.set_visible_child_name("empty")
                self._show_toast("Sicherungen laden fehlgeschlagen")
                return
            if not snaps:
                self._restore_stack.set_visible_child_name("empty")
                self._show_toast("Keine Sicherungen gefunden")
                return
            for s in snaps:
                tags = ", ".join(s.get("tags") or []) or "ohne Markierung"
                short = s.get("short_id") or (s.get("id") or "")[:8]
                row = Adw.ActionRow(
                    title=str(s.get("time") or "Unbekannte Zeit"),
                    subtitle=f"{short} · {tags}",
                )
                row.snapshot_id = s.get("id", "")  # type: ignore[attr-defined]
                self._snap_list.append(row)
            self._restore_stack.set_visible_child_name("list")
            self._append_log(f"{len(snaps)} Sicherung(en) geladen.")
            self._show_toast("Sicherungen geladen")

        self._run_admin(list_snapshots_as_admin, done, "Sicherungen werden geladen …", overlay=False)

    def _on_snapshot_selected(self, _lb: Gtk.ListBox, row: Gtk.ListBoxRow | None) -> None:
        if row and hasattr(row, "snapshot_id"):
            self._selected_snapshot_id = row.snapshot_id  # type: ignore[attr-defined]

    def _on_restore(self, *_args) -> None:
        if not self._selected_snapshot_id:
            self._show_toast("Bitte zuerst eine Sicherung in der Liste wählen.")
            return
        parts = []
        if self._restore_db.get_active():
            parts.append("Datenbank")
        if self._restore_cfg.get_active():
            parts.append("Konfiguration")
        if self._restore_data.get_active():
            parts.append("Nutzerdateien")
        if not parts:
            self._show_toast("Bitte mindestens einen Punkt einschalten.")
            return

        sid = self._selected_snapshot_id
        dialog = Adw.AlertDialog(
            heading="Wirklich wiederherstellen?",
            body=(
                f"Sicherung: {sid[:12]}…\n"
                f"Es wird ersetzt: {', '.join(parts)}\n\n"
                "Das lässt sich nicht rückgängig machen."
            ),
        )
        dialog.add_response("cancel", "Abbrechen")
        dialog.add_response("restore", "Wiederherstellen")
        dialog.set_response_appearance("restore", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response("cancel")
        dialog.set_close_response("cancel")

        def on_response(_d: Adw.AlertDialog, response: str) -> None:
            if response != "restore":
                return

            def done(result) -> None:
                if isinstance(result, tuple):
                    ok, msg = result
                    self._append_log(msg)
                    self._show_toast("Wiederherstellung fertig" if ok else "Wiederherstellung fehlgeschlagen")

            self._run_admin(
                lambda: restore_as_admin(
                    sid,
                    database=self._restore_db.get_active(),
                    config=self._restore_cfg.get_active(),
                    data=self._restore_data.get_active(),
                    on_output=lambda ln: idle_log(self._append_log, ln),
                ),
                done,
                "Wiederherstellung läuft …",
                goto_log=True,
            )

        dialog.connect("response", on_response)
        dialog.choose(self)

    def _alert(self, heading: str, body: str) -> None:
        dialog = Adw.AlertDialog(heading=heading, body=body)
        dialog.add_response("ok", "OK")
        dialog.set_default_response("ok")
        dialog.set_close_response("ok")
        dialog.present(self)

    def _on_close_request(self, *_args) -> bool:
        if self._busy:
            self._show_toast("Bitte warten, bis der Vorgang fertig ist.")
            return True
        if not self._dirty:
            return False
        dialog = Adw.AlertDialog(
            heading="Ungespeicherte Änderungen",
            body="Die Einstellungen wurden noch nicht gespeichert. Fenster trotzdem schließen?",
        )
        dialog.add_response("cancel", "Zurück")
        dialog.add_response("discard", "Verwerfen")
        dialog.add_response("save", "Speichern")
        dialog.set_response_appearance("save", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_response_appearance("discard", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response("save")
        dialog.set_close_response("cancel")

        def on_response(_d: Adw.AlertDialog, response: str) -> None:
            if response == "discard":
                self._dirty = False
                self.close()
            elif response == "save":
                self._on_save()

        dialog.connect("response", on_response)
        dialog.choose(self)
        return True
