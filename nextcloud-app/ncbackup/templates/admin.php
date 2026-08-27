<?php

declare(strict_types=1);

/** @var \OCP\IL10N $l */
/** @var array $_ */
?>
<div id="ncbackup-admin" class="section">
	<h2><?php p($l->t('NC Backup')); ?></h2>
	<p class="settings-hint">
		<?php p($l->t('Connection to the nc-backup 1.8 service. Use the web access key from /etc/nc-backup/web-token. Start backups from the NC Backup app icon.')); ?>
	</p>

	<p>
		<label for="ncbackup-url"><?php p($l->t('nc-backup URL')); ?></label>
		<input type="url" id="ncbackup-url" value="<?php p($_['backup_url']); ?>" placeholder="http://127.0.0.1:42173" />
	</p>
	<p>
		<label for="ncbackup-token"><?php p($l->t('Access key')); ?></label>
		<input type="text" id="ncbackup-token" autocomplete="off" spellcheck="false"
			placeholder="<?php p($_['has_token'] ? $l->t('Key is set – paste a new one to replace it') : $l->t('Paste the key from /etc/nc-backup/web-token')); ?>" />
	</p>
	<p>
		<button type="button" id="ncbackup-save" class="primary"><?php p($l->t('Save settings')); ?></button>
	</p>
	<p id="ncbackup-save-status" class="settings-hint"></p>
</div>
