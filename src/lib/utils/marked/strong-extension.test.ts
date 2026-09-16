import { describe, expect, it } from 'vitest';
import { Marked } from 'marked';

import { relaxedStrong } from './strong-extension';

const marked = new Marked(relaxedStrong);
const standard = new Marked();

describe('relaxed strong emphasis', () => {
	const sentences = [
		'这是一段用于测试 Markdown 加粗渲染的中文文本。',
		'This is an English sentence for testing Markdown bold rendering.'
	];

	for (const sentence of sentences) {
		for (const suffix of ['', '测试', 'Test']) {
			for (const space of ['', ' ']) {
				it(`renders ${JSON.stringify(sentence + space)} followed by ${JSON.stringify(suffix)}`, () => {
					expect(marked.parseInline(`**${sentence}${space}**${suffix}`)).toBe(
						`<strong>${sentence}${space}</strong>${suffix}`
					);
				});
			}
		}
	}

	it('handles adjacent prose and multiple bold spans', () => {
		expect(marked.parseInline('前文**中文。**测试，**English. **Test，**正常**。')).toBe(
			'前文<strong>中文。</strong>测试，<strong>English. </strong>Test，<strong>正常</strong>。'
		);
	});

	it('preserves inline formatting inside a relaxed bold span', () => {
		expect(marked.parseInline('**包含 *斜体* 和 `代码`。**测试')).toBe(
			'<strong>包含 <em>斜体</em> 和 <code>代码</code>。</strong>测试'
		);
	});

	it.each([
		['**包含 `**`。**测试', '<strong>包含 <code>**</code>。</strong>测试'],
		[
			'**包含 [链接](https://example.com/**)。**测试',
			'<strong>包含 <a href="https://example.com/**">链接</a>。</strong>测试'
		],
		['**包含 \\*\\*。**测试', '<strong>包含 **。</strong>测试'],
		[
			'**包含 <span title="**">标签</span>。**测试',
			'<strong>包含 <span title="**">标签</span>。</strong>测试'
		]
	])('does not close bold at masked delimiters in %s', (src, html) => {
		expect(marked.parseInline(src)).toBe(html);
	});

	it.each([
		'**正常粗体**和**另一段**',
		'__bold__ and _italic_',
		'***bold italic***',
		'**outer *inner* text**',
		'**outer **inner** text**',
		'**outer *inner***',
		'**line one\nline two**',
		'** leading whitespace**',
		'** **',
		'**',
		'**尚未结束。*',
		'\\*\\*literal。\\*\\*测试',
		'`**literal。**测试`',
		'```md\n**literal。**测试\n```',
		'[link](https://example.com/**literal.**suffix)',
		'<code>**literal。**测试</code>'
	])('preserves existing Markdown behavior for %s', (src) => {
		expect(marked.parse(src)).toBe(standard.parse(src));
	});

	it('renders a streamed span once its closing delimiter arrives', () => {
		const src = '**中文。 **测试';
		for (let end = 1; end < src.indexOf('**', 2) + 2; end++) {
			expect(marked.parseInline(src.slice(0, end))).toBe(standard.parseInline(src.slice(0, end)));
		}
		expect(marked.parseInline(src)).toBe('<strong>中文。 </strong>测试');
	});
});
