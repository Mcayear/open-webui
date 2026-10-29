const RETRY_KEY = 'open-webui:module-load-retry';
const RETRY_INTERVAL_MS = 60_000;

type RecoveryOptions = {
	storage: () => Pick<Storage, 'getItem' | 'setItem'>;
	reload: () => void;
	now?: () => number;
};

export function recoverFromModuleLoadError(error: unknown, options: RecoveryOptions): boolean {
	if (
		!(error instanceof TypeError) ||
		!/^(Failed to fetch dynamically imported module:|error loading dynamically imported module:|Importing a module script failed\.?$)/i.test(
			error.message
		)
	) {
		return false;
	}

	try {
		const storage = options.storage();
		const now = (options.now ?? Date.now)();
		const lastRetry = storage.getItem(RETRY_KEY);
		if (lastRetry !== null && Math.abs(now - Number(lastRetry)) < RETRY_INTERVAL_MS) {
			return false;
		}

		// Persist before navigating so another failed import cannot cause a reload loop.
		// If session storage is unavailable, leave the original error page visible.
		storage.setItem(RETRY_KEY, String(now));
		options.reload();
		return true;
	} catch {
		return false;
	}
}
