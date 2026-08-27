document.addEventListener('DOMContentLoaded', function () {
	// Nextcloud content area often has overflow:hidden — enable scrolling for this app.
	(function enableAppScroll() {
		const root = document.getElementById('ncbackup-app');
		if (!root) {
			return;
		}
		let node = root.parentElement;
		while (node && node !== document.body) {
			const id = node.id || '';
			const cls = node.className || '';
			if (
				id === 'content' ||
				id === 'content-vue' ||
				id === 'app-content' ||
				id === 'app-content-vue' ||
				(typeof cls === 'string' && (cls.indexOf('app-content') !== -1 || cls.indexOf('app-ncbackup') !== -1))
			) {
				node.style.setProperty('overflow-y', 'auto', 'important');
				node.style.setProperty('overflow-x', 'hidden', 'important');
				node.style.setProperty('max-height', 'calc(100dvh - var(--header-height, 50px))', 'important');
			}
			node = node.parentElement;
		}
		document.documentElement.style.overflowY = 'auto';
		document.body.style.overflowY = 'auto';
	})();

	const startBtn = document.getElementById('ncbackup-start');
	const refreshBtn = document.getElementById('ncbackup-refresh');
	const saveDestBtn = document.getElementById('ncbackup-save-dest');
	const saveSchedBtn = document.getElementById('ncbackup-save-sched');
	const targetEl = document.getElementById('ncbackup-target');
	const pathEl = document.getElementById('ncbackup-path');
	const schedEnabledEl = document.getElementById('ncbackup-sched-enabled');
	const schedTimeEl = document.getElementById('ncbackup-sched-time');
	const logEl = document.getElementById('ncbackup-log');
	const barEl = document.getElementById('ncbackup-bar');
	const destEl = document.getElementById('ncbackup-destination');
	const readyEl = document.getElementById('ncbackup-ready');
	if (!startBtn) {
		return;
	}

	let pollTimer = null;

	function headers() {
		return {
			requesttoken: OC.requestToken,
			'Content-Type': 'application/json',
			Accept: 'application/json',
			'X-Requested-With': 'XMLHttpRequest',
		};
	}

	function request(url, options) {
		return fetch(url, Object.assign({ credentials: 'same-origin', headers: headers() }, options))
			.then(function (response) {
				return response.json().then(function (data) {
					return { ok: response.ok, data: data };
				}).catch(function () {
					return { ok: response.ok, data: {} };
				});
			});
	}

	function show(text) {
		if (logEl) {
			logEl.textContent = text;
		}
	}

	function setBar(percent) {
		if (barEl) {
			barEl.style.width = Math.max(0, Math.min(100, percent || 0)) + '%';
		}
	}

	function errMessage(data, fallback) {
		return (data && (data.message || data.error)) || fallback;
	}

	function normalizeTime(value) {
		const m = String(value || '').match(/^(\d{1,2}):(\d{2})/);
		if (!m) {
			return '02:30';
		}
		const h = Math.max(0, Math.min(23, parseInt(m[1], 10)));
		const min = Math.max(0, Math.min(59, parseInt(m[2], 10)));
		return String(h).padStart(2, '0') + ':' + String(min).padStart(2, '0');
	}

	function formatStatus(data) {
		const lines = [];
		if (data.destination) {
			lines.push(t('ncbackup', 'Destination') + ': ' + data.destination);
		}
		if (data.schedule) {
			const sched = data.schedule;
			if (sched.enabled) {
				lines.push(t('ncbackup', 'Schedule') + ': ' + (sched.on_calendar || '') + ' (' + t('ncbackup', 'enabled') + ')');
			} else {
				lines.push(t('ncbackup', 'Schedule') + ': ' + t('ncbackup', 'disabled'));
			}
		}
		if (data.ready === false && data.errors && data.errors.length) {
			lines.push(t('ncbackup', 'Not ready') + ': ' + data.errors.join('; '));
		}
		if (data.running) {
			setBar(data.percent || 50);
			lines.push((data.phase || 'backup') + ' …');
			if (data.detail) {
				lines.push(data.detail);
			}
			return lines.join('\n');
		}
		if (data.success === true) {
			setBar(100);
			lines.push(data.message || t('ncbackup', 'Backup finished.'));
			return lines.join('\n');
		}
		if (data.success === false) {
			setBar(0);
			lines.push(data.message || t('ncbackup', 'Backup failed.'));
			return lines.join('\n');
		}
		if (data.last_backup && data.last_backup.time) {
			lines.push(t('ncbackup', 'Last backup') + ': ' + data.last_backup.time);
		}
		if (!lines.length) {
			return t('ncbackup', 'Ready to start a backup.');
		}
		return lines.join('\n');
	}

	function applyMeta(data) {
		if (destEl && data.destination) {
			destEl.textContent = data.destination;
		}
		if (readyEl) {
			if (data.ready === false) {
				readyEl.textContent = t('ncbackup', 'nc-backup reports configuration problems — check the web UI.');
				readyEl.classList.add('ncbackup-warn');
			} else {
				readyEl.textContent = t('ncbackup', 'Uses the destination configured above / in nc-backup.');
				readyEl.classList.remove('ncbackup-warn');
			}
		}
		if (data.schedule && schedEnabledEl && schedTimeEl) {
			schedEnabledEl.checked = !!data.schedule.enabled;
			if (data.schedule.on_calendar) {
				schedTimeEl.value = normalizeTime(data.schedule.on_calendar);
			}
		}
	}

	function fillTargets(data) {
		if (!targetEl) {
			return;
		}
		const targets = data.targets || [];
		const selectedPath = data.local_path || '';
		targetEl.innerHTML = '';
		const empty = document.createElement('option');
		empty.value = '';
		empty.textContent = t('ncbackup', 'Choose a target');
		targetEl.appendChild(empty);
		targets.forEach(function (item) {
			const option = document.createElement('option');
			option.value = item.path;
			let label = item.display || item.path;
			if (item.free_gb != null) {
				label += ' (' + item.free_gb + ' GB)';
			}
			option.textContent = label;
			if (item.selected || (selectedPath && item.path === selectedPath)) {
				option.selected = true;
			}
			targetEl.appendChild(option);
		});
		if (pathEl) {
			if (selectedPath) {
				pathEl.value = selectedPath;
			} else if (targetEl.value) {
				pathEl.value = targetEl.value;
			}
		}
		if (destEl && data.destination_summary) {
			destEl.textContent = data.destination_summary;
		}
		if (data.schedule && schedEnabledEl && schedTimeEl) {
			schedEnabledEl.checked = !!data.schedule.enabled;
			schedTimeEl.value = normalizeTime(data.schedule.on_calendar || '02:30');
		}
	}

	function pollStatus() {
		request(OC.generateUrl('/apps/ncbackup/status'), { method: 'GET' })
			.then(function (result) {
				if (!result.data) {
					return;
				}
				if (!result.ok || result.data.ok === false) {
					show(errMessage(result.data, t('ncbackup', 'Could not load status.')));
					return;
				}
				applyMeta(result.data);
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

	function refresh() {
		request(OC.generateUrl('/apps/ncbackup/targets'), { method: 'GET' })
			.then(function (result) {
				if (!result.ok || (result.data && result.data.ok === false)) {
					show(errMessage(result.data, t('ncbackup', 'Could not load targets.')));
					return;
				}
				fillTargets(result.data || {});
			})
			.catch(function (err) {
				show(String(err));
			});
		pollStatus();
	}

	if (targetEl && pathEl) {
		targetEl.addEventListener('change', function () {
			if (targetEl.value) {
				pathEl.value = targetEl.value;
			}
		});
	}

	if (refreshBtn) {
		refreshBtn.addEventListener('click', refresh);
	}

	if (saveDestBtn) {
		saveDestBtn.addEventListener('click', function () {
			const path = ((pathEl && pathEl.value) || (targetEl && targetEl.value) || '').trim();
			if (!path) {
				show(t('ncbackup', 'Please choose a backup target.'));
				return;
			}
			saveDestBtn.disabled = true;
			request(OC.generateUrl('/apps/ncbackup/destination'), {
				method: 'POST',
				body: JSON.stringify({ local_path: path }),
			}).then(function (result) {
				saveDestBtn.disabled = false;
				if (!result.ok || (result.data && result.data.ok === false)) {
					show(errMessage(result.data, t('ncbackup', 'Could not save destination.')));
					return;
				}
				show(errMessage(result.data, t('ncbackup', 'Destination saved.')));
				if (destEl && result.data.destination_summary) {
					destEl.textContent = result.data.destination_summary;
				}
				refresh();
			}).catch(function (err) {
				saveDestBtn.disabled = false;
				show(String(err));
			});
		});
	}

	if (saveSchedBtn) {
		saveSchedBtn.addEventListener('click', function () {
			const enabled = !!(schedEnabledEl && schedEnabledEl.checked);
			const time = normalizeTime(schedTimeEl ? schedTimeEl.value : '02:30');
			saveSchedBtn.disabled = true;
			request(OC.generateUrl('/apps/ncbackup/schedule'), {
				method: 'POST',
				body: JSON.stringify({ enabled: enabled, on_calendar: time }),
			}).then(function (result) {
				saveSchedBtn.disabled = false;
				if (!result.ok || (result.data && result.data.ok === false)) {
					show(errMessage(result.data, t('ncbackup', 'Could not save schedule.')));
					return;
				}
				show(errMessage(result.data, t('ncbackup', 'Schedule saved.')));
				pollStatus();
			}).catch(function (err) {
				saveSchedBtn.disabled = false;
				show(String(err));
			});
		});
	}

	startBtn.addEventListener('click', function () {
		startBtn.disabled = true;
		show(t('ncbackup', 'Starting backup…'));
		setBar(1);
		request(OC.generateUrl('/apps/ncbackup/start'), {
			method: 'POST',
			body: '{}',
		}).then(function (result) {
			startBtn.disabled = false;
			if (!result.ok || (result.data && result.data.ok === false)) {
				show(errMessage(result.data, t('ncbackup', 'Could not start backup.')));
				return;
			}
			show(errMessage(result.data, t('ncbackup', 'Backup started.')));
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

	refresh();
});
