#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID:-}" -ne 0 ]]; then
  echo "Bitte mit sudo ausführen: sudo ./install/install.sh"
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
INSTALL_USER="${SUDO_USER:-${USER}}"

echo "==> Abhängigkeiten installieren"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y \
  python3 \
  python3-pip \
  python3-gi \
  python3-flask \
  python3-bcrypt \
  gir1.2-gtk-3.0 \
  rsync \
  mariadb-client \
  postgresql-client \
  policykit-1 \
  gnupg \
  python3-setuptools

echo "==> Gruppe und Verzeichnisse anlegen"
groupadd -f nc-backup
install -d -m 775 -o root -g nc-backup /etc/nc-backup
install -d -m 755 -o root -g root /var/log/nc-backup

echo "==> Python-Paket installieren"
rm -rf "${PROJECT_DIR}/build" "${PROJECT_DIR}/src/"*.egg-info 2>/dev/null || true
pip3 install --break-system-packages --no-cache-dir "${PROJECT_DIR}"

echo "==> Desktop-Eintrag und Policy installieren"
install -m 644 "${SCRIPT_DIR}/nc-backup.desktop" /usr/share/applications/nc-backup.desktop
install -m 644 "${SCRIPT_DIR}/org.ncbackup.policy" /usr/share/polkit-1/actions/org.ncbackup.policy
install -d -m 755 /usr/lib/nc-backup
install -m 755 "${SCRIPT_DIR}/apply-schedule.sh" /usr/lib/nc-backup/apply-schedule.sh
install -m 755 "${SCRIPT_DIR}/enable-web-service.sh" /usr/lib/nc-backup/enable-web-service.sh

echo "==> Benutzer zur Gruppe nc-backup hinzufügen: ${INSTALL_USER}"
usermod -aG nc-backup "${INSTALL_USER}" || true

echo "==> Nextcloud-App nach /usr/share/nc-backup"
install -d -m 755 /usr/share/nc-backup
rm -rf /usr/share/nc-backup/nextcloud-app
cp -a "${PROJECT_DIR}/nextcloud-app" /usr/share/nc-backup/

echo "==> Web-GUI als systemd-Dienst (Autostart nach Reboot)"
install -m 755 "${SCRIPT_DIR}/enable-web-service.sh" /usr/lib/nc-backup/enable-web-service.sh
install -m 644 "${SCRIPT_DIR}/nc-backup-web.service" /usr/lib/nc-backup/nc-backup-web.service
"${SCRIPT_DIR}/enable-web-service.sh" || true

echo "==> Geplanten systemd-Job auf den echten nc-backup-run-Pfad bringen"
if command -v nc-backup-run >/dev/null 2>&1; then
  nc-backup-run --apply-schedule || true
fi

echo
echo "Installation abgeschlossen."
echo "Web-GUI:  http://$(hostname -I | awk '{print $1}'):42173"
echo "Status:   systemctl status nc-backup-web"
echo "Starte GTK-GUI mit: nc-backup"
echo "Oder über das Anwendungsmenü: Nextcloud Backup"
echo
echo "Hinweis: Nach der Gruppenänderung ggf. ab- und wieder anmelden."
