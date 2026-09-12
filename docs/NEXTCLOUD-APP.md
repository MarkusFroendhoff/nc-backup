# NC Backup (Nextcloud-App) für nc-backup 1.8

Die App ist **nicht** im Nextcloud-App-Store. Sie steuert den lokalen **nc-backup**-Webdienst (kein Restore).

| Wo | Was |
|----|-----|
| **Einstellungen → Verwaltung → NC Backup** | **URL** + **Zugangsschlüssel** (`/etc/nc-backup/web-token`) |
| **App-Symbol „NC Backup“** | lokales Ziel, Zeitplan, Backup starten |

Wiederherstellung bleibt in der nc-backup-Web-GUI (`http://SERVER:42173`).

## Funktionen (App 1.3)

- lokales Sicherungsziel aus Mount-Liste wählen oder Pfad eingeben
- täglichen Zeitplan aktivieren (Uhrzeit HH:MM)
- Backup jetzt starten + Statusanzeige
- Cloud-Ziele (SFTP/S3/…) weiterhin nur in der Web-GUI

## Voraussetzungen

- nc-backup **1.8.x** mit laufendem `nc-backup-web` (Port 42173)
- Nextcloud 28–40

## Installation (nativ)

```bash
NC=/var/www/nextcloud
SRC=/usr/share/nc-backup/nextcloud-app/ncbackup
# oder: SRC=~/nc-backup/nextcloud-app/ncbackup

sudo rm -rf "$NC/apps/ncbackup"
sudo cp -a "$SRC" "$NC/apps/ncbackup"
sudo chown -R www-data:www-data "$NC/apps/ncbackup"
sudo -u www-data php "$NC/occ" app:enable --force ncbackup
sudo -u www-data php "$NC/occ" config:system:set allow_local_remote_servers --value=true --type=boolean
```

## Zugangsschlüssel

```bash
sudo cat /etc/nc-backup/web-token
```

Nextcloud → **Einstellungen → Verwaltung → NC Backup** → URL `http://127.0.0.1:42173` + Schlüssel.

## API

- `GET /api/status`, `GET /api/targets`, `GET /api/config`
- `POST /api/config` (lokales Ziel), `POST /api/schedule`, `POST /api/backup`
- Auth: `Authorization: Bearer <web-token>`
- `POST /api/backup` erwartet ein JSON-Objekt. Leerer Body und `{}` sind ok.
  Ab nc-backup **2.0.3** gilt auch das leere Array `[]` (PHP `json_encode([])`)
  als leeres Objekt. Nicht-leere Arrays bleiben 400.

## Kompatibilität 1.8.2

Es gibt keinen aktiven 1.8-Zweig. Wer auf **1.8.2** bleibt (z. B. Raspberry Pi
unter Ubuntu 24.04), kann entweder die Nextcloud-App **1.3.3+** einspielen
(sendet `{}`) oder denselben `_read_json`-Patch wie in 2.0.3 anwenden.
Die 24.04-/1.8.x-Kompatibilität der übrigen API bleibt unverändert.
