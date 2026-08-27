<?php

declare(strict_types=1);

return [
	'routes' => [
		['name' => 'page#index', 'url' => '/', 'verb' => 'GET'],
		['name' => 'backup#start', 'url' => '/start', 'verb' => 'POST'],
		['name' => 'backup#status', 'url' => '/status', 'verb' => 'GET'],
		['name' => 'backup#targets', 'url' => '/targets', 'verb' => 'GET'],
		['name' => 'backup#setDestination', 'url' => '/destination', 'verb' => 'POST'],
		['name' => 'backup#setSchedule', 'url' => '/schedule', 'verb' => 'POST'],
		['name' => 'settings#save', 'url' => '/settings', 'verb' => 'POST'],
	],
];
