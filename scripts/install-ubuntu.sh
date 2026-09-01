#!/usr/bin/env bash
# NC Backup — Installation auf Ubuntu (GUI + Web-Oberfläche)
# Ein Befehl:  sudo ./scripts/install-ubuntu.sh

set -euo pipefail

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Bitte mit sudo ausführen: sudo $0"
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

if [[ -f /etc/os-release ]]; then
  # shellcheck disable=SC1091
  . /etc/os-release
  if [[ "${ID:-}" != "ubuntu" ]]; then
    if [[ "${ID:-}" == "debian" || "${ID_LIKE:-}" == *debian* ]]; then
      echo "Hinweis: Dies ist ${PRETTY_NAME:-Debian}, nicht Ubuntu. Die Installation wird trotzdem fortgesetzt."
    else
      echo "Hinweis: Kein Ubuntu erkannt (${PRETTY_NAME:-unbekannt}). Die Installation wird trotzdem versucht."
    fi
  fi
fi

echo "==> Pakete installieren …"
apt-get update -qq
apt-get install -y \
  python3 python3-pip python3-yaml python3-setuptools \
  python3-gi gir1.2-adw-1 gir1.2-gtk-4.0 \
  restic rclone mariadb-client rsync pkexec polkitd

echo "==> NC Backup installieren …"
pip3 install --break-system-packages "${REPO_ROOT}"

echo "==> Systemdateien …"
install -d /etc/nc-backup
if [[ ! -f /etc/nc-backup/config.yaml ]]; then
  install -m 600 "${REPO_ROOT}/config/config.example.yaml" /etc/nc-backup/config.yaml
fi

install -Dm644 "${REPO_ROOT}/share/applications/de.ncbackup.NcBackup.desktop" \
  /usr/share/applications/de.ncbackup.NcBackup.desktop

install -Dm644 "${REPO_ROOT}/share/polkit-1/actions/de.ncbackup.policy" \
  /usr/share/polkit-1/actions/de.ncbackup.policy

install -Dm644 "${REPO_ROOT}/systemd/nc-backup.service" /etc/systemd/system/nc-backup.service
install -Dm644 "${REPO_ROOT}/systemd/nc-backup.timer" /etc/systemd/system/nc-backup.timer
install -Dm644 "${REPO_ROOT}/systemd/nc-backup-web.service" /etc/systemd/system/nc-backup-web.service

mkdir -p /var/backups/nextcloud
chmod 700 /var/backups/nextcloud

echo "==> Nextcloud erkennen …"
python3 - <<'PY' || true
from nc_backup.detect import apply_detected_defaults
from nc_backup.secrets import ensure_web_token

info = apply_detected_defaults()
print(info.get("summary") or "")
ensure_web_token()
PY

if command -v ufw >/dev/null 2>&1; then
  # Regel anlegen, UFW aber nicht selbst einschalten.
  ufw allow 42173/tcp comment 'nc-backup-web' >/dev/null 2>&1 || true
fi

systemctl daemon-reload
systemctl enable --now nc-backup-web.service

TOKEN=""
if [[ -f /etc/nc-backup/web-token ]]; then
  TOKEN="$(tr -d '\n' < /etc/nc-backup/web-token)"
fi

MSG="$(cat <<MSGEND
NC Backup ist eingerichtet.

• Desktop: „NC Backup“ im Anwendungsmenü öffnen
• Web: http://192.168.178.4:42173
• Zugangsschlüssel: ${TOKEN}
  (liegt unter /etc/nc-backup/web-token — bitte notieren)

Den automatischen Zeitplan stellen Sie nach der Zielwahl in der App ein.
MSGEND
)"

echo ""
echo "${MSG}"

if [[ -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ]]; then
  if command -v zenity >/dev/null 2>&1; then
    zenity --info --title="NC Backup" --width=420 --text="${MSG}" || true
  elif command -v kdialog >/dev/null 2>&1; then
    kdialog --title "NC Backup" --msgbox "${MSG}" || true
  fi
fi
