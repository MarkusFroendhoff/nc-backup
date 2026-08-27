"""Root-Operationen via pkexec (blockiert nicht selbst — Aufrufer im Thread)."""

from __future__ import annotations

import json
import subprocess
import tempfile
from collections.abc import Callable
from pathlib import Path

LineCb = Callable[[str], None]


def _pkexec_python(
    py_code: str,
    extra_cleanup: Path | None = None,
    on_output: LineCb | None = None,
) -> tuple[bool, str]:
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as py:
        py.write(py_code)
        py_path = py.name

    with tempfile.NamedTemporaryFile("w", suffix=".sh", delete=False, encoding="utf-8") as sh:
        sh.write(f"#!/bin/sh\nset -e\npython3 '{py_path}'\n")
        sh_path = sh.name
    Path(sh_path).chmod(0o755)

    try:
        if on_output is None:
            r = subprocess.run(["pkexec", "bash", sh_path], capture_output=True, text=True)
            out = (r.stdout or "") + (r.stderr or "")
            ok = r.returncode == 0
            return ok, out.strip() or ("OK" if ok else "Abgebrochen oder keine Berechtigung")

        proc = subprocess.Popen(
            ["pkexec", "bash", sh_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        chunks: list[str] = []
        assert proc.stdout is not None
        for line in proc.stdout:
            chunks.append(line)
            on_output(line.rstrip("\n"))
        rc = proc.wait()
        out = "".join(chunks)
        ok = rc == 0
        return ok, out.strip() or ("OK" if ok else "Abgebrochen oder keine Berechtigung")
    finally:
        Path(py_path).unlink(missing_ok=True)
        Path(sh_path).unlink(missing_ok=True)
        if extra_cleanup:
            extra_cleanup.unlink(missing_ok=True)


def save_config_as_admin(yaml_path: Path, on_output: LineCb | None = None) -> tuple[bool, str]:
    code = f"""
import yaml
from pathlib import Path
from nc_backup.config_store import save_config
from nc_backup.models import AppConfig

data = yaml.safe_load(Path({repr(str(yaml_path))}).read_text(encoding='utf-8'))
save_config(AppConfig.from_dict(data or {{}}))
print('Konfiguration gespeichert.')
"""
    return _pkexec_python(code, extra_cleanup=yaml_path, on_output=on_output)


def run_backup_as_admin(on_output: LineCb | None = None) -> tuple[bool, str]:
    code = """
from nc_backup.engine import run_backup
import sys
sys.exit(run_backup())
"""
    return _pkexec_python(code, on_output=on_output)


def install_timer_as_admin(yaml_path: Path, on_output: LineCb | None = None) -> tuple[bool, str]:
    code = f"""
import yaml
from pathlib import Path
from nc_backup.config_store import save_config
from nc_backup.models import AppConfig
from nc_backup.scheduler import apply_schedule
import subprocess

data = yaml.safe_load(Path({repr(str(yaml_path))}).read_text(encoding='utf-8'))
cfg = AppConfig.from_dict(data or {{}})
save_config(cfg)
apply_schedule(cfg)
subprocess.run(['systemctl', 'daemon-reload'], check=True)
if cfg.schedule.enabled:
    subprocess.run(['systemctl', 'enable', '--now', 'nc-backup.timer'], check=True)
    print('Timer aktiviert.')
else:
    subprocess.run(['systemctl', 'disable', '--now', 'nc-backup.timer'], check=False)
    print('Timer deaktiviert.')
"""
    return _pkexec_python(code, extra_cleanup=yaml_path, on_output=on_output)


def list_snapshots_as_admin(on_output: LineCb | None = None) -> tuple[bool, str, list[dict]]:
    code = """
import json
from nc_backup.config_store import load_config
from nc_backup.restore import get_snapshots
snaps = get_snapshots(load_config())
print(json.dumps([s.__dict__ for s in snaps]))
"""
    ok, out = _pkexec_python(code, on_output=on_output)
    if not ok:
        return ok, out, []
    try:
        line = out.strip().splitlines()[-1] if out else "[]"
        return True, out, json.loads(line)
    except json.JSONDecodeError:
        return False, out, []


def restore_as_admin(
    snapshot_id: str,
    *,
    database: bool,
    config: bool,
    data: bool,
    on_output: LineCb | None = None,
) -> tuple[bool, str]:
    code = f"""
from nc_backup.config_store import load_config
from nc_backup.restore import RestoreOptions, run_restore
opts = RestoreOptions(
    snapshot_id={snapshot_id!r},
    restore_database={database},
    restore_config={config},
    restore_data={data},
)
run_restore(load_config(), opts)
print('Wiederherstellung abgeschlossen.')
"""
    return _pkexec_python(code, on_output=on_output)


def save_rclone_remote_as_admin(spec_path: Path, on_output: LineCb | None = None) -> tuple[bool, str]:
    code = f"""
import json
from pathlib import Path
from nc_backup.rclone_wizard import RcloneRemoteSpec, RcloneProvider, write_remote

raw = json.loads(Path({repr(str(spec_path))}).read_text(encoding='utf-8'))
spec = RcloneRemoteSpec(
    name=raw['name'],
    provider=RcloneProvider(raw['provider']),
    webdav_url=raw.get('webdav_url', ''),
    webdav_user=raw.get('webdav_user', ''),
    webdav_pass=raw.get('webdav_pass', ''),
    s3_endpoint=raw.get('s3_endpoint', ''),
    s3_access_key=raw.get('s3_access_key', ''),
    s3_secret_key=raw.get('s3_secret_key', ''),
    s3_region=raw.get('s3_region', 'eu-central-1'),
    sftp_host=raw.get('sftp_host', ''),
    sftp_user=raw.get('sftp_user', ''),
    sftp_pass=raw.get('sftp_pass', ''),
    sftp_port=int(raw.get('sftp_port', 22)),
    client_id=raw.get('client_id', ''),
    client_secret=raw.get('client_secret', ''),
)
path = write_remote(spec)
print(f'Remote gespeichert: {{path}}')
"""
    return _pkexec_python(code, extra_cleanup=spec_path, on_output=on_output)


def test_rclone_as_admin(remote_name: str, on_output: LineCb | None = None) -> tuple[bool, str]:
    code = f"""
from nc_backup.rclone_wizard import test_remote
ok, msg = test_remote({remote_name!r})
print(msg)
import sys
sys.exit(0 if ok else 1)
"""
    return _pkexec_python(code, on_output=on_output)


def list_rclone_remotes_as_admin(on_output: LineCb | None = None) -> tuple[bool, str, list[str]]:
    code = """
import json
from nc_backup.rclone_wizard import list_remotes
print(json.dumps(list_remotes()))
"""
    ok, out = _pkexec_python(code, on_output=on_output)
    if not ok:
        return ok, out, []
    try:
        line = out.strip().splitlines()[-1]
        return True, out, json.loads(line)
    except json.JSONDecodeError:
        return False, out, []


def oauth_rclone_as_admin(remote_name: str, on_output: LineCb | None = None) -> tuple[bool, str]:
    """Öffnet Terminal für OAuth — pkexec mit DISPLAY."""
    code = f"""
import os
import subprocess
env = os.environ.copy()
env['RCLONE_CONFIG'] = '/etc/nc-backup/rclone.conf'
subprocess.run(['rclone', 'config', 'reconnect', {remote_name!r} + ':'], env=env, check=True)
print('OAuth-Verknüpfung abgeschlossen.')
"""
    return _pkexec_python(code, on_output=on_output)
