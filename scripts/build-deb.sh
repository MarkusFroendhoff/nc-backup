#!/usr/bin/env bash
# .deb-Paket bauen (auf Ubuntu/Debian)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

if ! command -v dpkg-buildpackage >/dev/null 2>&1; then
  echo "Bitte Build-Tools installieren:"
  echo "  sudo apt install dpkg-dev debhelper dh-python python3-all python3-setuptools"
  exit 1
fi

echo "==> Baue nc-backup Debian-Paket …"
dpkg-buildpackage -us -uc -b

DEB="$(ls -1t ../nc-backup_*.deb 2>/dev/null | head -1)"
if [[ -n "${DEB}" ]]; then
  echo ""
  echo "Fertig: ${DEB}"
  echo "Installieren: sudo apt install ./${DEB##*/}"
else
  echo "Paket erstellt (siehe ../*.deb)"
fi
