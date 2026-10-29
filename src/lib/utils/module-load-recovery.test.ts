import { describe, expect, it, vi } from 'vitest';
import { recoverFromModuleLoadError } from './module-load-recovery';

const importError = () =>
	new TypeError('Failed to fetch dynamically imported module: https://example.com/_app/node.js');

function setup() {
	const values = new Map<string, string>();
	const storage = {
		getItem: (key: string) => values.get(key) ?? null,
		setItem: (key: string, value: string) => values.set(key, value)
	};
	const reload = vi.fn();
	return { values, storage, options: { storage: () => storage, reload, now: () => 100_000 } };
}

describe('module download recovery', () => {
	it.each([
		'Failed to fetch dynamically imported module: https://example.com/_app/node.js',
		'error loading dynamically imported module: https://example.com/_app/node.js',
		'Importing a module script failed.'
	])('retries a browser import failure: %s', (message) => {
		const { options, values } = setup();
		options.reload.mockImplementation(() => expect([...values.values()]).toEqual(['100000']));
		expect(recoverFromModuleLoadError(new TypeError(message), options)).toBe(true);
		expect(options.reload).toHaveBeenCalledOnce();
	});

	it('keeps the retry limit across page loads and allows a later retry', () => {
		const { storage, options } = setup();
		expect(recoverFromModuleLoadError(importError(), options)).toBe(true);
		const nextPage = { storage: () => storage, reload: vi.fn(), now: () => 159_999 };
		expect(recoverFromModuleLoadError(importError(), nextPage)).toBe(false);
		expect(nextPage.reload).not.toHaveBeenCalled();
		expect(recoverFromModuleLoadError(importError(), { ...nextPage, now: () => 160_000 })).toBe(
			true
		);
	});

	it.each([
		new TypeError('Failed to fetch'),
		new Error('Failed to fetch dynamically imported module: https://example.com/node.js'),
		new ReferenceError('missing is not defined'),
		new SyntaxError('Unexpected token'),
		'Failed to fetch dynamically imported module: https://example.com/node.js',
		null
	])('does not reload for unrelated errors: %s', (error) => {
		const { options, values } = setup();
		expect(recoverFromModuleLoadError(error, options)).toBe(false);
		expect(options.reload).not.toHaveBeenCalled();
		expect(values.size).toBe(0);
	});

	it.each(['access', 'getItem', 'setItem'])('does not reload if storage fails at %s', (stage) => {
		const { options, storage } = setup();
		const fail = () => {
			throw new Error('Storage unavailable');
		};
		if (stage === 'access') options.storage = fail;
		else storage[stage as 'getItem' | 'setItem'] = fail;
		expect(recoverFromModuleLoadError(importError(), options)).toBe(false);
		expect(options.reload).not.toHaveBeenCalled();
	});

	it('replaces a corrupt retry marker', () => {
		const { options, values } = setup();
		recoverFromModuleLoadError(importError(), options);
		for (const key of values.keys()) values.set(key, 'invalid');
		expect(recoverFromModuleLoadError(importError(), options)).toBe(true);
		expect([...values.values()]).toEqual(['100000']);
	});

	it('keeps the guard if navigation throws', () => {
		const { options } = setup();
		options.reload.mockImplementationOnce(() => {
			throw new Error('Navigation failed');
		});
		expect(recoverFromModuleLoadError(importError(), options)).toBe(false);
		expect(recoverFromModuleLoadError(importError(), options)).toBe(false);
		expect(options.reload).toHaveBeenCalledOnce();
	});
});
