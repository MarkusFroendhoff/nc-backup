#!/usr/bin/env bash
# Erstellt ein Quell-Archiv zum Weitergeben (ohne .git, __pycache__, Mac-Metadaten).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
VERSION="$(grep '^version' "${PROJECT_DIR}/pyproject.toml" | head -1 | sed 's/.*"\(.*\)".*/\1/')"
RELEASE_DIR="${PROJECT_DIR}/../nc-backup-${VERSION}"
ARCHIVE="${PROJECT_DIR}/../nc-backup-${VERSION}.tar.gz"

echo "==> Release-Archiv ${ARCHIVE}"
rm -rf "${RELEASE_DIR}"
mkdir -p "${RELEASE_DIR}"

export COPYFILE_DISABLE=1
tar -cf - \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  --exclude='.DS_Store' \
  --exclude='._*' \
  --exclude='.git' \
  --exclude='debian/nc-backup' \
  --exclude='*.egg-info' \
  --exclude='build' \
  -C "${PROJECT_DIR}" . | tar -xf - -C "${RELEASE_DIR}"

COPYFILE_DISABLE=1 tar -czf "${ARCHIVE}" -C "$(dirname "${RELEASE_DIR}")" "$(basename "${RELEASE_DIR}")"
rm -rf "${RELEASE_DIR}"

echo "Fertig: ${ARCHIVE}"
echo ""
echo "Weitergeben:"
echo "  1. Archiv: nc-backup-${VERSION}.tar.gz  (Quellcode + install.sh)"
echo "  2. Oder .deb bauen: ./install/build-deb.sh"
echo "  3. Anleitung: docs/INSTALL.md"
