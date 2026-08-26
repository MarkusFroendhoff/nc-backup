<?php

declare(strict_types=1);

namespace OCA\NcBackup\Controller;

use OCA\NcBackup\Service\BackupClient;
use OCP\AppFramework\Controller;
use OCP\AppFramework\Http\Attribute\NoCSRFRequired;
use OCP\AppFramework\Http\TemplateResponse;
use OCP\IGroupManager;
use OCP\IRequest;
use OCP\IURLGenerator;
use OCP\IUserSession;
use OCP\Util;

class PageController extends Controller {
	public function __construct(
		string $appName,
		IRequest $request,
		private BackupClient $client,
		private IUserSession $userSession,
		private IGroupManager $groupManager,
		private IURLGenerator $url,
	) {
		parent::__construct($appName, $request);
	}

	/**
	 * @NoCSRFRequired
	 */
	#[NoCSRFRequired]
	public function index(): TemplateResponse {
		Util::addScript('ncbackup', 'app');
		Util::addStyle('ncbackup', 'app');
		$isAdmin = $this->isAdmin();
		return new TemplateResponse('ncbackup', 'index', [
			'is_admin' => $isAdmin,
			'has_token' => $isAdmin && $this->client->isConfigured(),
			'settings_url' => $this->url->linkToRoute('settings.AdminSettings.index', ['section' => 'ncbackup']),
		]);
	}

	private function isAdmin(): bool {
		$user = $this->userSession->getUser();
		return $user !== null && $this->groupManager->isAdmin($user->getUID());
	}
}
