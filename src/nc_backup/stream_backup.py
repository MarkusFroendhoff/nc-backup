"""Direkt-Streaming: Quellen → tar|gzip|gpg auf Ziellaufwerk ohne Pi-Zwischenspeicher."""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path

from nc_backup.config_php import parse_config_php
from nc_backup.config_store import AppConfig
from nc_backup.db_dump import DatabaseDumpError, dump_database
from nc_backup.file_backup import FileBackupError, format_bytes
from nc_backup.gpg_crypto import GpgError, gpg_available
from nc_backup.secrets_store import load_gpg_passphrase

logger = logging.getLogger(__name__)


def _safe_folder_name(source: Path) -> str:
    return source.name or source.as_posix().replace("/", "_")


def _sed_pattern(text: str) -> str:
    return re.escape(text)


def _build_tar_command(
    top_dir: str,
    source_folders: list[str],
    extra_paths: list[tuple[Path, str]],
) -> list[str]:
    """Erstellt tar-Kommando, das Quellordner direkt einliest (ohne rsync-Kopie)."""
    command = ["tar", "-cf", "-"]
    for folder in source_folders:
        source = Path(folder)
        if not source.exists():
            raise FileBackupError(f"Quellordner nicht gefunden: {source}")
        parent = source.parent
        name = source.name
        safe = _safe_folder_name(source)
        transform = f"s,^{_sed_pattern(name)}/,{top_dir}/files/{safe}/,"
        command.extend(["--transform", transform, "-C", str(parent), name])

    for host_path, arc_path in extra_paths:
        if host_path.is_file():
            parent = host_path.parent
            name = host_path.name
            target = f"{top_dir}/{arc_path}/{name}" if arc_path else f"{top_dir}/{name}"
            transform = f"s,^{_sed_pattern(name)}$,{target},"
            command.extend(["--transform", transform, "-C", str(parent), name])
            continue
        parent = host_path.parent
        name = host_path.name
        prefix = f"{top_dir}/{arc_path}" if arc_path else top_dir
        transform = f"s,^{_sed_pattern(name)}/,{prefix}/,"
        command.extend(["--transform", transform, "-C", str(parent), name])

    return command


def run_stream_encrypted_backup(
    config: AppConfig,
    progress_callback=None,
) -> tuple[Path, list[str], str | None, list[str]]:
    """
    Schreibt ein verschlüsseltes .tar.gz.gpg direkt auf export_path.
    Nur DB-Dump und Manifest nutzen kurz /tmp (~ wenige MB/GB).
    """
    if not config.encrypt_backups:
        raise GpgError("Stream-Modus erfordert aktivierte Verschlüsselung.")
    if not gpg_available():
        raise GpgError("gpg ist nicht installiert.")

    export = Path(config.export_path)
    if not export.is_dir():
        raise FileBackupError(f"Export-Pfad existiert nicht: {export}")

    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    top_dir = f"nextcloud-backup_{stamp}"
    archive_name = f"{top_dir}.tar.gz"
    output_path = export / f"{archive_name}.gpg"

    errors: list[str] = []
    database_dump: str | None = None
    files_backed_up = list(config.source_folders)

    def report(percent: int, phase: str, detail: str = "") -> None:
        if progress_callback:
            progress_callback(percent, phase, detail)
        if detail:
            logger.info("%s – %s", phase, detail)

    report(5, "Stream-Backup", f"Ziel: {output_path.name}")

    with tempfile.TemporaryDirectory(prefix="nc-backup-stream-") as tmp:
        tmp_path = Path(tmp)
        extra_paths: list[tuple[Path, str]] = []

        if config.include_database and config.config_php_path:
            report(10, "Datenbank", "Dump nach /tmp (kurzzeitig)…")
            try:
                db_config = parse_config_php(config.config_php_path)
                dump_path = dump_database(
                    db_config,
                    tmp_path / "database",
                    docker_db_container=config.docker_db_container,
                )
                database_dump = f"database/{dump_path.name}"
                extra_paths.append((tmp_path / "database", "database"))
                report(15, "Datenbank", f"Dump bereit: {dump_path.name}")
            except (DatabaseDumpError, FileNotFoundError, ValueError) as exc:
                errors.append(f"Datenbank-Dump: {exc}")
                logger.error("Datenbank-Dump fehlgeschlagen: %s", exc)

        manifest = {
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "install_mode": config.install_mode,
            "source_folders": config.source_folders,
            "export_path": config.export_path,
            "files_backed_up": files_backed_up,
            "folder_mapping": [
                {"source": src, "backup": f"files/{_safe_folder_name(Path(src))}"}
                for src in config.source_folders
            ],
            "database_dump": database_dump,
            "encrypted": True,
            "backup_mode": "stream_encrypted",
            "errors": errors,
        }
        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        extra_paths.append((manifest_path, ""))

        report(20, "Stream-Backup", "tar → gzip → gpg (direkt auf Ziel)…")

        tar_cmd = _build_tar_command(top_dir, config.source_folders, extra_paths)
        gzip_cmd = ["gzip", "-n"]
        gpg_cmd = _build_stream_gpg_command(config, output_path)
        passphrase = ""
        if config.gpg_mode == "symmetric":
            passphrase = load_gpg_passphrase()
            if not passphrase:
                raise GpgError("Keine Verschlüsselungs-Passphrase hinterlegt.")

        passphrase_file: Path | None = None
        try:
            if passphrase:
                passphrase_file = tmp_path / ".gpg-pass"
                passphrase_file.write_text(passphrase + "\n", encoding="utf-8")
                os.chmod(passphrase_file, 0o600)
                yes_idx = gpg_cmd.index("--yes")
                gpg_cmd[yes_idx + 1:yes_idx + 1] = [
                    "--passphrase-file", str(passphrase_file),
                ]

            tar_proc = subprocess.Popen(
                tar_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            gzip_proc = subprocess.Popen(
                gzip_cmd,
                stdin=tar_proc.stdout,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            assert tar_proc.stdout is not None
            tar_proc.stdout.close()

            gpg_proc = subprocess.Popen(
                gpg_cmd,
                stdin=gzip_proc.stdout,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
            assert gzip_proc.stdout is not None
            gzip_proc.stdout.close()

            gzip_stderr = gzip_proc.stderr.read().decode("utf-8", errors="replace") if gzip_proc.stderr else ""
            tar_stderr = tar_proc.stderr.read().decode("utf-8", errors="replace") if tar_proc.stderr else ""
            gpg_stderr = gpg_proc.stderr.read().decode("utf-8", errors="replace") if gpg_proc.stderr else ""

            gzip_code = gzip_proc.wait()
            tar_code = tar_proc.wait()
            gpg_code = gpg_proc.wait()
        finally:
            if passphrase_file and passphrase_file.exists():
                passphrase_file.unlink(missing_ok=True)

        if tar_code != 0:
            raise FileBackupError(tar_stderr.strip() or "tar fehlgeschlagen")
        if gzip_code != 0:
            raise FileBackupError(gzip_stderr.strip() or "gzip fehlgeschlagen")
        if gpg_code != 0:
            output_path.unlink(missing_ok=True)
            raise GpgError(gpg_stderr.strip() or "GPG-Verschlüsselung fehlgeschlagen")

    if not output_path.exists():
        raise GpgError(f"Verschlüsseltes Archiv wurde nicht erstellt: {output_path}")

    size = output_path.stat().st_size
    report(100, "Fertig", f"Stream-Backup: {output_path.name} ({format_bytes(size)})")
    return output_path, files_backed_up, database_dump, errors


def _build_stream_gpg_command(config: AppConfig, output_path: Path) -> list[str]:
    if config.gpg_mode == "recipient":
        if not config.gpg_recipient:
            raise GpgError("GPG-Empfänger fehlt.")
        return [
            "gpg",
            "--batch",
            "--yes",
            "--trust-model", "always",
            "-r", config.gpg_recipient,
            "-o", str(output_path),
            "-e",
        ]

    return [
        "gpg",
        "--batch",
        "--yes",
        "--cipher-algo", "AES256",
        "-o", str(output_path),
        "-c",
    ]
