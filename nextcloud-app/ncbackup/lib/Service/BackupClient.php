<?php

declare(strict_types=1);

namespace OCA\NcBackup\Service;

use OCP\Http\Client\IClientService;
use OCP\IConfig;
use RuntimeException;
use Throwable;

class BackupClient {
	public function __construct(
		private IClientService $clientService,
		private IConfig $config,
	) {
	}

	public function startBackup(string $exportPath = ''): array {
		$payload = [];
		if ($exportPath !== '') {
			$payload['export_path'] = $exportPath;
		}
		return $this->request('POST', '/api/v1/backup', $payload);
	}

	public function status(): array {
		return $this->request('GET', '/api/v1/status');
	}

	public function targets(): array {
		return $this->request('GET', '/api/v1/targets');
	}

	public function isConfigured(): bool {
		return $this->config->getAppValue('ncbackup', 'api_token', '') !== '';
	}

	private function request(string $method, string $path, array $payload = []): array {
		$base = rtrim($this->config->getAppValue('ncbackup', 'backup_url', 'http://127.0.0.1:42173'), '/');
		$token = $this->config->getAppValue('ncbackup', 'api_token', '');
		if ($base === '' || $token === '') {
			throw new RuntimeException('Set the API token under Settings → NC Backup.');
		}

		$client = $this->clientService->newClient();
		$options = [
			'headers' => [
				'Authorization' => 'Bearer ' . $token,
				'Accept' => 'application/json',
			],
			'timeout' => 20,
			'nextcloud' => [
				'allow_local_address' => true,
			],
		];
		if ($payload !== []) {
			$options['json'] = $payload;
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
		if ($status === 401) {
			throw new RuntimeException('API token is invalid.');
		}
		if ($status >= 400 && empty($data['ok'])) {
			throw new RuntimeException((string)($data['message'] ?? ('nc-backup HTTP ' . $status)));
		}
		return $data;
	}
}
