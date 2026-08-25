#!/usr/bin/env bash
# Web-GUI als systemd-Dienst einrichten (Start beim Boot).
set -euo pipefail

if [[ "${EUID:-}" -ne 0 ]]; then
  echo "Bitte mit sudo ausführen: sudo ./install/enable-web-service.sh"
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="/etc/nc-backup/web.env"
SERVICE_DST="/etc/systemd/system/nc-backup-web.service"

WEB_BIN="$(command -v nc-backup-web || true)"
if [[ -z "${WEB_BIN}" ]]; then
  echo "Fehler: nc-backup-web nicht gefunden. Zuerst das Paket installieren."
  exit 1
fi

install -d -m 775 -o root -g nc-backup /etc/nc-backup

if [[ ! -f "${ENV_FILE}" ]]; then
  SECRET="$(openssl rand -hex 32 2>/dev/null || head -c 32 /dev/urandom | xxd -p -c 32)"
  cat > "${ENV_FILE}" <<EOF
# Nextcloud Backup Web-GUI
NC_BACKUP_WEB_HOST=0.0.0.0
NC_BACKUP_WEB_PORT=42173
NC_BACKUP_WEB_SECRET=${SECRET}
EOF
  chmod 640 "${ENV_FILE}"
  chown root:nc-backup "${ENV_FILE}"
  echo "==> ${ENV_FILE} angelegt"
else
  echo "==> ${ENV_FILE} existiert bereits"
fi

sed "s|^ExecStart=.*|ExecStart=${WEB_BIN}|" \
  "${SCRIPT_DIR}/nc-backup-web.service" > "${SERVICE_DST}"
chmod 644 "${SERVICE_DST}"

systemctl daemon-reload
systemctl enable nc-backup-web.service
systemctl restart nc-backup-web.service

echo
echo "Web-GUI läuft als Dienst und startet beim Boot automatisch."
echo "Status:  systemctl status nc-backup-web"
echo "Logs:    journalctl -u nc-backup-web -f"
echo "URL:     http://$(hostname -I | awk '{print $1}'):42173"
