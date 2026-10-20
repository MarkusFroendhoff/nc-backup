const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const root = path.resolve(__dirname, '..');
const status = require(path.join(root, 'nextcloud-app/ncbackup/js/app.js'));

const MAINT_EN = 'Backup is running — Nextcloud is in maintenance mode.';
const MAINT_DE = 'Backup läuft – Nextcloud ist im Wartungsmodus.';

test('Nextcloud maintenance page is not a generic status error', () => {
	assert.equal(status.isMaintenanceResponse(503, '1', {}), true);
	assert.equal(status.isMaintenanceResponse(503, ' 1 ', {}), true);
	assert.equal(status.isMaintenanceResponse(503, true, { message: 'ignored because of the header' }), true);
	// HTML body: JSON parse fails and the caller passes {}.
	assert.equal(status.isMaintenanceResponse(503, null, {}), true);
	assert.equal(status.isMaintenanceResponse(503, '', null), true);
});

test('service and auth failures stay errors', () => {
	assert.equal(status.isMaintenanceResponse(400, null, {
		ok: false,
		message: 'nc-backup unreachable: connection refused',
	}), false);
	assert.equal(status.isMaintenanceResponse(400, null, {
		ok: false,
		message: 'Access key is invalid.',
	}), false);
	assert.equal(status.isMaintenanceResponse(403, '', {
		ok: false,
		message: 'Admins only.',
	}), false);
	assert.equal(status.isMaintenanceResponse(503, null, {
		ok: false,
		message: 'nc-backup HTTP 503',
	}), false);
	assert.equal(status.isMaintenanceResponse(500, null, {}), false);
	assert.equal(status.isMaintenanceResponse(200, null, { ok: true, running: false }), false);
});

test('maintenance starts polling and a finished backup stops it', () => {
	assert.equal(status.nextPollAction({ maintenance: true }, false), 'poll');
	assert.equal(status.nextPollAction({
		ok: true,
		data: { ok: true, running: true },
	}, false), 'poll');
	assert.equal(status.nextPollAction({
		ok: true,
		data: { ok: true, running: false, success: true },
	}, true), 'idle');
});

test('real errors do not start a loop, but an active loop keeps going', () => {
	const unreachable = {
		ok: false,
		data: { ok: false, message: 'nc-backup unreachable: timed out' },
	};
	assert.equal(status.nextPollAction(unreachable, false), 'idle');
	assert.equal(status.nextPollAction(unreachable, true), 'keep');
	assert.equal(status.nextPollAction({ transportError: true }, false), 'idle');
	assert.equal(status.nextPollAction({ transportError: true }, true), 'keep');
});

test('a late 503 cannot overwrite status recovered after maintenance', () => {
	let current = 0;
	let polling = false;
	function begin() {
		return ++current;
	}
	function finish(seq, result) {
		const decision = status.interpretStatusResult(seq, current, result, polling);
		if (decision.ignore) {
			return decision;
		}
		if (decision.action === 'poll') {
			polling = true;
		} else if (decision.action === 'idle') {
			polling = false;
		}
		return decision;
	}

	const during = begin();
	const first = finish(during, { ok: false, maintenance: true, data: {} });
	assert.equal(first.maintenance, true);
	assert.equal(first.action, 'poll');
	assert.equal(polling, true);

	const after = begin();
	const recovered = finish(after, {
		ok: true,
		maintenance: false,
		data: { ok: true, running: false, success: true },
	});
	assert.equal(recovered.action, 'idle');
	assert.equal(polling, false);

	const late = finish(during, { ok: false, maintenance: true, data: {} });
	assert.equal(late.ignore, true);
	assert.equal(polling, false);
});

test('translations and release versions', () => {
	const de = JSON.parse(fs.readFileSync(path.join(root, 'nextcloud-app/ncbackup/l10n/de.json'), 'utf8'));
	assert.equal(de.translations[MAINT_EN], MAINT_DE);
	const deJs = fs.readFileSync(path.join(root, 'nextcloud-app/ncbackup/l10n/de.js'), 'utf8');
	assert.ok(deJs.includes(MAINT_EN));
	assert.ok(deJs.includes(MAINT_DE));
	const appJs = fs.readFileSync(path.join(root, 'nextcloud-app/ncbackup/js/app.js'), 'utf8');
	assert.ok(appJs.includes(MAINT_EN));

	const info = fs.readFileSync(path.join(root, 'nextcloud-app/ncbackup/appinfo/info.xml'), 'utf8');
	assert.match(info, /<version>1\.3\.4<\/version>/);
	const changelog = fs.readFileSync(path.join(root, 'debian/changelog'), 'utf8');
	assert.match(changelog, /^nc-backup \(2\.1\.2-1\)/);
	const pyproject = fs.readFileSync(path.join(root, 'pyproject.toml'), 'utf8');
	assert.match(pyproject, /version = "2\.1\.2"/);
});
