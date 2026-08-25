"""Web-GUI für Nextcloud Backup."""

from __future__ import annotations

import argparse
import os
import secrets
import threading
from pathlib import Path

from flask import Flask, jsonify, redirect, render_template_string, request, session, url_for

from nc_backup.auth import hash_password, verify_password
from nc_backup.backup_engine import run_backup, setup_logging
from nc_backup.config_store import AppConfig, config_needs_password, default_config_for_mode, load_config, save_config
from nc_backup.docker_detect import detect_docker_installations
from nc_backup.i18n import Translator, detect_browser_lang, normalize_lang
from nc_backup.job_status import _backup_lock, backup_tracker
from nc_backup.mounts import list_backup_targets
from nc_backup.path_discover import apply_discovered_paths, discover_paths_from_config_php
from nc_backup.restore_engine import RestoreOptions, run_restore
from nc_backup.secrets_store import clear_gpg_passphrase, load_gpg_passphrase, save_gpg_passphrase
from nc_backup.space_check import check_backup_space
from nc_backup.systemd_schedule import apply_schedule, describe_schedule

DEFAULT_PORT = 42173
DEFAULT_HOST = "0.0.0.0"

app = Flask(__name__)
app.secret_key = os.environ.get("NC_BACKUP_WEB_SECRET", secrets.token_hex(32))


PAGE = """
<!doctype html>
<html lang="{{ lang }}">
<head>
  <meta charset="utf-8">
  <title>{{ t('title') }}</title>
  <style>
    body { font-family: sans-serif; margin: 2rem; max-width: 980px; color: #1a1a1a; }
    .row { margin: .7rem 0; }
    input[type=text], input[type=password], textarea, select { width: 100%; padding: .45rem; box-sizing: border-box; }
    textarea { min-height: 80px; }
    .card { border: 1px solid #ccc; border-radius: 8px; padding: 1rem; margin: 1rem 0; }
    .msg { background: #f0f7ff; padding: .75rem; border-left: 4px solid #2b6cb0; }
    .err { background: #fff5f5; border-left-color: #c53030; }
    .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; }
    button { padding: .5rem .8rem; cursor: pointer; }
    .hint { color: #555; font-size: .9rem; margin-top: .25rem; }
    .topbar { display:flex; justify-content:space-between; align-items:center; gap:1rem; flex-wrap:wrap; margin-bottom:1rem; }
    .lang-form { display:flex; gap:.4rem; align-items:center; font-size:.9rem; }
    .lang-form select { width:auto; }
    .progress-wrap { background: #e8e8e8; border-radius: 8px; overflow: hidden; height: 22px; }
    .progress-bar { background: #2b6cb0; height: 100%; width: 0%; color: #fff; font-size: .8rem; text-align: center; line-height: 22px; transition: width .25s; }
    #progress-log { background: #111; color: #d7ffd7; font-family: ui-monospace, monospace; font-size: .85rem; padding: .75rem; min-height: 140px; max-height: 240px; overflow: auto; white-space: pre-wrap; }
  </style>
</head>
<body>
  <div class="topbar">
    <h1 style="margin:0">{{ t('heading') }}</h1>
    <form class="lang-form" method="post" action="{{ url_for('set_language') }}">
      <label for="ui_language">{{ t('lang_label') }}</label>
      <select id="ui_language" name="ui_language" onchange="this.form.submit()">
        <option value="de" {{ "selected" if lang == "de" else "" }}>{{ t('lang_de') }}</option>
        <option value="en" {{ "selected" if lang == "en" else "" }}>{{ t('lang_en') }}</option>
      </select>
    </form>
  </div>
  {% if message %}<div class="msg {{ 'err' if is_error else '' }}">{{ message }}</div>{% endif %}

  {% if not logged_in %}
    {% if setup_mode %}
      <div class="card">
        <h2>{{ t('setup_title') }}</h2>
        <form method="post" action="{{ url_for('setup_password') }}">
          <div class="row"><label>{{ t('new_password') }}</label><input type="password" name="password" required></div>
          <div class="row"><label>{{ t('confirm_password') }}</label><input type="password" name="password_confirm" required></div>
          <button type="submit">{{ t('save_password') }}</button>
        </form>
      </div>
    {% else %}
      <div class="card">
        <h2>{{ t('login_title') }}</h2>
        <form method="post" action="{{ url_for('login') }}">
          <div class="row"><label>{{ t('master_password') }}</label><input type="password" name="password" required></div>
          <button type="submit">{{ t('login') }}</button>
        </form>
      </div>
    {% endif %}
  {% else %}
    <p><a href="{{ url_for('logout') }}">{{ t('logout') }}</a></p>

    <div class="card">
      <h2>{{ t('quick_actions') }}</h2>
      <button type="button" id="btn-backup" onclick="startBackup()">{{ t('backup_now') }}</button>
      <button type="button" onclick="checkSpace()">{{ t('check_space') }}</button>
      <form method="post" action="{{ url_for('detect_docker') }}" style="display:inline;">
        <button type="submit">{{ t('detect_docker') }}</button>
      </form>
      <form method="post" action="{{ url_for('detect_paths') }}" style="display:inline;">
        <button type="submit">{{ t('detect_paths') }}</button>
      </form>
      <form method="post" action="{{ url_for('refresh_targets') }}" style="display:inline;">
        <button type="submit">{{ t('refresh_targets') }}</button>
      </form>
    </div>

    <div class="card" id="progress-card">
      <h2>{{ t('progress') }}</h2>
      <div class="progress-wrap"><div class="progress-bar" id="progress-bar">0%</div></div>
      <p id="progress-phase">{{ t('ready') }}</p>
      <p id="progress-detail" class="hint"></p>
      <div id="progress-log"></div>
    </div>

    <div class="card">
      <h2>{{ t('settings') }}</h2>
      <form method="post" action="{{ url_for('save_settings_route') }}">
        <div class="grid">
          <div class="row">
            <label>{{ t('install_mode') }}</label>
            <select name="install_mode">
              {% for mode in ["native","docker","custom"] %}
              <option value="{{ mode }}" {{ "selected" if cfg.install_mode == mode else "" }}>{{ mode }}</option>
              {% endfor %}
            </select>
          </div>
          <div class="row">
            <label>{{ t('backup_target') }}</label>
            <select name="export_target_choice" onchange="if(this.value){document.getElementById('export_path').value=this.value;}">
              <option value="">{{ t('choose_target') }}</option>
              {% for target in targets %}
              <option value="{{ target.path }}" {{ "selected" if cfg.export_path == target.path else "" }}>{{ target.display }}</option>
              {% endfor %}
            </select>
            <div class="hint">{{ t('target_hint') }}</div>
          </div>
          <div class="row">
            <label>{{ t('export_path') }}</label>
            <input id="export_path" type="text" name="export_path" value="{{ cfg.export_path }}" placeholder="/media/markus/USBSTICK">
          </div>
          <div class="row">
            <label>{{ t('config_php') }}</label><input type="text" name="config_php_path" value="{{ cfg.config_php_path }}">
          </div>
          <div class="row">
            <label>{{ t('docker_nc') }}</label><input type="text" name="docker_nextcloud_container" value="{{ cfg.docker_nextcloud_container }}">
          </div>
          <div class="row">
            <label>{{ t('docker_db') }}</label><input type="text" name="docker_db_container" value="{{ cfg.docker_db_container }}">
          </div>
          <div class="row">
            <label>{{ t('source_folders') }}</label>
            <textarea name="source_folders">{{ source_text }}</textarea>
          </div>
        </div>

        <div class="row"><label><input type="checkbox" name="include_database" {{ "checked" if cfg.include_database else "" }}> {{ t('include_db') }}</label></div>

        <div class="row">
          <label>{{ t('backup_mode') }}</label>
          <select name="backup_mode">
            <option value="auto" {{ "selected" if cfg.backup_mode == "auto" else "" }}>{{ t('mode_auto') }}</option>
            <option value="stream_encrypted" {{ "selected" if cfg.backup_mode == "stream_encrypted" else "" }}>{{ t('mode_stream') }}</option>
            <option value="incremental" {{ "selected" if cfg.backup_mode == "incremental" else "" }}>{{ t('mode_incr') }}</option>
            <option value="classic" {{ "selected" if cfg.backup_mode == "classic" else "" }}>{{ t('mode_classic') }}</option>
          </select>
          <div class="hint">{{ t('mode_hint')|safe }}</div>
        </div>

        <div class="row"><label><input type="checkbox" name="encrypt_backups" {{ "checked" if cfg.encrypt_backups else "" }}> {{ t('encrypt') }}</label></div>

        <div class="row">
          <label>{{ t('gpg_mode') }}</label>
          <select name="gpg_mode">
            <option value="symmetric" {{ "selected" if cfg.gpg_mode == "symmetric" else "" }}>{{ t('gpg_pass') }}</option>
            <option value="recipient" {{ "selected" if cfg.gpg_mode == "recipient" else "" }}>{{ t('gpg_key') }}</option>
          </select>
          <div class="hint">{{ t('gpg_hint')|safe }}</div>
        </div>

        <div class="row">
          <label>{{ t('gpg_recipient') }}</label>
          <input type="text" name="gpg_recipient" value="{{ cfg.gpg_recipient }}" placeholder="markus@example.com">
          <div class="hint">{{ t('gpg_recipient_hint')|safe }}</div>
        </div>

        <div class="row"><label><input type="checkbox" name="remove_plaintext_after_encrypt" {{ "checked" if cfg.remove_plaintext_after_encrypt else "" }}> {{ t('remove_plain') }}</label></div>
        <div class="row">
          <label>{{ t('gpg_passphrase') }}</label>
          <input type="password" name="gpg_passphrase" placeholder="{{ t('gpg_passphrase_ph') }}">
        </div>
        <button type="submit">{{ t('save_settings') }}</button>
      </form>
    </div>

    <div class="card">
      <h2>{{ t('schedule') }}</h2>
      <p>{{ schedule_text }}</p>
      <form method="post" action="{{ url_for('save_schedule_route') }}">
        <div class="row"><label><input type="checkbox" name="schedule_enabled" {{ "checked" if cfg.schedule.enabled else "" }}> {{ t('schedule_enable') }}</label></div>
        <div class="row"><label>{{ t('hour') }}</label><input type="text" name="schedule_hour" value="{{ cfg.schedule.hour }}"></div>
        <div class="row"><label>{{ t('minute') }}</label><input type="text" name="schedule_minute" value="{{ cfg.schedule.minute }}"></div>
        <div class="row"><label>{{ t('weekdays') }}</label><input type="text" name="schedule_weekdays" value="{{ weekdays_text }}"></div>
        <button type="submit">{{ t('save_schedule') }}</button>
      </form>
    </div>

    <div class="card">
      <h2>{{ t('restore') }}</h2>
      <form method="post" action="{{ url_for('run_restore_route') }}">
        <div class="row"><label>{{ t('backup_path') }}</label><input type="text" name="backup_path" required></div>
        <div class="row"><label><input type="checkbox" name="restore_files" checked> {{ t('restore_files') }}</label></div>
        <div class="row"><label><input type="checkbox" name="restore_database" checked> {{ t('restore_db') }}</label></div>
        <div class="row"><label><input type="checkbox" name="maintenance_mode" checked> {{ t('maintenance') }}</label></div>
        <div class="row"><label><input type="checkbox" name="delete_extra_files"> {{ t('delete_extra') }}</label></div>
        <div class="row"><label>{{ t('restore_gpg') }}</label><input type="password" name="restore_gpg_passphrase"></div>
        <button type="submit">{{ t('restore_start') }}</button>
      </form>
    </div>
  {% endif %}
  {% if logged_in %}
  <script>
    const I18N = {
      spaceOk: {{ t('js_space_ok')|tojson }},
      spaceBad: {{ t('js_space_bad')|tojson }},
      start: {{ t('js_start')|tojson }},
      starting: {{ t('js_starting')|tojson }},
      error: {{ t('js_error')|tojson }},
      startFail: {{ t('js_start_fail')|tojson }},
    };
    let pollTimer = null;

    async function checkSpace() {
      const response = await fetch('{{ url_for("check_space") }}');
      const data = await response.json();
      const lines = [data.message].concat(data.details || []);
      updateProgress({
        running: false,
        percent: data.ok ? 100 : 0,
        phase: data.ok ? I18N.spaceOk : I18N.spaceBad,
        detail: data.message,
        log_lines: lines,
      });
      alert(data.message);
    }

    async function startBackup() {
      const btn = document.getElementById('btn-backup');
      btn.disabled = true;
      document.getElementById('progress-log').textContent = '';
      updateProgress({running:true, percent:1, phase:I18N.start, detail:I18N.starting, log_lines:[]});
      const response = await fetch('{{ url_for("run_backup_now") }}', {method:'POST'});
      const data = await response.json();
      if (!data.ok) {
        btn.disabled = false;
        updateProgress({running:false, percent:0, phase:I18N.error, detail:data.message || I18N.startFail, log_lines:[data.message || '']});
        return;
      }
      if (pollTimer) clearInterval(pollTimer);
      pollTimer = setInterval(pollProgress, 1000);
      pollProgress();
    }

    async function pollProgress() {
      const response = await fetch('{{ url_for("backup_status") }}');
      const data = await response.json();
      updateProgress(data);
      if (!data.running) {
        clearInterval(pollTimer);
        pollTimer = null;
        document.getElementById('btn-backup').disabled = false;
      }
    }

    function updateProgress(data) {
      const bar = document.getElementById('progress-bar');
      const percent = data.percent || 0;
      bar.style.width = percent + '%';
      bar.textContent = percent + '%';
      document.getElementById('progress-phase').textContent = data.phase || '';
      document.getElementById('progress-detail').textContent = data.detail || '';
      const log = document.getElementById('progress-log');
      if (data.log_lines && data.log_lines.length) {
        log.textContent = data.log_lines.join('\\n');
        log.scrollTop = log.scrollHeight;
      }
    }

    fetch('{{ url_for("backup_status") }}').then(r => r.json()).then(data => {
      if (data.running) {
        document.getElementById('btn-backup').disabled = true;
        pollTimer = setInterval(pollProgress, 1000);
        updateProgress(data);
      }
    });
  </script>
  {% endif %}
</body>
</html>
"""


def _resolve_lang(cfg: AppConfig | None = None) -> str:
    cfg = cfg or load_config()
    if session.get("ui_language") in ("de", "en"):
        return session["ui_language"]
    stored = getattr(cfg, "ui_language", "auto") or "auto"
    if stored in ("de", "en"):
        return stored
    return detect_browser_lang(request.headers.get("Accept-Language"))


def _t(cfg: AppConfig | None = None) -> Translator:
    return Translator(_resolve_lang(cfg))


def _cfg_from_form(form) -> AppConfig:
    cfg = load_config()
    source_folders = [line.strip() for line in form.get("source_folders", "").splitlines() if line.strip()]
    cfg.install_mode = form.get("install_mode", cfg.install_mode)
    cfg.source_folders = source_folders
    cfg.export_path = form.get("export_path", "").strip()
    cfg.config_php_path = form.get("config_php_path", "").strip()
    cfg.docker_nextcloud_container = form.get("docker_nextcloud_container", "").strip()
    cfg.docker_db_container = form.get("docker_db_container", "").strip()
    cfg.include_database = bool(form.get("include_database"))
    cfg.backup_mode = form.get("backup_mode", "auto")
    cfg.encrypt_backups = bool(form.get("encrypt_backups"))
    cfg.gpg_mode = form.get("gpg_mode", "symmetric")
    cfg.gpg_recipient = form.get("gpg_recipient", "").strip()
    cfg.remove_plaintext_after_encrypt = bool(form.get("remove_plaintext_after_encrypt"))
    cfg.setup_complete = True
    return cfg


def _render(message: str = "", is_error: bool = False):
    cfg = load_config()
    lang = _resolve_lang(cfg)
    t = Translator(lang)
    logged_in = bool(session.get("logged_in"))
    setup_mode = not cfg.setup_complete or not config_needs_password(cfg)
    targets = list_backup_targets() if logged_in else []
    return render_template_string(
        PAGE,
        cfg=cfg,
        logged_in=logged_in,
        setup_mode=setup_mode,
        message=message,
        is_error=is_error,
        source_text="\n".join(cfg.source_folders),
        weekdays_text=",".join(str(day) for day in cfg.schedule.weekdays),
        schedule_text=describe_schedule(cfg.schedule),
        targets=targets,
        lang=lang,
        t=t,
    )


@app.get("/")
def index():
    return _render()


@app.post("/set-language")
def set_language():
    lang = normalize_lang(request.form.get("ui_language", "de"))
    session["ui_language"] = lang
    cfg = load_config()
    cfg.ui_language = lang
    save_config(cfg)
    return _render(_t(cfg)("ok_lang"))


@app.post("/setup-password")
def setup_password():
    t = _t()
    cfg = load_config()
    password = request.form.get("password", "")
    password_confirm = request.form.get("password_confirm", "")
    if not password or password != password_confirm:
        return _render(t("err_password_mismatch"), True)
    cfg.password_hash = hash_password(password)
    cfg.setup_complete = True
    if not cfg.source_folders:
        defaults = default_config_for_mode("native")
        cfg.install_mode = defaults.install_mode
        cfg.config_php_path = defaults.config_php_path
        cfg.source_folders = defaults.source_folders
    save_config(cfg)
    session["logged_in"] = True
    return redirect(url_for("index"))


@app.post("/login")
def login():
    t = _t()
    cfg = load_config()
    password = request.form.get("password", "")
    if verify_password(password, cfg.password_hash):
        session["logged_in"] = True
        return redirect(url_for("index"))
    return _render(t("err_wrong_password"), True)


@app.get("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


def _require_login():
    cfg = load_config()
    setup_mode = not cfg.setup_complete or not config_needs_password(cfg)
    if setup_mode:
        return None
    if session.get("logged_in"):
        return None
    return _render(_t(cfg)("err_login"), True)


@app.post("/save-settings")
def save_settings_route():
    maybe = _require_login()
    if maybe is not None:
        return maybe
    t = _t()
    cfg = _cfg_from_form(request.form)
    gpg_passphrase = request.form.get("gpg_passphrase", "").strip()
    if cfg.encrypt_backups and cfg.gpg_mode == "symmetric" and gpg_passphrase:
        save_gpg_passphrase(gpg_passphrase)
    elif not cfg.encrypt_backups:
        clear_gpg_passphrase()
    elif cfg.encrypt_backups and cfg.gpg_mode == "symmetric" and not load_gpg_passphrase():
        return _render(t("err_gpg_pass"), True)
    if cfg.encrypt_backups and cfg.gpg_mode == "recipient" and not cfg.gpg_recipient:
        return _render(t("err_gpg_recipient"), True)
    save_config(cfg)
    return _render(t("ok_settings"))


@app.post("/detect-paths")
def detect_paths():
    maybe = _require_login()
    if maybe is not None:
        return maybe
    t = _t()
    cfg = load_config()
    try:
        discovery = discover_paths_from_config_php(cfg.config_php_path)
    except (FileNotFoundError, ValueError, OSError) as exc:
        return _render(t("err_paths", exc=exc), True)
    apply_discovered_paths(cfg, discovery)
    save_config(cfg)
    return _render(t("ok_paths", summary=discovery.summary))


@app.post("/detect-docker")
def detect_docker():
    maybe = _require_login()
    if maybe is not None:
        return maybe
    t = _t()
    try:
        detections = detect_docker_installations()
    except RuntimeError as exc:
        return _render(t("err_docker", exc=exc), True)
    if not detections:
        return _render(t("err_no_docker"), True)
    detection = detections[0]
    cfg = load_config()
    cfg.install_mode = "docker"
    cfg.docker_nextcloud_container = detection.nextcloud_container
    cfg.docker_db_container = detection.db_container
    cfg.config_php_path = detection.config_php_path
    cfg.source_folders = detection.source_folders
    save_config(cfg)
    return _render(t("ok_docker", summary=detection.summary))


@app.post("/refresh-targets")
def refresh_targets():
    maybe = _require_login()
    if maybe is not None:
        return maybe
    t = _t()
    targets = list_backup_targets()
    if not targets:
        return _render(t("err_no_targets"), True)
    return _render(t("ok_targets", n=len(targets)))


@app.get("/check-space")
def check_space():
    maybe = _require_login()
    if maybe is not None:
        return jsonify({"ok": False, "message": _t()("err_login")}), 401
    cfg = load_config()
    result = check_backup_space(cfg)
    return jsonify(result.to_dict())


@app.post("/backup-now")
def run_backup_now():
    t = _t()
    maybe = _require_login()
    if maybe is not None:
        return jsonify({"ok": False, "message": t("err_login")}), 401

    cfg = load_config()
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


@app.get("/backup-status")
def backup_status():
    maybe = _require_login()
    if maybe is not None:
        return jsonify({"ok": False, "message": _t()("err_login")}), 401
    return jsonify(backup_tracker.snapshot())


@app.post("/save-schedule")
def save_schedule_route():
    maybe = _require_login()
    if maybe is not None:
        return maybe
    t = _t()
    cfg = load_config()
    try:
        cfg.schedule.enabled = bool(request.form.get("schedule_enabled"))
        cfg.schedule.hour = int(request.form.get("schedule_hour", cfg.schedule.hour))
        cfg.schedule.minute = int(request.form.get("schedule_minute", cfg.schedule.minute))
        weekdays_raw = request.form.get("schedule_weekdays", "0,1,2,3,4,5,6")
        weekdays = [int(part.strip()) for part in weekdays_raw.split(",") if part.strip()]
        cfg.schedule.weekdays = [day for day in weekdays if 0 <= day <= 6] or [0, 1, 2, 3, 4, 5, 6]
    except ValueError:
        return _render(t("err_schedule"), True)
    save_config(cfg)
    try:
        message = apply_schedule(cfg)
    except OSError as exc:
        return _render(t("err_schedule_apply", exc=exc), True)
    return _render(message)


@app.post("/restore")
def run_restore_route():
    maybe = _require_login()
    if maybe is not None:
        return maybe
    t = _t()
    cfg = load_config()
    backup_path = request.form.get("backup_path", "").strip()
    if not backup_path:
        return _render(t("err_backup_path"), True)
    options = RestoreOptions(
        restore_files=bool(request.form.get("restore_files")),
        restore_database=bool(request.form.get("restore_database")),
        maintenance_mode=bool(request.form.get("maintenance_mode")),
        delete_extra_files=bool(request.form.get("delete_extra_files")),
        gpg_passphrase=request.form.get("restore_gpg_passphrase", "").strip(),
    )
    result = run_restore(cfg, Path(backup_path), options)
    if result.success:
        return _render(result.message)
    return _render(t("err_restore", message=result.message, errors="; ".join(result.errors)), True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Nextcloud Backup Web-GUI")
    parser.add_argument("--host", default=os.environ.get("NC_BACKUP_WEB_HOST", DEFAULT_HOST))
    parser.add_argument("--port", type=int, default=int(os.environ.get("NC_BACKUP_WEB_PORT", DEFAULT_PORT)))
    args = parser.parse_args()

    print(f"Starte Web-GUI auf http://{args.host}:{args.port}")
    app.run(host=args.host, port=args.port, debug=False, threaded=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
