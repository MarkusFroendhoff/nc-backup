<?php

declare(strict_types=1);

namespace OCA\NcBackup\Service;

use OCP\Http\Client\IClientService;
use OCP\IConfig;
use RuntimeException;
use Throwable;

/**
 * Client for nc-backup 1.8.x web API (Bearer = Inhalt von /etc/nc-backup/web-token).
 */
class BackupClient {
	public function __construct(
		private IClientService $clientService,
		private IConfig $config,
	) {
	}

	public function startBackup(): array {
		return $this->request('POST', '/api/backup', []);
	}

	public function status(): array {
		return $this->request('GET', '/api/status');
	}

	public function targets(): array {
		return $this->request('GET', '/api/targets');
	}

	public function config(): array {
		return $this->request('GET', '/api/config');
	}

	/**
	 * Set local backup destination path (provider=local).
	 */
	public function setLocalDestination(string $localPath): array {
		$path = trim($localPath);
		if ($path === '') {
			throw new RuntimeException('Destination path is empty.');
		}
		return $this->request('POST', '/api/config', [
			'provider' => 'local',
			'local_path' => $path,
		]);
	}

	public function setSchedule(bool $enabled, string $onCalendar): array {
		$time = trim($onCalendar);
		if ($time === '') {
			$time = '02:30';
		}
		return $this->request('POST', '/api/schedule', [
			'enabled' => $enabled,
			'on_calendar' => $time,
		]);
	}

	public function isConfigured(): bool {
		return $this->config->getAppValue('ncbackup', 'api_token', '') !== '';
	}

	private function request(string $method, string $path, array $payload = []): array {
		$base = rtrim($this->config->getAppValue('ncbackup', 'backup_url', 'http://127.0.0.1:42173'), '/');
		$token = $this->config->getAppValue('ncbackup', 'api_token', '');
		if ($base === '' || $token === '') {
			throw new RuntimeException('Set the access key under Settings → NC Backup.');
		}

		$client = $this->clientService->newClient();
		$options = [
			'headers' => [
				'Authorization' => 'Bearer ' . $token,
				'Accept' => 'application/json',
				'X-NC-Backup-Token' => $token,
			],
			'timeout' => 20,
			'nextcloud' => [
				'allow_local_address' => true,
			],
		];
		if ($method === 'POST') {
			$options['headers']['Content-Type'] = 'application/json';
			$options['body'] = json_encode($payload);
		}

		try {
			if ($method === 'POST') {
				$response = $client->post($base . $path, $options);
			} else {
				$response = $client->get($base . $path, $options);
			}
		} catch (Throwable $exception) {
			throw new RuntimeException('nc-backup unreachable: ' . $exception->getMessage(), 0, $exception);
		}

		$body = $response->getBody();
		$data = json_decode(is_string($body) ? $body : (string)$body, true);
		if (!is_array($data)) {
			throw new RuntimeException('Invalid response from nc-backup.');
		}
		$status = $response->getStatusCode();
		$error = (string)($data['error'] ?? $data['message'] ?? '');
		if ($status === 401 || $status === 403) {
			throw new RuntimeException($error !== '' ? $error : 'Access key is invalid.');
		}
		if ($status >= 400 && empty($data['ok'])) {
			throw new RuntimeException($error !== '' ? $error : ('nc-backup HTTP ' . $status));
		}
		return $data;
	}
}
