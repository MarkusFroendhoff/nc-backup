# Installation – Nextcloud Backup

Unterstützte Systeme: **Ubuntu 24.04 / Debian 12** auf **ARM64** (Raspberry Pi) und **Intel/AMD (x86_64)**.  
Nextcloud nativ oder per Docker.

---

## Variante A: Installationsskript (empfohlen für Quellcode)

```bash
tar -xzf nc-backup-1.7.0.tar.gz
cd nc-backup-1.7.0
chmod +x install/install.sh
sudo ./install/install.sh
```

Das Skript:

- installiert Abhängigkeiten
- richtet die **Web-GUI als systemd-Dienst** ein (Autostart nach Reboot)
- startet die GUI auf Port **42173**

Danach im Browser:

```text
http://SERVER-IP:42173
```

Status prüfen:

```bash
systemctl status nc-backup-web
journalctl -u nc-backup-web -f
```

---

## Variante B: Debian-Paket (.deb) – zum Weitergeben

Das Paket ist **`Architecture: all`** – **ein** `.deb` funktioniert auf Pi **und** Intel-PC.

### Paket bauen

**Auf Ubuntu/Debian (Pi oder PC):**

```bash
sudo apt install devscripts debhelper dh-python
cd nc-backup-1.7.0
debuild -us -uc -b
```

**Auf dem Mac (mit Docker):**

```bash
chmod +x install/build-deb.sh install/make-release.sh
./install/build-deb.sh amd64
```

**Release-Archiv erstellen (Quellcode zum Weitergeben):**

```bash
./install/make-release.sh
# → ../nc-backup-1.7.0.tar.gz
```

### Paket installieren

```bash
sudo dpkg -i nc-backup_1.7.0-1_all.deb
sudo apt -f install
```

Nach der Installation:

- Web-GUI läuft als Dienst **`nc-backup-web`**
- startet automatisch beim Boot
- Konfiguration: `/etc/nc-backup/`

```bash
systemctl status nc-backup-web
```

---

## Aktualisieren (bestehende Installation)

Einstellungen in `/etc/nc-backup/` bleiben erhalten.

**Debian-Paket:**

```bash
sudo dpkg -i nc-backup_1.7.0-1_all.deb
sudo apt -f install
sudo systemctl restart nc-backup-web
```

**Quellcode / `install.sh`:**

```bash
cd ~/nc-backup
sudo ./install/install.sh
```

Prüfen:

```bash
pip3 show nc-backup | grep Version
# Erwartung: Version: 1.7.0
systemctl status nc-backup-web
```

---

## Web-GUI manuell als systemd-Dienst (falls nötig)

```bash
sudo /usr/lib/nc-backup/enable-web-service.sh
```

Konfiguration: `/etc/nc-backup/web.env` (Host, Port, Session-Secret).

---

## Ersteinrichtung in der Web-GUI

1. Master-Passwort festlegen
2. **Einstellungen**:
   - Installationsart (Nativ / Docker / Benutzerdefiniert)
   - `config.php`-Pfad
   - Quellordner (Daten, Config)
   - **Backup-Ziel** (USB, Netzwerk-Mount, SMB)
   - **Backup-Modus**:
     - *Automatisch* – mit Verschlüsselung → Stream direkt aufs Ziel
     - *Stream verschlüsselt* – kein Zwischenspeicher auf dem Server
     - *Inkrementell* – nur geänderte Dateien (Hardlinks)
3. Optional: Datenbank-Dump, GPG-Verschlüsselung
4. **Speicherplatz prüfen** vor dem ersten Backup

---

## Netzwerk-Backup (SMB/NFS)

Das Ziel muss **gemountet** sein, z. B.:

```bash
sudo mount -t cifs //192.168.x.x/Freigabe /mnt/backup \
  -o credentials=/etc/nc-backup/smb-omv.credentials,uid=0,gid=0,vers=3.0
```

Prüfen:

```bash
findmnt /mnt/backup    # muss Netzwerk-Share zeigen, nicht /dev/nvme...
```

In der Web-GUI: Export-Pfad `/mnt/backup`, **Laufwerke neu einlesen**.

---

## Firewall (UFW)

```bash
sudo ufw allow 42173/tcp comment "nc-backup-web"
```

Nur Heimnetz:

```bash
sudo ufw allow from 192.168.0.0/16 to any port 42173 proto tcp
```

---

## Geplante Backups (systemd-Timer)

In der Web-GUI unter **Zeitplan** einstellen, oder:

```bash
systemctl status nc-backup.timer
sudo journalctl -u nc-backup.service
```

Logs: `/var/log/nc-backup/backup.log`

---

## Befehle

| Befehl | Zweck |
|--------|--------|
| `nc-backup-web` | Web-GUI manuell starten |
| `nc-backup` | GTK-GUI (mit Display) |
| `sudo nc-backup-run` | Backup per Terminal |
| `systemctl restart nc-backup-web` | Web-GUI neu starten |

---

## Deinstallation

```bash
sudo systemctl disable --now nc-backup-web nc-backup.timer
sudo dpkg -r nc-backup
# oder bei Skript-Installation:
sudo pip3 uninstall nc-backup
```

Konfiguration bleibt in `/etc/nc-backup/` (optional manuell löschen).
