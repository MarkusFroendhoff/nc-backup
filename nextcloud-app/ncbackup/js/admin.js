document.addEventListener('DOMContentLoaded', function () {
	const saveBtn = document.getElementById('ncbackup-save');
	if (!saveBtn) {
		return;
	}
	const urlEl = document.getElementById('ncbackup-url');
	const tokenEl = document.getElementById('ncbackup-token');
	const statusEl = document.getElementById('ncbackup-save-status');

	saveBtn.addEventListener('click', function () {
		saveBtn.disabled = true;
		statusEl.textContent = '';
		fetch(OC.generateUrl('/apps/ncbackup/settings'), {
			method: 'POST',
			credentials: 'same-origin',
			headers: {
				requesttoken: OC.requestToken,
				'Content-Type': 'application/json',
				Accept: 'application/json',
				'X-Requested-With': 'XMLHttpRequest',
			},
			body: JSON.stringify({
				backup_url: urlEl.value,
				api_token: tokenEl.value,
			}),
		}).then(function (response) {
			return response.json().then(function (data) {
				return { ok: response.ok, data: data };
			});
		}).then(function (result) {
			saveBtn.disabled = false;
			if (result.data && result.data.ok) {
				tokenEl.value = '';
				tokenEl.placeholder = t('ncbackup', 'Token is set – paste a new one to replace it');
				statusEl.textContent = t('ncbackup', 'Settings saved.');
			} else {
				statusEl.textContent = (result.data && result.data.message) || t('ncbackup', 'Could not save settings.');
			}
		}).catch(function (err) {
			saveBtn.disabled = false;
			statusEl.textContent = String(err);
		});
	});
});
