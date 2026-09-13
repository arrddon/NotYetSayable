import './style.css';
import QRCode from 'qrcode';
import { Api, ApiError, configured, demo } from './api';
import { mountMap } from './map';
import type { Created, OperatorState, Participant, Snapshot } from './types';

const app = document.querySelector<HTMLElement>('#app')!;
const isOperator = location.pathname === '/operator';
const api = new Api(isOperator);
let snapshot: Snapshot | undefined;
let operatorState: OperatorState | undefined;
let participantId = location.pathname.match(/^\/participant\/([0-9a-f-]+)$/i)?.[1];
let busy = false;
let refreshing = false;
let networkError = !navigator.onLine;
let revoked = false;
let serverOffset = 0;
let screenKey = '';
let cleanupMap: (() => void) | undefined;
let unsubscribe: (() => void) | undefined;
let selectedSession = sessionStorage.getItem('nys-selected-session') ?? '';
type Pending = { name: string; args: Record<string, unknown> };
type SavedEntry = { token: string; generation: number };
const entries: Record<string, SavedEntry> = JSON.parse(sessionStorage.getItem('nys-entries') ?? '{}');
const pendingKey = () => `nys-pending-${isOperator ? 'operator' : participantId ?? 'join'}`;
const pending = (): Pending | null => JSON.parse(sessionStorage.getItem(pendingKey()) ?? 'null');
const statusNames: Record<string, string> = {
  consent: 'Consent', tutorial: 'Instructions', question: 'Response', map: 'Map', complete: 'Complete',
  ready: 'Ready', countdown: 'Countdown', processing: 'Processing', result: 'Result ready', error: 'Error',
};

function el<K extends keyof HTMLElementTagNameMap>(tag: K, text?: string, cls?: string): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (cls) node.className = cls;
  return node;
}
function button(text: string, action: () => void, disabled = false) {
  const node = el('button', text);
  node.type = 'button'; node.disabled = disabled;
  node.addEventListener('click', action);
  return node;
}
function link(text: string, href: string) { const node = el('a', text); node.href = href; return node; }
function content() { return document.querySelector<HTMLElement>('#content')!; }
function clearContent() { cleanupMap?.(); cleanupMap = undefined; content().replaceChildren(); }
function shell() {
  app.replaceChildren(el('h1', isOperator ? 'Operator' : 'Not Yet Sayable'));
  if (demo) app.append(el('p', 'Demo mode', 'notice'));
  const errors = el('div'); errors.id = 'errors'; errors.setAttribute('role', 'alert');
  const pendingBox = el('div'); pendingBox.id = 'pending';
  const main = el('div'); main.id = 'content';
  app.append(errors, pendingBox, main);
}
function message(text = '') {
  const host = document.querySelector<HTMLElement>('#errors')!;
  host.replaceChildren();
  if (!text) return;
  const box = el('div', undefined, 'error'); box.append(el('p', text));
  if (networkError) box.append(button('Reconnect', () => { void refresh(); }));
  host.append(box);
}
function updatePending() {
  const host = document.querySelector<HTMLElement>('#pending')!;
  host.replaceChildren();
  if (pending() && !busy) {
    const box = el('div', undefined, 'notice');
    box.append(el('p', 'Your last request is awaiting confirmation.'),
      button('Check request', () => { const item = pending(); if (item) void mutate(item.name, item.args, true); }));
    host.append(box);
  }
  content().querySelectorAll<HTMLButtonElement>('button[data-action]').forEach((b) => {
    b.disabled = busy || networkError || Boolean(pending()) || b.dataset.unavailable === 'true';
  });
}
function actionButton(text: string, action: () => void, unavailable = false) {
  const b = button(text, action, unavailable || busy || networkError || Boolean(pending()));
  b.dataset.action = 'true'; b.dataset.unavailable = String(unavailable); return b;
}
function handleError(error: unknown) {
  const e = error instanceof ApiError ? error : new ApiError(String(error));
  networkError = e.network;
  if (networkError) message('Internet Error. Please reconnect.');
  else {
    const descriptions: Record<string, string> = {
      STALE_STATE: 'Updating your current step.',
      STALE_GENERATION: 'Please scan your new QR code.',
      ENTRY_EXPIRED: 'This QR code has expired. Please ask the operator.',
      ENTRY_IN_USE: 'This QR code is already in use. Please ask the operator.',
      FORBIDDEN: isOperator ? 'Operator access required. Please sign in with an authorised account.' : 'Please scan your new QR code.',
      INVALID_TRANSITION: 'Updating your current step. Please try again.',
      INVALID_COORDINATES: 'Please select a valid location.',
    };
    const code = Object.keys(descriptions).find((key) => e.message.includes(key));
    message(code ? descriptions[code] : (isOperator ? `Request failed: ${e.message}` : 'Unable to continue. Please ask the operator.'));
    if (!isOperator && code && ['FORBIDDEN','STALE_GENERATION'].includes(code)) {
      revoked = true; clearContent(); content().append(el('p', 'Please scan your new QR code.'));
    }
  }
  updatePending();
}

async function mutate(name: string, args: Record<string, unknown>, replay = false) {
  if (busy || (!replay && pending())) return;
  busy = true; message();
  sessionStorage.setItem(pendingKey(), JSON.stringify({ name, args })); updatePending();
  try {
    const result = await api.call<unknown>(name, args);
    sessionStorage.removeItem(pendingKey()); networkError = false;
    if (name === 'nys_action') {
      snapshot = result as Snapshot;
      history.replaceState(null, '', `/participant/${participantId}`);
      screenKey = ''; renderParticipant();
    } else if (name === 'nys_create_session') {
      const created = result as Created;
      selectedSession = created.session_id;
      sessionStorage.setItem('nys-selected-session', selectedSession);
      for (const entry of created.entries) entries[entry.id] = { token: entry.token, generation: 1 };
      sessionStorage.setItem('nys-entries', JSON.stringify(entries));
    } else if (name === 'nys_operator_action') {
      const updated = result as { snapshot: Snapshot; token: string | null };
      if (updated.token) {
        entries[updated.snapshot.participant.id] = { token: updated.token, generation: updated.snapshot.participant.generation };
        sessionStorage.setItem('nys-entries', JSON.stringify(entries));
      }
      screenKey = '';
    }
    await refresh();
  } catch (error) {
    if (!(error instanceof ApiError && error.network)) {
      sessionStorage.removeItem(pendingKey());
      await refresh();
    }
    handleError(error);
  } finally { busy = false; updatePending(); }
}
function act(action: string, data: Record<string, unknown> = {}) {
  if (!snapshot) return;
  const p = snapshot.participant;
  void mutate('nys_action', { p_id: p.id, p_generation: p.generation, p_revision: p.revision,
    p_request_id: crypto.randomUUID(), p_action: action, p_data: data });
}
function operatorAct(p: Participant, action: string) {
  if (action === 'reset' && !confirm(`Reset participant ${p.slot}? Their current QR code will expire.`)) return;
  void mutate('nys_operator_action', { p_id: p.id, p_generation: p.generation, p_revision: p.revision,
    p_request_id: crypto.randomUUID(), p_action: action });
}

function renderParticipant() {
  if (!snapshot || revoked) return;
  const p = snapshot.participant;
  const requestedReview = Number(new URLSearchParams(location.search).get('review'));
  const review = !['countdown','processing'].includes(p.status)
    ? snapshot.responses.find((r) => r.question === requestedReview) : undefined;
  const key = [p.id, p.generation, p.revision, review?.question ?? ''].join(':');
  if (key === screenKey) return;
  screenKey = key; clearContent();
  const host = content();
  host.append(el('p', p.slot, 'muted'));
  if (review) {
    host.append(el('p', 'Step ' + review.question));
    const actions = el('div', undefined, 'actions');
    actions.append(actionButton('Repeat this step', () => act('revisit', { question: review.question })),
      button('Return', () => { history.pushState(null, '', '/participant/' + p.id); renderParticipant(); }));
    host.append(actions);
  } else if (p.step === 'consent') {
    host.append(el('h2', 'Consent'));
    const label = el('label'); const check = el('input'); check.type = 'checkbox';
    label.append(check, ' I agree to take part and have my written responses captured and processed.');
    const next = actionButton('Agree and begin', () => act('consent'), true);
    check.onchange = () => { next.dataset.unavailable = String(!check.checked); updatePending(); };
    host.append(label, next);
  } else if (p.step === 'tutorial') {
    host.append(el('p', 'Follow the instructions on the installation.'), actionButton('Continue', () => act('tutorial')));
  } else if (p.step === 'question') {
    if (p.status === 'ready') host.append(actionButton('Confirm', () => act('confirm')));
    else if (p.status === 'countdown') {
      const counter = el('p'); counter.id = 'countdown'; host.append(counter); tick();
    } else if (p.status === 'processing') host.append(el('p', 'Please wait…'));
    else if (p.status === 'error') host.append(actionButton('Try Again', () => act('retry')));
    else host.append(el('p', 'Look at the installation.'), actionButton('Continue', () => act('continue')));
  } else if (p.step === 'map') renderMap(host, p);
  else host.append(el('p', 'Thank you.'));
  // Optional recovery controls. Never render question copy, transcripts, or analysis on the phone.
  if (snapshot.responses.length && !['countdown','processing'].includes(p.status)) {
    const details = el('details'); details.append(el('summary', 'Repeat a step'));
    const nav = el('nav', undefined, 'actions');
    for (const r of snapshot.responses) {
      const a = link('Step ' + r.question, '/participant/' + p.id + '?review=' + r.question);
      a.onclick = (event) => { event.preventDefault(); history.pushState(null, '', a.href); renderParticipant(); };
      nav.append(a);
    }
    details.append(nav); host.append(details);
  }
  updatePending();
}

function renderMap(host: HTMLElement, p: Participant) {
  host.append(el('h2', 'Pin a place'), el('p', 'Tap the map to choose a place.'));
  const mapHost = el('div'); mapHost.id = 'map';
  const mapMessage = el('p', '', 'muted'); mapMessage.id = 'map-message';
  const form = el('form'); const lat = el('input'); const lng = el('input');
  for (const input of [lat, lng]) { input.type = 'number'; input.step = 'any'; input.required = true; }
  lat.min = '-90'; lat.max = '90'; lng.min = '-180'; lng.max = '180';
  if (p.pin) { lat.value = String(p.pin.lat); lng.value = String(p.pin.lng); }
  const latLabel = el('label', 'Latitude '); latLabel.append(lat);
  const lngLabel = el('label', 'Longitude '); lngLabel.append(lng);
  const submit = actionButton('Confirm location', () => form.requestSubmit());
  const coordinates = el('details'); coordinates.append(el('summary', 'Enter coordinates'), latLabel, lngLabel);
  form.append(coordinates, submit);
  form.onsubmit = (event) => { event.preventDefault(); if (form.reportValidity()) act('pin', { lat: Number(lat.value), lng: Number(lng.value) }); };
  host.append(mapHost, mapMessage, form);
  const map = mountMap(mapHost, p.pin, (pin) => { lat.value = String(pin.lat); lng.value = String(pin.lng); });
  for (const input of [lat,lng]) input.onchange = () => {
    if (lat.value && lng.value && lat.validity.valid && lng.validity.valid) map.setPin({ lat: Number(lat.value), lng: Number(lng.value) });
  };
  cleanupMap = map.destroy;
}

function renderOperator() {
  if (!operatorState) return;
  const state = operatorState;
  if (!state.sessions.some((s) => s.id === selectedSession)) selectedSession = state.sessions[0]?.id ?? '';
  const participants = state.participants.filter((p) => p.session_id === selectedSession);
  const key = `operator:${selectedSession}:${state.sessions.length}:${participants.map((p) => `${p.id}:${p.revision}`).join(',')}`;
  if (screenKey === key) { tick(); return; }
  screenKey = key; clearContent();
  const host = content();
  const actions = el('div', undefined, 'actions');
  actions.append(actionButton('New session / QR codes', () => void mutate('nys_create_session', { p_request_id: crypto.randomUUID() })),
    button('Sign out', () => { void api.logout().then(() => location.reload()); }));
  host.append(actions);
  const health = el('p'); health.id = 'health'; host.append(health);
  if (!state.sessions.length) { host.append(el('p', 'Create a session to get entry links for A and B.')); return; }
  const select = el('select'); select.setAttribute('aria-label', 'Session');
  for (const s of state.sessions) {
    const option = el('option', `${new Date(s.created_at).toLocaleString('en-GB')} · ${s.id.slice(0, 8)}`);
    option.value = s.id; select.append(option);
  }
  select.value = selectedSession;
  select.onchange = () => { selectedSession = select.value; sessionStorage.setItem('nys-selected-session', selectedSession); screenKey = ''; renderOperator(); };
  host.append(select);
  host.append(el('p', `Session ID: ${selectedSession}`, 'muted'));
  const grid = el('div', undefined, 'operator-grid');
  for (const p of participants) {
    const section = el('section'); section.dataset.participant = p.slot;
    section.append(el('h2', `Participant ${p.slot}`), el('p', `${statusNames[p.step]}${p.step === 'question' ? ` Q${p.question}` : ''} · ${statusNames[p.status]}`));
    const age = el('p', '', 'muted'); age.dataset.since = p.updated_at; section.append(age);
    if (p.error_code) section.append(el('p', `Error: ${p.error_code}`));
    const controls = el('div', undefined, 'actions');
    controls.append(actionButton(`Reset ${p.slot}`, () => operatorAct(p, 'reset')),
      actionButton('Stop and allow retry', () => operatorAct(p, 'recover'), !['countdown','processing','error'].includes(p.status)),
      actionButton('Reissue entry link', () => operatorAct(p, 'rotate_entry')));
    section.append(controls);
    const saved = entries[p.id];
    if (saved && saved.generation === p.generation) {
      const entryUrl = `${location.origin}/join#token=${encodeURIComponent(saved.token)}`;
      const canvas = el('canvas', undefined, 'qr'); canvas.setAttribute('aria-label', `Participant ${p.slot} entry QR`);
      void QRCode.toCanvas(canvas, entryUrl, { width: 180, margin: 1, errorCorrectionLevel: 'M' }).catch(handleError);
      const entryLink = link(`Open participant ${p.slot}`, entryUrl); entryLink.target = '_blank'; entryLink.rel = 'noopener noreferrer';
      section.append(canvas, entryLink, el('p', 'One browser per entry. Reissuing removes access from the previous browser.', 'muted'));
    } else section.append(el('p', 'Reissue the entry link to display a QR code.', 'muted'));
    grid.append(section);
  }
  host.append(grid); tick(); updatePending();
}

function tick() {
  const now = Date.now() + serverOffset;
  const countdown = document.querySelector('#countdown');
  if (countdown && snapshot?.participant.countdown_ends_at) {
    const remaining = Math.ceil((Date.parse(snapshot.participant.countdown_ends_at) - now) / 1000);
    const text = remaining > 0 ? String(Math.min(3, remaining)) : 'Please wait…';
    if (countdown.textContent !== text) countdown.textContent = text;
  }
  const health = document.querySelector('#health');
  if (health && operatorState) {
    const h = operatorState.health;
    const age = h ? Math.max(0, Math.floor((now - Date.parse(h.last_seen_at)) / 1000)) : null;
    health.textContent = age !== null ? `${age < 10 ? 'Connected' : 'No response'} · ${h!.mode === 'mock' ? 'Mock worker' : 'Local system'} · ${age}s ago` : 'Waiting for the local system';
  }
  document.querySelectorAll<HTMLElement>('[data-since]').forEach((node) => {
    node.textContent = `Last change: ${Math.max(0, Math.floor((now - Date.parse(node.dataset.since!)) / 1000))}s ago`;
  });
}
async function refresh() {
  if (refreshing || revoked || !api.userId || (!isOperator && !participantId)) return;
  refreshing = true;
  try {
    const start = Date.now();
    if (isOperator) {
      operatorState = await api.call<OperatorState>('nys_operator_state');
      serverOffset = Date.parse(operatorState.server_now) - (start + Date.now()) / 2;
      renderOperator();
    } else {
      const incoming = await api.call<Snapshot>('nys_snapshot', { p_id: participantId });
      // Ignore a delayed fetch older than a mutation response already rendered.
      if (!snapshot || incoming.participant.generation > snapshot.participant.generation ||
        (incoming.participant.generation === snapshot.participant.generation && incoming.participant.revision >= snapshot.participant.revision)) snapshot = incoming;
      serverOffset = Date.parse(incoming.server_now) - (start + Date.now()) / 2;
      renderParticipant();
    }
    if (networkError) message();
    networkError = false;
  } catch (error) { handleError(error); }
  finally { refreshing = false; updatePending(); }
}
function loginScreen() {
  clearContent();
  const form = el('form'); const email = el('input'); email.type = 'email'; email.autocomplete = 'username';
  const password = el('input'); password.type = 'password'; password.autocomplete = 'current-password';
  if (!demo) {
    email.required = true; password.required = true;
    const e = el('label', 'Email '); e.append(email); const p = el('label', 'Password '); p.append(password); form.append(e,p);
  }
  const submit = button(demo ? 'Open operator demo' : 'Sign in', () => form.requestSubmit()); form.append(submit);
  form.onsubmit = async (event) => {
    event.preventDefault(); submit.disabled = true;
    try { await api.login(email.value, password.value); await startState(); }
    catch (error) { handleError(error); }
    finally { submit.disabled = false; }
  };
  content().append(form);
}
async function startState() {
  if (isOperator && !await api.call<boolean>('nys_is_operator')) {
    await api.logout();
    loginScreen();
    message('Operator access required. Please sign in with an authorised account.');
    return;
  }
  await refresh();
  unsubscribe?.(); unsubscribe = api.subscribe(participantId, () => { void refresh(); });
  // Refetch after subscription setup; periodic reads repair missed realtime events.
  await refresh();
}
async function start() {
  shell();
  if (!configured) {
    content().append(el('p', 'Connection is not configured. Please ask the operator.'));
    return;
  }
  if (location.pathname === '/') {
    content().append(el('p', 'Please scan your QR code.'), link('Operator', '/operator'));
    return;
  }
  try {
    await api.init();
    if (isOperator && !api.userId) { loginScreen(); return; }
    if (location.pathname === '/join') {
      const token = new URLSearchParams(location.hash.slice(1)).get('token');
      if (!token) throw new ApiError('ENTRY_EXPIRED');
      snapshot = await api.call<Snapshot>('nys_join', { p_token: token });
      participantId = snapshot.participant.id;
      history.replaceState(null, '', `/participant/${participantId}`);
    }
    if (!isOperator && !participantId) { content().append(el('p', 'Please scan your QR code.')); return; }
    await startState(); updatePending();
  } catch (error) {
    handleError(error);
    content().append(button('Reload', () => location.reload()));
  }
}
window.addEventListener('popstate', () => { screenKey = ''; renderParticipant(); void refresh(); });
window.addEventListener('online', () => { void refresh(); });
window.addEventListener('offline', () => { handleError(new ApiError('OFFLINE', true)); });
window.addEventListener('focus', () => { void refresh(); });
document.addEventListener('visibilitychange', () => { if (!document.hidden) void refresh(); });
setInterval(() => { if (!document.hidden) void refresh(); }, 1500);
setInterval(tick, 250);
void start();
