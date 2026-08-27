#!/usr/bin/env bash
# Datenbank-Backup für Nextcloud (MariaDB/MySQL oder PostgreSQL)

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/common.sh
source "${SCRIPT_DIR}/lib/common.sh"

backup_mariadb() {
  local out="$1"
  : "${DB_NAME:?DB_NAME fehlt}"
  : "${DB_USER:?DB_USER fehlt}"

  local -a mysqldump_args=(
    --single-transaction
    --quick
    --lock-tables=false
    -h "${DB_HOST:-localhost}"
    -P "${DB_PORT:-3306}"
    -u "${DB_USER}"
  )

  if [[ -n "${DB_PASSWORD:-}" ]]; then
    MYSQL_PWD="${DB_PASSWORD}" mysqldump "${mysqldump_args[@]}" "${DB_NAME}" > "${out}"
  elif [[ -f /root/.my.cnf ]] || [[ -f "${HOME}/.my.cnf" ]]; then
    mysqldump "${mysqldump_args[@]}" "${DB_NAME}" > "${out}"
  else
    die "DB_PASSWORD leer und keine .my.cnf — Zugangsdaten setzen"
  fi
}

backup_postgresql() {
  local out="$1"
  : "${PG_DATABASE:?PG_DATABASE fehlt}"
  : "${PG_USER:?PG_USER fehlt}"

  export PGPASSWORD="${PG_PASSWORD:-}"
  pg_dump \
    -h "${PG_HOST:-localhost}" \
    -p "${PG_PORT:-5432}" \
    -U "${PG_USER}" \
    -F p \
    --no-owner \
    --no-acl \
    "${PG_DATABASE}" > "${out}"
  unset PGPASSWORD
}

backup_database() {
  local dest_dir="$1"
  local raw="${dest_dir}/database.sql"
  log "Datenbank-Backup (${DB_TYPE}) …"

  case "${DB_TYPE}" in
    mariadb|mysql)
      backup_mariadb "${raw}"
      ;;
    postgresql|postgres)
      backup_postgresql "${raw}"
      ;;
    *)
      die "Unbekannter DB_TYPE: ${DB_TYPE} (mariadb oder postgresql)"
      ;;
  esac

  compress_file "${raw}"
  log "Datenbank gesichert."
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  load_config
  stamp="${1:-$(date +%Y%m%d-%H%M%S)}"
  ensure_backup_dir "${stamp}"
  backup_database "${BACKUP_DIR}"
fi
