# Backup wiederherstellen

Ab **v1.2** gibt es einen **Restore-Assistenten** in der GUI (Tab „Wiederherstellen“).

## Über die GUI (empfohlen)

1. Tab **Wiederherstellen** öffnen
2. Backup-**Ordner** oder verschlüsselte **`.gpg`-Datei** wählen
3. Bei Verschlüsselung: Passphrase eingeben
4. **Backup analysieren** – zeigt Inhalt aus `manifest.json`
5. Optionen wählen:
   - Dateien wiederherstellen
   - Datenbank wiederherstellen
   - Wartungsmodus (occ)
   - `--delete` (nur bei Voll-Restore!)
6. **Wiederherstellen**

Zielpfade kommen aus dem Backup-Manifest bzw. den aktuellen **Einstellungen** (Quellordner).

## Verschlüsseltes Backup

```
/mnt/backup/nextcloud-backup_2026-06-08_020000.tar.gz.gpg
```

Die GUI entschlüsselt temporär, spielt ein und räumt auf.

## Manuell (Terminal)

### Entschlüsseln

```bash
gpg -o backup.tar.gz -d nextcloud-backup_….tar.gz.gpg
tar -xzf backup.tar.gz -C /tmp/restore
```

### Dateien

```bash
BACKUP="/tmp/restore/nextcloud-backup_…"
sudo rsync -aHAX "$BACKUP/files/data/" /var/www/nextcloud/data/
sudo rsync -aHAX "$BACKUP/files/config/" /var/www/nextcloud/config/
```

### Datenbank

MariaDB/MySQL (nativ):

```bash
mysql -u root -p nextcloud < "$BACKUP/database/database_*.sql"
```

MariaDB/MySQL (Docker):

```bash
docker exec -i <db-container> mysql -u nextcloud -p nextcloud < "$BACKUP/database/database_*.sql"
```

PostgreSQL (nativ):

```bash
sudo -u postgres psql nextcloud < "$BACKUP/database/database_*.sql"
```

SQLite:

```bash
sudo cp "$BACKUP/database/"*.db /pfad/aus/config.php/
```

## Wichtige Hinweise

| Thema | Hinweis |
|-------|---------|
| Wartungsmodus | Wird per `occ` gesetzt (nativ/Docker) |
| `--delete` | Löscht Dateien am Ziel, die im Backup fehlen |
| config.php | Nach Restore Pfade und DB-Zugang prüfen |
| Abschluss | `occ files:scan --all` und `occ status` |
