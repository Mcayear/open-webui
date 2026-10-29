import type { HandleClientError } from '@sveltejs/kit';
import { recoverFromModuleLoadError } from '$lib/utils/module-load-recovery';

export const handleError: HandleClientError = ({ error, event }) => {
	console.error(error);
	recoverFromModuleLoadError(error, {
		storage: () => window.sessionStorage,
		reload: () => {
			const current = new URL(window.location.href);
			if (
				current.origin === event.url.origin &&
				current.pathname === event.url.pathname &&
				current.search === event.url.search
			) {
				// Replacing a URL with a fragment can be a same-document navigation.
				if (current.hash !== event.url.hash) {
					window.history.replaceState(window.history.state, '', event.url.href);
				}
				window.location.reload();
			} else {
				window.location.replace(event.url.href);
			}
		}
	});
};
