#!/usr/bin/env bash
# Gemeinsame Hilfsfunktionen für nc-backup

set -euo pipefail

log() {
  printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"
}

die() {
  log "FEHLER: $*"
  exit 1
}

load_config() {
  local config_file="${NC_BACKUP_CONFIG:-/etc/nc-backup/backup.env}"
  if [[ -f "${config_file}" ]]; then
    # shellcheck source=/dev/null
    source "${config_file}"
  elif [[ -f "$(dirname "$0")/../../config/backup.env" ]]; then
    # shellcheck source=/dev/null
    source "$(dirname "$0")/../../config/backup.env"
  else
    die "Keine Konfiguration gefunden. Erwartet: ${config_file}"
  fi

  : "${NC_INSTALL_DIR:?NC_INSTALL_DIR fehlt}"
  : "${NC_DATA_DIR:?NC_DATA_DIR fehlt}"
  : "${BACKUP_ROOT:?BACKUP_ROOT fehlt}"
  DB_TYPE="${DB_TYPE:-mariadb}"
  RETENTION_DAYS="${RETENTION_DAYS:-14}"
  COMPRESS="${COMPRESS:-gzip}"
  NC_MAINTENANCE_MODE="${NC_MAINTENANCE_MODE:-true}"
  NC_OCC_USER="${NC_OCC_USER:-www-data}"
}

run_as_www_data() {
  if [[ "$(id -u)" -eq 0 ]]; then
    sudo -u "${NC_OCC_USER}" -- "$@"
  else
    "$@"
  fi
}

occ() {
  local occ_bin="${NC_INSTALL_DIR}/occ"
  [[ -x "${occ_bin}" ]] || die "occ nicht gefunden: ${occ_bin}"
  run_as_www_data php "${occ_bin}" "$@"
}

maintenance_on() {
  [[ "${NC_MAINTENANCE_MODE}" == "true" ]] || return 0
  log "Wartungsmodus aktivieren …"
  occ maintenance:mode --on
}

maintenance_off() {
  [[ "${NC_MAINTENANCE_MODE}" == "true" ]] || return 0
  log "Wartungsmodus deaktivieren …"
  occ maintenance:mode --off || true
}

ensure_backup_dir() {
  local stamp="$1"
  BACKUP_DIR="${BACKUP_ROOT}/${stamp}"
  mkdir -p "${BACKUP_DIR}"
  chmod 700 "${BACKUP_ROOT}" 2>/dev/null || true
}

compress_file() {
  local src="$1"
  case "${COMPRESS}" in
    gzip)
      gzip -9 -f "${src}"
      echo "${src}.gz"
      ;;
    zstd)
      command -v zstd >/dev/null || die "zstd nicht installiert"
      zstd -19 -f "${src}" -o "${src}.zst"
      rm -f "${src}"
      echo "${src}.zst"
      ;;
    none)
      echo "${src}"
      ;;
    *)
      die "Unbekannte COMPRESS-Option: ${COMPRESS}"
      ;;
  esac
}

prune_old_backups() {
  [[ "${RETENTION_DAYS}" -gt 0 ]] || return 0
  log "Alte Backups löschen (älter als ${RETENTION_DAYS} Tage) …"
  find "${BACKUP_ROOT}" -mindepth 1 -maxdepth 1 -type d -mtime "+${RETENTION_DAYS}" -exec rm -rf {} +
}
