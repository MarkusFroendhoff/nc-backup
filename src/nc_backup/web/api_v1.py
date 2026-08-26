"""JSON-API für die Nextcloud-App: Backup starten, Status, Ziel-Laufwerke."""

from __future__ import annotations

import threading
from dataclasses import replace

from flask import Flask, jsonify, request

from nc_backup.auth import verify_api_token
from nc_backup.backup_engine import run_backup, setup_logging
from nc_backup.config_store import load_config
from nc_backup.i18n import Translator
from nc_backup.job_status import _backup_lock, backup_tracker
from nc_backup.mounts import list_backup_targets
from nc_backup.space_check import check_backup_space


def _token_from_request() -> str:
    header = request.headers.get("Authorization", "")
    token = header[7:].strip() if header.lower().startswith("bearer ") else ""
    if not token:
        token = request.headers.get("X-NC-Backup-Token", "").strip()
    return token


def _require_api_token():
    cfg = load_config()
    if not verify_api_token(_token_from_request(), getattr(cfg, "api_token_hash", None)):
        return jsonify({"ok": False, "message": "Unauthorized"}), 401
    return None


def _has_rule(flask_app: Flask, rule_path: str, method: str) -> bool:
    method = method.upper()
    for rule in flask_app.url_map.iter_rules():
        if rule.rule == rule_path and method in (rule.methods or set()):
            return True
    return False


def _apply_export_path(cfg):
    payload = request.get_json(silent=True) or {}
    export_path = (payload.get("export_path") or request.form.get("export_path") or "").strip()
    if export_path:
        return replace(cfg, export_path=export_path)
    return cfg


def register_api_v1(flask_app: Flask) -> None:
    """Hängt /api/v1/* an die Web-GUI. Ein zweiter Aufruf ändert vorhandene Routen nicht."""

    if not _has_rule(flask_app, "/api/v1/targets", "GET"):

        @flask_app.get("/api/v1/targets")
        def api_targets():
            denied = _require_api_token()
            if denied is not None:
                return denied
            cfg = load_config()
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
                        "selected": item.path == cfg.export_path,
                    }
                )
            return jsonify({"ok": True, "export_path": cfg.export_path, "targets": targets})

    try:
        import nc_backup.web.app as webapp

        original = getattr(webapp, "_launch_backup", None)
        if original is not None and not getattr(webapp, "_nc_export_path_wrapped", False):

            def _wrapped_launch(cfg):
                return original(_apply_export_path(cfg))

            webapp._launch_backup = _wrapped_launch
            webapp._nc_export_path_wrapped = True
    except Exception:  # noqa: BLE001
        pass

    if _has_rule(flask_app, "/api/v1/backup", "POST"):
        return

    def _launch_backup(cfg):
        t = Translator(getattr(cfg, "ui_language", "de") or "de")
        cfg = _apply_export_path(cfg)
        space = check_backup_space(cfg)
        if not space.ok:
            return jsonify({"ok": False, "message": space.message, "details": space.details}), 400
        if not _backup_lock.acquire(blocking=False):
            return jsonify({"ok": False, "message": t("err_backup_running")}), 409
        setup_logging()
        backup_tracker.reset()
        backup_tracker.update(percent=1, phase="Speicherplatz", detail=space.message)

        def worker() -> None:
            try:
                def on_progress(percent: int, phase: str, detail: str = "") -> None:
                    backup_tracker.update(percent=percent, phase=phase, detail=detail)

                result = run_backup(cfg, progress_callback=on_progress)
                backup_tracker.finish(
                    success=result.success,
                    message=result.message,
                    destination=str(result.destination or ""),
                    errors=result.errors,
                )
            except Exception as exc:  # noqa: BLE001
                backup_tracker.finish(success=False, message=str(exc), errors=[str(exc)])
            finally:
                _backup_lock.release()

        threading.Thread(target=worker, daemon=True).start()
        return jsonify({"ok": True, "message": t("ok_backup_started"), "space": space.to_dict()})

    @flask_app.post("/api/v1/backup")
    def api_backup():
        denied = _require_api_token()
        if denied is not None:
            return denied
        return _launch_backup(load_config())

    @flask_app.get("/api/v1/status")
    def api_status():
        denied = _require_api_token()
        if denied is not None:
            return denied
        return jsonify(backup_tracker.snapshot())
