<?php

declare(strict_types=1);

namespace OCA\NcBackup\Controller;

use OCA\NcBackup\Service\BackupClient;
use OCP\AppFramework\Controller;
use OCP\AppFramework\Http\DataResponse;
use OCP\IGroupManager;
use OCP\IRequest;
use OCP\IUserSession;
use RuntimeException;

class BackupController extends Controller {
	public function __construct(
		string $appName,
		IRequest $request,
		private BackupClient $client,
		private IUserSession $userSession,
		private IGroupManager $groupManager,
	) {
		parent::__construct($appName, $request);
	}

	public function start(): DataResponse {
		if (!$this->isAdmin()) {
			return new DataResponse(['ok' => false, 'message' => 'Admins only.'], 403);
		}
		$exportPath = trim((string)$this->request->getParam('export_path', ''));
		try {
			return new DataResponse($this->client->startBackup($exportPath));
		} catch (RuntimeException $exception) {
			return new DataResponse(['ok' => false, 'message' => $exception->getMessage()], 400);
		}
	}

	public function status(): DataResponse {
		if (!$this->isAdmin()) {
			return new DataResponse(['ok' => false, 'message' => 'Admins only.'], 403);
		}
		try {
			return new DataResponse($this->client->status());
		} catch (RuntimeException $exception) {
			return new DataResponse(['ok' => false, 'message' => $exception->getMessage()], 400);
		}
	}

	public function targets(): DataResponse {
		if (!$this->isAdmin()) {
			return new DataResponse(['ok' => false, 'message' => 'Admins only.'], 403);
		}
		try {
			return new DataResponse($this->client->targets());
		} catch (RuntimeException $exception) {
			return new DataResponse(['ok' => false, 'message' => $exception->getMessage()], 400);
		}
	}

	private function isAdmin(): bool {
		$user = $this->userSession->getUser();
		return $user !== null && $this->groupManager->isAdmin($user->getUID());
	}
}
