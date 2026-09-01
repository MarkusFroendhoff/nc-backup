#!/usr/bin/env bash
# Installation auf Ubuntu 24.04 / 26.04 LTS (Zielsystem)

set -euo pipefail

INSTALL_PREFIX="${INSTALL_PREFIX:-/opt/nc-backup}"
CONFIG_DIR="/etc/nc-backup"
SYSTEMD_DIR="/etc/systemd/system"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Bitte als root ausführen: sudo $0"
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

echo "Installiere nc-backup nach ${INSTALL_PREFIX} …"
mkdir -p "${INSTALL_PREFIX}/scripts/lib"
cp -r "${REPO_ROOT}/scripts/"* "${INSTALL_PREFIX}/scripts/"
chmod +x "${INSTALL_PREFIX}/scripts/"*.sh

mkdir -p "${CONFIG_DIR}"
if [[ ! -f "${CONFIG_DIR}/backup.env" ]]; then
  cp "${REPO_ROOT}/config/backup.env.example" "${CONFIG_DIR}/backup.env"
  chmod 600 "${CONFIG_DIR}/backup.env"
  echo "Konfiguration angelegt: ${CONFIG_DIR}/backup.env — bitte anpassen!"
else
  echo "Konfiguration existiert bereits: ${CONFIG_DIR}/backup.env"
fi

mkdir -p /var/backups/nextcloud
chmod 700 /var/backups/nextcloud

cp "${REPO_ROOT}/systemd/nc-backup.service" "${SYSTEMD_DIR}/"
cp "${REPO_ROOT}/systemd/nc-backup.timer" "${SYSTEMD_DIR}/"

# Pfade in Unit-Datei anpassen
sed -i "s|/opt/nc-backup|${INSTALL_PREFIX}|g" "${SYSTEMD_DIR}/nc-backup.service"

systemctl daemon-reload
systemctl enable nc-backup.timer

echo ""
echo "Fertig. Nächste Schritte:"
echo "  1. ${CONFIG_DIR}/backup.env bearbeiten"
echo "  2. Manuell testen: ${INSTALL_PREFIX}/scripts/backup-nextcloud.sh"
echo "  3. Timer starten: systemctl start nc-backup.timer"
echo "  4. Status: systemctl list-timers nc-backup.timer"
