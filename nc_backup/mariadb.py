"""Datenbank-Dump (Host-mysqldump/pg_dump oder docker exec)."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from nc_backup.logutil import log
from nc_backup.models import AppConfig
from nc_backup.detect import parse_dbhost
from nc_backup.runner import which

DUMP_TIMEOUT = 3600


def _db_type(cfg: AppConfig) -> str:
    raw = (getattr(cfg.database, "type", "") or "mysql").lower().strip()
    if raw in ("postgres", "postgresql"):
        return "pgsql"
    return raw or "mysql"


def _is_pgsql(db_type: str) -> bool:
    return db_type in ("pgsql", "postgres", "postgresql")


def _docker_creds(cfg: AppConfig, container: str) -> tuple[str, str, str]:
    db = cfg.database
    user, password, name = db.user, db.password, db.name
    if user and password and name:
        return user, password, name
    try:
        from nc_backup.docker_detect import credentials_from_env, docker_run, parse_inspect
    except ImportError:
        return user, password, name
    try:
        result = docker_run(["inspect", container], timeout=12)
    except Exception:
        return user, password, name
    if result.returncode != 0:
        return user, password, name
    import json

    try:
        data = json.loads(result.stdout or "[]")
    except json.JSONDecodeError:
        return user, password, name
    raw = data[0] if isinstance(data, list) and data else data
    if not isinstance(raw, dict):
        return user, password, name
    info = parse_inspect(raw)
    extra = credentials_from_env(info.env, _db_type(cfg))
    user = user or extra.get("dbuser") or user
    password = password or extra.get("dbpassword") or password
    name = name or extra.get("dbname") or name
    return user, password, name


def dump_database(cfg: AppConfig, dest_sql: Path) -> None:
    dest_sql.parent.mkdir(parents=True, exist_ok=True)
    db = cfg.database
    db_type = _db_type(cfg)
    container = (getattr(db, "container", "") or "").strip()

    if container:
        log(f"Datenbank-Dump im Docker-Container {container} …")
        _dump_via_docker(cfg, dest_sql, db_type, container)
        log("Datenbank-Dump abgeschlossen.")
        return

    if db_type == "sqlite":
        _dump_sqlite(cfg, dest_sql)
        return

    if _is_pgsql(db_type):
        log(f"Datenbank-Backup nach {dest_sql} …")
        _dump_postgres_host(cfg, dest_sql)
        log("Datenbank-Dump abgeschlossen.")
        return

    log(f"Datenbank-Backup nach {dest_sql} …")
    _dump_mysql_host(cfg, dest_sql)
    log("Datenbank-Dump abgeschlossen.")


def _raise_docker_fail(exc: BaseException) -> None:
    from nc_backup.docker_detect import DockerError, docker_error_message

    if isinstance(exc, DockerError):
        raise RuntimeError(str(exc)) from exc
    raise RuntimeError(docker_error_message(exc)) from exc


def _dump_via_docker(cfg: AppConfig, dest_sql: Path, db_type: str, container: str) -> None:
    from nc_backup.docker_detect import (
        DockerError,
        DockerUnavailable,
        docker_bin,
        docker_run,
    )

    if not docker_bin():
        raise RuntimeError(
            "Docker ist nicht installiert oder nicht im PATH. "
            "Für Container-Datenbanken wird das Kommando „docker“ benötigt."
        )
    try:
        running = docker_run(
            ["inspect", "-f", "{{.State.Running}}", container],
            timeout=12,
        )
    except DockerUnavailable as exc:
        raise RuntimeError(str(exc)) from exc
    except DockerError as exc:
        _raise_docker_fail(exc)
        return
    if running.returncode != 0 or (running.stdout or "").strip().lower() != "true":
        err = (running.stderr or "").strip()
        if err:
            from nc_backup.docker_detect import _perm_denied

            if _perm_denied(err):
                raise RuntimeError(
                    "Keine Berechtigung für Docker. Bitte nc-backup als root ausführen "
                    "oder den Dienstbenutzer in die Gruppe „docker“ aufnehmen."
                )
        raise RuntimeError(
            f"Der Datenbank-Container „{container}“ läuft nicht. "
            "Bitte den Container starten und die Sicherung erneut versuchen."
        )

    user, password, name = _docker_creds(cfg, container)
    if not name:
        raise RuntimeError("Datenbankname fehlt — bitte in der Konfiguration oder config.php prüfen.")
    if not user:
        raise RuntimeError("Datenbankbenutzer fehlt — bitte in der Konfiguration oder config.php prüfen.")

    if _is_pgsql(db_type):
        _dump_postgres_docker(container, user, password, name, dest_sql)
    else:
        _dump_mysql_docker(container, user, password, name, dest_sql)


def _dump_mysql_docker(
    container: str, user: str, password: str, name: str, dest_sql: Path
) -> None:
    from nc_backup.docker_detect import docker_bin

    binary = docker_bin()
    env_args = ["-e", f"MYSQL_PWD={password}"] if password else []
    last_err = ""
    for dump_bin in ("mariadb-dump", "mysqldump"):
        cmd = [
            binary,
            "exec",
            *env_args,
            container,
            dump_bin,
            "-u",
            user,
            "--single-transaction",
            "--quick",
            "--lock-tables=false",
            name,
        ]
        try:
            with dest_sql.open("wb") as out:
                result = subprocess.run(
                    cmd,
                    stdout=out,
                    stderr=subprocess.PIPE,
                    check=False,
                    timeout=DUMP_TIMEOUT,
                )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(
                f"Dump im Container {container} hat das Zeitlimit überschritten."
            ) from exc
        except FileNotFoundError as exc:
            raise RuntimeError(
                "Docker ist nicht installiert oder nicht im PATH. "
                "Für Container-Datenbanken wird das Kommando „docker“ benötigt."
            ) from exc
        if result.returncode == 0:
            return
        last_err = (result.stderr or b"").decode("utf-8", errors="replace")
        if "executable file not found" in last_err or "not found" in last_err.lower():
            continue
        from nc_backup.docker_detect import _perm_denied

        if _perm_denied(last_err):
            raise RuntimeError(
                "Keine Berechtigung für Docker. Bitte nc-backup als root ausführen "
                "oder den Dienstbenutzer in die Gruppe „docker“ aufnehmen."
            )
        raise RuntimeError(
            f"Dump im Container {container} fehlgeschlagen: {last_err.strip() or dump_bin}"
        )
    raise RuntimeError(
        f"Weder mariadb-dump noch mysqldump im Container {container} gefunden. {last_err.strip()}"
    )


def _dump_postgres_docker(
    container: str, user: str, password: str, name: str, dest_sql: Path
) -> None:
    from nc_backup.docker_detect import docker_bin

    binary = docker_bin()
    env_args = ["-e", f"PGPASSWORD={password}"] if password else []
    cmd = [
        binary,
        "exec",
        *env_args,
        container,
        "pg_dump",
        "-U",
        user,
        "-d",
        name,
        "-F",
        "p",
    ]
    try:
        with dest_sql.open("wb") as out:
            result = subprocess.run(
                cmd,
                stdout=out,
                stderr=subprocess.PIPE,
                check=False,
                timeout=DUMP_TIMEOUT,
            )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f"pg_dump im Container {container} hat das Zeitlimit überschritten."
        ) from exc
    except FileNotFoundError as exc:
        raise RuntimeError(
            "Docker ist nicht installiert oder nicht im PATH. "
            "Für Container-Datenbanken wird das Kommando „docker“ benötigt."
        ) from exc
    if result.returncode != 0:
        err = (result.stderr or b"").decode("utf-8", errors="replace")
        from nc_backup.docker_detect import _perm_denied

        if _perm_denied(err):
            raise RuntimeError(
                "Keine Berechtigung für Docker. Bitte nc-backup als root ausführen "
                "oder den Dienstbenutzer in die Gruppe „docker“ aufnehmen."
            )
        raise RuntimeError(
            f"pg_dump im Container {container} fehlgeschlagen: {err.strip()}"
        )


def _dump_mysql_host(cfg: AppConfig, dest_sql: Path) -> None:
    binary = which("mariadb-dump") or which("mysqldump")
    if binary is None:
        raise RuntimeError("mysqldump/mariadb-dump nicht installiert (Paket mariadb-client)")
    db = cfg.database
    cmd = [
        binary,
        "--single-transaction",
        "--quick",
        "--lock-tables=false",
        "-u",
        db.user,
        db.name,
    ]
    host, port_from_host = parse_dbhost(db.host or "localhost")
    if host.startswith("/") or host.endswith(".sock"):
        cmd[1:1] = ["-S", host]
    else:
        cmd[1:1] = ["-h", host, "-P", str(port_from_host or db.port or 3306)]
    env = os.environ.copy()
    if db.password:
        env["MYSQL_PWD"] = db.password
    with dest_sql.open("wb") as out:
        result = subprocess.run(
            cmd, env=env, stdout=out, stderr=subprocess.PIPE, check=False, timeout=DUMP_TIMEOUT
        )
    if result.returncode != 0:
        err = (result.stderr or b"").decode("utf-8", errors="replace")
        raise RuntimeError(err.strip() or "mysqldump fehlgeschlagen")


def _dump_postgres_host(cfg: AppConfig, dest_sql: Path) -> None:
    if which("pg_dump") is None:
        raise RuntimeError("pg_dump nicht installiert (Paket postgresql-client)")
    db = cfg.database
    env = os.environ.copy()
    if db.password:
        env["PGPASSWORD"] = db.password
    host = db.host or "localhost"
    cmd = ["pg_dump", "-U", db.user, "-d", db.name, "-F", "p"]
    if host.startswith("/") or str(host).endswith(".sock"):
        cmd.extend(["-h", host])
    else:
        cmd.extend(["-h", host, "-p", str(db.port or 5432)])
    with dest_sql.open("wb") as out:
        result = subprocess.run(
            cmd, env=env, stdout=out, stderr=subprocess.PIPE, check=False, timeout=DUMP_TIMEOUT
        )
    if result.returncode != 0:
        err = (result.stderr or b"").decode("utf-8", errors="replace")
        raise RuntimeError(err.strip() or "pg_dump fehlgeschlagen")


def _dump_sqlite(cfg: AppConfig, dest_sql: Path) -> None:
    name = cfg.database.name
    candidates = []
    if cfg.nextcloud.data_dir:
        candidates.append(Path(cfg.nextcloud.data_dir) / name)
    candidates.append(Path(name))
    src = next((p for p in candidates if p.is_file()), None)
    if src is None:
        raise RuntimeError(f"SQLite-Datei nicht gefunden: {name}")
    shutil.copy2(src, dest_sql)
    log(f"SQLite kopiert von {src}")
