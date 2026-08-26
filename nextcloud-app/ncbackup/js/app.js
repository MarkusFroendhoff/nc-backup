document.addEventListener('DOMContentLoaded', function () {
	const targetEl = document.getElementById('ncbackup-target');
	const pathEl = document.getElementById('ncbackup-path');
	const startBtn = document.getElementById('ncbackup-start');
	const refreshBtn = document.getElementById('ncbackup-refresh');
	const logEl = document.getElementById('ncbackup-log');
	const barEl = document.getElementById('ncbackup-bar');
	if (!targetEl || !startBtn) {
		return;
	}

	let pollTimer = null;

	function headers() {
		return {
			requesttoken: OC.requestToken,
			'Content-Type': 'application/json',
			Accept: 'application/json',
		};
	}

	function request(url, options) {
		return fetch(url, Object.assign({ credentials: 'same-origin', headers: headers() }, options))
			.then(function (response) {
				return response.json().then(function (data) {
					return { ok: response.ok, data: data };
				});
			});
	}

	function show(text) {
		logEl.textContent = text;
	}

	function setBar(percent) {
		barEl.style.width = Math.max(0, Math.min(100, percent || 0)) + '%';
	}

	function loadTargets() {
		targetEl.innerHTML = '<option value="">' + t('ncbackup', 'Loading targets…') + '</option>';
		request(OC.generateUrl('/apps/ncbackup/targets'), { method: 'GET' })
			.then(function (result) {
				const data = result.data || {};
				const targets = data.targets || [];
				targetEl.innerHTML = '';
				const empty = document.createElement('option');
				empty.value = '';
				empty.textContent = t('ncbackup', 'Choose a target');
				targetEl.appendChild(empty);
				targets.forEach(function (item) {
					const option = document.createElement('option');
					option.value = item.path;
					option.textContent = item.display || item.path;
					if (item.selected) {
						option.selected = true;
					}
					targetEl.appendChild(option);
				});
				if (data.export_path && !pathEl.value) {
					pathEl.value = data.export_path;
				}
				if (!result.ok || data.ok === false) {
					show(data.message || t('ncbackup', 'Could not load targets.'));
				}
			})
			.catch(function (err) {
				show(String(err));
			});
	}

	targetEl.addEventListener('change', function () {
		if (targetEl.value) {
			pathEl.value = targetEl.value;
		}
	});

	function formatStatus(data) {
		if (data.running) {
			setBar(data.percent);
			return (data.percent || 0) + '%  ' + (data.phase || '') + '\n' + (data.detail || '');
		}
		if (data.success === true) {
			setBar(100);
			return (data.message || t('ncbackup', 'Backup finished.')) + (data.destination ? '\n' + data.destination : '');
		}
		if (data.success === false) {
			return data.message || t('ncbackup', 'Backup failed.');
		}
		return JSON.stringify(data, null, 2);
	}

	function pollStatus() {
		request(OC.generateUrl('/apps/ncbackup/status'), { method: 'GET' })
			.then(function (result) {
				if (!result.data) {
					return;
				}
				show(formatStatus(result.data));
				if (!result.data.running && pollTimer) {
					clearInterval(pollTimer);
					pollTimer = null;
				}
			})
			.catch(function (err) {
				show(String(err));
			});
	}

	refreshBtn.addEventListener('click', loadTargets);

	startBtn.addEventListener('click', function () {
		const exportPath = (pathEl.value || targetEl.value || '').trim();
		if (!exportPath) {
			show(t('ncbackup', 'Please choose a backup target.'));
			return;
		}
		startBtn.disabled = true;
		show(t('ncbackup', 'Starting backup…'));
		setBar(1);
		request(OC.generateUrl('/apps/ncbackup/start'), {
			method: 'POST',
			body: JSON.stringify({ export_path: exportPath }),
		}).then(function (result) {
			startBtn.disabled = false;
			if (!result.ok || (result.data && result.data.ok === false)) {
				show((result.data && result.data.message) || t('ncbackup', 'Could not start backup.'));
				return;
			}
			show((result.data && result.data.message) || t('ncbackup', 'Backup started.'));
			if (pollTimer) {
				clearInterval(pollTimer);
			}
			pollTimer = setInterval(pollStatus, 2000);
			pollStatus();
		}).catch(function (err) {
			startBtn.disabled = false;
			show(String(err));
		});
	});

	loadTargets();
});
