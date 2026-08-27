<?php

declare(strict_types=1);

namespace OCA\NcBackup\Controller;

use OCA\NcBackup\Service\BackupClient;
use OCP\AppFramework\Controller;
use OCP\AppFramework\Http\Attribute\NoCSRFRequired;
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
		try {
			$data = $this->client->startBackup();
			return new DataResponse([
				'ok' => true,
				'message' => (string)($data['message'] ?? 'Backup started.'),
			]);
		} catch (RuntimeException $exception) {
			return new DataResponse(['ok' => false, 'message' => $exception->getMessage()], 400);
		}
	}

	/**
	 * @NoCSRFRequired
	 */
	#[NoCSRFRequired]
	public function status(): DataResponse {
		if (!$this->isAdmin()) {
			return new DataResponse(['ok' => false, 'message' => 'Admins only.'], 403);
		}
		try {
			$data = $this->client->status();
			return new DataResponse($this->normalizeStatus($data));
		} catch (RuntimeException $exception) {
			return new DataResponse(['ok' => false, 'message' => $exception->getMessage()], 400);
		}
	}

	/**
	 * @NoCSRFRequired
	 */
	#[NoCSRFRequired]
	public function targets(): DataResponse {
		if (!$this->isAdmin()) {
			return new DataResponse(['ok' => false, 'message' => 'Admins only.'], 403);
		}
		try {
			$targets = $this->client->targets();
			$config = $this->client->config();
			$cfg = is_array($config['config'] ?? null) ? $config['config'] : [];
			$dest = is_array($cfg['destination'] ?? null) ? $cfg['destination'] : [];
			$localPath = (string)($dest['local_path'] ?? '');
			$provider = (string)($dest['provider'] ?? 'local');
			$schedule = is_array($cfg['schedule'] ?? null) ? $cfg['schedule'] : [];

			$list = [];
			foreach (($targets['targets'] ?? []) as $item) {
				if (!is_array($item)) {
					continue;
				}
				$path = (string)($item['path'] ?? '');
				$list[] = [
					'path' => $path,
					'label' => (string)($item['label'] ?? ''),
					'kind' => (string)($item['kind'] ?? ''),
					'display' => (string)($item['display'] ?? $path),
					'writable' => (bool)($item['writable'] ?? false),
					'free_gb' => $item['free_gb'] ?? null,
					'selected' => $provider === 'local' && $path !== '' && $path === $localPath,
				];
			}

			return new DataResponse([
				'ok' => true,
				'targets' => $list,
				'local_path' => $localPath,
				'provider' => $provider,
				'destination_summary' => (string)($cfg['destination_summary'] ?? ''),
				'schedule' => [
					'enabled' => (bool)($schedule['enabled'] ?? false),
					'on_calendar' => (string)($schedule['on_calendar'] ?? '02:30'),
				],
			]);
		} catch (RuntimeException $exception) {
			return new DataResponse(['ok' => false, 'message' => $exception->getMessage(), 'targets' => []], 400);
		}
	}

	public function setDestination(): DataResponse {
		if (!$this->isAdmin()) {
			return new DataResponse(['ok' => false, 'message' => 'Admins only.'], 403);
		}
		$path = trim((string)$this->request->getParam('local_path', ''));
		if ($path === '') {
			$path = trim((string)$this->request->getParam('path', ''));
		}
		try {
			$data = $this->client->setLocalDestination($path);
			$cfg = is_array($data['config'] ?? null) ? $data['config'] : [];
			return new DataResponse([
				'ok' => true,
				'message' => (string)($data['message'] ?? 'Destination saved.'),
				'destination_summary' => (string)($cfg['destination_summary'] ?? ''),
				'local_path' => (string)(($cfg['destination']['local_path'] ?? $path)),
			]);
		} catch (RuntimeException $exception) {
			return new DataResponse(['ok' => false, 'message' => $exception->getMessage()], 400);
		}
	}

	public function setSchedule(): DataResponse {
		if (!$this->isAdmin()) {
			return new DataResponse(['ok' => false, 'message' => 'Admins only.'], 403);
		}
		$enabledRaw = $this->request->getParam('enabled', false);
		$enabled = filter_var($enabledRaw, FILTER_VALIDATE_BOOLEAN, FILTER_NULL_ON_FAILURE);
		if ($enabled === null) {
			$enabled = in_array((string)$enabledRaw, ['1', 'true', 'on', 'yes'], true);
		}
		$time = trim((string)$this->request->getParam('on_calendar', ''));
		if ($time === '') {
			$time = trim((string)$this->request->getParam('time', '02:30'));
		}
		if (!preg_match('/^\d{1,2}:\d{2}$/', $time)) {
			return new DataResponse(['ok' => false, 'message' => 'Time must be HH:MM.'], 400);
		}
		try {
			$data = $this->client->setSchedule((bool)$enabled, $time);
			return new DataResponse([
				'ok' => true,
				'message' => (string)($data['message'] ?? 'Schedule saved.'),
				'schedule' => [
					'enabled' => (bool)$enabled,
					'on_calendar' => $time,
				],
			]);
		} catch (RuntimeException $exception) {
			return new DataResponse(['ok' => false, 'message' => $exception->getMessage()], 400);
		}
	}

	/**
	 * @param array<string, mixed> $data
	 * @return array<string, mixed>
	 */
	private function normalizeStatus(array $data): array {
		$job = is_array($data['job'] ?? null) ? $data['job'] : [];
		$running = !empty($job['running']);
		$ok = array_key_exists('ok', $job) ? $job['ok'] : null;
		$percent = 0;
		if ($running) {
			$percent = 50;
		} elseif ($ok === true) {
			$percent = 100;
		}

		$errors = [];
		if (is_array($data['errors'] ?? null)) {
			$errors = array_values(array_map('strval', $data['errors']));
		}

		return [
			'ok' => true,
			'running' => $running,
			'success' => $running ? null : $ok,
			'message' => (string)($job['message'] ?? ''),
			'percent' => $percent,
			'phase' => (string)($job['kind'] ?? ''),
			'detail' => (string)($data['log_snippet'] ?? ''),
			'destination' => (string)($data['destination'] ?? ''),
			'ready' => (bool)($data['ready'] ?? false),
			'errors' => $errors,
			'nextcloud' => is_array($data['nextcloud'] ?? null) ? $data['nextcloud'] : [],
			'schedule' => is_array($data['schedule'] ?? null) ? $data['schedule'] : [],
			'last_backup' => $data['last_backup'] ?? null,
		];
	}

	private function isAdmin(): bool {
		$user = $this->userSession->getUser();
		return $user !== null && $this->groupManager->isAdmin($user->getUID());
	}
}
