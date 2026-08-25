"""Hilfsdialoge."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # noqa: E402


def info_dialog(parent: Gtk.Window, title: str, message: str) -> None:
    dialog = Gtk.MessageDialog(
        transient_for=parent,
        flags=0,
        message_type=Gtk.MessageType.INFO,
        buttons=Gtk.ButtonsType.OK,
        text=title,
    )
    dialog.format_secondary_text(message)
    dialog.run()
    dialog.destroy()


def error_dialog(parent: Gtk.Window, title: str, message: str) -> None:
    dialog = Gtk.MessageDialog(
        transient_for=parent,
        flags=0,
        message_type=Gtk.MessageType.ERROR,
        buttons=Gtk.ButtonsType.OK,
        text=title,
    )
    dialog.format_secondary_text(message)
    dialog.run()
    dialog.destroy()


def confirm_dialog(parent: Gtk.Window, title: str, message: str) -> bool:
    dialog = Gtk.MessageDialog(
        transient_for=parent,
        flags=0,
        message_type=Gtk.MessageType.QUESTION,
        buttons=Gtk.ButtonsType.YES_NO,
        text=title,
    )
    dialog.format_secondary_text(message)
    response = dialog.run()
    dialog.destroy()
    return response == Gtk.ResponseType.YES


def password_dialog(parent: Gtk.Window, title: str, message: str, confirm: bool = False) -> str | None:
    dialog = Gtk.Dialog(title=title, transient_for=parent, flags=0)
    dialog.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OK, Gtk.ResponseType.OK)
    dialog.set_default_size(420, 0)

    box = dialog.get_content_area()
    box.set_spacing(8)
    box.set_margin_start(12)
    box.set_margin_end(12)
    box.set_margin_top(12)
    box.set_margin_bottom(12)

    label = Gtk.Label(label=message, xalign=0)
    box.pack_start(label, False, False, 0)

    entry = Gtk.Entry()
    entry.set_visibility(False)
    entry.set_input_purpose(Gtk.InputPurpose.PASSWORD)
    entry.set_activates_default(True)
    box.pack_start(entry, False, False, 0)

    confirm_entry = None
    if confirm:
        confirm_label = Gtk.Label(label="Passwort bestätigen:", xalign=0)
        box.pack_start(confirm_label, False, False, 0)
        confirm_entry = Gtk.Entry()
        confirm_entry.set_visibility(False)
        confirm_entry.set_input_purpose(Gtk.InputPurpose.PASSWORD)
        confirm_entry.set_activates_default(True)
        box.pack_start(confirm_entry, False, False, 0)

    dialog.show_all()
    response = dialog.run()
    password = entry.get_text()
    dialog.destroy()

    if response != Gtk.ResponseType.OK:
        return None
    if confirm and confirm_entry and password != confirm_entry.get_text():
        return ""
    return password


def choose_docker_detection(parent: Gtk.Window, detections: list) -> object | None:
    dialog = Gtk.Dialog(
        title="Docker-Installation wählen",
        transient_for=parent,
        flags=0,
    )
    dialog.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OK, Gtk.ResponseType.OK)
    dialog.set_default_size(560, 320)

    box = dialog.get_content_area()
    box.set_spacing(8)
    box.set_margin_start(12)
    box.set_margin_end(12)
    box.set_margin_top(12)
    box.set_margin_bottom(12)

    box.pack_start(
        Gtk.Label(
            label="Mehrere Nextcloud-Container gefunden. Bitte eine Installation wählen:",
            xalign=0,
            wrap=True,
        ),
        False,
        False,
        0,
    )

    list_box = Gtk.ListBox()
    list_box.set_selection_mode(Gtk.SelectionMode.SINGLE)
    for detection in detections:
        row = Gtk.ListBoxRow()
        label = Gtk.Label(label=detection.summary, xalign=0, selectable=True)
        row.add(label)
        row.detection = detection
        list_box.add(row)
    list_box.select_row(list_box.get_row_at_index(0))
    box.pack_start(list_box, True, True, 0)
    dialog.show_all()

    response = dialog.run()
    row = list_box.get_selected_row()
    detection = getattr(row, "detection", None) if row else None
    dialog.destroy()
    if response == Gtk.ResponseType.OK:
        return detection
    return None


def folder_chooser(parent: Gtk.Window, title: str) -> str | None:
    dialog = Gtk.FileChooserDialog(
        title=title,
        transient_for=parent,
        action=Gtk.FileChooserAction.SELECT_FOLDER,
    )
    dialog.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OPEN, Gtk.ResponseType.OK)
    response = dialog.run()
    path = dialog.get_filename()
    dialog.destroy()
    if response == Gtk.ResponseType.OK and path:
        return path
    return None
