# Sicherheit der Backup-Dateien

## Master-Passwort (GUI)

| Geschützt | Nicht geschützt |
|-----------|-----------------|
| Start der GUI | Exportierte Backup-Dateien |
| Ändern der Einstellungen | Direkter Dateizugriff auf Export-Pfad |

## GPG-Verschlüsselung (ab v1.2)

In den **Einstellungen** kann aktiviert werden:

- **Passphrase (AES256):** Backup wird als `.tar.gz.gpg` gespeichert
- **GPG-Empfänger:** Verschlüsselung mit öffentlichem Schlüssel (`gpg -r`)

### Ablauf

1. Backup wird normal erstellt (Ordner mit `files/`, `database/`, `manifest.json`)
2. Ordner wird zu `.tar.gz` gepackt und mit GPG verschlüsselt
3. Optional: unverschlüsselter Ordner wird gelöscht (Standard: ja)

### Passphrase-Speicherung

Für **geplante Backups** wird die Verschlüsselungs-Passphrase in  
`/etc/nc-backup/secrets.json` gespeichert (`chmod 600`).

> Getrennt vom GUI-Master-Passwort – beide merken!

### Empfehlungen

| Maßnahme | Nutzen |
|----------|--------|
| GPG-Verschlüsselung aktivieren | Schutz bei Diebstahl des Backup-Mediums |
| Starke Passphrase (20+ Zeichen) | Widerstand gegen Brute-Force |
| LUKS auf USB zusätzlich | Zweite Schicht |
| `secrets.json` nur root-lesbar | Schutz der Zeitplan-Passphrase |

## Was noch fehlt

- Keine Signatur/Checksum-Prüfung
- Kein Hardware-Token-Zwang
