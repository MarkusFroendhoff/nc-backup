"""Hilfen für Docker-basierte Nextcloud-Installationen."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path


class DockerError(RuntimeError):
    pass


def docker_available() -> bool:
    return shutil.which("docker") is not None


def container_running(name: str) -> bool:
    if not name or not docker_available():
        return False
    result = subprocess.run(
        ["docker", "inspect", "-f", "{{.State.Running}}", name],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0 and result.stdout.strip() == "true"


def exec_in_container(container: str, command: list[str]) -> subprocess.CompletedProcess[str]:
    if not container_running(container):
        raise DockerError(f"Container läuft nicht: {container}")
    return subprocess.run(
        ["docker", "exec", container, *command],
        capture_output=True,
        text=True,
        check=False,
    )


def dump_mysql_in_container(
    container: str,
    dbname: str,
    dbuser: str,
    dbpassword: str,
    output_file: Path,
) -> None:
    env = ["-e", f"MYSQL_PWD={dbpassword}"] if dbpassword else []
    command = [
        "docker", "exec", *env, container,
        "mysqldump",
        "-u", dbuser,
        "--single-transaction",
        "--quick",
        dbname,
    ]
    result = subprocess.run(command, capture_output=True, check=False)
    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", errors="replace")
        raise DockerError(f"mysqldump im Container fehlgeschlagen: {stderr}")
    output_file.write_bytes(result.stdout)


def dump_postgres_in_container(
    container: str,
    dbname: str,
    dbuser: str,
    dbpassword: str,
    output_file: Path,
) -> None:
    env = ["-e", f"PGPASSWORD={dbpassword}"] if dbpassword else []
    command = [
        "docker", "exec", *env, container,
        "pg_dump",
        "-U", dbuser,
        "-d", dbname,
        "-F", "p",
    ]
    result = subprocess.run(command, capture_output=True, check=False)
    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", errors="replace")
        raise DockerError(f"pg_dump im Container fehlgeschlagen: {stderr}")
    output_file.write_text(result.stdout.decode("utf-8", errors="replace"), encoding="utf-8")


def list_container_mounts(container: str) -> list[dict[str, str]]:
    if not container_running(container):
        return []
    result = subprocess.run(
        ["docker", "inspect", container, "--format", "{{json .Mounts}}"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return []
    mounts = json.loads(result.stdout or "[]")
    return [
        {
            "source": mount.get("Source", ""),
            "destination": mount.get("Destination", ""),
        }
        for mount in mounts
    ]
