import { readFileSync } from 'node:fs';
import { runInNewContext } from 'node:vm';
import { describe, expect, it } from 'vitest';

const html = readFileSync(new URL('../../app.html', import.meta.url), 'utf8');
const bootstrap = html.match(/<script>([\s\S]*?)<\/script>/)?.[1];
if (!bootstrap) throw new Error('Missing document language bootstrap');

function initialLanguage({
	search = '',
	locale = null,
	languages = ['zh-CN', 'en-US'],
	language = 'zh-CN',
	storageDenied = false
}: {
	search?: string;
	locale?: string | null;
	languages?: string[];
	language?: string;
	storageDenied?: boolean;
} = {}) {
	const document = { documentElement: { lang: 'en' } };
	runInNewContext(bootstrap!, {
		document,
		window: { location: { search } },
		navigator: { languages, language },
		localStorage: {
			getItem: () => {
				if (storageDenied) throw new Error('Storage access denied');
				return locale;
			}
		},
		URLSearchParams,
		Intl
	});
	return document.documentElement.lang;
}

describe('document language before app initialization', () => {
	it('uses the browser language on a first visit', () => {
		expect(initialLanguage()).toBe('zh-CN');
	});

	it('uses the saved interface language before the browser preference', () => {
		expect(initialLanguage({ locale: 'fr-FR' })).toBe('fr-FR');
	});

	it('gives the language URL parameter priority over saved preferences', () => {
		expect(initialLanguage({ search: '?lang=zh-TW', locale: 'en-US' })).toBe('zh-TW');
	});

	it('works when local storage access is denied', () => {
		expect(initialLanguage({ storageDenied: true })).toBe('zh-CN');
	});

	it('ignores malformed preferences and canonicalizes the next valid language', () => {
		expect(initialLanguage({ search: '?lang=not_a_locale', locale: 'zh-cn' })).toBe('zh-CN');
	});

	it('falls back to navigator.language and then English when no preference is available', () => {
		expect(initialLanguage({ languages: [], language: 'ja-JP' })).toBe('ja-JP');
		expect(initialLanguage({ languages: [], language: '' })).toBe('en');
	});
});
