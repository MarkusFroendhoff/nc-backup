<?php

declare(strict_types=1);

namespace OCA\NcBackup\Controller;

use OCP\AppFramework\Controller;
use OCP\AppFramework\Http\DataResponse;
use OCP\IConfig;
use OCP\IGroupManager;
use OCP\IRequest;
use OCP\IUserSession;

class SettingsController extends Controller {
	public function __construct(
		string $appName,
		IRequest $request,
		private IConfig $config,
		private IUserSession $userSession,
		private IGroupManager $groupManager,
	) {
		parent::__construct($appName, $request);
	}

	public function save(): DataResponse {
		if (!$this->isAdmin()) {
			return new DataResponse(['ok' => false, 'message' => 'Admins only.'], 403);
		}

		$backupUrl = trim((string)$this->request->getParam('backup_url', ''));
		$apiToken = trim((string)$this->request->getParam('api_token', ''));

		if ($backupUrl !== '') {
			$this->config->setAppValue('ncbackup', 'backup_url', rtrim($backupUrl, '/'));
		}
		if ($apiToken !== '') {
			$this->config->setAppValue('ncbackup', 'api_token', $apiToken);
		}

		$stored = $this->config->getAppValue('ncbackup', 'api_token', '') !== '';
		return new DataResponse([
			'ok' => true,
			'has_token' => $stored,
			'backup_url' => $this->config->getAppValue('ncbackup', 'backup_url', 'http://127.0.0.1:42173'),
		]);
	}

	private function isAdmin(): bool {
		$user = $this->userSession->getUser();
		return $user !== null && $this->groupManager->isAdmin($user->getUID());
	}
}
