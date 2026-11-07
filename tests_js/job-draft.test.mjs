import test from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const { isExcluded, collectElements, parseDraft } = require('../static/js/job-draft.js');

const TTL = 7 * 24 * 60 * 60 * 1000;
const NOW = 1_700_000_000_000;

function field(overrides) {
    return Object.assign({ name: 'title', type: 'text', value: '', checked: false }, overrides);
}

test('isExcluded: чувствительные и служебные поля не попадают в черновик', () => {
    const excluded = [
        { name: 'csrfmiddlewaretoken', type: 'hidden' },
        { name: 'lat', type: 'hidden' },
        { name: 'lng', type: 'text' },
        { name: 'avatar', type: 'file' },
        { name: 'password', type: 'password' },
        { name: 'save', type: 'submit' },
        { name: 'preview', type: 'button' },
        { type: 'text' },
    ];
    for (const el of excluded) {
        assert.equal(isExcluded(el), true, JSON.stringify(el));
    }
    assert.equal(isExcluded({ name: 'title', type: 'text' }), false);
    assert.equal(isExcluded({ name: 'agree', type: 'checkbox' }), false);
});

test('collectElements: пустые значения не создают черновик', () => {
    const draft = collectElements([
        field({ name: 'title', value: '   ' }),
        field({ name: 'description', value: '' }),
    ]);
    assert.equal(draft, null);
});

test('collectElements: собирает массивы, пропускает неотмеченные и исключённые', () => {
    const draft = collectElements([
        field({ name: 'title', value: 'Уборка' }),
        field({ name: 'skills', value: '1' }),
        field({ name: 'skills', value: '2' }),
        field({ name: 'agree', type: 'checkbox', checked: false }),
        field({ name: 'remote', type: 'checkbox', checked: true, value: '1' }),
        field({ name: 'lat', type: 'hidden', value: '55.7' }),
    ]);

    assert.deepEqual(draft.fields, {
        title: ['Уборка'],
        skills: ['1', '2'],
        remote: ['1'],
    });
    assert.equal(typeof draft.saved_at, 'number');
});

test('parseDraft: валидный черновик возвращается', () => {
    const draft = { saved_at: NOW - 1000, fields: { title: ['Уборка'] } };
    assert.deepEqual(parseDraft(JSON.stringify(draft), NOW, TTL), draft);
});

test('parseDraft: просроченный черновик отбрасывается', () => {
    const draft = { saved_at: NOW - TTL - 1, fields: { title: ['Уборка'] } };
    assert.equal(parseDraft(JSON.stringify(draft), NOW, TTL), null);
});

test('parseDraft: битый JSON отбрасывается', () => {
    assert.equal(parseDraft('{not json', NOW, TTL), null);
});

test('parseDraft: неполные данные отбрасываются', () => {
    assert.equal(parseDraft('', NOW, TTL), null);
    assert.equal(parseDraft(JSON.stringify({ fields: {} }), NOW, TTL), null);
    assert.equal(parseDraft(JSON.stringify({ saved_at: NOW }), NOW, TTL), null);
});
