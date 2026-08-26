# Nextcloud Backup Programm

GUI-Backup für **Nextcloud** auf **Ubuntu/Debian** – **ARM64** (Raspberry Pi) und **Intel/AMD (x86_64)**.

## Funktionen

- Web-GUI (headless, Deutsch/Englisch) + optionale GTK-GUI
- Stream-Verschlüsselung direkt auf Netzwerk/USB (ohne Server-Zwischenspeicher)
- Inkrementelle Snapshots (rsync mit Hardlinks)
- Master-Passwort, GPG-Verschlüsselung, Restore-Assistent
- Native, Docker- und benutzerdefinierte Installation
- Datenbank-Dump: MariaDB/MySQL, PostgreSQL, SQLite
- Geplante Backups per systemd-Timer
- **Autostart der Web-GUI nach Reboot** (systemd)
- Optional: **Nextcloud-App** – eigene Oberfläche zum Backup starten, API-Token nur in den Einstellungen

## Schnellstart

```bash
chmod +x install/install.sh
sudo ./install/install.sh
```

Web-GUI: `http://SERVER-IP:42173`  
Status: `systemctl status nc-backup-web`

## Weitergeben / Installationspaket

| Methode | Für wen |
|---------|---------|
| **`install/make-release.sh`** | Quellcode-Archiv `.tar.gz` |
| **`install/build-deb.sh`** | Debian-Paket `.deb` (ARM + Intel) |
| **`install/install.sh`** | Direktinstallation aus Quellcode |

Ausführliche Anleitung: [docs/INSTALL.md](docs/INSTALL.md)

```bash
./install/make-release.sh          # nc-backup-1.5.0.tar.gz
./install/build-deb.sh amd64       # .deb bauen (Mac mit Docker)
```

## Projektstruktur

```
src/nc_backup/          Python-Paket
nextcloud-app/ncbackup  Nextcloud-App (eigene Oberfläche + Token in Einstellungen)
install/                install.sh, systemd, .deb-Build
debian/                 Debian-Paketierung (Architecture: all)
docs/                   Dokumentation
```

## Lizenz

Open Source unter **GPL-3.0-or-later**.  
Website: https://plugins.froendhoff.com/nc-backup/  
Quellcode: https://github.com/MarkusFroendhoff/nc-backup

