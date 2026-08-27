<?php

declare(strict_types=1);

namespace OCA\NcBackup\Settings;

use OCP\IL10N;
use OCP\IURLGenerator;
use OCP\Settings\IIconSection;

class AdminSection implements IIconSection {
	public function __construct(
		private IL10N $l,
		private IURLGenerator $url,
	) {
	}

	public function getID(): string {
		return 'ncbackup';
	}

	public function getName(): string {
		return $this->l->t('NC Backup');
	}

	public function getPriority(): int {
		return 80;
	}

	public function getIcon(): string {
		return $this->url->imagePath('ncbackup', 'app.svg');
	}
}
