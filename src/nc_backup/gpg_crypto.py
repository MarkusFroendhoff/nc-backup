"""GPG-Verschlüsselung für Backup-Archive."""

from __future__ import annotations

import shutil
import subprocess
import tarfile
from pathlib import Path

from nc_backup.config_store import AppConfig
from nc_backup.secrets_store import load_gpg_passphrase


class GpgError(RuntimeError):
    pass


def gpg_available() -> bool:
    return shutil.which("gpg") is not None


def _run_gpg(command: list[str], passphrase: str = "") -> None:
    # Optionen muessen VOR -c/-d/-e und dem Dateinamen stehen.
    if passphrase:
        if not command or command[0] != "gpg":
            raise GpgError("Ungültiger GPG-Befehl.")
        command = [
            "gpg",
            "--pinentry-mode", "loopback",
            "--passphrase-fd", "0",
            *command[1:],
        ]
    process = subprocess.run(
        command,
        input=(passphrase + "\n").encode("utf-8") if passphrase else None,
        capture_output=True,
        check=False,
    )
    if process.returncode != 0:
        stderr = process.stderr.decode("utf-8", errors="replace")
        raise GpgError(stderr.strip() or "GPG-Befehl fehlgeschlagen")


def create_tarball(source_dir: Path, archive_path: Path) -> Path:
    if not source_dir.is_dir():
        raise GpgError(f"Backup-Ordner nicht gefunden: {source_dir}")
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive_path, "w:gz") as tar:
        tar.add(source_dir, arcname=source_dir.name)
    return archive_path


def encrypt_archive(
    archive_path: Path,
    output_path: Path,
    *,
    mode: str = "symmetric",
    recipient: str = "",
    passphrase: str = "",
) -> Path:
    if not gpg_available():
        raise GpgError("gpg ist nicht installiert.")

    if mode == "recipient":
        if not recipient:
            raise GpgError("GPG-Empfänger fehlt.")
        command = [
            "gpg",
            "--batch",
            "--yes",
            "--trust-model", "always",
            "-r", recipient,
            "-o", str(output_path),
            "-e",
            str(archive_path),
        ]
        _run_gpg(command)
    else:
        if not passphrase:
            raise GpgError("Verschlüsselungs-Passphrase fehlt.")
        command = [
            "gpg",
            "--batch",
            "--yes",
            "--cipher-algo", "AES256",
            "-o", str(output_path),
            "-c",
            str(archive_path),
        ]
        _run_gpg(command, passphrase=passphrase)
    return output_path


def decrypt_archive(
    encrypted_path: Path,
    output_path: Path,
    *,
    passphrase: str = "",
) -> Path:
    if not gpg_available():
        raise GpgError("gpg ist nicht installiert.")
    if not passphrase:
        raise GpgError("Entschlüsselungs-Passphrase fehlt.")

    command = [
        "gpg",
        "--batch",
        "--yes",
        "-o", str(output_path),
        "-d",
        str(encrypted_path),
    ]
    _run_gpg(command, passphrase=passphrase)
    return output_path


def extract_tarball(archive_path: Path, destination: Path) -> Path:
    destination.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive_path, "r:gz") as tar:
        tar.extractall(path=destination)
    children = [path for path in destination.iterdir() if path.is_dir()]
    if len(children) == 1:
        return children[0]
    if children:
        return children[0]
    raise GpgError("Archiv enthält keinen Backup-Ordner.")


def encrypt_backup_directory(
    backup_dir: Path,
    config: AppConfig,
    passphrase: str | None = None,
) -> Path:
    if not config.encrypt_backups:
        raise GpgError("Verschlüsselung ist deaktiviert.")

    secret = passphrase or load_gpg_passphrase()
    if config.gpg_mode == "symmetric" and not secret:
        raise GpgError("Keine Verschlüsselungs-Passphrase hinterlegt.")

    tar_path = backup_dir.with_suffix(".tar.gz")
    gpg_path = Path(f"{tar_path}.gpg")

    create_tarball(backup_dir, tar_path)
    encrypt_archive(
        tar_path,
        gpg_path,
        mode=config.gpg_mode,
        recipient=config.gpg_recipient,
        passphrase=secret or "",
    )
    tar_path.unlink(missing_ok=True)

    if config.remove_plaintext_after_encrypt:
        shutil.rmtree(backup_dir)

    return gpg_path


def open_encrypted_backup(encrypted_path: Path, passphrase: str, work_dir: Path) -> Path:
    tar_path = work_dir / encrypted_path.name.replace(".gpg", "")
    if tar_path.suffix != ".gz":
        tar_path = work_dir / f"{encrypted_path.stem}.tar.gz"

    decrypt_archive(encrypted_path, tar_path, passphrase=passphrase)
    return extract_tarball(tar_path, work_dir)
