import { readdir, readFile } from 'node:fs/promises';
import path from 'node:path';
import ts from 'typescript';

const counts = { error: 0, log: 0, debug: 0 };
const violations = [];

async function inspect(directory) {
	for (const entry of await readdir(directory, { withFileTypes: true })) {
		const filename = path.join(directory, entry.name);
		if (entry.isDirectory()) {
			await inspect(filename);
		} else if (entry.name.endsWith('.js')) {
			const source = ts.createSourceFile(
				filename,
				await readFile(filename, 'utf8'),
				ts.ScriptTarget.Latest,
				true
			);
			function visit(node) {
				if (ts.isCallExpression(node)) {
					const callee = node.expression;
					const property = ts.isPropertyAccessExpression(callee)
						? callee.name.text
						: ts.isElementAccessExpression(callee) && ts.isStringLiteral(callee.argumentExpression)
							? callee.argumentExpression.text
							: null;
					if (
						property &&
						Object.hasOwn(counts, property) &&
						ts.isIdentifier(callee.expression) &&
						callee.expression.text === 'console'
					) {
						counts[property]++;
						if (property !== 'error') violations.push(`${filename}: console.${property}`);
					}
				}
				ts.forEachChild(node, visit);
			}
			visit(source);
		}
	}
}

await inspect(path.resolve('build/_app/immutable'));
if (violations.length || counts.error === 0) {
	throw new Error(
		`Production console check failed: ${JSON.stringify(counts)}\n${violations.join('\n')}`
	);
}
console.log(`Production console check passed: ${JSON.stringify(counts)}`);
