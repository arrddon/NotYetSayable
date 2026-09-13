import { before, after, beforeEach, test } from 'node:test';
import assert from 'node:assert/strict';
import { randomUUID } from 'node:crypto';
import { openDatabase, rpc, asRole, OPERATOR_ID } from '../tools/database.mjs';
import { mockResult } from '../tools/mock-processing.mjs';

let db;
const users = { A: randomUUID(), B: randomUUID(), outsider: randomUUID() };
const op = (name, args) => rpc(db, OPERATOR_ID, name, args);
const worker = (name, args) => rpc(db, null, name, args, 'service_role');
const call = (slot, name, args) => rpc(db, users[slot], name, args);
before(async () => { db = await openDatabase(); });
after(async () => { await db.close(); });
beforeEach(async () => {
  await db.exec('truncate public.sessions, public.participants, public.jobs, public.responses, nys_private.entries, nys_private.receipts, public.worker_health cascade');
});
async function pair() {
  const created = await op('nys_create_session', { p_request_id: randomUUID() });
  const states = {};
  for (const entry of created.entries) states[entry.slot] = await call(entry.slot, 'nys_join', { p_token: entry.token });
  return { ...states, created };
}
function args(s, action, data = {}, request = randomUUID()) {
  const p = s.participant;
  return { p_id: p.id, p_generation: p.generation, p_revision: p.revision, p_request_id: request, p_action: action, p_data: data };
}
async function action(s, name, data) { return call(s.participant.slot, 'nys_action', args(s, name, data)); }
async function ready(s) { return action(await action(s, 'consent'), 'tutorial'); }
async function due(s) {
  await db.query("update public.jobs set not_before = now() - interval '1 second' where id = $1", [s.participant.active_job_id]);
  return worker('nys_worker_claim', { p_mode: 'mock' });
}
async function finish(job, error = null) {
  return worker('nys_worker_finish', { p_job_id: job.id, p_lease_id: job.lease_id, p_result: mockResult(job), p_error: error });
}
async function snapshot(s) { return call(s.participant.slot, 'nys_snapshot', { p_id: s.participant.id }); }
async function completeQuestion(s) {
  const confirmed = await action(s, 'confirm');
  await finish(await due(confirmed));
  return snapshot(confirmed);
}

test('A and B progress independently; all four answers are required before pinning', async () => {
  let { A, B } = await pair();
  A = await ready(A);
  for (let q = 1; q <= 4; q++) {
    assert.equal(A.participant.question, q);
    await assert.rejects(action(A, 'pin', { lat: 0, lng: 0 }), /INVALID_TRANSITION/);
    A = await completeQuestion(A);
    A = await action(A, 'continue');
  }
  assert.equal(A.participant.step, 'map');
  await assert.rejects(action(A, 'pin', { lat: 91, lng: 0 }), /INVALID_COORDINATES/);
  A = await action(A, 'pin', { lat: 51.5, lng: -0.1 });
  assert.equal(A.participant.step, 'complete');
  assert.equal(A.responses.length, 4);
  B = await snapshot(B);
  assert.equal(B.participant.step, 'consent');
});

test('same request is idempotent; concurrent double-click with another ID is rejected', async () => {
  let { A } = await pair(); A = await ready(A);
  const request = args(A, 'confirm');
  const [first, second] = await Promise.all([call('A','nys_action',request),call('A','nys_action',request)]);
  assert.equal(first.participant.active_job_id, second.participant.active_job_id);
  await assert.rejects(action(A, 'confirm'), /STALE_STATE/);
  assert.equal((await db.query('select count(*)::int as n from public.jobs')).rows[0].n, 1);
  await assert.rejects(call('A','nys_action',{ ...request, p_action: 'retry' }), /REQUEST_REUSED/);
});

test('server countdown survives refresh; concurrent A/B jobs remain separate', async () => {
  let { A, B } = await pair(); A = await ready(A); B = await ready(B);
  [A,B] = await Promise.all([action(A,'confirm'),action(B,'confirm')]);
  assert.notEqual(A.participant.active_job_id, B.participant.active_job_id);
  assert.equal(await worker('nys_worker_claim',{ p_mode:'mock' }), null);
  const refreshed = await snapshot(A);
  assert.equal(refreshed.participant.countdown_ends_at, A.participant.countdown_ends_at);
  const ja = await due(A); const jb = await due(B);
  assert.notEqual(ja.id, jb.id);
  await finish(jb); await finish(ja);
  assert.equal((await snapshot(A)).responses[0].result.raw_response.includes('Participant A'), true);
  assert.equal((await snapshot(B)).responses[0].result.raw_response.includes('Participant B'), true);
});

test('reset A cancels old work, revokes its QR/browser, and does not reset B', async () => {
  let { A, B, created } = await pair(); A = await ready(A); B = await ready(B);
  A = await action(A,'confirm'); const job = await due(A); A = await snapshot(A);
  const resetArgs = args(A,'reset'); delete resetArgs.p_data;
  const reset = await op('nys_operator_action', resetArgs);
  assert.equal(await finish(job), false);
  await assert.rejects(snapshot(A), /FORBIDDEN/);
  await assert.rejects(call('A','nys_join',{ p_token: created.entries[0].token }), /ENTRY_EXPIRED/);
  const joined = await call('A','nys_join',{ p_token: reset.token });
  assert.equal(joined.participant.generation, 2);
  assert.equal(joined.responses.length, 0);
  assert.equal((await snapshot(B)).participant.step, 'question');
  assert.equal((await op('nys_operator_action', resetArgs)).token, reset.token);
});

test('retry replaces one response; stale attempts cannot overwrite the replacement', async () => {
  let { A } = await pair(); A = await ready(A);
  A = await action(A,'confirm'); const old = await due(A); await finish(old);
  A = await snapshot(A); A = await action(A,'continue');
  A = await action(A,'revisit',{ question:1 }); A = await action(A,'confirm');
  assert.equal(A.responses.length, 0);
  const replacement = await due(A); assert.equal(replacement.attempt, 2);
  assert.equal(await finish(old), false);
  await finish(replacement); A = await snapshot(A);
  assert.equal(A.responses.length, 1);
  assert.equal(A.responses[0].attempt, 2);
  A = await action(A,'continue'); assert.equal(A.participant.question, 2);
});

test('failure, operator recovery, timeout and retry never skip the question', async () => {
  let { A } = await pair(); A = await ready(A);
  A = await action(A,'confirm'); let job = await due(A); await finish(job, 'OCR_FAILED');
  A = await snapshot(A); assert.equal(A.participant.status, 'error');
  await assert.rejects(action(A,'continue'), /INVALID_TRANSITION/);
  A = await action(A,'retry'); job = await due(A); A = await snapshot(A);
  const recovery = args(A,'recover'); delete recovery.p_data;
  await op('nys_operator_action',recovery);
  assert.equal(await finish(job), false);
  A = await snapshot(A); A = await action(A,'retry');
  await db.query("update public.jobs set deadline = now() - interval '1 second' where id = $1", [A.participant.active_job_id]);
  await worker('nys_worker_claim',{ p_mode:'mock' });
  A = await snapshot(A); assert.equal(A.participant.error_code, 'TIMEOUT');
  A = await action(A,'retry'); await finish(await due(A)); A = await snapshot(A);
  assert.equal(A.participant.status, 'result'); assert.equal(A.participant.question, 1);
});

test('participants cannot access another participant, operator commands, worker RPCs, or direct writes', async () => {
  const { A, B } = await pair();
  await assert.rejects(call('B','nys_snapshot',{ p_id:A.participant.id }), /FORBIDDEN/);
  await assert.rejects(call('B','nys_action',args(A,'consent')), /FORBIDDEN/);
  await assert.rejects(call('B','nys_create_session',{ p_request_id:randomUUID() }), /FORBIDDEN/);
  await assert.rejects(call('B','nys_worker_claim',{ p_mode:'mock' }), /permission denied/);
  await assert.rejects(asRole(db,users.B,'authenticated',(tx) => tx.query("update public.participants set step='complete' where id=$1",[B.participant.id])), /permission denied/);
  await assert.rejects(asRole(db,users.B,'authenticated',(tx) => tx.query('select * from nys_private.entries')), /permission denied/);
  const visible = await asRole(db,users.B,'authenticated',(tx) => tx.query('select id from public.participants'));
  assert.deepEqual(visible.rows.map((x) => x.id), [B.participant.id]);
  const anon = await asRole(db,null,'anon',(tx) => tx.query("select has_function_privilege('anon','public.nys_join(text)','execute') as allowed"));
  assert.equal(anon.rows[0].allowed, false);
});

test('RLS hides responses from previous generations even after a new browser joins', async () => {
  let { A } = await pair(); A = await completeQuestion(await ready(A));
  const resetArgs = args(A,'reset'); delete resetArgs.p_data;
  const reset = await op('nys_operator_action',resetArgs);
  await call('outsider','nys_join',{ p_token:reset.token });
  const rows = await asRole(db,users.outsider,'authenticated',(tx) => tx.query('select * from public.responses'));
  assert.equal(rows.rows.length, 0);
  assert.equal((await db.query('select count(*)::int as n from public.responses')).rows[0].n, 1);
});

test('QR binds to one browser; rotation preserves answers and revokes previous owner', async () => {
  let { A, created } = await pair(); A = await completeQuestion(await ready(A));
  await assert.rejects(call('outsider','nys_join',{ p_token:created.entries[0].token }), /ENTRY_IN_USE/);
  const request = args(A,'rotate_entry'); delete request.p_data;
  const rotated = await op('nys_operator_action',request);
  await assert.rejects(snapshot(A), /FORBIDDEN/);
  const joined = await call('outsider','nys_join',{ p_token:rotated.token });
  assert.equal(joined.responses.length, 1);
  assert.equal(joined.participant.generation, 1);
});

test('creating sessions is idempotent and worker results require the correct lease and schema', async () => {
  const req = { p_request_id:randomUUID() };
  const first = await op('nys_create_session',req);
  assert.deepEqual(await op('nys_create_session',req), first);
  assert.equal((await db.query('select count(*)::int as n from public.sessions')).rows[0].n, 1);
  let A = await call('A','nys_join',{ p_token:first.entries[0].token });
  A = await action(await ready(A),'confirm'); const job = await due(A);
  assert.equal(await worker('nys_worker_finish',{p_job_id:job.id,p_lease_id:randomUUID(),p_result:mockResult(job),p_error:null}),false);
  await assert.rejects(worker('nys_worker_finish',{p_job_id:job.id,p_lease_id:job.lease_id,p_result:{},p_error:null}), /INVALID_RESULT/);
  assert.equal(await finish(job), true);
  assert.equal(await finish(job), true);
  assert.equal((await snapshot(A)).responses.length, 1);
});
