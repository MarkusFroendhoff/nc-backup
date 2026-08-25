#!/usr/bin/env bash
# Baut ein .deb-Paket (Architecture: all → läuft auf ARM64 und Intel/AMD).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
ARCH="${1:-}"
OUTPUT_DIR="$(cd "${PROJECT_DIR}/.." && pwd)"

if [[ -z "${ARCH}" ]]; then
  ARCH="$(uname -m)"
  case "${ARCH}" in
    x86_64) ARCH="amd64" ;;
    aarch64|arm64) ARCH="arm64" ;;
  esac
fi

PLATFORM="linux/${ARCH}"
VERSION="$(grep '^version' "${PROJECT_DIR}/pyproject.toml" | head -1 | sed 's/.*"\(.*\)".*/\1/')"

echo "==> Baue nc-backup ${VERSION} .deb (Architecture: all, Build-Host: ${ARCH})"
echo "    Das fertige Paket läuft auf Raspberry Pi (ARM) und Intel/AMD (x86_64)."

build_native() {
  cd "${PROJECT_DIR}"
  sudo apt-get update -qq
  sudo apt-get install -y -qq \
    devscripts debhelper dh-python python3-all python3-setuptools \
    python3-bcrypt python3-flask python3-gi rsync build-essential
  debuild -us -uc -b
}

if command -v docker >/dev/null 2>&1; then
  echo "==> Build in Docker (${PLATFORM})"
  docker run --rm --platform "${PLATFORM}" \
    -v "${PROJECT_DIR}:/build" \
    -w /build \
    ubuntu:24.04 \
    bash -ec '
      set -euo pipefail
      export DEBIAN_FRONTEND=noninteractive
      apt-get update -qq
      apt-get install -y -qq \
        devscripts debhelper dh-python python3-all python3-setuptools \
        python3-bcrypt python3-flask python3-gi rsync build-essential
      debuild -us -uc -b
      ls -la ../*.deb
    '
elif [[ "$(uname -s)" == "Linux" ]] && command -v debuild >/dev/null 2>&1; then
  echo "==> Nativer Build auf diesem System"
  build_native
else
  echo "Weder Docker noch debuild verfügbar."
  echo ""
  echo "Option A – auf Ubuntu/Debian (Pi oder PC):"
  echo "  sudo apt install devscripts debhelper dh-python"
  echo "  cd \"${PROJECT_DIR}\" && debuild -us -uc -b"
  echo ""
  echo "Option B – Mac mit Docker:"
  echo "  ./install/build-deb.sh amd64"
  exit 1
fi

DEB="$(ls -1 "${OUTPUT_DIR}"/nc-backup_"${VERSION}"-*_all.deb 2>/dev/null | tail -1)"
if [[ -n "${DEB}" ]]; then
  echo ""
  echo "Fertig: ${DEB}"
  echo ""
  echo "Installieren (auf beliebigem Ubuntu/Debian, ARM oder Intel):"
  echo "  sudo dpkg -i ${DEB}"
  echo "  sudo apt -f install"
else
  echo "Hinweis: .deb sollte in ${OUTPUT_DIR}/ liegen."
  ls -la "${OUTPUT_DIR}"/*.deb 2>/dev/null || true
fi
