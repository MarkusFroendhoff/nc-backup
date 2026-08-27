"""Subprocess-Hilfen."""

from __future__ import annotations

import subprocess
from collections.abc import Sequence

from nc_backup.logutil import log, log_error


def run(
    cmd: Sequence[str],
    *,
    env: dict[str, str] | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    log(f"$ {' '.join(cmd)}")
    result = subprocess.run(
        cmd,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.stdout:
        for line in result.stdout.strip().splitlines():
            log(line)
    if result.stderr:
        for line in result.stderr.strip().splitlines():
            log(line)
    if check and result.returncode != 0:
        log_error(f"Befehl fehlgeschlagen (Exit {result.returncode})")
        raise subprocess.CalledProcessError(result.returncode, cmd, result.stdout, result.stderr)
    return result


def which(name: str) -> str | None:
    from shutil import which as _which

    return _which(name)
