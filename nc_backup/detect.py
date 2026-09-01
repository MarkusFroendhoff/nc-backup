"""Nextcloud-Installation erkennen (Pfade, config.php, Docker, Webserver-Benutzer)."""

from __future__ import annotations

import pwd
import re
from dataclasses import dataclass, field
from pathlib import Path

from nc_backup.models import AppConfig

COMMON_ROOTS = (
    "/var/www/nextcloud",
    "/var/www/html/nextcloud",
    "/var/www/html",
    "/snap/nextcloud/current/htdocs",
    "/opt/nextcloud",
    "/srv/nextcloud",
    "/usr/share/nextcloud",
)

OCC_USERS = ("www-data", "nginx", "httpd", "www", "apache", "http")

_STR = re.compile(
    r"""['\"](datadirectory|dbhost|dbport|dbname|dbuser|dbpassword|dbtype)['\"]\s*=>\s*['\"]([^'\"]*)['\"]""",
    re.IGNORECASE,
)
_NUM = re.compile(
    r"""['\"](dbport)['\"]\s*=>\s*(\d+)""",
    re.IGNORECASE,
)


@dataclass
class NextcloudDetection:
    install_dir: str = ""
    data_dir: str = ""
    occ_user: str = ""
    occ_user_confident: bool = False
    db_host: str = "localhost"
    db_port: int = 3306
    db_name: str = "nextcloud"
    db_user: str = "nextcloud"
    db_password: str = ""
    db_type: str = "mysql"
    found: bool = False
    config_parsed: bool = False
    candidates: list[str] = field(default_factory=list)
    source: str = "native"
    nc_container: str = ""
    db_container: str = ""
    db_same_container: bool = False
    db_on_host: bool = False
    notes: list[str] = field(default_factory=list)
    docker_image: str = ""
    occ_inner: str = ""
    db_type_label: str = ""


def _looks_like_nc(root: Path) -> bool:
    return (root / "config" / "config.php").is_file() or (root / "occ").is_file()


def find_install_dirs() -> list[Path]:
    found: list[Path] = []
    seen: set[str] = set()

    def add(p: Path) -> None:
        try:
            key = str(p.resolve()) if p.exists() else str(p)
        except OSError:
            key = str(p)
        if key in seen:
            return
        if p.is_dir() and _looks_like_nc(p):
            seen.add(key)
            found.append(p)

    for raw in COMMON_ROOTS:
        add(Path(raw))

    for base in (Path("/var/www"), Path("/var/www/html"), Path("/opt"), Path("/usr/share")):
        if not base.is_dir():
            continue
        try:
            children = list(base.iterdir())
        except OSError:
            continue
        for child in children:
            if (child / "occ").is_file():
                add(child)

    snap = Path("/snap/nextcloud")
    if snap.is_dir():
        try:
            for child in snap.iterdir():
                add(child / "htdocs")
                add(child / "nextcloud")
        except OSError:
            pass

    return found


def parse_config_php_text(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for m in _STR.finditer(text):
        out[m.group(1).lower()] = m.group(2)
    for m in _NUM.finditer(text):
        out[m.group(1).lower()] = m.group(2)
    return out


def parse_config_php(path: Path) -> dict[str, str]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}
    return parse_config_php_text(text)


def detect_occ_user(install_dir: Path) -> tuple[str, bool]:
    """(Benutzername, treffer_sicher) — sicher, wenn der Ordner einem Webserver-Konto gehört."""
    for candidate in (install_dir / "occ", install_dir / "config", install_dir):
        try:
            uid = candidate.stat().st_uid
            name = pwd.getpwuid(uid).pw_name
        except (OSError, KeyError):
            continue
        if name in OCC_USERS:
            return name, True
    for name in OCC_USERS:
        try:
            pwd.getpwnam(name)
            return name, False
        except KeyError:
            continue
    return "", False


def parse_dbhost(raw: str) -> tuple[str, int | None]:
    """Nextcloud-dbhost: Host, Host:Port oder Host:/pfad.sock."""
    raw = (raw or "localhost").strip()
    if not raw:
        return "localhost", None
    if ":" in raw and not raw.startswith("["):
        host_part, _, rest = raw.partition(":")
        if rest.startswith("/") or rest.endswith(".sock"):
            return rest, None
        if rest.isdigit() and host_part:
            return host_part, int(rest)
    if raw.startswith("/") or raw.endswith(".sock"):
        return raw, None
    return raw, None


def _apply_parsed_db(d: NextcloudDetection, parsed: dict[str, str]) -> None:
    if parsed.get("dbname"):
        d.db_name = parsed["dbname"]
    if parsed.get("dbuser"):
        d.db_user = parsed["dbuser"]
    if "dbpassword" in parsed:
        d.db_password = parsed["dbpassword"]
    if parsed.get("dbtype"):
        d.db_type = parsed["dbtype"].lower()
    host, port_from_host = parse_dbhost(parsed.get("dbhost", "localhost"))
    d.db_host = host
    if parsed.get("dbport", "").isdigit():
        d.db_port = int(parsed["dbport"])
    elif port_from_host:
        d.db_port = port_from_host
    elif d.db_type in ("pgsql", "postgres", "postgresql") and d.db_port == 3306:
        d.db_port = 5432


def inspect_install(root: Path) -> NextcloudDetection:
    d = NextcloudDetection()
    d.install_dir = str(root)
    d.found = _looks_like_nc(root)
    d.data_dir = str(root / "data")
    d.source = "native"

    cfg_php = root / "config" / "config.php"
    parsed = parse_config_php(cfg_php) if cfg_php.is_file() else {}
    if parsed:
        d.config_parsed = True
        if parsed.get("datadirectory"):
            d.data_dir = parsed["datadirectory"]
        _apply_parsed_db(d, parsed)

    user, confident = detect_occ_user(root)
    d.occ_user = user or "www-data"
    d.occ_user_confident = bool(user) and confident
    return d


def _from_docker(install) -> NextcloudDetection:
    d = NextcloudDetection()
    d.source = "docker"
    d.found = True
    d.nc_container = install.nc_container
    d.db_container = install.db_container
    d.db_same_container = install.db_same_container
    d.db_on_host = install.db_on_host
    d.install_dir = install.install_dir
    d.data_dir = install.data_dir
    d.docker_image = install.image
    d.occ_inner = install.occ_inner
    d.notes = list(install.notes)
    d.db_type = install.db_type or "mysql"
    d.db_type_label = install.db_type_label
    d.occ_user = install.occ_user or "www-data"
    d.occ_user_confident = False
    parsed = install.parsed or {}
    if parsed:
        d.config_parsed = True
        _apply_parsed_db(d, parsed)
        if parsed.get("datadirectory") and install.data_dir:
            d.data_dir = install.data_dir
    if install.install_dir:
        user, confident = detect_occ_user(Path(install.install_dir))
        if user and confident:
            d.occ_user = user
            d.occ_user_confident = True
    if install.config_php_path and not d.install_dir:
        d.install_dir = str(Path(install.config_php_path).parent.parent)
    return d


def _try_docker() -> tuple[NextcloudDetection | None, str]:
    try:
        from nc_backup.docker_detect import DockerError, detect_docker_install, docker_available
    except ImportError:
        return None, ""
    if not docker_available():
        return None, ""
    try:
        install = detect_docker_install()
    except DockerError as exc:
        return None, str(exc)
    except OSError as exc:
        return None, str(exc)
    if install is None:
        return None, ""
    return _from_docker(install), ""


def detect_nextcloud(preferred: str | None = None) -> NextcloudDetection:
    candidates = find_install_dirs()
    native: NextcloudDetection | None = None
    if preferred:
        p = Path(preferred)
        if p.is_dir():
            native = inspect_install(p)
    if native is None and candidates:
        native = inspect_install(candidates[0])

    docker_det, docker_note = _try_docker()

    native_ok = bool(native and native.found and native.config_parsed)
    docker_ok = bool(docker_det and docker_det.found and docker_det.config_parsed)
    native_found = bool(native and native.found)
    docker_found = bool(docker_det and docker_det.found)

    # Native mit echter config.php gewinnt; sonst Docker/AIO; sonst native ohne config.
    if preferred and native and native.found:
        chosen = native
    elif native_ok:
        chosen = native
    elif docker_ok or (docker_found and not native_found):
        chosen = docker_det
    elif native_found:
        chosen = native
    elif docker_found:
        chosen = docker_det
    else:
        chosen = NextcloudDetection()
        if docker_note:
            chosen.notes.append(docker_note)

    assert chosen is not None
    chosen.candidates = [str(p) for p in candidates]
    if docker_det and docker_det.install_dir and docker_det.install_dir not in chosen.candidates:
        chosen.candidates.append(docker_det.install_dir)
    if chosen.install_dir and chosen.install_dir not in chosen.candidates and chosen.found:
        chosen.candidates.insert(0, chosen.install_dir)
    if docker_note and docker_note not in chosen.notes:
        chosen.notes.append(docker_note)
    return chosen


def apply_detection(cfg: AppConfig, det: NextcloudDetection) -> None:
    if det.install_dir:
        cfg.nextcloud.install_dir = det.install_dir
    if det.data_dir:
        cfg.nextcloud.data_dir = det.data_dir
    if det.occ_user:
        cfg.nextcloud.occ_user = det.occ_user
    cfg.nextcloud.container = det.nc_container or ""
    if det.occ_inner:
        cfg.nextcloud.occ_inner = det.occ_inner
    if det.config_parsed:
        cfg.database.host = det.db_host
        cfg.database.port = det.db_port
        cfg.database.name = det.db_name
        cfg.database.user = det.db_user
        if det.db_password:
            cfg.database.password = det.db_password
        if det.db_type:
            cfg.database.type = det.db_type
    cfg.database.container = det.db_container or ""
    if det.db_on_host:
        cfg.database.container = ""


def _db_label(det: NextcloudDetection) -> str:
    if det.db_type_label:
        return det.db_type_label
    t = (det.db_type or "").lower()
    if t in ("pgsql", "postgres", "postgresql"):
        return "PostgreSQL"
    if t == "mariadb":
        return "MariaDB"
    if t == "sqlite":
        return "SQLite"
    if t == "mysql":
        return "MySQL"
    return "MariaDB"


def detection_summary(det: NextcloudDetection) -> str:
    if not det.found:
        if det.notes:
            return "Es wurde keine Nextcloud-Installation gefunden. " + " ".join(det.notes)
        return "Es wurde keine Nextcloud-Installation gefunden."
    if det.source == "docker" and det.nc_container:
        parts = [f"Nextcloud in Docker (Container {det.nc_container})."]
        if det.data_dir:
            parts.append(f"Daten: {det.data_dir}.")
        else:
            parts.append("Daten: Host-Pfad unbekannt (Volume nicht gemountet).")
        if det.db_same_container or (det.db_container and det.db_container == det.nc_container):
            parts.append("Datenbank im selben Container.")
        elif det.db_on_host or not det.db_container:
            if det.db_on_host or (det.db_host in ("localhost", "127.0.0.1", "::1") and not det.db_container):
                parts.append("Datenbank auf dem Host.")
            else:
                parts.append(f"Datenbank: {det.db_host} (kein Container erkannt).")
        else:
            parts.append(f"Datenbank: Container {det.db_container} ({_db_label(det)}).")
        return " ".join(parts)
    install = det.install_dir or ""
    bits = [f"Nextcloud gefunden unter {install}."]
    if det.data_dir:
        bits.append(f"Datenverzeichnis: {det.data_dir}.")
    if det.config_parsed:
        bits.append("Angaben kommen aus config.php.")
    return " ".join(bits)


def detection_public_dict(det: NextcloudDetection | None = None) -> dict:
    """Web/Installer-JSON ohne Datenbankpasswort."""
    if det is None:
        det = detect_nextcloud()
    found = bool(det.found)
    install = det.install_dir or ""
    return {
        "found": found,
        "install_dir": install,
        "data_dir": det.data_dir or "",
        "dbhost": det.db_host,
        "dbport": det.db_port,
        "dbname": det.db_name,
        "dbuser": det.db_user,
        "dbtype": det.db_type,
        "occ_user": det.occ_user,
        "config_parsed": det.config_parsed,
        "candidates": list(det.candidates),
        "source": det.source,
        "nc_container": det.nc_container,
        "db_container": det.db_container,
        "notes": list(det.notes),
        "summary": detection_summary(det),
    }


def apply_detected_defaults(config_path: Path | str | None = None) -> dict:
    """Schreibt erkannte Werte nur, wenn config.yaml noch die Standardwerte hat."""
    from nc_backup.config_store import load_config, save_config, config_path as default_path

    det = detect_nextcloud()
    info = detection_public_dict(det)
    info["applied"] = False
    if not det.found:
        return info

    target = Path(config_path) if config_path else default_path()
    cfg = load_config() if config_path is None else None
    if cfg is None:
        import yaml
        if target.is_file():
            data = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
            cfg = AppConfig.from_dict(data)
        else:
            cfg = AppConfig()

    default_install = cfg.nextcloud.install_dir in ("", "/var/www/nextcloud")
    default_data = cfg.nextcloud.data_dir in ("", "/var/www/nextcloud/data")
    changed = False
    if default_install:
        apply_detection(cfg, det)
        changed = True
    else:
        if default_data and det.data_dir:
            cfg.nextcloud.data_dir = det.data_dir
            changed = True
        if cfg.nextcloud.occ_user in ("", "www-data") and det.occ_user:
            cfg.nextcloud.occ_user = det.occ_user
            changed = True
        if not cfg.nextcloud.container and det.nc_container:
            cfg.nextcloud.container = det.nc_container
            if det.occ_inner:
                cfg.nextcloud.occ_inner = det.occ_inner
            changed = True
        if cfg.database.name in ("", "nextcloud") and det.config_parsed:
            cfg.database.host = det.db_host
            cfg.database.port = det.db_port
            cfg.database.name = det.db_name
            cfg.database.user = det.db_user
            if det.db_type:
                cfg.database.type = det.db_type
            changed = True
        if not cfg.database.container and det.db_container and not det.db_on_host:
            cfg.database.container = det.db_container
            changed = True
        if not cfg.database.password and det.db_password:
            cfg.database.password = det.db_password
            changed = True

    if changed:
        save_config(cfg, target if config_path else None)
        info["applied"] = True
        info["summary"] = detection_summary(det).rstrip(".") + " — Angaben wurden übernommen."
    else:
        info["summary"] = (
            detection_summary(det).rstrip(".") + " — bestehende Konfiguration belassen."
        )
    return info


def needs_setup(cfg: AppConfig) -> bool:
    """Ersteinrichtung, wenn noch Beispielwerte und kein Restic-Passwort."""
    dest = cfg.destination
    nc = cfg.nextcloud
    default_install = nc.install_dir in ("", "/var/www/nextcloud")
    default_repo = dest.local_path in ("", "/var/backups/nextcloud/restic-repo")
    no_pw = not (dest.restic_password or "").strip()
    return no_pw and default_install and default_repo
