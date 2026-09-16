import { Tokenizer, type MarkedExtension } from 'marked';

// Chat responses commonly put punctuation or a space before the closing **,
// immediately followed by more text. CommonMark does not treat that as a closer.
export const relaxedStrong: MarkedExtension = {
	tokenizer: {
		emStrong(this: Tokenizer, src, maskedSrc, prevChar) {
			// Preserve standard emphasis, including nested and triple delimiters.
			const token = Tokenizer.prototype.emStrong.call(this, src, maskedSrc, prevChar);
			if (token) return token;
			if (this.lexer.state.inRawBlock || !/^\*\*[^\s*]/.test(src)) return;

			// Marked masks code, links, HTML tags and escapes. Use the same mask so
			// literal asterisks inside those constructs cannot close the bold span.
			const delimiters = /\*{2,}/g;
			delimiters.lastIndex = 2;
			const closing = delimiters.exec(maskedSrc.slice(-src.length));
			if (!closing || closing[0] !== '**') return;

			const text = src.slice(2, closing.index);
			if (!/[\p{P}\p{S} \t]$/u.test(text)) return;

			return {
				type: 'strong',
				raw: src.slice(0, closing.index + 2),
				text,
				tokens: this.lexer.inlineTokens(text)
			};
		}
	}
};
