<?php

declare(strict_types=1);

/** @var \OCP\IL10N $l */
/** @var array $_ */
?>
<div id="ncbackup-app" class="ncbackup-wrap">
	<?php if (empty($_['is_admin'])): ?>
		<p><?php p($l->t('Only administrators can start backups.')); ?></p>
	<?php else: ?>
		<header class="ncbackup-header">
			<h2><?php p($l->t('NC Backup')); ?></h2>
			<p class="ncbackup-lead">
				<?php p($l->t('Choose a target and start a backup. Restore stays in the nc-backup web UI.')); ?>
			</p>
			<p class="ncbackup-lead">
				<a href="<?php p($_['settings_url']); ?>"><?php p($l->t('API token and URL are set under Settings → NC Backup.')); ?></a>
			</p>
		</header>

		<?php if (empty($_['has_token'])): ?>
			<p class="ncbackup-warn">
				<?php p($l->t('No API token yet.')); ?>
				<a href="<?php p($_['settings_url']); ?>"><?php p($l->t('Enter it in the settings first.')); ?></a>
			</p>
		<?php endif; ?>

		<label for="ncbackup-target"><?php p($l->t('Backup target')); ?></label>
		<div class="ncbackup-row">
			<select id="ncbackup-target">
				<option value=""><?php p($l->t('Loading targets…')); ?></option>
			</select>
			<button type="button" id="ncbackup-refresh"><?php p($l->t('Refresh')); ?></button>
		</div>
		<p>
			<label for="ncbackup-path"><?php p($l->t('Or enter a path')); ?></label>
			<input type="text" id="ncbackup-path" placeholder="/mnt/backup" />
		</p>
		<p>
			<button type="button" id="ncbackup-start" class="primary"><?php p($l->t('Start backup now')); ?></button>
		</p>
		<div class="ncbackup-progress">
			<div id="ncbackup-bar"></div>
		</div>
		<pre id="ncbackup-log"></pre>
	<?php endif; ?>
</div>
