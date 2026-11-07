import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const read = (path) => readFileSync(join(root, path), 'utf8');

test('job-step: белый текст не используется на bg-primary-500', () => {
    const js = read('static/js/job-step.js');
    assert.equal(js.includes('bg-primary-500'), false, 'bg-primary-500 даёт 3.18:1 с белым текстом');
    assert.match(js, /border-primary-600 bg-primary-600 text-white/);
    assert.match(js, /bg-primary-600 hover:bg-primary-700 text-white/);
});

test('bulk-toolbar: фон следует теме, а не жёсткому #fafafa', () => {
    const css = read('static/css/app.css');
    assert.match(css, /\.bulk-toolbar\s*{[^}]*background:\s*var\(--ui-neutral-50\)/s);
    assert.doesNotMatch(css, /\.bulk-toolbar\s*{[^}]*background:\s*#fafafa/s);
});

test('dark hover primary-кнопок остаётся тёмным', () => {
    const css = read('static/css/app.css');
    assert.match(
        css,
        /\[data-theme="dark"\] \.hover\\:bg-primary-700:hover\s*{\s*background-color:\s*#92400e/s,
    );
    assert.match(
        css,
        /prefers-color-scheme: dark[\s\S]*?\.hover\\:bg-primary-700:hover\s*{\s*background-color:\s*#92400e/s,
    );
});
