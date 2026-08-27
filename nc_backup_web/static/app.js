const SECRET_ERR = "Schlüssel muss Groß- und Kleinbuchstaben, Zahlen und ein Sonderzeichen enthalten.";
const TITLES = {
  overview: "Übersicht",
  setup: "Einrichtung",
  dest: "Ziel",
  schedule: "Zeitplan",
  restore: "Wiederherstellung",
  log: "Protokoll",
};

function isValidSecret(value) {
  if (!value) return false;
  const hasUpper = /[A-Z]/.test(value);
  const hasLower = /[a-z]/.test(value);
  const hasDigit = /[0-9]/.test(value);
  const hasSpecial = /[^A-Za-z0-9\s]/.test(value);
  return hasUpper && hasLower && hasDigit && hasSpecial;
}

async function api(path, opts = {}) {
  const res = await fetch(path, {
    credentials: "same-origin",
    headers: { "Content-Type": "application/json", ...(opts.headers || {}) },
    ...opts,
  });
  let data = {};
  try { data = await res.json(); } catch { data = {}; }
  if (res.status === 401 && path !== "/api/login") {
    showLogin();
    const err = new Error("Bitte zuerst anmelden.");
    err.auth = true;
    throw err;
  }
  if (!res.ok) {
    throw new Error(data.error || "Aktion fehlgeschlagen.");
  }
  return data;
}

function showLogin() {
  document.getElementById("login-screen").hidden = false;
  document.getElementById("app").hidden = true;
}
function showApp() {
  document.getElementById("login-screen").hidden = true;
  document.getElementById("app").hidden = false;
}

function setText(id, text) {
  const el = document.getElementById(id);
  if (el) el.textContent = text || "";
}
function setMsg(id, text, show) {
  const el = document.getElementById(id);
  if (!el) return;
  el.hidden = !show;
  el.textContent = text || "";
}

let currentPage = "overview";
let pollTimer = null;
let selectedSnap = null;
let wizStep = 1;
let destConfig = {};

function gotoPage(name) {
  currentPage = name;
  document.querySelectorAll(".page").forEach((p) => { p.hidden = true; });
  document.getElementById("page-" + name).hidden = false;
  document.getElementById("page-title").textContent = TITLES[name] || name;
  document.querySelectorAll(".nav button").forEach((b) => {
    b.classList.toggle("active", b.dataset.page === name);
  });
  if (name === "overview") loadOverview();
  if (name === "setup") initWizard();
  if (name === "dest") loadDest();
  if (name === "schedule") loadSchedule();
  if (name === "restore") loadSnaps();
  if (name === "log") loadLog();
}

function fmtTime(iso) {
  if (!iso) return "Noch keine";
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso;
    return d.toLocaleString("de-DE", { dateStyle: "medium", timeStyle: "short" });
  } catch {
    return iso;
  }
}

async function loadOverview() {
  const s = await api("/api/status");
  const pill = document.getElementById("ov-status");
  if (s.job && s.job.running) {
    pill.textContent = s.job.kind === "restore" ? "Wiederherstellung läuft" : "Sicherung läuft";
    pill.className = "status-pill busy";
  } else if (s.ready && s.nextcloud && s.nextcloud.found) {
    pill.textContent = "Bereit";
    pill.className = "status-pill ok";
  } else if (s.nextcloud && s.nextcloud.found) {
    pill.textContent = "Bitte einrichten";
    pill.className = "status-pill warn";
  } else {
    pill.textContent = "Nextcloud nicht gefunden";
    pill.className = "status-pill warn";
  }
  setText("ov-nc", (s.nextcloud && s.nextcloud.summary) || "");
  if (s.last_backup) {
    setText("ov-last", fmtTime(s.last_backup.time));
    setText("ov-last-id", s.last_backup.short_id ? "Punkt " + s.last_backup.short_id : "");
  } else {
    setText("ov-last", "Noch keine");
    setText("ov-last-id", "");
  }
  setText("ov-dest", s.destination || "Noch nicht eingerichtet");
  const sch = s.schedule || {};
  setText("ov-sched", sch.enabled ? "Täglich um " + (sch.on_calendar || "—") : "Kein automatischer Zeitplan");
  setText("ov-log", s.log_snippet || "Noch keine Meldungen.");
  const jobEl = document.getElementById("ov-job");
  if (s.job && s.job.running) {
    jobEl.textContent = "Bitte warten …";
    document.getElementById("btn-backup").disabled = true;
  } else {
    jobEl.textContent = s.job && s.job.message ? s.job.message : "";
    document.getElementById("btn-backup").disabled = false;
  }
}

async function startBackup() {
  setText("ov-job", "Sicherung wird gestartet …");
  try {
    await api("/api/backup", { method: "POST", body: "{}" });
    pollStatus();
  } catch (err) {
    setText("ov-job", err.message);
  }
}

function pollStatus() {
  if (pollTimer) clearInterval(pollTimer);
  pollTimer = setInterval(async () => {
    try {
      const s = await api("/api/status");
      if (currentPage === "overview") await loadOverview();
      if (!s.job || !s.job.running) {
        clearInterval(pollTimer);
        pollTimer = null;
      }
    } catch {
      clearInterval(pollTimer);
      pollTimer = null;
    }
  }, 2000);
}

function providerFields(provider, values, prefix) {
  const v = values || {};
  const id = (n) => prefix + "-" + n;
  if (provider === "local") {
    return [
      `<label for="${id("target-choice")}">Angeschlossene Laufwerke</label>`,
      `<select id="${id("target-choice")}"><option value="">Laufwerke werden geladen …</option></select>`,
      `<button type="button" class="btn" id="${prefix}-refresh-targets">Laufwerke neu einlesen</button>`,
      field("Ordner oder USB-Laufwerk", id("local_path"), v.local_path || ""),
    ].join("");
  }
  if (provider === "sftp") {
    return [
      field("Rechner", id("sftp_host"), v.sftp_host || ""),
      field("Benutzer", id("sftp_user"), v.sftp_user || ""),
      field("Ordner", id("sftp_path"), v.sftp_path || "/backups/nextcloud"),
      field("Passwort (optional)", id("sftp_password"), "", "password"),
    ].join("");
  }
  if (provider === "s3") {
    return [
      field("Adresse (Endpoint)", id("s3_endpoint"), v.s3_endpoint || "s3.amazonaws.com"),
      field("Bucket", id("s3_bucket"), v.s3_bucket || ""),
      field("Ordner im Bucket", id("s3_prefix"), v.s3_prefix || "nextcloud"),
      field("Zugangsschlüssel", id("s3_access_key"), v.s3_access_key || ""),
      field("Geheimschlüssel", id("s3_secret_key"), "", "password"),
      field("Region", id("s3_region"), v.s3_region || "eu-central-1"),
    ].join("");
  }
  if (provider === "webdav") {
    return [
      field("Adresse (URL)", id("webdav_url"), v.webdav_url || ""),
      field("Benutzer", id("webdav_user"), v.webdav_user || ""),
      field("Passwort", id("webdav_password"), "", "password"),
    ].join("");
  }
  if (provider === "azure") {
    return [
      field("Konto", id("azure_account"), v.azure_account || ""),
      field("Schlüssel", id("azure_key"), "", "password"),
      field("Container", id("azure_container"), v.azure_container || "nextcloud"),
    ].join("");
  }
  if (provider === "b2") {
    return [
      field("Konto-ID", id("b2_account_id"), v.b2_account_id || ""),
      field("Anwendungsschlüssel", id("b2_account_key"), "", "password"),
      field("Bucket", id("b2_bucket"), v.b2_bucket || ""),
    ].join("");
  }
  if (provider === "rclone") {
    return [
      field("Remote-Name", id("rclone_remote"), v.rclone_remote || ""),
      field("Pfad", id("rclone_path"), v.rclone_path || "nextcloud-backup"),
    ].join("");
  }
  return "";
}
function field(label, id, value, type) {
  const t = type || "text";
  const val = value == null ? "" : String(value).replace(/"/g, "&quot;");
  return `<label for="${id}">${label}</label><input id="${id}" type="${t}" value="${val}">`;
}
function collectFields(prefix, provider) {
  const g = (n) => {
    const el = document.getElementById(prefix + "-" + n);
    return el ? el.value : "";
  };
  const out = { provider };
  const keys = {
    local: ["local_path"],
    sftp: ["sftp_host", "sftp_user", "sftp_path", "sftp_password"],
    s3: ["s3_endpoint", "s3_bucket", "s3_prefix", "s3_access_key", "s3_secret_key", "s3_region"],
    webdav: ["webdav_url", "webdav_user", "webdav_password"],
    azure: ["azure_account", "azure_key", "azure_container"],
    b2: ["b2_account_id", "b2_account_key", "b2_bucket"],
    rclone: ["rclone_remote", "rclone_path"],
  };
  (keys[provider] || []).forEach((k) => { out[k] = g(k); });
  return out;
}

function setWizStep(n) {
  wizStep = n;
  [1, 2, 3, 4].forEach((i) => {
    document.getElementById("wiz-" + i).hidden = i !== n;
  });
  document.querySelectorAll("#wizard-steps li").forEach((li, idx) => {
    li.classList.toggle("on", idx === n - 1);
  });
  document.getElementById("wiz-back").hidden = n === 1;
  document.getElementById("wiz-next").textContent = n === 4 ? "Fertig" : "Weiter";
}

async function initWizard() {
  setWizStep(1);
  setMsg("wiz-msg", "", false);
  setMsg("wiz-err", "", false);
  await runDetect();
  renderWizFields();
  if (!document.getElementById("wiz-restic").value) {
    await regenPw();
  }
}

async function runDetect() {
  setText("wiz-nc", "Suche nach Nextcloud …");
  try {
    const d = await api("/api/detect");
    let line = d.summary || (d.found ? "Nextcloud gefunden." : "Keine Nextcloud gefunden.");
    if (d.data_dir) line += "\nDaten: " + d.data_dir;
    setText("wiz-nc", line);
  } catch (err) {
    setText("wiz-nc", err.message);
  }
}

function renderWizFields() {
  const prov = document.querySelector("#wiz-provider input:checked").value;
  document.getElementById("wiz-fields").innerHTML = providerFields(prov, destConfig, "wiz");
  if (prov === "local") {
    const refresh = document.getElementById("wiz-refresh-targets");
    if (refresh) refresh.onclick = () => fillTargets("wiz", document.getElementById("wiz-local_path") && document.getElementById("wiz-local_path").value);
    fillTargets("wiz", destConfig.local_path);
  }
}

async function regenPw() {
  const data = await api("/api/secret/new");
  document.getElementById("wiz-restic").value = data.secret || "";
  setMsg("wiz-pw-err", "", false);
}

async function wizardNext() {
  setMsg("wiz-err", "", false);
  if (wizStep === 1) { setWizStep(2); return; }
  if (wizStep === 2) { setWizStep(3); return; }
  if (wizStep === 3) {
    const pw = document.getElementById("wiz-restic").value;
    if (!pw) { setMsg("wiz-pw-err", "Ein leerer Schlüssel ist nicht erlaubt.", true); return; }
    if (!isValidSecret(pw)) { setMsg("wiz-pw-err", SECRET_ERR, true); return; }
    setMsg("wiz-pw-err", "", false);
    setWizStep(4);
    return;
  }
  const prov = document.querySelector("#wiz-provider input:checked").value;
  const body = collectFields("wiz", prov);
  body.restic_password = document.getElementById("wiz-restic").value;
  const t = document.getElementById("wiz-time").value || "02:30";
  body.on_calendar = t;
  body.enable_schedule = document.getElementById("wiz-enable").checked;
  try {
    const res = await api("/api/wizard", { method: "POST", body: JSON.stringify(body) });
    let msg = res.message || "Einrichtung gespeichert.";
    if (res.restic_password_once) {
      msg += " Sicherungskennwort (bitte notieren): " + res.restic_password_once;
    }
    setMsg("wiz-msg", msg, true);
    gotoPage("overview");
  } catch (err) {
    setMsg("wiz-err", err.message, true);
  }
}

async function fillTargets(prefix, current) {
  const sel = document.getElementById(prefix + "-target-choice");
  const pathEl = document.getElementById(prefix + "-local_path");
  if (!sel || !pathEl) return;
  try {
    const res = await api("/api/targets");
    const targets = res.targets || [];
    if (!targets.length) {
      sel.innerHTML = '<option value="">Kein USB- oder Netzlaufwerk gefunden</option>';
      return;
    }
    sel.innerHTML = '<option value="">— Laufwerk wählen —</option>' +
      targets.map((item) => {
        const path = String(item.path || "").replace(/"/g, "&quot;");
        const label = String(item.display || item.path || "").replace(/</g, "&lt;");
        const selAttr = current && item.path === current ? " selected" : "";
        return `<option value="${path}"${selAttr}>${label}</option>`;
      }).join("");
    sel.onchange = () => { if (sel.value) pathEl.value = sel.value; };
  } catch (err) {
    sel.innerHTML = '<option value="">Laufwerke konnten nicht gelesen werden</option>';
  }
}

async function loadDest() {
  try {
    const res = await api("/api/config");
    destConfig = (res.config && res.config.destination) || {};
    const prov = destConfig.provider || "local";
    document.getElementById("dest-provider").value = prov;
    document.getElementById("dest-fields").innerHTML = providerFields(prov, destConfig, "dest");
    document.getElementById("dest-restic").value = "";
    setMsg("dest-msg", "", false);
    setMsg("dest-err", "", false);
    const refresh = document.getElementById("dest-refresh-targets");
    if (refresh) refresh.onclick = () => fillTargets("dest", document.getElementById("dest-local_path").value);
    if (prov === "local") await fillTargets("dest", destConfig.local_path);
  } catch (err) {
    setMsg("dest-err", err.message || "Ziel konnte nicht geladen werden.", true);
  }
}

async function saveDest() {
  const prov = document.getElementById("dest-provider").value;
  const body = { destination: collectFields("dest", prov) };
  const pw = document.getElementById("dest-restic").value;
  if (pw) {
    if (!isValidSecret(pw)) { setMsg("dest-err", SECRET_ERR, true); return; }
    body.destination.restic_password = pw;
  }
  try {
    const res = await api("/api/config", { method: "POST", body: JSON.stringify(body) });
    let msg = res.message || "Gespeichert.";
    if (res.restic_password_once) msg += " Neues Kennwort: " + res.restic_password_once;
    setMsg("dest-msg", msg, true);
    setMsg("dest-err", "", false);
  } catch (err) {
    setMsg("dest-err", err.message, true);
  }
}

async function loadSchedule() {
  setMsg("sched-err", "", false);
  try {
    const res = await api("/api/config");
    const sch = (res.config && res.config.schedule) || {};
    document.getElementById("sched-enabled").checked = !!sch.enabled;
    let clock = sch.on_calendar || "02:30";
    if (/^\d{1,2}:\d{2}/.test(clock)) {
      const [h, m] = clock.split(":");
      clock = String(h).padStart(2, "0") + ":" + m.slice(0, 2);
    }
    document.getElementById("sched-time").value = clock;
  } catch (err) {
    setMsg("sched-err", err.message || "Zeitplan konnte nicht geladen werden.", true);
  }
}

async function saveSchedule() {
  setMsg("sched-err", "", false);
  const body = {
    enabled: document.getElementById("sched-enabled").checked,
    on_calendar: document.getElementById("sched-time").value || "02:30",
  };
  try {
    const res = await api("/api/schedule", { method: "POST", body: JSON.stringify(body) });
    setMsg("sched-msg", res.message || "Gespeichert.", true);
  } catch (err) {
    setMsg("sched-err", err.message || "Zeitplan konnte nicht gespeichert werden.", true);
  }
}

async function loadSnaps() {
  setMsg("rst-err", "", false);
  const ul = document.getElementById("snap-list");
  ul.innerHTML = "<li>Lade …</li>";
  try {
    const res = await api("/api/snapshots");
    const snaps = res.snapshots || [];
    if (!snaps.length) {
      ul.innerHTML = "<li>Keine Sicherungspunkte gefunden.</li>";
      return;
    }
    ul.innerHTML = "";
    snaps.forEach((s) => {
      const li = document.createElement("li");
      li.textContent = fmtTime(s.time) + "  ·  " + (s.short_id || s.id);
      li.dataset.id = s.id;
      li.addEventListener("click", () => {
        selectedSnap = s.id;
        ul.querySelectorAll("li").forEach((n) => n.classList.remove("sel"));
        li.classList.add("sel");
      });
      ul.appendChild(li);
    });
  } catch (err) {
    ul.innerHTML = "";
    setMsg("rst-err", err.message, true);
  }
}

async function doRestore() {
  setMsg("rst-err", "", false);
  if (!selectedSnap) {
    setMsg("rst-err", "Bitte einen Sicherungspunkt wählen.", true);
    return;
  }
  const dlg = document.getElementById("confirm-dlg");
  const ok = await new Promise((resolve) => {
    dlg.addEventListener("close", () => resolve(dlg.returnValue === "ok"), { once: true });
    dlg.showModal();
  });
  if (!ok) return;
  try {
    await api("/api/restore", {
      method: "POST",
      body: JSON.stringify({
        snapshot_id: selectedSnap,
        confirm: true,
        database: document.getElementById("rst-db").checked,
        config: document.getElementById("rst-cfg").checked,
        data: document.getElementById("rst-data").checked,
      }),
    });
    setMsg("rst-msg", "Wiederherstellung gestartet.", true);
    pollStatus();
  } catch (err) {
    setMsg("rst-err", err.message, true);
  }
}

async function loadLog() {
  const res = await api("/api/log");
  const text = [res.log, res.journal].filter(Boolean).join("\n\n—— Journal ——\n\n");
  setText("log-full", text || "Noch keine Einträge.");
}

async function boot() {
  try {
    await api("/api/status");
    showApp();
    gotoPage("overview");
  } catch (err) {
    showLogin();
  }
}

document.getElementById("login-form").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const key = document.getElementById("login-key").value;
  const errEl = document.getElementById("login-error");
  errEl.hidden = true;
  if (!key) {
    errEl.textContent = "Ein leerer Schlüssel ist nicht erlaubt.";
    errEl.hidden = false;
    return;
  }
  if (!isValidSecret(key)) {
    errEl.textContent = SECRET_ERR;
    errEl.hidden = false;
    return;
  }
  try {
    await api("/api/login", { method: "POST", body: JSON.stringify({ token: key }) });
    showApp();
    gotoPage("overview");
  } catch (err) {
    errEl.textContent = err.message;
    errEl.hidden = false;
  }
});

document.querySelectorAll(".nav button").forEach((b) => {
  b.addEventListener("click", () => gotoPage(b.dataset.page));
});
document.getElementById("btn-logout").addEventListener("click", async () => {
  try { await api("/api/logout", { method: "POST", body: "{}" }); } catch { /* ignore */ }
  showLogin();
});
document.getElementById("btn-backup").addEventListener("click", startBackup);
document.getElementById("btn-detect").addEventListener("click", runDetect);
document.getElementById("wiz-provider").addEventListener("change", renderWizFields);
document.getElementById("wiz-next").addEventListener("click", wizardNext);
document.getElementById("wiz-back").addEventListener("click", () => setWizStep(Math.max(1, wizStep - 1)));
document.getElementById("btn-regen-pw").addEventListener("click", regenPw);
document.getElementById("dest-provider").addEventListener("change", () => {
  const prov = document.getElementById("dest-provider").value;
  document.getElementById("dest-fields").innerHTML = providerFields(prov, destConfig, "dest");
  const refresh = document.getElementById("dest-refresh-targets");
  if (refresh) refresh.onclick = () => fillTargets("dest", document.getElementById("dest-local_path").value);
  if (prov === "local") fillTargets("dest", destConfig.local_path);
});
document.getElementById("btn-save-dest").addEventListener("click", saveDest);
document.getElementById("btn-save-sched").addEventListener("click", saveSchedule);
document.getElementById("btn-load-snaps").addEventListener("click", loadSnaps);
document.getElementById("btn-restore").addEventListener("click", doRestore);
document.getElementById("btn-refresh-log").addEventListener("click", loadLog);

boot();
