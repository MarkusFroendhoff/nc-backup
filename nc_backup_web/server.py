"""ThreadingHTTPServer für die NC-Backup-Web-Oberfläche (nur stdlib)."""

from __future__ import annotations

import hmac
import json
import os
import secrets as stdsecrets
import subprocess
import sys
import threading
import traceback
from datetime import datetime
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from nc_backup.secrets import (
    SECRET_ERROR_DE,
    WEB_TOKEN_PATH,
    ensure_web_token,
    generate_secret,
    is_valid_secret,
    load_web_token,
    secret_error,
    write_web_token,
)

STATIC_DIR = Path(__file__).resolve().parent / "static"
COOKIE_NAME = "nc_backup_session"
_LOG_LOCK = threading.Lock()
_LOG_LINES: list[str] = []
_LOG_MAX = 800
_JOB_LOCK = threading.Lock()
_JOB: dict[str, Any] = {
    "running": False,
    "kind": None,
    "ok": None,
    "message": "",
    "started": None,
    "finished": None,
}


def _log_append(line: str) -> None:
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    text = line if line.startswith("[") else f"[{stamp}] {line}"
    with _LOG_LOCK:
        _LOG_LINES.append(text)
        if len(_LOG_LINES) > _LOG_MAX:
            del _LOG_LINES[: len(_LOG_LINES) - _LOG_MAX]


def _install_log_hook() -> None:
    try:
        from nc_backup import logutil
    except ImportError:
        return
    orig = logutil.log
    orig_err = logutil.log_error

    def hooked(msg: str) -> None:
        _log_append(msg)
        orig(msg)

    def hooked_err(msg: str) -> None:
        _log_append("FEHLER: " + msg)
        orig_err(msg)

    logutil.log = hooked  # type: ignore[method-assign]
    logutil.log_error = hooked_err  # type: ignore[method-assign]


_install_log_hook()


def destination_summary(cfg: Any) -> str:
    from nc_backup.models import Provider

    d = getattr(cfg, "destination", None)
    if d is None:
        export = getattr(cfg, "export_path", "") or ""
        return f"Dieser Computer — {export}" if export else "Noch kein Ziel"
    p = d.provider
    if p == Provider.LOCAL:
        return f"Dieser Computer — {d.local_path}"
    if p == Provider.SFTP:
        host = d.sftp_host or "…"
        user = d.sftp_user or "…"
        return f"Anderer Rechner (SFTP) — {user}@{host}:{d.sftp_path}"
    if p == Provider.S3:
        bucket = d.s3_bucket or "…"
        return f"Online-Speicher (S3) — {bucket}"
    if p == Provider.WEBDAV:
        return f"WebDAV — {d.webdav_url or '…'}"
    if p == Provider.AZURE:
        return f"Azure — {d.azure_container or '…'}"
    if p == Provider.B2:
        return f"Backblaze B2 — {d.b2_bucket or '…'}"
    if p == Provider.RCLONE:
        return f"Rclone — {d.rclone_remote or '…'}"
    return p.value


def _public_config(cfg: Any) -> dict[str, Any]:
    data = cfg.to_dict()
    dest = data.get("destination") or {}
    dest.pop("restic_password", None)
    dest.pop("sftp_password", None)
    dest.pop("s3_secret_key", None)
    dest.pop("webdav_password", None)
    dest.pop("azure_key", None)
    dest.pop("b2_account_key", None)
    data["destination"] = dest
    db = data.get("database") or {}
    db["password_set"] = bool(cfg.database.password)
    db.pop("password", None)
    data["database"] = db
    data["restic_password_set"] = bool(cfg.destination.restic_password)
    data["destination_summary"] = destination_summary(cfg)
    return data


def _apply_dest_fields(cfg: Any, body: dict[str, Any]) -> str | None:
    """Aktualisiert Ziel-Felder. Gibt Fehlermeldung oder None zurück."""
    from nc_backup.models import BackupMode, Provider

    dest = cfg.destination
    if "mode" in body and body["mode"]:
        dest.mode = BackupMode(body["mode"])
    if "provider" in body and body["provider"]:
        dest.provider = Provider(body["provider"])

    str_fields = (
        "local_path",
        "sftp_host",
        "sftp_user",
        "sftp_path",
        "s3_endpoint",
        "s3_bucket",
        "s3_prefix",
        "s3_access_key",
        "s3_region",
        "webdav_url",
        "webdav_user",
        "azure_account",
        "azure_container",
        "azure_prefix",
        "b2_account_id",
        "b2_bucket",
        "b2_prefix",
        "rclone_remote",
        "rclone_path",
    )
    for name in str_fields:
        if name in body and body[name] is not None:
            setattr(dest, name, str(body[name]).strip())

    secret_fields = (
        "sftp_password",
        "s3_secret_key",
        "webdav_password",
        "azure_key",
        "b2_account_key",
    )
    for name in secret_fields:
        if name in body and body[name]:
            setattr(dest, name, str(body[name]))

    if "sftp_port" in body and body["sftp_port"] not in (None, ""):
        dest.sftp_port = int(body["sftp_port"])

    ret = body.get("retention") or {}
    if ret:
        if "keep_daily" in ret:
            dest.retention.keep_daily = int(ret["keep_daily"])
        if "keep_weekly" in ret:
            dest.retention.keep_weekly = int(ret["keep_weekly"])
        if "keep_monthly" in ret:
            dest.retention.keep_monthly = int(ret["keep_monthly"])

    if "restic_password" in body:
        pw = body["restic_password"]
        if pw is None:
            pass
        elif pw == "":
            pass
        else:
            err = secret_error(str(pw))
            if err:
                return err
            dest.restic_password = str(pw)
    return None


def _apply_nc_db(cfg: Any, body: dict[str, Any]) -> None:
    nc = body.get("nextcloud") or {}
    if nc:
        if "install_dir" in nc:
            cfg.nextcloud.install_dir = str(nc["install_dir"]).strip()
        if "data_dir" in nc:
            cfg.nextcloud.data_dir = str(nc["data_dir"]).strip()
        if "occ_user" in nc:
            cfg.nextcloud.occ_user = str(nc["occ_user"]).strip()
        if "maintenance_mode" in nc:
            cfg.nextcloud.maintenance_mode = bool(nc["maintenance_mode"])
        if "container" in nc and nc["container"] is not None:
            cfg.nextcloud.container = str(nc["container"]).strip()
        if "occ_inner" in nc and nc["occ_inner"] is not None:
            cfg.nextcloud.occ_inner = str(nc["occ_inner"]).strip()
    db = body.get("database") or {}
    if db:
        if "host" in db:
            cfg.database.host = str(db["host"]).strip()
        if "port" in db and db["port"] not in (None, ""):
            cfg.database.port = int(db["port"])
        if "name" in db:
            cfg.database.name = str(db["name"]).strip()
        if "user" in db:
            cfg.database.user = str(db["user"]).strip()
        if db.get("password"):
            cfg.database.password = str(db["password"])
        if "type" in db and db["type"] is not None:
            cfg.database.type = str(db["type"]).strip() or cfg.database.type
        if "container" in db and db["container"] is not None:
            cfg.database.container = str(db["container"]).strip()



def _detect_public() -> dict[str, Any]:
    """Nextcloud-Erkennung als JSON ohne Geheimnisse."""
    from nc_backup.detect import detection_public_dict

    info = dict(detection_public_dict())
    info.pop("dbpassword", None)
    info.pop("db_password", None)
    return info

def _enable_timer(cfg: Any) -> None:
    from nc_backup.scheduler import apply_schedule

    apply_schedule(cfg)
    subprocess.run(["systemctl", "daemon-reload"], check=False)
    if cfg.schedule.enabled:
        subprocess.run(["systemctl", "enable", "--now", "nc-backup.timer"], check=False)
    else:
        subprocess.run(["systemctl", "disable", "--now", "nc-backup.timer"], check=False)


def _journal_snippet(n: int = 80) -> str:
    try:
        proc = subprocess.run(
            [
                "journalctl",
                "-u",
                "nc-backup.service",
                "-u",
                "nc-backup-web.service",
                "-n",
                str(n),
                "--no-pager",
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=8,
        )
        text = (proc.stdout or proc.stderr or "").strip()
        return text
    except (OSError, subprocess.TimeoutExpired):
        return ""


def _run_job(kind: str, fn) -> None:
    with _JOB_LOCK:
        if _JOB["running"]:
            return
        _JOB.update(
            {
                "running": True,
                "kind": kind,
                "ok": None,
                "message": "",
                "started": datetime.now().isoformat(timespec="seconds"),
                "finished": None,
            }
        )

    def worker() -> None:
        ok = False
        message = ""
        try:
            result = fn()
            if isinstance(result, tuple):
                ok, message = bool(result[0]), str(result[1])
            elif isinstance(result, int):
                ok = result == 0
                message = "Fertig." if ok else "Vorgang fehlgeschlagen."
            else:
                ok = True
                message = str(result) if result else "Fertig."
        except Exception as exc:
            ok = False
            message = str(exc)
            _log_append("FEHLER: " + message)
            traceback.print_exc()
        with _JOB_LOCK:
            _JOB.update(
                {
                    "running": False,
                    "ok": ok,
                    "message": message,
                    "finished": datetime.now().isoformat(timespec="seconds"),
                }
            )

    threading.Thread(target=worker, name=f"nc-{kind}", daemon=True).start()


class Handler(BaseHTTPRequestHandler):
    server_version = "nc-backup-web/1.8"

    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def _send(self, code: int, body: bytes, content_type: str, extra: list[tuple[str, str]] | None = None) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cache-Control", "no-store")
        if extra:
            for k, v in extra:
                self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, payload: dict[str, Any], extra: list[tuple[str, str]] | None = None) -> None:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._send(code, raw, "application/json; charset=utf-8", extra)

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or "0")
        if length <= 0:
            return {}
        if length > 1_000_000:
            raise ValueError("Anfrage zu groß")
        raw = self.rfile.read(length)
        if not raw:
            return {}
        data = json.loads(raw.decode("utf-8"))
        if not isinstance(data, dict):
            raise ValueError("JSON-Objekt erwartet")
        return data

    def _token_ok(self, offered: str | None) -> bool:
        stored = load_web_token() or ""
        if not stored or not is_valid_secret(stored):
            ensure_web_token()
            stored = load_web_token() or ""
        if not offered or not stored:
            return False
        return hmac.compare_digest(offered, stored)

    def _offered_token(self) -> str | None:
        auth = self.headers.get("Authorization") or ""
        if auth.lower().startswith("bearer "):
            return auth[7:].strip()
        header_token = (self.headers.get("X-NC-Backup-Token") or "").strip()
        if header_token:
            return header_token
        cookie_header = self.headers.get("Cookie") or ""
        if cookie_header:
            jar = SimpleCookie()
            try:
                jar.load(cookie_header)
            except Exception:
                jar = SimpleCookie()
            if COOKIE_NAME in jar:
                return jar[COOKIE_NAME].value
        return None

    def _authed(self) -> bool:
        return self._token_ok(self._offered_token())

    def _need_auth(self) -> bool:
        if self._authed():
            return False
        self._json(401, {"ok": False, "error": "Bitte zuerst anmelden."})
        return True

    def _cookie_header(self, token: str) -> str:
        return (
            f"{COOKIE_NAME}={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=86400"
        )

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        if path in ("/", "/index.html"):
            self._serve_static("index.html")
            return
        if path.startswith("/static/"):
            self._serve_static(path[len("/static/") :])
            return
        if path == "/api/login":
            self._json(200, {"ok": True, "need_login": not self._authed()})
            return
        if path.startswith("/api/"):
            if self._need_auth():
                return
            try:
                self._api_get(path)
            except Exception as exc:
                traceback.print_exc()
                self._json(500, {"ok": False, "error": f"Laden fehlgeschlagen: {exc}"})
            return
        self._json(404, {"ok": False, "error": "Nicht gefunden."})

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        try:
            body = self._read_json()
        except Exception as exc:
            self._json(400, {"ok": False, "error": str(exc)})
            return
        if path == "/api/login":
            self._api_login(body)
            return
        if path.startswith("/api/"):
            if self._need_auth():
                return
            try:
                self._api_post(path, body)
            except Exception as exc:
                traceback.print_exc()
                self._json(500, {"ok": False, "error": f"Speichern fehlgeschlagen: {exc}"})
            return
        self._json(404, {"ok": False, "error": "Nicht gefunden."})

    def _serve_static(self, rel: str) -> None:
        rel = rel.lstrip("/")
        if not rel or ".." in rel.split("/"):
            self._json(404, {"ok": False, "error": "Nicht gefunden."})
            return
        candidate = (STATIC_DIR / rel).resolve()
        try:
            candidate.relative_to(STATIC_DIR)
        except ValueError:
            self._json(404, {"ok": False, "error": "Nicht gefunden."})
            return
        if not candidate.is_file():
            self._json(404, {"ok": False, "error": "Nicht gefunden."})
            return
        suffix = candidate.suffix.lower()
        types = {
            ".html": "text/html; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".js": "application/javascript; charset=utf-8",
            ".svg": "image/svg+xml",
            ".png": "image/png",
            ".ico": "image/x-icon",
        }
        data = candidate.read_bytes()
        extra = [("Cache-Control", "no-cache")]
        self._send(200, data, types.get(suffix, "application/octet-stream"), extra)

    def _api_login(self, body: dict[str, Any]) -> None:
        offered = str(body.get("token") or body.get("key") or body.get("password") or "")
        if offered.strip() == "":
            self._json(400, {"ok": False, "error": "Bitte den Zugangsschlüssel eingeben."})
            return
        if not is_valid_secret(offered):
            self._json(400, {"ok": False, "error": SECRET_ERROR_DE})
            return
        if not self._token_ok(offered):
            self._json(403, {"ok": False, "error": "Zugangsschlüssel ungültig."})
            return
        self._json(
            200,
            {"ok": True},
            extra=[("Set-Cookie", self._cookie_header(offered))],
        )

    def _api_get(self, path: str) -> None:
        from nc_backup.config_store import load_config
        from nc_backup.engine import validate

        if path == "/api/status":
            cfg = load_config()
            detected = _detect_public()
            errors = validate(cfg)
            with _JOB_LOCK:
                job = dict(_JOB)
            with _LOG_LOCK:
                snippet = "\n".join(_LOG_LINES[-40:])
            last_backup = None
            try:
                from nc_backup.restore import get_snapshots

                snaps = get_snapshots(cfg)
                if snaps:
                    last_backup = {
                        "time": snaps[0].time,
                        "short_id": snaps[0].short_id,
                    }
            except Exception:
                last_backup = None
            self._json(
                200,
                {
                    "ok": True,
                    "nextcloud": {
                        "found": bool(detected.get("found")),
                        "summary": detected.get("summary") or "",
                        "install_dir": cfg.nextcloud.install_dir,
                        "data_dir": cfg.nextcloud.data_dir,
                    },
                    "destination": destination_summary(cfg),
                    "schedule": {
                        "enabled": cfg.schedule.enabled,
                        "on_calendar": cfg.schedule.on_calendar,
                    },
                    "restic_password_set": bool(cfg.destination.restic_password),
                    "ready": not errors,
                    "errors": errors,
                    "job": job,
                    "log_snippet": snippet,
                    "last_backup": last_backup,
                },
            )
            return
        if path == "/api/detect":
            self._json(200, {"ok": True, **_detect_public()})
            return
        if path == "/api/targets":
            from nc_backup.mounts import list_backup_targets

            targets = []
            for item in list_backup_targets():
                targets.append(
                    {
                        "path": item.path,
                        "label": item.label,
                        "kind": item.kind,
                        "display": item.display,
                        "writable": item.writable,
                        "free_gb": item.free_gb,
                    }
                )
            self._json(200, {"ok": True, "targets": targets})
            return
        if path == "/api/config":
            cfg = load_config()
            self._json(200, {"ok": True, "config": _public_config(cfg)})
            return
        if path == "/api/log":
            with _LOG_LOCK:
                mem = "\n".join(_LOG_LINES[-400:])
            journal = _journal_snippet()
            self._json(200, {"ok": True, "log": mem, "journal": journal})
            return
        if path == "/api/snapshots":
            try:
                from nc_backup.restore import get_snapshots

                snaps = get_snapshots(load_config())
                self._json(
                    200,
                    {
                        "ok": True,
                        "snapshots": [s.__dict__ for s in snaps],
                    },
                )
            except Exception as exc:
                self._json(400, {"ok": False, "error": str(exc), "snapshots": []})
            return
        if path == "/api/secret/new":
            self._json(200, {"ok": True, "secret": generate_secret()})
            return
        if path == "/api/update":
            from nc_backup.updates import check_for_update

            force = "force=1" in (self.path or "")
            try:
                info = check_for_update(force=force)
            except Exception as exc:
                info = {
                    "ok": False,
                    "installed": __import__("nc_backup").__version__,
                    "latest": "",
                    "update_available": False,
                    "url": "https://github.com/MarkusFroendhoff/nc-backup",
                    "message": f"Update-Prüfung fehlgeschlagen: {exc}",
                }
            self._json(200, info)
            return
        self._json(404, {"ok": False, "error": "Nicht gefunden."})

    def _api_post(self, path: str, body: dict[str, Any]) -> None:
        from nc_backup.config_store import load_config, save_config

        if path == "/api/logout":
            extra = [
                (
                    "Set-Cookie",
                    f"{COOKIE_NAME}=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0",
                )
            ]
            self._json(200, {"ok": True}, extra=extra)
            return
        if path == "/api/web-token":
            new = str(body.get("token") or body.get("key") or "")
            err = secret_error(new)
            if err:
                self._json(400, {"ok": False, "error": err})
                return
            write_web_token(new)
            self._json(
                200,
                {"ok": True, "message": "Zugangsschlüssel gespeichert."},
                extra=[("Set-Cookie", self._cookie_header(new))],
            )
            return
        if path == "/api/detect-apply":
            from nc_backup.detect import apply_detected_defaults

            info = apply_detected_defaults()
            self._json(200, {"ok": True, **info})
            return
        if path == "/api/config":
            cfg = load_config()
            _apply_nc_db(cfg, body)
            err = _apply_dest_fields(cfg, body.get("destination") or body)
            if err:
                self._json(400, {"ok": False, "error": err})
                return
            sched = body.get("schedule") or {}
            if sched:
                if "enabled" in sched:
                    cfg.schedule.enabled = bool(sched["enabled"])
                if "on_calendar" in sched and sched["on_calendar"]:
                    cfg.schedule.on_calendar = str(sched["on_calendar"]).strip()
            if not cfg.destination.restic_password:
                cfg.destination.restic_password = generate_secret()
                once = cfg.destination.restic_password
            else:
                once = None
            save_config(cfg)
            payload: dict[str, Any] = {
                "ok": True,
                "message": "Einstellungen gespeichert.",
                "config": _public_config(cfg),
            }
            if once:
                payload["restic_password_once"] = once
                payload["message"] += " Das Sicherungskennwort wird nur diesmal angezeigt — bitte notieren."
            self._json(200, payload)
            return
        if path == "/api/wizard":
            cfg = load_config()
            from nc_backup.detect import detect_nextcloud, apply_detected_defaults
            from nc_backup.models import BackupMode, Provider

            detected = _detect_public()
            if detected.get("found"):
                apply_detected_defaults()
                cfg = load_config()

            _apply_nc_db(cfg, body)
            provider = str(body.get("provider") or "local")
            try:
                cfg.destination.provider = Provider(provider)
            except ValueError:
                self._json(400, {"ok": False, "error": "Unbekanntes Ziel."})
                return
            cfg.destination.mode = BackupMode.INCREMENTAL
            err = _apply_dest_fields(cfg, body)
            if err:
                self._json(400, {"ok": False, "error": err})
                return
            generated = False
            pw = str(body.get("restic_password") or "")
            if pw:
                err = secret_error(pw)
                if err:
                    self._json(400, {"ok": False, "error": err})
                    return
                cfg.destination.restic_password = pw
            elif not cfg.destination.restic_password:
                cfg.destination.restic_password = generate_secret()
                generated = True
            time_s = str(body.get("on_calendar") or body.get("time") or "02:30").strip()
            cfg.schedule.on_calendar = time_s
            cfg.schedule.enabled = bool(body.get("enable_schedule", True))
            save_config(cfg)
            try:
                _enable_timer(cfg)
            except Exception as exc:
                _log_append(f"Zeitplan: {exc}")
            payload = {
                "ok": True,
                "message": "Einrichtung gespeichert.",
                "config": _public_config(cfg),
                "detected": detected,
            }
            if generated:
                payload["restic_password_once"] = cfg.destination.restic_password
            self._json(200, payload)
            return
        if path == "/api/schedule":
            cfg = load_config()
            if "enabled" in body:
                cfg.schedule.enabled = bool(body["enabled"])
            if body.get("on_calendar"):
                cfg.schedule.on_calendar = str(body["on_calendar"]).strip()
            save_config(cfg)
            try:
                _enable_timer(cfg)
                msg = "Zeitplan gespeichert."
            except Exception as exc:
                msg = f"Einstellungen gespeichert, Zeitplan konnte nicht aktiviert werden: {exc}"
            self._json(200, {"ok": True, "message": msg})
            return
        if path == "/api/backup":
            with _JOB_LOCK:
                if _JOB["running"]:
                    self._json(409, {"ok": False, "error": "Es läuft bereits ein Vorgang."})
                    return

            def _do_backup():
                from nc_backup.engine import run_backup

                code = run_backup()
                return code == 0, "Sicherung abgeschlossen." if code == 0 else "Sicherung fehlgeschlagen."

            _run_job("backup", _do_backup)
            self._json(200, {"ok": True, "message": "Sicherung gestartet."})
            return
        if path == "/api/restore":
            if not body.get("confirm"):
                self._json(
                    400,
                    {
                        "ok": False,
                        "error": "Bitte die Wiederherstellung bestätigen.",
                    },
                )
                return
            snap = str(body.get("snapshot_id") or body.get("snapshot") or "").strip()
            if not snap:
                self._json(400, {"ok": False, "error": "Kein Sicherungspunkt gewählt."})
                return
            with _JOB_LOCK:
                if _JOB["running"]:
                    self._json(409, {"ok": False, "error": "Es läuft bereits ein Vorgang."})
                    return

            def _do_restore():
                from nc_backup.restore import RestoreOptions, run_restore
                from nc_backup.config_store import load_config as _load

                opts = RestoreOptions(
                    snapshot_id=snap,
                    restore_database=bool(body.get("database", True)),
                    restore_config=bool(body.get("config", True)),
                    restore_data=bool(body.get("data", False)),
                )
                run_restore(_load(), opts)
                return True, "Wiederherstellung abgeschlossen."

            _run_job("restore", _do_restore)
            self._json(200, {"ok": True, "message": "Wiederherstellung gestartet."})
            return
        self._json(404, {"ok": False, "error": "Nicht gefunden."})


def serve(bind: str, port: int) -> None:
    ensure_web_token()
    httpd = ThreadingHTTPServer((bind, port), Handler)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
