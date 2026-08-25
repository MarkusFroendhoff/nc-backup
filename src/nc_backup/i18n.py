"""UI-Übersetzungen (DE/EN) für die Web-GUI."""

from __future__ import annotations

from typing import Any

TRANSLATIONS: dict[str, dict[str, str]] = {
    "de": {
        "title": "Nextcloud Backup Web",
        "heading": "Nextcloud Backup (Web-GUI)",
        "lang_label": "Sprache",
        "lang_de": "Deutsch",
        "lang_en": "English",
        "setup_title": "Ersteinrichtung",
        "new_password": "Neues Master-Passwort",
        "confirm_password": "Passwort bestätigen",
        "save_password": "Passwort speichern",
        "login_title": "Anmeldung",
        "master_password": "Master-Passwort",
        "login": "Anmelden",
        "logout": "Abmelden",
        "quick_actions": "Schnellaktionen",
        "backup_now": "Backup jetzt starten",
        "check_space": "Speicherplatz prüfen",
        "detect_docker": "Docker automatisch erkennen",
        "detect_paths": "Pfade aus config.php lesen",
        "refresh_targets": "Laufwerke neu einlesen",
        "progress": "Fortschritt",
        "ready": "Bereit",
        "settings": "Einstellungen",
        "install_mode": "Installationsmodus",
        "backup_target": "Backup-Ziel (Laufwerk / Netzwerk)",
        "choose_target": "— bitte wählen oder Pfad unten eingeben —",
        "target_hint": "USB-Sticks, Netzlaufwerke und Ordner unter /mnt und /media werden erkannt.",
        "export_path": "Export-Pfad (kann auch manuell gesetzt werden)",
        "config_php": "config.php-Pfad",
        "docker_nc": "Docker Nextcloud-Container",
        "docker_db": "Docker DB-Container",
        "source_folders": "Quellordner (eine Zeile pro Ordner)",
        "include_db": "Datenbank-Dump einschließen",
        "backup_mode": "Backup-Modus",
        "mode_auto": "Automatisch (empfohlen)",
        "mode_stream": "Stream verschlüsselt (Netzwerk, kein Server-Cache)",
        "mode_incr": "Inkrementell (nur geänderte Dateien)",
        "mode_classic": "Klassisch (Ordner + optional tar/gpg)",
        "mode_hint": "<b>Automatisch:</b> mit Verschlüsselung → Stream direkt aufs Ziel; ohne → inkrementell.<br><b>Stream verschlüsselt:</b> tar→gzip→gpg direkt auf Netzwerk/USB, kein Staging auf dem Server.<br><b>Inkrementell:</b> rsync mit Hardlinks unter <code>nextcloud-backup-snapshots/</code> (unverschlüsselt).<br><b>Klassisch:</b> bisheriges Verhalten (volle Kopie auf Ziel, dann Archiv).",
        "encrypt": "Backups verschlüsseln",
        "gpg_mode": "Verschlüsselungsart",
        "gpg_pass": "Passwort (einfach, empfohlen)",
        "gpg_key": "GPG-Schlüssel (nur wenn du schon einen hast)",
        "gpg_hint": "<b>Passwort:</b> Du legst ein Passwort fest und brauchst es zum Entschlüsseln.<br><b>GPG-Schlüssel:</b> Nur sinnvoll, wenn du bereits einen GPG-Schlüssel hast.",
        "gpg_recipient": "GPG-Schlüssel (E-Mail oder Key-ID)",
        "gpg_recipient_hint": "Nur bei „GPG-Schlüssel“ ausfüllen. Leer lassen bei Passwort-Verschlüsselung. Anzeigen mit: <code>gpg --list-keys</code>",
        "remove_plain": "Unverschlüsselten Ordner nach Verschlüsselung löschen",
        "gpg_passphrase": "Verschlüsselungs-Passwort (nur bei „Passwort“)",
        "gpg_passphrase_ph": "leer lassen = unverändert",
        "save_settings": "Einstellungen speichern",
        "schedule": "Zeitplan",
        "schedule_enable": "Geplantes Backup aktivieren",
        "hour": "Stunde (0-23)",
        "minute": "Minute (0-59)",
        "weekdays": "Wochentage (0=Mo ... 6=So, Komma getrennt)",
        "save_schedule": "Zeitplan speichern + anwenden",
        "restore": "Wiederherstellen",
        "backup_path": "Backup-Pfad (Ordner oder .gpg)",
        "restore_files": "Dateien wiederherstellen",
        "restore_db": "Datenbank wiederherstellen",
        "maintenance": "Wartungsmodus setzen",
        "delete_extra": "Zusätzliche Zieldateien löschen (--delete)",
        "restore_gpg": "GPG-Passphrase (nur für verschlüsselte Backups)",
        "restore_start": "Restore starten",
        "js_space_ok": "Speicherplatz ok",
        "js_space_bad": "Ziel zu klein",
        "js_start": "Start",
        "js_starting": "Backup wird gestartet…",
        "js_error": "Fehler",
        "js_start_fail": "Start fehlgeschlagen",
        "err_password_mismatch": "Passwörter stimmen nicht überein.",
        "err_wrong_password": "Falsches Passwort.",
        "err_login": "Bitte anmelden.",
        "err_gpg_pass": "Bitte Verschlüsselungs-Passwort setzen (Modus „Passwort“).",
        "err_gpg_recipient": "Bitte GPG-Schlüssel (E-Mail oder Key-ID) angeben.",
        "ok_settings": "Einstellungen gespeichert.",
        "err_paths": "Pfad-Erkennung fehlgeschlagen: {exc}",
        "ok_paths": "Pfade aus config.php übernommen:\n{summary}",
        "err_docker": "Docker-Erkennung fehlgeschlagen: {exc}",
        "err_no_docker": "Keine Docker-Installation erkannt.",
        "ok_docker": "Docker erkannt: {summary}",
        "err_no_targets": "Keine Laufwerke gefunden. USB einstecken und ggf. mounten, dann erneut einlesen.",
        "ok_targets": "{n} mögliche Backup-Ziele gefunden.",
        "err_backup_running": "Es läuft bereits ein Backup.",
        "ok_backup_started": "Backup gestartet.",
        "err_schedule": "Ungültige Zeitplan-Eingabe.",
        "err_schedule_apply": "Zeitplan konnte nicht angewendet werden: {exc}",
        "err_backup_path": "Bitte Backup-Pfad angeben.",
        "err_restore": "{message} Fehler: {errors}",
        "ok_lang": "Sprache gespeichert.",
    },
    "en": {
        "title": "Nextcloud Backup Web",
        "heading": "Nextcloud Backup (Web UI)",
        "lang_label": "Language",
        "lang_de": "Deutsch",
        "lang_en": "English",
        "setup_title": "Initial setup",
        "new_password": "New master password",
        "confirm_password": "Confirm password",
        "save_password": "Save password",
        "login_title": "Sign in",
        "master_password": "Master password",
        "login": "Sign in",
        "logout": "Sign out",
        "quick_actions": "Quick actions",
        "backup_now": "Start backup now",
        "check_space": "Check free space",
        "detect_docker": "Detect Docker automatically",
        "detect_paths": "Read paths from config.php",
        "refresh_targets": "Rescan drives",
        "progress": "Progress",
        "ready": "Ready",
        "settings": "Settings",
        "install_mode": "Install mode",
        "backup_target": "Backup target (drive / network)",
        "choose_target": "— choose or enter path below —",
        "target_hint": "USB sticks, network shares and folders under /mnt and /media are detected.",
        "export_path": "Export path (can also be set manually)",
        "config_php": "config.php path",
        "docker_nc": "Docker Nextcloud container",
        "docker_db": "Docker DB container",
        "source_folders": "Source folders (one path per line)",
        "include_db": "Include database dump",
        "backup_mode": "Backup mode",
        "mode_auto": "Automatic (recommended)",
        "mode_stream": "Stream encrypted (network, no server cache)",
        "mode_incr": "Incremental (changed files only)",
        "mode_classic": "Classic (folder + optional tar/gpg)",
        "mode_hint": "<b>Automatic:</b> with encryption → stream directly to target; without → incremental.<br><b>Stream encrypted:</b> tar→gzip→gpg straight to network/USB, no staging on the server.<br><b>Incremental:</b> rsync hardlinks under <code>nextcloud-backup-snapshots/</code> (unencrypted).<br><b>Classic:</b> previous behaviour (full copy on target, then archive).",
        "encrypt": "Encrypt backups",
        "gpg_mode": "Encryption type",
        "gpg_pass": "Password (simple, recommended)",
        "gpg_key": "GPG key (only if you already have one)",
        "gpg_hint": "<b>Password:</b> You set a password and need it to decrypt.<br><b>GPG key:</b> Only useful if you already have a GPG key.",
        "gpg_recipient": "GPG key (email or key ID)",
        "gpg_recipient_hint": "Only for “GPG key”. Leave empty for password encryption. List keys: <code>gpg --list-keys</code>",
        "remove_plain": "Delete unencrypted folder after encryption",
        "gpg_passphrase": "Encryption password (password mode only)",
        "gpg_passphrase_ph": "leave empty = unchanged",
        "save_settings": "Save settings",
        "schedule": "Schedule",
        "schedule_enable": "Enable scheduled backup",
        "hour": "Hour (0-23)",
        "minute": "Minute (0-59)",
        "weekdays": "Weekdays (0=Mon ... 6=Sun, comma-separated)",
        "save_schedule": "Save schedule + apply",
        "restore": "Restore",
        "backup_path": "Backup path (folder or .gpg)",
        "restore_files": "Restore files",
        "restore_db": "Restore database",
        "maintenance": "Enable maintenance mode",
        "delete_extra": "Delete extra files on target (--delete)",
        "restore_gpg": "GPG passphrase (encrypted backups only)",
        "restore_start": "Start restore",
        "js_space_ok": "Space OK",
        "js_space_bad": "Target too small",
        "js_start": "Start",
        "js_starting": "Starting backup…",
        "js_error": "Error",
        "js_start_fail": "Failed to start",
        "err_password_mismatch": "Passwords do not match.",
        "err_wrong_password": "Wrong password.",
        "err_login": "Please sign in.",
        "err_gpg_pass": "Please set an encryption password (password mode).",
        "err_gpg_recipient": "Please enter a GPG key (email or key ID).",
        "ok_settings": "Settings saved.",
        "err_paths": "Path detection failed: {exc}",
        "ok_paths": "Paths from config.php applied:\n{summary}",
        "err_docker": "Docker detection failed: {exc}",
        "err_no_docker": "No Docker installation detected.",
        "ok_docker": "Docker detected: {summary}",
        "err_no_targets": "No drives found. Plug in USB and mount if needed, then rescan.",
        "ok_targets": "{n} possible backup targets found.",
        "err_backup_running": "A backup is already running.",
        "ok_backup_started": "Backup started.",
        "err_schedule": "Invalid schedule input.",
        "err_schedule_apply": "Could not apply schedule: {exc}",
        "err_backup_path": "Please enter a backup path.",
        "err_restore": "{message} Errors: {errors}",
        "ok_lang": "Language saved.",
    },
}


def normalize_lang(lang: str | None) -> str:
    value = (lang or "de").strip().lower()
    if value.startswith("en"):
        return "en"
    return "de"


def detect_browser_lang(accept_language: str | None) -> str:
    if not accept_language:
        return "de"
    primary = accept_language.split(",")[0].strip().lower()
    return normalize_lang(primary)


def get_translations(lang: str) -> dict[str, str]:
    code = normalize_lang(lang)
    base = TRANSLATIONS["de"]
    if code == "de":
        return dict(base)
    merged = dict(base)
    merged.update(TRANSLATIONS.get(code, {}))
    return merged


class Translator:
    def __init__(self, lang: str) -> None:
        self.lang = normalize_lang(lang)
        self._data = get_translations(self.lang)

    def __call__(self, key: str, **kwargs: Any) -> str:
        text = self._data.get(key, TRANSLATIONS["de"].get(key, key))
        if kwargs:
            try:
                return text.format(**kwargs)
            except (KeyError, ValueError):
                return text
        return text
