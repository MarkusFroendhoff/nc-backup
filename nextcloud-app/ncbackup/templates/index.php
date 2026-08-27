<?php

declare(strict_types=1);

/** @var \OCP\IL10N $l */
/** @var array $_ */
?>
<div id="ncbackup-app" class="ncbackup-wrap">
	<div class="ncbackup-panel">
	<?php if (empty($_['is_admin'])): ?>
		<p><?php p($l->t('Only administrators can start backups.')); ?></p>
	<?php else: ?>
		<header class="ncbackup-header">
			<h2><?php p($l->t('NC Backup')); ?></h2>
			<p class="ncbackup-lead">
				<?php p($l->t('Choose a local destination, configure the schedule, and start a backup. Restore stays in the nc-backup web UI.')); ?>
			</p>
			<p class="ncbackup-lead">
				<a href="<?php p($_['settings_url']); ?>"><?php p($l->t('Access key and URL are set under Settings → NC Backup.')); ?></a>
			</p>
		</header>

		<?php if (empty($_['has_token'])): ?>
			<p class="ncbackup-warn">
				<?php p($l->t('No access key yet.')); ?>
				<a href="<?php p($_['settings_url']); ?>"><?php p($l->t('Enter it in the settings first.')); ?></a>
			</p>
		<?php endif; ?>

		<section class="ncbackup-section ncbackup-run">
			<h3><?php p($l->t('Run now')); ?></h3>
			<p id="ncbackup-destination" class="ncbackup-lead"><?php p($l->t('Loading…')); ?></p>
			<p id="ncbackup-ready" class="ncbackup-lead">
				<?php p($l->t('Uses the destination configured above / in nc-backup.')); ?>
			</p>
			<p class="ncbackup-actions">
				<button type="button" id="ncbackup-start" class="primary"><?php p($l->t('Start backup now')); ?></button>
				<button type="button" id="ncbackup-refresh"><?php p($l->t('Refresh')); ?></button>
			</p>
			<div class="ncbackup-progress" aria-hidden="true">
				<div id="ncbackup-bar"></div>
			</div>
			<pre id="ncbackup-log" class="ncbackup-log"></pre>
		</section>

		<section class="ncbackup-section">
			<h3><?php p($l->t('Backup destination')); ?></h3>
			<label for="ncbackup-target"><?php p($l->t('Local target')); ?></label>
			<div class="ncbackup-row">
				<select id="ncbackup-target">
					<option value=""><?php p($l->t('Loading targets…')); ?></option>
				</select>
			</div>
			<p>
				<label for="ncbackup-path"><?php p($l->t('Or enter a path')); ?></label>
				<input type="text" id="ncbackup-path" placeholder="/mnt/backup" autocomplete="off" />
			</p>
			<p class="ncbackup-actions">
				<button type="button" id="ncbackup-save-dest"><?php p($l->t('Save destination')); ?></button>
			</p>
			<p class="ncbackup-hint"><?php p($l->t('Cloud targets (SFTP, S3, …) are configured in the nc-backup web UI.')); ?></p>
		</section>

		<section class="ncbackup-section">
			<h3><?php p($l->t('Scheduled backups')); ?></h3>
			<p class="ncbackup-row">
				<label class="ncbackup-check" for="ncbackup-sched-enabled">
					<input type="checkbox" id="ncbackup-sched-enabled" />
					<?php p($l->t('Enable daily schedule')); ?>
				</label>
			</p>
			<p>
				<label for="ncbackup-sched-time"><?php p($l->t('Time (HH:MM)')); ?></label>
				<input type="time" id="ncbackup-sched-time" value="02:30" />
			</p>
			<p class="ncbackup-actions">
				<button type="button" id="ncbackup-save-sched"><?php p($l->t('Save schedule')); ?></button>
			</p>
		</section>
	<?php endif; ?>
	</div>
</div>
