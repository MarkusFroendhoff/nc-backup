#!/usr/bin/env bash
# Dateidaten und Nextcloud-Konfiguration sichern

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/common.sh
source "${SCRIPT_DIR}/lib/common.sh"

backup_data() {
  local dest_dir="$1"
  [[ -d "${NC_DATA_DIR}" ]] || die "Datenverzeichnis nicht gefunden: ${NC_DATA_DIR}"

  local archive="${dest_dir}/nextcloud-data.tar"
  log "Dateidaten archivieren (${NC_DATA_DIR}) …"

  tar -cf "${archive}" \
    -C "$(dirname "${NC_DATA_DIR}")" \
    "$(basename "${NC_DATA_DIR}")"

  compress_file "${archive}"
  log "Dateidaten gesichert."
}

backup_config() {
  local dest_dir="$1"
  local config_dir="${NC_INSTALL_DIR}/config"
  [[ -d "${config_dir}" ]] || die "Config-Verzeichnis nicht gefunden: ${config_dir}"

  local archive="${dest_dir}/nextcloud-config.tar"
  log "Konfiguration archivieren …"

  tar -cf "${archive}" \
    -C "${NC_INSTALL_DIR}" \
    config

  compress_file "${archive}"
  log "Konfiguration gesichert."
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  load_config
  stamp="${1:-$(date +%Y%m%d-%H%M%S)}"
  ensure_backup_dir "${stamp}"
  backup_data "${BACKUP_DIR}"
  backup_config "${BACKUP_DIR}"
fi
