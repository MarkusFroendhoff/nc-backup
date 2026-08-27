"""Assistent: Rclone-Remote anlegen."""

from __future__ import annotations

import json
import tempfile
from collections.abc import Callable
from pathlib import Path

import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")
from gi.repository import Adw, Gtk  # noqa: E402

from nc_backup.rclone_wizard import RcloneProvider
from nc_backup_gui.admin import (
    list_rclone_remotes_as_admin,
    oauth_rclone_as_admin,
    save_rclone_remote_as_admin,
    test_rclone_as_admin,
)
from nc_backup_gui.jobs import run_async

PROVIDERS = [
    (RcloneProvider.WEBDAV.value, "WebDAV (andere Nextcloud, Synology, …)"),
    (RcloneProvider.S3.value, "S3-kompatibel"),
    (RcloneProvider.SFTP.value, "SFTP / SSH"),
    (RcloneProvider.GOOGLE_DRIVE.value, "Google Drive"),
    (RcloneProvider.DROPBOX.value, "Dropbox"),
    (RcloneProvider.ONEDRIVE.value, "OneDrive"),
]


class RcloneWizardDialog(Adw.Window):
    def __init__(self, parent: Gtk.Window, on_saved: Callable[[str], None]) -> None:
        super().__init__(transient_for=parent, modal=True, title="Cloud-Dienst einrichten")
        self._on_saved = on_saved
        self._busy = False
        self.set_default_size(520, 620)
        self.set_hide_on_close(True)

        header = Adw.HeaderBar()
        header.set_show_end_title_buttons(True)
        header.set_title_widget(Adw.WindowTitle(title="Cloud-Dienst", subtitle="Rclone-Verbindung"))

        self._toast_overlay = Adw.ToastOverlay()
        toolbar = Adw.ToolbarView()
        toolbar.add_top_bar(header)

        self._name = Adw.EntryRow(title="Name der Verbindung")
        self._provider = Adw.ComboRow(title="Anbieter")
        self._provider.set_model(Gtk.StringList.new([label for _, label in PROVIDERS]))
        self._provider.set_selected(0)
        self._provider.connect("notify::selected", self._on_provider_changed)

        self._stack = Gtk.Stack()
        self._fields: dict[str, Adw.EntryRow] = {}
        pages = [
            ("webdav", [
                ("webdav_url", "Adresse (URL)", False),
                ("webdav_user", "Benutzername", False),
                ("webdav_pass", "Passwort", True),
            ]),
            ("s3", [
                ("s3_endpoint", "Server-Adresse", False),
                ("s3_access_key", "Zugangsschlüssel", False),
                ("s3_secret_key", "Geheimschlüssel", True),
                ("s3_region", "Region", False),
            ]),
            ("sftp", [
                ("sftp_host", "Rechner / Server", False),
                ("sftp_user", "Benutzername", False),
                ("sftp_pass", "Passwort", True),
            ]),
            ("oauth", [
                ("client_id", "Client-ID (optional)", False),
                ("client_secret", "Client-Secret (optional)", True),
            ]),
        ]
        for key, fields in pages:
            g = Adw.PreferencesGroup()
            for fid, label, secret in fields:
                row: Adw.EntryRow = (
                    Adw.PasswordEntryRow(title=label) if secret else Adw.EntryRow(title=label)
                )
                self._fields[fid] = row
                g.add(row)
            self._stack.add_named(g, key)

        hint = Gtk.Label(
            label="Bei Google Drive, Dropbox und OneDrive nach dem Speichern "
            "„Mit Konto verbinden“ ausführen — es öffnet sich der Browser.",
            wrap=True,
            xalign=0,
        )
        hint.add_css_class("dim-label")

        self._remote_list = Gtk.Label(label="Vorhandene Verbindungen: —", xalign=0, wrap=True)

        save_btn = Gtk.Button(label="Verbindung speichern")
        save_btn.add_css_class("suggested-action")
        save_btn.connect("clicked", self._on_save)
        test_btn = Gtk.Button(label="Verbindung testen")
        test_btn.connect("clicked", self._on_test)
        oauth_btn = Gtk.Button(label="Mit Konto verbinden")
        oauth_btn.connect("clicked", self._on_oauth)
        refresh_btn = Gtk.Button(label="Liste aktualisieren")
        refresh_btn.connect("clicked", lambda *_: self._refresh_remotes())

        self._action_btns = [save_btn, test_btn, oauth_btn, refresh_btn]
        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        actions.set_homogeneous(True)
        for b in self._action_btns:
            b.add_css_class("pill")
            actions.append(b)

        base = Adw.PreferencesGroup()
        base.add(self._name)
        base.add(self._provider)

        box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=12,
            margin_top=12,
            margin_bottom=12,
            margin_start=12,
            margin_end=12,
        )
        box.append(base)
        box.append(self._stack)
        box.append(hint)
        box.append(self._remote_list)
        box.append(actions)

        clamp = Adw.Clamp(maximum_size=520)
        clamp.set_child(box)
        sw = Gtk.ScrolledWindow()
        sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        sw.set_child(clamp)
        toolbar.set_content(sw)
        self._toast_overlay.set_child(toolbar)
        self.set_content(self._toast_overlay)

        self._on_provider_changed()
        self._refresh_remotes()

    def _toast(self, msg: str) -> None:
        self._toast_overlay.add_toast(Adw.Toast.new(msg))

    def _provider_id(self) -> str:
        idx = int(self._provider.get_selected())
        if 0 <= idx < len(PROVIDERS):
            return PROVIDERS[idx][0]
        return RcloneProvider.WEBDAV.value

    def _on_provider_changed(self, *_args) -> None:
        pid = self._provider_id()
        if pid in (
            RcloneProvider.GOOGLE_DRIVE.value,
            RcloneProvider.DROPBOX.value,
            RcloneProvider.ONEDRIVE.value,
        ):
            self._stack.set_visible_child_name("oauth")
        elif pid == RcloneProvider.S3.value:
            self._stack.set_visible_child_name("s3")
        elif pid == RcloneProvider.SFTP.value:
            self._stack.set_visible_child_name("sftp")
        else:
            self._stack.set_visible_child_name("webdav")

    def _build_spec(self) -> dict:
        spec: dict = {"name": self._name.get_text().strip(), "provider": self._provider_id()}
        for key, entry in self._fields.items():
            spec[key] = entry.get_text()
        if spec["provider"] == "sftp" and not spec.get("sftp_port"):
            spec["sftp_port"] = 22
        return spec

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        for b in self._action_btns:
            b.set_sensitive(not busy)

    def _alert(self, heading: str, body: str) -> None:
        dialog = Adw.AlertDialog(heading=heading, body=body or "—")
        dialog.add_response("ok", "OK")
        dialog.set_default_response("ok")
        dialog.set_close_response("ok")
        dialog.present(self)

    def _need_name(self) -> str | None:
        name = self._name.get_text().strip()
        if not name:
            self._toast("Bitte zuerst einen Namen für die Verbindung vergeben.")
            self._alert("Name fehlt", "Ohne Namen kann die Verbindung nicht gespeichert oder getestet werden.")
            return None
        return name

    def _refresh_remotes(self) -> None:
        if self._busy:
            return
        self._set_busy(True)

        def done(result) -> None:
            self._set_busy(False)
            if isinstance(result, Exception):
                self._remote_list.set_text("Vorhandene Verbindungen: (nicht lesbar)")
                return
            ok, _, remotes = result
            if ok and remotes:
                self._remote_list.set_text("Vorhandene Verbindungen: " + ", ".join(remotes))
            elif ok:
                self._remote_list.set_text("Vorhandene Verbindungen: (keine)")
            else:
                self._remote_list.set_text("Vorhandene Verbindungen: (nicht lesbar)")

        run_async(list_rclone_remotes_as_admin, done)

    def _on_save(self, *_args) -> None:
        spec = self._build_spec()
        if not spec["name"]:
            self._need_name()
            return
        if self._busy:
            return
        fd, path = tempfile.mkstemp(suffix=".json")
        import os

        os.close(fd)
        p = Path(path)
        p.write_text(json.dumps(spec), encoding="utf-8")
        self._set_busy(True)

        def done(result) -> None:
            self._set_busy(False)
            if isinstance(result, Exception):
                self._alert("Fehler", str(result))
                return
            ok, msg = result
            if ok:
                self._on_saved(spec["name"])
                self._refresh_remotes()
            self._alert("Gespeichert" if ok else "Fehler", msg)

        run_async(lambda: save_rclone_remote_as_admin(p), done)

    def _on_test(self, *_args) -> None:
        name = self._need_name()
        if not name or self._busy:
            return
        self._set_busy(True)

        def done(result) -> None:
            self._set_busy(False)
            if isinstance(result, Exception):
                self._alert("Verbindung fehlgeschlagen", str(result))
                return
            ok, msg = result
            self._alert("Verbindung OK" if ok else "Verbindung fehlgeschlagen", msg)

        run_async(lambda: test_rclone_as_admin(name), done)

    def _on_oauth(self, *_args) -> None:
        name = self._need_name()
        if not name or self._busy:
            return
        self._set_busy(True)

        def done(result) -> None:
            self._set_busy(False)
            if isinstance(result, Exception):
                self._alert("Verbinden fehlgeschlagen", str(result))
                return
            ok, msg = result
            self._alert("Konto verbunden" if ok else "Verbinden fehlgeschlagen", msg)

        run_async(lambda: oauth_rclone_as_admin(name), done)
