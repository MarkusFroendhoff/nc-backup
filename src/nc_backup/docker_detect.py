"""Automatische Erkennung von Docker-Nextcloud-Installationen."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from nc_backup.docker_helper import docker_available, list_container_mounts

NC_KEYWORDS = ("nextcloud", "owncloud")
DB_KEYWORDS = ("mariadb", "mysql", "postgres", "postgresql")


@dataclass
class DockerDetection:
    nextcloud_container: str
    db_container: str = ""
    source_folders: list[str] = field(default_factory=list)
    config_php_path: str = ""
    notes: list[str] = field(default_factory=list)

    @property
    def summary(self) -> str:
        db = self.db_container or "kein DB-Container erkannt"
        return f"{self.nextcloud_container} → DB: {db}"


def detect_docker_installations() -> list[DockerDetection]:
    if not docker_available():
        raise RuntimeError("Docker ist nicht installiert oder nicht im PATH.")

    containers = _list_running_containers()
    if not containers:
        raise RuntimeError("Keine laufenden Docker-Container gefunden.")

    candidates = [info for info in containers if _is_nextcloud_container(info)]
    if not candidates:
        raise RuntimeError(
            "Kein Nextcloud-Container gefunden. "
            "Erwartet werden laufende Container mit 'nextcloud' im Namen oder Image."
        )

    detections: list[DockerDetection] = []
    for info in candidates:
        name = _container_name(info)
        detection = _detect_from_container(name, containers)
        detections.append(detection)
    return detections


def _list_running_containers() -> list[dict]:
    result = subprocess.run(
        ["docker", "ps", "--format", "{{json .}}"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "docker ps fehlgeschlagen")

    containers: list[dict] = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if line:
            containers.append(json.loads(line))
    return containers


def _container_name(info: dict) -> str:
    return info.get("Names", "") or info.get("Name", "")


def _container_image(info: dict) -> str:
    return (info.get("Image", "") or "").lower()


def _is_nextcloud_container(info: dict) -> bool:
    image = _container_image(info)
    name = _container_name(info).lower()
    return any(keyword in image or keyword in name for keyword in NC_KEYWORDS)


def _is_db_container(info: dict) -> bool:
    image = _container_image(info)
    name = _container_name(info).lower()
    return any(keyword in image or keyword in name for keyword in DB_KEYWORDS)


def _inspect_label(container: str, label: str) -> str:
    result = subprocess.run(
        ["docker", "inspect", container, "--format", f"{{{{index .Config.Labels \"{label}\"}}}}"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return ""
    value = result.stdout.strip()
    return "" if value == "<no value>" else value


def _container_networks(container: str) -> set[str]:
    result = subprocess.run(
        [
            "docker", "inspect", container,
            "--format", "{{range $name, $_ := .NetworkSettings.Networks}}{{$name}} {{end}}",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return set()
    return {part for part in result.stdout.split() if part}


def _find_db_container(nextcloud_container: str, containers: list[dict]) -> str:
    nc_networks = _container_networks(nextcloud_container)
    nc_project = _inspect_label(nextcloud_container, "com.docker.compose.project")

    network_matches: list[str] = []
    project_matches: list[str] = []

    for info in containers:
        name = _container_name(info)
        if name == nextcloud_container or not _is_db_container(info):
            continue

        if nc_networks and _container_networks(name) & nc_networks:
            network_matches.append(name)

        project = _inspect_label(name, "com.docker.compose.project")
        if nc_project and project == nc_project:
            project_matches.append(name)

    if len(network_matches) == 1:
        return network_matches[0]
    if network_matches:
        return network_matches[0]
    if len(project_matches) == 1:
        return project_matches[0]
    if project_matches:
        return project_matches[0]
    return ""


def _normalize_dest(destination: str) -> str:
    return destination.rstrip("/")


def resolve_paths_from_mounts(mounts: list[dict[str, str]]) -> tuple[list[str], str, list[str]]:
    notes: list[str] = []
    folders: list[str] = []
    config_php = ""
    by_dest = {_normalize_dest(mount["destination"]): mount["source"] for mount in mounts}

    config_mounts = ("/var/www/html/config", "/config")
    data_mounts = ("/var/www/html/data", "/data")
    root_mounts = ("/var/www/html",)

    for dest in config_mounts:
        if dest not in by_dest:
            continue
        host_path = by_dest[dest]
        if host_path not in folders:
            folders.append(host_path)
        candidate = Path(host_path) / "config.php"
        if candidate.is_file():
            config_php = str(candidate)
        else:
            notes.append(f"config.php nicht auf Host gefunden: {candidate}")
        break

    for dest in data_mounts:
        if dest not in by_dest:
            continue
        host_path = by_dest[dest]
        if host_path not in folders:
            folders.append(host_path)
        break

    for dest in root_mounts:
        if dest not in by_dest:
            continue
        root = Path(by_dest[dest])
        data_dir = root / "data"
        config_dir = root / "config"
        if str(data_dir) not in folders:
            folders.append(str(data_dir))
        if str(config_dir) not in folders:
            folders.append(str(config_dir))
        candidate = config_dir / "config.php"
        if candidate.is_file() and not config_php:
            config_php = str(candidate)
        break

    for mount in mounts:
        source = mount["source"]
        if "/docker/volumes/" in source:
            notes.append(f"Docker-Volume erkannt: {source}")

    if not folders:
        notes.append("Keine typischen Nextcloud-Mounts gefunden (/var/www/html/...).")

    return folders, config_php, notes


def _detect_from_container(container: str, all_containers: list[dict]) -> DockerDetection:
    mounts = list_container_mounts(container)
    folders, config_php, notes = resolve_paths_from_mounts(mounts)
    db_container = _find_db_container(container, all_containers)

    if db_container:
        notes.append(f"DB-Container über Netzwerk/Compose erkannt: {db_container}")
    else:
        notes.append("Kein DB-Container automatisch erkannt – ggf. manuell eintragen.")

    return DockerDetection(
        nextcloud_container=container,
        db_container=db_container,
        source_folders=folders,
        config_php_path=config_php,
        notes=notes,
    )
