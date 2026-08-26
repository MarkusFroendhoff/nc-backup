<?php

declare(strict_types=1);

namespace OCA\NcBackup\AppInfo;

use OCP\AppFramework\App;
use OCP\AppFramework\Bootstrap\IBootContext;
use OCP\AppFramework\Bootstrap\IBootstrap;
use OCP\AppFramework\Bootstrap\IRegistrationContext;
use OCP\IGroupManager;
use OCP\INavigationManager;
use OCP\IURLGenerator;
use OCP\IUserSession;
use OCP\L10N\IFactory;

class Application extends App implements IBootstrap {
	public const APP_ID = 'ncbackup';

	public function __construct() {
		parent::__construct(self::APP_ID);
	}

	public function register(IRegistrationContext $context): void {
	}

	public function boot(IBootContext $context): void {
		$context->injectFn([$this, 'registerNavigation']);
	}

	public function registerNavigation(
		INavigationManager $navigationManager,
		IURLGenerator $url,
		IUserSession $userSession,
		IGroupManager $groupManager,
		IFactory $l10nFactory,
	): void {
		$user = $userSession->getUser();
		if ($user === null || !$groupManager->isAdmin($user->getUID())) {
			return;
		}
		$l = $l10nFactory->get(self::APP_ID);
		$navigationManager->add(static function () use ($url, $l) {
			return [
				'id' => 'ncbackup',
				'order' => 80,
				'href' => $url->linkToRoute('ncbackup.page.index'),
				'icon' => $url->imagePath('ncbackup', 'app.svg'),
				'name' => $l->t('NC Backup'),
			];
		});
	}
}
