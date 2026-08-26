# NC Backup (Nextcloud-App)

Die App ist **nicht** im Nextcloud-App-Store. Nextcloud lädt sie nur, wenn der Ordner im echten `apps/`-Verzeichnis liegt, `www-data` gehört und per `occ` aktiviert wird.

| Wo | Was |
|----|-----|
| **Einstellungen → Verwaltung → NC Backup** | nur **URL** und **API-Token** eintragen |
| **App-Symbol „NC Backup“** (oben, wie Kalender) | Ziel wählen und Backup starten |

Wiederherstellung bleibt in der nc-backup-Web-GUI.

## 1. App holen

```bash
cd /tmp
git clone --depth 1 https://github.com/MarkusFroendhoff/nc-backup.git
ls /tmp/nc-backup/nextcloud-app/ncbackup/appinfo/info.xml
```

Nach `install.sh` oft auch unter `/usr/share/nc-backup/nextcloud-app/ncbackup`. Der Ordner **muss** `ncbackup` heißen.

## 2. Nextcloud-Pfad

```bash
sudo find /var/www /opt /srv -name occ 2>/dev/null | head
```

Nativ häufig: `/var/www/nextcloud/occ` → Ziel `/var/www/nextcloud/apps/ncbackup`.

## 3. Kopieren und aktivieren (nativ)

```bash
NC=/var/www/nextcloud
SRC=/tmp/nc-backup/nextcloud-app/ncbackup

sudo rm -rf "$NC/apps/ncbackup"
sudo cp -a "$SRC" "$NC/apps/ncbackup"
sudo chown -R www-data:www-data "$NC/apps/ncbackup"

sudo -u www-data php "$NC/occ" app:enable ncbackup
# bei „nicht kompatibel“:
sudo -u www-data php "$NC/occ" app:enable --force ncbackup
sudo -u www-data php "$NC/occ" app:list | grep ncbackup
```

**Docker:** in das gemountete `apps`-Volume kopieren, dann `docker exec -u www-data KONTAINER php occ app:enable --force ncbackup`. URL nicht `127.0.0.1` (das ist der Container) – LAN-IP oder `http://172.17.0.1:42173`.

## 4. Token

1. Web-GUI `http://SERVER-IP:42173` → Einstellungen → **Neues API-Token erzeugen** (nur einmal sichtbar).
2. Nextcloud → **Einstellungen → Verwaltung → NC Backup**
3. Nativ gleicher Rechner: `http://127.0.0.1:42173` + Token → speichern.
4. Oben **NC Backup** → Ziel → starten.

Lokale URLs von Nextcloud blockiert:

```bash
sudo -u www-data php /var/www/nextcloud/occ config:system:set allow_local_remote_servers --value=true --type=boolean
```

## Typische Fehler

| Symptom | Lösung |
|---------|--------|
| Nicht im Store | Normal – manuell kopieren + `occ` |
| nicht kompatibel | `occ app:enable --force ncbackup` |
| CSRF / Zugriff verboten | aktuelle App von GitHub |
| nicht erreichbar | Dienst, URL (Docker!), `allow_local_remote_servers` |
| Token ungültig | neu erzeugen und in den Einstellungen speichern |
