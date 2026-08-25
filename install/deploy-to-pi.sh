#!/usr/bin/env bash
# Erstellt ein sauberes Archiv fuer den Pi (ohne Null-Byte-Probleme bei scp).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
ARCHIVE="/tmp/nc-backup-deploy.tar.gz"

echo "==> Packe Projekt nach ${ARCHIVE}"
export COPYFILE_DISABLE=1
tar -czf "${ARCHIVE}" \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  --exclude='.DS_Store' \
  --exclude='._*' \
  --exclude='.git' \
  -C "${PROJECT_DIR}" .

echo "==> Kopiere auf Pi (IP/Benutzer anpassen):"
echo "scp ${ARCHIVE} markus@192.168.178.4:~/nc-backup.tar.gz"
echo
echo "==> Auf dem Pi ausfuehren:"
cat <<'EOF'
mkdir -p ~/nc-backup
tar -xzf ~/nc-backup.tar.gz -C ~/nc-backup
cd ~/nc-backup
sudo pip3 uninstall -y nc-backup 2>/dev/null || true
sudo ./install/install.sh
sudo nc-backup-web --host 0.0.0.0 --port 42173
EOF
