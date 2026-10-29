import { afterEach, describe, expect, it, vi } from 'vitest';
import { handleError } from './hooks.client';

afterEach(() => {
	vi.restoreAllMocks();
	vi.unstubAllGlobals();
});

function setup(current: string) {
	const values = new Map<string, string>();
	const browser = {
		location: { href: current, reload: vi.fn(), replace: vi.fn() },
		history: { state: { existing: true }, replaceState: vi.fn() },
		sessionStorage: {
			getItem: (key: string) => values.get(key) ?? null,
			setItem: (key: string, value: string) => values.set(key, value)
		}
	};
	vi.stubGlobal('window', browser);
	const log = vi.spyOn(console, 'error').mockImplementation(() => {});
	const error = new TypeError(
		'Failed to fetch dynamically imported module: https://example.com/a.js'
	);
	const failAt = (url: string) =>
		handleError({
			error,
			event: { url: new URL(url), params: {}, route: { id: '/' } },
			status: 500,
			message: 'Internal Error'
		});
	return { browser, log, error, failAt };
}

describe('client error recovery navigation', () => {
	it('reloads the initial URL even with a fragment, preserves the error and limits retries', () => {
		const url = 'https://example.com/?q=hello#message';
		const { browser, log, error, failAt } = setup(url);
		failAt(url);
		expect(browser.location.reload).toHaveBeenCalledOnce();
		expect(browser.location.replace).not.toHaveBeenCalled();
		expect(browser.history.replaceState).not.toHaveBeenCalled();
		expect(log).toHaveBeenCalledWith(error);
		failAt(url);
		expect(browser.location.reload).toHaveBeenCalledOnce();
		expect(log).toHaveBeenCalledTimes(2);
	});

	it('preserves the intended route, query and fragment when navigation fails', () => {
		const { browser, failAt } = setup('https://example.com/');
		const target = 'https://example.com/c/chat?q=hello#message';
		failAt(target);
		expect(browser.location.replace).toHaveBeenCalledWith(target);
		expect(browser.location.reload).not.toHaveBeenCalled();
	});

	it('updates a changed fragment before reloading the same path and query', () => {
		const { browser, failAt } = setup('https://example.com/c/chat?q=hello#old');
		const target = 'https://example.com/c/chat?q=hello#new';
		failAt(target);
		expect(browser.history.replaceState).toHaveBeenCalledWith(browser.history.state, '', target);
		expect(browser.location.reload).toHaveBeenCalledOnce();
		expect(browser.location.replace).not.toHaveBeenCalled();
	});
});
