# NC Backup (Nextcloud-App)

Zwei getrennte Stellen:

| Wo | Was |
|----|-----|
| **Einstellungen → Verwaltung → NC Backup** | nur **URL** und **API-Token** eintragen |
| **App-Symbol „NC Backup“** (oben, wie Kalender) | Ziel wählen und Backup starten |

Wiederherstellung bleibt in der nc-backup-Web-GUI.

## Auf dem Pi aktualisieren (bestehende 1.7.0-Installation)

App ersetzen:

```bash
SRC=~/nc-backup/nextcloud-app/ncbackup
sudo rm -rf /var/www/nextcloud/apps/ncbackup
sudo cp -a "$SRC" /var/www/nextcloud/apps/ncbackup
sudo chown -R www-data:www-data /var/www/nextcloud/apps/ncbackup
sudo -u www-data php /var/www/nextcloud/occ app:enable --force ncbackup
```

nc-backup-API (Ziele + Token) nachziehen, **ohne** das Python-Paket komplett neu zu installieren:

```bash
cd ~/nc-backup
SITE=$(python3 -c "import nc_backup, pathlib; print(pathlib.Path(nc_backup.__file__).parent)")
sudo cp src/nc_backup/web/api_v1.py "$SITE/web/api_v1.py"
sudo python3 - <<'PY'
from pathlib import Path
import nc_backup.web.app as m
p = Path(m.__file__)
text = p.read_text(encoding="utf-8")
needle = "from nc_backup.web.api_v1 import register_api_v1"
if needle not in text:
    text += "\nfrom nc_backup.web.api_v1 import register_api_v1\nregister_api_v1(app)\n"
    p.write_text(text, encoding="utf-8")
print("patched", p)
PY
sudo systemctl restart nc-backup-web
```

Token erzeugen: Web-GUI `http://192.168.178.4:42173` → Einstellungen → **Neues API-Token erzeugen**.

In Nextcloud: **Einstellungen → NC Backup** → Token einfügen → speichern.

Dann oben auf **NC Backup** klicken, Ziel wählen, starten.

Falls Nextcloud lokale URLs blockiert:

```bash
sudo -u www-data php /var/www/nextcloud/occ config:system:set allow_local_remote_servers --value=true --type=boolean
```
