"""Docker-/Podman-Erkennung für Nextcloud und die zugehörige Datenbank."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DOCKER_TIMEOUT = 12
DOCKER_INSPECT_TIMEOUT = 18
DOCKER_EXEC_TIMEOUT = 10

NC_CONFIG_INNER = (
    "/var/www/html/config/config.php",
    "/config/www/nextcloud/config/config.php",
    "/var/www/html/nextcloud/config/config.php",
)

NC_OCC_INNER = (
    "/var/www/html/occ",
    "/config/www/nextcloud/occ",
)

CONFIG_MOUNT_DESTS = (
    "/var/www/html/config",
    "/config/www/nextcloud/config",
    "/config",
)
DATA_MOUNT_DESTS = (
    "/var/www/html/data",
    "/data",
    "/mnt/ncdata",
)
ROOT_MOUNT_DESTS = (
    "/var/www/html",
    "/var/www/html/nextcloud",
)

HOST_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "0.0.0.0"}

AIO_NC = "nextcloud-aio-nextcloud"
AIO_DB = "nextcloud-aio-database"

NC_EXCLUDE_SUBSTR = (
    "nextcloud-aio-database",
    "nextcloud-aio-redis",
    "nextcloud-aio-apache",
    "nextcloud-aio-talk",
    "nextcloud-aio-notify",
    "nextcloud-aio-imaginary",
    "nextcloud-aio-clamav",
    "nextcloud-aio-fulltext",
    "nextcloud-aio-collabora",
    "nextcloud-aio-onlyoffice",
    "nextcloud-aio-whiteboard",
    "nextcloud-aio-docker-socket",
    "nextcloud-aio-mastercontainer",
    "nextcloud-aio-watchtower",
    "nextcloud-aio-domaincheck",
    "nextcloud-aio-borgbackup",
)

NC_HELPER_NAME = (
    "redis",
    "proxy",
    "apache",
    "nginx",
    "caddy",
    "traefik",
    "talk",
    "clamav",
    "collabora",
    "onlyoffice",
    "imaginary",
    "notify",
    "whiteboard",
    "fulltext",
    "mastercontainer",
    "watchtower",
    "cron",
)

_DB_NAME_RE = re.compile(
    r"(?:^|[-_.])(?:db|database|mariadb|mysql|postgres|postgresql)(?:$|[-_.])",
    re.IGNORECASE,
)


class DockerError(RuntimeError):
    pass


class DockerUnavailable(DockerError):
    pass


class DockerPermissionError(DockerError):
    pass


def docker_bin() -> str | None:
    return shutil.which("docker") or shutil.which("podman")


def docker_available() -> bool:
    return docker_bin() is not None


def _perm_denied(stderr: str) -> bool:
    text = (stderr or "").lower()
    return (
        "permission denied" in text
        or "access denied" in text
        or "got permission denied while trying to connect" in text
    )


def _daemon_down(stderr: str) -> bool:
    text = (stderr or "").lower()
    return (
        "cannot connect to the docker daemon" in text
        or "is the docker daemon running" in text
        or "cannot connect to podman" in text
    )


def docker_run(
    args: list[str],
    *,
    timeout: float = DOCKER_TIMEOUT,
    extra_env: dict[str, str] | None = None,
    binary_output: bool = False,
) -> subprocess.CompletedProcess[Any]:
    binary = docker_bin()
    if not binary:
        raise DockerUnavailable(
            "Docker ist nicht installiert oder nicht im PATH. "
            "Für Container-Datenbanken wird das Kommando „docker“ benötigt."
        )
    env = None
    if extra_env:
        import os

        env = os.environ.copy()
        env.update(extra_env)
    try:
        result = subprocess.run(
            [binary, *args],
            capture_output=True,
            text=not binary_output,
            check=False,
            timeout=timeout,
            env=env,
        )
    except FileNotFoundError as exc:
        raise DockerUnavailable(
            "Docker ist nicht installiert oder nicht im PATH. "
            "Für Container-Datenbanken wird das Kommando „docker“ benötigt."
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise DockerError(
            "Docker-Befehl hat nicht rechtzeitig geantwortet "
            f"({timeout:.0f}s, {' '.join(args[:3])}…)."
        ) from exc
    err = result.stderr if isinstance(result.stderr, str) else (
        result.stderr.decode("utf-8", errors="replace") if result.stderr else ""
    )
    if result.returncode != 0 and _perm_denied(err):
        raise DockerPermissionError(
            "Keine Berechtigung für Docker. Bitte nc-backup als root ausführen "
            "oder den Dienstbenutzer in die Gruppe „docker“ aufnehmen."
        )
    if result.returncode != 0 and _daemon_down(err):
        raise DockerError(
            "Docker ist installiert, aber der Docker-Dienst läuft nicht."
        )
    return result


@dataclass
class ContainerInfo:
    id: str
    name: str
    image: str
    running: bool
    labels: dict[str, str] = field(default_factory=dict)
    env: dict[str, str] = field(default_factory=dict)
    mounts: list[dict[str, str]] = field(default_factory=list)
    networks: set[str] = field(default_factory=set)
    aliases: set[str] = field(default_factory=set)
    network_mode: str = ""
    published_db_port: int | None = None
    ips: set[str] = field(default_factory=set)
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def project(self) -> str:
        return (
            self.labels.get("com.docker.compose.project")
            or self.labels.get("io.podman.compose.project")
            or ""
        )

    @property
    def service(self) -> str:
        return (
            self.labels.get("com.docker.compose.service")
            or self.labels.get("io.podman.compose.service")
            or ""
        )

    @property
    def blob(self) -> str:
        return " ".join(
            (
                self.name,
                self.image,
                self.service,
                " ".join(self.aliases),
            )
        ).lower()


@dataclass
class DockerInstall:
    nc_container: str
    db_container: str = ""
    db_same_container: bool = False
    db_on_host: bool = False
    install_dir: str = ""
    data_dir: str = ""
    config_php_path: str = ""
    config_inner: str = ""
    occ_inner: str = ""
    occ_user: str = "www-data"
    parsed: dict[str, str] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    running: bool = True
    db_type: str = "mysql"
    db_type_label: str = "MariaDB"
    image: str = ""


def map_container_path(container_path: str, mounts: list[dict[str, str]]) -> str:
    """Mappt einen Pfad im Container auf den Host-Pfad (längster Mount-Präfix)."""
    norm = (container_path or "").rstrip("/") or "/"
    best_src = ""
    best_len = -1
    for mount in mounts:
        dest = (mount.get("destination") or mount.get("Destination") or "").rstrip("/") or "/"
        src = (mount.get("source") or mount.get("Source") or "").rstrip("/")
        if not src:
            continue
        if norm == dest or norm.startswith(dest + "/"):
            if len(dest) > best_len:
                best_len = len(dest)
                rel = norm[len(dest) :].lstrip("/")
                best_src = str(Path(src) / rel) if rel else src
    return best_src


def resolve_paths_from_mounts(
    mounts: list[dict[str, str]],
) -> tuple[list[str], str, list[str]]:
    """1.7.1-kompatibel: Host-Ordner und config.php aus typischen Nextcloud-Mounts."""
    notes: list[str] = []
    folders: list[str] = []
    config_php = ""
    by_dest = {
        (m.get("destination") or m.get("Destination") or "").rstrip("/"): (
            m.get("source") or m.get("Source") or ""
        )
        for m in mounts
    }

    for dest in CONFIG_MOUNT_DESTS:
        if dest not in by_dest:
            continue
        host_path = by_dest[dest]
        if host_path and host_path not in folders:
            folders.append(host_path)
        for candidate in (
            Path(host_path) / "config.php",
            Path(host_path) / "www" / "nextcloud" / "config" / "config.php",
        ):
            if candidate.is_file():
                config_php = str(candidate)
                break
        if not config_php:
            notes.append(f"config.php nicht auf Host gefunden: {Path(host_path) / 'config.php'}")
        break

    for dest in DATA_MOUNT_DESTS:
        if dest not in by_dest:
            continue
        host_path = by_dest[dest]
        if host_path and host_path not in folders:
            folders.append(host_path)
        break

    for dest in ROOT_MOUNT_DESTS:
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
        source = mount.get("source") or mount.get("Source") or ""
        if "/docker/volumes/" in source or "/containers/storage/volumes/" in source:
            notes.append(f"Docker-Volume erkannt: {source}")

    if not folders:
        notes.append("Keine typischen Nextcloud-Mounts gefunden (/var/www/html/...).")

    return folders, config_php, notes


def _parse_ps(stdout: str) -> list[dict]:
    text = (stdout or "").strip()
    if not text:
        return []
    if text.startswith("["):
        data = json.loads(text)
        return data if isinstance(data, list) else []
    rows: list[dict] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def _labels_from_ps(raw: Any) -> dict[str, str]:
    if isinstance(raw, dict):
        return {str(k): str(v) for k, v in raw.items()}
    text = str(raw or "")
    out: dict[str, str] = {}
    if not text or text == "<no value>":
        return out
    for part in text.split(","):
        if "=" in part:
            k, _, v = part.partition("=")
            out[k.strip()] = v.strip()
    return out


def _brief_containers() -> list[dict[str, str]]:
    result = docker_run(
        ["ps", "-a", "--format", "{{json .}}"],
        timeout=DOCKER_TIMEOUT,
    )
    if result.returncode != 0:
        err = (result.stderr or "").strip()
        if _perm_denied(err):
            raise DockerPermissionError(
                "Keine Berechtigung für Docker. Bitte nc-backup als root ausführen "
                "oder den Dienstbenutzer in die Gruppe „docker“ aufnehmen."
            )
        raise DockerError(err or "docker ps fehlgeschlagen.")
    rows = []
    for item in _parse_ps(result.stdout or ""):
        name = item.get("Names") or item.get("Names") or item.get("Name") or ""
        if isinstance(name, list):
            name = name[0] if name else ""
        name = str(name).split(",")[0].lstrip("/")
        status = str(item.get("Status") or item.get("State") or "")
        state = str(item.get("State") or "")
        running = state.lower() == "running" or status.lower().startswith("up")
        rows.append(
            {
                "id": str(item.get("ID") or item.get("Id") or ""),
                "name": name,
                "image": str(item.get("Image") or ""),
                "status": status,
                "running": "1" if running else "0",
                "labels": item.get("Labels") or {},
            }
        )
    return rows


def _inspect_many(ids: list[str]) -> list[dict]:
    if not ids:
        return []
    result = docker_run(["inspect", *ids], timeout=DOCKER_INSPECT_TIMEOUT)
    if result.returncode != 0:
        err = (result.stderr or "").strip()
        if _perm_denied(err):
            raise DockerPermissionError(
                "Keine Berechtigung für Docker. Bitte nc-backup als root ausführen "
                "oder den Dienstbenutzer in die Gruppe „docker“ aufnehmen."
            )
        return []
    try:
        data = json.loads(result.stdout or "[]")
    except json.JSONDecodeError:
        return []
    if isinstance(data, dict):
        return [data]
    return data if isinstance(data, list) else []


def _env_map(raw: dict) -> dict[str, str]:
    out: dict[str, str] = {}
    for item in (raw.get("Config") or {}).get("Env") or []:
        text = str(item)
        if "=" in text:
            key, _, value = text.partition("=")
            out[key] = value
    return out


def _published_db_port(raw: dict) -> int | None:
    ports = (raw.get("NetworkSettings") or {}).get("Ports") or {}
    for key, bindings in ports.items():
        short = str(key).split("/")[0]
        if short not in ("3306", "5432", "3307"):
            continue
        if not bindings:
            continue
        try:
            host_port = int(bindings[0].get("HostPort") or 0)
        except (TypeError, ValueError, IndexError, AttributeError):
            continue
        if host_port:
            return host_port
    bindings = (raw.get("HostConfig") or {}).get("PortBindings") or {}
    for key, entries in bindings.items():
        short = str(key).split("/")[0]
        if short not in ("3306", "5432", "3307"):
            continue
        if not entries:
            continue
        try:
            host_port = int(entries[0].get("HostPort") or 0)
        except (TypeError, ValueError, IndexError, AttributeError):
            continue
        if host_port:
            return host_port
    return None


def parse_inspect(raw: dict) -> ContainerInfo:
    name = str(raw.get("Name") or "").lstrip("/")
    config = raw.get("Config") or {}
    state = raw.get("State") or {}
    labels = dict(config.get("Labels") or {})
    mounts = []
    for mount in raw.get("Mounts") or []:
        mounts.append(
            {
                "source": str(mount.get("Source") or ""),
                "destination": str(mount.get("Destination") or ""),
                "type": str(mount.get("Type") or ""),
            }
        )
    networks: set[str] = set()
    aliases: set[str] = set()
    ips: set[str] = set()
    nets = (raw.get("NetworkSettings") or {}).get("Networks") or {}
    for net_name, net in nets.items():
        if net_name:
            networks.add(str(net_name))
        ip = str((net or {}).get("IPAddress") or "")
        if ip:
            ips.add(ip)
        for alias in (net or {}).get("Aliases") or []:
            if alias:
                aliases.add(str(alias))
    aliases.add(name)
    service = labels.get("com.docker.compose.service") or ""
    if service:
        aliases.add(service)
    running = bool(state.get("Running"))
    image = str(config.get("Image") or raw.get("Image") or "")
    return ContainerInfo(
        id=str(raw.get("Id") or "")[:12],
        name=name,
        image=image,
        running=running,
        labels=labels,
        env=_env_map(raw),
        mounts=mounts,
        networks=networks,
        aliases=aliases,
        network_mode=str((raw.get("HostConfig") or {}).get("NetworkMode") or ""),
        published_db_port=_published_db_port(raw),
        ips=ips,
        raw=raw,
    )


def _is_db_blob(blob: str) -> bool:
    if AIO_DB in blob:
        return True
    if any(k in blob for k in ("mariadb", "mysql", "postgres", "postgresql")):
        if "nextcloud-aio-nextcloud" in blob:
            return False
        return True
    return bool(_DB_NAME_RE.search(blob))


def is_db_container(info: ContainerInfo) -> bool:
    return _is_db_blob(info.blob)


def is_nc_container(info: ContainerInfo) -> bool:
    blob = info.blob
    name = info.name.lower()
    image = info.image.lower()
    if AIO_NC in blob:
        return True
    if is_db_container(info):
        return False
    if any(ex in name or ex in image for ex in NC_EXCLUDE_SUBSTR):
        return False
    if "nextcloud" not in blob and "owncloud" not in blob:
        return False
    for helper in NC_HELPER_NAME:
        if helper in name and AIO_NC not in name:
            # "nextcloud-cron" / sidecar, nicht die App selbst
            if "nextcloud" in name and helper in (
                "redis",
                "proxy",
                "apache",
                "nginx",
                "caddy",
                "traefik",
                "talk",
                "clamav",
                "collabora",
                "onlyoffice",
                "imaginary",
                "notify",
                "whiteboard",
                "fulltext",
                "mastercontainer",
                "watchtower",
                "cron",
            ):
                return False
    return True


def _load_candidates() -> list[ContainerInfo]:
    brief = _brief_containers()
    if not brief:
        return []
    interesting: list[str] = []
    for row in brief:
        blob = f"{row['name']} {row['image']}".lower()
        labels = row.get("labels") or {}
        label_blob = ""
        if isinstance(labels, dict):
            label_blob = " ".join(str(v) for v in labels.values()).lower()
        else:
            label_blob = str(labels).lower()
        blob = blob + " " + label_blob
        if "nextcloud" in blob or "owncloud" in blob or _is_db_blob(blob):
            interesting.append(row["id"] or row["name"])
    if not interesting:
        # Fallback: alles inspecten, wenn wenig Container da sind
        if len(brief) <= 30:
            interesting = [row["id"] or row["name"] for row in brief]
        else:
            return []
    raws = _inspect_many([i for i in interesting if i])
    return [parse_inspect(raw) for raw in raws]


def _container_running(name: str) -> bool:
    if not name:
        return False
    try:
        result = docker_run(
            ["inspect", "-f", "{{.State.Running}}", name],
            timeout=DOCKER_TIMEOUT,
        )
    except DockerError:
        return False
    return result.returncode == 0 and (result.stdout or "").strip().lower() == "true"


def read_config_text_from_container(name: str) -> tuple[str, str]:
    """Gibt (text, inner_path) zurück."""
    if not _container_running(name):
        return "", ""
    for inner in NC_CONFIG_INNER:
        try:
            result = docker_run(["exec", name, "cat", inner], timeout=DOCKER_EXEC_TIMEOUT)
        except DockerError:
            continue
        text = result.stdout or ""
        if result.returncode == 0 and ("dbhost" in text or "datadirectory" in text):
            return text, inner
    return "", ""


def copy_config_from_container(container: str, dest: Path) -> bool:
    """Kopiert den config-Ordner aus dem Container auf den Host. True bei Erfolg."""
    dest.mkdir(parents=True, exist_ok=True)
    for inner in (
        "/var/www/html/config",
        "/config/www/nextcloud/config",
        "/var/www/html/nextcloud/config",
    ):
        try:
            result = docker_run(["cp", f"{container}:{inner}/.", str(dest)], timeout=60)
        except DockerError:
            continue
        if result.returncode == 0 and any(dest.iterdir()):
            return True
    return False


def credentials_from_env(env: dict[str, str], db_type: str) -> dict[str, str]:
    t = (db_type or "mysql").lower()
    out: dict[str, str] = {}
    if t in ("pgsql", "postgres", "postgresql"):
        if env.get("POSTGRES_DB"):
            out["dbname"] = env["POSTGRES_DB"]
        if env.get("POSTGRES_USER"):
            out["dbuser"] = env["POSTGRES_USER"]
        if env.get("POSTGRES_PASSWORD"):
            out["dbpassword"] = env["POSTGRES_PASSWORD"]
        return out
    if env.get("MYSQL_DATABASE") or env.get("MARIADB_DATABASE"):
        out["dbname"] = env.get("MYSQL_DATABASE") or env.get("MARIADB_DATABASE") or ""
    if env.get("MYSQL_USER") or env.get("MARIADB_USER"):
        out["dbuser"] = env.get("MYSQL_USER") or env.get("MARIADB_USER") or ""
    if env.get("MYSQL_PASSWORD") or env.get("MARIADB_PASSWORD"):
        out["dbpassword"] = env.get("MYSQL_PASSWORD") or env.get("MARIADB_PASSWORD") or ""
    elif env.get("MYSQL_ROOT_PASSWORD") or env.get("MARIADB_ROOT_PASSWORD"):
        out["dbpassword"] = env.get("MYSQL_ROOT_PASSWORD") or env.get("MARIADB_ROOT_PASSWORD") or ""
        out.setdefault("dbuser", "root")
    return out


def db_engine_from_blob(blob: str, parsed_type: str = "") -> str:
    if parsed_type:
        t = parsed_type.lower()
        if t in ("pgsql", "postgres", "postgresql"):
            return "pgsql"
        if t in ("mysql", "mariadb", "sqlite"):
            return t
    b = blob.lower()
    if "postgres" in b:
        return "pgsql"
    if "mariadb" in b:
        return "mariadb"
    if "mysql" in b:
        return "mysql"
    return parsed_type.lower() or "mysql"


def db_type_label(db_type: str, blob: str = "") -> str:
    t = (db_type or "").lower()
    b = blob.lower()
    if "mariadb" in b or t == "mariadb":
        return "MariaDB"
    if t in ("pgsql", "postgres", "postgresql") or "postgres" in b:
        return "PostgreSQL"
    if t == "sqlite":
        return "SQLite"
    if t == "mysql" or "mysql" in b:
        return "MySQL"
    return "MariaDB"


def is_host_local(dbhost: str) -> bool:
    raw = (dbhost or "").strip()
    if not raw:
        return True
    if raw.startswith("/") or raw.endswith(".sock"):
        return True
    host = raw.split(":")[0].strip().lower()
    return host in HOST_LOCAL_HOSTS


def _score_nc(info: ContainerInfo, has_config: bool) -> tuple:
    name = info.name.lower()
    aio = 1 if AIO_NC in name or AIO_NC in info.image.lower() else 0
    return (
        1 if info.running else 0,
        1 if has_config else 0,
        aio,
        1 if "linuxserver/nextcloud" in info.image.lower() or "linuxserver/nextcloud" in info.blob else 0,
    )


def _find_db_for_nc(
    nc: ContainerInfo,
    containers: list[ContainerInfo],
    dbhost: str,
) -> tuple[ContainerInfo | None, str]:
    """Findet den DB-Container. Rückgabe (info, grund)."""
    host = (dbhost or "").split(":")[0].strip()
    others = [c for c in containers if c.name != nc.name]

    if host and not is_host_local(host):
        host_l = host.lower()
        for c in others:
            names = {c.name.lower(), *(a.lower() for a in c.aliases), c.service.lower()}
            if host_l in names or host_l == c.id.lower() or host in c.ips:
                return c, f"dbhost „{host}“ entspricht Container {c.name}"

    dbs = [c for c in others if is_db_container(c)]
    if not dbs:
        return None, ""

    # AIO-Paar
    if AIO_NC in nc.name.lower() or AIO_NC in nc.image.lower():
        for c in dbs:
            if AIO_DB in c.name.lower() or AIO_DB in c.image.lower():
                return c, f"AIO-Standard: {c.name}"

    project = nc.project
    project_matches = [c for c in dbs if project and c.project == project]
    net_matches = [c for c in dbs if nc.networks and (c.networks & nc.networks)]

    # dbhost als Teil des Namens
    if host and not is_host_local(host):
        host_l = host.lower()
        named = [c for c in dbs if host_l in c.name.lower() or host_l in c.service.lower()]
        if named:
            return named[0], f"Name enthält dbhost „{host}“"

    if len(project_matches) == 1:
        return project_matches[0], f"Compose-Projekt {project}"
    if project_matches:
        running = [c for c in project_matches if c.running]
        pick = running[0] if running else project_matches[0]
        return pick, f"Compose-Projekt {project}"
    if len(net_matches) == 1:
        return net_matches[0], f"gemeinsames Docker-Netz {', '.join(sorted(nc.networks & net_matches[0].networks))}"
    if net_matches:
        running = [c for c in net_matches if c.running]
        pick = running[0] if running else net_matches[0]
        return pick, "gemeinsames Docker-Netz"

    running = [c for c in dbs if c.running]
    if len(running) == 1:
        return running[0], "einziger laufender DB-Container"
    if len(dbs) == 1:
        return dbs[0], "einziger DB-Container"
    return None, ""


def _occ_user_for(info: ContainerInfo) -> str:
    image = info.image.lower()
    if "linuxserver" in image:
        return "abc"
    return "www-data"


def _inner_occ(info: ContainerInfo) -> str:
    by_dest = {m["destination"].rstrip("/"): m for m in info.mounts}
    if "/var/www/html" in by_dest:
        return "/var/www/html/occ"
    if "linuxserver" in info.image.lower() or "/config" in by_dest:
        return "/config/www/nextcloud/occ"
    return "/var/www/html/occ"


def _parse_config_text(text: str) -> dict[str, str]:
    from nc_backup.detect import parse_config_php_text

    return parse_config_php_text(text)


def detect_docker_install(preferred_container: str = "") -> DockerInstall | None:
    """Erkennt eine Docker-Nextcloud. None, wenn Docker fehlt oder nichts gefunden."""
    if not docker_available():
        return None
    containers = _load_candidates()
    ncs = [c for c in containers if is_nc_container(c)]
    if not ncs:
        return None

    running = [c for c in ncs if c.running]
    pool = running or ncs

    if preferred_container:
        for c in ncs:
            if c.name == preferred_container or c.id.startswith(preferred_container):
                pool = [c]
                break

    scored: list[tuple[tuple, ContainerInfo, dict[str, str], str, str, list[str]]] = []
    for c in pool:
        notes: list[str] = []
        folders, config_php, mount_notes = resolve_paths_from_mounts(c.mounts)
        notes.extend(mount_notes)
        parsed: dict[str, str] = {}
        inner = ""
        if config_php:
            try:
                text = Path(config_php).read_text(encoding="utf-8", errors="replace")
                parsed = _parse_config_text(text)
            except OSError:
                parsed = {}
        if not parsed:
            text, inner = read_config_text_from_container(c.name)
            if text:
                parsed = _parse_config_text(text)
                notes.append(f"config.php aus Container gelesen ({inner}).")
        scored.append((_score_nc(c, bool(parsed)), c, parsed, config_php, inner, notes))

    scored.sort(key=lambda item: item[0], reverse=True)
    _score, nc, parsed, config_php, inner, notes = scored[0]

    data_inner = parsed.get("datadirectory") or "/var/www/html/data"
    data_host = map_container_path(data_inner, nc.mounts)
    if not data_host:
        # Fallback: typische Data-Mounts
        folders, _, _ = resolve_paths_from_mounts(nc.mounts)
        for folder in folders:
            if folder.rstrip("/").endswith("/data") or folder.rstrip("/").endswith("/ncdata"):
                data_host = folder
                break
        if not data_host:
            notes.append(
                f"Datenverzeichnis im Container ist {data_inner}, aber kein Host-Volume gefunden. "
                "restic kann die Dateien vom Host nicht sichern, solange das Volume fehlt."
            )

    install_host = ""
    if config_php:
        install_host = str(Path(config_php).parent.parent)
    if not install_host:
        html_host = map_container_path("/var/www/html", nc.mounts)
        if html_host:
            install_host = html_host
    if not install_host:
        cfg_host = map_container_path("/var/www/html/config", nc.mounts)
        if cfg_host:
            install_host = str(Path(cfg_host).parent)

    dbhost = parsed.get("dbhost") or ""
    db_type = db_engine_from_blob(nc.blob, parsed.get("dbtype") or "")
    db_container = ""
    db_same = False
    db_on_host = False
    db_info: ContainerInfo | None = None

    network_mode = (nc.network_mode or "").lower()
    host_net = network_mode in ("host", "ns:host")

    if is_host_local(dbhost):
        if host_net:
            db_on_host = True
            notes.append("Nextcloud-Container nutzt network_mode=host — Datenbank auf dem Host.")
        else:
            # localhost im Container: Dump via docker exec in den NC-Container.
            db_same = True
            db_container = nc.name
            notes.append(
                "dbhost ist localhost — Dump erfolgt im Nextcloud-Container "
                f"({nc.name})."
            )
            other_db, _reason = _find_db_for_nc(nc, containers, "")
            if other_db:
                notes.append(
                    f"Separater DB-Container {other_db.name} wurde gesehen, "
                    "aber dbhost ist localhost — daher nicht verwendet."
                )
    else:
        db_info, reason = _find_db_for_nc(nc, containers, dbhost)
        if db_info:
            db_container = db_info.name
            if reason:
                notes.append(f"DB-Container erkannt: {db_info.name} ({reason}).")
        else:
            notes.append(
                f"dbhost ist „{dbhost}“, aber kein passender DB-Container gefunden. "
                "Bitte den Container-Namen in der Konfiguration eintragen."
            )

    if db_info:
        db_type = db_engine_from_blob(db_info.blob, parsed.get("dbtype") or db_type)
        extra = credentials_from_env(db_info.env, db_type)
        for key, value in extra.items():
            if value and not parsed.get(key):
                parsed[key] = value
                notes.append(f"{key} aus Container-Umgebung übernommen.")
    elif db_same:
        extra = credentials_from_env(nc.env, db_type)
        for key, value in extra.items():
            if value and not parsed.get(key):
                parsed[key] = value

    if not nc.running:
        notes.append(
            f"Nextcloud-Container {nc.name} läuft nicht. Bitte starten, bevor gesichert wird."
        )
    if db_container and db_container != nc.name:
        db_running = any(c.name == db_container and c.running for c in containers)
        if not db_running:
            notes.append(
                f"Datenbank-Container {db_container} läuft nicht. Der Dump schlägt sonst fehl."
            )

    label_blob = db_info.blob if db_info else nc.blob
    return DockerInstall(
        nc_container=nc.name,
        db_container=db_container,
        db_same_container=db_same,
        db_on_host=db_on_host,
        install_dir=install_host,
        data_dir=data_host,
        config_php_path=config_php,
        config_inner=inner or "/var/www/html/config/config.php",
        occ_inner=_inner_occ(nc),
        occ_user=_occ_user_for(nc),
        parsed=parsed,
        notes=notes,
        running=nc.running,
        db_type=db_type,
        db_type_label=db_type_label(db_type, label_blob),
        image=nc.image,
    )


def docker_error_message(exc: BaseException) -> str:
    if isinstance(exc, DockerError):
        return str(exc)
    text = str(exc)
    if _perm_denied(text):
        return (
            "Keine Berechtigung für Docker. Bitte nc-backup als root ausführen "
            "oder den Dienstbenutzer in die Gruppe „docker“ aufnehmen."
        )
    return text
