import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';

const source = readFileSync(new URL('../web/button-reveal.ts', import.meta.url), 'utf8');
const js = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText;
const main = readFileSync(new URL('../web/main.ts', import.meta.url), 'utf8');
const utilities = ts.transpileModule(main.slice(main.indexOf('function message('), main.indexOf('function actionButton(')), {}).outputText;
const mapView = ts.transpileModule(main.slice(main.indexOf('function renderMap('), main.indexOf('function renderOperator(')), {}).outputText;

function setup(disabled = false) {
  let now = 0, calls = 0;
  const timers = [], listeners = [];
  const scope = { exports: {}, window: { setTimeout: (callback, ms) => timers.push({ callback, at: now + ms }) } };
  vm.runInNewContext(js, scope);
  const node = {
    disabled, dataset: {}, inert: false, isConnected: true,
    addEventListener: (_, callback) => listeners.push(callback),
    click() {
      let stopped = false;
      const event = { preventDefault() {}, stopImmediatePropagation: () => { stopped = true; } };
      for (const listener of listeners) { listener(event); if (stopped) return; }
      if (!node.disabled) calls++;
    },
  };
  scope.exports.revealButtonAfterDelay(node);
  return {
    node, calls: () => calls,
    advance(ms) {
      now += ms;
      for (const timer of timers.splice(0)) {
        if (timer.at <= now) timer.callback(); else timers.push(timer);
      }
    },
  };
}

test('participant button blocks activation until the full three seconds have elapsed', () => {
  const h = setup();
  assert.equal(h.node.inert, true);
  assert.equal(h.node.dataset.reveal, 'waiting');
  h.node.click(); h.advance(2999); h.node.click();
  assert.equal(h.calls(), 0);
  h.advance(1);
  assert.equal(h.node.inert, false);
  assert.equal(h.node.dataset.reveal, 'ready');
  h.node.click();
  assert.equal(h.calls(), 1);
});

test('revealing a button preserves validation and network disabled state', () => {
  const h = setup(true);
  h.advance(3000);
  assert.equal(h.node.disabled, true);
  h.node.click();
  assert.equal(h.calls(), 0);
  h.node.disabled = false;
  h.node.click();
  assert.equal(h.calls(), 1);
});

test('a timer from the previous screen cannot reveal a new screen button', () => {
  const previous = setup(), next = setup();
  previous.node.isConnected = false;
  previous.advance(3000);
  assert.equal(previous.node.inert, true);
  assert.equal(next.node.inert, true);
  next.advance(3000);
  assert.equal(next.node.inert, false);
});

test('routine polling preserves recovery buttons so their delay can finish', () => {
  const makeHost = () => ({ dataset: {}, firstElementChild: null,
    replaceChildren() { this.firstElementChild = null; },
    append(child) { this.firstElementChild = child; } });
  const errors = makeHost(), pendingHost = makeHost();
  let createdButtons = 0;
  const scope = {
    document: { querySelector: selector => selector === '#errors' ? errors : pendingHost },
    el: () => ({ append() {} }), button: () => { createdButtons++; return {}; },
    content: () => ({ querySelectorAll: () => [] }),
    networkError: true, busy: false, pending: () => ({ name: 'nys_action' }),
  };
  vm.createContext(scope); vm.runInContext(utilities, scope);
  scope.message('Internet Error. Please reconnect.'); scope.updatePending();
  const firstError = errors.firstElementChild, firstPending = pendingHost.firstElementChild;
  scope.message('Internet Error. Please reconnect.'); scope.updatePending();
  scope.message('Internet Error. Please reconnect.'); scope.updatePending();
  assert.equal(errors.firstElementChild, firstError);
  assert.equal(pendingHost.firstElementChild, firstPending);
  assert.equal(createdButtons, 2);
  scope.busy = true; scope.updatePending();
  assert.equal(pendingHost.firstElementChild, null);
  scope.message();
  assert.equal(errors.firstElementChild, null);
});

test('Enter in the coordinate form cannot bypass the three-second button wait', () => {
  const h = setup(), nodes = [], actions = [];
  const scope = {
    el(tag) {
      const node = { tag, value: '', append() {}, querySelectorAll: () => [], reportValidity: () => true };
      nodes.push(node); return node;
    },
    actionButton: () => h.node,
    revealButtonAfterDelay() {},
    mountMap: () => ({ destroy() {}, setPin() {} }), updatePending() {},
    act: (...args) => actions.push(args),
  };
  vm.createContext(scope); vm.runInContext(mapView, scope);
  scope.renderMap({ classList: { add() {} }, append() {} }, { pin: { lat: 51.5, lng: 0.1 } });
  const form = nodes.find(node => node.tag === 'form');
  const event = { preventDefault() {} };
  form.onsubmit(event);
  assert.equal(actions.length, 0);
  h.advance(3000); h.node.disabled = true;
  form.onsubmit(event);
  assert.equal(actions.length, 0);
  h.node.disabled = false; form.onsubmit(event);
  assert.equal(actions.length, 1);
  assert.equal(actions[0][0], 'pin');
});
