#!/usr/bin/env bash
# Vollständiges Nextcloud-Backup: Datenbank + Daten + Config
# Für Ubuntu 24.04 LTS — als root oder mit sudo ausführen

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/common.sh
source "${SCRIPT_DIR}/lib/common.sh"

write_manifest() {
  local dest_dir="$1"
  local manifest="${dest_dir}/MANIFEST.txt"
  {
    echo "hostname=$(hostname -f 2>/dev/null || hostname)"
    echo "timestamp=${STAMP}"
    echo "nc_version=$(occ -V 2>/dev/null || echo unknown)"
    echo "db_type=${DB_TYPE}"
    echo "data_dir=${NC_DATA_DIR}"
    echo "ubuntu=$(. /etc/os-release 2>/dev/null && echo "${PRETTY_NAME:-unknown}" || echo unknown)"
  } > "${manifest}"
}

maybe_rsync() {
  [[ -n "${RSYNC_TARGET:-}" ]] || return 0
  command -v rsync >/dev/null || die "rsync nicht installiert"
  log "Sync nach ${RSYNC_TARGET} …"
  rsync -aH --delete "${BACKUP_ROOT}/" "${RSYNC_TARGET}"
}

maybe_notify() {
  local status="$1"
  [[ -n "${NOTIFY_EMAIL:-}" ]] || return 0
  command -v mail >/dev/null || return 0
  echo "nc-backup auf $(hostname) beendet mit Status ${status}" | mail -s "nc-backup: ${status}" "${NOTIFY_EMAIL}" || true
}

main() {
  load_config
  STAMP="$(date +%Y%m%d-%H%M%S)"
  ensure_backup_dir "${STAMP}"

  trap 'maintenance_off; maybe_notify FAILED; exit 1' ERR
  trap 'maintenance_off' EXIT

  log "=== Nextcloud-Backup start (${STAMP}) ==="

  maintenance_on

  "${SCRIPT_DIR}/backup-database.sh" "${STAMP}"
  "${SCRIPT_DIR}/backup-data.sh" "${STAMP}"

  write_manifest "${BACKUP_DIR}"
  prune_old_backups
  maybe_rsync

  log "=== Backup abgeschlossen: ${BACKUP_DIR} ==="
  maybe_notify OK
}

main "$@"
