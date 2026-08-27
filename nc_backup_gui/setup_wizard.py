"""Ersteinrichtung — verständlich, ohne Fachbegriffe wo möglich."""

from __future__ import annotations

import tempfile
from collections.abc import Callable
from pathlib import Path

import gi
import yaml

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")
from gi.repository import Adw, Gtk  # noqa: E402

from nc_backup.detect import (
    NextcloudDetection,
    apply_detection,
    detect_nextcloud,
    inspect_install,
)
from nc_backup.models import AppConfig, BackupMode, Provider
from nc_backup_gui.admin import install_timer_as_admin, save_config_as_admin
from nc_backup_gui.jobs import run_async
from nc_backup_gui.passwords import (
    generate_restic_password,
    is_strong_password,
    password_error_message,
)
from nc_backup_gui.rclone_dialog import RcloneWizardDialog

OCC_LABELS = ["www-data", "nginx", "httpd", "www", "apache"]


def _title(text: str) -> Gtk.Label:
    lab = Gtk.Label(label=text, wrap=True, xalign=0)
    lab.add_css_class("title-1")
    return lab


def _body(text: str) -> Gtk.Label:
    lab = Gtk.Label(label=text, wrap=True, xalign=0)
    lab.add_css_class("body")
    lab.add_css_class("dim-label")
    return lab


class SetupWizard(Adw.ApplicationWindow):
    def __init__(
        self,
        *,
        application: Adw.Application,
        config: AppConfig,
        on_done: Callable[[AppConfig, bool], None],
    ) -> None:
        super().__init__(application=application, title="NC Backup einrichten")
        self._cfg = config
        self._on_done = on_done
        self._completed = False
        self._busy = False
        self._det = detect_nextcloud(config.nextcloud.install_dir or None)
        self._restic_pw = generate_restic_password()
        self._dest_kind = "local"  # local | nas | cloud
        self._cloud_kind = "webdav"  # webdav | rclone
        self.set_default_size(640, 720)
        self.set_resizable(True)

        header = Adw.HeaderBar()
        self._window_title = Adw.WindowTitle(
            title="NC Backup",
            subtitle="Schritt 1 von 3 — Nextcloud finden",
        )
        header.set_title_widget(self._window_title)

        self._toast_overlay = Adw.ToastOverlay()
        toolbar = Adw.ToolbarView()
        toolbar.add_top_bar(header)

        self._carousel = Adw.Carousel()
        self._carousel.set_interactive(False)
        self._carousel.set_vexpand(True)
        self._carousel.append(self._build_page_nextcloud())
        self._carousel.append(self._build_page_destination())
        self._carousel.append(self._build_page_schedule())
        self._carousel.connect("notify::position", self._on_page)

        dots = Adw.CarouselIndicatorDots()
        dots.set_carousel(self._carousel)

        self._back_btn = Gtk.Button(label="Zurück")
        self._back_btn.connect("clicked", self._on_back)
        self._next_btn = Gtk.Button(label="Weiter")
        self._next_btn.add_css_class("suggested-action")
        self._next_btn.add_css_class("pill")
        self._next_btn.connect("clicked", self._on_next)

        nav = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        nav.set_margin_top(8)
        nav.set_margin_bottom(16)
        nav.set_margin_start(24)
        nav.set_margin_end(24)
        nav.append(self._back_btn)
        dots.set_hexpand(True)
        dots.set_halign(Gtk.Align.CENTER)
        nav.append(dots)
        nav.append(self._next_btn)

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        outer.append(self._carousel)
        outer.append(nav)
        toolbar.set_content(outer)
        self._toast_overlay.set_child(toolbar)
        self.set_content(self._toast_overlay)

        self.connect("close-request", self._on_close_request)
        self._apply_detection_to_ui(self._det)
        self._on_page()

    def _toast(self, msg: str) -> None:
        self._toast_overlay.add_toast(Adw.Toast.new(msg))

    def _wrap(self, *widgets: Gtk.Widget) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        box.set_margin_top(28)
        box.set_margin_bottom(12)
        box.set_margin_start(28)
        box.set_margin_end(28)
        for w in widgets:
            box.append(w)
        clamp = Adw.Clamp()
        clamp.set_maximum_size(560)
        clamp.set_child(box)
        sw = Gtk.ScrolledWindow()
        sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        sw.set_child(clamp)
        sw.set_vexpand(True)
        return sw

    def _choose_folder(self, on_path: Callable[[str], None]) -> None:
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
                on_path(path)

        dialog.select_folder(self, None, finished)

    # --- Page 1: Nextcloud ---
    def _build_page_nextcloud(self) -> Gtk.Widget:
        self._nc_status = Gtk.Label(wrap=True, xalign=0)
        self._nc_status.add_css_class("heading")
        self._nc_details = Gtk.Label(wrap=True, xalign=0)
        self._nc_details.add_css_class("body")
        self._nc_details.add_css_class("dim-label")

        pick = Gtk.Button(label="Anderen Ordner wählen")
        pick.add_css_class("pill")
        pick.connect("clicked", lambda *_: self._choose_folder(self._on_nc_folder))

        self._nc_path_row = Adw.EntryRow(title="Ordner der Nextcloud")
        self._nc_path_row.set_show_apply_button(False)

        self._occ_group = Adw.PreferencesGroup(
            title="Wer betreibt die Website?",
            description="Konnte nicht automatisch erkannt werden. "
            "Meist ist es „www-data“ — das Konto, unter dem der Webserver läuft.",
        )
        self._occ_combo = Adw.ComboRow(title="Systemkonto")
        self._occ_combo.set_model(Gtk.StringList.new(OCC_LABELS))
        self._occ_group.add(self._occ_combo)

        return self._wrap(
            _title("Willkommen"),
            _body(
                "Wir richten die Sicherung Ihrer Nextcloud in drei kurzen Schritten ein. "
                "Technische Details bleiben im Hintergrund."
            ),
            self._nc_status,
            self._nc_details,
            self._nc_path_row,
            pick,
            self._occ_group,
        )

    def _apply_detection_to_ui(self, det: NextcloudDetection) -> None:
        self._det = det
        self._nc_path_row.set_text(det.install_dir)
        if det.found:
            extra = ""
            if len(det.candidates) > 1:
                extra = f" (weitere Fundorte: {len(det.candidates) - 1})"
            from nc_backup.detect import detection_summary

            self._nc_status.set_text(detection_summary(det) if getattr(det, "nc_container", "") else f"Nextcloud gefunden unter {det.install_dir}{extra}")
            bits = []
            if det.data_dir:
                bits.append(f"Datenordner: {det.data_dir}")
            if getattr(det, "nc_container", ""):
                bits.append(f"Container: {det.nc_container}")
            if getattr(det, "db_container", ""):
                bits.append(f"Datenbank-Container: {det.db_container}")
            if det.config_parsed:
                bits.append(f"Datenbank: {det.db_name} auf {det.db_host}")
            else:
                bits.append("Die Einstellungsdatei konnte nicht gelesen werden — Sie können das später nachtragen.")
            self._nc_details.set_text("\n".join(bits))
        else:
            self._nc_status.set_text("Nextcloud wurde nicht automatisch gefunden.")
            self._nc_details.set_text(
                "Bitte den Ordner wählen, in dem Nextcloud installiert ist "
                "(dort liegt typischerweise die Datei „occ“)."
            )
        self._occ_group.set_visible(not det.occ_user_confident)
        if det.occ_user in OCC_LABELS:
            self._occ_combo.set_selected(OCC_LABELS.index(det.occ_user))
        else:
            self._occ_combo.set_selected(0)

    def _on_nc_folder(self, path: str) -> None:
        det = inspect_install(Path(path))
        found = detect_nextcloud()
        det.candidates = found.candidates
        self._apply_detection_to_ui(det)

    # --- Page 2: Destination + password ---
    def _build_page_destination(self) -> Gtk.Widget:
        self._dest_list = Gtk.ListBox()
        self._dest_list.add_css_class("boxed-list")
        self._dest_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        for kind, title, subtitle in [
            ("local", "Auf diesem Rechner", "Lokal auf der Festplatte — gut zum Einstieg"),
            ("nas", "Auf einem Netzwerklaufwerk", "NAS oder Freigabe, die bereits eingebunden ist"),
            ("cloud", "In die Cloud", "Eine andere Nextcloud, oder Dienste wie Dropbox"),
        ]:
            row = Adw.ActionRow(title=title, subtitle=subtitle)
            row.dest_kind = kind  # type: ignore[attr-defined]
            self._dest_list.append(row)
        self._dest_list.connect("row-selected", self._on_dest_selected)

        self._local_path = Adw.EntryRow(title="Speicherort auf diesem Rechner")
        self._local_path.set_text("/var/backups/nextcloud/restic-repo")
        folder_btn = Gtk.Button(icon_name="folder-open-symbolic")
        folder_btn.add_css_class("flat")
        folder_btn.set_valign(Gtk.Align.CENTER)
        folder_btn.set_tooltip_text("Ordner wählen")
        folder_btn.connect("clicked", lambda *_: self._choose_folder(self._local_path.set_text))
        self._local_path.add_suffix(folder_btn)

        self._cloud_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self._webdav_url = Adw.EntryRow(title="Adresse der Cloud")
        self._webdav_user = Adw.EntryRow(title="Benutzername")
        self._webdav_pass = Adw.PasswordEntryRow(title="Passwort der Cloud")
        rclone_row = Adw.ActionRow(
            title="Dropbox, Google Drive, OneDrive, …",
            subtitle="Separater Assistent — nur nötig, wenn Sie nicht WebDAV nutzen",
        )
        rclone_row.set_activatable(True)
        rclone_row.add_suffix(Gtk.Image.new_from_icon_name("go-next-symbolic"))
        rclone_row.connect("activated", self._on_rclone)
        cloud_group = Adw.PreferencesGroup()
        cloud_group.add(self._webdav_url)
        cloud_group.add(self._webdav_user)
        cloud_group.add(self._webdav_pass)
        cloud_group.add(rclone_row)
        self._cloud_box.append(cloud_group)

        pw_group = Adw.PreferencesGroup(
            title="Ihr Wiederherstellungs-Passwort",
            description=(
                "Ohne dieses Passwort können Sicherungen niemand — auch Sie nicht — "
                "zurückspielen. Es wird nur dies eine Mal angezeigt. "
                "Bitte kopieren und an einem sicheren Ort aufbewahren."
            ),
        )
        self._pw_row = Adw.EntryRow(title="Passwort")
        self._pw_row.set_text(self._restic_pw)
        copy_btn = Gtk.Button(icon_name="edit-copy-symbolic")
        copy_btn.add_css_class("flat")
        copy_btn.set_valign(Gtk.Align.CENTER)
        copy_btn.set_tooltip_text("Kopieren")
        copy_btn.connect("clicked", self._on_copy_pw)
        regen_btn = Gtk.Button(icon_name="view-refresh-symbolic")
        regen_btn.add_css_class("flat")
        regen_btn.set_valign(Gtk.Align.CENTER)
        regen_btn.set_tooltip_text("Neues Passwort erzeugen")
        regen_btn.connect("clicked", self._on_regen_pw)
        self._pw_row.add_suffix(copy_btn)
        self._pw_row.add_suffix(regen_btn)
        self._pw_row.connect("changed", self._on_pw_changed)

        self._pw_confirm = Adw.SwitchRow(
            title="Ich habe das Passwort sicher gespeichert",
            subtitle="Ohne Bestätigung geht es nicht weiter. Es gibt kein Überspringen.",
        )
        self._pw_confirm.connect("notify::active", lambda *_: self._on_page())
        self._pw_hint = Gtk.Label(wrap=True, xalign=0)
        self._pw_hint.add_css_class("caption")
        pw_group.add(self._pw_row)
        pw_group.add(self._pw_confirm)

        self._dest_list.select_row(self._dest_list.get_row_at_index(0))

        return self._wrap(
            _title("Wo sollen die Sicherungen hin?"),
            _body("Wählen Sie den Ort, an dem die Kopien Ihrer Nextcloud liegen sollen."),
            self._dest_list,
            self._local_path,
            self._cloud_box,
            pw_group,
            self._pw_hint,
        )

    def _on_dest_selected(self, _lb: Gtk.ListBox, row: Gtk.ListBoxRow | None) -> None:
        kind = getattr(row, "dest_kind", "local") if row else "local"
        self._dest_kind = kind
        self._cloud_box.set_visible(kind == "cloud")
        if kind == "local":
            self._local_path.set_title("Speicherort auf diesem Rechner")
            self._local_path.set_visible(True)
        elif kind == "nas":
            self._local_path.set_title("Ordner des Netzwerklaufwerks")
            self._local_path.set_visible(True)
        else:
            self._local_path.set_title("Zwischenordner auf diesem Rechner")
            self._local_path.set_visible(True)

    def _on_rclone(self, *_args) -> None:
        def on_saved(name: str) -> None:
            self._cloud_kind = "rclone"
            self._cfg.destination.rclone_remote = name
            self._cfg.destination.provider = Provider.RCLONE
            self._toast(f"Cloud-Verbindung „{name}“ eingerichtet")

        dlg = RcloneWizardDialog(self, on_saved)
        dlg.present()

    def _on_copy_pw(self, *_args) -> None:
        pw = self._pw_row.get_text()
        try:
            self.get_clipboard().set(pw)
        except Exception:
            self._toast("Kopieren nicht möglich — bitte markieren und selbst kopieren.")
            return
        self._toast("Passwort in die Zwischenablage kopiert")

    def _on_regen_pw(self, *_args) -> None:
        self._restic_pw = generate_restic_password()
        self._pw_row.set_text(self._restic_pw)
        self._pw_confirm.set_active(False)
        self._toast("Neues Passwort erzeugt — bitte erneut kopieren und bestätigen.")

    def _on_pw_changed(self, *_args) -> None:
        self._restic_pw = self._pw_row.get_text()
        err = password_error_message(self._restic_pw)
        self._pw_hint.set_text(err or "Das Passwort erfüllt die Sicherheitsvorgaben.")
        if err:
            self._pw_hint.add_css_class("error")
        else:
            self._pw_hint.remove_css_class("error")
        self._on_page()

    # --- Page 3: Schedule ---
    def _build_page_schedule(self) -> Gtk.Widget:
        self._sched_enabled = Adw.SwitchRow(
            title="Täglich automatisch sichern",
            subtitle="Nachts, wenn niemand arbeitet — empfohlen",
        )
        self._sched_enabled.set_active(True)
        self._hour = Adw.SpinRow.new_with_range(0, 23, 1)
        self._hour.set_title("Stunde")
        self._hour.set_value(2)
        self._minute = Adw.SpinRow.new_with_range(0, 59, 1)
        self._minute.set_title("Minute")
        self._minute.set_value(30)
        group = Adw.PreferencesGroup(title="Zeitplan")
        group.add(self._sched_enabled)
        group.add(self._hour)
        group.add(self._minute)

        self._summary = Gtk.Label(wrap=True, xalign=0)
        self._summary.add_css_class("body")

        return self._wrap(
            _title("Wann darf gesichert werden?"),
            _body(
                "Ein tägliches automatisches Backup hält Ihre Daten auf dem neuesten Stand. "
                "Sie können das später jederzeit ändern."
            ),
            group,
            self._summary,
        )

    def _refresh_summary(self) -> None:
        dest = {
            "local": "auf diesem Rechner",
            "nas": "auf dem Netzwerklaufwerk",
            "cloud": "in der Cloud",
        }.get(self._dest_kind, "")
        nc = self._nc_path_row.get_text().strip() or "(nicht gewählt)"
        time_s = f"{int(self._hour.get_value()):02d}:{int(self._minute.get_value()):02d}"
        sched = (
            f"täglich um {time_s} Uhr"
            if self._sched_enabled.get_active()
            else "kein automatischer Zeitplan"
        )
        self._summary.set_text(
            f"Zusammenfassung:\n"
            f"• Nextcloud: {nc}\n"
            f"• Sicherungen: {dest}\n"
            f"• Zeitplan: {sched}\n\n"
            "Zum Abschluss werden die Einstellungen mit Administratorrechten gespeichert."
        )

    def _on_page(self, *_args) -> None:
        idx = int(round(self._carousel.get_position()))
        titles = (
            "Schritt 1 von 3 — Nextcloud finden",
            "Schritt 2 von 3 — Speicherort & Passwort",
            "Schritt 3 von 3 — Zeitplan",
        )
        self._window_title.set_subtitle(titles[idx] if idx < len(titles) else "")
        self._back_btn.set_sensitive(idx > 0 and not self._busy)
        if idx >= 2:
            self._next_btn.set_label("Einrichtung abschließen")
            self._refresh_summary()
        else:
            self._next_btn.set_label("Weiter")
        self._next_btn.set_sensitive(not self._busy)

    def _on_back(self, *_args) -> None:
        if self._busy:
            return
        idx = int(round(self._carousel.get_position()))
        if idx > 0:
            self._carousel.scroll_to(self._carousel.get_nth_page(idx - 1), True)

    def _on_next(self, *_args) -> None:
        if self._busy:
            return
        idx = int(round(self._carousel.get_position()))
        if idx == 0:
            err = self._validate_nc()
            if err:
                self._alert("Noch nicht fertig", err)
                return
            self._carousel.scroll_to(self._carousel.get_nth_page(1), True)
            return
        if idx == 1:
            err = self._validate_dest()
            if err:
                self._alert("Noch nicht fertig", err)
                return
            self._carousel.scroll_to(self._carousel.get_nth_page(2), True)
            return
        err = self._validate_dest() or self._validate_nc()
        if err:
            self._alert("Noch nicht fertig", err)
            return
        self._finish()

    def _validate_nc(self) -> str | None:
        path = self._nc_path_row.get_text().strip()
        if not path:
            return "Bitte den Ordner Ihrer Nextcloud angeben oder wählen."
        return None

    def _validate_dest(self) -> str | None:
        pw = self._pw_row.get_text()
        err = password_error_message(pw)
        if err:
            return err
        if not is_strong_password(pw):
            return "Das Wiederherstellungs-Passwort ist Pflicht und zu schwach."
        if not self._pw_confirm.get_active():
            return (
                "Bitte bestätigen Sie, dass Sie das Wiederherstellungs-Passwort "
                "an einem sicheren Ort gespeichert haben. Ohne dieses Passwort "
                "können Sicherungen nicht zurückgespielt werden."
            )
        if self._dest_kind == "nas" and not self._local_path.get_text().strip():
            return "Bitte den Ordner des Netzwerklaufwerks wählen."
        if self._dest_kind == "cloud" and self._cloud_kind != "rclone":
            if not self._webdav_url.get_text().strip():
                return "Bitte die Adresse Ihrer Cloud angeben, oder Dropbox/Google Drive über den Assistenten einrichten."
        return None

    def _alert(self, heading: str, body: str) -> None:
        dialog = Adw.AlertDialog(heading=heading, body=body)
        dialog.add_response("ok", "OK")
        dialog.set_default_response("ok")
        dialog.set_close_response("ok")
        dialog.present(self)

    def _apply_to_config(self) -> AppConfig:
        cfg = self._cfg
        path = self._nc_path_row.get_text().strip()
        if path and self._det and path == (self._det.install_dir or "") and self._det.found:
            det = self._det
        else:
            det = inspect_install(Path(path)) if path else self._det
            if self._det and getattr(self._det, "nc_container", ""):
                det.nc_container = self._det.nc_container
                det.db_container = self._det.db_container
                det.db_type = getattr(self._det, "db_type", det.db_type)
                det.occ_inner = getattr(self._det, "occ_inner", "")
                det.source = getattr(self._det, "source", det.source)
                det.db_same_container = getattr(self._det, "db_same_container", False)
                det.db_on_host = getattr(self._det, "db_on_host", False)
        apply_detection(cfg, det)
        if path:
            cfg.nextcloud.install_dir = path
        if det.data_dir:
            cfg.nextcloud.data_dir = det.data_dir
        if not det.occ_user_confident:
            idx = int(self._occ_combo.get_selected())
            if 0 <= idx < len(OCC_LABELS):
                cfg.nextcloud.occ_user = OCC_LABELS[idx]
        elif det.occ_user:
            cfg.nextcloud.occ_user = det.occ_user

        cfg.destination.mode = BackupMode.INCREMENTAL
        cfg.destination.restic_password = self._pw_row.get_text()
        local = self._local_path.get_text().strip() or "/var/backups/nextcloud/restic-repo"
        cfg.destination.local_path = local

        if self._dest_kind in ("local", "nas"):
            cfg.destination.provider = Provider.LOCAL
        elif self._cloud_kind == "rclone" and cfg.destination.rclone_remote:
            cfg.destination.provider = Provider.RCLONE
        else:
            cfg.destination.provider = Provider.WEBDAV
            cfg.destination.webdav_url = self._webdav_url.get_text().strip()
            cfg.destination.webdav_user = self._webdav_user.get_text().strip()
            cfg.destination.webdav_password = self._webdav_pass.get_text()

        cfg.schedule.enabled = self._sched_enabled.get_active()
        cfg.schedule.on_calendar = (
            f"{int(self._hour.get_value()):02d}:{int(self._minute.get_value()):02d}"
        )
        return cfg

    def _finish(self) -> None:
        if not is_strong_password(self._pw_row.get_text()) or not self._pw_confirm.get_active():
            self._alert(
                "Passwort fehlt",
                "Die Einrichtung kann ohne gültiges Wiederherstellungs-Passwort "
                "nicht abgeschlossen werden.",
            )
            return
        cfg = self._apply_to_config()
        fd, name = tempfile.mkstemp(suffix=".yaml")
        import os

        os.close(fd)
        tmp = Path(name)
        tmp.write_text(
            yaml.safe_dump(cfg.to_dict(), allow_unicode=True, default_flow_style=False),
            encoding="utf-8",
        )
        self._busy = True
        self._on_page()
        self._next_btn.set_label("Wird gespeichert …")

        def work():
            if cfg.schedule.enabled:
                return install_timer_as_admin(tmp)
            return save_config_as_admin(tmp)

        def done(result) -> None:
            self._busy = False
            self._on_page()
            if isinstance(result, Exception):
                self._alert("Speichern fehlgeschlagen", str(result))
                return
            ok, msg = result
            if not ok:
                self._alert(
                    "Speichern fehlgeschlagen",
                    msg or "Die Administrator-Freigabe wurde abgebrochen.",
                )
                return
            self._completed = True
            self._on_done(cfg, True)
            self.close()

        run_async(work, done)

    def _on_close_request(self, *_args) -> bool:
        if self._completed:
            return False
        if self._busy:
            self._toast("Bitte warten, bis das Speichern fertig ist.")
            return True
        dialog = Adw.AlertDialog(
            heading="Einrichtung abbrechen?",
            body=(
                "Ohne abgeschlossene Einrichtung können keine Sicherungen angelegt werden. "
                "Es gibt kein Überspringen — entweder fertig einrichten oder das Programm beenden."
            ),
        )
        dialog.add_response("stay", "Weiter einrichten")
        dialog.add_response("quit", "Programm beenden")
        dialog.set_response_appearance("quit", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response("stay")
        dialog.set_close_response("stay")

        def on_response(_d: Adw.AlertDialog, response: str) -> None:
            if response == "quit":
                app = self.get_application()
                self._completed = True
                self.close()
                if app is not None:
                    app.quit()

        dialog.connect("response", on_response)
        dialog.choose(self)
        return True
