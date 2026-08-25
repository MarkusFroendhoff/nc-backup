"""Datenbank-Dumps für MySQL, PostgreSQL und SQLite."""

from __future__ import annotations

import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

from nc_backup.config_php import NextcloudDbConfig
from nc_backup.docker_helper import (
    DockerError,
    dump_mysql_in_container,
    dump_postgres_in_container,
)


class DatabaseDumpError(RuntimeError):
    pass


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def dump_database(
    db_config: NextcloudDbConfig,
    target_dir: Path,
    docker_db_container: str = "",
) -> Path:
    target_dir.mkdir(parents=True, exist_ok=True)
    dbtype = db_config.dbtype

    if dbtype in ("mysql", "mariadb"):
        output = target_dir / f"database_{_timestamp()}.sql"
        if docker_db_container:
            dump_mysql_in_container(
                docker_db_container,
                db_config.dbname,
                db_config.dbuser,
                db_config.dbpassword,
                output,
            )
        else:
            _dump_mysql_host(db_config, output)
        return output

    if dbtype in ("pgsql", "postgres", "postgresql"):
        output = target_dir / f"database_{_timestamp()}.sql"
        if docker_db_container:
            dump_postgres_in_container(
                docker_db_container,
                db_config.dbname,
                db_config.dbuser,
                db_config.dbpassword,
                output,
            )
        else:
            _dump_postgres_host(db_config, output)
        return output

    if dbtype == "sqlite":
        sqlite_path = _resolve_sqlite_path(db_config)
        output = target_dir / f"database_{sqlite_path.name}"
        shutil.copy2(sqlite_path, output)
        return output

    raise DatabaseDumpError(f"Unbekannter Datenbanktyp: {dbtype}")


def _dump_mysql_host(db_config: NextcloudDbConfig, output: Path) -> None:
    if not shutil.which("mysqldump") and not shutil.which("mariadb-dump"):
        raise DatabaseDumpError("mysqldump/mariadb-dump nicht installiert")
    binary = shutil.which("mariadb-dump") or shutil.which("mysqldump")
    env = os.environ.copy()
    if db_config.dbpassword:
        env["MYSQL_PWD"] = db_config.dbpassword
    host = db_config.dbhost.split(":")[0]
    port = db_config.dbhost.split(":")[1] if ":" in db_config.dbhost else None
    command = [binary, "-h", host, "-u", db_config.dbuser, "--single-transaction", "--quick"]
    if port:
        command.extend(["-P", port])
    command.append(db_config.dbname)
    with output.open("wb") as handle:
        result = subprocess.run(command, stdout=handle, stderr=subprocess.PIPE, env=env, check=False)
    if result.returncode != 0:
        raise DatabaseDumpError(result.stderr.decode("utf-8", errors="replace"))


def _dump_postgres_host(db_config: NextcloudDbConfig, output: Path) -> None:
    if not shutil.which("pg_dump"):
        raise DatabaseDumpError("pg_dump nicht installiert")
    env = os.environ.copy()
    if db_config.dbpassword:
        env["PGPASSWORD"] = db_config.dbpassword
    host = db_config.dbhost.split(":")[0]
    port = db_config.dbhost.split(":")[1] if ":" in db_config.dbhost else "5432"
    command = [
        "pg_dump",
        "-h", host,
        "-p", port,
        "-U", db_config.dbuser,
        "-d", db_config.dbname,
        "-F", "p",
    ]
    with output.open("w", encoding="utf-8") as handle:
        result = subprocess.run(command, stdout=handle, stderr=subprocess.PIPE, env=env, check=False)
    if result.returncode != 0:
        raise DatabaseDumpError(result.stderr.decode("utf-8", errors="replace"))


def _resolve_sqlite_path(db_config: NextcloudDbConfig) -> Path:
    if db_config.datadirectory:
        candidate = Path(db_config.datadirectory) / db_config.dbname
        if candidate.is_file():
            return candidate
    candidate = Path(db_config.dbname)
    if candidate.is_file():
        return candidate
    raise DatabaseDumpError(f"SQLite-Datei nicht gefunden: {db_config.dbname}")
