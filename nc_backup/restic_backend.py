"""Inkrementelle Backups mit Restic."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from nc_backup.logutil import log
from nc_backup.models import AppConfig, Provider
from nc_backup.runner import run, which

# Feste Pfade, damit Restic Parent-Snapshots erkennt (kein /tmp/nc-backup-* pro Lauf).
STAGING_ROOT = Path("/var/lib/nc-backup/staging")
# Einzeldatei-Export: nie in die laufende Nextcloud schreiben.
_DEFAULT_EXPORT_ROOT = Path("/var/lib/nc-backup/exports")
_SNAPSHOT_ID_RE = re.compile(r"^[A-Fa-f0-9]{8,64}$")
_GLOB_CHARS_RE = re.compile(r"[*?\[\]{}]")


@dataclass
class SnapshotInfo:
    id: str
    short_id: str
    time: str
    hostname: str
    tags: list[str]


@dataclass
class SnapshotNode:
    path: str
    name: str
    type: str
    size: int | None = None


def export_root() -> Path:
    raw = (os.environ.get("NC_BACKUP_EXPORT_ROOT") or "").strip()
    return Path(raw) if raw else _DEFAULT_EXPORT_ROOT


def validate_snapshot_id(raw: str) -> str:
    sid = (raw or "").strip()
    if not _SNAPSHOT_ID_RE.fullmatch(sid):
        raise ValueError("Ungültige Sicherungspunkt-ID.")
    return sid


def normalize_snapshot_path(raw: str) -> str:
    """Absoluter POSIX-Pfad ohne '..'; für restic ls/restore --include."""
    text = (raw or "").strip()
    if not text:
        raise ValueError("Kein Dateipfad angegeben.")
    if "\x00" in text:
        raise ValueError("Ungültiger Pfad.")
    if _GLOB_CHARS_RE.search(text):
        raise ValueError("Pfad darf keine Suchzeichen wie * oder ? enthalten.")
    if not text.startswith("/"):
        text = "/" + text
    parts: list[str] = []
    for part in text.split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            raise ValueError("Pfad darf keine '..'-Bestandteile enthalten.")
        parts.append(part)
    return "/" + "/".join(parts)


def parent_snapshot_path(path: str) -> str | None:
    norm = normalize_snapshot_path(path)
    if norm == "/":
        return None
    parent = str(Path(norm).parent)
    return parent if parent.startswith("/") else "/" + parent


def _is_ls_node(item: dict) -> bool:
    if not isinstance(item, dict):
        return False
    msg = str(item.get("message_type") or item.get("struct_type") or "")
    if msg == "snapshot":
        return False
    if "path" not in item:
        return False
    kind = str(item.get("type") or "")
    return kind in ("file", "dir", "symlink")


def parse_ls_json(stdout: str) -> list[SnapshotNode]:
    """restic ls --json: NDJSON, erstes Objekt oft der Snapshot."""
    nodes: list[SnapshotNode] = []
    for line in (stdout or "").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not _is_ls_node(item):
            continue
        path = str(item.get("path") or "")
        if not path:
            continue
        name = str(item.get("name") or Path(path).name or path)
        kind = str(item.get("type") or "file")
        if kind == "symlink":
            kind = "file"
        size_raw = item.get("size")
        size = int(size_raw) if isinstance(size_raw, int) else None
        nodes.append(SnapshotNode(path=path, name=name, type=kind, size=size))
    return nodes


def parse_find_json(stdout: str) -> list[SnapshotNode]:
    """restic find --json: ein JSON-Array, gruppiert nach Snapshot."""
    text = (stdout or "").strip()
    if not text:
        return []
    try:
        raw = json.loads(text)
    except json.JSONDecodeError:
        return parse_ls_json(text)
    groups: list[dict]
    if isinstance(raw, list):
        groups = [g for g in raw if isinstance(g, dict)]
    elif isinstance(raw, dict):
        groups = [raw]
    else:
        return []
    nodes: list[SnapshotNode] = []
    seen: set[str] = set()
    for group in groups:
        matches = group.get("matches")
        if not isinstance(matches, list):
            continue
        for item in matches:
            if not isinstance(item, dict):
                continue
            path = str(item.get("path") or "")
            if not path or path in seen:
                continue
            seen.add(path)
            name = str(item.get("name") or Path(path).name or path)
            kind = str(item.get("type") or "file")
            if kind == "symlink":
                kind = "file"
            if kind not in ("file", "dir"):
                kind = "file"
            size_raw = item.get("size")
            size = int(size_raw) if isinstance(size_raw, int) else None
            nodes.append(SnapshotNode(path=path, name=name, type=kind, size=size))
    return nodes


def _immediate_children(nodes: list[SnapshotNode], prefix: str) -> list[SnapshotNode]:
    root = prefix.rstrip("/") or ""
    children: dict[str, SnapshotNode] = {}
    for node in nodes:
        path = node.path.rstrip("/")
        if root:
            if path == root:
                continue
            base = root + "/"
            if not path.startswith(base):
                continue
            rest = path[len(base) :]
        else:
            rest = path.lstrip("/")
        if not rest:
            continue
        first = rest.split("/", 1)[0]
        child_path = f"{root}/{first}" if root else "/" + first
        deeper = "/" in rest
        kind = "dir" if deeper or node.type == "dir" else node.type
        size = None if kind == "dir" else node.size
        prev = children.get(child_path)
        if prev is None or (prev.type != "dir" and kind == "dir"):
            children[child_path] = SnapshotNode(
                path=child_path,
                name=first,
                type=kind,
                size=size,
            )
    return _sort_nodes(list(children.values()))


def _sort_nodes(nodes: list[SnapshotNode]) -> list[SnapshotNode]:
    return sorted(nodes, key=lambda n: (0 if n.type == "dir" else 1, n.name.casefold(), n.path))


def _sanitize_find_query(raw: str) -> str:
    text = (raw or "").strip()
    if not text:
        raise ValueError("Bitte einen Suchbegriff eingeben.")
    cleaned = _GLOB_CHARS_RE.sub("", text).strip()
    if not cleaned:
        raise ValueError("Bitte einen Suchbegriff ohne * ? [ ] eingeben.")
    return cleaned


def _live_nextcloud_roots(cfg: AppConfig) -> list[Path]:
    roots: list[Path] = []
    for raw in (cfg.nextcloud.data_dir, cfg.nextcloud.install_dir):
        text = (raw or "").strip()
        if not text:
            continue
        path = Path(text)
        try:
            roots.append(path.resolve())
        except OSError:
            roots.append(path)
    return roots


def ensure_export_target(cfg: AppConfig, target: Path) -> Path:
    """Zielordner anlegen und prüfen, dass er nicht in der Live-Nextcloud liegt."""
    root = export_root()
    root.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(root, 0o700)
    except OSError:
        pass
    resolved_root = root.resolve()
    target.mkdir(parents=True, exist_ok=True)
    resolved = target.resolve()
    if not resolved.is_relative_to(resolved_root):
        raise ValueError("Export-Pfad liegt nicht im sicheren Export-Ordner.")
    for live in _live_nextcloud_roots(cfg):
        if resolved.is_relative_to(live) or resolved_root.is_relative_to(live):
            raise ValueError(
                "Einzeldateien dürfen nicht in die laufende Nextcloud geschrieben werden."
            )
    return resolved


def resolve_export_file(raw: str) -> Path:
    """Nur Dateien unter dem Export-Ordner (für Download)."""
    text = (raw or "").strip()
    if not text:
        raise ValueError("Kein Export-Pfad angegeben.")
    path = Path(text)
    if not path.is_absolute():
        path = export_root() / path
    resolved = path.resolve()
    root = export_root().resolve()
    if not resolved.is_relative_to(root):
        raise ValueError("Download nur aus dem Export-Ordner erlaubt.")
    if not resolved.is_file():
        raise ValueError("Die Datei liegt nicht (mehr) im Export-Ordner.")
    return resolved


def _restic_ls_find(
    cfg: AppConfig,
    snapshot_id: str,
    args: list[str],
    *,
    timeout: int = 60,
) -> str:
    if which("restic") is None:
        raise RuntimeError("restic nicht installiert")
    env = _restic_env(cfg)
    try:
        proc = subprocess.run(
            ["restic", *args],
            env=env,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("Zeitüberschreitung beim Lesen der Sicherung.") from exc
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "restic-Befehl fehlgeschlagen").strip()
        raise RuntimeError(err.splitlines()[-1] if err else "restic-Befehl fehlgeschlagen")
    return proc.stdout or ""


def list_snapshot_paths(
    cfg: AppConfig,
    snapshot_id: str,
    *,
    prefix: str = "",
    search: str = "",
    limit: int = 200,
) -> tuple[str, list[SnapshotNode]]:
    """Dateien/Ordner in einem Snapshot. Ohne Suche nur die direkte Ebene."""
    sid = validate_snapshot_id(snapshot_id)
    query = (search or "").strip()
    if query:
        needle = _sanitize_find_query(query)
        stdout = _restic_ls_find(
            cfg,
            sid,
            ["find", "--json", "--ignore-case", "--snapshot", sid, "--", f"*{needle}*"],
            timeout=90,
        )
        nodes = parse_find_json(stdout)
        if prefix:
            base = normalize_snapshot_path(prefix).rstrip("/")
            nodes = [
                n
                for n in nodes
                if n.path.rstrip("/") == base or n.path.startswith(base + "/")
            ]
        nodes = _sort_nodes(nodes)[: max(1, min(limit, 500))]
        current = normalize_snapshot_path(prefix) if prefix else (
            str(Path(cfg.nextcloud.data_dir).as_posix()) if cfg.nextcloud.data_dir else "/"
        )
        return current, nodes

    current = normalize_snapshot_path(prefix) if prefix else (
        str(Path((cfg.nextcloud.data_dir or "/").rstrip("/") or "/").as_posix())
    )
    if current != "/":
        current = current.rstrip("/") or "/"
    ls_dir = current if current != "/" else "/"
    try:
        stdout = _restic_ls_find(cfg, sid, ["ls", "--json", sid, ls_dir], timeout=60)
    except RuntimeError:
        if prefix or current == "/":
            raise
        current = "/"
        stdout = _restic_ls_find(cfg, sid, ["ls", "--json", sid, "/"], timeout=60)
    nodes = parse_ls_json(stdout)
    children = _immediate_children(nodes, current if current != "/" else "")
    return current, children[: max(1, min(limit, 500))]


def restored_path_under_target(target: Path, include_path: str) -> Path:
    rel = include_path.lstrip("/")
    return (target / rel).resolve()


def restore_include_path(
    cfg: AppConfig,
    snapshot_id: str,
    include_path: str,
    *,
    is_dir: bool = False,
) -> Path:
    """Nur include_path per restic restore --include in den Export-Ordner holen."""
    sid = validate_snapshot_id(snapshot_id)
    include = normalize_snapshot_path(include_path)
    live_data = (cfg.nextcloud.data_dir or "").rstrip("/")
    live_install = (cfg.nextcloud.install_dir or "").rstrip("/")
    if live_data and include.rstrip("/") == live_data:
        raise ValueError(
            "Bitte eine einzelne Datei oder einen Unterordner wählen, "
            "nicht das ganze Datenverzeichnis."
        )
    if live_install and include.rstrip("/") == live_install:
        raise ValueError(
            "Bitte eine einzelne Datei wählen, nicht die ganze Nextcloud-Installation."
        )

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(include).name)[:80] or "datei"
    target = export_root() / f"{stamp}-{sid[:8]}-{safe_name}"
    resolved_target = ensure_export_target(cfg, target)

    env = _restic_env(cfg)
    cmd = [
        "restic",
        "restore",
        sid,
        "--target",
        str(resolved_target),
        "--include",
        include,
    ]
    if is_dir:
        cmd.extend(["--include", include.rstrip("/") + "/**"])
    log(f"Restic restore {sid[:12]} --include {include} → {resolved_target}")
    run(cmd, env=env)

    restored = restored_path_under_target(resolved_target, include)
    if not restored.is_relative_to(resolved_target):
        raise RuntimeError("Wiederhergestellter Pfad liegt außerhalb des Export-Ordners.")
    if not restored.exists():
        found: list[Path] = []
        for child in resolved_target.rglob("*"):
            if child.is_file() or child.is_dir():
                found.append(child)
                if len(found) > 20:
                    break
        if len(found) == 1:
            restored = found[0]
        elif found:
            files = [p for p in found if p.is_file()]
            restored = files[0] if len(files) == 1 else resolved_target
        else:
            raise FileNotFoundError(
                f"Pfad {include} wurde im Sicherungspunkt nicht gefunden."
            )
    log(f"Datei liegt unter {restored}")
    return restored


def _restic_env(cfg: AppConfig) -> dict[str, str]:
    dest = cfg.destination
    env = os.environ.copy()
    pw = dest.restic_password
    if not pw:
        raise ValueError("Restic-Passwort fehlt (Repository-Verschlüsselung)")
    env["RESTIC_PASSWORD"] = pw

    repo = repository_url(cfg)
    env["RESTIC_REPOSITORY"] = repo

    if dest.provider == Provider.S3:
        env["AWS_ACCESS_KEY_ID"] = dest.s3_access_key
        env["AWS_SECRET_ACCESS_KEY"] = dest.s3_secret_key
        if dest.s3_region:
            env["AWS_DEFAULT_REGION"] = dest.s3_region
    elif dest.provider == Provider.AZURE:
        env["AZURE_ACCOUNT_NAME"] = dest.azure_account
        env["AZURE_ACCOUNT_KEY"] = dest.azure_key
    elif dest.provider == Provider.B2:
        env["B2_ACCOUNT_ID"] = dest.b2_account_id
        env["B2_ACCOUNT_KEY"] = dest.b2_account_key

    if dest.provider == Provider.SFTP and dest.sftp_password:
        env["SSHPASS"] = dest.sftp_password

    return env


def repository_url(cfg: AppConfig) -> str:
    d = cfg.destination
    p = d.provider
    if p in (Provider.WEBDAV, Provider.RCLONE):
        Path(d.local_path).mkdir(parents=True, exist_ok=True)
        return str(Path(d.local_path).resolve())
    if p == Provider.LOCAL:
        Path(d.local_path).mkdir(parents=True, exist_ok=True)
        return str(Path(d.local_path).resolve())
    if p == Provider.SFTP:
        port = f":{d.sftp_port}" if d.sftp_port != 22 else ""
        return f"sftp:{d.sftp_user}@{d.sftp_host}{port}:{d.sftp_path}"
    if p == Provider.S3:
        prefix = d.s3_prefix.strip("/")
        path = f"{d.s3_bucket}/{prefix}" if prefix else d.s3_bucket
        return f"s3:{d.s3_endpoint}/{path}"
    if p == Provider.AZURE:
        return f"azure:{d.azure_container}/{d.azure_prefix}"
    if p == Provider.B2:
        return f"b2:{d.b2_bucket}/{d.b2_prefix}"
    raise ValueError(f"Provider {p.value} nutzt kein Restic-Repository direkt")


def ensure_repository(cfg: AppConfig) -> None:
    if which("restic") is None:
        raise RuntimeError("restic nicht installiert — siehe README")
    env = _restic_env(cfg)
    snapshots = run(["restic", "snapshots"], env=env, check=False)
    if snapshots.returncode == 0:
        return
    log("Restic-Repository wird initialisiert …")
    run(["restic", "init"], env=env)


def list_snapshots(cfg: AppConfig) -> list[SnapshotInfo]:
    if which("restic") is None:
        raise RuntimeError("restic nicht installiert")
    env = _restic_env(cfg)
    proc = subprocess.run(
        ["restic", "snapshots", "--json"],
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    raw = json.loads(proc.stdout or "[]")
    result: list[SnapshotInfo] = []
    for item in raw:
        result.append(
            SnapshotInfo(
                id=item["id"],
                short_id=item["short_id"],
                time=item["time"],
                hostname=item.get("hostname", ""),
                tags=item.get("tags") or [],
            )
        )
    result.sort(key=lambda s: s.time, reverse=True)
    return result


def restore_snapshot(cfg: AppConfig, snapshot_id: str, target: Path) -> None:
    env = _restic_env(cfg)
    target.mkdir(parents=True, exist_ok=True)
    log(f"Restic restore {snapshot_id} → {target}")
    run(["restic", "restore", snapshot_id, "--target", str(target)], env=env)


def _prepare_staging_dirs() -> tuple[Path, Path]:
    if STAGING_ROOT.exists():
        shutil.rmtree(STAGING_ROOT)
    db_dir = STAGING_ROOT / "database"
    cfg_dir = STAGING_ROOT / "config"
    db_dir.mkdir(parents=True)
    cfg_dir.mkdir(parents=True)
    return db_dir, cfg_dir


def _latest_snapshot_id(env: dict[str, str]) -> str | None:
    """Neueste Snapshot-ID, ohne Pfad-Filter (restic 'latest' verlangt gleiche Pfade)."""
    snapshots = run(["restic", "snapshots", "--json"], env=env, check=False)
    if snapshots.returncode != 0:
        return None
    try:
        raw = json.loads(snapshots.stdout or "[]")
    except json.JSONDecodeError:
        return None
    if not isinstance(raw, list) or not raw:
        return None
    raw.sort(key=lambda s: str(s.get("time") or ""), reverse=True)
    sid = raw[0].get("id") or raw[0].get("short_id")
    return str(sid) if sid else None


def backup_paths(cfg: AppConfig, paths: list[Path], tag: str) -> None:
    env = _restic_env(cfg)
    cmd = [
        "restic",
        "backup",
        "--tag",
        tag,
        "--host",
        os.uname().nodename,
    ]
    parent = _latest_snapshot_id(env)
    if parent:
        cmd.extend(["--parent", parent])
        log(f"Restic-Parent: {parent[:12]}")
    cmd.extend(str(p) for p in paths)
    run(cmd, env=env)
    _apply_retention(cfg, env)


def _apply_retention(cfg: AppConfig, env: dict[str, str]) -> None:
    r = cfg.destination.retention
    cmd = [
        "restic",
        "forget",
        "--prune",
        "--keep-daily",
        str(r.keep_daily),
        "--keep-weekly",
        str(r.keep_weekly),
        "--keep-monthly",
        str(r.keep_monthly),
    ]
    run(cmd, env=env)
    log("Aufbewahrungsregeln angewendet.")


def run_incremental_backup(cfg: AppConfig) -> None:
    """Staging mit DB + Config, Restic-Backup inkl. Datenverzeichnis."""
    ensure_repository(cfg)
    stamp = __import__("datetime").datetime.now().strftime("%Y%m%d-%H%M%S")
    db_dir, cfg_dir = _prepare_staging_dirs()

    from nc_backup.mariadb import dump_database

    dump_database(cfg, db_dir / "nextcloud.sql")

    nc_config = Path(cfg.nextcloud.install_dir) / "config"
    if nc_config.is_dir():
        shutil.copytree(nc_config, cfg_dir / "config", dirs_exist_ok=True)
    else:
        container = (getattr(cfg.nextcloud, "container", "") or "").strip()
        if container:
            from nc_backup.docker_detect import copy_config_from_container

            if copy_config_from_container(container, cfg_dir / "config"):
                log(f"config/ aus Container {container} kopiert.")
            else:
                log(
                    "config/ liegt nicht auf dem Host und konnte nicht "
                    f"aus dem Container {container} kopiert werden."
                )

    paths = [db_dir, cfg_dir, Path(cfg.nextcloud.data_dir)]
    backup_paths(cfg, paths, tag=f"nc-backup-{stamp}")
    log(f"Inkrementelles Backup abgeschlossen (Snapshot-Tag: nc-backup-{stamp}).")
