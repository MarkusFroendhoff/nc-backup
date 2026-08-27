<?php

declare(strict_types=1);

namespace OCA\NcBackup\Settings;

use OCP\AppFramework\Http\TemplateResponse;
use OCP\IConfig;
use OCP\Settings\ISettings;
use OCP\Util;

class AdminSettings implements ISettings {
	public function __construct(
		private IConfig $config,
	) {
	}

	public function getForm(): TemplateResponse {
		Util::addScript('ncbackup', 'admin');
		Util::addStyle('ncbackup', 'admin');
		return new TemplateResponse('ncbackup', 'admin', [
			'backup_url' => $this->config->getAppValue('ncbackup', 'backup_url', 'http://127.0.0.1:42173'),
			'has_token' => $this->config->getAppValue('ncbackup', 'api_token', '') !== '',
		]);
	}

	public function getSection(): string {
		return 'ncbackup';
	}

	public function getPriority(): int {
		return 0;
	}
}
