#!/usr/bin/env bash
# Sauberes Archiv fuer den Pi (ohne Mac-Ressource-Forks).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
ARCHIVE="/tmp/nc-backup-deploy.tar.gz"
PI="${PI:-markus@192.168.178.4}"

echo "==> Packe Projekt nach ${ARCHIVE}"
export COPYFILE_DISABLE=1
COPYFILE_DISABLE=1 tar -czf "${ARCHIVE}" \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  --exclude='.DS_Store' \
  --exclude='._*' \
  --exclude='.git' \
  -C "${PROJECT_DIR}" .

echo "==> Kopiere nach ${PI}:~/nc-backup.tar.gz"
scp "${ARCHIVE}" "${PI}:~/nc-backup.tar.gz"

echo ""
echo "==> Auf dem Pi ausfuehren:"
cat <<EOF
mkdir -p ~/nc-backup
tar -xzf ~/nc-backup.tar.gz -C ~/nc-backup
cd ~/nc-backup
sudo ./scripts/install-ubuntu.sh
# Web-UI: http://192.168.178.4:42173
EOF
