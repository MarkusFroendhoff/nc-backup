# NC Backup

**Nextcloud-Backup für Ubuntu 24.04 LTS** — mit **grafischer Oberfläche**, **Web-Oberfläche**, **inkrementellen Snapshots** (Restic) und Anbindung an **lokale Festplatten**, **SFTP**, **S3**, **Azure**, **Backblaze B2**, **WebDAV** sowie **Rclone** (Dropbox, Google Drive, OneDrive, …).

## Funktionen

| Funktion | Beschreibung |
|----------|--------------|
| **GUI** | Alle Einstellungen eingeben: Nextcloud-Pfade, MariaDB, Ziel, Zeitplan |
| **Web-Oberfläche** | Dieselbe Struktur im Browser unter http://192.168.178.4:42173 |
| **Inkrementell** | Restic sichert nur geänderte Blöcke — schneller, weniger Speicher |
| **MariaDB** | Konsistenter Dump mit `mysqldump --single-transaction` |
| **Wartungsmodus** | Optional während des Laufs (`occ maintenance:mode`) |
| **Cloud/Netzwerk** | SFTP und S3 direkt über Restic; WebDAV/Rclone per Sync |
| **Zeitplan** | systemd-Timer (z. B. täglich 02:30 Uhr) aus der Oberfläche aktivieren |
| **Wiederherstellung** | Snapshots anzeigen und DB/Config/Daten selektiv zurückspielen |
| **.deb-Paket** | Offizielle Installation für Ubuntu 24.04 |

## Architektur

```mermaid
flowchart LR
  GUI[nc-backup-gui] -->|pkexec| CFG[/etc/nc-backup/config.yaml]
  WEB[nc-backup-web] --> CFG
  GUI -->|Backup starten| CLI[nc-backup run]
  WEB --> CLI
  CLI --> OCC[occ Wartungsmodus]
  CLI --> DB[mysqldump]
  CLI --> RESTIC[restic backup]
  RESTIC --> LOCAL[Lokal / SFTP / S3 / Azure / B2]
  RESTIC --> RCLONE[rclone sync]
  RCLONE --> WEBDAV[WebDAV / Dropbox / …]
```

Bei **WebDAV** und **Rclone-Remotes** liegt das verschlüsselte Restic-Repository zuerst lokal; danach synchronisiert `rclone` zum Cloud-Ziel.

## Erste Schritte

1. Legen Sie den Ordner `nc-backup` auf den Ubuntu-Rechner, auf dem Nextcloud läuft.
2. Öffnen Sie in diesem Ordner ein Terminal (Rechtsklick → „Im Terminal öffnen“) und geben Sie ein:

   `sudo ./scripts/install-ubuntu.sh`

3. Fertig. Öffnen Sie **NC Backup** im Anwendungsmenü — oder im Browser **http://192.168.178.4:42173**.
   Den Zugangsschlüssel zeigt die Installation einmal an; er liegt unter `/etc/nc-backup/web-token`.

Beim ersten Start hilft ein kurzer Assistent: Nextcloud wird erkannt, Sie wählen, wohin die Sicherungen sollen, und legen eine Uhrzeit fest.

### Variante: .deb-Paket

Wenn eine `.deb`-Datei vorliegt:

```bash
sudo apt install ./nc-backup_1.8.0-1_all.deb
```

Paket bauen (nur wenn Sie das selbst tun möchten):

```bash
sudo apt install dpkg-dev debhelper dh-python python3-all python3-setuptools
./scripts/build-deb.sh
```

## Unterstützte Ziele

| Anbieter | Technik | Hinweis |
|----------|---------|---------|
| Lokal / NAS | Restic → Ordner | Einfachster Einstieg |
| SFTP/SSH | Restic → `sftp:…` | SSH-Key empfohlen (`ssh-copy-id`) |
| S3-kompatibel | Restic → `s3:…` | AWS, MinIO, Wasabi, Hetzner Object Storage |
| Azure Blob | Restic | Account + Key in der Oberfläche |
| Backblaze B2 | Restic | Account ID + Application Key |
| WebDAV | Restic lokal + `rclone sync` | z. B. zweite Nextcloud, Synology |
| Rclone-Remote | Restic lokal + `rclone sync` | Vorher `rclone config` für Dropbox/GDrive o. ä. |

## Inkrementell — was bedeutet das?

- **Dateidaten**: Restic speichert nur geänderte Chunks — ideal für große `data/`-Verzeichnisse.
- **Datenbank**: Jeder Lauf erzeugt einen neuen SQL-Dump; Restic dedupliziert trotzdem auf Block-Ebene.
- **Aufbewahrung**: z. B. 7 tägliche, 4 wöchentliche, 6 monatliche Snapshots (`restic forget --prune`).

Legacy-Modus **Vollbackup (tar.gz)** bleibt für einfache, dateibasierte Archive verfügbar.

## Konfigurationsdateien

| Datei | Inhalt |
|-------|--------|
| `/etc/nc-backup/config.yaml` | Alle Einstellungen (ohne Restic-Passwort) |
| `/etc/nc-backup/restic-password` | Repository-Passwort (chmod 600) |
| `/etc/nc-backup/web-token` | Zugangsschlüssel der Web-Oberfläche (chmod 600) |
| `/etc/nc-backup/rclone.conf` | WebDAV-Zugang (von der App geschrieben) |

Beispiel: `config/config.example.yaml`

## Abhängigkeiten

- `restic` — inkrementelle Snapshots
- `mariadb-client` — Datenbank-Dump
- `rclone` — WebDAV/Cloud-Sync
- GTK4 / Libadwaita — Desktop-Oberfläche

Die Web-Oberfläche nutzt nur die Python-Standardbibliothek.

## Sicherheit

- Konfiguration und Passwörter nur für root lesbar.
- Restic-Repository ist **verschlüsselt** — Passwort sicher aufbewahren (Verlust = Daten nicht mehr lesbar).
- Zugangsschlüssel und Sicherungskennwort müssen Groß- und Kleinbuchstaben, Zahlen und ein Sonderzeichen enthalten.
- Die Web-Oberfläche lauscht standardmäßig nur auf `0.0.0.0:42173` (nicht im lokalen Netz). Es gibt kein HTTPS.
- Für Produktion: Offsite-Ziel (SFTP/S3) und getrennte Zugangsdaten.

## Ältere Bash-Skripte

Die Skripte unter `scripts/` (Vollbackup ohne Restic) bleiben nutzbar; die empfohlene Variante ist **GUI / Web + `nc-backup run`**.

## Kommandozeile

```bash
sudo nc-backup validate
sudo nc-backup run
sudo nc-backup snapshots
journalctl -u nc-backup.service -e
```

## Lizenz

AGPL-3.0-or-later — dieselbe Lizenzfamilie wie Nextcloud.
