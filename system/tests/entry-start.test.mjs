import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';

// Exercise the real entry route and click handler without network or participant data.
const source = readFileSync(new URL('../web/main.ts', import.meta.url), 'utf8');
const entryCode = source.slice(source.indexOf('function renderEntry('), source.indexOf("window.addEventListener('popstate'"));
const js = ts.transpileModule(entryCode, { compilerOptions: { target: ts.ScriptTarget.ES2022 } }).outputText;

function setup(call) {
  const nodes = [], saved = new Map(), errors = [];
  let renderCount = 0;
  const scope = {
    configured: true, publicDisplayId: undefined, isOperator: false,
    participantId: undefined, snapshot: undefined, screenKey: '',
    location: { pathname: '/join', hash: '#token=synthetic-entry' },
    document: { body: { classList: { add() {} } } },
    sessionStorage: { setItem: (k, v) => saved.set(k, v) },
    history: { replaceState: (_, __, path) => { scope.location.pathname = path; scope.location.hash = ''; } },
    api: { init: async () => {}, call },
    el: () => ({ append() {} }),
    button: (text, click) => ({ text, click, disabled: false }),
    content: () => ({ append: (...items) => nodes.push(...items) }),
    shell() {}, clearContent() {}, message() {}, updatePending() {},
    renderParticipant: () => { renderCount++; }, startState: async () => {},
    handleError: error => errors.push(error), URLSearchParams,
  };
  vm.createContext(scope);
  vm.runInContext(js, scope);
  return { scope, nodes, saved, errors, renders: () => renderCount };
}
const flush = () => new Promise(resolve => setImmediate(resolve));

test('QR open does not claim; Start claims once and goes directly to consent', async () => {
  const calls = [];
  let finish;
  const h = setup((...args) => { calls.push(args); return new Promise(resolve => { finish = resolve; }); });
  await h.scope.start();
  assert.equal(calls.length, 0);
  const start = h.nodes.find(node => node.text === 'Start');
  start.click(); start.click();
  assert.equal(calls.length, 1);
  assert.equal(calls[0][0], 'nys_join');
  assert.equal(calls[0][1].p_token, 'synthetic-entry');
  assert.equal(start.disabled, true);
  finish({ participant: { id: 'synthetic-participant', generation: 2, step: 'consent' } });
  await flush();
  assert.equal(h.saved.get('nys-intro-synthetic-participant-2'), 'started');
  assert.equal(h.scope.location.pathname, '/participant/synthetic-participant');
  assert.equal(h.scope.location.hash, '');
  assert.equal(h.renders(), 1);
});

test('failed Start keeps the entry retryable without marking it started', async () => {
  let attempts = 0;
  const h = setup(async () => { attempts++; throw new Error('NETWORK'); });
  await h.scope.start();
  const start = h.nodes.find(node => node.text === 'Start');
  start.click(); await flush();
  assert.equal(start.disabled, false);
  assert.equal(h.saved.size, 0);
  assert.equal(h.scope.location.pathname, '/join');
  start.click(); await flush();
  assert.equal(attempts, 2);
  assert.equal(h.errors.length, 2);
});
